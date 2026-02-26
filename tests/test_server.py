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
    assert "17 providers" in server.instructions


@pytest.mark.asyncio
async def test_list_providers_tool():
    """list_providers should return all 17 providers."""
    from model_radar.server import list_providers

    result = json.loads(await list_providers())
    assert result["total_providers"] == 17
    assert result["total_models"] >= 130
    assert len(result["providers"]) == 17

    # Check each provider has required fields
    for p in result["providers"]:
        assert "provider" in p
        assert "key" in p
        assert "models" in p
        assert "api_key" in p
        assert p["api_key"] in ("configured", "missing")


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

    # Filter by provider
    result = json.loads(await list_models(provider="nvidia"))
    assert result["count"] == 41
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

    result = json.loads(await list_models(provider="nvidia", tier="S+"))
    assert result["count"] > 0
    for m in result["models"]:
        assert m["provider_key"] == "nvidia"
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
    """host_swap_instructions with model_id returns that model's endpoint."""
    from model_radar.server import host_swap_instructions

    result = json.loads(await host_swap_instructions(model_id="llama-3.3-70b-versatile", provider="groq"))
    assert result["chosen_model"]["model_id"] == "llama-3.3-70b-versatile"
    assert result["openai_endpoint"]["model_id"] == "llama-3.3-70b-versatile"
    assert "base_url" in result["openai_endpoint"]
    assert "api.groq.com" in result["openai_endpoint"]["base_url"]


@pytest.mark.asyncio
async def test_restart_server_disabled_without_env():
    """restart_server returns ok: false when MODEL_RADAR_ALLOW_RESTART is not set."""
    import os
    from model_radar.server import restart_server

    orig = os.environ.pop("MODEL_RADAR_ALLOW_RESTART", None)
    try:
        result = json.loads(await restart_server())
        assert result.get("ok") is False
        assert "MODEL_RADAR_ALLOW_RESTART" in result.get("message", "")
    finally:
        if orig is not None:
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
        with patch("os._exit"):  # prevent real exit
            loop = MagicMock()
            loop.call_later.side_effect = capture_call_later
            with patch("asyncio.get_running_loop", return_value=loop):
                result = json.loads(await restart_server())
        assert result.get("ok") is True
        assert "exit" in result.get("message", "").lower()
        assert len(call_later_calls) == 1
        delay, exit_callback = call_later_calls[0]
        assert delay == 0
        # Callback should be the _exit that calls os._exit(0)
        exit_callback()
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
