<!-- mcp-name: io.github.srclight/model-radar -->
# model-radar

MCP server that discovers live model catalogs across HTTPS providers (free and paid) and subscription CLIs (Claude Code, Grok, Antigravity/`agy`, Codex), ranks models by measured latency, and lets AI agents run a prompt on the fastest one, compare answers across several, or judge output with a panel of models.

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

**Keeping keys somewhere else.** Set `MODEL_RADAR_CONFIG` to the full path of the config file, for example one on an encrypted or removable volume:

```sh
export MODEL_RADAR_CONFIG=/path/to/secure-volume/model-radar.json
```

Only that file is then read and written. If it is missing (say, the volume is not mounted), model-radar loads no keys from disk, says so in `list_providers()` and `/healthz` (`config_ok: false`), and refuses to save rather than create the path. It never falls back to the home directory, and a `config.json` in the working directory is never read. Provider env vars such as `GROQ_API_KEY` still override the file.

See [Keys and security](#keys-and-security) for what model-radar does with keys.

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

## Keys and security

- **One file holds the keys.** It is `~/.model-radar/config.json`, or the file named by `MODEL_RADAR_CONFIG`, created with mode `0600`. Provider env vars override it. Nothing else is read.
- **Keys are never returned.** `list_providers()`, `profile()` and `/healthz` report `configured` or `missing`, the names of stored keys, and the config path. They never include a key value.
- **Keys go only to their own provider.** A key is sent to that provider's API endpoint and nowhere else. There is no telemetry.
- **The HTTP server binds to `127.0.0.1`.** The dashboard and its REST routes are off unless you pass `--web`.
- **Do not commit a config file.** `config.json` is in `.gitignore`; `config.example.json` is the template.

| Environment variable | Purpose |
|----------------------|---------|
| `MODEL_RADAR_CONFIG` | Full path of the config file to use in place of `~/.model-radar/config.json` |
| `MODEL_RADAR_CLI_TIMEOUT` | Seconds to wait for a subscription CLI to answer (default 300) |
| `MODEL_RADAR_ALLOW_RESTART` | Set to `0` to disable the `restart_server()` tool |
| `<PROVIDER>_API_KEY` | A provider key; see the Providers table for each name |

## MCP argument validation

Unknown tool arguments are **refused**, not silently dropped — a mistyped filter is rejected with an
error, never answered as if it were applied. Every tool advertises `additionalProperties: false`.
The guard comes from [`ironmcp`](https://github.com/srclight/ironmcp) (`strict_server`), and
`tests/test_conformance.py` checks that every tool enforces what it advertises.

**AI agents:** an `unknown argument(s): … running older code … reconnect` error means the running
server predates the argument you sent — nothing ran; reconnect the MCP rather than retrying the same
call.

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
| Vercel AI Gateway | `AI_GATEWAY_API_KEY` | List price; free monthly credit needs a card on file. Also serves `typesafe-ai/jev` via `evaluate` |
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
- **`quality_probe(job)`** — Time + pass/fail on a fixed prompt (`translate`, `rewrite`, `review`, or `dict`: five dictionary headwords)
- **`still_free(speed?)`** — Which Lane A hosts still answer; up to 3 chat models each in parallel (`speed=fast` prefers small/flash ids)
- **`batch_run(prompts, results_file?)`** — Batch execution with incremental JSONL, resume support, adaptive concurrency

### Evaluation (LLM-as-Judge)
- **`judge(prompt, rubric, count=3, exclude_providers?)`** — Rate a single item with N diverse judges (pass the producer to exclude)
- **`compare(item_a, item_b, blind=True)`** — Blind A/B comparison, randomized order per judge
- **`batch_judge(items, rubric, results_file?)`** — Evaluate at scale with incremental results
- **`backtranslate_eval(..., exclude_providers?)`** — Back-translation quality metric; do not use the producer
- **`evaluate(state, questions, model_id?)`** — Typed judgments from TypeSafe Jev (`typesafe-ai/jev`) through Vercel AI Gateway: boolean P(yes), choice, or score. Needs `AI_GATEWAY_API_KEY`

### Quality & Setup
- **`benchmark(model_id?)`** — Quality-test with 5 coding challenges
- **`refresh_models()`** — Fetch live lists and replace each provider’s catalog (purge retired ids)
- **`setup_guide(provider?)`** — Setup instructions for unconfigured providers
- **`setup_workflow(step, provider_selection?)`** — Step-by-step setup for an agent guiding a user through provider signups
- **`configure_key(provider, api_key, key_id?, make_active?)`** — Save a named API key; other keys on the provider are kept
- **`host_swap_instructions(model_id?, provider?, min_tier?)`** — Base URL and model id to set in a host app (Cursor, Claude Code, and others), and where each app keeps its settings
- **`restart_server()`** — Restart for code updates (SSE mode)
- **`server_stats()`** — Uptime and start time

### Spend control
- **`profile()`** — Spend lane of each provider (A never invoices, B is a monthly CLI, C can charge) with your `funded` and `spend_ok` flags. No secrets
- **`set_profile(provider, spend_ok?, funded?, login?)`** — Set those flags. A provider that can charge is never picked unprompted unless it is funded and `spend_ok` is true
- **`credits(provider?)`** — Remaining prepaid balance or quota where the provider has an API for it (OpenRouter, Vercel AI Gateway, SiliconFlow, Groq)

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
