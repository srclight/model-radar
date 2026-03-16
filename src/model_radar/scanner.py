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


class ProviderThrottle:
    """Tracks 429 errors per provider, computes backoff delays, and adjusts concurrency."""

    def __init__(self, max_delay: float = 16.0, window: float = 60.0,
                 default_concurrency: int = 5, min_concurrency: int = 1):
        self._recent_429s: dict[str, list[float]] = {}
        self._max_delay = max_delay
        self._window = window
        self._default_concurrency = default_concurrency
        self._min_concurrency = min_concurrency
        self._concurrency: dict[str, int] = {}
        self._recent_calls: dict[str, list[tuple[float, bool]]] = {}  # (time, was_429)

    def record_429(self, provider: str) -> None:
        now = time.monotonic()
        hits = self._recent_429s.setdefault(provider, [])
        hits.append(now)
        # Prune old entries outside window
        self._recent_429s[provider] = [t for t in hits if now - t < self._window]
        # Track for adaptive concurrency
        self._recent_calls.setdefault(provider, []).append((now, True))
        self._prune_calls(provider, now)
        # Reduce concurrency on 429
        current = self._concurrency.get(provider, self._default_concurrency)
        self._concurrency[provider] = max(self._min_concurrency, current // 2)

    def record_success(self, provider: str) -> None:
        now = time.monotonic()
        hits = self._recent_429s.get(provider)
        if hits:
            # Decay: remove oldest entry on success
            hits.pop(0)
            if not hits:
                del self._recent_429s[provider]
        # Track for adaptive concurrency
        self._recent_calls.setdefault(provider, []).append((now, False))
        self._prune_calls(provider, now)
        # Gradually recover concurrency on sustained success
        calls = self._recent_calls.get(provider, [])
        recent_successes = sum(1 for _, was_429 in calls[-10:] if not was_429)
        if recent_successes >= 10:
            current = self._concurrency.get(provider, self._default_concurrency)
            if current < self._default_concurrency:
                self._concurrency[provider] = min(self._default_concurrency, current + 1)

    def _prune_calls(self, provider: str, now: float) -> None:
        calls = self._recent_calls.get(provider)
        if calls:
            self._recent_calls[provider] = [(t, f) for t, f in calls if now - t < self._window]

    def should_throttle(self, provider: str) -> float:
        """Returns delay in seconds (0 = no throttle)."""
        now = time.monotonic()
        hits = self._recent_429s.get(provider)
        if not hits:
            return 0.0
        # Prune old entries
        recent = [t for t in hits if now - t < self._window]
        self._recent_429s[provider] = recent
        if not recent:
            return 0.0
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s based on hit count
        delay = min(2 ** (len(recent) - 1), self._max_delay)
        return delay

    def effective_concurrency(self, provider: str | None = None) -> int:
        """Get the current adaptive concurrency for a provider (or global default)."""
        if provider is None:
            # Return the minimum across all throttled providers, or default
            if not self._concurrency:
                return self._default_concurrency
            return min(self._concurrency.values())
        return self._concurrency.get(provider, self._default_concurrency)

    def is_degraded(self, provider: str) -> bool:
        """True if a provider has recent 429s (useful for judge/worker selection)."""
        now = time.monotonic()
        hits = self._recent_429s.get(provider, [])
        recent = [t for t in hits if now - t < self._window]
        return len(recent) >= 2


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
    # Verified-alive cache: model key → True (verified) or False (broken)
    verified: dict[str, bool] = field(default_factory=dict)
    # Per-provider rate limit tracker
    throttle: ProviderThrottle = field(default_factory=ProviderThrottle)

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
            # Hello check: for OpenAI-style APIs, ensure we got a real completion (not 200 + error in body)
            if model.provider != "replicate":
                try:
                    data = resp.json()
                    choices = data.get("choices") if isinstance(data, dict) else None
                    if not choices or not isinstance(choices, list):
                        return PingResult(model=model, status="error", latency_ms=elapsed_ms,
                                          error_detail="no_choices")
                    first = choices[0] if choices else None
                    if not isinstance(first, dict) or "message" not in first:
                        return PingResult(model=model, status="error", latency_ms=elapsed_ms,
                                          error_detail="no_message")
                except Exception:
                    return PingResult(model=model, status="error", latency_ms=elapsed_ms,
                                      error_detail="invalid_response")
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


VERIFY_PAYLOAD = {
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    "max_tokens": 5,
    "temperature": 0,
}


async def _verify_one(
    client: httpx.AsyncClient,
    model: Model,
    cfg: dict,
    verify_prompt: str | None = None,
) -> bool:
    """Send a real prompt and check for non-empty content. Returns True if functional."""
    api_key = get_api_key(cfg, model.provider)
    if not api_key:
        return False

    url = _get_provider_url(model.provider, cfg)
    if model.provider == "googleai":
        url = f"{url}?key={api_key}"

    headers = {"Content-Type": "application/json"}
    if api_key:
        if model.provider == "replicate":
            headers["Authorization"] = f"Token {api_key}"
        elif model.provider != "googleai":
            headers["Authorization"] = f"Bearer {api_key}"

    prompt_text = verify_prompt or "Reply with exactly: OK"
    if model.provider == "replicate":
        payload = {"input": {"prompt": prompt_text}, "version": model.model_id}
    else:
        payload = {
            "model": model.model_id,
            "messages": [{"role": "user", "content": prompt_text}],
            "max_tokens": 5,
            "temperature": 0,
        }

    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
        if resp.status_code not in (200, 201):
            return False

        data = resp.json()
        if model.provider == "replicate":
            output = data.get("output", [])
            content = "".join(output) if isinstance(output, list) else str(output)
        else:
            choices = data.get("choices", [])
            if not choices:
                return False
            msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = msg.get("content", "") or ""
            if isinstance(content, list):
                content = "".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            # Check reasoning fields for models that put output there (GPT-OSS etc.)
            if not content or not content.strip():
                content = (
                    msg.get("reasoning")
                    or msg.get("reasoning_content")
                    or ""
                )
                if content and not isinstance(content, str):
                    content = str(content)

        # Non-empty, non-whitespace content = functionally alive
        return bool(content and content.strip())
    except Exception:
        return False


async def scan_models(
    tier: str | None = None,
    provider: str | None = None,
    min_tier: str | None = None,
    configured_only: bool = False,
    free_only: bool = False,
    limit: int = 0,
    state: ScanState | None = None,
    verify: bool = False,
    verify_prompt: str | None = None,
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

    # Verified-alive: send a real prompt to models marked "up" and check for content
    if verify:
        up_results = [r for r in results if r.status == "up"]
        if up_results:
            async with httpx.AsyncClient() as verify_client:
                verify_tasks = []
                for r in up_results:
                    key = _model_key(r.model)
                    # Use cache if available
                    if state and key in state.verified:
                        continue
                    verify_tasks.append((r, _verify_one(verify_client, r.model, cfg, verify_prompt)))

                if verify_tasks:
                    verify_results = await asyncio.gather(
                        *(t for _, t in verify_tasks)
                    )
                    for (r, _), is_alive in zip(verify_tasks, verify_results):
                        key = _model_key(r.model)
                        if not is_alive:
                            r.status = "broken"
                            r.error_detail = "verified_empty_response"
                        if state:
                            state.verified[key] = is_alive

            # Apply cached verification results
            if state:
                for r in up_results:
                    key = _model_key(r.model)
                    if key in state.verified and not state.verified[key]:
                        r.status = "broken"
                        r.error_detail = "verified_empty_response"

    # Sort: up models by latency first, then others
    def sort_key(r: PingResult):
        status_order = {"up": 0, "no_key": 1, "overloaded": 2, "broken": 3, "timeout": 4, "error": 5, "not_found": 6}
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
        "broken": "BROKEN",
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
