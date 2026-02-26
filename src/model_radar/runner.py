"""
Run prompts on free coding models.

Picks the fastest available model (or a specified one) and sends
a chat/completions request, returning the full response.
"""

from __future__ import annotations

import os
import time

import httpx

from .config import get_api_key, load_config
from .providers import PROVIDERS, Model
from .scanner import ScanState, scan_models


async def _call_model(
    model: Model,
    messages: list[dict],
    cfg: dict,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> dict:
    """Send a chat/completions request to a model and return the response."""
    api_key = get_api_key(cfg, model.provider)
    if not api_key:
        return {"error": f"No API key for provider {model.provider}"}

    prov = PROVIDERS[model.provider]
    url = prov.url

    # Cloudflare needs account_id
    if model.provider == "cloudflare":
        acct = cfg.get("cloudflare_account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        url = url.replace("{account_id}", acct)

    # Google AI uses key param
    if model.provider == "googleai":
        url = f"{url}?key={api_key}"

    headers = {"Content-Type": "application/json"}
    if model.provider == "replicate":
        headers["Authorization"] = f"Token {api_key}"
    elif model.provider != "googleai":
        headers["Authorization"] = f"Bearer {api_key}"

    # Replicate uses a different format
    if model.provider == "replicate":
        # Replicate predictions API — simplified, just send the last user message
        last_msg = messages[-1]["content"] if messages else ""
        payload = {"input": {"prompt": last_msg}, "version": model.model_id}
    else:
        payload = {
            "model": model.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=120.0)
        elapsed_ms = (time.monotonic() - start) * 1000

    if resp.status_code not in (200, 201):
        return {
            "error": f"HTTP {resp.status_code}",
            "detail": resp.text[:500],
            "model": model.label,
            "provider": prov.name,
        }

    data = resp.json()

    # Extract the response text
    content = ""
    if model.provider == "replicate":
        # Replicate returns output as a list of strings
        output = data.get("output", [])
        content = "".join(output) if isinstance(output, list) else str(output)
    else:
        # OpenAI-compatible format
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")

    usage = data.get("usage", {})

    return {
        "content": content,
        "model_id": model.model_id,
        "model_label": model.label,
        "provider": prov.name,
        "provider_key": model.provider,
        "tier": model.tier,
        "latency_ms": round(elapsed_ms, 1),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
    }


async def run_on_fastest(
    prompt: str,
    system_prompt: str | None = None,
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str = "A",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    state: ScanState | None = None,
) -> dict:
    """
    Run a prompt on the fastest available model.

    If model_id is provided, uses that model directly (skips scanning).
    Otherwise, pings configured models and picks the fastest one.
    """
    cfg = load_config()

    if model_id:
        # Find the model in our registry
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
            return {"error": f"Model '{model_id}' not found in registry"}
    else:
        # Scan and pick the fastest UP model
        results = await scan_models(
            min_tier=min_tier, provider=provider,
            configured_only=True, limit=5, state=state,
        )
        up_results = [r for r in results if r.status == "up"]
        if not up_results:
            return {
                "error": "No models available. Check API keys with list_providers().",
            }
        target = up_results[0].model

    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    return await _call_model(
        model=target, messages=messages, cfg=cfg,
        max_tokens=max_tokens, temperature=temperature,
    )
