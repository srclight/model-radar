"""
model-radar MCP server.

Exposes tools for AI agents to discover, ping, and select
the fastest free coding LLM models across configured providers.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .cli_provider import is_cli_provider
from .config import (
    get_api_key,
    get_configured_providers,
    get_key_meta,
    get_provider_flags,
    in_default_pool,
    is_provider_enabled,
    load_config,
    save_config,
    set_api_key,
    set_provider_flags,
)
from .lanes import provider_lane
from .db import get_models_for_discovery
from .providers import ALL_TIERS, PROVIDERS, TIER_ORDER, get_all_models
from .scanner import ScanState, format_result, scan_models

MCP_INSTRUCTIONS = """\
model-radar: Free coding model discovery and execution for AI agents.

Pings free coding LLM models across HTTPS providers and subscription CLIs \
(claude, grok, agy/gemini, codex) and ranks HTTPS models by real-time latency. \
Run prompts on the fastest model, verify answers across multiple models, \
or pin subscriptions for a parallel review — all through MCP tools.

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
- "Review this on Claude + Grok + Gemini" → ask(prompt, providers=["claude","grok","gemini"])
- "What should I use for translation / rewrite / code review?" → recommend(job="translate"|"rewrite"|"review")
- "Time and score a few models on a translation / lemma rewrite / code review" → quality_probe(job=…)
- "Refresh the model list from the internet" → refresh_models()
- "Run these prompts in batch" → batch_run(prompts=[{"prompt": "..."}, ...])
- "Check which models actually work" → scan(verify=True) or get_fastest(verified=True)
- "Give me N models from different providers" → get_workers(count=N, verified=True)
- "Evaluate this translation" → backtranslate_eval(text, translation, source_lang, target_lang)

## Tool guide — Discovery
- list_providers() — See all providers, API-key status, and which subscription CLIs are installed. Call first when unsure.
- list_models(tier?, provider?, min_tier?, free_only?) — Browse catalog without pinging. \
  model_id = code name to use when inserting/configuring (API, Cursor, run()); label = display only. \
  min_tier="A" means A or better. free_only=true for free only. \
  Response includes is_free when known and cost_class \
  (zero|free_tier|subscription|local|paid|unknown).
- scan(..., verify?) — Ping models in parallel, get ranked by latency. Use when you need live speed data. \
  Set verify=true to also check models produce non-empty output (catches "ghost" models that ping UP but return empty content).
- get_fastest(min_tier?, provider?, count?, free_only?, verified?) — Best N models right now. \
  Example: get_fastest(free_only=True, min_tier="A", count=5) for "5 free A-or-better models". \
  Set verified=true to exclude models that return empty responses.
- provider_status() — Per-provider health check.

## Tool guide — Execution
- run(prompt, free_only?, model_id?, provider?, min_tier?, ...) — Run a prompt on the fastest model. \
  Use free_only=true when the user wants a free model. Retries on next fastest if one fails.
- ask(prompt, count=3, model_ids?, providers?, ...) — Run the same prompt on N models in parallel. \
  Pin subscriptions with providers=["claude","grok","gemini"] or model_ids=["sonnet","grok-4.6"]. \
  Default ask never spends a monthly plan.
- batch_run(prompts, ...) — Run multiple prompts with bounded concurrency. For translation pipelines, \
  data extraction, classification. Auto-retries failed items on alternate models. \
  Set results_file for incremental JSONL output and resume support.

## Tool guide — Evaluation (LLM-as-judge)
- judge(prompt, rubric, scale?, count?) — Rate a single item using N diverse judge models. \
  Returns aggregate scores, per-judge details, and inter-rater agreement.
- compare(item_a, item_b, context?, dimensions?, judge_count?) — Blind A/B comparison by N judges. \
  Randomizes item order per judge to prevent position bias.
- batch_judge(items, rubric, scale?, judge_count?, concurrency?, results_file?) — Run evaluations at scale. \
  Processes items with bounded concurrency and returns summary statistics. \
  Set results_file for incremental JSONL output and automatic resume on interruption.

## Tool guide — Pipeline utilities
- recommend(job, count?, include_subscriptions?, free_only?) — Short diverse lineup for a job \
  (translate|rewrite|review|code). Chat models only, one per provider. CLIs opt-in. \
  Use refs with ask(model_ids=…) or quality_probe(model_ids=…).
- quality_probe(job, model_ids?, providers?, count?) — Timed pass/fail on a fixed prompt \
  (EN→ZH, lemma rewrite, or a bare-return code bug).
- get_workers(count?, min_tier?, free_only?, verified?) — Get N verified-alive models across N distinct providers, \
  tier >= min_tier, ranked by latency. The single most common call pattern for translation pipelines. \
  Returns model_ids ready to use with run() or batch_run().
- backtranslate_eval(text, translation, source_lang, target_lang, back_model_id?) — \
  Translate back to source language using a different model, compute gloss overlap. \
  The most powerful non-circular quality metric for translation: translate→back-translate→overlap.

## Tool guide — Quality & Setup
- refresh_models(provider?, run_ping?, ping_limit?) — Fetch latest model lists from APIs; \
  use periodically so free/paid and model list stay current.
- benchmark(...) — Quality-test models; results show in later scan/get_fastest.
- setup_guide(provider?) — Signup instructions for unconfigured providers.
- configure_key(provider, api_key, key_id?) — Add/update a named key (does not delete others).
- credits(provider?) — Leftover USD/quota where a public API exists (OpenRouter, SiliconFlow, Groq headers).
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
- is_free in responses: true = free, false = paid, field missing = unknown. Use free_only=true to filter to Lane A (never invoices).
- cost_class: zero ($0/token), free_tier (NIM/Groq rate limits), subscription (CLI plan), local (Ollama), paid, unknown.
- Lanes: A never invoices (default), B subscription CLI (include_subscriptions), C can charge (include_paid and funded=true). profile() / set_profile() edit local spend_ok and funded. spend_ok is unprompted permission; funded means a paid call would work.
- quality_score: prefer 4/5 or 5/5; avoid below 3/5 when shown.
- If only one provider is configured, suggest setup_guide() for more coverage.
- run() retries on failure automatically; no need to implement retry yourself.

## Instructions for host agents
- **SSE and Cursor:** The server must be started in a separate terminal and already listening \
  before Cursor connects. If Cursor tries to connect before the server is up, it will timeout \
  ("fetch failed", "Connect Timeout"). On this host the unit is model-radar.service on port 8743. \
  Restart with `./scripts/restart-mcp.sh` or `systemctl --user restart model-radar.service`. \
  Do not kill+nohup a second copy.
- **Web dashboard:** `model-radar serve --transport sse --port 8743 --web` → http://127.0.0.1:8743/ \
  The server binds to 127.0.0.1 only; keys never leave the machine.
- **Restarting the server:** Call `restart_server()` so systemd can respawn, or run `./scripts/restart-mcp.sh`.
- **Starting the server:** `systemctl --user start model-radar.service` (port 8743). \
  Manual: `model-radar serve --transport sse --port 8743 --web`.
- **Privacy:** Do not log, echo, or send API keys off-host. list_providers and API responses \
  show only "configured" or "missing"; never the actual key. Keys are stored only in \
  ~/.model-radar/config.json (0o600).
"""

mcp = FastMCP("model-radar", instructions=MCP_INSTRUCTIONS, stateless_http=True)


def health_payload() -> dict:
    """Process identity for update scripts. No secrets."""
    from . import __version__
    names = sorted(
        getattr(t, "name", "")
        for t in getattr(getattr(mcp, "_tool_manager", None), "list_tools", lambda: [])()
        if getattr(t, "name", "")
    )
    if not names:
        names = sorted(
            n for n, fn in globals().items()
            if callable(fn) and getattr(fn, "__mcp_tool__", False)
        )
    return {
        "ok": True,
        "version": __version__,
        "listen": "127.0.0.1:8743",
        "tools": names,
        "has_still_free": "still_free" in names,
    }


async def _healthz(_request: Request) -> JSONResponse:
    return JSONResponse(health_payload())


mcp.custom_route("/healthz", ["GET"])(_healthz)

# Shared scan state for rolling averages across calls within a session
_state = ScanState()


@mcp.tool()
async def list_providers() -> str:
    """List all providers with status (configured/unconfigured, kind, model count).

    Call this first to see which providers you have API keys for, and which
    subscription CLIs (claude, grok, gemini, codex) are installed on PATH.
    No network requests — instant response.
    """
    import shutil
    cfg = load_config()
    rows = []
    total_models = 0
    configured = set(get_configured_providers(cfg))
    for key, prov in PROVIDERS.items():
        has_key = get_api_key(cfg, key) is not None
        enabled = is_provider_enabled(cfg, key)
        kind = getattr(prov, "kind", "https")
        n = len(prov.models)
        total_models += n
        row = {
            "provider": prov.name,
            "key": key,
            "models": n,
            "kind": kind,
            "access": "cli" if kind == "cli" else ("local" if key == "ollama" else "api_key"),
            "api_key": "configured" if has_key else ("n/a" if kind == "cli" else "missing"),
            "configured": key in configured,
            "enabled": enabled,
            "env_vars": list(prov.env_vars),
        }
        flags = get_provider_flags(cfg, key)
        row["lane"] = provider_lane(key)
        row["spend_ok"] = flags["spend_ok"]
        row["funded"] = flags["funded"]
        row["login"] = flags["login"]
        row["in_default_pool"] = in_default_pool(cfg, key)
        meta = get_key_meta(cfg, key)
        row["key_ids"] = meta["ids"]
        row["active_key"] = meta["active"]
        if kind == "cli":
            row["installed"] = bool(prov.cmd and shutil.which(prov.cmd))
        rows.append(row)
    return json.dumps({
        "total_providers": len(PROVIDERS),
        "configured": len(configured),
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
    from .provider_sync import ensure_catalog_fresh
    await ensure_catalog_fresh(provider)
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
        from .cost import cost_class
        if m.is_free is not None:
            row["is_free"] = m.is_free
        row["cost_class"] = cost_class(m.provider, m.model_id, m.is_free)
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
    verify: bool = False,
    verify_prompt: str | None = None,
) -> str:
    """Ping models in parallel and return ranked results by latency. Use when you need live speed data or a ranked list.

    Pings all matching models, returns sorted fastest-first. Takes 2-10 seconds depending on filters.

    When verify=True, sends a real prompt to each "up" model and checks for non-empty
    content. Models that return empty/garbage are marked as BROKEN (distinct from ERROR
    or OVERLOADED). This catches models that ping as UP but are functionally dead.
    Verification results are cached across scans within the session.

    Args:
        tier: Filter to exact tier (S+, S, A+, A, A-, B+, B, C)
        provider: Filter to provider key (nvidia, groq, cerebras, etc.)
        min_tier: Show this tier and above (e.g. "S" shows only S+ and S)
        configured_only: Only ping models whose provider has an API key
        free_only: Only include models marked as free (from API or :free/-free in id)
        limit: Max results (default 20, 0 = all)
        verify: Send a real prompt to validate non-empty content (default false)
        verify_prompt: Custom verification prompt (default "Reply with exactly: OK")
    """
    from .provider_sync import ensure_catalog_fresh
    await ensure_catalog_fresh(provider)
    results = await scan_models(
        tier=tier, provider=provider, min_tier=min_tier,
        configured_only=configured_only, free_only=free_only, limit=limit, state=_state,
        verify=verify, verify_prompt=verify_prompt,
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
    include_paid: bool = False,
    verified: bool = False,
) -> str:
    """Get the N fastest available models right now. Use when the user wants recommendations or \"best/fastest/free\" models.

    Pings configured providers and returns top N by latency. Use model_id from results as the code name when inserting or configuring (e.g. run(prompt, model_id=..., provider=...)). Example: get_fastest(free_only=True, min_tier=\"A\", count=5) for \"5 free A-or-better models\".

    When verified=True, also sends a real prompt to each model to confirm it produces
    non-empty output. Models that ping as UP but return empty content are excluded.

    Args:
        min_tier: Minimum quality tier (default "A" — shows S+, S, A+, A)
        provider: Limit to specific provider
        count: How many results (default 5)
        free_only: If true, only Lane A (never invoices)
        include_paid: Include funded Lane C hosts
        verified: If true, verify models produce non-empty output (default false)
    """
    from .provider_sync import ensure_catalog_fresh
    await ensure_catalog_fresh(provider)
    results = await scan_models(
        min_tier=min_tier, provider=provider,
        configured_only=True, free_only=free_only, include_paid=include_paid,
        limit=count * 2 if verified else count,
        state=_state, verify=verified,
    )
    # Subscription CLIs are opt-in (model_ids / providers=) — do not rank them as "fastest"
    # unless the caller named that CLI provider.
    if not (provider and is_cli_provider(provider)):
        results = [r for r in results if not is_cli_provider(r.model.provider)]
    # Only return models that are actually up
    up_results = [r for r in results if r.status == "up"][:count]
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
async def configure_key(
    provider: str,
    api_key: str,
    key_id: str = "default",
    make_active: bool | None = None,
) -> str:
    """Add or update a named API key. Does not delete other keys on this provider.

    Args:
        provider: Provider key (nvidia, groq, cerebras, minimax, …)
        api_key: The API key value
        key_id: Name for this key (e.g. coding-plan, paygo, work). Default 'default'.
        make_active: If true, this key is the one radar uses. If omitted, the
                     first key stays active.
    """
    if provider not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        return json.dumps({
            "error": f"Unknown provider '{provider}'",
            "available_providers": available,
        }, indent=2)

    cfg = load_config()
    meta = set_api_key(cfg, provider, api_key, key_id=key_id or "default", make_active=make_active)
    save_config(cfg)

    return json.dumps({
        "success": True,
        "provider": PROVIDERS[provider].name,
        "key_id": key_id or "default",
        "active_key": meta["active"],
        "key_ids": meta["ids"],
        "message": f"Saved key '{key_id or 'default'}' for {PROVIDERS[provider].name}. "
                   f"Active: {meta['active']}. Config: ~/.model-radar/config.json",
    }, indent=2)


@mcp.tool()
async def profile() -> str:
    """Show spend lanes and local funded/spend_ok flags. No secrets.

    Lane A = never invoices. B = subscription CLI. C = can charge.
    Default picks use Lane A only. Lane C needs funded=true and
    (spend_ok or include_paid).
    """
    cfg = load_config()
    rows = []
    for key, prov in PROVIDERS.items():
        flags = get_provider_flags(cfg, key)
        rows.append({
            "key": key,
            "provider": prov.name,
            "lane": provider_lane(key),
            "configured": key in get_configured_providers(cfg),
            "spend_ok": flags["spend_ok"],
            "funded": flags["funded"],
            "login": flags["login"],
        })
    return json.dumps({
        "spend_policy": "default Lane A; Lane C only if funded and (spend_ok or include_paid)",
        "providers": rows,
    }, indent=2)


@mcp.tool()
async def set_profile(
    provider: str,
    spend_ok: bool | None = None,
    funded: bool | None = None,
    login: str | None = None,
) -> str:
    """Set local spend_ok / funded / login for a provider. Saved to ~/.model-radar/config.json.

    spend_ok: allow unprompted paid picks (default false).
    funded: a paid call would work (card or credits). Not permission.
    login: how you signed up, e.g. github:youruser or google:you@example.com.
    """
    if provider not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        return json.dumps({
            "error": f"Unknown provider '{provider}'",
            "available_providers": available,
        }, indent=2)
    if spend_ok is None and funded is None and not login:
        return json.dumps({
            "error": "Pass spend_ok, funded, and/or login",
            "provider": provider,
        }, indent=2)
    cfg = load_config()
    set_provider_flags(cfg, provider, spend_ok=spend_ok, funded=funded, login=login)
    save_config(cfg)
    flags = get_provider_flags(cfg, provider)
    return json.dumps({
        "success": True,
        "provider": provider,
        "lane": provider_lane(provider),
        "spend_ok": flags["spend_ok"],
        "funded": flags["funded"],
        "login": flags["login"],
    }, indent=2)


@mcp.tool()
async def still_free(ping: bool = True, speed: str = "quality") -> str:
    """Lane A sweep: identify which default-pool hosts still answer.

    Use this before a Strong's judge night or dictmaster retranslate.
    Pings up to 3 chat models per host in parallel so you get a small
    live set. speed=quality ranks by tier; speed=fast prefers small /
    flash / lite ids (Cloudflare 20B before a 120B that needs >10s).
    OpenRouter only pings :free ids. Cooled hosts are listed, not pinged.
    Returns completion_calls so you can see the quota cost.

    Args:
        ping: If false, list candidates only (zero completions).
        speed: Probe class — quality (default) or fast.
    """
    from .sweep import still_free as _sweep
    return json.dumps(await _sweep(ping=ping, speed=speed), indent=2)


@mcp.tool()
async def credits(provider: str | None = None) -> str:
    """Read leftover credits or quota where a public API exists.

    OpenRouter: prepaid USD remaining. SiliconFlow: prepaid balance.
    Groq: remaining daily/minute rate limits (not dollars).
    Most other hosts have no credit API — those are omitted, not guessed.
    """
    from .credits import fetch_credits
    return json.dumps(fetch_credits(provider), indent=2)


@mcp.tool()
async def refresh_models(
    provider: str | None = None,
    run_ping: bool = False,
    ping_limit: int = 20,
) -> str:
    """Fetch latest model lists and replace each provider's catalog (add new ids, purge retired ones).

    Catalog GETs are free. A successful fetch discards that provider's previous
    list. An empty/failed fetch keeps the last snapshot. Use this to get the
    current catalog, then call scan() or get_fastest(). list_models() also
    refreshes any catalog older than an hour.

    Args:
        provider: Optional provider to refresh only (minimax, cerebras, ollama, …)
        run_ping: If true, run a ping test on up to ping_limit models after refreshing
        ping_limit: Max models to ping when run_ping is true (default 20)
    """
    from .provider_sync import refresh_models_from_live

    counts = await refresh_models_from_live(provider=provider)
    if not counts:
        return json.dumps({
            "refreshed": 0,
            "message": "No providers with API keys returned models.",
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
    from .provider_sync import ensure_catalog_fresh
    from .runner import run_on_fastest

    await ensure_catalog_fresh(provider)
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
    providers: list[str] | None = None,
    model_ids: list[str] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Run the same prompt on multiple models in parallel and return all responses.

    Use this for verification, consensus, and writing reviews. Pin subscription
    CLIs (claude, grok, gemini, codex) with model_ids or providers — they are
    never auto-picked, so a monthly plan is not spent by accident.

    Args:
        prompt: The question or task to send to all models
        system_prompt: Optional system prompt applied to all models
        count: How many models to query in parallel (default 3)
        min_tier: Minimum quality tier for model selection (default "A")
        provider: Limit auto-pick to one provider (nvidia, groq, claude, …)
        providers: Explicit provider list, e.g. ["claude", "grok", "gemini"]
        model_ids: Explicit models, e.g. ["sonnet", "grok-4.6"] or "claude/sonnet"
        max_tokens: Max response tokens per model (default 4096)
        temperature: Sampling temperature (default 0.0 for deterministic)
    """
    from .consensus import ask_models
    from .provider_sync import ensure_catalog_fresh

    await ensure_catalog_fresh(provider)
    result = await ask_models(
        prompt=prompt,
        system_prompt=system_prompt,
        count=count,
        min_tier=min_tier,
        provider=provider,
        providers=providers,
        model_ids=model_ids,
        max_tokens=max_tokens,
        temperature=temperature,
        state=_state,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def recommend(
    job: str = "code",
    count: int = 6,
    include_subscriptions: bool = False,
    free_only: bool = False,
    include_paid: bool = False,
) -> str:
    """Recommend a short diverse lineup for a job (no ping).

    Jobs: translate (EN/ZH and review), rewrite (lemma-study prose),
    review (code implementations), code (general coding).

    Returns chat models only, at most one per provider. Subscription CLIs
    are omitted unless include_subscriptions=True (they spend a monthly plan).

    Args:
        job: translate | rewrite | review | code | dict
        count: How many models (default 6, max 12)
        include_subscriptions: Include claude/grok/agy/codex (default false)
        free_only: Only Lane A (never invoices)
        include_paid: Include funded Lane C hosts (still skipped if funded is not true)
    """
    from .provider_sync import ensure_catalog_fresh
    from .recommend import JOBS, recommend_payload

    await ensure_catalog_fresh()
    if job not in JOBS:
        return json.dumps({
            "error": f"Unknown job '{job}'",
            "jobs": list(JOBS),
        }, indent=2)
    return json.dumps(
        recommend_payload(
            job=job,
            count=count,
            include_subscriptions=include_subscriptions,
            free_only=free_only,
            include_paid=include_paid,
        ),
        indent=2,
    )


@mcp.tool()
async def quality_probe(
    job: str = "translate",
    model_ids: list[str] | None = None,
    providers: list[str] | None = None,
    count: int = 3,
    include_subscriptions: bool = False,
) -> str:
    """Time and score a few models on a fixed probe for a job.

    translate — EN→ZH one sentence (CJK present, no prompt echo)
    rewrite   — lemma-study sentence (keep δικαιόω / righteous sense)
    review    — spot a bare `return` in first_even()
    dict      — Paper B five headwords (geography + covid, no echo)

    Omit model_ids to use recommend() for this job.

    Args:
        job: translate | rewrite | review | dict
        model_ids: Explicit models (provider/id or id)
        providers: One best model per named provider
        count: How many to pick when model_ids omitted (default 3)
        include_subscriptions: Allow CLI models in auto-pick (default false)
    """
    from .probe import run_quality_probe
    result = await run_quality_probe(
        job=job,
        model_ids=model_ids,
        providers=providers,
        count=count,
        include_subscriptions=include_subscriptions,
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def batch_run(
    prompts: list[dict],
    system_prompt: str | None = None,
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str = "A",
    free_only: bool = False,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    concurrency: int = 5,
    retry_on_fail: bool = True,
    results_file: str | None = None,
) -> str:
    """Run multiple prompts in parallel with bounded concurrency and auto-retry.

    For batch workloads: translation pipelines, data extraction, classification,
    content generation. Picks the fastest model and runs all prompts through it.
    Failed items are automatically retried on alternate models.

    Each prompt dict should have a "prompt" key and optional "system_prompt"
    (overrides the top-level system_prompt) and "metadata" keys for tracking.

    When results_file is set, each completed item is appended as a JSON line
    immediately. If interrupted, the file contains all completed items and
    can be resumed (already-completed indices are skipped).

    Args:
        prompts: List of {"prompt": "...", "system_prompt": "...", "metadata": {...}}
        system_prompt: Default system prompt for all items (per-item overrides)
        model_id: Specific model to use (skips scanning). Use list_models() to browse.
        provider: Limit to a specific provider
        min_tier: Minimum quality tier when auto-selecting (default "A")
        free_only: If true, only use free models
        max_tokens: Max response tokens per item (default 4096)
        temperature: Sampling temperature (default 0.0)
        concurrency: Max parallel requests (default 5)
        retry_on_fail: Auto-retry failed items on alternate models (default true)
        results_file: Path to JSONL file for incremental writes and resume support
    """
    from .runner import batch_run as _batch_run

    result = await _batch_run(
        prompts=prompts,
        system_prompt=system_prompt,
        model_id=model_id,
        provider=provider,
        min_tier=min_tier,
        free_only=free_only,
        max_tokens=max_tokens,
        temperature=temperature,
        concurrency=concurrency,
        retry_on_fail=retry_on_fail,
        results_file=results_file,
        state=_state,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def judge(
    prompt: str,
    rubric: list[str],
    scale: str = "1-5",
    count: int = 3,
    min_tier: str = "A",
    free_only: bool = False,
    output_format: str = "csv",
    max_tokens: int = 256,
    temperature: float = 0.0,
    exclude_providers: list[str] | None = None,
    exclude_model_ids: list[str] | None = None,
) -> str:
    """Rate a single item using N diverse judge models and return aggregate scores.

    Auto-selects judges spread across different providers for independence.
    Enforces structured output (CSV or JSON scores), retries on malformed
    responses, and computes inter-rater agreement metrics.

    Use this for evaluation tasks: rating translations, code quality,
    content accuracy, or any rubric-based assessment.

    Args:
        prompt: The evaluation prompt (describe what to rate and provide the content)
        rubric: List of scoring dimensions (e.g. ["accuracy", "naturalness", "completeness"])
        scale: Rating scale as "min-max" (default "1-5", also supports "1-10")
        count: Number of judge models to use (default 3)
        min_tier: Minimum quality tier for judge selection (default "A")
        free_only: If true, only use free models as judges
        output_format: How judges format scores — "csv" (default) or "json"
        max_tokens: Max response tokens per judge (default 256)
        temperature: Sampling temperature (default 0.0)
        exclude_providers: Do not use these hosts (pass the producer, e.g. ["minimax"])
        exclude_model_ids: Do not use these model ids
    """
    from .judge import judge_item

    result = await judge_item(
        prompt=prompt,
        rubric=rubric,
        scale=scale,
        count=count,
        min_tier=min_tier,
        free_only=free_only,
        output_format=output_format,
        max_tokens=max_tokens,
        temperature=temperature,
        state=_state,
        exclude_providers=exclude_providers,
        exclude_model_ids=exclude_model_ids,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def compare(
    item_a: str,
    item_b: str,
    context: str | None = None,
    dimensions: list[str] | None = None,
    scale: str = "1-5",
    judge_count: int = 3,
    blind: bool = True,
    min_tier: str = "A",
    free_only: bool = False,
    max_tokens: int = 512,
    temperature: float = 0.0,
    exclude_providers: list[str] | None = None,
    exclude_model_ids: list[str] | None = None,
) -> str:
    """Blind A/B comparison of two items judged by N models.

    When blind=True (default), randomizes which item is shown as A vs B
    to each judge independently, then de-randomizes scores. This prevents
    position bias where judges consistently favor the first item shown.

    Use for comparing translations, code solutions, summaries, or any
    pair of outputs where you want an objective preference.

    Args:
        item_a: First item to compare
        item_b: Second item to compare
        context: Optional context for the comparison (e.g. the original task)
        dimensions: Scoring dimensions (default ["quality"])
        scale: Rating scale as "min-max" (default "1-5")
        judge_count: Number of judge models (default 3)
        blind: Randomize A/B order per judge to prevent position bias (default true)
        min_tier: Minimum quality tier for judge selection (default "A")
        free_only: If true, only use free models as judges
        max_tokens: Max response tokens per judge (default 512)
        temperature: Sampling temperature (default 0.0)
        exclude_providers: Skip these hosts (the producer)
        exclude_model_ids: Skip these model ids
    """
    from .judge import compare_items

    result = await compare_items(
        item_a=item_a,
        item_b=item_b,
        context=context,
        dimensions=dimensions,
        scale=scale,
        judge_count=judge_count,
        blind=blind,
        min_tier=min_tier,
        free_only=free_only,
        max_tokens=max_tokens,
        temperature=temperature,
        state=_state,
        exclude_providers=exclude_providers,
        exclude_model_ids=exclude_model_ids,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def batch_judge(
    items: list[dict],
    rubric: list[str],
    scale: str = "1-5",
    judge_count: int = 3,
    min_tier: str = "A",
    free_only: bool = False,
    output_format: str = "csv",
    concurrency: int = 5,
    max_tokens: int = 256,
    temperature: float = 0.0,
    results_file: str | None = None,
    exclude_providers: list[str] | None = None,
    exclude_model_ids: list[str] | None = None,
) -> str:
    """Run judge evaluations at scale on a list of items.

    Processes items with bounded concurrency using a shared pool of diverse
    judges. Returns per-item scores, summary statistics (mean, stdev, min,
    max per dimension), and error counts.

    Each item in the list should have a "prompt" key with the evaluation
    prompt, and an optional "metadata" key for tracking (e.g. language,
    entry ID).

    When results_file is set, each scored item is appended as a JSON line
    immediately after scoring. On interruption, the file contains all
    completed items. On resume (same results_file), already-scored indices
    are skipped automatically.

    Args:
        items: List of {"prompt": "...", "metadata": {...}} dicts
        rubric: List of scoring dimensions (e.g. ["accuracy", "naturalness"])
        scale: Rating scale as "min-max" (default "1-5")
        judge_count: Judges per item (default 3)
        min_tier: Minimum quality tier for judge selection (default "A")
        free_only: If true, only use free models as judges
        output_format: How judges format scores — "csv" (default) or "json"
        concurrency: Max items evaluated in parallel (default 5)
        max_tokens: Max response tokens per judge (default 256)
        temperature: Sampling temperature (default 0.0)
        results_file: Path to JSONL file for incremental writes and resume support
        exclude_providers: Skip these hosts (the producer)
        exclude_model_ids: Skip these model ids
    """
    from .judge import batch_judge_items

    result = await batch_judge_items(
        items=items,
        rubric=rubric,
        scale=scale,
        judge_count=judge_count,
        min_tier=min_tier,
        free_only=free_only,
        output_format=output_format,
        concurrency=concurrency,
        max_tokens=max_tokens,
        temperature=temperature,
        state=_state,
        results_file=results_file,
        exclude_providers=exclude_providers,
        exclude_model_ids=exclude_model_ids,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_workers(
    count: int = 5,
    min_tier: str = "A",
    free_only: bool = False,
    verified: bool = True,
) -> str:
    """Get N verified-alive models across N distinct providers, ranked by tier then latency.

    The single most common pattern for translation pipelines and batch evaluation:
    "give me N working models from N different providers". Returns model_ids ready
    to use with run(model_id=...) or batch_run(model_id=...).

    Provider diversity is enforced: at most 1 model per provider. Models are verified
    alive by default (sends a real prompt to confirm non-empty output).

    Args:
        count: Number of workers to return (default 5)
        min_tier: Minimum quality tier (default "A")
        free_only: Only include free models (default false)
        verified: Verify models produce non-empty output (default true)
    """
    from .provider_sync import ensure_catalog_fresh
    await ensure_catalog_fresh()
    # Scan more models than needed to have room after provider dedup
    results = await scan_models(
        min_tier=min_tier, configured_only=True, free_only=free_only,
        limit=count * 4, state=_state, verify=verified,
    )
    up_results = [r for r in results if r.status == "up"]
    # Batch/translation workers should not silently spend Max/Pro quota.
    up_results = [r for r in up_results if not is_cli_provider(r.model.provider)]

    # Enforce provider diversity: 1 model per provider, best first
    seen_providers: set[str] = set()
    workers = []
    for r in up_results:
        if r.model.provider in seen_providers:
            continue
        # Skip providers with recent rate limit issues
        if _state.throttle.is_degraded(r.model.provider):
            continue
        seen_providers.add(r.model.provider)
        workers.append(format_result(r, _state))
        if len(workers) >= count:
            break

    # If we couldn't fill from distinct providers (after excluding degraded),
    # relax degraded filter
    if len(workers) < count:
        for r in up_results:
            if r.model.provider in seen_providers:
                continue
            seen_providers.add(r.model.provider)
            workers.append(format_result(r, _state))
            if len(workers) >= count:
                break

    return json.dumps({
        "count": len(workers),
        "distinct_providers": len(seen_providers),
        "verified": verified,
        "workers": workers,
        "usage": "Pass model_id and provider_key to run() or batch_run().",
    }, indent=2)


@mcp.tool()
async def backtranslate_eval(
    text: str,
    translation: str,
    source_lang: str,
    target_lang: str,
    back_model_id: str | None = None,
    min_tier: str = "A",
    free_only: bool = False,
    max_tokens: int = 512,
    exclude_providers: list[str] | None = None,
    exclude_model_ids: list[str] | None = None,
) -> str:
    """Evaluate a translation via back-translation and gloss overlap.

    Translates the output back to the source language using a different model,
    then computes word-level gloss overlap with the original text. This is the
    most powerful non-circular quality metric for translation:
    original → translate → back-translate → overlap.

    Returns the back-translation, overlap score (0.0-1.0), matching/missing/extra
    glosses, and the model used for back-translation.

    Args:
        text: Original source-language text (e.g. "father, head of household")
        translation: The translated text to evaluate (e.g. "Vater, Haupt eines Haushalts")
        source_lang: Source language name (e.g. "English")
        target_lang: Target language name (e.g. "German")
        back_model_id: Specific model for back-translation (default: auto-select different model)
        min_tier: Minimum quality tier for auto-selection (default "A")
        free_only: Only use free models (default false)
        max_tokens: Max response tokens (default 512)
        exclude_providers: Do not back-translate on these hosts (the producer)
        exclude_model_ids: Do not use these model ids
    """
    from .runner import backtranslate_eval as _backtranslate

    result = await _backtranslate(
        text=text,
        translation=translation,
        source_lang=source_lang,
        target_lang=target_lang,
        back_model_id=back_model_id,
        min_tier=min_tier,
        free_only=free_only,
        max_tokens=max_tokens,
        state=_state,
        exclude_providers=exclude_providers,
        exclude_model_ids=exclude_model_ids,
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
            "hint": "Example: systemctl --user restart model-radar.service",
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
    from . import __version__
    from .db import get_cache_meta
    catalog = {}
    try:
        from .provider_sync import HTTPS_CATALOG_KEYS
        from .db import catalog_fetched_at
        latest = None
        for key in HTTPS_CATALOG_KEYS:
            dt = catalog_fetched_at(key)
            if dt and (latest is None or dt > latest):
                latest = dt
        catalog = {
            "last_fetch": latest.isoformat() if latest else None,
            "source_sample": get_cache_meta("catalog:minimax:source"),
        }
    except Exception:
        catalog = {}
    return json.dumps({
        "version": __version__,
        "started_at": started_at.isoformat(),
        "started_at_epoch": _server_start_time,
        "uptime_seconds": round(uptime, 2),
        "uptime_human": f"{int(uptime)}s",
        "catalog": catalog,
        "listen": "127.0.0.1:8743",
    }, indent=2)


def create_server() -> FastMCP:
    """Return the MCP server instance.

    Catalog refresh is started from the serve loop (see cli._run_uvicorn),
    not here — create_server() runs before an event loop exists.
    """
    global _server_start_time
    if _server_start_time is None:
        _server_start_time = time.time()
    return mcp


async def _startup_refresh() -> None:
    """Background task: refresh model catalog from live APIs. Errors are logged, never raised."""
    try:
        from .provider_sync import ensure_catalog_fresh
        counts = await ensure_catalog_fresh(force=True)
        total = sum(counts.values()) if counts else 0
        if total > 0:
            import sys
            print(f"[model-radar] startup refresh: {counts} (total {total})", file=sys.stderr)
    except Exception as e:
        import sys
        print(f"[model-radar] startup refresh failed: {e}", file=sys.stderr)


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
