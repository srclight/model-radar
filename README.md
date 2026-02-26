# model-radar

MCP server that pings 130+ free coding LLM models across 17 providers in real-time, ranks them by latency, and helps AI agents pick the fastest available model.

Inspired by [free-coding-models](https://github.com/vava-nessa/free-coding-models).

## Install

```sh
pip install model-radar
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

**Cursor** (`.cursor/mcp.json` in project root or `~/.cursor/mcp.json`):
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

**OpenClaw** (`~/.openclaw/openclaw.json`):
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

### 3. CLI usage

```sh
# Scan models
model-radar scan --min-tier S --limit 10

# List providers
model-radar providers

# Save a key
model-radar configure nvidia nvapi-xxx
```

## Providers (17)

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
| Codestral | `CODESTRAL_API_KEY` | 30 req/min, 2000/day |
| Hyperbolic | `HYPERBOLIC_API_KEY` | $1 free trial |
| Scaleway | `SCALEWAY_API_KEY` | 1M free tokens |
| Google AI | `GOOGLE_API_KEY` | 14.4K req/day |
| SiliconFlow | `SILICONFLOW_API_KEY` | Free model quotas |
| Together AI | `TOGETHER_API_KEY` | Credits vary |
| Cloudflare | `CLOUDFLARE_API_TOKEN` | 10K neurons/day |
| Perplexity | `PERPLEXITY_API_KEY` | Tiered limits |

## MCP Tools

- **`list_providers()`** — See all 17 providers with config status
- **`list_models(tier?, provider?, min_tier?)`** — Browse the model catalog
- **`scan(tier?, provider?, min_tier?, configured_only?, limit?)`** — Ping models in parallel, ranked by latency
- **`get_fastest(min_tier?, provider?, count?)`** — Quick: best N models right now
- **`provider_status()`** — Per-provider health check
- **`configure_key(provider, api_key)`** — Save an API key

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

## License

MIT
