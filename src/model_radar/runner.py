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
    usage = data.get("usage", {})

    # Extract the response text
    content = ""
    if model.provider == "replicate":
        # Replicate returns output as a list of strings
        output = data.get("output", [])
        content = "".join(output) if isinstance(output, list) else str(output)
    else:
        # OpenAI-compatible format (content can be str, null, or list of parts)
        choices = data.get("choices", [])
        if choices:
            choice = choices[0] if isinstance(choices[0], dict) else {}
            msg = choice.get("message", {}) or {}
            raw = msg.get("content")
            if raw is None:
                content = ""
            elif isinstance(raw, list):
                # Multimodal: [{"type": "text", "text": "..."}, ...]
                content = "".join(
                    p.get("text", "") for p in raw if isinstance(p, dict) and p.get("type") == "text"
                )
            else:
                content = str(raw) if raw else ""
            # Some providers put text in choice.text, message.text, or reasoning when content is null
            if not content and usage.get("completion_tokens"):
                content = (
                    choice.get("text")
                    or msg.get("text")
                    or msg.get("reasoning")
                    or msg.get("reasoning_content")
                    or ""
                )
                if content and not isinstance(content, str):
                    content = str(content)
            if not content and isinstance(msg.get("content"), list):
                # Unstructured list of parts: just concat any string we find
                for part in msg.get("content") or []:
                    if isinstance(part, dict) and part.get("text"):
                        content += part.get("text", "")
                    elif isinstance(part, str):
                        content += part

    # Expose full raw API response body for debugging
    raw_response = data if resp.status_code in (200, 201) else None

    out = {
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
    if raw_response is not None:
        out["raw_response"] = raw_response
    return out


def _find_model(model_id: str, provider: str | None = None) -> Model | None:
    """Look up a model in the registry by ID."""
    for pkey, prov in PROVIDERS.items():
        if provider and pkey != provider:
            continue
        for mid, label, tier, swe, ctx in prov.models:
            if mid == model_id:
                return Model(
                    model_id=mid, label=label, tier=tier,
                    swe_score=swe, context=ctx, provider=pkey,
                )
    return None


async def run_on_fastest(
    prompt: str,
    system_prompt: str | None = None,
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str = "A",
    free_only: bool = False,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    state: ScanState | None = None,
    max_retries: int = 3,
) -> dict:
    """
    Run a prompt on the fastest available model with automatic fallback.

    If model_id is provided, uses that model directly (no fallback).
    Otherwise, pings configured models and tries the fastest ones in order.
    Set free_only=True to restrict to models marked as free (from API or :free/-free in id).
    On failure (429, timeout, error), automatically retries on the next
    fastest model up to max_retries times.
    """
    cfg = load_config()

    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    if model_id:
        # Specific model — no fallback
        target = _find_model(model_id, provider)
        if not target:
            return {"error": f"Model '{model_id}' not found in registry"}
        return await _call_model(
            model=target, messages=messages, cfg=cfg,
            max_tokens=max_tokens, temperature=temperature,
        )

    # Scan and try models in order with fallback
    results = await scan_models(
        min_tier=min_tier, provider=provider,
        configured_only=True, free_only=free_only,
        limit=max_retries + 2, state=state,
    )
    up_results = [r for r in results if r.status == "up"]
    if not up_results:
        return {
            "error": "No models available. Check API keys with list_providers().",
        }

    retries = []
    for i, ping_result in enumerate(up_results[:max_retries]):
        result = await _call_model(
            model=ping_result.model, messages=messages, cfg=cfg,
            max_tokens=max_tokens, temperature=temperature,
        )
        if "error" not in result:
            if retries:
                result["retries"] = retries
            return result
        # Record the failure and try next model
        retries.append({
            "model_id": ping_result.model.model_id,
            "model_label": ping_result.model.label,
            "error": result["error"],
        })

    # All retries exhausted
    return {
        "error": f"All {len(retries)} models failed. Tried: "
                 + ", ".join(r["model_label"] for r in retries),
        "retries": retries,
    }
