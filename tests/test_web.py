"""Tests for the web dashboard and REST API (--web with SSE)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from model_radar.server import create_server
from model_radar.web import add_web_routes, _dashboard_html


def test_dashboard_html_contains_title_and_sections():
    html = _dashboard_html()
    assert "Model Radar" in html
    assert "Status" in html
    assert "Config" in html
    assert "Discovery" in html
    assert "Execution" in html
    assert "/api/list_providers" in html
    assert "/api/get_fastest" in html
    assert "/api/scan" in html
    assert "/api/run" in html
    assert "/api/restart_server" in html


@pytest.mark.asyncio
async def test_web_routes_registered_and_dashboard_served():
    """With add_web_routes, the Starlette app serves dashboard at / and API at /api/*."""
    server = create_server()
    add_web_routes(server)
    app = server.sse_app()
    from starlette.testclient import TestClient
    client = TestClient(app)
    # Dashboard
    r = client.get("/")
    assert r.status_code == 200
    assert "Model Radar" in r.text
    assert "text/html" in r.headers.get("content-type", "")
    # API list_providers
    r = client.get("/api/list_providers")
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert "total" in data
    assert data["total"] >= 21
    assert data["total"] == len(data["providers"])


@pytest.mark.asyncio
async def test_api_configure_key_validation():
    """POST /api/configure_key requires provider and api_key."""
    server = create_server()
    add_web_routes(server)
    app = server.sse_app()
    from starlette.testclient import TestClient
    client = TestClient(app)
    r = client.post("/api/configure_key", json={})
    assert r.status_code == 400
    assert "error" in r.json()
    r = client.post("/api/configure_key", json={"provider": "groq"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_api_server_stats():
    """GET /api/server_stats returns started_at and uptime."""
    server = create_server()
    add_web_routes(server)
    app = server.sse_app()
    from starlette.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/server_stats")
    assert r.status_code == 200
    data = r.json()
    assert "started_at" in data
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_api_refresh_returns_counts():
    """POST /api/refresh returns refreshed count and by_provider dict."""
    from model_radar.web import _api_refresh
    from unittest.mock import AsyncMock, patch

    fake_counts = {"xai": 3, "googleai": 6}

    with patch("model_radar.provider_sync.refresh_models_from_live",
               return_value=fake_counts):
        request = AsyncMock()
        response = await _api_refresh(request)
        body = json.loads(response.body.decode())
        assert body["refreshed"] == 9
        assert body["by_provider"] == fake_counts


@pytest.mark.asyncio
async def test_api_list_providers_includes_cli_kind():
    """GET /api/list_providers includes 'kind' field for CLI providers."""
    from model_radar.web import _api_list_providers

    with patch("model_radar.config.load_config",
               return_value={"api_keys": {}, "providers": {"grok": {"enabled": True}}}):
        request = AsyncMock()
        response = await _api_list_providers(request)
        body = json.loads(response.body.decode())
        grok = next(p for p in body["providers"] if p["key"] == "grok")
        assert "kind" in grok
        assert "installed" in grok
