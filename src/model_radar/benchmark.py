"""
Quick coding benchmark for free models.

Runs a set of small, objectively verifiable challenges against a model
and scores pass/fail. Designed to catch common failure modes: bad math,
hallucination, instruction ignoring, broken code, garbled output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .config import load_config
from .providers import PROVIDERS, Model
from .quality import record_benchmark
from .runner import _call_model
from .scanner import ScanState, scan_models


@dataclass(frozen=True, slots=True)
class Challenge:
    name: str
    category: str  # math, code, instruction, reasoning
    system_prompt: str
    prompt: str
    max_tokens: int
    validate: str  # name of validation function


# ---------------------------------------------------------------------------
# Validation helpers — each returns (passed: bool, detail: str)
# ---------------------------------------------------------------------------

def _check_math_5461(response: str) -> tuple[bool, str]:
    """127 * 43 = 5461"""
    if "5461" in response:
        return True, "correct: 5461 found"
    return False, f"expected 5461, got: {response[:80]}"


def _check_exact_hello(response: str) -> tuple[bool, str]:
    """Must contain exactly HELLO WORLD."""
    cleaned = response.strip()
    if "HELLO WORLD" in cleaned.upper():
        return True, "correct: HELLO WORLD found"
    return False, f"expected 'HELLO WORLD', got: {cleaned[:80]}"


def _check_is_prime(response: str) -> tuple[bool, str]:
    """Must contain a def is_prime function with basic structure."""
    if "def is_prime" not in response:
        return False, "missing 'def is_prime'"
    # Should have a return True and return False (or boolean logic)
    has_true = "True" in response or "true" in response
    has_false = "False" in response or "false" in response
    if has_true and has_false:
        return True, "correct: is_prime function with boolean returns"
    # Some implementations use return n % i != 0 style
    if "return" in response and ("%" in response or "mod" in response.lower()):
        return True, "correct: is_prime function with modulo logic"
    return False, f"is_prime function looks incomplete"


def _check_list_comp(response: str) -> tuple[bool, str]:
    """print([x**2 for x in range(5)]) should output [0, 1, 4, 9, 16]."""
    if "[0, 1, 4, 9, 16]" in response:
        return True, "correct: [0, 1, 4, 9, 16]"
    # Also accept without spaces
    if "[0,1,4,9,16]" in response:
        return True, "correct: [0,1,4,9,16]"
    return False, f"expected [0, 1, 4, 9, 16], got: {response[:80]}"


def _check_json_output(response: str) -> tuple[bool, str]:
    """Must output valid JSON with name='test' and value=42."""
    # Extract JSON from response (may be wrapped in markdown code blocks)
    text = response.strip()
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Try to find JSON in the response
        match = re.search(r"\{[^}]+\}", response)
        if match:
            try:
                obj = json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                return False, f"invalid JSON: {text[:80]}"
        else:
            return False, f"no JSON found: {text[:80]}"
    if obj.get("name") == "test" and obj.get("value") == 42:
        return True, "correct: valid JSON with name=test, value=42"
    return False, f"wrong values: {obj}"


# Map of validator name -> function
_VALIDATORS: dict[str, callable] = {
    "math_5461": _check_math_5461,
    "exact_hello": _check_exact_hello,
    "is_prime": _check_is_prime,
    "list_comp": _check_list_comp,
    "json_output": _check_json_output,
}


# ---------------------------------------------------------------------------
# Challenge set
# ---------------------------------------------------------------------------

CHALLENGES = (
    Challenge(
        name="arithmetic",
        category="math",
        system_prompt="You are a calculator. Reply with only the number, nothing else.",
        prompt="What is 127 * 43?",
        max_tokens=32,
        validate="math_5461",
    ),
    Challenge(
        name="instruction_following",
        category="instruction",
        system_prompt="Follow instructions exactly. Output only what is asked.",
        prompt="Reply with exactly: HELLO WORLD",
        max_tokens=32,
        validate="exact_hello",
    ),
    Challenge(
        name="code_generation",
        category="code",
        system_prompt="You are a Python expert. Output only code, no explanation.",
        prompt="Write a Python function `is_prime(n)` that returns True if n is prime, False otherwise.",
        max_tokens=256,
        validate="is_prime",
    ),
    Challenge(
        name="code_reasoning",
        category="reasoning",
        system_prompt="You are a Python expert. Be concise.",
        prompt="What does this Python code print?\n\nprint([x**2 for x in range(5)])",
        max_tokens=64,
        validate="list_comp",
    ),
    Challenge(
        name="json_output",
        category="instruction",
        system_prompt="You are a helpful assistant. Output only valid JSON, nothing else.",
        prompt='Output a JSON object with key "name" set to "test" and key "value" set to 42.',
        max_tokens=64,
        validate="json_output",
    ),
)


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

async def benchmark_model(model: Model, cfg: dict) -> dict:
    """Run all challenges against a single model and return scores."""
    results = []
    passed = 0

    for challenge in CHALLENGES:
        messages = [
            {"role": "system", "content": challenge.system_prompt},
            {"role": "user", "content": challenge.prompt},
        ]
        resp = await _call_model(
            model=model,
            messages=messages,
            cfg=cfg,
            max_tokens=challenge.max_tokens,
            temperature=0.0,
        )

        if "error" in resp:
            results.append({
                "challenge": challenge.name,
                "category": challenge.category,
                "passed": False,
                "detail": f"API error: {resp['error']}",
                "latency_ms": resp.get("latency_ms"),
            })
            continue

        content = resp.get("content", "")
        validator = _VALIDATORS[challenge.validate]
        ok, detail = validator(content)

        if ok:
            passed += 1

        results.append({
            "challenge": challenge.name,
            "category": challenge.category,
            "passed": ok,
            "detail": detail,
            "latency_ms": resp.get("latency_ms"),
            "response_preview": content[:120],
        })

    score_data = {
        "model_id": model.model_id,
        "model_label": model.label,
        "provider": PROVIDERS[model.provider].name,
        "provider_key": model.provider,
        "tier": model.tier,
        "passed": passed,
        "total": len(CHALLENGES),
        "score": f"{passed}/{len(CHALLENGES)}",
        "pct": round(passed / len(CHALLENGES) * 100),
        "results": results,
    }

    # Persist quality score for future recommendations
    record_benchmark(model.model_id, passed, len(CHALLENGES),
                     details=[{"name": r["challenge"], "passed": r["passed"]}
                              for r in results])

    return score_data


async def benchmark_models(
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str = "A",
    count: int = 3,
    state: ScanState | None = None,
) -> list[dict]:
    """
    Benchmark one or more models.

    If model_id is given, benchmarks that specific model.
    Otherwise, scans for the fastest `count` UP models and benchmarks each.
    """
    cfg = load_config()

    if model_id:
        # Find the specific model
        target = None
        for pkey, prov in PROVIDERS.items():
            if provider and pkey != provider:
                continue
            for mid, label, tier, swe, ctx in prov.models:
                if mid == model_id:
                    target = Model(
                        model_id=mid, label=label, tier=tier,
                        swe_score=swe, context=ctx, provider=pkey,
                    )
                    break
            if target:
                break
        if not target:
            return [{"error": f"Model '{model_id}' not found in registry"}]
        models = [target]
    else:
        # Scan and pick the fastest UP models
        results = await scan_models(
            min_tier=min_tier, provider=provider,
            configured_only=True, limit=count * 2,  # scan extra in case some are down
            state=state,
        )
        up_models = [r.model for r in results if r.status == "up"]
        if not up_models:
            return [{"error": "No models available. Check API keys with list_providers()."}]
        models = up_models[:count]

    # Benchmark each model
    scores = []
    for model in models:
        result = await benchmark_model(model, cfg)
        scores.append(result)

    # Sort by score descending, then by total latency
    scores.sort(
        key=lambda s: (
            -s["pct"],
            sum(r.get("latency_ms", 0) or 0 for r in s["results"]),
        )
    )

    return scores
