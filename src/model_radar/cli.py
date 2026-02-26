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
    import uvicorn
    server = uvicorn.Server(config)
    await server.serve()


@main.command()
@click.option("--provider", "-p", default=None, help="Filter by provider key")
@click.option("--tier", "-t", default=None, help="Filter by exact tier (S+, S, A, etc.)")
@click.option("--min-tier", "-m", default="A", help="Minimum tier (default: A)")
@click.option("--limit", "-n", type=int, default=10, help="Max results")
def scan(provider: str | None, tier: str | None, min_tier: str | None, limit: int):
    """Scan models and show results (CLI mode)."""
    import asyncio
    import json

    from .scanner import format_result, scan_models

    async def _run():
        results = await scan_models(
            tier=tier, provider=provider, min_tier=min_tier, limit=limit,
        )
        for r in results:
            d = format_result(r)
            status = d["status"]
            lat = f"{d['latency_ms']}ms" if d["latency_ms"] else "---"
            click.echo(f"  {status:<12} {lat:>8}  [{d['tier']:>3}] {d['label']:<25} {d['provider']}")

    asyncio.run(_run())


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
def configure(provider: str, api_key: str):
    """Save an API key to ~/.model-radar/config.json.

    Example: model-radar configure nvidia nvapi-xxx
    """
    from .config import CONFIG_PATH, load_config, save_config
    from .providers import PROVIDERS

    if provider not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        click.echo(f"Unknown provider '{provider}'. Available: {available}", err=True)
        raise SystemExit(1)

    cfg = load_config()
    cfg["api_keys"][provider] = api_key
    save_config(cfg)
    click.echo(f"Saved {PROVIDERS[provider].name} key to {CONFIG_PATH}")
