"""
Multi-model consensus — run the same prompt on N models in parallel.

Returns all responses so the calling agent can compare, verify, and
pick the best answer. Useful for high-stakes queries where you want
multiple independent opinions.
"""

from __future__ import annotations

import asyncio

from .cli_provider import is_cli_provider
from .config import load_config
from .providers import PROVIDERS, Model, get_all_models
from .quality import get_model_quality
from .runner import _call_model
from .scanner import ScanState, scan_models


def resolve_model_ref(ref: str) -> Model | None:
    """Resolve 'sonnet', 'grok-4.6', or 'claude/sonnet' to a Model.

    Exact model_id wins (NVIDIA ids contain slashes). Then provider/id
    if the left side is a known provider key.
    """
    models = get_all_models()
    exact = [m for m in models if m.model_id == ref]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return exact[0]
    if "/" in ref:
        left, right = ref.split("/", 1)
        if left in PROVIDERS:
            for m in models:
                if m.provider == left and m.model_id == right:
                    return m
    return None


def _best_model_for_provider(provider_key: str) -> Model | None:
    models = [m for m in get_all_models() if m.provider == provider_key]
    if not models:
        return None
    from .providers import TIER_ORDER
    models.sort(key=lambda m: TIER_ORDER.get(m.tier, 99))
    return models[0]


async def ask_models(
    prompt: str,
    system_prompt: str | None = None,
    count: int = 3,
    min_tier: str = "A",
    provider: str | None = None,
    providers: list[str] | None = None,
    model_ids: list[str] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    state: ScanState | None = None,
) -> dict:
    """
    Run the same prompt on multiple models in parallel.

    Pinning:
      model_ids=["sonnet", "grok-4.6"]  — exact models (subscription opt-in)
      providers=["claude", "grok"]      — best model on each named provider
    Otherwise scans for the fastest `count` HTTPS models. Subscription CLIs
    are never auto-picked — they exist to ride a monthly plan, so a host
    must name them.
    """
    cfg = load_config()
    targets: list[Model] = []
    missing: list[str] = []

    if model_ids:
        for ref in model_ids:
            model = resolve_model_ref(ref)
            if model is None:
                missing.append(ref)
            else:
                targets.append(model)
        if missing:
            return {
                "error": f"Unknown model_ids: {missing}. "
                         f"Use list_models() or provider/model_id (e.g. claude/sonnet).",
                "unknown": missing,
            }
    elif providers:
        for key in providers:
            if key not in PROVIDERS:
                missing.append(key)
                continue
            model = _best_model_for_provider(key)
            if model is None:
                missing.append(key)
            else:
                targets.append(model)
        if missing and not targets:
            return {
                "error": f"Unknown or empty providers: {missing}.",
                "unknown": missing,
            }
    elif provider and is_cli_provider(provider):
        # CLI models live in PROVIDERS, not necessarily in the ping DB.
        model = _best_model_for_provider(provider)
        if model:
            targets = [model]
    else:
        results = await scan_models(
            min_tier=min_tier, provider=provider,
            configured_only=True, limit=count * 4,
            state=state,
        )
        up_models = [r.model for r in results if r.status == "up"]
        # Default ask never burns a subscription quota.
        up_models = [m for m in up_models if not is_cli_provider(m.provider)]
        targets = up_models[:count]

    if not targets:
        return {
            "error": "No models available. Check API keys with list_providers(), "
                     "or pin subscriptions with model_ids=/providers=.",
        }

    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Run all models in parallel
    tasks = [
        _call_model(
            model=m, messages=messages, cfg=cfg,
            max_tokens=max_tokens, temperature=temperature,
        )
        for m in targets
    ]
    raw_results = await asyncio.gather(*tasks)

    # Build structured responses
    responses = []
    for result in raw_results:
        entry = {
            "model_id": result.get("model_id", "unknown"),
            "model_label": result.get("model_label", "unknown"),
            "provider": result.get("provider", "unknown"),
            "tier": result.get("tier", "unknown"),
            "latency_ms": result.get("latency_ms"),
        }
        # Include quality score if available
        mid = result.get("model_id", "")
        quality = get_model_quality(mid)
        if quality:
            entry["quality_pct"] = quality["pct"]

        if "error" in result:
            entry["error"] = result["error"]
            entry["content"] = None
        else:
            entry["content"] = result.get("content", "")
            entry["usage"] = result.get("usage")
            if result.get("think_content"):
                entry["think_content"] = result["think_content"]
            if "raw_response" in result:
                entry["raw_response"] = result["raw_response"]

        responses.append(entry)

    succeeded = [r for r in responses if r.get("content") is not None]
    failed = [r for r in responses if r.get("error")]

    return {
        "prompt": prompt,
        "models_queried": len(targets),
        "models_responded": len(succeeded),
        "models_failed": len(failed),
        "responses": responses,
    }
