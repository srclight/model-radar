# CLI Subscriptions — Phase 2 (correctness + Claude + named compare)

> **For agentic workers:** this is the next slice of `docs/superpowers/specs/2026-08-14-grok-gemini-cli-providers-design.md` (Phase 1 landed as v0.8.0). Do not treat this as a second product.

**Why CLI exists:** people already pay for SuperGrok, Claude Pro/Max, Google Workspace Gemini, or ChatGPT Plus/Pro. model-radar should ride those subscriptions so `ask` / `review` / `compare` do not require a separate API key or pay-as-you-go credits.

**Goal:** Make the existing Grok/Gemini CLI path actually usable, add Claude (and Codex if installed) the same way, and let a host pin those subscriptions by name for a parallel review.

**Architecture:** HTTPS keys stay the default for free-tier hosts. CLI is a second *access method* for a vendor (`xai` vs `grok`, `anthropic` vs `claude`), registered only when the binary is on PATH. Auto-pick (`get_fastest`, default `ask`, `get_workers`) never silently spends a subscription — CLI is opt-in via `model_ids` or `providers=["claude","grok"]`.

**Tech Stack:** Existing (httpx, FastMCP, asyncio subprocess). No new dependencies.

**Related:** `docs/superpowers/specs/2026-08-14-grok-gemini-cli-providers-design.md` (Phase 1, landed as v0.8.0). This plan is the next slice.

**Current version:** 0.9.0 on `develop` (Phase 2 subscription slice implemented in this working tree; not yet committed).

**Implemented in this slice:** CLI counts as configured; `-p` headless spawn + temp cwd; grok-4.6/4.5; Claude (and Codex if on PATH); `ask(model_ids=…, providers=…)`; auto-pick never spends a subscription; setup guides for grok/gemini/claude/codex.

---

## Status as of 2026-08-14

### What already works

| Capability | Where | Notes |
|---|---|---|
| 21 HTTPS providers, 219 static models | `providers.py` | NVIDIA, Groq, Cerebras, SambaNova, OpenRouter, HF, Replicate, DeepInfra, Fireworks, Mistral, Hyperbolic, Scaleway, Google AI, SiliconFlow, Together, Cloudflare, xAI, Inference.net, SEA-LION, Ollama, Perplexity |
| API key store | `~/.model-radar/config.json` + env vars | 19/21 keys configured on this machine. Missing: `xai`, `perplexity` |
| Setup wizard | `setup_guide`, `setup_workflow`, `configure_key` | Guides exist for 12 providers. Missing for CLI, xAI, OpenAI, Anthropic, DeepSeek, Cloudflare, etc. |
| Parallel same-prompt | `ask()` / `ask_models()` | Auto-picks fastest UP models. **Cannot pin models.** |
| Parallel batch | `batch_run()` | JSONL + resume |
| LLM-as-judge | `judge()`, `compare()`, `batch_judge()` | Diverse judges, blind A/B. Also cannot pin judge model ids. |
| Live catalog refresh | `provider_sync.py` | OpenRouter, NVIDIA, Groq, Cerebras, SambaNova, SiliconFlow, HF, xAI, Google AI. Runs on server startup. |
| CLI kind (`kind="cli"`) | `cli_provider.py` + scanner/runner dispatch | v0.8.0. Detects `grok` and `gemini` on PATH. |

This machine already has: `grok` (logged in, models `grok-4.6` / `grok-4.5`), `gemini`, `claude` 2.1.232. `codex` is not installed. `openai` on PATH is the Python SDK CLI (needs `OPENAI_API_KEY`), not a ChatGPT-subscription rider.

### What v0.8.0 shipped — and what is still broken

The Grok/Gemini CLI work is committed but not yet *usable* as a comparison backend:

1. **CLI providers are never "configured."** `get_configured_providers()` requires `get_api_key()`. CLI providers have `env_vars=()` and no key, so `ask()`, `run()`, `get_fastest()`, `get_workers()`, and `judge()` all pass `configured_only=True` and skip them.
2. **Wrong grok/gemini invocation.** Real flags:
   - Grok: `grok -p "<prompt>" -m <model> --output-format json` (and should deny tools).
   - Gemini: `gemini -p "<prompt>" -m <model> --output-format json`.
   - Current code appends the prompt as a trailing positional and does **not** pass `-p`/`--single`. That starts an interactive session or hangs.
3. **Stale CLI catalog.** Hardcoded `grok-4` / `grok-3` / `grok-3-mini`. Live `grok models` is `grok-4.6` (default) and `grok-4.5`.
4. **Ping is `--version` only.** A binary that exists looks "up" instantly and will dominate latency rankings if it ever enters the pool.
5. **Running MCP process is stale.** Live `list_providers()` still reports 21 providers / 219 models and no `grok`/`gemini`. The in-process server has not been restarted onto 0.8.0.
6. **README / `configure_key` docstring / architecture.md** still say "21 providers" and do not mention CLI. Plan Task 11 (README) was not done.

The 2026-08-14 design spec explicitly parked `claude`, `codex`, and `aider` as out of scope. That is the work this plan covers.

### Coverage gaps vs the goal

**Missing first-party HTTPS providers (the ones users actually have subscriptions/keys for):**

| Vendor | Why it matters | Free? | Status |
|---|---|---|---|
| Anthropic | Claude Opus/Sonnet/Haiku — needed for writing reviews | Paid (small console credits) | **Absent** |
| OpenAI | GPT-4.1 / 5 / o-series | Paid (and some free via other hosts) | **Absent** as a provider. Only `openai/gpt-oss-*` on other hosts. |
| DeepSeek official | Cheap/free-ish frontier coder | Yes (low cost + often free) | Only via NVIDIA/Fireworks/etc. |
| xAI API | Grok via pay-as-you-go | Key missing; account `ACTIVE_NO_BILLING` | Defined, unused |
| Perplexity | Sonar | Key missing | Defined, unused |

**Missing CLI subscription riders:**

| Binary | On this machine | Rides | Status |
|---|---|---|---|
| `grok` | yes, logged in | SuperGrok | Registered, invocation + configured-check broken |
| `gemini` | yes | Google Workspace | Same |
| `claude` | yes (2.1.232) | Claude Pro/Max | Not registered |
| `codex` | no | ChatGPT Plus/Pro | Not registered |
| `openai` CLI | yes | Requires API key | Do **not** treat as a subscription CLI |

**Setup-guide holes:** no guides for `xai`, `perplexity`, `ollama`, `inferencenet`, `sealion`, `replicate`, `hyperbolic`, `scaleway`, `cloudflare`, or any CLI. `setup_guide()` currently returns `unconfigured: []` because the remaining HTTPS providers have no guide entries.

**Compare/review holes:**

- `ask()` cannot take `model_ids=["claude-opus", "grok-4.6", "gpt-4.1"]`.
- `ask()` cannot take `providers=["claude", "grok", "openai"]`.
- `judge()` / `compare()` cannot pin judges either.
- There is no first-class `review()` tool. The playbook says "call `run()` per model," which is serial and loses the point of parallel reviews.

---

## Recommended design

### Decision 1 — Dual access, not dual identity

Each vendor can have **two** providers:

| HTTPS (API key) | CLI (subscription) |
|---|---|
| `xai` | `grok` |
| `googleai` | `gemini` |
| `anthropic` (new) | `claude` (new) |
| `openai` (new) | `codex` (new, if installed) |

They stay separate keys so `get_workers()` can still enforce provider diversity, and so a missing API key does not hide a working subscription (or vice versa). Labels must say `(API)` vs `(Subscription)`.

Do **not** merge them into one provider with two transports. That would break "N models from N providers" and make config confusing.

### Decision 2 — CLI means single-turn completion, not an agent

model-radar is a completion/compare engine. Spawned CLIs must not read the repo, run tools, or start a TUI.

Required spawn profile (per CLI):

| CLI | Headless | Model | JSON | Isolation |
|---|---|---|---|---|
| `grok` | `-p` / `--single` | `-m` | `--output-format json` | `--permission-mode plan` or `--tools ""`, `--verbatim`, `--cwd` temp dir |
| `gemini` | `-p` | `-m` | `--output-format json` | `--approval-mode plan`, temp cwd |
| `claude` | `-p` / `--print` | `--model` | `--output-format json` | `--bare --tools "" --permission-mode plan`, temp cwd |
| `codex` | print/exec mode (confirm at implement time) | model flag | json if available | no-tools + temp cwd |

Timeouts: 120s default for CLI (subscription models are slower than Groq). Ping must be a real 1-token completion, not `--version`, or CLI providers must be excluded from `get_fastest()` latency ranking.

Parser: keep one `_extract_response_text` and add a Claude shape (`result`, `result.text`, or the existing `response`/`choices` walk). Add a golden-fixture per CLI from a real `-p` capture.

### Decision 3 — "Configured" means usable

Change `get_configured_providers()`:

```
configured =
    enabled
    AND (
      kind=="https" AND api_key present
      OR kind=="cli" AND shutil.which(cmd) AND (optional auth probe cached)
    )
```

Add `ollama` and CLI keys to a `_NO_KEY_PROVIDERS` (or `kind`-based) set. `list_providers()` should return `kind`, `access` (`api_key` | `cli` | `local`), `installed`, `configured`.

### Decision 4 — Named-model compare is the review feature

Do not invent a separate review product. Extend the tools that already exist:

```
ask(prompt, model_ids=["claude-opus-4-6", "grok-4.6", "gpt-4.1"], system_prompt=REVIEW_RUBRIC)
ask(prompt, providers=["claude", "grok", "openai", "gemini"], count=4)
```

Add an optional thin wrapper:

```
review(text, rubric?, model_ids?, providers?, count=4)
```

that is just `ask()` with a default writing-review system prompt (clarity, structure, claims, voice). Hosts like lemma-review-gauntlet can pass their own `system_prompt` and skip `review()`.

Same `model_ids` argument on `judge()` / `compare()` so writing reviews can pin Claude + Grok + GPT as judges.

### Decision 5 — Catalog policy: free-first, first-party complete, live-fetch the rest

Do **not** hand-curate every model on every host. Policy:

1. Static catalog keeps a **seed** of known-good free + first-party models (what we have now, plus Anthropic/OpenAI/DeepSeek).
2. `refresh_models_from_live()` is the source of truth for anything with a `/v1/models` (or vendor equivalent). Expand the fetcher list to every OpenAI-compatible provider we already have a key for (Together, Fireworks, Mistral, DeepInfra, Hyperbolic, Scaleway, Inference.net, …) using the existing `_fetch_openai_compatible_models`.
3. CLI model lists come from the CLI itself when possible (`grok models`, `claude /model` list if available) and fall back to a small static seed.
4. `is_free` stays derived from pricing / `:free` / subscription-kind. Subscription CLI models are `is_free=True` (free *to the user*).

### Decision 6 — Setup guides for every provider, including CLI

`setup_guide(provider?)` must never say "no guide yet." Every `PROVIDERS` entry gets a guide:

- HTTPS: signup URL, 3-step key instructions, env var, key prefix, free-tier one-liner, `configure_key(...)`.
- CLI: install command, `login` command, how to verify (`grok models`, `claude --version`), no API key required.

`setup_workflow` step 2 should list unconfigured *HTTPS and CLI* together, marked `access: api_key | cli`.

Priority order for the host to recommend:

1. NVIDIA, Groq, Google AI Studio (best free HTTPS)
2. Any CLI already on PATH (`claude`, `grok`, `gemini`)
3. OpenRouter (many `:free` models)
4. Anthropic / OpenAI keys if the user wants pay-as-you-go first-party
5. Everything else

---

## Out of scope

- Playwright scraping of web UIs (already parked; TOS-fragile).
- Treating Cursor / Copilot / `openai` SDK CLI as subscription backends.
- Aider, Open Interpreter as providers (they are agents, not model access).
- Periodic refresh loops (startup + explicit `refresh_models()` is enough).
- Billing / spend tracking beyond existing usage fields.
- Changing MCP transport or adding dependencies.

---

## Phased plan

### Phase 0 — Make the existing CLI path actually work (v0.8.1)

Correctness fix for what just landed. No new vendors.

**Files:** `config.py`, `cli_provider.py`, `scanner.py`, `guides.py`, tests.

- [ ] Treat `kind=="cli"` as configured when `shutil.which(cmd)` is true. Add tests that `get_configured_providers()` includes `grok` when the binary is mocked on PATH and excludes it when not.
- [ ] Fix spawn args:
  - grok: `["grok", "-p", prompt, "-m", model_id, "--output-format", "json", "--permission-mode", "plan", "--verbatim"]`
  - gemini: `["gemini", "-p", prompt, "-m", model_id, "--output-format", "json", "--approval-mode", "plan"]`
  - `cwd` = `tempfile.mkdtemp(prefix="mr-cli-")` so the CLI cannot see the model-radar repo.
- [ ] Replace hardcoded grok models with `grok-4.6`, `grok-4.5` (keep older ids only if `grok models` still lists them).
- [ ] CLI ping: run the same headless command with prompt `"hi"` and `max_tokens`-equivalent if the CLI has one; 8s timeout. `--version` is install-detect only, not latency.
- [ ] Exclude CLI providers from `get_fastest()` default ranking (or rank them after HTTPS). They are for *named* compare, not "fastest free coder."
- [ ] Restart the running MCP server and confirm `list_providers()` shows `grok` / `gemini` with `kind=cli`, `configured=true`.
- [ ] Manual: `ask("Reply with the word ping.", providers="grok")` returns JSON text within 120s.

### Phase 1 — CLI registry + Claude (and Codex if present) (v0.9.0)

Turn `register_cli_providers()` into a table so adding a CLI is data.

**Files:** `cli_provider.py`, `providers.py`, `guides.py`, `tests/test_cli_provider.py`.

```python
CLI_SPECS = (
    CliSpec(
        key="grok", name="Grok (Subscription)", cmd="grok",
        model_flag="-m", prompt_flag="-p",
        extra_args=("--output-format", "json", "--permission-mode", "plan", "--verbatim"),
        models=(("grok-4.6", "Grok 4.6 (Subscription)", "S+", "72.0%", "256k"),
                ("grok-4.5", "Grok 4.5 (Subscription)", "S+", "70.0%", "256k")),
        login_hint="grok login",
        install_url="https://docs.x.ai/build/overview",
    ),
    CliSpec(
        key="gemini", name="Gemini (Subscription)", cmd="gemini",
        model_flag="-m", prompt_flag="-p",
        extra_args=("--output-format", "json", "--approval-mode", "plan"),
        models=(("gemini-2.5-pro", ...), ("gemini-2.5-flash", ...), ("gemini-2.5-flash-lite", ...)),
        login_hint="gemini auth login",
        install_hint="npm install -g @google/gemini-cli",
    ),
    CliSpec(
        key="claude", name="Claude (Subscription)", cmd="claude",
        model_flag="--model", prompt_flag="-p",
        extra_args=("--print", "--output-format", "json", "--bare", "--tools", "",
                    "--permission-mode", "plan"),
        models=(("opus", "Claude Opus (Subscription)", "S+", "72.0%", "200k"),
                ("sonnet", "Claude Sonnet (Subscription)", "S", "65.0%", "200k"),
                ("haiku", "Claude Haiku (Subscription)", "A+", "50.0%", "200k")),
        login_hint="claude auth login  (or existing Claude Code login)",
        install_url="https://docs.anthropic.com/en/docs/claude-code",
    ),
    CliSpec(
        key="codex", name="Codex (Subscription)", cmd="codex",
        # flags confirmed at implement time from `codex --help`
        ...
    ),
)
```

- [ ] `register_cli_providers()` walks `CLI_SPECS` and registers each `cmd` found on PATH.
- [ ] Parser fixtures: one captured JSON blob per CLI (`tests/fixtures/cli_grok.json`, `cli_gemini.json`, `cli_claude.json`).
- [ ] Auth-error mapping: if stderr contains `login` / `not authenticated` / `unauthorized`, raise `CLIProviderError` that names the exact login command.
- [ ] Guides for `grok`, `gemini`, `claude`, `codex`.
- [ ] `list_providers()` includes `kind` and `installed`.
- [ ] Manual: `ask("2+2?", model_ids=["sonnet", "grok-4.6", "gemini-2.5-flash"])`.

Codex is registered only if installed; no requirement to install it in this phase.

### Phase 2 — First-party HTTPS: Anthropic, OpenAI, DeepSeek (v0.9.0, same release if small)

These are the paid/official APIs the user asked about ("gpt, more?"). They sit next to the CLI riders.

**Files:** `providers.py`, `provider_sync.py`, `guides.py`, `endpoints.py`, `server.py` (`configure_key` docstring), `config.example.json`, tests.

```python
_p("anthropic", "Anthropic", "https://api.anthropic.com/v1/messages",
   ("ANTHROPIC_API_KEY",), (
    ("claude-opus-4-6", "Claude Opus 4.6", "S+", "72.0%", "200k"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6", "S", "65.0%", "200k"),
    ("claude-haiku-4-5", "Claude Haiku 4.5", "A+", "50.0%", "200k"),
), api_style="anthropic")  # NOT OpenAI-compatible

_p("openai", "OpenAI", "https://api.openai.com/v1/chat/completions",
   ("OPENAI_API_KEY",), (
    ("gpt-4.1", "GPT-4.1", "S+", "70.0%", "1M"),
    ("gpt-4.1-mini", "GPT-4.1 Mini", "S", "60.0%", "1M"),
    ("o4-mini", "o4-mini", "S", "60.0%", "200k"),
    ("gpt-4o", "GPT-4o", "S", "60.0%", "128k"),
))

_p("deepseek", "DeepSeek", "https://api.deepseek.com/chat/completions",
   ("DEEPSEEK_API_KEY",), (
    ("deepseek-chat", "DeepSeek Chat", "S+", "73.1%", "128k"),
    ("deepseek-reasoner", "DeepSeek Reasoner", "S+", "73.1%", "128k"),
))
```

Anthropic Messages API is the one non-OpenAI wire format. Handle it in `runner.py` / `scanner.py` the same way Replicate is already special-cased (`api_style="anthropic"`): `x-api-key` header, `anthropic-version`, `{model, max_tokens, messages}` body, content from `content[0].text`.

- [ ] Live fetch: `GET https://api.anthropic.com/v1/models`, `GET https://api.openai.com/v1/models`, `GET https://api.deepseek.com/models`.
- [ ] Guides with exact console URLs:
  - Anthropic: https://console.anthropic.com/settings/keys
  - OpenAI: https://platform.openai.com/api-keys
  - DeepSeek: https://platform.deepseek.com/api_keys
- [ ] `configure_key` accepts the new keys. Docstring lists them.
- [ ] Do **not** mark these `is_free=True`. `free_only=True` continues to hide them.

Confirm current Anthropic / OpenAI model ids at implement time from the live list endpoint (ids above are seeds).

### Phase 3 — Named-model compare and review (v0.9.0 / v0.10.0)

**Files:** `consensus.py`, `judge.py`, `server.py`, `cli.py`, playbook, tests.

```python
async def ask_models(
    prompt: str,
    ...,
    model_ids: list[str] | None = None,
    providers: list[str] | None = None,  # OR keep single `provider` and add `providers`
) -> dict:
```

Selection rules:

1. If `model_ids` is set, resolve each id (must be unique or take an optional `provider=` / `provider:model` form `claude/sonnet`). Skip scan. Fail a missing id loudly, do not silently substitute.
2. Else if `providers` is set, pick the best UP model per listed provider (tier, then latency).
3. Else today's behavior (fastest `count` at `min_tier`).

Same `model_ids` / `providers` on `judge_item` and `compare_items`.

Optional wrapper:

```python
async def review(text: str, rubric: list[str] | None = None, **ask_kwargs) -> dict:
    system = default_writing_review_prompt(rubric or DEFAULT_RUBRIC)
    return await ask_models(prompt=text, system_prompt=system, **ask_kwargs)
```

Default rubric: `clarity`, `structure`, `evidence`, `voice`, `actionability`. Keep it short; lemma/gauntlet hosts will pass their own system prompt.

- [ ] MCP: `ask(..., model_ids?, providers?)`, `review(...)`, `judge(..., model_ids?)`, `compare(..., model_ids?)`.
- [ ] CLI: `model-radar ask -P "..." --models claude/sonnet,grok/grok-4.6,openai/gpt-4.1`.
- [ ] Playbook section: "Send a writing review to Claude + Grok + GPT at once."
- [ ] Tests: pinned ids are the ones called; unknown id returns a structured error; provider list yields ≤1 model per provider.

### Phase 4 — Setup completeness + live fetch for every keyed host (v0.10.0)

**Files:** `guides.py`, `setup_workflow.py`, `provider_sync.py`, `README.md`, `docs/architecture.md`, `CLAUDE.md`.

- [ ] A `_GUIDES` entry for every key in `PROVIDERS`. Delete `_NO_GUIDE`.
- [ ] CLI guides include install + login + verify.
- [ ] `setup_guide()` with no args lists unconfigured HTTPS *and* missing CLIs, sorted HIGH → LOW.
- [ ] Expand `all_fetchable` to every OpenAI-compatible provider that already has a fetcher helper or can use `_fetch_openai_compatible_models` (together, fireworks, codestral, deepinfra, hyperbolic, scaleway, inferencenet, ollama).
- [ ] README: provider table includes Anthropic/OpenAI/DeepSeek and a "CLI subscriptions" subsection. Counts stop being hardcoded "21."
- [ ] `list_providers` / server blurb use `len(PROVIDERS)` instead of "21."

### Phase 5 — Verify end-to-end on this machine

This is the acceptance run, not more code.

```
# restart MCP
model-radar serve --transport sse --port 8743 --web

list_providers()
  → grok, gemini, claude present; kind=cli; configured=true
  → anthropic/openai/deepseek present; api_key missing until configured

setup_guide()
  → xai, perplexity, anthropic, openai, claude, grok all have steps

ask(prompt=<short review>, model_ids=["sonnet", "grok-4.6", "gemini-2.5-flash"])
  → 3 responses, no hang, no repo files touched (confirm cwd isolation)

review(text=<paragraph>, providers=["claude", "grok", "gemini"])
  → same, with default rubric

configure_key("anthropic", ...) / configure_key("openai", ...)
  → ask(..., providers=["anthropic", "openai", "claude"]) uses API for the first two and CLI for the third
```

Browser: dashboard CLI section lists installed binaries and a Refresh button (already added in v0.8.0; confirm it shows `claude` after Phase 1).

---

## File map (what changes, by phase)

| File | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| `src/model_radar/config.py` | configured=usable | | | | |
| `src/model_radar/cli_provider.py` | spawn flags, ping, models | `CLI_SPECS` + claude/codex | | | |
| `src/model_radar/providers.py` | grok model ids | register from specs | anthropic/openai/deepseek | | |
| `src/model_radar/scanner.py` | real CLI ping | | anthropic wire | | |
| `src/model_radar/runner.py` | | | anthropic wire | | |
| `src/model_radar/consensus.py` | | | | `model_ids`/`providers` | |
| `src/model_radar/judge.py` | | | | pin judges | |
| `src/model_radar/server.py` | list kind | claude in tools | configure_key docs | `review` tool | drop "21" |
| `src/model_radar/guides.py` | grok/gemini | claude/codex | anthropic/openai/deepseek | | fill remaining |
| `src/model_radar/provider_sync.py` | | optional `grok models` | 3 new fetchers | | all keyed hosts |
| `src/model_radar/endpoints.py` | | | anthropic base_url | | |
| `README.md` / `docs/architecture.md` | | | | | counts + CLI section |
| `tests/test_cli_provider.py` | spawn/configured | specs + fixtures | | | |
| `tests/test_consensus.py` | | | | pinned ask | |
| `tests/test_guides.py` | | | | | every provider has a guide |

---

## Risks

| Risk | Mitigation |
|---|---|
| Agent CLIs touch the repo or run tools | temp cwd + `--bare` / `--tools ""` / `--permission-mode plan` |
| Claude/Grok JSON shape changes | one parser, fixtures from real captures |
| Subscription quota burn from pings | CLI excluded from `get_fastest()`; ping rarely; never `verify=True` on a full CLI catalog scan by default |
| Anthropic Messages API special case | isolate behind `api_style`, test with a recorded payload |
| Model ids rot (already happened for grok) | live fetch + CLI `models` command; static list is a seed |
| Dual Claude (API + CLI) confuses hosts | distinct keys + labels; `ask(providers=["claude"])` is subscription, `ask(providers=["anthropic"])` is key |
| 60s timeout too short | 120s CLI default; `ask` already returns per-model errors |

---

## Suggested release cut

- **0.8.1** — Phase 0 only. Unblocks using the CLIs Tim already has.
- **0.9.0** — Phases 1–3. Claude + Codex CLI, Anthropic/OpenAI/DeepSeek keys, named-model `ask`/`review`.
- **0.10.0** — Phase 4. Guides and live-fetch completeness. Docs match reality.

---

## Self-review

Spec/goal coverage:

- CLI claude + grok + gpt/codex → Phases 0, 1, 2
- Access keys still first-class → Phase 2, Decision 1
- Almost all providers, certainly free ones → Decision 5 + Phase 4
- Easy key instructions → Decision 6 + Phase 4
- Model comparisons / writing reviews to many models at once → Decision 4 + Phase 3

No placeholders. Types (`CliSpec`, `model_ids: list[str] | None`, `api_style`) are named here so later tasks do not invent a second vocabulary.
