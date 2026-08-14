"""Best-effort credit / quota reads. Most hosts have no balance API.

Never returns secrets. Unknown providers are skipped, not invented.
"""

from __future__ import annotations

import httpx

from .config import get_api_key, load_config


def _auth(cfg: dict, provider: str) -> dict | None:
    key = get_api_key(cfg, provider)
    if not key or key == "local":
        return None
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def _openrouter(cfg: dict) -> dict:
    headers = _auth(cfg, "openrouter")
    if not headers:
        return {"provider": "openrouter", "ok": False, "error": "no key"}
    r = httpx.get("https://openrouter.ai/api/v1/credits", headers=headers, timeout=15.0)
    if r.status_code != 200:
        return {"provider": "openrouter", "ok": False, "http": r.status_code}
    data = (r.json() or {}).get("data") or {}
    purchased = float(data.get("total_credits") or 0)
    used = float(data.get("total_usage") or 0)
    return {
        "provider": "openrouter",
        "ok": True,
        "kind": "prepaid_usd",
        "purchased": purchased,
        "used": used,
        "remaining": round(purchased - used, 4),
    }


def _siliconflow(cfg: dict) -> dict:
    headers = _auth(cfg, "siliconflow")
    if not headers:
        return {"provider": "siliconflow", "ok": False, "error": "no key"}
    r = httpx.get("https://api.siliconflow.com/v1/user/info", headers=headers, timeout=15.0)
    if r.status_code != 200:
        return {"provider": "siliconflow", "ok": False, "http": r.status_code}
    data = (r.json() or {}).get("data") or {}
    return {
        "provider": "siliconflow",
        "ok": True,
        "kind": "prepaid_balance",
        "remaining": data.get("totalBalance") or data.get("balance"),
        "charge_balance": data.get("chargeBalance"),
    }


def _groq_quota(cfg: dict) -> dict:
    """Groq has no dollar balance. Remaining free-tier rate limits from one tiny call."""
    headers = _auth(cfg, "groq")
    if not headers:
        return {"provider": "groq", "ok": False, "error": "no key"}
    headers["Content-Type"] = "application/json"
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1,
        },
        timeout=20.0,
    )
    if r.status_code not in (200, 429):
        return {"provider": "groq", "ok": False, "http": r.status_code}
    return {
        "provider": "groq",
        "ok": True,
        "kind": "rate_limit",
        "remaining_requests_day": r.headers.get("x-ratelimit-remaining-requests"),
        "limit_requests_day": r.headers.get("x-ratelimit-limit-requests"),
        "remaining_tokens_minute": r.headers.get("x-ratelimit-remaining-tokens"),
        "limit_tokens_minute": r.headers.get("x-ratelimit-limit-tokens"),
    }


_HANDLERS = {
    "openrouter": _openrouter,
    "siliconflow": _siliconflow,
    "groq": _groq_quota,
}


def fetch_credits(provider: str | None = None, cfg: dict | None = None) -> dict:
    """Query hosts that expose a credit or quota API."""
    cfg = cfg if cfg is not None else load_config()
    if provider:
        fn = _HANDLERS.get(provider)
        if not fn:
            return {
                "error": f"No credit API for '{provider}'",
                "supported": sorted(_HANDLERS),
            }
        return {"results": [fn(cfg)]}
    results = []
    for key, fn in _HANDLERS.items():
        if get_api_key(cfg, key):
            try:
                results.append(fn(cfg))
            except httpx.HTTPError as exc:
                results.append({"provider": key, "ok": False, "error": type(exc).__name__})
    return {
        "supported": sorted(_HANDLERS),
        "note": "Most hosts have no balance API. Cerebras/Together/MiniMax dollars are dashboard-only.",
        "results": results,
    }
