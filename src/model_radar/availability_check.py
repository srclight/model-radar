"""
Check model availability and identify obsolete models.
"""

import asyncio
from dataclasses import dataclass
from typing import Literal
from .db import filter_models, get_all_models
from .provider_sync import fetch_all_provider_models, compare_models
from .config import load_config, get_api_key


@dataclass
class AvailabilityResult:
    model_id: str
    provider: str
    status: Literal["available", "obsolete", "rate_limited", "not_found", "error"]
    message: str = ""
    pricing: dict | None = None


async def check_model_availability(
    provider: str,
    model_id: str,
    api_key: str | None = None,
) -> AvailabilityResult:
    """
    Check if a specific model is available.
    
    This is a lightweight check - just verifies the model exists.
    """
    # We'll implement per-provider availability checks
    if provider == "openrouter":
        # Check via OpenRouter API
        pass
    elif provider == "nvidia":
        # Check via NVIDIA API
        pass
    elif provider == "groq":
        # Check via Groq API
        pass
    
    # For now, return not implemented
    return AvailabilityResult(
        model_id=model_id,
        provider=provider,
        status="error",
        message="Not implemented yet"
    )


async def scan_hardcoded_models() -> dict:
    """
    Scan all hardcoded models to see which are still available.
    
    Returns:
        Dict with availability status
    """
    cfg = load_config()
    
    # Get hardcoded models
    hardcoded = get_all_models()
    
    # Get live models from APIs
    live = await fetch_all_provider_models()
    
    results = {
        "total_hardcoded": len(hardcoded),
        "available": [],
        "obsolete": [],
        "unknown": [],
    }
    
    for model in hardcoded:
        provider = model.provider
        model_id = model.model_id
        
        # Check if provider has live data
        if provider in live:
            live_models = live[provider]
            live_ids = {m.model_id for m in live_models}
            
            if model_id in live_ids:
                results["available"].append(model)
            else:
                results["obsolete"].append(model)
        else:
            results["unknown"].append(model)
    
    return results


def print_availability_report(results: dict):
    """Print availability report."""
    print("\n" + "="*60)
    print("MODEL AVAILABILITY REPORT")
    print("="*60)
    
    print(f"\nTotal hardcoded models: {results['total_hardcoded']}")
    print(f"Available: {len(results['available'])}")
    print(f"Potentially obsolete: {len(results['obsolete'])}")
    print(f"Unknown (no API): {len(results['unknown'])}")
    
    if results['obsolete']:
        print("\n⚠️  Potentially obsolete models:")
        for model in results['obsolete'][:20]:
            print(f"  - [{model.tier}] {model.label} ({model.provider}/{model.model_id})")
        if len(results['obsolete']) > 20:
            print(f"  ... and {len(results['obsolete']) - 20} more")
    
    if results['unknown']:
        print("\n❓ Models without API verification:")
        for model in results['unknown'][:20]:
            print(f"  - [{model.tier}] {model.label} ({model.provider}/{model.model_id})")
        if len(results['unknown']) > 20:
            print(f"  ... and {len(results['unknown']) - 20} more")


async def main():
    """Main function."""
    print("Scanning hardcoded models for availability...")
    results = await scan_hardcoded_models()
    print_availability_report(results)
    
    # Save detailed report
    import json
    from pathlib import Path
    
    report = {
        "total": results["total_hardcoded"],
        "available_count": len(results["available"]),
        "obsolete_count": len(results["obsolete"]),
        "unknown_count": len(results["unknown"]),
        "obsolete_models": [
            {"id": m.model_id, "provider": m.provider, "tier": m.tier, "label": m.label}
            for m in results["obsolete"]
        ],
    }
    
    report_path = Path("availability_report.json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nDetailed report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
