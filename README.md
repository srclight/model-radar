<!-- mcp-name: io.github.srclight/model-radar -->
# model-radar

MCP server that pings free coding LLM models across HTTPS providers and subscription CLIs (Claude Code, Grok, Antigravity/`agy`, Codex), ranks them by latency, and helps AI agents pick the fastest available model — or pin several subscriptions for a parallel review.

Inspired by [free-coding-models](https://github.com/vava-nessa/free-coding-models).

## Install

```sh
pip install model-radar-mcp
```

## Quick Start

### 1. Configure an API key

```sh
# Option A: Save to ~/.model-radar/config.json
model-radar configure nvidia nvapi-xxx

# Option B: Environment variable
export NVIDIA_API_KEY=nvapi-xxx
```

Or copy the template: `cp config.example.json ~/.model-radar/config.json` and edit it.

### 2. Add to your MCP client

**Claude Code** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "model-radar": {
      "command": "model-radar",
      "args": ["serve"]
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`):

Stdio (Cursor starts the server):
```json
{
  "mcpServers": {
    "model-radar": {
      "command": "/path/to/your/.venv/bin/model-radar",
      "args": ["serve"]
    }
  }
}
```

Streamable HTTP (persistent server — recommended):
```json
{
  "mcpServers": {
    "model-radar": {
      "url": "http://127.0.0.1:8743/mcp",
      "transportType": "streamable-http"
    }
  }
}
```

Start the server first:
```sh
model-radar serve --transport sse --port 8743
```

**OpenClaw** (`~/.openclaw/config/mcporter.json`):
```json
{
  "mcpServers": {
    "model-radar": {
      "type": "http",
      "url": "http://127.0.0.1:8743/mcp"
    }
  }
}
```

**Web dashboard:** Add `--web` for a localhost UI at `http://127.0.0.1:8743/` for status, config, discovery, and running prompts. The server binds to 127.0.0.1 only; keys never leave your machine.
```sh
model-radar serve --transport sse --port 8743 --web
```

**Auto-restart wrapper:**
```sh
while true; do model-radar serve --transport sse --port 8743; sleep 1; done
```
Then call `restart_server()` from any MCP client to reload with updated code.

### 3. CLI usage

```sh
# Scan models
model-radar scan --min-tier S --limit 10

# List providers
model-radar providers

# Save a key
model-radar configure nvidia nvapi-xxx
```

## Catalogs are live

Model ids are **not** a hardcoded list. On startup, once an hour, and after a completion 404, model-radar fetches each provider’s `/v1/models` (Ollama `/api/tags`, `grok models` / `agy models`) and **replaces** that provider’s catalog — new ids in, retired ids gone. `GET /v1/models` is free; completions are what you pay for.

Seed tuples in the package are a fallback plus SWE-bench overlays for known ids. See [Catalog playbook](docs/playbook-catalogs.md).

```sh
model-radar db refresh              # force live replace
python scripts/catalog-report.py    # seed vs live vs missing keys (no secrets)
```

## Providers

HTTPS providers take an API key (`configure_key` or env). Call `list_providers()` for the current count and key status.

| Provider | Env Var | Notes |
|----------|---------|--------|
| NVIDIA NIM | `NVIDIA_API_KEY` | Rate-limited, no expiry |
| Groq | `GROQ_API_KEY` | Free tier |
| Cerebras | `CEREBRAS_API_KEY` | Small, fast; catalog rotates often |
| SambaNova | `SAMBANOVA_API_KEY` | $5 credits / 3 months |
| OpenRouter | `OPENROUTER_API_KEY` | `:free` ids change frequently |
| Hugging Face | `HF_TOKEN` / `HUGGINGFACE_API_KEY` | Free monthly credits |
| Replicate | `REPLICATE_API_TOKEN` | Dev quota |
| DeepInfra | `DEEPINFRA_API_KEY` | Free dev tier |
| Fireworks | `FIREWORKS_API_KEY` | $1 free credits |
| Codestral/Mistral | `CODESTRAL_API_KEY` | 30 req/min, 2000/day |
| Hyperbolic | `HYPERBOLIC_API_KEY` | $1 free trial |
| Scaleway | `SCALEWAY_API_KEY` | 1M free tokens |
| Google AI | `GOOGLE_API_KEY` | 14.4K req/day |
| SiliconFlow | `SILICONFLOW_API_KEY` | Free model quotas |
| Together AI | `TOGETHER_API_KEY` | Credits vary |
| Cloudflare | `CLOUDFLARE_API_TOKEN` | 10K neurons/day |
| Perplexity | `PERPLEXITY_API_KEY` | Tiered limits |
| xAI | `XAI_API_KEY` | Or use the `grok` CLI instead |
| Inference.net | `INFERENCE_NET_API_KEY` | Free tier |
| SEA-LION | `SEALION_API_KEY` | Free tier |
| MiniMax | `MINIMAX_API_KEY` | `api.minimax.io` (M3). Same token works on `/anthropic` — do not set `ANTHROPIC_AUTH_TOKEN` globally |
| Ollama | none (local daemon) | Models already pulled on `127.0.0.1:11434` |

## CLI subscriptions

If you already pay for a monthly plan, model-radar can ride that subscription — no API key. The official CLI is auto-detected from `$PATH` at startup.

| CLI | Rides | Login |
|-----|--------|--------|
| `claude` | Claude Pro / Max | `claude auth login` |
| `grok` | SuperGrok | `grok login` |
| `agy` (provider key `gemini`) | Google AI Pro/Ultra / Gemini | run `agy` once to sign in |
| `codex` | ChatGPT Plus / Pro | `codex login` |

The old `gemini` CLI was deprecated (June 2026) in favor of [Antigravity CLI](https://antigravity.google/docs/cli/install) (`agy`). Install: `curl -fsSL https://antigravity.google/cli/install.sh | bash`. `agy models` may also list Claude and GPT-OSS on the same login. Codex-in-agy is a conversation mode; for model-radar use the standalone `codex` CLI.

These never join `get_fastest()` / default `ask()` — that would spend quota by accident. Pin them:

```
ask(prompt="Review this paragraph…", providers=["claude", "grok", "gemini"])
ask(prompt="…", model_ids=["sonnet", "grok-4.6"])
```

## MCP Tools

### Discovery
- **`list_providers()`** — See all providers, API-key status, and installed subscription CLIs
- **`list_models(tier?, provider?, min_tier?, free_only?)`** — Browse the catalog (refreshes a provider if its list is older than an hour)
- **`scan(verify?)`** — Ping models in parallel, ranked by latency. `verify=True` checks for non-empty output.
- **`get_fastest(min_tier?, count?, free_only?, verified?)`** — Best N models right now
- **`get_workers(count?, min_tier?, verified?)`** — N verified-alive models from N distinct providers
- **`provider_status()`** — Per-provider health check

### Execution
- **`run(prompt, model_id?, free_only?)`** — Execute on fastest model with auto-fallback
- **`ask(prompt, count=3, model_ids?, providers?)`** — Same prompt on N models (Ollama sequential, remotes parallel)
- **`recommend(job)`** — Short diverse lineup for `translate` / `rewrite` / `review` / `code` / `dict`
- **`quality_probe(job)`** — Time + pass/fail on a fixed prompt (`dict` = Paper B five headwords)
- **`still_free()`** — Which Lane A hosts still answer; skips dead catalog ids; reports `completion_calls`
- **`batch_run(prompts, results_file?)`** — Batch execution with incremental JSONL, resume support, adaptive concurrency

### Evaluation (LLM-as-Judge)
- **`judge(prompt, rubric, count=3, exclude_providers?)`** — Rate a single item with N diverse judges (pass the producer to exclude)
- **`compare(item_a, item_b, blind=True)`** — Blind A/B comparison, randomized order per judge
- **`batch_judge(items, rubric, results_file?)`** — Evaluate at scale with incremental results
- **`backtranslate_eval(..., exclude_providers?)`** — Back-translation quality metric; do not use the producer

### Quality & Setup
- **`benchmark(model_id?)`** — Quality-test with 5 coding challenges
- **`refresh_models()`** — Fetch live lists and replace each provider’s catalog (purge retired ids)
- **`setup_guide(provider?)`** — Setup instructions for unconfigured providers
- **`configure_key(provider, api_key)`** — Save an API key
- **`restart_server()`** — Restart for code updates (SSE mode)
- **`server_stats()`** — Uptime and start time

## Tier Scale (SWE-bench Verified)

| Tier | Score | Meaning |
|------|-------|---------|
| S+ | 70%+ | Elite frontier coders |
| S | 60-70% | Excellent |
| A+ | 50-60% | Great |
| A | 40-50% | Good |
| A- | 35-40% | Decent |
| B+ | 30-35% | Average |
| B | 20-30% | Below average |
| C | <20% | Lightweight/edge |

## Documentation

- [Architecture](docs/architecture.md) — Module map, live catalogs, transport, rate limiting
- [MCP Transport](docs/mcp-transport.md) — Transport options, stateless HTTP, client configuration
- [Catalog playbook](docs/playbook-catalogs.md) — Live vs seed, TTL, purge, 404 refetch
- [Local MCP ops](docs/playbook-local-mcp.md) — systemd restart, keys, compare runs
- [Translation Pipeline Playbook](docs/playbook-translation-pipeline.md) — Batch translation patterns
- [LLM-as-Judge Playbook](docs/playbook-llm-as-judge.md) — Evaluation patterns and judge selection

## License

MIT
