# Live Model Fetching

Model Radar can now fetch **live model lists** directly from provider APIs, showing you exactly what's available right now.

## Supported Providers

✅ **OpenRouter** - 344+ models available  
✅ **NVIDIA NIM** - 184+ models available  
✅ **Groq** - 20 models available  

## Usage

### Fetch All Providers

```bash
model-radar db live
```

### Fetch Specific Provider

```bash
model-radar db live --provider openrouter
model-radar db live --provider nvidia
model-radar db live --provider groq
```

### Compare with Hardcoded Models

See what's new and what's missing:

```bash
model-radar db live --compare
```

**Example output:**
```
Comparison with hardcoded models:
  openrouter:
    Hardcoded: 10
    Live: 344
    New in live (338): anthropic/claude-sonnet-4.6, ...
    Missing from live (4): mimo-v2-flash-free, ...
  
  nvidia:
    Hardcoded: 41
    Live: 184
    New in live (142): ...
  
  groq:
    Hardcoded: 10
    Live: 20
    New in live (14): ...
```

## API Endpoints Used

### OpenRouter
- **Endpoint:** `GET https://openrouter.ai/api/v1/models`
- **Auth:** Bearer token (API key)
- **Response:** List of models with pricing, context length, capabilities

### NVIDIA NIM
- **Endpoint:** `GET https://integrate.api.nvidia.com/v1/models`
- **Auth:** Bearer token (API key)
- **Response:** List of models with metadata

### Groq
- **Endpoint:** `GET https://api.groq.com/openai/v1/models`
- **Auth:** Bearer token (API key)
- **Response:** List of models with creation date and ownership

## Python API

```python
from model_radar.provider_sync import fetch_all_provider_models

# Fetch from all configured providers
results = await fetch_all_provider_models()

# Results:
# {
#     "openrouter": [ProviderModel(...), ...],
#     "nvidia": [ProviderModel(...), ...],
#     "groq": [ProviderModel(...), ...],
# }

# Fetch from specific provider
openrouter_models = await fetch_all_provider_models(provider="openrouter")
```

## Comparison API

```python
from model_radar.provider_sync import compare_models
from model_radar.db import filter_models

# Get hardcoded models
hardcoded = filter_models(provider="openrouter")

# Get live models
live = await fetch_openrouter_models(api_key)

# Compare
comparison = compare_models(hardcoded, live)
# {
#     "missing": ["new-model-1", "new-model-2"],  # In live but not hardcoded
#     "extra": ["old-model-1"],                   # In hardcoded but not live
#     "matched": ["model-1", "model-2"],          # In both
# }
```

## What This Tells Us

### OpenRouter
- **Hardcoded:** 10 models
- **Live:** 344 models
- **Status:** OpenRouter has **334 more models** than we have hardcoded!
- **Missing from live:** 4 free-tier models we listed

### NVIDIA
- **Hardcoded:** 41 models
- **Live:** 184 models
- **Status:** NVIDIA has **143 more models** than hardcoded
- **Note:** NVIDIA's catalog is much larger than our hardcoded list

### Groq
- **Hardcoded:** 10 models
- **Live:** 20 models
- **Status:** Groq has **10 more models** than hardcoded
- **Missing from live:** 4 models we have hardcoded are not in Groq's API

## Next Steps

### 1. Auto-Sync New Models
We could automatically add new models from live APIs to the database:

```bash
model-radar db sync --from-live
```

### 2. Periodic Sync
Set up a cron job or scheduled task to sync model lists daily/weekly.

### 3. Provider-Specific Tiers
Use live data to update tier information based on actual SWE-bench scores.

### 4. Availability Tracking
Track which models are currently available vs deprecated.

## Notes

- **API Keys Required:** You need valid API keys for each provider
- **Rate Limits:** Some providers may rate-limit unauthenticated requests
- **Privacy:** API keys are sent to providers (required for authentication)
- **No Caching:** Live fetch always gets fresh data (no caching yet)
