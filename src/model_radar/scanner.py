"""
Async model scanner — pings models in parallel via httpx.

Sends a minimal chat/completions request to each model endpoint and measures
round-trip latency. Models without an API key are still pinged (will return
401/403) but latency is recorded to show the endpoint is reachable.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import httpx

from .config import get_api_key, get_configured_providers, is_provider_enabled, load_config
from .db import get_models_for_discovery
from .providers import PROVIDERS, TIER_ORDER, Model
from .quality import get_model_quality

# Minimal payload — triggers a fast response from chat/completions endpoints
PING_PAYLOAD = {
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 1,
    "temperature": 0,
}

TIMEOUT_SECONDS = 10.0


@dataclass
class PingResult:
    model: Model
    status: str  # "up", "no_key", "timeout", "overloaded", "error", "not_found"
    latency_ms: float | None = None
    error_detail: str | None = None


@dataclass
class ScanState:
    """Accumulates rolling stats across multiple scan rounds."""
    ping_counts: dict[str, int] = field(default_factory=dict)
    success_counts: dict[str, int] = field(default_factory=dict)
    latency_sums: dict[str, float] = field(default_factory=dict)

    def record(self, key: str, success: bool, latency_ms: float | None):
        self.ping_counts[key] = self.ping_counts.get(key, 0) + 1
        if success and latency_ms is not None:
            self.success_counts[key] = self.success_counts.get(key, 0) + 1
            self.latency_sums[key] = self.latency_sums.get(key, 0) + latency_ms

    def avg_latency(self, key: str) -> float | None:
        count = self.success_counts.get(key, 0)
        if count == 0:
            return None
        return self.latency_sums[key] / count

    def uptime_pct(self, key: str) -> float | None:
        total = self.ping_counts.get(key, 0)
        if total == 0:
            return None
        return (self.success_counts.get(key, 0) / total) * 100


def _model_key(model: Model) -> str:
    return f"{model.provider}/{model.model_id}"


def _get_provider_url(provider_key: str, cfg: dict) -> str:
    """Get the endpoint URL, handling Cloudflare's account_id template."""
    prov = PROVIDERS[provider_key]
    url = prov.url
    if provider_key == "cloudflare":
        acct = cfg.get("cloudflare_account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        url = url.replace("{account_id}", acct)
    return url


async def _ping_one(
    client: httpx.AsyncClient,
    model: Model,
    cfg: dict,
) -> PingResult:
    """Ping a single model endpoint and return the result."""
    api_key = get_api_key(cfg, model.provider)
    url = _get_provider_url(model.provider, cfg)

    # Replicate uses a different API format
    if model.provider == "replicate":
        payload = {"input": {"prompt": "hi"}, "version": model.model_id}
    else:
        payload = {**PING_PAYLOAD, "model": model.model_id}

    headers = {"Content-Type": "application/json"}
    if api_key:
        if model.provider == "replicate":
            headers["Authorization"] = f"Token {api_key}"
        elif model.provider == "googleai":
            # Google AI uses key param, not Bearer
            url = f"{url}?key={api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    start = time.monotonic()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
        elapsed_ms = (time.monotonic() - start) * 1000

        if resp.status_code in (200, 201):
            return PingResult(model=model, status="up", latency_ms=elapsed_ms)
        elif resp.status_code in (401, 403):
            if api_key:
                return PingResult(model=model, status="error", latency_ms=elapsed_ms,
                                  error_detail="invalid_key")
            return PingResult(model=model, status="no_key", latency_ms=elapsed_ms)
        elif resp.status_code == 404:
            return PingResult(model=model, status="not_found", latency_ms=elapsed_ms)
        elif resp.status_code == 429:
            return PingResult(model=model, status="overloaded", latency_ms=elapsed_ms)
        elif resp.status_code >= 500:
            return PingResult(model=model, status="overloaded", latency_ms=elapsed_ms,
                              error_detail=f"HTTP {resp.status_code}")
        else:
            return PingResult(model=model, status="error", latency_ms=elapsed_ms,
                              error_detail=f"HTTP {resp.status_code}")

    except httpx.TimeoutException:
        elapsed_ms = (time.monotonic() - start) * 1000
        return PingResult(model=model, status="timeout", latency_ms=elapsed_ms)
    except httpx.ConnectError as e:
        return PingResult(model=model, status="error", error_detail=str(e)[:100])
    except Exception as e:
        return PingResult(model=model, status="error", error_detail=str(e)[:100])


async def scan_models(
    tier: str | None = None,
    provider: str | None = None,
    min_tier: str | None = None,
    configured_only: bool = False,
    free_only: bool = False,
    limit: int = 0,
    state: ScanState | None = None,
) -> list[PingResult]:
    """
    Ping models in parallel and return results sorted by latency.

    Args:
        tier: Filter to exact tier (e.g. "S+")
        provider: Filter to specific provider key
        min_tier: Filter to this tier or better (e.g. "A" includes S+, S, A+, A)
        configured_only: Only ping models whose provider has an API key
        free_only: Only include models marked as free (from API or heuristic)
        limit: Max results to return (0 = all)
        state: Optional ScanState for rolling averages
    """
    cfg = load_config()
    models = get_models_for_discovery(tier=tier, provider=provider, min_tier=min_tier, free_only=free_only)

    if configured_only:
        configured = set(get_configured_providers(cfg))
        models = [m for m in models if m.provider in configured]
    else:
        # Still filter out disabled providers
        models = [m for m in models if is_provider_enabled(cfg, m.provider)]

    async with httpx.AsyncClient() as client:
        tasks = [_ping_one(client, m, cfg) for m in models]
        results = await asyncio.gather(*tasks)

    # Record stats
    if state:
        for r in results:
            key = _model_key(r.model)
            state.record(key, r.status == "up", r.latency_ms)

    # Sort: up models by latency first, then others
    def sort_key(r: PingResult):
        status_order = {"up": 0, "no_key": 1, "overloaded": 2, "timeout": 3, "error": 4, "not_found": 5}
        return (
            status_order.get(r.status, 9),
            r.latency_ms if r.latency_ms is not None else 999999,
            TIER_ORDER.get(r.model.tier, 99),
        )

    results = sorted(results, key=sort_key)

    if limit > 0:
        results = results[:limit]

    return results


def format_result(r: PingResult, state: ScanState | None = None) -> dict:
    """Format a PingResult into a dict for MCP tool output."""
    key = _model_key(r.model)
    status_icons = {
        "up": "UP",
        "no_key": "NO_KEY",
        "timeout": "TIMEOUT",
        "overloaded": "OVERLOADED",
        "not_found": "NOT_FOUND",
        "error": "ERROR",
    }
    out = {
        "model_id": r.model.model_id,
        "label": r.model.label,
        "provider": PROVIDERS[r.model.provider].name,
        "provider_key": r.model.provider,
        "tier": r.model.tier,
        "swe_score": r.model.swe_score,
        "context": r.model.context,
        "status": status_icons.get(r.status, r.status),
        "latency_ms": round(r.latency_ms, 1) if r.latency_ms is not None else None,
    }
    if r.error_detail:
        out["error"] = r.error_detail
    if getattr(r.model, "is_free", None) is not None:
        out["is_free"] = r.model.is_free
    if state:
        avg = state.avg_latency(key)
        if avg is not None:
            out["avg_latency_ms"] = round(avg, 1)
        uptime = state.uptime_pct(key)
        if uptime is not None:
            out["uptime_pct"] = round(uptime, 1)
    # Include quality score if model has been benchmarked
    quality = get_model_quality(r.model.model_id)
    if quality:
        out["quality_score"] = f"{quality['passed']}/{quality['total']}"
        out["quality_pct"] = quality["pct"]
    return out
