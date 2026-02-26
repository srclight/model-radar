"""
Ping test all models to verify they're working.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Literal
import httpx

from .config import get_api_key, load_config
from .db import get_all_models, record_ping
from .providers import PROVIDERS


@dataclass
class PingTestResult:
    model_id: str
    provider: str
    status: Literal["success", "error", "timeout", "not_found", "rate_limited"]
    latency_ms: float | None = None
    error_message: str | None = None
    is_free: bool = False


async def ping_model(
    model_id: str,
    provider: str,
    api_key: str | None,
    timeout: float = 10.0,
) -> PingTestResult:
    """
    Ping a single model to verify it works.
    
    Returns:
        PingTestResult with status and latency
    """
    if not api_key:
        return PingTestResult(
            model_id=model_id,
            provider=provider,
            status="error",
            error_message="No API key"
        )
    
    # Get provider endpoint
    prov = PROVIDERS.get(provider)
    if not prov:
        return PingTestResult(
            model_id=model_id,
            provider=provider,
            status="error",
            error_message=f"Unknown provider: {provider}"
        )
    
    url = prov.url
    
    # Prepare request
    if provider == "replicate":
        payload = {"input": {"prompt": "hi"}, "version": model_id}
        headers = {"Authorization": f"Token {api_key}"}
    else:
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
        headers = {"Authorization": f"Bearer {api_key}"}
    
    start = time.monotonic()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
            elapsed_ms = (time.monotonic() - start) * 1000
        
        if resp.status_code == 200:
            return PingTestResult(
                model_id=model_id,
                provider=provider,
                status="success",
                latency_ms=elapsed_ms,
                is_free="free" in model_id.lower() or ":free" in model_id,
            )
        elif resp.status_code in (401, 403):
            return PingTestResult(
                model_id=model_id,
                provider=provider,
                status="error",
                error_message="Invalid API key",
            )
        elif resp.status_code == 404:
            return PingTestResult(
                model_id=model_id,
                provider=provider,
                status="not_found",
                error_message="Model not found",
            )
        elif resp.status_code == 429:
            return PingTestResult(
                model_id=model_id,
                provider=provider,
                status="rate_limited",
                error_message="Rate limited",
            )
        else:
            return PingTestResult(
                model_id=model_id,
                provider=provider,
                status="error",
                error_message=f"HTTP {resp.status_code}",
            )
    except httpx.TimeoutException:
        return PingTestResult(
            model_id=model_id,
            provider=provider,
            status="timeout",
            error_message="Request timed out",
        )
    except Exception as e:
        return PingTestResult(
            model_id=model_id,
            provider=provider,
            status="error",
            error_message=str(e)[:100],
        )


async def ping_all_models(
    provider: str | None = None,
    limit: int = 0,
    concurrency: int = 10,
) -> list[PingTestResult]:
    """
    Ping all models (or filtered by provider) to verify they work.
    
    Args:
        provider: Filter by provider
        limit: Max models to test
        concurrency: Number of concurrent requests
    
    Returns:
        List of PingTestResult
    """
    cfg = load_config()
    
    # Get models
    models = get_all_models()
    if provider:
        models = [m for m in models if m.provider == provider]
    if limit > 0:
        models = models[:limit]
    
    results = []
    semaphore = asyncio.Semaphore(concurrency)
    
    async def ping_with_semaphore(model):
        async with semaphore:
            api_key = get_api_key(cfg, model.provider)
            result = await ping_model(model.model_id, model.provider, api_key)
            
            # Record to database
            record_ping(
                model_id=model.model_id,
                provider_key=model.provider,
                status=result.status,
                latency_ms=result.latency_ms,
                error_detail=result.error_message,
            )
            
            return result
    
    # Ping all models concurrently
    tasks = [ping_with_semaphore(model) for model in models]
    results = await asyncio.gather(*tasks)
    
    return list(results)


def print_ping_results(results: list[PingTestResult]):
    """Print ping test results."""
    if not results:
        print("No results")
        return
    
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status != "success")
    
    print(f"\n{'='*60}")
    print(f"PING TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total: {total} | Success: {success} | Failed: {failed}")
    print(f"{'='*60}\n")
    
    # Group by status
    by_status = {}
    for r in results:
        if r.status not in by_status:
            by_status[r.status] = []
        by_status[r.status].append(r)
    
    for status, status_results in sorted(by_status.items()):
        print(f"\n{status.upper()} ({len(status_results)}):")
        for r in status_results[:10]:
            latency = f"{r.latency_ms:.0f}ms" if r.latency_ms else "---"
            free_tag = " [FREE]" if r.is_free else ""
            print(f"  [{r.provider}] {r.model_id} {latency}{free_tag}")
        if len(status_results) > 10:
            print(f"  ... and {len(status_results) - 10} more")
