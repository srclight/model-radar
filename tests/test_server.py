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
