# Benchmarking

Run quality benchmarks across models, interpret results, and update quality scores.

## When to Use

When you need to evaluate model quality (e.g., after adding new models, comparing providers, or auditing the tier assignments).

## Steps

### 1. Select models to benchmark

```
get_fastest(min_tier="A", count=10, verified=True)
```

Or target specific models:
```
scan(provider="nvidia", verify=True)
```

### 2. Run the benchmark

Via MCP:
```
benchmark(min_tier="A", provider="nvidia")
```

Or for a specific model:
```
benchmark(model_id="nvidia/llama-3.1-nemotron-ultra-253b-v1")
```

The benchmark runs 5 coding challenges and scores pass/fail. Results are stored in the quality database (~/.model-radar/quality.json) and affect future `get_fastest()` rankings.

### 3. Interpret results

Quality scores are 0-5 (number of challenges passed):
- **5/5**: Excellent -- reliable for coding tasks
- **4/5**: Good -- minor issues, generally usable
- **3/5**: Acceptable -- may struggle with complex tasks
- **2/5 or below**: Avoid for coding -- consider downgrading tier

### 4. Cross-validate with judge evaluation

For deeper quality assessment, use LLM-as-judge:

```
judge(
  prompt="Write a Python function that finds the longest common subsequence of two strings",
  rubric=["correctness", "efficiency", "code_quality"],
  scale="1-5",
  count=3
)
```

See `docs/playbook-llm-as-judge.md` for full evaluation patterns.

### 5. Update tier assignments if needed

If benchmark results consistently disagree with the assigned tier:
1. Check SWE-bench Verified for updated scores
2. Update the `tier` field in `src/model_radar/providers.py`
3. Run tests to ensure no tier validation failures

### 6. Batch benchmark for comprehensive audit

To benchmark all models from a provider:
```
scan(provider="provider_key", verify=True)
benchmark(provider="provider_key")
```

To benchmark across all configured providers:
```
benchmark(min_tier="B")
```

## Interpreting Benchmark vs Tier Disagreements

| Benchmark | Tier | Action |
|-----------|------|--------|
| 5/5 | B or lower | Check SWE-bench, consider upgrade |
| 0-2/5 | A or higher | May be a flaky model, re-run. If consistent, downgrade |
| 3-4/5 | matches tier | No action needed |

## Checklist

- [ ] Models selected (verified alive first)
- [ ] Benchmark run completed
- [ ] Results interpreted (scores + tier alignment)
- [ ] Tier adjustments made if needed (in providers.py)
- [ ] Tests pass after any tier changes
