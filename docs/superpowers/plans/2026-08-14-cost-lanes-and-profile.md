# Cost lanes + funded marker

> **For agentic workers:** Implement in this session. TDD. Do not invent a billing CRM.

**Goal:** Stop treating “has a key” as “safe to call.” Default selection is Lane A. Lane C is opt-in and only if `funded`.

**Architecture:** A tiny `lanes.py` classifies provider/model as A (never invoices), B (subscription CLI), or C (money). Local `~/.model-radar/config.json` `providers.<key>` already exists; add two bits there: `spend_ok` (unprompted paid pick) and `funded` (a paid call would work). No new file, nothing checked in with secrets.

**Spec:** `Vault/Areas/Srclight/Model Radar/2026-08-14-provider-cost-lanes.md`

**Stack:** existing Python package, pytest, FastMCP, click.

## Constraints

- `spend_ok` defaults **false**. Cerebras and MiniMax stay false even though they are funded.
- `funded` is tri-state: `true` / `false` / omitted (`null` = unknown). Lane C with `funded` false or unknown is never selected.
- `free_only` means Lane A, not DB `is_free` (that marks Cerebras free today — wrong for this account).
- Lane B only when `include_subscriptions=True`.
- Lane C only when `include_paid=True` **or** `spend_ok=True`, **and** `funded is True`.
- OpenRouter: `:free` / `-free` → A; other ids → C. Provider row is `mixed`.
- Cloudflare: daily-neuron models → A; Kimi K2.6 / K2.7 / GLM 5.2 → C.
- Do not store balances, cards, or plan names.

## Files

- Create: `src/model_radar/lanes.py`, `tests/test_lanes.py`
- Modify: `cost.py`, `config.py`, `recommend.py`, `scanner.py`, `server.py`, `cli.py`, `config.example.json`, `tests/test_cost.py`, `tests/test_config.py`, `tests/test_recommend.py`, `tests/test_server.py`
- Local only (never commit): `~/.model-radar/config.json`. Identity and wallets: `/mnt/a/srclight/`. Discussion: Vault.

## Tasks

### 1. `lane_for` / `provider_lane`

Lane A keys: `nvidia`, `groq`, `googleai`, `cloudflare`, `sealion`, `ollama`, `codestral`, `sambanova`.
Lane B: CLI providers.
Else Lane C (includes `cerebras`, `minimax`, `together`, …).

### 2. Config flags

`get_provider_flags(cfg, key) -> {enabled, spend_ok, funded}`.
`set_provider_flags(cfg, key, spend_ok=, funded=)` mutates `providers.<key>`, preserves `enabled`.

`model_in_scope(provider, model_id, cfg, free_only=, include_subscriptions=, include_paid=) -> bool`.

### 3. Wire selection

`recommend_models`, `scan_models` (hence `get_fastest` / `run`) drop out-of-scope models. Add `include_paid` to `recommend`.

### 4. Surface

`list_providers` adds `lane`, `spend_ok`, `funded`.
MCP: `profile()`, `set_profile(provider, spend_ok?, funded?)`.
CLI: `model-radar profile` and `model-radar profile set KEY [--funded/--no-funded] [--spend-ok/--no-spend-ok]`.

### 5. Local seed only

Seed `funded` / `login` in `~/.model-radar/config.json` and `/mnt/a/srclight/`. Never commit those values.
