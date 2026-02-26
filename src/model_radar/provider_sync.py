"""
Fetch live model lists from provider APIs.

Supports:
- OpenRouter: GET https://openrouter.ai/api/v1/models
- NVIDIA: GET https://integrate.api.nvidia.com/v1/models
- Groq: GET https://api.groq.com/openai/v1/models
"""

from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Any

from .config import get_api_key, load_config


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
    headers = {"Authorization": f"Bearer {api_key}"}
    
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
    headers = {"Authorization": f"Bearer {api_key}"}
    
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
    headers = {"Authorization": f"Bearer {api_key}"}
    
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
    
    providers_to_fetch = []
    if provider:
        providers_to_fetch = [provider]
    else:
        providers_to_fetch = ["openrouter", "nvidia", "groq"]
    
    tasks = []
    
    if "openrouter" in providers_to_fetch:
        api_key = get_api_key(cfg, "openrouter")
        tasks.append(("openrouter", fetch_openrouter_models(api_key)))
    
    if "nvidia" in providers_to_fetch:
        api_key = get_api_key(cfg, "nvidia")
        tasks.append(("nvidia", fetch_nvidia_models(api_key)))
    
    if "groq" in providers_to_fetch:
        api_key = get_api_key(cfg, "groq")
        tasks.append(("groq", fetch_groq_models(api_key)))
    
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
