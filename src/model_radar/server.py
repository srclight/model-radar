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
from .providers import ALL_TIERS, PROVIDERS, TIER_ORDER, get_all_models, filter_models
from .scanner import ScanState, format_result, scan_models

MCP_INSTRUCTIONS = """\
model-radar: Free coding model discovery and execution for AI agents.

Pings 134+ free coding LLM models across 17 providers and ranks them by \
real-time latency. Run prompts on the fastest model, verify answers across \
multiple models, and benchmark quality — all through MCP tools.

## Quick start
1. Call `list_providers()` to see which providers have API keys configured
2. Call `get_fastest()` for a quick recommendation of the best model right now
3. Call `run(prompt)` to execute a prompt on the fastest available model

## Tool guide — Discovery
- `list_providers()` — See all 17 providers and which have API keys
- `list_models(tier?, provider?)` — Browse the model catalog (no pinging)
- `scan(tier?, provider?, min_tier?, configured_only?, limit?)` — \
  Ping models in parallel, get ranked results with live latency
- `get_fastest(min_tier?, provider?, count?)` — Quick: best N models right now
- `provider_status()` — Per-provider health check

## Tool guide — Execution
- `run(prompt, ...)` — Run a prompt on the fastest model with automatic \
  fallback. If a model fails, retries on the next fastest automatically.
- `ask(prompt, count=3, ...)` — Multi-model consensus. Run the same prompt \
  on N models in parallel and compare responses for verification.

## Tool guide — Quality & Setup
- `benchmark(model_id?, count?)` — Quality-test models with 5 coding \
  challenges. Results are saved and shown in future scan/get_fastest calls.
- `setup_guide(provider?)` — Get signup instructions for unconfigured \
  providers. Returns URLs and steps you can relay to your user.
- `configure_key(provider, api_key)` — Save an API key for a provider.
- `setup_workflow(step, provider_selection?)` — Deterministic setup: step 1 \
  Playwright check/install, step 2 list remaining providers, step 3 login \
  instructions for selected providers + where to save keys, step 4 where to save.
- `host_swap_instructions(model_id?, provider?, min_tier?)` — Where to search the \
  machine (Cursor, Claude Code, Open Interpreter, OpenClaw) and what OpenAI \
  base_url + model_id to set; includes WSL/Windows/Mac paths and model-radar key locations.
- `restart_server()` — (SSE only, opt-in) Exit the server process so a process manager \
  can restart it and load new tools. Requires MODEL_RADAR_ALLOW_RESTART=1.
- `server_stats()` — When the server started (ISO timestamp) and uptime in seconds. \
  Use to answer "how fast did model-radar come up" or "how long has it been running".

## Tier scale (SWE-bench Verified)
S+ (70%+) > S (60-70%) > A+ (50-60%) > A (40-50%) > A- (35-40%) > B+ (30-35%) > B (20-30%) > C (<20%)

## Notes for agents
- Models with a quality_score field have been benchmarked. Prefer models \
  scoring 4/5 or 5/5. Avoid models scoring below 3/5.
- If only 1 provider is configured, call setup_guide() and suggest your \
  user add more providers for better coverage and fallback.
- The run() tool automatically retries on the next fastest model if one \
  fails. You do not need to implement retry logic yourself.

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
- **Restarting the server:** If the user wants to "bring up the website", "restart the server", or \
  "reload" and the server is already running under a restart loop (e.g. MODEL_RADAR_ALLOW_RESTART=1 \
  with a loop that restarts on exit), call `restart_server()`. Do not start a second server on \
  another port. If no server is running, tell the user to run the command above in a terminal (with \
  --web if they want the dashboard).
- **Starting the server:** If the user wants the server or dashboard and nothing is running, \
  instruct them to run in a terminal: `model-radar serve --transport sse --port 8765 --web` (or \
  without --web for MCP only). For automatic restarts after code changes: \
  `MODEL_RADAR_ALLOW_RESTART=1` and a wrapper like `while true; do model-radar serve --transport sse --port 8765 --web; sleep 1; done`.
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


@mcp.tool()
async def run(
    prompt: str,
    system_prompt: str | None = None,
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str = "A",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Run a prompt on the fastest available free model and return the response.

    Picks the fastest responding model automatically, or use a specific one.
    This turns model-radar from discovery into execution — one tool call to
    get work done on a free coding model.

    Args:
        prompt: The user message to send
        system_prompt: Optional system prompt (e.g. "You are a Python expert")
        model_id: Specific model to use (skips scanning). Use list_models() to browse.
        provider: Limit to a specific provider (nvidia, groq, etc.)
        min_tier: Minimum quality tier when auto-selecting (default "A")
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
    """Request the server to exit so a process manager can restart it (SSE only, opt-in).

    When running model-radar with SSE (e.g. model-radar serve --transport sse), a
    process manager or wrapper can restart the server on exit. This tool exits the
    process with code 0 so the manager starts a fresh process (and loads any updated
    code/tools). The client must reconnect after the restart.

    Requires MODEL_RADAR_ALLOW_RESTART=1. If not set, returns instructions instead
    of exiting (so agents cannot restart the server by default).
    """
    if os.environ.get("MODEL_RADAR_ALLOW_RESTART") != "1":
        return json.dumps({
            "ok": False,
            "message": "Restart is disabled. To enable: set MODEL_RADAR_ALLOW_RESTART=1 "
                       "and run the server under a process manager that restarts on exit "
                       "(e.g. a loop or systemd). Then call restart_server() again.",
            "hint": "Example: MODEL_RADAR_ALLOW_RESTART=1 model-radar serve --transport sse --port 8765",
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
