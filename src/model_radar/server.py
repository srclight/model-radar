"""
model-radar MCP server.

Exposes tools for AI agents to discover, ping, and select
the fastest free coding LLM models across 17 providers.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from .config import (
    get_api_key,
    get_configured_providers,
    is_provider_enabled,
    load_config,
    save_config,
)
from .db import get_models_for_discovery
from .providers import ALL_TIERS, PROVIDERS, TIER_ORDER, get_all_models
from .scanner import ScanState, format_result, scan_models

MCP_INSTRUCTIONS = """\
model-radar: Free coding model discovery and execution for AI agents.

Pings 134+ free coding LLM models across 17 providers and ranks them by \
real-time latency. Run prompts on the fastest model, verify answers across \
multiple models, and benchmark quality — all through MCP tools.

## Quick start
1. Call list_providers() to see which providers have API keys configured.
2. Call get_fastest() for a quick recommendation of the best model right now.
3. Call run(prompt) to execute a prompt on the fastest available model.

## How to answer common user requests
- "What models are available?" → list_models() or list_models(min_tier="A")
- "Give me 5 fast free models" or "free and fast" → get_fastest(free_only=True, min_tier="A", count=5)
- "Only free models" / "list free models" → list_models(free_only=True) or get_fastest(free_only=True, count=10)
- "Run this on a free model" → run(prompt, free_only=True)
- "Best model for coding" / "fastest model" → get_fastest(min_tier="A", count=5)
- "Compare answers from several models" → ask(prompt, count=3)
- "Refresh the model list from the internet" → refresh_models()

## Tool guide — Discovery
- list_providers() — See all 17 providers and which have API keys. Call first when unsure.
- list_models(tier?, provider?, min_tier?, free_only?) — Browse catalog without pinging. \
  model_id = code name to use when inserting/configuring (API, Cursor, run()); label = display only. \
  min_tier="A" means A or better. free_only=true for free only. Response includes is_free when known.
- scan(...) — Ping models in parallel, get ranked by latency. Use when you need live speed data.
- get_fastest(min_tier?, provider?, count?, free_only?) — Best N models right now. \
  Example: get_fastest(free_only=True, min_tier="A", count=5) for "5 free A-or-better models".
- provider_status() — Per-provider health check.

## Tool guide — Execution
- run(prompt, free_only?, model_id?, provider?, min_tier?, ...) — Run a prompt on the fastest model. \
  Use free_only=true when the user wants a free model. Retries on next fastest if one fails.
- ask(prompt, count=3, ...) — Run the same prompt on N models in parallel; compare responses.

## Tool guide — Quality & Setup
- refresh_models(provider?, run_ping?, ping_limit?) — Fetch latest model lists from APIs; \
  use periodically so free/paid and model list stay current.
- benchmark(...) — Quality-test models; results show in later scan/get_fastest.
- setup_guide(provider?) — Signup instructions for unconfigured providers.
- configure_key(provider, api_key) — Save an API key.
- setup_workflow(step, provider_selection?) — Step-by-step setup (Playwright, providers, keys).
- host_swap_instructions(model_id?, provider?, min_tier?) — Where to set base_url + model_id on the host.
- restart_server() — (SSE only) Exit so process manager can restart. Allowed by default; set MODEL_RADAR_ALLOW_RESTART=0 to disable.
- server_stats() — Server start time and uptime.

## Tier scale (SWE-bench Verified)
Better → worse: S+ (70%+) > S (60-70%) > A+ (50-60%) > A (40-50%) > A- (35-40%) > B+ (30-35%) > B (20-30%) > C (<20%). \
min_tier="A" means "A or better" (includes A+, S, S+).

## Notes for agents
- **Always give the user the model_id** when you list or recommend models (scan, get_fastest, ask results, etc.). Show both label and model_id (e.g. "Kimi K2 Instruct — moonshotai/kimi-k2-instruct") so the user can copy it for run(model_id=...), Cursor config, or host_swap_instructions.
- model_id is the model code name — use it when inserting or configuring (API calls, Cursor, run(prompt, model_id=\"...\"), host_swap_instructions). label is display-only.
- is_free in responses: true = free, false = paid, field missing = unknown. Use free_only=true to filter to free only.
- quality_score: prefer 4/5 or 5/5; avoid below 3/5 when shown.
- If only one provider is configured, suggest setup_guide() for more coverage.
- run() retries on failure automatically; no need to implement retry yourself.

## Instructions for host agents
- **SSE and Cursor:** The server must be started in a separate terminal and already listening \
  before Cursor connects. If Cursor tries to connect before the server is up, it will timeout \
  ("fetch failed", "Connect Timeout"). Tell the user: start `model-radar serve --transport sse --port 8765` \
  (or with --web), wait for "Uvicorn running on...", then open Cursor or add the MCP server URL. \
  That way server startup is separate from MCP connection and all tools are immediately active.
- **Web dashboard:** The user can get a localhost UI (status, config, discovery, run) \
  by running model-radar with SSE and --web. Command: \
  `model-radar serve --transport sse --port 8765 --web`. Dashboard URL: \
  http://127.0.0.1:8765/ . The server binds to 127.0.0.1 only; keys and data never leave the machine.
- **Restarting the server:** If the user wants to restart or reload, call `restart_server()`. The server will exit with code 0; if run under a loop (e.g. `while true; do model-radar serve ...; sleep 1; done`) it will come back with fresh code. Do not start a second server on another port.
- **Starting the server:** If nothing is running, instruct: `model-radar serve --transport sse --port 8765 --web` (or without --web). For auto-restart on code changes: `while true; do model-radar serve --transport sse --port 8765 --web; sleep 1; done`.
- **Privacy:** Do not log, echo, or send API keys off-host. list_providers and API responses \
  show only "configured" or "missing"; never the actual key. Keys are stored only in \
  ~/.model-radar/config.json (0o600).
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
    free_only: bool = False,
) -> str:
    """List models in the catalog without pinging. Use when the user asks what models are available or to browse by tier/provider/free.

    Response includes model_id (the code name to use when inserting/configuring, e.g. run(prompt, model_id=...) or Cursor settings) and label (display only).

    Args:
        tier: Filter to exact tier (S+, S, A+, A, A-, B+, B, C)
        provider: Filter to provider key (nvidia, groq, cerebras, etc.)
        min_tier: Show this tier and above (e.g. "A" = A, A+, S, S+)
        free_only: If true, only list models marked as free (from API or :free/-free in id)
    """
    models = get_models_for_discovery(tier=tier, provider=provider, min_tier=min_tier, free_only=free_only)
    # Sort by tier quality
    models.sort(key=lambda m: (TIER_ORDER.get(m.tier, 99), m.label))
    rows = []
    for m in models:
        row = {
            "model_id": m.model_id,
            "label": m.label,
            "provider": PROVIDERS[m.provider].name,
            "provider_key": m.provider,
            "tier": m.tier,
            "swe_score": m.swe_score,
            "context": m.context,
        }
        if m.is_free is not None:
            row["is_free"] = m.is_free
        rows.append(row)
    return json.dumps({
        "count": len(rows),
        "filters": {"tier": tier, "provider": provider, "min_tier": min_tier, "free_only": free_only},
        "model_id_usage": "Use model_id as the model code name when configuring clients or API calls (e.g. run(prompt, model_id=..., provider=...)). label is for display only.",
        "models": rows,
    }, indent=2)


@mcp.tool()
async def scan(
    tier: str | None = None,
    provider: str | None = None,
    min_tier: str | None = None,
    configured_only: bool = False,
    free_only: bool = False,
    limit: int = 20,
) -> str:
    """Ping models in parallel and return ranked results by latency. Use when you need live speed data or a ranked list.

    Pings all matching models, returns sorted fastest-first. Takes 2-10 seconds depending on filters.

    Args:
        tier: Filter to exact tier (S+, S, A+, A, A-, B+, B, C)
        provider: Filter to provider key (nvidia, groq, cerebras, etc.)
        min_tier: Show this tier and above (e.g. "S" shows only S+ and S)
        configured_only: Only ping models whose provider has an API key
        free_only: Only include models marked as free (from API or :free/-free in id)
        limit: Max results (default 20, 0 = all)
    """
    results = await scan_models(
        tier=tier, provider=provider, min_tier=min_tier,
        configured_only=configured_only, free_only=free_only, limit=limit, state=_state,
    )
    rows = [format_result(r, _state) for r in results]

    up_count = sum(1 for r in results if r.status == "up")
    return json.dumps({
        "scanned": len(results),
        "up": up_count,
        "model_id_usage": "Use model_id as the model code name when configuring clients or API calls (e.g. run(prompt, model_id=..., provider=...)). label is for display only.",
        "results": rows,
    }, indent=2)


@mcp.tool()
async def get_fastest(
    min_tier: str | None = "A",
    provider: str | None = None,
    count: int = 5,
    free_only: bool = False,
) -> str:
    """Get the N fastest available models right now. Use when the user wants recommendations or \"best/fastest/free\" models.

    Pings configured providers and returns top N by latency. Use model_id from results as the code name when inserting or configuring (e.g. run(prompt, model_id=..., provider=...)). Example: get_fastest(free_only=True, min_tier=\"A\", count=5) for \"5 free A-or-better models\".

    Args:
        min_tier: Minimum quality tier (default "A" — shows S+, S, A+, A)
        provider: Limit to specific provider
        count: How many results (default 5)
        free_only: If true, only return models marked as free
    """
    results = await scan_models(
        min_tier=min_tier, provider=provider,
        configured_only=True, free_only=free_only, limit=count, state=_state,
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
        "model_id_usage": "Use model_id as the model code name when configuring clients or API calls (e.g. run(prompt, model_id=..., provider=...)). label is for display only.",
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


@mcp.tool()
async def refresh_models(
    provider: str | None = None,
    run_ping: bool = False,
    ping_limit: int = 20,
) -> str:
    """Fetch latest model lists from configured providers (openrouter, nvidia, groq) and replace them in the database.

    Only providers with API keys are fetched; their previous model list is discarded and replaced with the live API list. Other providers keep their existing list. Use this to get the current catalog, then call scan() or get_fastest() for discovery. Optionally run a quick ping test after refresh.

    Args:
        provider: Optional provider to refresh only (openrouter, nvidia, groq)
        run_ping: If true, run a ping test on up to ping_limit models after refreshing
        ping_limit: Max models to ping when run_ping is true (default 20)
    """
    from .provider_sync import refresh_models_from_live

    counts = await refresh_models_from_live(provider=provider)
    if not counts:
        return json.dumps({
            "refreshed": 0,
            "message": "No providers with API keys returned models (openrouter, nvidia, groq).",
            "ping_run": False,
        }, indent=2)

    total = sum(counts.values())
    result = {
        "refreshed": total,
        "by_provider": counts,
        "ping_run": False,
    }
    if run_ping and total > 0:
        from .ping_test import ping_all_models
        ping_provider = list(counts.keys())[0] if provider is None and len(counts) == 1 else provider
        results = await ping_all_models(provider=ping_provider, limit=ping_limit, concurrency=5)
        up = sum(1 for r in results if r.status == "success")
        result["ping_run"] = True
        result["ping_tested"] = len(results)
        result["ping_up"] = up
    return json.dumps(result, indent=2)


@mcp.tool()
async def run(
    prompt: str,
    system_prompt: str | None = None,
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str = "A",
    free_only: bool = False,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Run a prompt on the fastest available model and return the response.

    Use when the user wants to execute a prompt. Picks the fastest responding
    model automatically (with optional fallback). Set free_only=True when the
    user asks for a free model only.

    Args:
        prompt: The user message to send
        system_prompt: Optional system prompt (e.g. "You are a Python expert")
        model_id: Specific model to use (skips scanning). Use list_models() to browse.
        provider: Limit to a specific provider (nvidia, groq, etc.)
        min_tier: Minimum quality tier when auto-selecting (default "A")
        free_only: If true, only consider models marked as free (default false)
        max_tokens: Max response tokens (default 4096)
        temperature: Sampling temperature (default 0.0 for deterministic)
    """
    from .runner import run_on_fastest

    result = await run_on_fastest(
        prompt=prompt,
        system_prompt=system_prompt,
        model_id=model_id,
        provider=provider,
        min_tier=min_tier,
        free_only=free_only,
        max_tokens=max_tokens,
        temperature=temperature,
        state=_state,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def benchmark(
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str = "A",
    count: int = 3,
) -> str:
    """Quality-test models with 5 coding challenges and return pass/fail scores.

    Runs arithmetic, instruction following, code generation, code reasoning,
    and JSON output challenges. Catches models that are fast but hallucinate,
    ignore instructions, or produce garbled output.

    Without model_id, scans for the fastest models and benchmarks the top N.

    Args:
        model_id: Specific model to benchmark (optional)
        provider: Limit to a specific provider (nvidia, groq, etc.)
        min_tier: Minimum quality tier when auto-selecting (default "A")
        count: How many models to benchmark when auto-selecting (default 3)
    """
    from .benchmark import benchmark_models

    scores = await benchmark_models(
        model_id=model_id,
        provider=provider,
        min_tier=min_tier,
        count=count,
        state=_state,
    )
    return json.dumps({"benchmarks": scores}, indent=2)


@mcp.tool()
async def ask(
    prompt: str,
    system_prompt: str | None = None,
    count: int = 3,
    min_tier: str = "A",
    provider: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Run the same prompt on multiple models in parallel and return all responses.

    Use this for verification and consensus. When accuracy matters more than
    speed, ask N models the same question and compare their answers. If 3/3
    models agree, you can be more confident in the result.

    Returns all responses side-by-side with model info, latency, and quality
    scores (if previously benchmarked).

    Args:
        prompt: The question or task to send to all models
        system_prompt: Optional system prompt applied to all models
        count: How many models to query in parallel (default 3)
        min_tier: Minimum quality tier for model selection (default "A")
        provider: Limit to a specific provider (nvidia, groq, etc.)
        max_tokens: Max response tokens per model (default 4096)
        temperature: Sampling temperature (default 0.0 for deterministic)
    """
    from .consensus import ask_models

    result = await ask_models(
        prompt=prompt,
        system_prompt=system_prompt,
        count=count,
        min_tier=min_tier,
        provider=provider,
        max_tokens=max_tokens,
        temperature=temperature,
        state=_state,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def setup_guide(provider: str | None = None) -> str:
    """Get setup instructions for adding free model providers.

    Without arguments, returns a prioritized list of all unconfigured
    providers with signup URLs, free tier details, and setup steps.
    With a provider argument, returns detailed instructions for that
    specific provider.

    Use this to help your user expand their model coverage. More providers
    means better fallback options and more models to choose from.

    Args:
        provider: Specific provider key to get instructions for (optional).
                  Omit to see all unconfigured providers.
    """
    from .guides import get_setup_guide

    result = get_setup_guide(provider)
    return json.dumps(result, indent=2)


@mcp.tool()
async def setup_workflow(
    step: int,
    provider_selection: list[str] | None = None,
) -> str:
    """Deterministic setup workflow: guide the host to get API keys installed.

    Run steps in order. Step 1: check/install Playwright (optional). Step 2:
    get list of remaining (unconfigured) providers — then prompt the user to
    choose which to set up. Step 3: pass that selection as provider_selection
    to get login instructions and where to save each key. Step 4: summary of
    where keys are stored (config path, configure_key tool, env vars).

    Many providers support GitHub SSO; the response marks them so the host can
    tell the user they may only need to click \"Sign in with GitHub\" and allow.

    Args:
        step: 1 (Playwright), 2 (remaining providers), 3 (login + save), 4 (where to save).
        provider_selection: For step 3 only. List of provider keys (e.g. groq, openrouter)
                            the user chose from step 2. If omitted at step 3, response
                            tells you to prompt the user and call again with selection.
    """
    from .setup_workflow import get_workflow_step

    result = get_workflow_step(step=step, provider_selection=provider_selection)
    return json.dumps(result, indent=2)


@mcp.tool()
async def host_swap_instructions(
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str | None = "A",
) -> str:
    """Tell the host agent where to search the machine to swap in a model-radar model.

    Returns: (1) Where model-radar stores API keys. (2) OpenAI-compatible base_url
    and model_id for the given model (or a recommended min_tier model). (3) Per-app
    search locations for Cursor, Claude Code, Open Interpreter, OpenClaw — with paths
    for Linux, Mac, Windows, and WSL (e.g. ~/.cursor, /mnt/c/Users/<user>/.cursor).
    The host can search these paths and set base_url + model_id + API key so the app
    uses a free model from model-radar.

    Args:
        model_id: Specific model_id (e.g. llama-3.3-70b-versatile). Omit to get a
                  recommended model at min_tier.
        provider: Limit to this provider when choosing a recommended model.
        min_tier: When model_id is omitted, recommend a model at this tier or better (default A).
    """
    from .host_swap import get_host_swap_instructions

    result = get_host_swap_instructions(
        model_id=model_id, provider=provider, min_tier=min_tier,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def restart_server() -> str:
    """Request the server to exit so a process manager can restart it (SSE only).

    When running model-radar with SSE, a process manager or wrapper can restart
    the server on exit. This tool exits the process with code 0 so the manager
    starts a fresh process (and loads any updated code/tools). The client must
    reconnect after the restart. Restart is allowed by default; set
    MODEL_RADAR_ALLOW_RESTART=0 to disable.
    """
    allow = os.environ.get("MODEL_RADAR_ALLOW_RESTART", "1").strip().lower()
    if allow in ("0", "false", "no"):
        return json.dumps({
            "ok": False,
            "message": "Restart is disabled (MODEL_RADAR_ALLOW_RESTART=0). Remove it or set to 1 to allow.",
            "hint": "Example: model-radar serve --transport sse --port 8765 --web",
        }, indent=2)

    # Schedule exit on next tick so the tool response can be sent
    def _exit():
        os._exit(0)

    asyncio.get_running_loop().call_later(0, _exit)
    return json.dumps({
        "ok": True,
        "message": "Server will exit now. Reconnect after your process manager restarts it.",
    }, indent=2)


# Set when create_server() is called (once per process) so server_stats can report startup/uptime
_server_start_time: float | None = None


@mcp.tool()
async def server_stats() -> str:
    """Return when this server process started and how long it has been running.

    Use to answer questions like 'how fast did model-radar come up' or 'how long has
    the server been running'. started_at is set when the server process began (create_server
    was called); uptime_seconds is seconds since then.
    """
    global _server_start_time
    if _server_start_time is None:
        _server_start_time = time.time()
    now = time.time()
    uptime = now - _server_start_time
    started_at = datetime.fromtimestamp(_server_start_time, tz=timezone.utc)
    return json.dumps({
        "started_at": started_at.isoformat(),
        "started_at_epoch": _server_start_time,
        "uptime_seconds": round(uptime, 2),
        "uptime_human": f"{int(uptime)}s",
    }, indent=2)


def create_server() -> FastMCP:
    """Return the MCP server instance."""
    global _server_start_time
    if _server_start_time is None:
        _server_start_time = time.time()
    return mcp


def make_sse_and_streamable_http_app(mount_path: str | None = "/") -> "Starlette":
    """Return a Starlette app that serves both SSE (/sse, /messages/) and Streamable HTTP (/mcp).

    Cursor tries Streamable HTTP first, then falls back to SSE. Serving both on the same
    port avoids connection failures when Cursor connects. Uses the streamable app as
    base (so its lifespan runs) and adds SSE routes to it.
    """
    streamable_app = mcp.streamable_http_app()
    sse_app = mcp.sse_app(mount_path=mount_path)
    sse_routes = [r for r in sse_app.routes if getattr(r, "path", None) in ("/sse", "/messages")]
    streamable_app.router.routes.extend(sse_routes)
    return streamable_app
