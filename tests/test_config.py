"""Tests for config management."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from model_radar.config import (
    _empty_config,
    get_api_key,
    get_configured_providers,
    get_key_meta,
    get_provider_flags,
    in_default_pool,
    is_provider_enabled,
    load_config,
    save_config,
    set_api_key,
    set_provider_flags,
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


def test_get_configured_providers_includes_subscription_cli():
    """A subscription CLI on PATH is configured even with no API key."""
    from unittest.mock import patch

    from model_radar.cli_provider import register_cli_providers
    from model_radar.providers import PROVIDERS

    cli_keys = ("grok", "gemini", "claude", "codex")
    snapshot = {k: PROVIDERS[k] for k in cli_keys if k in PROVIDERS}
    try:
        for k in cli_keys:
            PROVIDERS.pop(k, None)
        with patch("shutil.which", lambda cmd: "/usr/bin/claude" if cmd == "claude" else None):
            register_cli_providers()
            cfg = {"api_keys": {}, "providers": {}}
            configured = get_configured_providers(cfg)
            assert "claude" in configured
            assert "nvidia" not in configured
    finally:
        for k in cli_keys:
            PROVIDERS.pop(k, None)
        for k, v in snapshot.items():
            PROVIDERS[k] = v
        register_cli_providers()


def test_provider_flags_defaults():
    cfg = {"providers": {}}
    flags = get_provider_flags(cfg, "cerebras")
    assert flags["enabled"] is True
    assert flags["spend_ok"] is False
    assert flags["funded"] is None
    assert flags["login"] is None


def test_set_provider_flags_preserves_enabled():
    cfg = {"providers": {"cerebras": {"enabled": True}}}
    set_provider_flags(cfg, "cerebras", spend_ok=False, funded=True, login="github:example")
    assert cfg["providers"]["cerebras"]["enabled"] is True
    assert cfg["providers"]["cerebras"]["spend_ok"] is False
    assert cfg["providers"]["cerebras"]["funded"] is True
    flags = get_provider_flags(cfg, "cerebras")
    assert flags == {
        "enabled": True, "spend_ok": False, "funded": True,
        "login": "github:example",
    }


def test_legacy_string_key_still_reads():
    cfg = {"api_keys": {"groq": "gsk-legacy"}, "providers": {}}
    assert get_api_key(cfg, "groq") == "gsk-legacy"
    meta = get_key_meta(cfg, "groq")
    assert meta["ids"] == ["default"]
    assert meta["active"] == "default"


def test_named_keys_active_and_add_does_not_clobber():
    cfg = {"api_keys": {}, "providers": {}}
    set_api_key(cfg, "minimax", "sk-cp-plan", key_id="coding-plan")
    set_api_key(cfg, "minimax", "sk-api-paygo", key_id="paygo")
    assert get_api_key(cfg, "minimax") == "sk-cp-plan"
    assert get_api_key(cfg, "minimax", key_id="paygo") == "sk-api-paygo"
    meta = get_key_meta(cfg, "minimax")
    assert set(meta["ids"]) == {"coding-plan", "paygo"}
    assert meta["active"] == "coding-plan"
    set_api_key(cfg, "minimax", "sk-api-paygo-2", key_id="paygo", make_active=True)
    assert get_api_key(cfg, "minimax") == "sk-api-paygo-2"
    assert get_api_key(cfg, "minimax", key_id="coding-plan") == "sk-cp-plan"


def test_in_default_pool_lane_a_yes_lane_c_needs_spend_ok():
    cfg = {
        "api_keys": {"groq": "gsk-x", "cerebras": "csk-x", "together": "tg-x"},
        "providers": {
            "cerebras": {"funded": True, "spend_ok": False},
            "together": {"funded": False, "spend_ok": False},
        },
    }
    assert in_default_pool(cfg, "groq") is True
    assert in_default_pool(cfg, "cerebras") is False
    cfg["providers"]["cerebras"]["spend_ok"] = True
    assert in_default_pool(cfg, "cerebras") is True
    assert in_default_pool(cfg, "together") is False
