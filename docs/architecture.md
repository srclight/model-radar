# Architecture

## Catalogs are live, not hardcoded

model-radar is for every user, not one machine. Provider **endpoints** (base URL, env var, CLI command) live in code. Model **ids** come from the user's world:

- HTTPS: `GET /v1/models` on startup, hourly (`CATALOG_TTL_SECONDS`), `refresh_models()`, and after a completion **404**
- Ollama: `GET http://127.0.0.1:11434/api/tags` on this machine (seed is empty)
- Subscription CLIs: `grok models`, `agy models`, etc.

A successful fetch **replaces** that provider’s SQLite rows (new ids in, retired ids gone). An empty/failed fetch keeps the last snapshot. Seed tuples in `SEED_MODELS` (`providers.py`) are fallbacks plus SWE-bench overlays for known ids — never the identity of the catalog.

Listing catalogs is free. Completions are what cost money. See [playbook-catalogs.md](playbook-catalogs.md).

## Overview

Model Radar is an MCP server that discovers, pings, and executes prompts on free coding LLM models across HTTPS providers, and rides monthly subscriptions via local CLIs (`claude`, `grok`, `agy`, `codex`). It ranks HTTPS models by real-time latency. Subscription CLIs are opt-in via `ask(model_ids=…)` / `ask(providers=…)`.

## Module Map

| Module | Purpose |
|--------|---------|
| `providers.py` | Provider endpoints + `SEED_MODELS` fallbacks, tier system (S+ through C based on SWE-bench Verified) |
| `scanner.py` | Async httpx ping engine, parallel model scanning, rolling stats, verified-alive checks, adaptive rate limiting |
| `runner.py` | Execute prompts via chat/completions API, automatic fallback, batch execution, back-translation evaluation |
| `consensus.py` | Multi-model consensus — run same prompt on N models in parallel |
| `judge.py` | LLM-as-judge evaluation — rate items, compare pairs, batch evaluation with diverse judges |
| `text_utils.py` | Think-tag stripping, script purity validation, prompt-echo detection |
| `benchmark.py` | Quick coding quality tests (5 challenges, pass/fail scoring) |
| `quality.py` | Persistent quality memory — stores benchmark scores across sessions |
| `guides.py` | Provider setup wizard — structured setup instructions for agents |
| `config.py` | Config management (`~/.model-radar/config.json`, or the file named by `MODEL_RADAR_CONFIG`), API key resolution |
| `server.py` | MCP server (`ironmcp.strict_server` on the mcp v2 SDK), all MCP tool definitions, `/healthz` |
| `cli.py` | Click CLI — serve, scan, providers, db commands |
| `db.py` | SQLite persistence for model catalog and ping results |
| `provider_sync.py` | Live `/v1/models` fetch, TTL refresh, purge+add, CLI catalog replace |
| `cli_provider.py` | Subscription CLIs (`claude`, `grok`, `agy`, `codex`) as single-turn completions |
| `lanes.py` | Spend lanes: A never invoices, B is a monthly CLI, C can charge |
| `cost.py` | Cost class of a model (`zero`, `free_tier`, `subscription`, `local`, `paid`, `unknown`) |
| `credits.py` | Remaining balance or quota, for the few providers that expose one |
| `cooldown.py` | Process-local provider cooldown after 401/402/429/529 |
| `recommend.py` | Short, provider-diverse lineup for a job (`translate`, `rewrite`, `review`, `code`, `dict`) |
| `probe.py` | Timed pass/fail quality probe on a fixed prompt per job |
| `sweep.py` | `still_free`: which never-invoicing hosts still answer |
| `evaluate.py` | Typed evaluation models (TypeSafe Jev) through Vercel AI Gateway |
| `endpoints.py` | OpenAI-compatible base URL and model id for a given model |
| `host_swap.py` | Where host apps keep their model settings, for swap instructions |
| `setup_workflow.py` | Step-by-step provider setup for a host agent |
| `web.py` | Optional dashboard and REST routes (`serve --transport sse --web`) |
| `availability_check.py`, `check_free.py`, `ping_test.py` | Maintenance scripts: obsolete ids, free vs paid, ping every model |

## Data Flow

```
Live /v1/models, Ollama /api/tags, `agy models`
                    ↓
        provider_sync.ensure_catalog_fresh
                    ↓
     db.py (replace provider rows) + PROVIDERS[]
                    ↓
           scanner.py (ping → latency ranking)
                    ↓
            runner.py (execute; 404 → refetch)
                    ↓
           server.py (MCP tools → agents)

SEED_MODELS overlay tier/SWE onto matching live ids only.
```

## Transport

The server uses **Streamable HTTP** (MCP spec 2025-03-26) with `stateless_http=True`:

- Each HTTP request is independent — no session tracking
- Survives server restarts without client errors
- SSE endpoints (`/sse`, `/messages/`) are still served for backward compatibility
- Streamable HTTP endpoint: `/mcp`

### Why stateless?

Stateful sessions (the SDK default) create a server-side session per client connection. When the server restarts, those sessions are lost and clients get `-32600 Session not found` errors. Since model-radar tools are all stateless request/response (no subscriptions, no streaming state), `stateless_http=True` is the correct choice.

## Configuration and keys

`config.py` resolves exactly one config file: the path in `MODEL_RADAR_CONFIG` if set, otherwise `~/.model-radar/config.json`. A provider env var overrides the key in the file.

- An explicit path is never created and never replaced by a fallback. If it is missing, `load_config()` returns an empty config and `config_status()` carries the error, which `list_providers()` and `/healthz` (`config_ok`) surface.
- `save_config()` raises `ConfigError` when the write fails or when the existing file does not parse, so a broken file is never overwritten.
- The file is created with mode `0600`. Tool responses carry key names and status only, never values.
- The test suite points the default path at a temp directory (`tests/conftest.py`), so tests never touch a real config.

## Rate Limiting

`ProviderThrottle` in `scanner.py` provides:

- **Per-provider 429 tracking** with exponential backoff (1s → 2s → 4s → 8s → 16s cap)
- **Adaptive concurrency** — auto-halves on 429s, recovers after 10 consecutive successes
- **Degradation detection** — `is_degraded(provider)` flags providers with 2+ recent rate limits
- **Global sharing** — single throttle instance across all tools in a session

## Verified-Alive Scanning

`scan(verify=True)` performs a two-stage check:

1. **Ping**: Lightweight `max_tokens=1` request to check endpoint reachability
2. **Verify**: Real prompt ("Reply with exactly: OK") to confirm non-empty output

This catches models that return HTTP 200 but produce empty content (GPT-OSS-120B class) or put output in non-standard fields (`message.reasoning`). The verify step also checks reasoning fields so reasoning models aren't falsely marked as broken.

## Provider Diversity

Judge selection (`_select_diverse_judges`) and `get_workers()` enforce provider diversity:
- At most 1 model per provider
- Degraded providers (recent 429s) are deprioritized
- Prevents correlated failures when a provider goes down
