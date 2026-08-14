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


_NO_AUTH_PROVIDERS = frozenset({"ollama"})
DEFAULT_KEY_ID = "default"


def _named_store(raw) -> dict | None:
    """Normalize a config api_keys entry to {active, keys} or None."""
    if isinstance(raw, str) and raw.strip():
        return {"active": DEFAULT_KEY_ID, "keys": {DEFAULT_KEY_ID: raw}}
    if isinstance(raw, dict) and isinstance(raw.get("keys"), dict):
        keys = {str(k): v for k, v in raw["keys"].items() if v}
        if not keys:
            return None
        active = raw.get("active")
        if active not in keys:
            active = next(iter(keys))
        return {"active": active, "keys": keys}
    return None


def get_key_meta(cfg: dict, provider_key: str) -> dict:
    """Named key ids only — never returns secrets."""
    store = _named_store((cfg.get("api_keys") or {}).get(provider_key))
    if not store:
        return {"active": None, "ids": []}
    return {"active": store["active"], "ids": list(store["keys"])}


def get_api_key(cfg: dict, provider_key: str, key_id: str | None = None) -> str | None:
    """Get API key: env var > config file > None. Local providers return a dummy key."""
    if provider_key in _NO_AUTH_PROVIDERS:
        return "local"
    prov = PROVIDERS.get(provider_key)
    if prov:
        for var in prov.env_vars:
            val = os.environ.get(var)
            if val:
                return val
    store = _named_store((cfg.get("api_keys") or {}).get(provider_key))
    if not store:
        return None
    if key_id:
        val = store["keys"].get(key_id)
        return val or None
    return store["keys"].get(store["active"]) or None


def set_api_key(
    cfg: dict,
    provider_key: str,
    api_key: str,
    *,
    key_id: str = DEFAULT_KEY_ID,
    make_active: bool | None = None,
) -> dict:
    """Add or update a named key. Does not delete other ids. First key becomes active."""
    keys_root = cfg.setdefault("api_keys", {})
    raw = keys_root.get(provider_key)
    store = _named_store(raw) or {"active": key_id, "keys": {}}
    store["keys"][key_id] = api_key
    if make_active is True or store.get("active") not in store["keys"]:
        store["active"] = key_id
    keys_root[provider_key] = store
    return {"active": store["active"], "ids": list(store["keys"])}


def in_default_pool(cfg: dict, provider_key: str) -> bool:
    """True if default recommend/get_fastest may pick this host unprompted."""
    from .cli_provider import CLI_SPEC_BY_KEY
    from .lanes import provider_lane

    if not is_provider_enabled(cfg, provider_key):
        return False
    if provider_key in CLI_SPEC_BY_KEY:
        return False
    if provider_key not in _NO_AUTH_PROVIDERS and not get_api_key(cfg, provider_key):
        return False
    lane = provider_lane(provider_key)
    if lane in ("A", "mixed"):
        return True
    flags = get_provider_flags(cfg, provider_key)
    return flags["funded"] is True and flags["spend_ok"]


def is_provider_enabled(cfg: dict, provider_key: str) -> bool:
    """Check if provider is enabled (default: True)."""
    return get_provider_flags(cfg, provider_key)["enabled"]


def get_provider_flags(cfg: dict, provider_key: str) -> dict:
    """Local profile bits: enabled, spend_ok, funded (True/False/None)."""
    raw = (cfg.get("providers") or {}).get(provider_key) or {}
    funded = raw.get("funded", None)
    if funded is not None:
        funded = bool(funded)
    login = raw.get("login")
    if login is not None:
        login = str(login).strip() or None
    return {
        "enabled": raw.get("enabled", True) is not False,
        "spend_ok": bool(raw.get("spend_ok", False)),
        "funded": funded,
        "login": login,
    }


def set_provider_flags(
    cfg: dict,
    provider_key: str,
    *,
    spend_ok: bool | None = None,
    funded: bool | None = None,
    enabled: bool | None = None,
    login: str | None = None,
) -> dict:
    """Mutate providers.<key> in place. Omitted kwargs are left unchanged."""
    providers = cfg.setdefault("providers", {})
    row = dict(providers.get(provider_key) or {})
    if spend_ok is not None:
        row["spend_ok"] = bool(spend_ok)
    if funded is not None:
        row["funded"] = bool(funded)
    if enabled is not None:
        row["enabled"] = bool(enabled)
    if login is not None:
        row["login"] = str(login).strip()
    providers[provider_key] = row
    return row


def get_configured_providers(cfg: dict) -> list[str]:
    """Return provider keys that are usable right now.

    HTTPS: an API key is present. CLI (subscription): the binary was
    registered because it is on PATH — no key required.
    """
    out = []
    for k, prov in PROVIDERS.items():
        if not is_provider_enabled(cfg, k):
            continue
        if getattr(prov, "kind", "https") == "cli":
            out.append(k)
        elif get_api_key(cfg, k):
            out.append(k)
    return out
