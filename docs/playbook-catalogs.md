# Playbook: Live catalogs

Model lists change without notice. Cerebras dropped Qwen 235B and Llama 3.1 8B; OpenRouter retired most `:free` ids; MiniMax added M3. Treat the provider’s `/v1/models` (or `agy models` / Ollama `/api/tags`) as truth. Seeds are a spare tire.

## Two lists, different jobs

| List | Where | Job |
|------|--------|-----|
| **Reachable (live)** | `GET /v1/models`, Ollama `/api/tags`, `grok models` / `agy models` | What *this user* can call. `ask` / `run` / `list_models` use this. |
| **Seed (default)** | `providers.py` `SEED_MODELS`, CLI `CliSpec.models` | Bootstrap + SWE-bench overlay when live fetch has not run or failed. |

Provider **endpoints** (base URL, env var, CLI command) live in code. Model **ids** do not.

## Listing catalogs is free

`GET /v1/models` is not billed as inference. Completions are. Refresh often.

Cerebras also publishes `GET https://api.cerebras.ai/public/v1/models` with no API key (pricing, preview, deprecated, reasoning flags). Authenticated `/v1/models` is still what this account can call.

## Refresh policy

| When | What |
|------|------|
| Server start | Parallel live fetch (`cli._run_uvicorn` → `_startup_refresh`). `create_server()` runs *before* the event loop — do not schedule refresh there. |
| `list_models` / `ask` / `run` / `scan` / `get_fastest` / `get_workers` | Refresh any catalog older than **1 hour** (`CATALOG_TTL_SECONDS`). |
| `refresh_models()` / `model-radar db refresh` | Force replace now. |
| HTTP **404** on a completion | Force-refresh that provider. If the id is gone, the error lists current ids. |

A **successful non-empty** fetch `DELETE`s that provider’s previous rows and inserts the live list (purge retired, add new). An **empty or failed** fetch **keeps** the last snapshot and records `catalog:{key}:source=failed`. Never wipe to nothing because the network hiccuped.

Seeds are captured on first `_p()` into `SEED_MODELS`. Live refresh overwrites `PROVIDERS[key].models` but overlays seed label/tier/SWE onto matching ids. Brand-new live ids (no seed row) are tier `C` until scored.

Ollama’s seed stays **empty**. The catalog is whatever this machine has pulled.

## What we learned in the field

- **Cerebras rotates hard.** Public lineup in Aug 2026: `gpt-oss-120b`, `gemma-4-31b`, `zai-glm-4.7` (GLM scheduled to drop 2026-08-17). Seed ids `qwen-3-235b-a22b-instruct-2507` and `llama3.1-8b` 404. Do not chase Qwen on Cerebras — resolve it from whoever still lists it.
- **Startup refresh used to be a no-op.** `asyncio.ensure_future` from `create_server()` ran before uvicorn owned a loop (`coroutine never awaited`). Refresh is started from `_run_uvicorn`.
- **Do not dump a 400-model OpenRouter list into the seed.** Seed is a curated *current* fallback (especially `:free` ids that still exist). Live DB holds the full list.
- **CLI catalogs belong in the same replace cycle.** `agy models` now includes Claude and GPT-OSS, not just Gemini. Codex-in-agy is a conversation mode; `agy models` may not list `gpt-5.6-terra`. Keep the standalone `codex` CLI for model-radar.
- **Host-swap is HTTPS-only.** CLI providers have `url=None`. Skip them when picking a default OpenAI-compatible endpoint.

## Commands

```sh
# Force live replace (purge + add)
model-radar db refresh
model-radar db refresh -p minimax

# Seed vs live vs keys (no secrets printed)
python scripts/catalog-report.py

# MCP
refresh_models()
refresh_models(provider="cerebras")
list_models(provider="minimax")
```

After changing catalog code, restart the live MCP — see [Local MCP ops](playbook-local-mcp.md).
