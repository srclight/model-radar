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
def serve(transport: str, port: int):
    """Start the MCP server."""
    from .server import create_server

    server = create_server()
    if transport == "sse":
        server.settings.host = "127.0.0.1"
        server.settings.port = port
    server.run(transport=transport)


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
