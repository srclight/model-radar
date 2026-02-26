"""
Configuration management for model-radar.

Config file: ~/.model-radar/config.json
Permissions: 0o600 (contains API keys)

Config structure:
{
    "api_keys": { "nvidia": "nvapi-xxx", "groq": "gsk_xxx", ... },
    "providers": { "nvidia": { "enabled": true }, ... },
    "cloudflare_account_id": null
}
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .providers import PROVIDERS

CONFIG_DIR = Path.home() / ".model-radar"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Local config in working directory takes precedence over home dir
LOCAL_CONFIG_PATH = Path("config.json")


def _empty_config() -> dict:
    return {
        "api_keys": {},
        "providers": {},
        "cloudflare_account_id": None,
    }


def _try_load(path: Path) -> dict | None:
    """Try to load a config file, return None if missing/corrupt."""
    if path.exists():
        try:
            raw = path.read_text().strip()
            cfg = json.loads(raw)
            if not isinstance(cfg.get("api_keys"), dict):
                cfg["api_keys"] = {}
            if not isinstance(cfg.get("providers"), dict):
                cfg["providers"] = {}
            return cfg
        except (json.JSONDecodeError, OSError):
            return None
    return None


def load_config() -> dict:
    """Load config: ./config.json > ~/.model-radar/config.json > empty."""
    # Local config takes precedence (project-level keys)
    cfg = _try_load(LOCAL_CONFIG_PATH)
    if cfg is not None:
        return cfg
    cfg = _try_load(CONFIG_PATH)
    if cfg is not None:
        return cfg
    return _empty_config()


def save_config(cfg: dict) -> None:
    """Write config to disk with restricted permissions."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def get_api_key(cfg: dict, provider_key: str) -> str | None:
    """Get API key: env var > config file > None."""
    prov = PROVIDERS.get(provider_key)
    if prov:
        for var in prov.env_vars:
            val = os.environ.get(var)
            if val:
                return val
    key = cfg.get("api_keys", {}).get(provider_key)
    return key if key else None


def is_provider_enabled(cfg: dict, provider_key: str) -> bool:
    """Check if provider is enabled (default: True)."""
    prov_cfg = cfg.get("providers", {}).get(provider_key)
    if not prov_cfg:
        return True
    return prov_cfg.get("enabled", True) is not False


def get_configured_providers(cfg: dict) -> list[str]:
    """Return provider keys that have an API key configured."""
    return [k for k in PROVIDERS if get_api_key(cfg, k) and is_provider_enabled(cfg, k)]
