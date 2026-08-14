# Grok + Gemini CLI Providers for Model Radar — Design Spec

**Date:** 2026-08-14
**Status:** Draft (awaiting user review)
**Author:** brainstorming session
**Branch:** develop

## Goal

Make Grok (via xAI SuperGrok subscription) and Gemini (via Google Workspaces subscription) usable through model-radar's existing `ask()`, `batch_run()`, `judge()`, and dashboard tools — so parallel reviews and translations from Claude Code ride the user's existing subscriptions instead of pay-as-you-go API credits.

Equally add periodic refresh on server startup so the model catalog stays current.

## Context

Model-radar currently supports 21 HTTPS-API providers (NVIDIA, Groq, Cerebras, SambaNova, OpenRouter, Hugging Face, Replicate, DeepInfra, Fireworks, Mistral, Hyperbolic, Scaleway, Google AI Studio, SiliconFlow, Together, Cloudflare, xAI, Inference.net, SEA-LION, Ollama, Perplexity). 219 models.

- **xAI provider** is defined (`providers.py:369-375`) but **API key is empty** in `~/.model-radar/config.json` — account is `ACTIVE_NO_BILLING` (no payment method on x.ai).
- **Google AI provider** is defined (`providers.py:293-299`) but only ships **Gemma 3** (4B/12B/27B). The `AIzaSy…` API key would unlock Gemini Pro/Flash once they're added.
- **Subscription access** is the user's preferred cost path. SuperGrok (x.com) and Google Workspaces Gemini (gemini.google.com) are web-interface subscriptions — no public API covers them.

Both xAI and Google ship official CLI tools that ride the subscription:

- **Grok Build CLI** (`grok` on PATH, already installed at `/home/tim/.local/bin/grok`) — uses X-account OAuth by default, which counts against the user's SuperGrok subscription. Source: [xAI Grok Build docs](https://docs.x.ai/build/overview). Auth: `grok login` (browser X flow); response: `grok -p "..." --output-format json`.
- **Gemini CLI** (`@google/gemini-cli` on npm, version 0.55.1, installed at `/home/tim/.config/nvm/versions/node/v22.22.0/bin/gemini`) — uses Google OAuth by default, which counts against the user's Google Workspaces subscription. Source: [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli). Auth: `gemini auth login`; response: `gemini -p "..." --output-format json`.

The CLIs both support:
- Non-interactive single-prompt mode (`-p` / `--prompt` / `--single`)
- Model selection (`-m`)
- JSON output mode (`--output-format json`)

This makes a CLI subprocess bridge clean: spawn → JSON parse → return.

## Architecture

### New provider kind: `cli`

Add a third provider kind alongside the existing HTTPS kinds. A `cli` provider has:

```python
{
  "key": "grok",
  "label": "Grok (Subscription)",
  "kind": "cli",
  "cmd": "grok",
  "cmd_args": ["--output-format", "json"],
  "prompt_via": "arg",   # "arg" (last positional) or "stdin"
  "model_flag": "-m",
  "models": [...],
  "tier": "...",
  "free": True,            # subscription = "free" to user
  "requires_auth": "X OAuth via 'grok login'",
  "category": "subscription",
}
```

Both Grok and Gemini are auto-detected at server startup via `shutil.which("grok")` and `shutil.which("gemini")`. If found, they're registered. If not, they're omitted from the catalog.

### Components

#### 1. `src/model_radar/cli_provider.py` (NEW)

Implements the CLI provider abstraction:

```python
async def ping_cli_provider(provider: dict) -> tuple[bool, float]:
    """Run `grok --version` async. Returns (success, latency_ms)."""

async def complete_cli_provider(provider: dict, model: str, messages: list, *, max_tokens: int = 4096) -> str:
    """Spawn `grok -m <model> -p <prompt>` subprocess, capture stdout, parse JSON response."""
```

Subprocess management:
- `asyncio.create_subprocess_exec(cmd, *args, stdout=PIPE, stderr=PIPE)`
- Timeout: 60s default (subscription CLIs can be slow).
- Cancellation: closes subprocess on task cancel.
- Output: parse JSON, extract `response` field (gemini) or `content` field (grok) — handle both shapes.
- Errors: non-zero exit → raise `CLIProviderError` with stderr tail.

#### 2. `src/model_radar/providers.py` changes

Add two kinds of entries:

```python
# Static OpenAI-compatible API providers (existing)
_p("xai", "xAI", "https://api.x.ai/v1/chat/completions", ("XAI_API_KEY",), (...))
_p("googleai", "Google AI", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", ("GOOGLE_API_KEY",), (...))

# NEW: CLI subscription providers (registered conditionally)
def _register_cli_providers():
    """Walk PATH for 'grok' and 'gemini' binaries; conditionally register them."""
    if shutil.which("grok"):
        _p("grok", "Grok (Subscription)", None, (), _grok_models, kind="cli", cmd="grok", ...)
    if shutil.which("gemini"):
        _p("gemini", "Gemini (Subscription)", None, (), _gemini_models, kind="cli", cmd="gemini", ...)
```

Already-defined `xai` and `googleai` providers get augmented with:
- **Gemini-Pro, Gemini-Flash, Gemini-Flash-Lite** added to the `googleai` model list (using the existing API key).
- `xai` provider model list stays as-is (Grok-4, Grok-3, Grok-3-mini via xAI API).

#### 3. `src/model_radar/provider_sync.py` additions

Two new fetch functions:

```python
async def fetch_xai_models(api_key: str) -> list[ProviderModel]:
    """GET https://api.x.ai/v1/models — only if API key configured."""

async def fetch_googleai_models(api_key: str) -> list[ProviderModel]:
    """GET https://generativelanguage.googleapis.com/v1beta/models — only if API key configured."""
```

Both wired into `refresh_models_from_live(provider=...)`.

#### 4. `src/model_radar/scanner.py` / `runner.py` changes

- `ping()` dispatches to `ping_cli_provider()` for `kind == "cli"` providers.
- `complete()` dispatches to `complete_cli_provider()` for `kind == "cli"` providers.
- Otherwise unchanged.

#### 5. `src/model_radar/server.py` changes

- On server startup, after `load_config()` and provider registration, spawn a background task:
  ```python
  asyncio.create_task(_startup_refresh())
  ```
- `_startup_refresh()` calls `refresh_models_from_live()` with a 60s timeout. Errors logged, never crash the server.
- Add `refresh` to the existing `refresh_models` MCP tool description as "use periodically; also runs automatically on server startup".

#### 6. `src/model_radar/web.py` changes

- New `POST /api/refresh` endpoint that calls `refresh_models()`.
- New dashboard section "CLI providers" showing install status, auth reminder, and a one-click "Refresh" button.
- `GET /api/providers` extended to include `kind: "cli"` and `installed: bool`.

#### 7. `tests/test_cli_provider.py` (NEW)

Test cases:
- Successful subprocess run → parsed response
- Timeout (subprocess hangs) → `CLIProviderError`
- Non-zero exit → `CLIProviderError` with stderr
- Malformed JSON output → `CLIProviderError`
- Empty stdout → `CLIProviderError`
- Concurrent invocations (multiple subprocesses at once)
- `shutil.which()` returns None → provider not registered

### Files changed

| File | Change |
|---|---|
| `src/model_radar/cli_provider.py` | **NEW** — subprocess exec, ping, complete |
| `src/model_radar/providers.py` | Add `kind` to provider registry; new CLI providers; new Gemini model definitions for googleai |
| `src/model_radar/provider_sync.py` | Add `fetch_xai_models`, `fetch_googleai_models` |
| `src/model_radar/scanner.py` | Dispatch `ping()` to CLI provider for `kind == "cli"` |
| `src/model_radar/runner.py` | Dispatch `complete()` to CLI provider for `kind == "cli"` |
| `src/model_radar/server.py` | Background refresh task on startup; updated tool descriptions |
| `src/model_radar/web.py` | `/api/refresh` endpoint; CLI providers UI section |
| `tests/test_cli_provider.py` | **NEW** — subprocess mocking, ping/complete, timeout/exit/JSON |

### Data flow

```
server startup
  ↓
load_config() + register_all_providers()
  ↓
register_cli_providers()  ← shutil.which() detection
  ↓
asyncio.create_task(_startup_refresh())
  ↓ (background)
refresh_models_from_live()  ← provider_sync additions
  ↓
live fetch (xai, googleai, etc.) populates DB

user calls ask("...", count=4)
  ↓
get_workers(count=4, verified=True)
  ↓
includes xai/grok models if they ping-alive
  ↓
each worker calls complete() → dispatches to HTTPS or CLI
  ↓
results aggregated
```

### Error handling

| Case | Behavior |
|---|---|
| `grok`/`gemini` not on PATH | Provider not registered; `list_models()` doesn't show it; `get_workers()` skips it |
| `grok`/`gemini` on PATH but not authenticated | `complete()` returns `CLIProviderError("Not authenticated — run `grok login` first")` |
| Subprocess timeout (>60s) | Killed; `CLIProviderError("Timeout after 60s")` |
| Non-zero exit | `CLIProviderError(stderr[-500:])` |
| Malformed JSON output | `CLIProviderError("Could not parse response: ...")` |
| Concurrent calls | Each spawns its own subprocess; per-call timeout; no shared state |

### Security

- CLI providers execute local binaries at known paths (PATH-resolved). No shell injection risk because we use `asyncio.create_subprocess_exec` (no shell).
- Prompts are passed as args or stdin (no string interpolation into shell).
- Auth is OAuth in the user's browser — model-radar never sees credentials.
- New `kind == "cli"` providers are clearly labeled in the UI as "subscription".

### Testing strategy

- **Unit tests with mocked subprocess** (`unittest.mock.AsyncMock` for `create_subprocess_exec`).
- **Manual end-to-end** after install:
  1. Run `grok login` (browser X OAuth).
  2. Run `gemini auth login` (browser Google OAuth).
  3. Start server: `model-radar serve --web --transport sse`.
  4. Call `get_models()` — Grok and Gemini CLI providers should appear.
  5. Call `ask("What is 2+2?", count=4)` — both CLI providers should respond if picked.
  6. Open dashboard at `http://localhost:8743/` — verify CLI providers section shows both as installed.

## Out of scope

- **Browser-session bridge** (Playwright route to ride the web UI directly). Fragile, TOS-questionable, and the CLI tools make it unnecessary. Parked.
- **Other CLI providers** (e.g. `claude`, `codex`, `aider`). Pattern is generic; add later if needed.
- **Periodic refresh interval** (every 6h, etc.). User chose "on startup only" — no periodic loop.
- **Subscription tier detection** (Pro vs Free). Both CLIs default to the user's highest-available model; no programmatic tier detection.

## Risks

1. **CLI output format changes.** xAI or Google could change their JSON shape. Mitigated: keep the parser in one place (`cli_provider.py`), unit tests cover both shapes.
2. **CLI binaries break / change behavior.** Mitigated: `complete()` catches non-zero exit and raises; `ping()` returns `fail`; the rest of the system gracefully degrades.
3. **Subscription auth expires.** Mitigated: clear error message tells the user to run `grok login` / `gemini auth login` again.
4. **Slow responses.** Subscription CLIs may run agentic flows (browser tab, thinking, etc.). Mitigated: 60s timeout per call; `ask()` and `batch_run()` already handle per-item timeouts.

## Acceptance criteria

- [ ] `grok` and `gemini` registered as providers when on PATH; absent when not.
- [ ] `get_models()` lists CLI providers with `kind: "cli"` and `installed: bool`.
- [ ] `ask()` and `batch_run()` can include CLI providers in the worker pool.
- [ ] `ask("...", count=4)` returns results from CLI providers (when picked) within 60s timeout.
- [ ] Server startup runs `refresh_models_from_live()` in the background without blocking.
- [ ] Live fetch for xAI and Google AI populates when API keys are configured.
- [ ] Dashboard shows CLI providers section with install status and auth reminder.
- [ ] All `tests/test_cli_provider.py` tests pass.
- [ ] All existing tests still pass.
- [ ] README/docs updated to explain the new CLI provider concept.

## References

- [xAI Grok Build official docs](https://docs.x.ai/build/overview)
- [xAI Grok Build CLI launch announcement](https://x.ai/news/grok-build-cli)
- [Google Gemini CLI on GitHub](https://github.com/google-gemini/gemini-cli)
- [MCP vs CLI bridge pattern (MindStudio)](https://www.mindstudio.ai/blog/mcp-servers-vs-cli-tools-for-ai-agents)
- [MCP CLI tooling (Philschmid)](https://www.philschmid.de/mcp-cli)
- Internal: `/mnt/a/gig8/credentials.json` (xAI account info, Google AI API key)
- Internal: `~/.model-radar/config.json` (current API key state)
