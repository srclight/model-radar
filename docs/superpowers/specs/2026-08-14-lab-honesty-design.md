# Lab honesty — design spec

**Date:** 2026-08-14  
**Status:** approved to implement (user: spec + plan + review + implement)  
**Scope:** model-radar repo only. Items 1–4 of Vault `2026-08-14-next-for-us`.  
**Out of scope:** zhcorpus/strongs `eval_*.py` rewiring (item 5), proxy, new providers, billing CRM, models.dev.

## Goal

An agent starting a Strong’s eval or a lemma rewrite can, without a new Python file:

1. See which of **our Lane A** hosts still answer, cheaply, and how many completion calls that cost.
2. Probe the **dictmaster 5-headword suite**, not just “hi” / one EN→ZH sentence.
3. Judge / back-translate with the **producer excluded**.
4. Treat **402 / 529 / 429** as skip-and-cool, **401** as this key, **404** as refresh catalog (already).

## Context

v0.11 made the wallet honest (lanes, named keys, `in_default_pool`, `credits()`). The lab is still not:

- `scan` / `get_fastest` POST a completion **per model**.
- `quality_probe` jobs are `translate` | `rewrite` | `review` — Paper B’s gate was five headwords.
- `judge` / `backtranslate_eval` can pick the same family that wrote the gloss.
- Scanner maps `>=500` to overloaded (so 529 is ok) but **402 is a generic error**; no 10-minute cooldown.

Vault: `Areas/Srclight/Model Radar/learnings.md`, `2026-08-14-next-for-us.md`, `2026-08-14-zhcorpus-papers-how-we-used-radar.md`.

## Architecture

Four small units. No new dependencies.

| Unit | File | Job |
|------|------|-----|
| Cooldown book | `src/model_radar/cooldown.py` (new) | Process-local: provider → until monotonic, reason. |
| HTTP classify | `scanner.py` + `runner.py` | Shared status set. Record cooldown on 401/402/429/529. |
| Lane A sweep | `src/model_radar/sweep.py` (new) | One cheap ping per in-default-pool Lane A host. |
| Dict probe | `probe.py` | Job `dict` — five Paper B headwords, deterministic checks. |
| Producer exclude | `judge.py`, `runner.backtranslate_eval` | `exclude_providers` / `exclude_model_ids`. |

MCP + CLI are thin wrappers. No private data in repo.

## 1. Cooldown

```python
COOLDOWN_SECONDS = 600  # 10 minutes

class CooldownBook:
    def record(self, provider: str, reason: str, seconds: float = COOLDOWN_SECONDS) -> None: ...
    def is_cooled(self, provider: str, now: float | None = None) -> bool: ...
    def remaining(self, provider: str, now: float | None = None) -> float: ...
    def reason(self, provider: str) -> str | None: ...
    def clear(self, provider: str | None = None) -> None: ...
```

- Process-global default instance `COOLDOWNS` (same lifetime as `ProviderThrottle`).
- Tests construct their own book; never sleep 600s — inject `now`.
- Reasons: `"401"`, `"402"`, `"429"`, `"529"`.
- **401** cools the provider (this key is dead; don’t retry it on the next model).
- **402 / 429 / 529** cool the provider (wallet empty / overloaded).
- **404** does **not** cool (catalog refresh already handles it).
- `scan_models` skips cooled providers (result status `"cooled"` if we need a row; otherwise omit).
- `run_on_fastest` skips cooled providers when walking the up-list.
- `_select_diverse_judges` must not pick a cooled provider (scan skip is enough if judges go through scan).

## 2. HTTP classify

Shared helper in `scanner.py` (imported by runner):

```python
RETRYABLE_HTTP = frozenset({402, 429, 500, 502, 503, 529})

def should_cooldown(status_code: int) -> str | None:
    """Return reason string or None."""
    if status_code in (401, 402, 429, 529):
        return str(status_code)
    return None
```

Ping mapping:

| HTTP | Ping status | Cooldown |
|------|-------------|----------|
| 200/201 | up (body check unchanged) | no |
| 401/403 + key | error / invalid_key | 401 only (403 stays error, no cool — some hosts 403 for geo) |
| 404 | not_found | no |
| 402, 429, 529, >=500 | overloaded | 402, 429, 529 yes; 5xx no (transient; existing throttle is enough) |
| other | error | no |

`run_on_fastest` already tries the next *up* model on any error. After this change, cooled hosts never enter that list for ~10 minutes.

## 3. `still_free` / Lane A sweep

```python
async def still_free(*, ping: bool = True) -> dict: ...
```

Rules:

- Candidates: configured, enabled, `in_default_pool`, `provider_lane` in `{A, mixed}`. Skip CLI (Lane B). Skip Lane C even if `spend_ok`.
- OpenRouter: only ping a **`:free` / `-free`** model. If none in the live catalog, **skip** (do not ping a paid id).
- Prefer a real chat model, better tier first (skip embeddings / ASR / TTS). One completion per provider unless the ping is **404 / not_found** — then try the next candidate, max 3 completions per host. 401/402/429/529 still stop (and cool).
- If the provider is cooled, do **not** ping; row `status="cooled"`, `reason`, `retry_s`.
- `ping=False`: catalog-only rows (`status="listed"`) — zero completion calls.
- OpenRouter `$0` remaining prepaid is **not** a skip. `:free` is supposed to work at $0. Skip only when cooled or no `:free` id.
- Return shape (no secrets):

```json
{
  "completion_calls": 3,
  "skipped": 1,
  "hosts": [
    {"provider": "groq", "lane": "A", "status": "up", "model_id": "…", "latency_ms": 120.0},
    {"provider": "openrouter", "lane": "mixed", "status": "skipped", "reason": "no :free model in catalog"},
    {"provider": "nvidia", "lane": "A", "status": "overloaded", "http": 529, "cooled_s": 600}
  ]
}
```

MCP: `still_free(ping: bool = True)`.  
CLI: `model-radar still-free [--no-ping]`.

Do **not** call `get_fastest` internally.

## 4. Job `dict`

Paper B 5-headword suite, public lexicon facts, no secrets:

| id | headword | must keep |
|----|----------|-----------|
| 110 | 警察报警电话 | china / taiwan / 中国 / 台湾 / 台灣 |
| 119 | 火警 | fire / 火 |
| 11區 | (Code Geass) | 11 or geass or 区 |
| 120 | 急救电话 | ambulance / emergency / 急救 |
| 2019冠狀病毒病 | COVID | covid / 冠状 / 冠狀 / coronavirus |

One prompt: produce compact lines `ID: <short gloss in English>`. Checks (deterministic):

- All five ids (`110`, `119`, `11區` or `11区`, `120`, `2019`) appear.
- 110 geography token present (case-insensitive).
- 2019 has a covid/coronavirus/冠状 token.
- No echo of the instruction sentence “Reply with only numbered glosses”.
- Non-empty after think-tag strip.

`recommend(job="dict")` uses the same hints as `translate`.  
`quality_probe(job="dict")` and CLI `--job dict`. Existing three jobs unchanged.

## 5. Producer ≠ judge

`judge_item(..., exclude_providers: list[str] | None = None, exclude_model_ids: list[str] | None = None)`

- After scan, drop models whose `provider` is in `exclude_providers` or whose `model_id` is in `exclude_model_ids` (exact, case-sensitive id).
- If the pool is empty after exclude, return `{"error": "no judges left after excluding producer", "excluded": ...}`. Do not silently fall back to the producer.
- MCP `judge` and `compare` get the same two optional args.

`backtranslate_eval(..., exclude_providers=..., exclude_model_ids=...)`

- When auto-selecting (`back_model_id` omitted), skip excluded hosts/ids.
- When `back_model_id` is set **and** it is excluded, return an error (do not call the producer).
- Default for MCP: callers pass the producer. No silent default exclude (we do not know the producer). Docs / tool description say: pass the producer.

`compare_items` / `batch_judge_items`: thread the same exclude args through judge selection.

## Testing

TDD. No live network in unit tests.

- Cooldown: record / expire / clear with injected `now`.
- Classify: 402 and 529 → overloaded + cooldown reason; 404 → no cool; 401 → cool.
- Sweep: mock one ping; assert `completion_calls ==` number of uncooled Lane A hosts; OpenRouter without `:free` is skipped; cooled host is not pinged.
- Dict probe: golden pass/fail strings (no API).
- Judge exclude: mock scan returning producer + two others; assert producer absent; empty-after-exclude errors.
- Backtranslate exclude: mocked `run_on_fastest` / `_find_model` not called for excluded id.

## Non-goals

- Changing default `scan` to one-per-provider (sweep is the cheap ritual; `scan` stays for explicit ranking).
- Public status page, telemetry of our keys, rewriting zhcorpus scripts.

## Done when

`pytest` green. MCP `still_free`, `quality_probe(job="dict")`, `judge(..., exclude_providers=["minimax"])`, 402/529 cooldown exist. README MCP list mentions them in one sentence each.
