"""Shared fixtures.

Tests never read or write a real config file: every test starts with
MODEL_RADAR_CONFIG unset and the default path pointed at an empty temp dir.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path_factory, monkeypatch):
    from model_radar import config as config_mod

    home = tmp_path_factory.mktemp("home") / ".model-radar"
    home.mkdir()
    monkeypatch.delenv(config_mod.CONFIG_ENV_VAR, raising=False)
    monkeypatch.setattr(config_mod, "CONFIG_PATH", home / "config.json")
