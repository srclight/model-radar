# Lab honesty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cheap Lane A sweep, Paper B dict probe, producer-excluded judges, and 402/529 cooldown — so our agents can run the lab without cooking quotas or grading MiniMax with MiniMax.

**Architecture:** New `cooldown.py` and `sweep.py`; classify HTTP in `scanner.py`; thread exclude lists through `judge.py` and `backtranslate_eval`; add `dict` job to `probe.py` / `recommend.py`. MCP + CLI wrappers only.

**Tech Stack:** Python 3.12, pytest, existing httpx scanner, no new deps.

**Spec:** `docs/superpowers/specs/2026-08-14-lab-honesty-design.md`

## Global Constraints

- No private data (emails, balances, login values, keys) in repo.
- No live network in unit tests.
- TDD: failing test first for each unit.
- Default pool remains Lane A; Lane C stays `spend_ok`-gated.
- Do not change `scan` into a one-per-provider sweep — `still_free` is that ritual.

## Files

| File | Role |
|------|------|
| `src/model_radar/cooldown.py` | Process-local cooldown book |
| `src/model_radar/sweep.py` | `still_free()` |
| `src/model_radar/scanner.py` | classify HTTP, skip cooled, record cooldown |
| `src/model_radar/runner.py` | record cooldown; backtranslate exclude |
| `src/model_radar/probe.py` | job `dict` |
| `src/model_radar/recommend.py` | job `dict` aliases translate hints |
| `src/model_radar/judge.py` | exclude_providers / exclude_model_ids |
| `src/model_radar/server.py` | MCP tools |
| `src/model_radar/cli.py` | `still-free`, `--job dict` |
| `tests/test_cooldown.py` | new |
| `tests/test_sweep.py` | new |
| `tests/test_probe.py` | dict cases |
| `tests/test_judge.py` | exclude |
| `tests/test_scanner.py` | 402/529 |
| `tests/test_runner.py` | exclude backtranslate |
| `tests/test_server.py` | tool wiring if existing pattern |
| `README.md` | one line each |

---

### Task 1: Cooldown book

**Files:** Create `src/model_radar/cooldown.py`, `tests/test_cooldown.py`

**Produces:** `CooldownBook`, `COOLDOWNS`, `COOLDOWN_SECONDS = 600`

- [ ] Failing tests for record / expire / clear / remaining
- [ ] Implement
- [ ] Commit

### Task 2: HTTP classify + scanner/runner cooldown

**Files:** `scanner.py`, `runner.py`, `tests/test_scanner.py`, `tests/test_runner.py`

**Produces:** `RETRYABLE_HTTP`, `should_cooldown(status_code) -> str | None`

- [ ] Tests: 402/529 → overloaded + cool; 404 → no cool; 401 → cool
- [ ] `scan_models` skips cooled providers
- [ ] `_call_model` records cooldown on 401/402/429/529
- [ ] Commit

### Task 3: `still_free`

**Files:** Create `sweep.py`, `tests/test_sweep.py`; MCP + CLI

**Produces:** `async def still_free(*, ping: bool = True) -> dict`

- [ ] Tests with mocked ping / config
- [ ] Implement + `still_free` tool + `model-radar still-free`
- [ ] Commit

### Task 4: Job `dict`

**Files:** `probe.py`, `recommend.py`, `tests/test_probe.py`, CLI/MCP choice lists

- [ ] Golden pass/fail tests
- [ ] Five-headword prompt + checks
- [ ] Commit

### Task 5: Producer exclude

**Files:** `judge.py`, `runner.py`, `server.py`, tests

**Produces:** `exclude_providers`, `exclude_model_ids` on judge / compare / batch_judge / backtranslate

- [ ] Tests: producer dropped; empty-after-exclude errors; explicit excluded back_model_id errors
- [ ] Implement
- [ ] Commit

### Task 6: Docs + full suite

- [ ] README MCP list
- [ ] `pytest` full suite green
- [ ] Commit

## Spec coverage

| Spec section | Task |
|--------------|------|
| Cooldown book | 1 |
| HTTP classify + scan/run | 2 |
| still_free | 3 |
| dict probe | 4 |
| producer ≠ judge | 5 |
| README | 6 |
| zhcorpus scripts | out of scope |

## Plan review (self)

- No TBD placeholders.
- Types: `exclude_providers: list[str] | None`, `exclude_model_ids: list[str] | None`, `still_free(ping: bool) -> dict`.
- OpenRouter skip = no `:free` id, not `$0` credits (matches spec).
- 403 does not cool (matches spec).
