"""
CLI entry point for model-radar.
"""

from __future__ import annotations

import click

from . import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="model-radar")
@click.pass_context
def main(ctx: click.Context):
    """model-radar: Free coding model discovery MCP server."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


@main.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio",
              help="MCP transport (default: stdio)")
@click.option("--port", type=int, default=8765, help="Port for SSE transport")
@click.option("--web", is_flag=True, help="Serve dashboard and REST API at / and /api/* (SSE only)")
def serve(transport: str, port: int, web: bool):
    """Start the MCP server."""
    import anyio

    from .server import create_server

    server = create_server()
    if transport == "sse":
        # Local only: bind to localhost so the server is never exposed on the network
        server.settings.host = "127.0.0.1"
        server.settings.port = port
        if web:
            from .web import add_web_routes
            add_web_routes(server)
        # Serve both SSE and Streamable HTTP on the same port so Cursor can connect
        # (Cursor tries Streamable HTTP first, then SSE)
        from .server import make_sse_and_streamable_http_app
        import uvicorn
        app = make_sse_and_streamable_http_app(mount_path="/")
        config = uvicorn.Config(
            app,
            host=server.settings.host,
            port=server.settings.port,
            log_level=server.settings.log_level.lower(),
        )
        anyio.run(_run_uvicorn, config)
        return
    elif web:
        click.echo("--web requires --transport sse; ignoring --web.", err=True)
    server.run(transport=transport)


async def _run_uvicorn(config) -> None:
    import asyncio

    import uvicorn

    from .server import _startup_refresh

    # create_server() runs before the event loop exists, so the in-process
    # ensure_future is a no-op. Kick refresh once uvicorn owns a loop.
    asyncio.create_task(_startup_refresh())
    server = uvicorn.Server(config)
    await server.serve()


@main.command("still-free")
@click.option("--no-ping", "ping", is_flag=True, default=True, flag_value=False,
              help="List Lane A hosts only; do not send completions")
def still_free_cmd(ping: bool):
    """One cheap ping per Lane A host in the default pool."""
    import asyncio
    import json

    from .sweep import still_free

    click.echo(json.dumps(asyncio.run(still_free(ping=ping)), indent=2))


@main.command()
@click.option("--job", "-j", type=click.Choice(["translate", "rewrite", "review", "dict"]), default="translate")
@click.option("--count", "-n", default=3, help="How many models to probe")
@click.option("--include-subscriptions", is_flag=True, help="Allow CLI subscriptions")
def probe(job: str, count: int, include_subscriptions: bool):
    """Time and score a fixed prompt (translate / rewrite / review)."""
    import asyncio
    import json

    from .probe import run_quality_probe

    result = asyncio.run(run_quality_probe(
        job=job, count=count, include_subscriptions=include_subscriptions,
    ))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@main.command()
@click.option("--provider", "-p", default=None, help="Filter by provider key")
@click.option("--tier", "-t", default=None, help="Filter by exact tier (S+, S, A, etc.)")
@click.option("--min-tier", "-m", default="A", help="Minimum tier (default: A)")
@click.option("--free", "free_only", is_flag=True, help="Only scan models marked as free")
@click.option("--limit", "-n", type=int, default=10, help="Max results")
def scan(provider: str | None, tier: str | None, min_tier: str | None, free_only: bool, limit: int):
    """Scan models and show results (CLI mode)."""
    import asyncio
    import json

    from .scanner import format_result, scan_models

    async def _run():
        results = await scan_models(
            tier=tier, provider=provider, min_tier=min_tier, free_only=free_only, limit=limit,
        )
        for r in results:
            d = format_result(r)
            status = d["status"]
            lat = f"{d['latency_ms']}ms" if d["latency_ms"] else "---"
            free_tag = " free" if d.get("is_free") else ""
            click.echo(f"  {status:<12} {lat:>8}  [{d['tier']:>3}] {d['label']:<25} {d['provider']}{free_tag}")

    asyncio.run(_run())


@main.command()
@click.option("--prompt", "-P", default="What time is it right now? Reply briefly with the current date and time.", help="Prompt to send")
@click.option("--min-tier", "-m", default="S", help="Minimum tier (default: S)")
@click.option("--count", "-n", type=int, default=10, help="Number of models to ask (default: 10)")
@click.option("--raw", is_flag=True, help="Print raw JSON output (for debugging)")
def ask(prompt: str, min_tier: str, count: int, raw: bool):
    """Ask the same prompt to the top N models (min tier); print raw JSON if --raw."""
    import asyncio
    import json

    from .consensus import ask_models

    async def _run():
        return await ask_models(prompt=prompt, min_tier=min_tier, count=count, max_tokens=80)

    result = asyncio.run(_run())
    if raw:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        # Chart: Model | Provider | Raw answer (unparsed from API)
        rows = result.get("responses", [])
        click.echo(f"\n  {'Model':<30} {'Provider':<10} Raw answer (unparsed)")
        click.echo("  " + "-" * 100)
        for r in rows:
            label = (r.get("model_label") or "?")[:28]
            prov = (r.get("provider") or "?")[:8]
            raw_response = r.get("raw_response")
            if raw_response is not None:
                raw_str = json.dumps(raw_response, ensure_ascii=False, default=str).replace("\n", " ")
                if len(raw_str) > 800:
                    raw_str = raw_str[:797] + "..."
            else:
                raw_str = "(no raw response)"
            click.echo(f"  {label:<30} {prov:<10} {raw_str}")
        click.echo("")

@main.command()
def providers():
    """List all providers and their configuration status."""
    from .config import get_api_key, is_provider_enabled, load_config
    from .providers import PROVIDERS

    cfg = load_config()
    for key, prov in PROVIDERS.items():
        has_key = get_api_key(cfg, key) is not None
        enabled = is_provider_enabled(cfg, key)
        status = "OK" if has_key else "no key"
        if not enabled:
            status = "disabled"
        click.echo(f"  {prov.name:<16} [{key:<12}] {len(prov.models):>3} models  {status}")


@main.command()
@click.argument("provider")
@click.argument("api_key")
@click.option("--id", "key_id", default="default", help="Name this key (e.g. coding-plan, paygo)")
@click.option("--active/--no-active", default=None, help="Make this the key radar uses")
def configure(provider: str, api_key: str, key_id: str, active: bool | None):
    """Add or update a named API key. Does not delete other keys.

    Example: model-radar configure minimax sk-cp-xxx --id coding-plan
    """
    from .config import CONFIG_PATH, load_config, save_config, set_api_key
    from .providers import PROVIDERS

    if provider not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        click.echo(f"Unknown provider '{provider}'. Available: {available}", err=True)
        raise SystemExit(1)

    cfg = load_config()
    meta = set_api_key(cfg, provider, api_key, key_id=key_id, make_active=active)
    save_config(cfg)
    click.echo(
        f"Saved {PROVIDERS[provider].name} key '{key_id}' "
        f"(active={meta['active']}) to {CONFIG_PATH}"
    )


@main.command()
@click.option("--provider", "-p", default=None)
def credits(provider: str | None):
    """Show leftover credits/quota for hosts that expose an API."""
    import json

    from .credits import fetch_credits

    click.echo(json.dumps(fetch_credits(provider), indent=2))


@main.group(invoke_without_command=True)
@click.pass_context
def profile(ctx: click.Context):
    """Show spend lanes and local funded/spend_ok flags."""
    if ctx.invoked_subcommand is not None:
        return
    from .config import get_configured_providers, get_provider_flags, load_config
    from .lanes import provider_lane
    from .providers import PROVIDERS

    cfg = load_config()
    configured = set(get_configured_providers(cfg))
    click.echo(f"  {'key':<14} {'lane':<6} {'cfg':<4} {'ok':<4} {'funded':<6} login")
    for key, _prov in PROVIDERS.items():
        flags = get_provider_flags(cfg, key)
        funded_s = {True: "yes", False: "no"}.get(flags["funded"], "?")
        click.echo(
            f"  {key:<14} {provider_lane(key):<6} "
            f"{'yes' if key in configured else '-':<4} "
            f"{'yes' if flags['spend_ok'] else 'no':<4} "
            f"{funded_s:<6} {flags['login'] or '—'}"
        )


@profile.command("set")
@click.argument("provider")
@click.option("--spend-ok/--no-spend-ok", default=None)
@click.option("--funded/--no-funded", default=None)
@click.option("--login", default=None, help="How you signed up, e.g. github:youruser or google:you@example.com")
def profile_set(provider: str, spend_ok: bool | None, funded: bool | None, login: str | None):
    """Set spend_ok / funded / login for a provider (local config only)."""
    from .config import CONFIG_PATH, load_config, save_config, set_provider_flags, get_provider_flags
    from .lanes import provider_lane
    from .providers import PROVIDERS

    if provider not in PROVIDERS:
        click.echo(f"Unknown provider '{provider}'", err=True)
        raise SystemExit(1)
    if spend_ok is None and funded is None and not login:
        click.echo("Pass --login and/or --spend-ok/--funded", err=True)
        raise SystemExit(1)
    cfg = load_config()
    set_provider_flags(cfg, provider, spend_ok=spend_ok, funded=funded, login=login)
    save_config(cfg)
    flags = get_provider_flags(cfg, provider)
    click.echo(
        f"{provider} lane={provider_lane(provider)} "
        f"spend_ok={flags['spend_ok']} funded={flags['funded']} "
        f"login={flags['login'] or '—'} → {CONFIG_PATH}"
    )


@main.group()
def db():
    """Database management commands."""
    pass


@db.command()
def sync():
    """Sync hardcoded provider models to SQLite database."""
    import json
    from .db import DB_PATH, sync_models

    click.echo(f"Syncing models to {DB_PATH}...")
    stats = sync_models()

    total = sum(stats.values())
    click.echo(f"Synced {total} models from {len(stats)} providers:")
    for provider_key, count in sorted(stats.items()):
        click.echo(f"  - {provider_key}: {count} models")


@db.command()
def status():
    """Show database statistics."""
    from .db import DB_PATH, get_stats, get_provider_stats

    stats = get_stats()
    provider_stats = get_provider_stats()

    click.echo(f"Database: {DB_PATH}")
    click.echo(f"Models: {stats['active_models']} active, {stats['inactive_models']} inactive")
    click.echo(f"Providers: {stats['providers']}")
    click.echo(f"Ping results: {stats['ping_results']}")
    if stats['last_ping']:
        click.echo(f"Last ping: {stats['last_ping']}")
    click.echo()
    click.echo("Per-provider breakdown:")
    for provider_key, pstats in sorted(provider_stats.items()):
        active = pstats['active_models']
        total = pstats['total_models']
        click.echo(f"  - {provider_key}: {active}/{total} models")


@db.command()
@click.option("--provider", "-p", default=None, help="Filter by provider key")
@click.option("--tier", "-t", default=None, help="Filter by exact tier")
@click.option("--min-tier", "-m", default=None, help="Filter by minimum tier")
@click.option("--inactive", is_flag=True, help="Include inactive models")
def query(provider: str | None, tier: str | None, min_tier: str | None, inactive: bool):
    """Query models from database."""
    from .db import filter_models

    models = filter_models(
        tier=tier,
        provider=provider,
        min_tier=min_tier,
        active_only=not inactive,
    )

    click.echo(f"Found {len(models)} models:")
    for model in models[:50]:  # Limit output
        click.echo(f"  [{model.tier:>3}] {model.label:<30} {model.provider}/{model.model_id}")

    if len(models) > 50:
        click.echo(f"  ... and {len(models) - 50} more")


@db.command()
@click.option("--provider", "-p", default=None, help="Specific provider to fetch (openrouter, nvidia, groq)")
@click.option("--compare", "-c", is_flag=True, help="Compare with hardcoded models")
def live(provider: str | None, compare: bool):
    """Fetch live model list from provider APIs.
    
    Requires API keys for the providers you want to query.
    Supported: openrouter, nvidia, groq
    """
    import asyncio
    from .provider_sync import fetch_all_provider_models, compare_models
    from .db import filter_models as db_filter_models
    
    click.echo("Fetching live models from provider APIs...")
    
    async def _fetch():
        return await fetch_all_provider_models(provider)
    
    results = asyncio.run(_fetch())
    
    if compare:
        click.echo("\nComparison with hardcoded models:")
        for provider_key, models in results.items():
            hardcoded = db_filter_models(provider=provider_key)
            comparison = compare_models(hardcoded, models)
            
            click.echo(f"\n  {provider_key}:")
            click.echo(f"    Hardcoded: {len(hardcoded)}")
            click.echo(f"    Live: {len(models)}")
            if comparison['missing']:
                click.echo(f"    New in live ({len(comparison['missing'])}): {', '.join(comparison['missing'][:5])}")
                if len(comparison['missing']) > 5:
                    click.echo(f"      ... and {len(comparison['missing']) - 5} more")
            if comparison['extra']:
                click.echo(f"    Missing from live ({len(comparison['extra'])}): {', '.join(comparison['extra'][:5])}")
    else:
        for provider_key, models in results.items():
            click.echo(f"\n{provider_key} ({len(models)} models):")
            for model in models[:20]:
                click.echo(f"  - {model.model_id}")
            if len(models) > 20:
                click.echo(f"  ... and {len(models) - 20} more")


@db.command()
@click.option("--provider", "-p", default=None, help="Filter by provider")
@click.option("--limit", "-l", default=10, help="Max models to report")
def obsolete(provider: str | None, limit: int):
    """Check which hardcoded models are obsolete (not in live APIs).
    
    Compares hardcoded models against live provider APIs to identify
    models that may have been deprecated or removed.
    """
    import asyncio
    from .provider_sync import fetch_all_provider_models
    from .db import filter_models as db_filter_models
    from .provider_sync import compare_models
    
    click.echo("Checking for obsolete models...")
    
    async def _check():
        return await fetch_all_provider_models(provider)
    
    live = asyncio.run(_check())
    
    obsolete_list = []
    for provider_key in (provider,) if provider else ["openrouter", "nvidia", "groq"]:
        hardcoded = db_filter_models(provider=provider_key)
        live_models = live.get(provider_key, [])
        
        comparison = compare_models(hardcoded, live_models)
        
        if comparison['extra']:  # In hardcoded but not in live
            for model in hardcoded:
                if model.model_id in comparison['extra']:
                    obsolete_list.append((provider_key, model))
    
    if not obsolete_list:
        click.echo("✓ No obsolete models found!")
        return
    
    click.echo(f"\n⚠️  Found {len(obsolete_list)} potentially obsolete models:")
    for i, (prov, model) in enumerate(obsolete_list[:limit]):
        click.echo(f"  [{model.tier}] {prov}/{model.model_id} - {model.label}")
    
    if len(obsolete_list) > limit:
        click.echo(f"  ... and {len(obsolete_list) - limit} more")


@db.command()
@click.option("--provider", "-p", default=None, help="Fetch only this provider (openrouter, nvidia, groq)")
@click.option("--ping", is_flag=True, help="Run ping test after refreshing (tests all refreshed models)")
@click.option("--ping-limit", default=50, help="Max models to ping when --ping (default 50)")
def refresh(provider: str | None, ping: bool, ping_limit: int):
    """Fetch latest model lists and replace each provider's catalog.

    Successful fetch: new ids in, retired ids gone. Empty fetch keeps the
    last snapshot. Catalog GETs are free. Then optionally ping.
    """
    import asyncio
    from .provider_sync import refresh_models_from_live
    from .ping_test import ping_all_models, print_ping_results

    click.echo("Fetching latest models from provider APIs (configured only)...")
    async def _refresh():
        return await refresh_models_from_live(provider=provider)
    counts = asyncio.run(_refresh())

    if not counts:
        click.echo("No providers with API keys returned models.")
        return

    total = sum(counts.values())
    click.echo(f"Refreshed {total} models from {len(counts)} provider(s):")
    for key, n in sorted(counts.items()):
        click.echo(f"  - {key}: {n} models")

    if ping:
        click.echo(f"\nPing testing up to {ping_limit} models...")
        async def _test():
            return await ping_all_models(provider=provider, limit=ping_limit, concurrency=5)
        results = asyncio.run(_test())
        print_ping_results(results)


@db.command()
@click.option("--provider", "-p", default=None, help="Filter by provider")
@click.option("--limit", "-l", default=20, help="Max models to test")
@click.option("--concurrency", "-c", default=5, help="Concurrent requests")
def ping_test(provider: str | None, limit: int, concurrency: int):
    """Ping test models to verify they're working.
    
    Actually calls the API to test if models are accessible.
    Records results to database.
    """
    import asyncio
    from .ping_test import ping_all_models, print_ping_results
    
    click.echo(f"Ping testing models (limit={limit}, concurrency={concurrency})...")
    
    async def _test():
        return await ping_all_models(provider=provider, limit=limit, concurrency=concurrency)
    
    results = asyncio.run(_test())
    print_ping_results(results)
