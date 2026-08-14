# Playbook: Translation Pipeline

Field-tested patterns from running 500K+ LLM translation calls across zhcorpus (428K entries) and Strong's Concordance (19.5K entries x 27 languages).

## Quick Start

### 1. Get a diverse model lineup

```
get_workers(count=5, min_tier="A", verified=True)
```

Returns 5 verified-alive models from 5 distinct providers, ranked by tier then latency. Excludes providers with recent rate limit issues.

### 2. Run batch translation

```
batch_run(
  prompts=[
    {"prompt": "Translate to German: father, head of household", "metadata": {"id": "H1"}},
    {"prompt": "Translate to German: mother, matriarch", "metadata": {"id": "H2"}},
    ...
  ],
  min_tier="A",
  free_only=True,
  concurrency=5,
  retry_on_fail=True,
  results_file="/tmp/translations.jsonl"
)
```

Key features:
- **Incremental JSONL** — each result written immediately, survives crashes
- **Resume support** — re-run with same `results_file` to skip completed items
- **Provider-diverse fallback** — failed items retry on a different provider
- **Adaptive concurrency** — auto-reduces on 429s, recovers on success

### 3. Validate translations

```
backtranslate_eval(
  text="father, head of household",
  translation="Vater, Haupt eines Haushalts",
  source_lang="English",
  target_lang="German"
)
```

Returns gloss overlap score (0.0-1.0), matching/missing/extra glosses. Use a different model for back-translation to avoid circular agreement.

## Known Model Issues

### Think-tag models (Qwen3 class)

Qwen3 32B / Qwen3.5 / MiniMax M3 wrap output in `<think>...</think>` tags, consuming max_tokens on reasoning before producing the answer. Model Radar strips think tags automatically in all tools (`runner.py`, `judge.py`). For a one-line translation use `max_tokens` ≥ 512 or you will get truncated English thinking and an empty translation.

### Reasoning-field models (GPT-OSS / GLM class)

GPT-OSS-120B and Cerebras `zai-glm-4.7` return empty `content` but put output in `message.reasoning`. Model Radar checks both fields transparently. `scan(verify=True)` won't falsely mark these as broken. Local Ollama `glm-4.7-flash` and `qwen3.5:9b` still dump reasoning when the token budget is 128.

### Stale catalog ids

Do not pin last month’s Cerebras/NVIDIA/OpenRouter names. `refresh_models()` first, or let the hourly/404 refresh run. A 404 now refetches that provider and names the current list instead of retrying a retired id.

### Local Ollama vs remotes

Ollama is one GPU — run local models **sequentially**. Remotes (MiniMax, Cerebras, `agy`, `grok`, `codex`) are safe in parallel. A 3B–20B local translate can take 1–5 minutes; the same sentence on MiniMax M3 or Cerebras `gpt-oss-120b` is under 2 seconds.

### Script purity

MiniMax M2.5 produces Korean with Hanja leakage (6.7%), Amharic with stray CJK, Greek with Cyrillic. Use `check_script_purity(text, language)` from `text_utils.py` to detect this:

```python
from model_radar.text_utils import check_script_purity
result = check_script_purity("아버지, 가장父", "ko")
# {"script_pure": False, "unexpected_ratio": 0.125, ...}
```

### Prompt echo

Some models echo back instructions in their output. Use `detect_prompt_echo(content, prompt)` from `text_utils.py`.

## Rate Limit Strategy

- **Never put 2+ judges on the same provider** — correlated rate limits disable all judges simultaneously
- `get_workers()` and `_select_diverse_judges()` enforce provider diversity by default
- `batch_run()` uses adaptive concurrency: starts at requested level, halves on 429s, recovers after 10 successes
- If you're running multiple tools concurrently (judge + translation + scan), they share the same `ProviderThrottle` instance, so backoff is coordinated

## Cost Tracking

`batch_run()` summary includes aggregate token usage:

```json
{
  "usage": {
    "total_prompt_tokens": 1234567,
    "total_completion_tokens": 234567,
    "total_tokens": 1469034
  }
}
```

Free models report $0 cost. For papers, compare with paid pricing to show savings.
