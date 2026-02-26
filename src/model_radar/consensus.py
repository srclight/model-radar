"""
Multi-model consensus — run the same prompt on N models in parallel.

Returns all responses so the calling agent can compare, verify, and
pick the best answer. Useful for high-stakes queries where you want
multiple independent opinions.
"""

from __future__ import annotations

import asyncio

from .config import load_config
from .providers import PROVIDERS, Model
from .quality import get_model_quality
from .runner import _call_model
from .scanner import ScanState, scan_models


async def ask_models(
    prompt: str,
    system_prompt: str | None = None,
    count: int = 3,
    min_tier: str = "A",
    provider: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    state: ScanState | None = None,
) -> dict:
    """
    Run the same prompt on multiple models in parallel.

    Scans for the fastest `count` UP models and sends the prompt to all
    of them simultaneously. Returns all responses for comparison.
    """
    cfg = load_config()

    # Scan for available models
    results = await scan_models(
        min_tier=min_tier, provider=provider,
        configured_only=True, limit=count * 2,
        state=state,
    )
    up_models = [r.model for r in results if r.status == "up"]

    if not up_models:
        return {
            "error": "No models available. Check API keys with list_providers().",
        }

    targets = up_models[:count]

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
