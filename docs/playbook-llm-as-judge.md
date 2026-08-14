# Playbook: LLM-as-Judge Evaluation

Field-tested patterns from running 10K+ evaluation calls across translation quality assessment and content comparison tasks.

## Tools

### Single item evaluation

```
judge(
  prompt="Rate this German translation of 'father, head of household': 'Vater, Haupt eines Haushalts'",
  rubric=["accuracy", "naturalness", "completeness"],
  scale="1-5",
  count=3
)
```

Returns aggregate scores, per-judge details, and inter-rater agreement (stdev when 3+ judges).

### A/B comparison

```
compare(
  item_a="Vater, Haupt eines Haushalts",
  item_b="Vater, Oberhaupt des Haushalts",
  context="Translation of 'father, head of household' to German",
  dimensions=["accuracy", "naturalness"],
  judge_count=3,
  blind=True
)
```

When `blind=True` (default), randomizes A/B order per judge to prevent position bias.

### Batch evaluation

```
batch_judge(
  items=[
    {"prompt": "Rate this translation: ...", "metadata": {"lang": "de", "id": "H1"}},
    {"prompt": "Rate this translation: ...", "metadata": {"lang": "fr", "id": "H1"}},
    ...
  ],
  rubric=["accuracy", "naturalness", "completeness"],
  concurrency=5,
  results_file="/tmp/eval_results.jsonl"
)
```

Key features:
- **Incremental JSONL** — each scored item written immediately
- **Resume support** — re-run with same file to skip completed items
- **Summary statistics** — mean, stdev, min, max per dimension

## Judge Selection

Judges are auto-selected with provider diversity:

1. Scan for available models at `min_tier` or better
2. Pick `count` models from distinct providers (round-robin by provider)
3. Skip providers flagged as degraded (recent 429s)

This prevents correlated failures: if SambaNova gets rate-limited, you don't lose 2/3 judges.

### Manual judge selection

For reproducibility, specify exact models:

```
run(prompt="Rate on a scale of 1-5: ...", model_id="moonshotai/kimi-k2-instruct", provider="siliconflow")
```

## Output Formats

### CSV (default, recommended)

Judges output: `4,5,3` (one number per rubric dimension).
- Fastest to parse
- Most reliable structured output
- Works with think-tag models (tags stripped before parsing)

### JSON

Judges output: `{"accuracy": 4, "naturalness": 5, "completeness": 3}`
- More readable in results
- Slightly higher parse failure rate

## Common Failures

### Think-tag models waste tokens

Qwen3 32B responds to "Output ONLY three numbers: 4,5,3" with `<think>Okay, let's tackle this...` and hits max_tokens. Model Radar strips think tags automatically before parsing scores.

### Empty content from reasoning models

GPT-OSS-120B puts scores in `message.reasoning` instead of `message.content`. The judge pipeline checks both fields.

### Rate limit cascade

Running judge eval + translation expansion + scan concurrently exceeds provider limits. The shared `ProviderThrottle` coordinates backoff across all tools, but for heavy workloads:
- Stagger tool calls (don't run judge + batch_run simultaneously)
- Use `get_workers()` to pre-select models and pass explicit `model_id` to avoid redundant scans

## Recommended Judge Models

Based on 10K+ evaluation calls:

| Model | Provider | Strengths |
|-------|----------|-----------|
| Kimi K2 | SiliconFlow | Reliable, fast, consistent structured output |
| Qwen3 235B | Cerebras | Different model family, good diversity |
| Llama 4 Scout | Groq/NVIDIA | Different perspective, fast on Groq |
| DeepSeek V3.1 | Fireworks | Strong reasoning, different training data |

Use 3 judges from 3 different providers for best inter-rater independence.
