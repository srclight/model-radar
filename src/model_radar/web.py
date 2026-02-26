"""
Web dashboard and REST API for model-radar (optional, used with --web when serving SSE).

Privacy-first, local-only: the server binds to 127.0.0.1 only. All data and API keys
stay on the user's machine. Keys are never logged, echoed in responses, or sent
anywhere except to the local config file (~/.model-radar/config.json). No telemetry.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Model Radar</title>
  <style>
    :root { --bg: #0f1117; --surface: #161b22; --border: #30363d; --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff; --success: #3fb950; --danger: #f85149; }
    * { box-sizing: border-box; }
    body { font-family: ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1rem; line-height: 1.5; }
    h1 { font-size: 1.5rem; margin: 0 0 1rem; }
    h2 { font-size: 1.1rem; margin: 1rem 0 0.5rem; color: var(--muted); }
    section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 600; }
    button, input[type="submit"] { background: var(--accent); color: #fff; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.9rem; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button.secondary { background: var(--surface); color: var(--text); border: 1px solid var(--border); }
    input, select, textarea { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 0.5rem; border-radius: 6px; width: 100%; max-width: 400px; }
    label { display: block; margin-bottom: 0.25rem; color: var(--muted); font-size: 0.85rem; }
    .form-row { margin-bottom: 0.75rem; }
    .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.5rem; }
    .status-up { background: var(--success); }
    .status-down { background: var(--danger); }
    .loading { color: var(--muted); }
    .error { color: var(--danger); font-size: 0.9rem; }
    .flex { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
    #scanResults, #fastestResults, #runOutput, #askOutput { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 0.85rem; max-height: 300px; overflow: auto; }
  </style>
</head>
<body>
  <h1>Model Radar</h1>
  <p style="color: var(--muted); margin: 0 0 0.5rem;">Status, config, discovery, and run — same server as MCP (SSE at <code>/sse</code>).</p>
  <p style="margin: 0 0 1rem; font-size: 0.9rem; color: var(--success);"><strong>Local only.</strong> Server listens on 127.0.0.1. Your keys and data never leave this machine; keys are stored only in ~/.model-radar/config.json (0o600).</p>

  <section>
    <h2>Status</h2>
    <div class="flex">
      <button type="button" id="btnProviderStatus">Provider health</button>
      <button type="button" id="btnFastest">Get fastest (5)</button>
    </div>
    <div id="statusOutput" class="loading">Click a button to load.</div>
  </section>

  <section>
    <h2>Config</h2>
    <div class="flex">
      <button type="button" id="btnListProviders">List providers</button>
    </div>
    <div id="configTable"></div>
    <div class="form-row" style="margin-top: 1rem;">
      <label>Add API key</label>
      <div class="flex">
        <input type="text" id="configProvider" placeholder="e.g. groq" style="max-width: 120px;">
        <input type="password" id="configKey" placeholder="API key" style="max-width: 200px;">
        <button type="button" id="btnConfigureKey">Save key</button>
      </div>
      <div id="configKeyResult" class="error"></div>
    </div>
    <div style="margin-top: 0.5rem;"><a href="#" id="linkSetupGuide" style="color: var(--accent);">Setup guide (unconfigured providers)</a></div>
    <div id="setupGuideOutput" style="margin-top: 0.5rem;"></div>
  </section>

  <section>
    <h2>Discovery</h2>
    <div class="flex">
      <label>Min tier</label>
      <select id="scanMinTier" style="max-width: 80px;">
        <option value="S+">S+</option><option value="S">S</option><option value="A+" selected>A+</option><option value="A">A</option><option value="A-">A-</option><option value="B+">B+</option><option value="B">B</option><option value="C">C</option>
      </select>
      <input type="number" id="scanLimit" value="10" min="1" max="50" style="max-width: 60px;">
      <button type="button" id="btnScan">Scan (ping models)</button>
      <button type="button" id="btnListModels" class="secondary">List models (catalog)</button>
    </div>
    <div id="scanResults" style="margin-top: 0.5rem;"></div>
  </section>

  <section>
    <h2>Execution</h2>
    <div class="form-row">
      <label>Prompt</label>
      <textarea id="runPrompt" rows="3" placeholder="Enter a prompt to run on the fastest model."></textarea>
    </div>
    <div class="flex">
      <button type="button" id="btnRun">Run (fastest model)</button>
      <button type="button" id="btnAsk">Ask 3 models (consensus)</button>
    </div>
    <div id="runOutput" style="margin-top: 0.5rem;"></div>
    <div id="askOutput" style="margin-top: 0.5rem;"></div>
  </section>

  <section>
    <h2>Server</h2>
    <div class="flex">
      <button type="button" id="btnServerStats">Server stats (started at, uptime)</button>
      <button type="button" id="btnRestart" class="secondary">Request restart (SSE only, requires MODEL_RADAR_ALLOW_RESTART=1)</button>
    </div>
    <div id="serverStatsOutput" style="margin-top: 0.5rem; color: var(--muted); font-size: 0.9rem;"></div>
    <div id="restartOutput" style="margin-top: 0.5rem;"></div>
  </section>

  <script>
    const api = (path, opts = {}) => fetch(path, { headers: { Accept: 'application/json', ...opts.headers }, ...opts }).then(r => r.json());
    const set = (id, text, isError) => { const el = document.getElementById(id); el.textContent = text; el.className = isError ? 'error' : ''; };
    const setHtml = (id, html) => { document.getElementById(id).innerHTML = html; };

    document.getElementById('btnProviderStatus').onclick = async () => {
      set('statusOutput', 'Loading…');
      try {
        const data = await api('/api/provider_status');
        set('statusOutput', JSON.stringify(data, null, 2));
      } catch (e) { set('statusOutput', e.message, true); }
    };
    document.getElementById('btnFastest').onclick = async () => {
      set('statusOutput', 'Loading…');
      try {
        const data = await api('/api/get_fastest?count=5');
        set('statusOutput', JSON.stringify(data, null, 2));
      } catch (e) { set('statusOutput', e.message, true); }
    };
    document.getElementById('btnListProviders').onclick = async () => {
      try {
        const data = await api('/api/list_providers');
        const rows = (data.providers || []).map(p => `<tr><td>${p.provider}</td><td>${p.key}</td><td>${p.models}</td><td>${p.api_key}</td><td>${p.enabled ? 'yes' : 'no'}</td></tr>`).join('');
        setHtml('configTable', data.providers && data.providers.length ? `<table><tr><th>Provider</th><th>Key</th><th>Models</th><th>API key</th><th>Enabled</th></tr>${rows}</table>` : '<p class="muted">No providers</p>');
      } catch (e) { setHtml('configTable', '<span class="error">' + e.message + '</span>'); }
    };
    document.getElementById('btnConfigureKey').onclick = async () => {
      const provider = document.getElementById('configProvider').value.trim();
      const api_key = document.getElementById('configKey').value.trim();
      if (!provider || !api_key) { set('configKeyResult', 'Provider and key required', true); return; }
      set('configKeyResult', '');
      try {
        const data = await api('/api/configure_key', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider, api_key }) });
        set('configKeyResult', data.message || (data.error || JSON.stringify(data)), !!data.error);
      } catch (e) { set('configKeyResult', e.message, true); }
    };
    document.getElementById('linkSetupGuide').onclick = async (e) => {
      e.preventDefault();
      try {
        const data = await api('/api/setup_guide');
        document.getElementById('setupGuideOutput').textContent = JSON.stringify(data, null, 2);
      } catch (err) { document.getElementById('setupGuideOutput').textContent = err.message; }
    };
    document.getElementById('btnScan').onclick = async () => {
      const minTier = document.getElementById('scanMinTier').value;
      const limit = document.getElementById('scanLimit').value;
      set('scanResults', 'Scanning…');
      try {
        const data = await api('/api/scan?min_tier=' + encodeURIComponent(minTier) + '&limit=' + limit);
        set('scanResults', JSON.stringify(data, null, 2));
      } catch (e) { set('scanResults', e.message, true); }
    };
    document.getElementById('btnListModels').onclick = async () => {
      set('scanResults', 'Loading…');
      try {
        const data = await api('/api/list_models');
        set('scanResults', JSON.stringify(data, null, 2));
      } catch (e) { set('scanResults', e.message, true); }
    };
    document.getElementById('btnRun').onclick = async () => {
      const prompt = document.getElementById('runPrompt').value.trim();
      if (!prompt) return;
      set('runOutput', 'Running…');
      try {
        const data = await api('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }) });
        set('runOutput', JSON.stringify(data, null, 2));
      } catch (e) { set('runOutput', e.message, true); }
    };
    document.getElementById('btnAsk').onclick = async () => {
      const prompt = document.getElementById('runPrompt').value.trim();
      if (!prompt) return;
      set('askOutput', 'Asking 3 models…');
      try {
        const data = await api('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt, count: 3 }) });
        set('askOutput', JSON.stringify(data, null, 2));
      } catch (e) { set('askOutput', e.message, true); }
    };
    document.getElementById('btnServerStats').onclick = async () => {
      const el = document.getElementById('serverStatsOutput');
      el.textContent = 'Loading…';
      try {
        const data = await api('/api/server_stats');
        el.innerHTML = `Started at <strong>${data.started_at}</strong> · Uptime <strong>${data.uptime_human}</strong> (${data.uptime_seconds}s)`;
        el.className = '';
      } catch (e) { el.textContent = e.message; el.className = 'error'; }
    };
    document.getElementById('btnRestart').onclick = async () => {
      set('restartOutput', 'Calling restart…');
      try {
        const data = await api('/api/restart_server');
        set('restartOutput', JSON.stringify(data, null, 2));
      } catch (e) { set('restartOutput', e.message, true); }
    };
    // Load server stats on page load
    document.getElementById('btnServerStats').click();
  </script>
</body>
</html>
"""


async def _api_list_providers(_request: Request) -> Response:
    from .server import list_providers
    body = await list_providers()
    return JSONResponse(json.loads(body))


async def _api_list_models(request: Request) -> Response:
    from .server import list_models
    tier = request.query_params.get("tier")
    provider = request.query_params.get("provider")
    min_tier = request.query_params.get("min_tier")
    body = await list_models(tier=tier or None, provider=provider or None, min_tier=min_tier or None)
    return JSONResponse(json.loads(body))


async def _api_scan(request: Request) -> Response:
    from .server import scan
    tier = request.query_params.get("tier")
    provider = request.query_params.get("provider")
    min_tier = request.query_params.get("min_tier")
    configured_only = request.query_params.get("configured_only", "false").lower() == "true"
    try:
        limit = int(request.query_params.get("limit", "20"))
    except ValueError:
        limit = 20
    body = await scan(tier=tier or None, provider=provider or None, min_tier=min_tier or None, configured_only=configured_only, limit=limit)
    return JSONResponse(json.loads(body))


async def _api_get_fastest(request: Request) -> Response:
    from .server import get_fastest
    min_tier = request.query_params.get("min_tier", "A")
    provider = request.query_params.get("provider")
    try:
        count = int(request.query_params.get("count", "5"))
    except ValueError:
        count = 5
    body = await get_fastest(min_tier=min_tier, provider=provider or None, count=count)
    return JSONResponse(json.loads(body))


async def _api_provider_status(_request: Request) -> Response:
    from .server import provider_status
    body = await provider_status()
    return JSONResponse(json.loads(body))


async def _api_setup_guide(request: Request) -> Response:
    from .server import setup_guide
    provider = request.query_params.get("provider")
    body = await setup_guide(provider=provider or None)
    return JSONResponse(json.loads(body))


async def _api_configure_key(request: Request) -> Response:
    """Save API key to local config only. Never log or echo the key."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    provider = data.get("provider")
    api_key = data.get("api_key")
    if not provider or not api_key:
        return JSONResponse({"error": "provider and api_key required"}, status_code=400)
    from .server import configure_key
    body = await configure_key(provider=provider, api_key=api_key)
    out = json.loads(body)
    if "error" in out:
        return JSONResponse(out, status_code=400)
    # Response contains only success message; never include the key
    return JSONResponse(out)


async def _api_run(request: Request) -> Response:
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    prompt = data.get("prompt")
    if not prompt:
        return JSONResponse({"error": "prompt required"}, status_code=400)
    from .server import run
    body = await run(
        prompt=prompt,
        system_prompt=data.get("system_prompt"),
        model_id=data.get("model_id"),
        provider=data.get("provider"),
        min_tier=data.get("min_tier", "A"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.0),
    )
    return JSONResponse(json.loads(body))


async def _api_ask(request: Request) -> Response:
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    prompt = data.get("prompt")
    if not prompt:
        return JSONResponse({"error": "prompt required"}, status_code=400)
    from .server import ask
    body = await ask(
        prompt=prompt,
        system_prompt=data.get("system_prompt"),
        count=data.get("count", 3),
        min_tier=data.get("min_tier", "A"),
        provider=data.get("provider"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.0),
    )
    return JSONResponse(json.loads(body))


async def _api_restart_server(_request: Request) -> Response:
    from .server import restart_server
    body = await restart_server()
    return JSONResponse(json.loads(body))


async def _api_server_stats(_request: Request) -> Response:
    from .server import server_stats
    body = await server_stats()
    return JSONResponse(json.loads(body))


async def _dashboard(_request: Request) -> Response:
    return HTMLResponse(_dashboard_html())


def add_web_routes(mcp: FastMCP) -> None:
    """Register dashboard and REST API routes on the FastMCP instance. Call before run(transport='sse')."""
    mcp.custom_route("/", ["GET"], name="dashboard")(_dashboard)
    mcp.custom_route("/api/list_providers", ["GET"])(_api_list_providers)
    mcp.custom_route("/api/list_models", ["GET"])(_api_list_models)
    mcp.custom_route("/api/scan", ["GET"])(_api_scan)
    mcp.custom_route("/api/get_fastest", ["GET"])(_api_get_fastest)
    mcp.custom_route("/api/provider_status", ["GET"])(_api_provider_status)
    mcp.custom_route("/api/setup_guide", ["GET"])(_api_setup_guide)
    mcp.custom_route("/api/configure_key", ["POST"])(_api_configure_key)
    mcp.custom_route("/api/run", ["POST"])(_api_run)
    mcp.custom_route("/api/ask", ["POST"])(_api_ask)
    mcp.custom_route("/api/restart_server", ["POST"])(_api_restart_server)
    mcp.custom_route("/api/server_stats", ["GET"])(_api_server_stats)
