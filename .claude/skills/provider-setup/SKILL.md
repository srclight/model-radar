# Provider Setup

Add a new LLM provider to model-radar end-to-end.

## When to Use

When adding a new provider (e.g., a new free LLM API) to the model-radar catalog.

## Steps

### 1. Research the provider

Gather:
- Provider name and API base URL
- Authentication method (Bearer token, API key in query param, no auth)
- Environment variable convention (e.g., PROVIDER_API_KEY)
- Available models with their IDs
- Free tier availability and rate limits
- Model quality tiers (check SWE-bench Verified if available)

### 2. Add provider definition in `src/model_radar/providers.py`

Add a new `Provider` entry to the `PROVIDERS` dict:

```python
"provider_key": Provider(
    name="Provider Name",
    base_url="https://api.provider.com/v1",
    env_vars=["PROVIDER_API_KEY"],
    models=[
        Model("org/model-name", "Model Display Name", tier="A", ctx=32768),
    ],
),
```

Key fields:
- `base_url`: The OpenAI-compatible chat/completions endpoint base
- `env_vars`: List of environment variable names for the API key
- `tier`: SWE-bench tier (S+, S, A+, A, A-, B+, B, C)
- `ctx`: Context window size

### 3. Handle auth quirks in `src/model_radar/runner.py`

Most providers use `Authorization: Bearer <key>`. If the new provider differs:
- Query param auth: add to the `if provider == "..."` block around line 55
- Token auth: add to the Token block around line 62
- No auth: add to `_NO_AUTH_PROVIDERS` in `config.py`

### 4. Add provider sync if they have a models API

If the provider has a `/models` endpoint for dynamic model discovery, add a fetch function in `src/model_radar/provider_sync.py`.

### 5. Add setup guide

Add signup instructions in `src/model_radar/guides.py` so `setup_guide("provider_key")` returns useful onboarding steps.

### 6. Write tests

Add test coverage in `tests/test_providers.py`:
- Provider key exists in PROVIDERS
- Models have valid tiers
- Base URL is well-formed

### 7. Verify

```sh
python -m pytest tests/ -v
model-radar providers                    # should list new provider
model-radar scan --provider provider_key # should ping successfully
```

Via MCP:
```
list_providers()          # new provider shows up
scan(provider="provider_key", verify=True)  # models respond
```

## Checklist

- [ ] Provider added to PROVIDERS dict in providers.py
- [ ] Auth handling in runner.py (if non-standard)
- [ ] Setup guide in guides.py
- [ ] Tests added and passing
- [ ] Verified via CLI scan and MCP tools
