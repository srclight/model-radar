"""
Fetch live model lists from provider APIs.

Supports:
- OpenRouter: GET https://openrouter.ai/api/v1/models
- NVIDIA: GET https://integrate.api.nvidia.com/v1/models
- Groq: GET https://api.groq.com/openai/v1/models
- Cerebras: GET https://api.cerebras.ai/v1/models
- SambaNova: GET https://api.sambanova.ai/v1/models
- SiliconFlow: GET https://api.siliconflow.com/v1/models
- Hugging Face: GET https://router.huggingface.co/v1/models
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import get_api_key, load_config
from .providers import is_ollama_embedding as _is_ollama_embedding

# Catalog GETs are free; refresh at most this often unless force=True.
CATALOG_TTL_SECONDS = 3600

HTTPS_CATALOG_KEYS = (
    "openrouter", "nvidia", "groq", "cerebras", "sambanova",
    "siliconflow", "huggingface", "xai", "googleai", "ollama",
    "minimax", "deepinfra", "fireworks", "codestral", "hyperbolic",
    "scaleway", "together", "inferencenet", "sealion",
)

_refresh_lock: asyncio.Lock | None = None


def _refresh_gate() -> asyncio.Lock:
    global _refresh_lock
    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()
    return _refresh_lock


@dataclass
class ProviderModel:
    """Model information from provider API."""
    model_id: str
    label: str | None = None
    provider: str = ""
    created: int | None = None
    context_length: int | None = None
    extra: dict | None = None


async def fetch_openrouter_models(api_key: str | None = None) -> list[ProviderModel]:
    """
    Fetch available models from OpenRouter API.
    
    Args:
        api_key: OpenRouter API key (optional, some endpoints work without it)
    
    Returns:
        List of ProviderModel instances
    """
    if not api_key:
        # OpenRouter allows listing without auth, but rate-limited
        return []
    
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "model-radar/0.5 (github.com/srclight/model-radar)",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                context_length = item.get("context_length")
                
                # Get display name from pricing or context
                pricing = item.get("pricing", {})
                label = pricing.get("prompt") if isinstance(pricing, dict) else None
                
                models.append(ProviderModel(
                    model_id=model_id,
                    label=label or model_id,
                    provider="openrouter",
                    created=item.get("created"),
                    context_length=context_length,
                    extra=item,
                ))
            
            return models
        except Exception as e:
            # Return empty list on error
            return []


async def fetch_nvidia_models(api_key: str | None = None) -> list[ProviderModel]:
    """
    Fetch available models from NVIDIA NIM API.
    
    Args:
        api_key: NVIDIA API key
    
    Returns:
        List of ProviderModel instances
    """
    if not api_key:
        return []
    
    url = "https://integrate.api.nvidia.com/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "model-radar/0.5 (github.com/srclight/model-radar)",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                
                models.append(ProviderModel(
                    model_id=model_id,
                    label=model_id,  # NVIDIA doesn't provide display names
                    provider="nvidia",
                    created=item.get("created"),
                    context_length=item.get("max_length"),
                    extra=item,
                ))
            
            return models
        except Exception as e:
            return []


async def fetch_groq_models(api_key: str | None = None) -> list[ProviderModel]:
    """
    Fetch available models from Groq API.
    
    Args:
        api_key: Groq API key
    
    Returns:
        List of ProviderModel instances
    """
    if not api_key:
        return []
    
    url = "https://api.groq.com/openai/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "model-radar/0.5 (github.com/srclight/model-radar)",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                owned_by = item.get("owned_by", "")
                
                models.append(ProviderModel(
                    model_id=model_id,
                    label=model_id,
                    provider="groq",
                    created=item.get("created"),
                    extra=item,
                ))
            
            return models
        except Exception as e:
            return []


async def _fetch_openai_compatible_models(
    url: str,
    api_key: str | None,
    provider_key: str,
) -> list[ProviderModel]:
    """Generic fetcher for OpenAI-compatible /v1/models endpoints."""
    if not api_key:
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "model-radar/0.5 (github.com/srclight/model-radar)",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()

            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                models.append(ProviderModel(
                    model_id=model_id,
                    label=model_id,
                    provider=provider_key,
                    created=item.get("created"),
                    context_length=item.get("max_length") or item.get("context_length"),
                    extra=item,
                ))
            return models
        except Exception:
            return []


async def fetch_cerebras_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from Cerebras API."""
    return await _fetch_openai_compatible_models(
        "https://api.cerebras.ai/v1/models", api_key, "cerebras",
    )


async def fetch_sambanova_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from SambaNova API."""
    return await _fetch_openai_compatible_models(
        "https://api.sambanova.ai/v1/models", api_key, "sambanova",
    )


async def fetch_siliconflow_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from SiliconFlow API."""
    return await _fetch_openai_compatible_models(
        "https://api.siliconflow.com/v1/models", api_key, "siliconflow",
    )


async def fetch_huggingface_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from Hugging Face Router API."""
    if not api_key:
        return []

    url = "https://router.huggingface.co/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "model-radar/0.5 (github.com/srclight/model-radar)",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()

            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                # Only include text-output models
                arch = item.get("architecture", {})
                if "text" not in arch.get("output_modalities", []):
                    continue
                # Get max context from providers
                providers = item.get("providers", [])
                ctx = max(
                    (p.get("context_length") or 0 for p in providers),
                    default=0,
                ) or None
                models.append(ProviderModel(
                    model_id=model_id,
                    label=model_id,
                    provider="huggingface",
                    created=item.get("created"),
                    context_length=ctx,
                    extra=item,
                ))
            return models
        except Exception:
            return []


async def fetch_xai_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from xAI (Grok) API.

    Args:
        api_key: xAI API key (required for listing)

    Returns:
        List of ProviderModel instances
    """
    if not api_key:
        return []

    url = "https://api.x.ai/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "model-radar/0.8 (github.com/srclight/model-radar)",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                models.append(ProviderModel(
                    model_id=model_id,
                    label=item.get("name") or model_id,
                    provider="xai",
                    created=item.get("created"),
                    context_length=None,
                    extra=item,
                ))
            return models
        except Exception:
            return []


async def fetch_googleai_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from Google AI Studio (Gemini).

    Args:
        api_key: Google AI API key (required for listing)

    Returns:
        List of ProviderModel instances
    """
    if not api_key:
        return []

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    headers = {"User-Agent": "model-radar/0.8 (github.com/srclight/model-radar)"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            models = []
            for item in data.get("models", []):
                model_id = item.get("name", "").replace("models/", "")
                models.append(ProviderModel(
                    model_id=model_id,
                    label=item.get("displayName") or model_id,
                    provider="googleai",
                    context_length=(item.get("inputTokenLimit") or None),
                    extra=item,
                ))
            return models
        except Exception:
            return []


async def fetch_minimax_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from MiniMax (OpenAI-compatible /v1/models)."""
    return await _fetch_openai_compatible_models(
        "https://api.minimax.io/v1/models", api_key, "minimax",
    )


async def fetch_deepinfra_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.deepinfra.com/v1/openai/models", api_key, "deepinfra",
    )


async def fetch_fireworks_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.fireworks.ai/inference/v1/models", api_key, "fireworks",
    )


async def fetch_codestral_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.mistral.ai/v1/models", api_key, "codestral",
    )


async def fetch_hyperbolic_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.hyperbolic.xyz/v1/models", api_key, "hyperbolic",
    )


async def fetch_scaleway_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.scaleway.ai/v1/models", api_key, "scaleway",
    )


async def fetch_together_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.together.xyz/v1/models", api_key, "together",
    )


async def fetch_inferencenet_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.inference.net/v1/models", api_key, "inferencenet",
    )


async def fetch_sealion_models(api_key: str | None = None) -> list[ProviderModel]:
    return await _fetch_openai_compatible_models(
        "https://api.sea-lion.ai/v1/models", api_key, "sealion",
    )


async def fetch_ollama_models(api_key: str | None = None) -> list[ProviderModel]:
    """List chat models from a local Ollama daemon (GET /api/tags). No API key."""
    url = "http://127.0.0.1:11434/api/tags"
    headers = {"User-Agent": "model-radar/0.9 (github.com/srclight/model-radar)"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=2.0)
            resp.raise_for_status()
            data = resp.json()
            models = []
            for item in data.get("models") or []:
                model_id = item.get("name") or item.get("model") or ""
                if not model_id or _is_ollama_embedding(model_id):
                    continue
                models.append(ProviderModel(
                    model_id=model_id,
                    label=model_id,
                    provider="ollama",
                    extra=item,
                ))
            return models
        except Exception:
            return []


async def fetch_all_provider_models(
    provider: str | None = None,
) -> dict[str, list[ProviderModel]]:
    """
    Fetch models from all configured providers.

    Args:
        provider: Optional provider filter (e.g., "openrouter", "nvidia", "groq")

    Returns:
        Dict mapping provider key to list of models
    """
    cfg = load_config()
    results = {}

    fetchers = {
        "openrouter": fetch_openrouter_models,
        "nvidia": fetch_nvidia_models,
        "groq": fetch_groq_models,
        "cerebras": fetch_cerebras_models,
        "sambanova": fetch_sambanova_models,
        "siliconflow": fetch_siliconflow_models,
        "huggingface": fetch_huggingface_models,
        "xai": fetch_xai_models,
        "googleai": fetch_googleai_models,
        "ollama": fetch_ollama_models,
        "minimax": fetch_minimax_models,
        "deepinfra": fetch_deepinfra_models,
        "fireworks": fetch_fireworks_models,
        "codestral": fetch_codestral_models,
        "hyperbolic": fetch_hyperbolic_models,
        "scaleway": fetch_scaleway_models,
        "together": fetch_together_models,
        "inferencenet": fetch_inferencenet_models,
        "sealion": fetch_sealion_models,
    }
    all_fetchable = list(fetchers)
    providers_to_fetch = [provider] if provider else all_fetchable

    tasks = []
    for pkey in providers_to_fetch:
        if pkey in fetchers:
            api_key = get_api_key(cfg, pkey)
            tasks.append((pkey, fetchers[pkey](api_key)))
    
    # Fetch in parallel
    import asyncio
    completed = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
    
    for i, (provider_key, _) in enumerate(tasks):
        result = completed[i]
        if isinstance(result, Exception):
            results[provider_key] = []
        else:
            results[provider_key] = result
    
    return results


def _is_free_from_pricing(extra: dict | None) -> bool | None:
    """Derive is_free from OpenRouter-style pricing (prompt/completion 0 = free). Returns None if unknown."""
    if not extra or not isinstance(extra.get("pricing"), dict):
        return None
    pricing = extra["pricing"]
    prompt = pricing.get("prompt")
    completion = pricing.get("completion")
    if prompt is None and completion is None:
        return None
    try:
        p = float(prompt) if prompt is not None else 0
        c = float(completion) if completion is not None else 0
        return p == 0 and c == 0
    except (TypeError, ValueError):
        if isinstance(prompt, str) and "free" in prompt.lower():
            return True
        return None


def _is_free_from_hf_providers(extra: dict | None) -> bool | None:
    """Derive is_free from HuggingFace router provider pricing. Free if any provider has 0/0."""
    if not extra or not isinstance(extra.get("providers"), list):
        return None
    for prov in extra["providers"]:
        pricing = prov.get("pricing", {})
        if not pricing:
            continue
        try:
            inp = float(pricing.get("input", 1))
            out = float(pricing.get("output", 1))
            if inp == 0 and out == 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _seed_by_id(provider_key: str) -> dict[str, tuple]:
    from .providers import SEED_MODELS
    return {row[0]: row for row in SEED_MODELS.get(provider_key, ())}


def _provider_models_to_db_rows(
    models: list[ProviderModel],
    provider_key: str,
) -> list[tuple[str, str, str, str, str, bool | None]]:
    """Map live API models to DB rows. Seed metadata overlays matching ids.

    Live list is identity (add new, drop retired). Seeds only supply
    label/tier/SWE/context for ids we already knew.
    """
    seeds = _seed_by_id(provider_key)
    rows = []
    for m in models:
        is_free = None
        if provider_key == "openrouter":
            is_free = _is_free_from_pricing(m.extra)
        elif provider_key == "huggingface":
            is_free = _is_free_from_hf_providers(m.extra)
        if is_free is None and (m.model_id or "").lower():
            if ":free" in (m.model_id or "").lower() or "-free" in (m.model_id or "").lower():
                is_free = True
        if is_free is None:
            from .cost import default_is_free
            is_free = default_is_free(provider_key)
        seed = seeds.get(m.model_id)
        if seed:
            _sid, seed_label, tier, swe, seed_ctx = seed
            label = seed_label if (not m.label or m.label == m.model_id) else m.label
            context = str(m.context_length) if m.context_length else seed_ctx
        else:
            label = m.label or m.model_id
            tier = "C"
            swe = ""
            context = str(m.context_length) if m.context_length else ""
        rows.append((m.model_id, label, tier, swe, context, is_free))
    return rows


def _apply_live_rows(
    provider_key: str,
    rows: list[tuple[str, str, str, str, str, bool | None]],
    db_path: Path | None = None,
) -> int:
    from .db import replace_provider_models
    n = replace_provider_models(provider_key, rows, db_path=db_path)
    try:
        from .providers import set_provider_models
        set_provider_models(provider_key, tuple(
            (mid, label, tier, swe, ctx) for mid, label, tier, swe, ctx, _free in rows
        ))
    except Exception:
        pass
    return n


async def refresh_models_from_live(
    provider: str | None = None,
    db_path: Path | None = None,
) -> dict[str, int]:
    """
    Fetch latest model lists and replace those providers' catalogs.

    A successful non-empty fetch deletes retired ids and inserts the live
    list. An empty/failed fetch leaves the last snapshot in place.
    """
    from .db import mark_catalog_fetched

    results = await fetch_all_provider_models(provider=provider)
    cfg = load_config()
    counts = {}
    for provider_key, models in results.items():
        if not models:
            attempted = bool(get_api_key(cfg, provider_key)) or provider_key == "ollama"
            if attempted:
                mark_catalog_fetched(provider_key, 0, ok=False, db_path=db_path)
            continue
        rows = _provider_models_to_db_rows(models, provider_key)
        n = _apply_live_rows(provider_key, rows, db_path=db_path)
        mark_catalog_fetched(provider_key, n, ok=True, db_path=db_path)
        counts[provider_key] = n
    return counts


def refresh_cli_catalogs(
    provider: str | None = None,
    db_path: Path | None = None,
) -> dict[str, int]:
    """Re-list subscription CLIs and replace their catalogs (purge + add)."""
    from .cli_provider import CLI_SPECS, fetch_cli_models
    from .db import mark_catalog_fetched
    from .providers import PROVIDERS

    counts = {}
    for spec in CLI_SPECS:
        if provider and spec.key != provider:
            continue
        if spec.key not in PROVIDERS:
            continue
        models = fetch_cli_models(spec)
        if not models:
            mark_catalog_fetched(spec.key, 0, ok=False, db_path=db_path)
            continue
        rows = [
            (mid, label, tier, swe, ctx, True)
            for mid, label, tier, swe, ctx in models
        ]
        n = _apply_live_rows(spec.key, rows, db_path=db_path)
        mark_catalog_fetched(spec.key, n, ok=True, db_path=db_path)
        counts[spec.key] = n
    return counts


def _auto_refresh_disabled(db_path: Path | None) -> bool:
    """Skip implicit refresh during pytest unless the test passed a db_path."""
    if db_path is not None:
        return False
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


async def ensure_catalog_fresh(
    provider: str | None = None,
    *,
    ttl_seconds: int = CATALOG_TTL_SECONDS,
    force: bool = False,
    db_path: Path | None = None,
) -> dict[str, int]:
    """Refresh catalogs that are missing or older than TTL.

    Catalog list calls are free. Completions are what cost money.
    """
    from .db import catalog_is_stale
    from .providers import PROVIDERS

    if not force and _auto_refresh_disabled(db_path):
        return {}

    async with _refresh_gate():
        https_stale = False
        cli_stale = False
        if provider:
            https_stale = provider in HTTPS_CATALOG_KEYS and (
                force or catalog_is_stale(provider, ttl_seconds, db_path)
            )
            cli_stale = (
                provider in PROVIDERS
                and getattr(PROVIDERS[provider], "kind", "https") == "cli"
                and (force or catalog_is_stale(provider, ttl_seconds, db_path))
            )
        else:
            https_stale = force or any(
                catalog_is_stale(k, ttl_seconds, db_path)
                for k in HTTPS_CATALOG_KEYS
            )
            cli_stale = force or any(
                catalog_is_stale(k, ttl_seconds, db_path)
                for k, p in PROVIDERS.items()
                if getattr(p, "kind", "https") == "cli"
            )

        counts: dict[str, int] = {}
        if https_stale:
            counts.update(await refresh_models_from_live(provider=provider, db_path=db_path))
        if cli_stale:
            counts.update(refresh_cli_catalogs(provider=provider, db_path=db_path))
        return counts


def compare_models(
    hardcoded_models: list[ProviderModel],
    live_models: list[ProviderModel],
) -> dict[str, list[str]]:
    """
    Compare hardcoded models with live models from API.
    
    Returns:
        Dict with 'missing', 'extra', and 'matched' lists
    """
    hardcoded_ids = {m.model_id for m in hardcoded_models}
    live_ids = {m.model_id for m in live_models}
    
    missing = list(live_ids - hardcoded_ids)  # In live but not hardcoded
    extra = list(hardcoded_ids - live_ids)    # In hardcoded but not live
    
    return {
        "missing": missing,
        "extra": extra,
        "matched": list(hardcoded_ids & live_ids),
    }
