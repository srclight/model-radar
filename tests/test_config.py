"""Tests for config management."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from model_radar.config import (
    _empty_config,
    get_api_key,
    get_configured_providers,
    is_provider_enabled,
    load_config,
    save_config,
)


def test_empty_config_shape():
    cfg = _empty_config()
    assert isinstance(cfg["api_keys"], dict)
    assert isinstance(cfg["providers"], dict)
    assert cfg["cloudflare_account_id"] is None


def _no_local(tmp_path):
    """Patch both local and home config paths to isolate tests."""
    return (
        patch("model_radar.config.LOCAL_CONFIG_PATH", tmp_path / "no-local.json"),
        patch("model_radar.config.CONFIG_DIR", tmp_path),
    )


def test_save_and_load(tmp_path):
    config_path = tmp_path / "config.json"
    local_patch, dir_patch = _no_local(tmp_path)
    with patch("model_radar.config.CONFIG_PATH", config_path), local_patch, dir_patch:
        cfg = _empty_config()
        cfg["api_keys"]["nvidia"] = "test-key-123"
        save_config(cfg)

        loaded = load_config()
        assert loaded["api_keys"]["nvidia"] == "test-key-123"


def test_load_missing_file(tmp_path):
    config_path = tmp_path / "nonexistent.json"
    local_patch, dir_patch = _no_local(tmp_path)
    with patch("model_radar.config.CONFIG_PATH", config_path), local_patch, dir_patch:
        cfg = load_config()
        assert cfg == _empty_config()


def test_load_corrupt_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("not valid json{{{")
    local_patch, dir_patch = _no_local(tmp_path)
    with patch("model_radar.config.CONFIG_PATH", config_path), local_patch, dir_patch:
        cfg = load_config()
        assert cfg == _empty_config()


def test_get_api_key_from_config():
    cfg = {"api_keys": {"nvidia": "nvapi-test"}, "providers": {}}
    assert get_api_key(cfg, "nvidia") == "nvapi-test"
    assert get_api_key(cfg, "groq") is None


def test_get_api_key_env_override():
    cfg = {"api_keys": {"nvidia": "config-key"}, "providers": {}}
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "env-key"}):
        assert get_api_key(cfg, "nvidia") == "env-key"


def test_is_provider_enabled_default():
    cfg = {"api_keys": {}, "providers": {}}
    assert is_provider_enabled(cfg, "nvidia") is True


def test_is_provider_disabled():
    cfg = {"api_keys": {}, "providers": {"nvidia": {"enabled": False}}}
    assert is_provider_enabled(cfg, "nvidia") is False


def test_get_configured_providers():
    cfg = {
        "api_keys": {"nvidia": "key1", "groq": "key2"},
        "providers": {"groq": {"enabled": False}},
    }
    configured = get_configured_providers(cfg)
    assert "nvidia" in configured
    assert "groq" not in configured  # disabled
