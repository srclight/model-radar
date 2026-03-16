<!-- mcp-name: io.github.srclight/model-radar -->
# model-radar

MCP server that pings 219+ free coding LLM models across 21 providers in real-time, ranks them by latency, and helps AI agents pick the fastest available model.

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

## Providers (21)

| Provider | Env Var | Free Tier |
|----------|---------|-----------|
| NVIDIA NIM | `NVIDIA_API_KEY` | Rate-limited, no expiry |
| Groq | `GROQ_API_KEY` | Free tier |
| Cerebras | `CEREBRAS_API_KEY` | Free tier |
| SambaNova | `SAMBANOVA_API_KEY` | $5 credits / 3 months |
| OpenRouter | `OPENROUTER_API_KEY` | 50 req/day on :free models |
| Hugging Face | `HF_TOKEN` | Free monthly credits |
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
| xAI | `XAI_API_KEY` | Free tier |
| Inference.net | `INFERENCE_API_KEY` | Free tier |
| SEA-LION | `SEALION_API_KEY` | Free tier |
| Ollama | `OLLAMA_API_KEY` | Local, free |

## MCP Tools

### Discovery
- **`list_providers()`** — See all 21 providers with config status
- **`list_models(tier?, provider?, min_tier?, free_only?)`** — Browse the model catalog
- **`scan(verify?)`** — Ping models in parallel, ranked by latency. `verify=True` checks for non-empty output.
- **`get_fastest(min_tier?, count?, free_only?, verified?)`** — Best N models right now
- **`get_workers(count?, min_tier?, verified?)`** — N verified-alive models from N distinct providers
- **`provider_status()`** — Per-provider health check

### Execution
- **`run(prompt, model_id?, free_only?)`** — Execute on fastest model with auto-fallback
- **`ask(prompt, count=3)`** — Same prompt on N models in parallel, compare responses
- **`batch_run(prompts, results_file?)`** — Batch execution with incremental JSONL, resume support, adaptive concurrency

### Evaluation (LLM-as-Judge)
- **`judge(prompt, rubric, count=3)`** — Rate a single item with N diverse judges
- **`compare(item_a, item_b, blind=True)`** — Blind A/B comparison, randomized order per judge
- **`batch_judge(items, rubric, results_file?)`** — Evaluate at scale with incremental results
- **`backtranslate_eval(text, translation, source_lang, target_lang)`** — Back-translation quality metric

### Quality & Setup
- **`benchmark(model_id?)`** — Quality-test with 5 coding challenges
- **`refresh_models()`** — Fetch latest model lists from live APIs
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

- [Architecture](docs/architecture.md) — Module map, data flow, transport, rate limiting
- [MCP Transport](docs/mcp-transport.md) — Transport options, stateless HTTP, client configuration
- [Translation Pipeline Playbook](docs/playbook-translation-pipeline.md) — Batch translation patterns
- [LLM-as-Judge Playbook](docs/playbook-llm-as-judge.md) — Evaluation patterns and judge selection

## License

MIT
