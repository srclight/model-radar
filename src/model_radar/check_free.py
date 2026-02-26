"""
Check which models are free vs paid by querying provider APIs.
"""

import asyncio
import json
from .provider_sync import fetch_openrouter_models, fetch_nvidia_models, fetch_groq_models
from .config import get_api_key, load_config


async def check_openrouter_pricing():
    """Check OpenRouter model pricing."""
    cfg = load_config()
    api_key = get_api_key(cfg, "openrouter")
    
    if not api_key:
        print("No OpenRouter API key configured")
        return
    
    print("Fetching OpenRouter models with pricing...")
    models = await fetch_openrouter_models(api_key)
    
    # Separate free vs paid
    free_models = []
    paid_models = []
    
    for model in models[:50]:  # Check first 50
        extra = model.extra or {}
        pricing = extra.get("pricing", {})
        
        # Check if any pricing tier is free
        is_free = False
        if isinstance(pricing, dict):
            # Check if prompt pricing is 0 or very low
            prompt_price = pricing.get("prompt", 1)
            if prompt_price == 0 or (isinstance(prompt_price, str) and 'free' in prompt_price.lower()):
                is_free = True
        
        # Check model ID for "free" indicator
        if 'free' in model.model_id.lower() or ':free' in model.model_id:
            is_free = True
        
        if is_free:
            free_models.append(model.model_id)
        else:
            paid_models.append(model.model_id)
    
    print(f"\nOpenRouter: {len(models)} total models")
    print(f"  Free models: {len(free_models)}")
    print(f"  Paid models: {len(paid_models)}")
    
    if free_models:
        print("\nFree models:")
        for m in free_models[:20]:
            print(f"  - {m}")
        if len(free_models) > 20:
            print(f"  ... and {len(free_models) - 20} more")
    
    print("\nFirst 20 paid models:")
    for m in paid_models[:20]:
        print(f"  - {m}")


async def check_groq_pricing():
    """Check Groq model pricing."""
    cfg = load_config()
    api_key = get_api_key(cfg, "groq")
    
    if not api_key:
        print("No Groq API key configured")
        return
    
    print("\nFetching Groq models...")
    models = await fetch_groq_models(api_key)
    
    # Groq has rate limits on free tier
    print(f"Groq: {len(models)} models available")
    
    # Check for rate limit indicators
    for model in models:
        extra = model.extra or {}
        if 'rate_limit' in str(extra).lower():
            print(f"  {model.model_id}: May have rate limits")


if __name__ == "__main__":
    print("Checking model pricing and availability...\n")
    asyncio.run(check_openrouter_pricing())
    asyncio.run(check_groq_pricing())
