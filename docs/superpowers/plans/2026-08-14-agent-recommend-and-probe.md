# Agent recommend + quality probe (v0.11 slice)

**Date:** 2026-08-14  
**Goal:** Make model-radar usable by an agent without a Python harness.

## Jobs we care about

| job | Example |
|-----|---------|
| `translate` | EN→ZH (or review a translation) |
| `rewrite` | Lemma-study sentence, keep meaning, clearer English |
| `review` | Short code-implementation review |

## This slice

1. **`cost_class`**: `zero` / `free_tier` / `subscription` / `local` / `paid` / `unknown`. Persist `is_free` for Ollama + free-tier hosts + paid APIs.
2. **`recommend(job, count)`**: 5–8 live *chat* models, one per provider, no embeddings, no auto CLI.
3. **`quality_probe(job)`**: one fixed prompt per job, time it, pass/fail checks (CJK / rewrite fidelity / named bug).
4. **`ask`**: Ollama sequential; remotes parallel.
5. **`server_stats`**: version + last catalog fetch. MCP instructions use port 8743 / systemd.

## Not this slice

Models.dev, Copilot, Anthropic/OpenAI first-party HTTPS, streaming progress, dollar estimates.
