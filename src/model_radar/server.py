"""
model-radar MCP server.

Exposes tools for AI agents to discover, ping, and select
the fastest free coding LLM models across 17 providers.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .config import (
    get_api_key,
    get_configured_providers,
    is_provider_enabled,
    load_config,
    save_config,
)
from .providers import ALL_TIERS, PROVIDERS, TIER_ORDER, get_all_models, filter_models
from .scanner import ScanState, format_result, scan_models

MCP_INSTRUCTIONS = """\
model-radar: Free coding model discovery for AI agents.

Pings 134+ free coding LLM models across 17 providers (NVIDIA NIM, Groq, \
Cerebras, SambaNova, OpenRouter, Hugging Face, Replicate, DeepInfra, Fireworks, \
Codestral, Hyperbolic, Scaleway, Google AI, SiliconFlow, Together AI, Cloudflare, \
Perplexity) and ranks them by real-time latency.

## Quick start
1. Call `list_providers()` to see which providers are configured
2. Call `scan_models()` to ping all models and get ranked results
3. Call `get_fastest()` for a quick recommendation

## Tool guide
- `list_providers()` — See all 17 providers and which have API keys
- `list_models(tier?, provider?)` — Browse the model catalog (no pinging)
- `scan_models(tier?, provider?, min_tier?, configured_only?, limit?)` — \
  Ping models in parallel, get ranked results with live latency
- `get_fastest(min_tier?, provider?, count?)` — Quick: best N models right now
- `provider_status()` — Detailed provider health check
- `configure_key(provider, api_key)` — Set an API key for a provider

## Tier scale (SWE-bench Verified)
S+ (70%+) > S (60-70%) > A+ (50-60%) > A (40-50%) > A- (35-40%) > B+ (30-35%) > B (20-30%) > C (<20%)
"""

mcp = FastMCP("model-radar", instructions=MCP_INSTRUCTIONS)

# Shared scan state for rolling averages across calls within a session
_state = ScanState()


@mcp.tool()
async def list_providers() -> str:
    """List all 17 providers with their status (configured/unconfigured, enabled/disabled, model count).

    Call this first to see which providers you have API keys for.
    No network requests — instant response.
    """
    cfg = load_config()
    rows = []
    total_models = 0
    configured_count = 0
    for key, prov in PROVIDERS.items():
        has_key = get_api_key(cfg, key) is not None
        enabled = is_provider_enabled(cfg, key)
        n = len(prov.models)
        total_models += n
        if has_key:
            configured_count += 1
        rows.append({
            "provider": prov.name,
            "key": key,
            "models": n,
            "api_key": "configured" if has_key else "missing",
            "enabled": enabled,
            "env_vars": list(prov.env_vars),
        })
    return json.dumps({
        "total_providers": len(PROVIDERS),
        "configured": configured_count,
        "total_models": total_models,
        "providers": rows,
    }, indent=2)


@mcp.tool()
async def list_models(
    tier: str | None = None,
    provider: str | None = None,
    min_tier: str | None = None,
) -> str:
    """Browse the model catalog without pinging. Instant response.

    Args:
        tier: Filter to exact tier (S+, S, A+, A, A-, B+, B, C)
        provider: Filter to provider key (nvidia, groq, cerebras, etc.)
        min_tier: Show this tier and above (e.g. "A" shows S+, S, A+, A)
    """
    models = filter_models(tier=tier, provider=provider, min_tier=min_tier)
    # Sort by tier quality
    models.sort(key=lambda m: (TIER_ORDER.get(m.tier, 99), m.label))
    rows = []
    for m in models:
        rows.append({
            "model_id": m.model_id,
            "label": m.label,
            "provider": PROVIDERS[m.provider].name,
            "provider_key": m.provider,
            "tier": m.tier,
            "swe_score": m.swe_score,
            "context": m.context,
        })
    return json.dumps({
        "count": len(rows),
        "filters": {"tier": tier, "provider": provider, "min_tier": min_tier},
        "models": rows,
    }, indent=2)


@mcp.tool()
async def scan(
    tier: str | None = None,
    provider: str | None = None,
    min_tier: str | None = None,
    configured_only: bool = False,
    limit: int = 20,
) -> str:
    """Ping models in parallel and return ranked results with live latency.

    This is the main tool — pings all matching models simultaneously and
    returns them sorted by latency (fastest first). Takes 2-10 seconds
    depending on how many models match the filters.

    Args:
        tier: Filter to exact tier (S+, S, A+, A, A-, B+, B, C)
        provider: Filter to provider key (nvidia, groq, cerebras, etc.)
        min_tier: Show this tier and above (e.g. "S" shows only S+ and S)
        configured_only: Only ping models whose provider has an API key
        limit: Max results (default 20, 0 = all)
    """
    results = await scan_models(
        tier=tier, provider=provider, min_tier=min_tier,
        configured_only=configured_only, limit=limit, state=_state,
    )
    rows = [format_result(r, _state) for r in results]

    up_count = sum(1 for r in results if r.status == "up")
    return json.dumps({
        "scanned": len(results),
        "up": up_count,
        "results": rows,
    }, indent=2)


@mcp.tool()
async def get_fastest(
    min_tier: str | None = "A",
    provider: str | None = None,
    count: int = 5,
) -> str:
    """Get the N fastest available models right now.

    Quick recommendation tool — pings only configured providers by default
    and returns the top results. Use this when you just want the best
    model to use right now.

    Args:
        min_tier: Minimum quality tier (default "A" — shows S+, S, A+, A)
        provider: Limit to specific provider
        count: How many results (default 5)
    """
    results = await scan_models(
        min_tier=min_tier, provider=provider,
        configured_only=True, limit=count, state=_state,
    )
    # Only return models that are actually up
    up_results = [r for r in results if r.status == "up"]
    rows = [format_result(r, _state) for r in up_results]

    if not rows:
        return json.dumps({
            "count": 0,
            "message": "No models responded. Check your API keys with list_providers().",
            "results": [],
        }, indent=2)

    return json.dumps({
        "count": len(rows),
        "fastest": rows[0] if rows else None,
        "results": rows,
    }, indent=2)


@mcp.tool()
async def provider_status() -> str:
    """Check health of all configured providers by pinging one model from each.

    Returns per-provider latency and status. Useful for diagnosing which
    providers are currently responsive vs overloaded.
    """
    cfg = load_config()
    configured = get_configured_providers(cfg)

    if not configured:
        return json.dumps({
            "message": "No providers configured. Set API keys with configure_key() or env vars.",
            "providers": [],
        }, indent=2)

    # Ping one model per configured provider
    results = []
    for pkey in configured:
        prov_results = await scan_models(provider=pkey, limit=1, state=_state)
        if prov_results:
            r = prov_results[0]
            results.append({
                "provider": PROVIDERS[pkey].name,
                "key": pkey,
                "status": r.status,
                "latency_ms": round(r.latency_ms, 1) if r.latency_ms else None,
                "test_model": r.model.label,
            })

    return json.dumps({"providers": results}, indent=2)


@mcp.tool()
async def configure_key(provider: str, api_key: str) -> str:
    """Set an API key for a provider. Saved to ~/.model-radar/config.json.

    Args:
        provider: Provider key (nvidia, groq, cerebras, sambanova, openrouter,
                  huggingface, replicate, deepinfra, fireworks, codestral,
                  hyperbolic, scaleway, googleai, siliconflow, together,
                  cloudflare, perplexity)
        api_key: The API key value
    """
    if provider not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        return json.dumps({
            "error": f"Unknown provider '{provider}'",
            "available_providers": available,
        }, indent=2)

    cfg = load_config()
    cfg["api_keys"][provider] = api_key
    save_config(cfg)

    return json.dumps({
        "success": True,
        "provider": PROVIDERS[provider].name,
        "message": f"API key saved for {PROVIDERS[provider].name}. "
                   f"Config: ~/.model-radar/config.json",
    }, indent=2)


def create_server() -> FastMCP:
    """Return the MCP server instance."""
    return mcp
