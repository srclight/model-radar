"""Tests for the setup guide module."""

from unittest.mock import patch

import pytest

from model_radar.guides import get_setup_guide


@pytest.fixture(autouse=True)
def _mock_config():
    """Provide a config with only nvidia configured."""
    cfg = {"api_keys": {"nvidia": "nvapi-test"}, "providers": {}}
    with patch("model_radar.guides.load_config", return_value=cfg), \
         patch("model_radar.guides.get_api_key", side_effect=lambda c, k: c["api_keys"].get(k)):
        yield


def test_guide_all_unconfigured():
    """Should return prioritized list of unconfigured providers."""
    result = get_setup_guide()
    assert "configured_providers" in result
    assert "nvidia" in result["configured_providers"]
    assert result["unconfigured_count"] > 0
    # Should be sorted by priority
    priorities = [u["priority"].split(" ")[0] for u in result["unconfigured"]]
    assert priorities[0] in ("HIGH", "MEDIUM")


def test_guide_specific_provider():
    """Should return detailed guide for a specific provider."""
    result = get_setup_guide("groq")
    assert result["provider"] == "groq"
    assert "signup_url" in result
    assert "steps" in result
    assert result["already_configured"] is False
    assert "configure_command" in result


def test_guide_configured_provider():
    """Should indicate provider is already configured."""
    result = get_setup_guide("nvidia")
    assert result["already_configured"] is True


def test_guide_unknown_provider():
    """Should return error for unknown provider."""
    result = get_setup_guide("nonexistent")
    assert "error" in result


def test_guide_has_setup_instructions():
    """All guides should have required fields."""
    result = get_setup_guide()
    for entry in result["unconfigured"]:
        assert "provider" in entry
        assert "name" in entry
        assert "signup_url" in entry
        assert "priority" in entry


def test_guide_includes_agent_instructions():
    """Should include instructions written for agents."""
    result = get_setup_guide()
    assert "setup_instructions" in result
    assert "configure_key" in result["setup_instructions"]
