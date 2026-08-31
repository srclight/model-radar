"""Tests for the MCP server tool registration and basic responses."""

import json

import pytest

from model_radar.server import create_server


@pytest.fixture
def server():
    return create_server()


def test_server_created(server):
    assert server.name == "model-radar"


def test_server_has_instructions(server):
    assert "model-radar" in server.instructions
    assert "subscription CLIs" in server.instructions


@pytest.mark.asyncio
async def test_list_providers_tool():
    """list_providers should return HTTPS providers plus any subscription CLIs on PATH."""
    from model_radar.server import list_providers

    result = json.loads(await list_providers())
    assert result["total_providers"] >= 21
    assert result["total_models"] >= 130
    assert len(result["providers"]) == result["total_providers"]

    # Check each provider has required fields
    for p in result["providers"]:
        assert "provider" in p
        assert "key" in p
        assert "models" in p
        assert "kind" in p
        assert "api_key" in p
        assert p["api_key"] in ("configured", "missing", "n/a")
        if p["kind"] == "cli":
            assert p["access"] == "cli"
            assert "installed" in p
        assert p["lane"] in ("A", "B", "C", "mixed")
        assert "spend_ok" in p
        assert "funded" in p
        assert "in_default_pool" in p
        assert "key_ids" in p


@pytest.mark.asyncio
async def test_list_models_tool():
    """list_models should return filtered results."""
    from model_radar.server import list_models

    # All models
    result = json.loads(await list_models())
    assert result["count"] >= 130

    # Filter by tier
    result = json.loads(await list_models(tier="S+"))
    assert result["count"] > 0
    assert all(m["tier"] == "S+" for m in result["models"])

    # Filter by provider (count is live, not a frozen seed)
    result = json.loads(await list_models(provider="nvidia"))
    assert result["count"] > 0
    assert all(m["provider_key"] == "nvidia" for m in result["models"])

    # Filter by min_tier
    result = json.loads(await list_models(min_tier="S"))
    assert result["count"] > 0
    allowed = {"S+", "S"}
    assert all(m["tier"] in allowed for m in result["models"])


@pytest.mark.asyncio
async def test_list_models_combined_filters():
    """Combining provider + tier filters should work."""
    from model_radar.server import list_models

    result = json.loads(await list_models(provider="minimax", tier="S+"))
    assert result["count"] > 0
    for m in result["models"]:
        assert m["provider_key"] == "minimax"
        assert m["tier"] == "S+"


@pytest.mark.asyncio
async def test_configure_key_unknown_provider():
    """configure_key should reject unknown providers."""
    from model_radar.server import configure_key

    result = json.loads(await configure_key("nonexistent", "some-key"))
    assert "error" in result
    assert "nonexistent" in result["error"]
    assert "available_providers" in result


@pytest.mark.asyncio
async def test_profile_and_set_profile_roundtrip(tmp_path, monkeypatch):
    from model_radar import config as config_mod
    from model_radar.server import profile, set_profile

    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "LOCAL_CONFIG_PATH", tmp_path / "no-local.json")
    (tmp_path / "config.json").write_text('{"api_keys": {}, "providers": {}}')

    listed = json.loads(await profile())
    cerebras = next(p for p in listed["providers"] if p["key"] == "cerebras")
    assert cerebras["lane"] == "C"
    assert cerebras["spend_ok"] is False
    assert cerebras["funded"] is None

    updated = json.loads(await set_profile("cerebras", spend_ok=False, funded=True))
    assert updated["success"] is True
    assert updated["funded"] is True
    assert updated["spend_ok"] is False

    listed = json.loads(await profile())
    cerebras = next(p for p in listed["providers"] if p["key"] == "cerebras")
    assert cerebras["funded"] is True


@pytest.mark.asyncio
async def test_setup_workflow_step1():
    """setup_workflow step 1 returns Playwright check/install instructions."""
    from model_radar.server import setup_workflow

    result = json.loads(await setup_workflow(step=1))
    assert result["step"] == 1
    assert "install_commands" in result
    assert "check_command" in result
    assert "playwright" in result["check_command"].lower()


@pytest.mark.asyncio
async def test_setup_workflow_step2():
    """setup_workflow step 2 returns unconfigured providers with provider_key and github_sso."""
    from model_radar.server import setup_workflow

    result = json.loads(await setup_workflow(step=2))
    assert result["step"] == 2
    assert "unconfigured" in result
    for entry in result["unconfigured"]:
        assert "provider_key" in entry
        assert "github_sso" in entry
        assert "signup_url" in entry


@pytest.mark.asyncio
async def test_setup_workflow_step3_no_selection():
    """setup_workflow step 3 without provider_selection tells host to prompt user."""
    from model_radar.server import setup_workflow

    result = json.loads(await setup_workflow(step=3))
    assert result["step"] == 3
    assert "error" in result or "host_instructions" in result
    assert "provider_selection" in result.get("host_instructions", "") or "step 2" in result.get("host_instructions", "")


@pytest.mark.asyncio
async def test_setup_workflow_step3_with_selection():
    """setup_workflow step 3 with provider_selection returns login + where_to_save."""
    from model_radar.server import setup_workflow

    result = json.loads(await setup_workflow(step=3, provider_selection=["groq", "openrouter"]))
    assert result["step"] == 3
    assert "providers" in result
    assert len(result["providers"]) == 2
    for p in result["providers"]:
        assert "provider_key" in p
        assert "where_to_save" in p or p.get("already_configured") or p.get("error")
        if "where_to_save" in p:
            assert "config_path" in p["where_to_save"]
            assert "tool_call" in p["where_to_save"]


@pytest.mark.asyncio
async def test_setup_workflow_step4():
    """setup_workflow step 4 returns where to save keys (path, methods, security)."""
    from model_radar.server import setup_workflow

    result = json.loads(await setup_workflow(step=4))
    assert result["step"] == 4
    assert "config_path" in result
    assert ".model-radar" in result["config_path"]
    assert "methods" in result
    assert "security" in result


@pytest.mark.asyncio
async def test_setup_workflow_step5():
    """setup_workflow step 5 returns host swap instructions (search_locations, openai_endpoint)."""
    from model_radar.server import setup_workflow

    result = json.loads(await setup_workflow(step=5))
    assert result["step"] == 5
    assert "search_locations" in result
    assert "model_radar_key_locations" in result
    assert any(loc["app"] == "Cursor" for loc in result["search_locations"])
    assert any(loc["app"] == "Open Interpreter" for loc in result["search_locations"])
    assert "openai_endpoint" in result
    if result.get("openai_endpoint"):
        assert "base_url" in result["openai_endpoint"]
        assert "model_id" in result["openai_endpoint"]


@pytest.mark.asyncio
async def test_host_swap_instructions():
    """host_swap_instructions returns key locations, search_locations, and optional endpoint."""
    from model_radar.server import host_swap_instructions

    result = json.loads(await host_swap_instructions())
    assert "model_radar_key_locations" in result
    assert "search_locations" in result
    assert "host_instructions" in result
    assert "primary_config" in result["model_radar_key_locations"]
    # Without model_id we get a recommended model and endpoint
    assert "openai_endpoint" in result
    assert result.get("chosen_model") or result.get("openai_endpoint") is None or "base_url" in result["openai_endpoint"]


@pytest.mark.asyncio
async def test_host_swap_instructions_with_model_id():
    """host_swap_instructions with model_id returns that model's endpoint.

    Pick a model that is ACTUALLY in the current catalog rather than hardcoding an
    id — providers rename and delist models, and a pinned id (this test previously
    used 'llama-3.3-70b-versatile', straight from the docstring) rots into a
    chosen_model=None crash the moment the catalog moves. Testing a live id keeps
    the assertion about behaviour, not about one provider's changing lineup.
    """
    from model_radar.db import get_models_for_discovery
    from model_radar.server import host_swap_instructions

    groq_models = [m for m in get_models_for_discovery() if m.provider == "groq"]
    if not groq_models:
        pytest.skip("no groq models in the current catalog to resolve an endpoint for")
    model_id = groq_models[0].model_id

    result = json.loads(await host_swap_instructions(model_id=model_id, provider="groq"))
    assert result["chosen_model"]["model_id"] == model_id
    assert result["openai_endpoint"]["model_id"] == model_id
    assert "base_url" in result["openai_endpoint"]
    assert "api.groq.com" in result["openai_endpoint"]["base_url"]


@pytest.mark.asyncio
async def test_restart_server_disabled_when_env_false():
    """restart_server returns ok: false when MODEL_RADAR_ALLOW_RESTART=0."""
    import os
    from model_radar.server import restart_server

    orig = os.environ.get("MODEL_RADAR_ALLOW_RESTART")
    os.environ["MODEL_RADAR_ALLOW_RESTART"] = "0"
    try:
        result = json.loads(await restart_server())
        assert result.get("ok") is False
        assert "MODEL_RADAR_ALLOW_RESTART" in result.get("message", "")
    finally:
        if orig is None:
            os.environ.pop("MODEL_RADAR_ALLOW_RESTART", None)
        else:
            os.environ["MODEL_RADAR_ALLOW_RESTART"] = orig


@pytest.mark.asyncio
async def test_restart_server_enabled_schedules_exit():
    """When MODEL_RADAR_ALLOW_RESTART=1, restart_server returns ok: True and schedules exit."""
    import os
    from unittest.mock import patch, MagicMock

    from model_radar.server import restart_server

    orig = os.environ.get("MODEL_RADAR_ALLOW_RESTART")
    os.environ["MODEL_RADAR_ALLOW_RESTART"] = "1"
    call_later_calls = []

    def capture_call_later(delay, callback):
        call_later_calls.append((delay, callback))
        return MagicMock()

    try:
        with patch("os._exit") as mock_exit:  # prevent real exit
            loop = MagicMock()
            loop.call_later.side_effect = capture_call_later
            with patch("asyncio.get_running_loop", return_value=loop):
                result = json.loads(await restart_server())
            assert result.get("ok") is True
            assert "exit" in result.get("message", "").lower()
            assert len(call_later_calls) == 1
            delay, exit_callback = call_later_calls[0]
            assert delay == 0
            exit_callback()
            mock_exit.assert_called_once_with(0)
    finally:
        if orig is None:
            os.environ.pop("MODEL_RADAR_ALLOW_RESTART", None)
        else:
            os.environ["MODEL_RADAR_ALLOW_RESTART"] = orig


@pytest.mark.asyncio
async def test_server_stats():
    """server_stats returns started_at and uptime_seconds."""
    from model_radar.server import server_stats

    result = json.loads(await server_stats())
    assert "started_at" in result
    assert "started_at_epoch" in result
    assert "uptime_seconds" in result
    assert "uptime_human" in result
    assert result["uptime_seconds"] >= 0
    assert "s" in result["uptime_human"]
    assert "version" in result
    assert result.get("listen") == "127.0.0.1:8743"


@pytest.mark.asyncio
async def test_startup_refresh_runs_and_logs(monkeypatch):
    """create_server() records start time. Catalog refresh is started from the serve loop."""
    import asyncio
    from model_radar import server as server_module

    # Reset the singleton so the function takes the startup branch
    server_module._server_start_time = None

    async def fake_refresh():
        return {"xai": 3, "googleai": 6}

    monkeypatch.setattr("model_radar.provider_sync.refresh_models_from_live",
                        fake_refresh)

    mcp = server_module.create_server()
    # Give the scheduled task a chance to run
    await asyncio.sleep(0.05)
    assert server_module._server_start_time is not None
