# Architecture

## Overview

Model Radar is an MCP server that discovers, pings, and executes prompts on free coding LLM models across 21 providers. It ranks models by real-time latency and helps AI agents pick the fastest available model.

## Module Map

| Module | Purpose |
|--------|---------|
| `providers.py` | Provider/model definitions, tier system (S+ through C based on SWE-bench Verified) |
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
| `provider_sync.py` | Live model fetching from provider APIs (OpenRouter, NVIDIA, Groq) |

## Data Flow

```
Provider APIs → providers.py (static catalog)
                    ↓
              db.py (SQLite, synced on first use)
                    ↓
           scanner.py (ping → latency ranking)
                    ↓
            runner.py (execute on fastest)
                    ↓
           server.py (MCP tools → agents)
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
