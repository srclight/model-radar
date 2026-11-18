"""Where the config file lives: default path, MODEL_RADAR_CONFIG, and failure modes."""

import json
import os
import stat

import pytest

from model_radar import config as config_mod
from model_radar.config import (
    CONFIG_ENV_VAR,
    ConfigError,
    _empty_config,
    config_path,
    config_status,
    load_config,
    save_config,
)

KEYS = {"api_keys": {"groq": "gsk_test"}, "providers": {}}


def test_default_path_when_env_unset():
    assert config_path() == config_mod.CONFIG_PATH
    status = config_status()
    assert status["source"] == "default"
    # A fresh install has no file yet. That is not an error.
    assert status == {**status, "exists": False, "ok": True, "error": None}


def test_env_var_names_the_only_file(tmp_path, monkeypatch):
    default = config_mod.CONFIG_PATH
    default.write_text(json.dumps({"api_keys": {"groq": "from-home"}, "providers": {}}))
    elsewhere = tmp_path / "vault" / "radar.json"
    elsewhere.parent.mkdir()
    elsewhere.write_text(json.dumps(KEYS))
    monkeypatch.setenv(CONFIG_ENV_VAR, str(elsewhere))

    assert config_path() == elsewhere
    assert load_config()["api_keys"]["groq"] == "gsk_test"
    assert config_status()["source"] == CONFIG_ENV_VAR

    cfg = load_config()
    cfg["api_keys"]["nvidia"] = "nvapi-test"
    save_config(cfg)
    assert json.loads(elsewhere.read_text())["api_keys"]["nvidia"] == "nvapi-test"
    assert "nvidia" not in json.loads(default.read_text())["api_keys"]


def test_env_var_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(CONFIG_ENV_VAR, "~/keys/radar.json")
    assert config_path() == tmp_path / "keys" / "radar.json"


def test_missing_explicit_file_does_not_fall_back(tmp_path, monkeypatch):
    """An unmounted volume must read as 'no keys', never as the home-dir keys."""
    config_mod.CONFIG_PATH.write_text(json.dumps({"api_keys": {"groq": "from-home"}, "providers": {}}))
    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "unmounted" / "radar.json"))

    assert load_config() == _empty_config()
    status = config_status()
    assert status["ok"] is False and status["exists"] is False
    assert "does not exist" in status["error"]


def test_save_never_creates_directories_for_an_explicit_path(tmp_path, monkeypatch):
    """Otherwise keys land on the disk underneath an unmounted mount point."""
    target = tmp_path / "unmounted" / "radar.json"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(target))
    with pytest.raises(ConfigError, match="does not exist"):
        save_config(dict(KEYS))
    assert not target.parent.exists()


def test_save_creates_the_default_directory(tmp_path, monkeypatch):
    target = tmp_path / "fresh" / ".model-radar" / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", target)
    save_config(dict(KEYS))
    assert json.loads(target.read_text()) == KEYS


def test_corrupt_file_is_reported_and_never_overwritten(tmp_path, monkeypatch):
    target = tmp_path / "radar.json"
    target.write_text('{"api_keys": {"groq": "gsk_real"')  # truncated
    monkeypatch.setenv(CONFIG_ENV_VAR, str(target))

    assert load_config() == _empty_config()
    status = config_status()
    assert status["ok"] is False and status["exists"] is True
    assert "not valid JSON" in status["error"]
    with pytest.raises(ConfigError, match="refusing to overwrite"):
        save_config(dict(KEYS))
    assert "gsk_real" in target.read_text()


def test_working_directory_config_is_ignored(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(json.dumps({"api_keys": {"groq": "planted"}, "providers": {}}))
    monkeypatch.chdir(tmp_path)
    assert load_config() == _empty_config()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_saved_file_is_owner_only(tmp_path, monkeypatch):
    target = tmp_path / "radar.json"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(target))
    old = os.umask(0o022)
    try:
        save_config(dict(KEYS))
    finally:
        os.umask(old)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_status_never_contains_key_material(tmp_path, monkeypatch):
    target = tmp_path / "radar.json"
    target.write_text(json.dumps(KEYS))
    monkeypatch.setenv(CONFIG_ENV_VAR, str(target))
    assert "gsk_test" not in json.dumps(config_status())


async def test_list_providers_reports_config_problem(tmp_path, monkeypatch):
    from model_radar.server import list_providers

    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "unmounted" / "radar.json"))
    out = json.loads(await list_providers())
    assert out["config"]["ok"] is False
    assert "warning" in out


async def test_configure_key_reports_a_failed_save(tmp_path, monkeypatch):
    from model_radar.server import configure_key

    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "unmounted" / "radar.json"))
    out = json.loads(await configure_key(provider="groq", api_key="gsk_test"))
    assert out["success"] is False
    assert "does not exist" in out["error"]
    assert "gsk_test" not in json.dumps(out)
