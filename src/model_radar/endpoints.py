"""
OpenAI-compatible endpoint info for use by host agents (e.g. swap instructions).

Provides base_url (strip /chat/completions) and auth style so clients can
configure Cursor, Open Interpreter, etc. to use a model-radar provider.
"""

from __future__ import annotations

import os

from .config import load_config
from .providers import PROVIDERS, Model, get_all_models, filter_models

# Providers that do not expose a standard OpenAI chat/completions endpoint
NON_OPENAI_PROVIDERS = frozenset({"replicate"})


def get_base_url(provider_key: str, cfg: dict | None = None) -> str | None:
    """
    Return the OpenAI-compatible base URL for a provider (no /chat/completions suffix).

    Callers append /chat/completions. For Cloudflare, {account_id} must be
    replaced with the user's CLOUDFLARE_ACCOUNT_ID. Returns None for
    non-OpenAI providers (e.g. replicate).
    """
    if provider_key in NON_OPENAI_PROVIDERS:
        return None
    prov = PROVIDERS.get(provider_key)
    if not prov:
        return None
    url = prov.url
    if provider_key == "cloudflare" and cfg is not None:
        acct = (cfg.get("cloudflare_account_id") or
                os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
        url = url.replace("{account_id}", acct)
    if "/chat/completions" in url:
        base = url.split("/chat/completions")[0]
        return base.rstrip("/") or None
    return url.rstrip("/") if url else None


def get_auth_style(provider_key: str) -> dict:
    """
    Return how the client should send the API key for this provider.

    Returns dict with: type ("bearer" | "query_key" | "token_header"), env_var.
    """
    prov = PROVIDERS.get(provider_key)
    if not prov:
        return {"type": "bearer", "env_var": None}
    env_var = prov.env_vars[0] if prov.env_vars else None
    if provider_key == "googleai":
        return {"type": "query_key", "env_var": env_var}
    if provider_key == "replicate":
        return {"type": "token_header", "env_var": env_var}
    return {"type": "bearer", "env_var": env_var}


def get_openai_endpoint_for_model(
    model: Model,
    cfg: dict | None = None,
) -> dict:
    """
    Return OpenAI-compatible endpoint info for a given model.

    Keys: base_url, model_id, provider_key, provider_name, auth (type + env_var).
    base_url is None for non-OpenAI providers.
    """
    if cfg is None:
        cfg = load_config()
    base_url = get_base_url(model.provider, cfg)
    auth = get_auth_style(model.provider)
    return {
        "base_url": base_url,
        "model_id": model.model_id,
        "provider_key": model.provider,
        "provider_name": PROVIDERS[model.provider].name,
        "auth_type": auth["type"],
        "env_var": auth["env_var"],
        "openai_compatible": base_url is not None,
    }
