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
| `config.py` | Config management (~/.model-radar/config.json), API key resolution |
| `server.py` | FastMCP server, all MCP tool definitions |
| `cli.py` | Click CLI — serve, scan, providers, db commands |
| `db.py` | SQLite persistence for model catalog and ping results |
| `provider_sync.py` | Live `/v1/models` fetch, TTL refresh, purge+add, CLI catalog replace |
| `cli_provider.py` | Subscription CLIs (`claude`, `grok`, `agy`, `codex`) as single-turn completions |

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

Stateful sessions (the FastMCP default) create a server-side session per client connection. When the server restarts, those sessions are lost and clients get `-32600 Session not found` errors. Since model-radar tools are all stateless request/response (no subscriptions, no streaming state), `stateless_http=True` is the correct choice.

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
