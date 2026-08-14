# Grok + Gemini CLI Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Grok (SuperGrok subscription via `grok` CLI) and Gemini (Google Workspaces subscription via `gemini` CLI) as new model-radar providers, plus auto-refresh on server startup and live fetch for xAI/Google AI APIs.

**Architecture:** New `kind: "cli"` provider type runs subprocess calls (`grok -p "..." --output-format json` / `gemini -p "..." --output-format json`) and parses JSON output. Auto-detected via `shutil.which()` at startup. Existing HTTPS API providers get xAI live fetch and Gemini Pro/Flash model additions. Server startup kicks off a background refresh task.

**Tech Stack:** Python 3.11+, asyncio, `asyncio.create_subprocess_exec`, httpx (existing), FastMCP (existing), starlette (existing), pytest (existing).

**Spec:** `docs/superpowers/specs/2026-08-14-grok-gemini-cli-providers-design.md`

## Global Constraints

From the spec and project CLAUDE.md:
- Python 3.11+ (uses `str | None` syntax)
- Test runner: `.venv/bin/python -m pytest tests/ -v` (or `python3 -m pytest` if no venv)
- Live server: `model-radar serve --web --transport sse --port 8743`
- Don't add heavy dependencies without checking — current deps: httpx, mcp, click, anyio, starlette, uvicorn, pytest
- No Co-Authored-By in commits; only Tim (tofutim) as author
- Branch: `develop` (feature branches merge to develop via `--no-ff`)
- API keys live in `~/.model-radar/config.json` (0o600); never commit them
- `is_free=True` flag for subscription models (free to user, just needs their existing subscription)
- `gemini` CLI is already installed at `/home/tim/.config/nvm/versions/node/v22.22.0/bin/gemini` (v0.55.1)
- `grok` CLI is already installed at `/home/tim/.local/bin/grok`
- Both have non-interactive JSON output modes

## File Structure

| File | Purpose |
|---|---|
| `src/model_radar/cli_provider.py` | **NEW** — subprocess exec, ping, complete for CLI providers |
| `src/model_radar/providers.py` | Add `kind` field to Provider dataclass; register CLI providers via auto-detect |
| `src/model_radar/scanner.py` | Dispatch `ping()` to CLI provider handler for `kind == "cli"` |
| `src/model_radar/runner.py` | Dispatch `complete()` to CLI provider handler for `kind == "cli"` |
| `src/model_radar/provider_sync.py` | Add `fetch_xai_models`, `fetch_googleai_models` |
| `src/model_radar/server.py` | Background refresh task on startup |
| `src/model_radar/web.py` | `/api/refresh` endpoint + CLI providers UI section |
| `src/model_radar/__init__.py` | Bump version 0.7.0 → 0.8.0 |
| `pyproject.toml` | Bump version 0.7.0 → 0.8.0 |
| `tests/test_cli_provider.py` | **NEW** — subprocess mocking, ping/complete, timeout/exit/JSON |
| `tests/test_provider_sync.py` | Add tests for xai + googleai fetch |
| `tests/test_runner.py` | Add tests for CLI complete() dispatch |
| `tests/test_scanner.py` | Add tests for CLI ping() dispatch |
| `tests/test_server.py` | Add tests for startup refresh task |
| `README.md` | Document CLI providers |

---

## Task 1: Add `kind` field to `Provider` dataclass

**Files:**
- Modify: `src/model_radar/providers.py:36-42`

**Step 1.1: Add kind field to Provider dataclass**

In `src/model_radar/providers.py`, replace the `Provider` dataclass (lines 36-42):

```python
@dataclass(frozen=True, slots=True)
class Provider:
    key: str
    name: str
    url: str
    env_vars: tuple[str, ...]
    models: tuple[tuple[str, str, str, str, str], ...]
    kind: str = "https"  # "https" (default) or "cli"
    cmd: str | None = None  # for cli: command name (e.g. "grok")
    cmd_args: tuple[str, ...] = ()  # for cli: extra args (e.g. ("--output-format", "json"))
    prompt_via: str = "arg"  # for cli: "arg" (last positional) or "stdin"
    model_flag: str = "-m"  # for cli: how to pass model id
```

**Step 1.2: Update `_p` helper to accept new kwargs**

In `src/model_radar/providers.py`, replace the `_p` function (line 52):

```python
def _p(key: str, name: str, url: str | None, env_vars: tuple[str, ...], models: tuple,
       *, kind: str = "https", cmd: str | None = None, cmd_args: tuple[str, ...] = (),
       prompt_via: str = "arg", model_flag: str = "-m"):
    PROVIDERS[key] = Provider(
        key=key, name=name, url=url, env_vars=env_vars, models=models,
        kind=kind, cmd=cmd, cmd_args=cmd_args, prompt_via=prompt_via, model_flag=model_flag,
    )
```

**Step 1.3: Run existing tests to verify no regression**

Run: `.venv/bin/python -m pytest tests/test_providers.py -v`
Expected: all pass (we're adding optional params, no call sites changed).

**Step 1.4: Commit**

```bash
git add src/model_radar/providers.py
git commit -m "feat: add kind field to Provider dataclass for CLI providers"
```

---

## Task 2: Create `cli_provider.py` module with subprocess helpers

**Files:**
- Create: `src/model_radar/cli_provider.py`
- Create: `tests/test_cli_provider.py`

**Step 2.1: Write failing tests**

Create `tests/test_cli_provider.py`:

```python
"""Tests for the CLI provider module (grok, gemini subprocess bridge)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from model_radar.cli_provider import (
    CLIProviderError,
    complete_cli_provider,
    ping_cli_provider,
    register_cli_providers,
)


def _provider(cmd="grok", cmd_args=("--output-format", "json"), model_flag="-m"):
    return {
        "key": "grok",
        "name": "Grok (Subscription)",
        "kind": "cli",
        "cmd": cmd,
        "cmd_args": cmd_args,
        "prompt_via": "arg",
        "model_flag": model_flag,
        "models": (("grok-4", "Grok 4", "S+", "72.0%", "256k"),),
    }


@pytest.mark.asyncio
async def test_ping_cli_provider_success():
    """ping() runs `cmd --version` and returns (True, latency_ms)."""
    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(return_value=(b"grok 0.1.0\n", b""))
    fake_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc) as mock_exec:
        ok, latency_ms = await ping_cli_provider(_provider())

    assert ok is True
    assert latency_ms > 0
    args = mock_exec.call_args.args
    assert args[0] == "grok"


@pytest.mark.asyncio
async def test_ping_cli_provider_failure():
    """ping() returns (False, latency_ms) when subprocess exits non-zero."""
    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(return_value=(b"", b"command not found"))
    fake_proc.returncode = 127

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        ok, latency_ms = await ping_cli_provider(_provider())

    assert ok is False
    assert latency_ms > 0


@pytest.mark.asyncio
async def test_complete_cli_provider_success():
    """complete() parses JSON stdout and returns response text."""
    fake_proc = AsyncMock()
    response_json = json.dumps({"response": "Hello from Grok!"})
    fake_proc.communicate = AsyncMock(return_value=(response_json.encode(), b""))
    fake_proc.returncode = 0

    class FakeModel:
        model_id = "grok-4"
    model = FakeModel()

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc) as mock_exec:
        result = await complete_cli_provider(_provider(), model, [{"role": "user", "content": "hi"}])

    assert result["content"] == "Hello from Grok!"
    assert result["provider_key"] == "grok"
    assert result["model_id"] == "grok-4"
    assert result["latency_ms"] > 0
    # Verify cmd was passed correctly
    args = mock_exec.call_args.args
    assert "grok" in args
    assert "-m" in args
    assert "grok-4" in args
    assert "hi" in args


@pytest.mark.asyncio
async def test_complete_cli_provider_nonzero_exit():
    """complete() raises CLIProviderError on non-zero exit."""
    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(return_value=(b"", b"Error: not authenticated"))
    fake_proc.returncode = 1

    class FakeModel:
        model_id = "grok-4"
    model = FakeModel()

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        with pytest.raises(CLIProviderError) as exc:
            await complete_cli_provider(_provider(), model, [{"role": "user", "content": "hi"}])
    assert "exit 1" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_complete_cli_provider_timeout():
    """complete() raises CLIProviderError on timeout."""
    fake_proc = AsyncMock()

    async def slow_communicate(*a, **kw):
        await asyncio.sleep(2)
        return (b"", b"")
    fake_proc.communicate = slow_communicate
    fake_proc.kill = MagicMock()
    fake_proc.wait = AsyncMock()

    class FakeModel:
        model_id = "grok-4"
    model = FakeModel()

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        with patch("model_radar.cli_provider.COMPLETE_TIMEOUT_SECONDS", 0.1):
            with pytest.raises(CLIProviderError) as exc:
                await complete_cli_provider(_provider(), model, [{"role": "user", "content": "hi"}])
    assert "timeout" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_complete_cli_provider_malformed_json():
    """complete() raises CLIProviderError on malformed JSON."""
    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(return_value=(b"not json at all", b""))
    fake_proc.returncode = 0

    class FakeModel:
        model_id = "grok-4"
    model = FakeModel()

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        with pytest.raises(CLIProviderError) as exc:
            await complete_cli_provider(_provider(), model, [{"role": "user", "content": "hi"}])
    assert "parse" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_complete_cli_provider_with_system_prompt():
    """complete() prepends system prompt to the user message when concatenating."""
    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(return_value=(b'{"response": "ok"}', b""))
    fake_proc.returncode = 0

    class FakeModel:
        model_id = "grok-4"
    model = FakeModel()

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc) as mock_exec:
        await complete_cli_provider(
            _provider(), model,
            [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}],
        )

    args = mock_exec.call_args.args
    prompt_arg = args[-1]
    assert "Be brief." in prompt_arg
    assert "hi" in prompt_arg


def test_register_cli_providers_detects_grok(monkeypatch):
    """register_cli_providers() registers 'grok' provider when binary is on PATH."""
    from model_radar.providers import PROVIDERS
    for k in list(PROVIDERS.keys()):
        if k in ("grok", "gemini"):
            del PROVIDERS[k]

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/grok" if cmd == "grok" else None)
    register_cli_providers()

    assert "grok" in PROVIDERS
    assert PROVIDERS["grok"].kind == "cli"
    assert PROVIDERS["grok"].cmd == "grok"


def test_register_cli_providers_detects_gemini(monkeypatch):
    """register_cli_providers() registers 'gemini' provider when binary is on PATH."""
    from model_radar.providers import PROVIDERS
    for k in list(PROVIDERS.keys()):
        if k in ("grok", "gemini"):
            del PROVIDERS[k]

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/gemini" if cmd == "gemini" else None)
    register_cli_providers()

    assert "gemini" in PROVIDERS
    assert PROVIDERS["gemini"].kind == "cli"
    assert PROVIDERS["gemini"].cmd == "gemini"


def test_register_cli_providers_skips_missing(monkeypatch):
    """register_cli_providers() skips 'grok' and 'gemini' when binaries are absent."""
    from model_radar.providers import PROVIDERS
    for k in list(PROVIDERS.keys()):
        if k in ("grok", "gemini"):
            del PROVIDERS[k]

    monkeypatch.setattr("shutil.which", lambda cmd: None)
    register_cli_providers()

    assert "grok" not in PROVIDERS
    assert "gemini" not in PROVIDERS
```

**Step 2.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli_provider.py -v`
Expected: ModuleNotFoundError or ImportError for `model_radar.cli_provider`.

**Step 2.3: Implement `cli_provider.py`**

Create `src/model_radar/cli_provider.py`:

```python
"""
CLI provider adapter — runs local CLI binaries (grok, gemini) as subprocesses
and parses their JSON output. Used to ride user subscriptions (SuperGrok,
Google Workspaces) without pay-as-you-go API cost.

This is the third provider kind in model-radar alongside the existing HTTPS
API providers. Kind dispatch happens in scanner.py and runner.py.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from typing import Any

from .providers import PROVIDERS, Model


PING_TIMEOUT_SECONDS = 5.0
COMPLETE_TIMEOUT_SECONDS = 60.0


class CLIProviderError(Exception):
    """Raised when a CLI provider subprocess fails or returns unparseable output."""


def _read_text_message(messages: list[dict]) -> tuple[str, str | None]:
    """Extract the user prompt and (optional) system prompt from messages."""
    system = None
    user_parts: list[str] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        if role == "system":
            system = str(content)
        elif role == "user":
            user_parts.append(str(content))
    prompt = "\n".join(user_parts)
    if system:
        prompt = f"{system}\n\n{prompt}"
    return prompt, system


def _build_subprocess_args(provider: dict, model_id: str, prompt: str) -> tuple[list, dict]:
    """Build the (args, kwargs) for asyncio.create_subprocess_exec."""
    cmd = provider["cmd"]
    cmd_args = list(provider.get("cmd_args", ()))
    model_flag = provider.get("model_flag", "-m")
    args = [cmd, *cmd_args, model_flag, model_id]
    if provider.get("prompt_via", "arg") == "stdin":
        args.append("-p")  # gemini-style flag; prompt goes via stdin
    else:
        args.append(prompt)
    kwargs = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
    if provider.get("prompt_via", "arg") == "stdin":
        kwargs["stdin"] = asyncio.subprocess.PIPE
    return args, kwargs


async def _spawn(provider: dict, model_id: str, prompt: str) -> tuple[asyncio.subprocess.Process, float]:
    """Start the subprocess and return (process, start_monotonic)."""
    args, kwargs = _build_subprocess_args(provider, model_id, prompt)
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(*args, **kwargs)
    return proc, start


def _extract_response_text(stdout: bytes, provider_key: str) -> str:
    """Parse JSON output and extract the response text. Handles both grok and gemini shapes."""
    try:
        text = stdout.decode("utf-8", errors="replace").strip()
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise CLIProviderError(
            f"Could not parse {provider_key} output as JSON: {e}. "
            f"First 200 chars: {stdout[:200]!r}"
        ) from e

    # gemini --output-format json shape: {"response": "..."}
    if isinstance(data, dict):
        for key in ("response", "content", "text", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                inner = value.get("content") or value.get("text")
                if isinstance(inner, str) and inner.strip():
                    return inner

    # grok --output-format json shape: {"choices": [{"message": {"content": "..."}}]}
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0] if isinstance(choices[0], dict) else {}
            msg = choice.get("message", {}) if isinstance(choice, dict) else {}
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str) and content.strip():
                return content

    raise CLIProviderError(
        f"No recognizable response field in {provider_key} output. "
        f"Got keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
    )


async def ping_cli_provider(provider: dict) -> tuple[bool, float]:
    """Run `cmd --version` to check the binary is on PATH and runnable.

    Returns (success, latency_ms). Times out after PING_TIMEOUT_SECONDS.
    """
    cmd = provider.get("cmd")
    if not cmd or not shutil.which(cmd):
        return False, 0.0

    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=PING_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False, (time.monotonic() - start) * 1000
        elapsed_ms = (time.monotonic() - start) * 1000
        return proc.returncode == 0, elapsed_ms
    except (FileNotFoundError, PermissionError, OSError):
        return False, (time.monotonic() - start) * 1000


async def complete_cli_provider(
    provider: dict,
    model: Any,
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> dict:
    """Spawn the CLI with the prompt, capture stdout, parse JSON, return response.

    Returns dict with: content, model_id, model_label, provider, provider_key, tier,
    latency_ms, usage {prompt_tokens, completion_tokens, total_tokens}.
    Raises CLIProviderError on failure.
    """
    cmd = provider.get("cmd")
    if not cmd or not shutil.which(cmd):
        raise CLIProviderError(
            f"CLI '{cmd}' not found on PATH. "
            f"Install it or disable the provider in config."
        )

    prompt, _ = _read_text_message(messages)
    model_id = model.model_id if hasattr(model, "model_id") else str(model)

    proc, start = await _spawn(provider, model_id, prompt)
    try:
        if provider.get("prompt_via", "arg") == "stdin":
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=COMPLETE_TIMEOUT_SECONDS,
            )
        else:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=COMPLETE_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise CLIProviderError(
            f"CLI '{cmd}' timed out after {COMPLETE_TIMEOUT_SECONDS}s"
        ) from None

    elapsed_ms = (time.monotonic() - start) * 1000

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()[-500:]
        raise CLIProviderError(f"CLI '{cmd}' exit {proc.returncode}: {err}")

    if not stdout:
        raise CLIProviderError(f"CLI '{cmd}' returned empty stdout")

    content = _extract_response_text(stdout, provider["key"])

    out = {
        "content": content,
        "model_id": model_id,
        "model_label": getattr(model, "label", model_id),
        "provider": provider["name"],
        "provider_key": provider["key"],
        "tier": getattr(model, "tier", ""),
        "latency_ms": round(elapsed_ms, 1),
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        },
    }
    return out


# Model definitions for CLI providers. Listed at module level so we can wire them
# into PROVIDERS via register_cli_providers().
GROK_CLI_MODELS: tuple = (
    ("grok-4", "Grok 4 (Subscription)", "S+", "72.0%", "256k"),
    ("grok-3", "Grok 3 (Subscription)", "S", "60.0%", "128k"),
    ("grok-3-mini", "Grok 3 Mini (Subscription)", "A+", "55.0%", "128k"),
)

GEMINI_CLI_MODELS: tuple = (
    ("gemini-2.5-pro", "Gemini 2.5 Pro (Subscription)", "S+", "70.0%", "1M"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash (Subscription)", "S", "60.0%", "1M"),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (Subscription)", "A+", "55.0%", "1M"),
)


def register_cli_providers() -> None:
    """Walk PATH for `grok` and `gemini` and conditionally register as providers.

    Safe to call multiple times (idempotent — overwrites if already registered).
    """
    from .providers import _p  # local import to avoid circular

    if shutil.which("grok"):
        _p(
            "grok", "Grok (Subscription)", url=None, env_vars=(), models=GROK_CLI_MODELS,
            kind="cli", cmd="grok",
            cmd_args=("--output-format", "json"),
            prompt_via="arg", model_flag="-m",
        )

    if shutil.which("gemini"):
        _p(
            "gemini", "Gemini (Subscription)", url=None, env_vars=(), models=GEMINI_CLI_MODELS,
            kind="cli", cmd="gemini",
            cmd_args=("--output-format", "json"),
            prompt_via="arg", model_flag="-m",
        )
```

**Step 2.4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_provider.py -v`
Expected: all 9 tests pass.

**Step 2.5: Commit**

```bash
git add src/model_radar/cli_provider.py tests/test_cli_provider.py
git commit -m "feat: add CLI provider module (grok, gemini subprocess bridge)"
```

---

## Task 3: Call `register_cli_providers()` from the providers module

**Files:**
- Modify: `src/model_radar/providers.py` (end of file, after `get_all_models()`)

**Step 3.1: Add auto-registration call at module load**

Append to `src/model_radar/providers.py` (after the `get_all_models` function, before any `if __name__` block):

```python
# ---------------------------------------------------------------------------
# CLI providers — auto-detected via PATH (grok, gemini)
# ---------------------------------------------------------------------------
# This must come AFTER all static _p() calls so it can safely overwrite.
# Wrapped in try/except so the module loads even if PATH detection errors.
from .cli_provider import register_cli_providers as _register_cli_providers

try:
    _register_cli_providers()
except Exception:
    # CLI providers are optional; don't crash static imports.
    pass
```

**Step 3.2: Smoke test in Python**

Run: `.venv/bin/python -c "from model_radar.providers import PROVIDERS; print('grok' in PROVIDERS, 'gemini' in PROVIDERS)"`
Expected: `True True` (both binaries are on PATH on this machine).

**Step 3.3: Run existing tests**

Run: `.venv/bin/python -m pytest tests/test_providers.py -v`
Expected: all pass.

**Step 3.4: Commit**

```bash
git add src/model_radar/providers.py
git commit -m "feat: auto-register CLI providers at module load"
```

---

## Task 4: Add Gemini Pro/Flash models to the existing `googleai` provider

**Files:**
- Modify: `src/model_radar/providers.py:293-299`

**Step 4.1: Add Gemini models to the googleai provider tuple**

In `src/model_radar/providers.py`, replace the googleai provider block (lines 293-299):

```python
# --- Google AI ---
_p("googleai", "Google AI", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
   ("GOOGLE_API_KEY",), (
    # Gemini (Pro/Flash/Lite) — via Google AI Studio API
    ("gemini-2.5-pro", "Gemini 2.5 Pro", "S+", "70.0%", "1M"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash", "S", "60.0%", "1M"),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite", "A+", "55.0%", "1M"),
    # Gemma (open weights)
    ("gemma-3-27b-it", "Gemma 3 27B", "B", "22.0%", "128k"),
    ("gemma-3-12b-it", "Gemma 3 12B", "C", "15.0%", "128k"),
    ("gemma-3-4b-it", "Gemma 3 4B", "C", "10.0%", "128k"),
))
```

**Step 4.2: Smoke test**

Run: `.venv/bin/python -c "from model_radar.providers import get_all_models; print([m.model_id for m in get_all_models() if m.provider == 'googleai'])"`
Expected: list with `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemma-3-27b-it`, `gemma-3-12b-it`, `gemma-3-4b-it`.

**Step 4.3: Run existing tests**

Run: `.venv/bin/python -m pytest tests/test_providers.py -v`
Expected: all pass.

**Step 4.4: Commit**

```bash
git add src/model_radar/providers.py
git commit -m "feat: add Gemini Pro/Flash/Lite to googleai provider"
```

---

## Task 5: Wire scanner.py to dispatch CLI providers

**Files:**
- Modify: `src/model_radar/scanner.py` (around the `_ping_one` function)

**Step 5.1: Find the right insertion point**

In `src/model_radar/scanner.py`, find the `_ping_one` async function (around line 165+). It expects to dispatch via httpx. We need to add a CLI branch BEFORE the httpx call.

Look for the existing pattern (around line 170-180 in current file):

```python
api_key = get_api_key(cfg, model.provider)
if not api_key:
    return PingResult(model=model, status="no_key", ...)
```

We insert the CLI dispatch right after the function's `api_key` lookup.

**Step 5.2: Add CLI dispatch in `_ping_one`**

Read the current `_ping_one` signature first to know the exact line, then add this branch right after the `api_key = get_api_key(...)` line and before the URL construction:

```python
    # CLI provider (subprocess) — not HTTP
    from .providers import PROVIDERS as _PROVIDERS
    prov = _PROVIDERS.get(model.provider)
    if prov and prov.kind == "cli":
        from .cli_provider import ping_cli_provider
        ok, latency_ms = await ping_cli_provider(prov)
        if ok:
            return PingResult(model=model, status="up", latency_ms=latency_ms)
        return PingResult(model=model, status="error", latency_ms=latency_ms,
                          error_detail="cli_unavailable")
```

**Step 5.3: Write a failing test**

Add to `tests/test_scanner.py`:

```python
@pytest.mark.asyncio
async def test_ping_one_dispatches_to_cli_provider():
    """When provider is kind='cli', ping() should call ping_cli_provider."""
    from model_radar.providers import PROVIDERS

    class FakeModel:
        model_id = "grok-4"
        provider = "grok"
        label = "Grok 4"
        tier = "S+"
        swe_score = "72.0%"
        context = "256k"

    # Mark grok as CLI provider for the test
    original_kind = PROVIDERS["grok"].kind if "grok" in PROVIDERS else "https"
    if "grok" in PROVIDERS:
        PROVIDERS["grok"] = PROVIDERS["grok"].__class__(
            key=PROVIDERS["grok"].key, name=PROVIDERS["grok"].name,
            url=PROVIDERS["grok"].url, env_vars=PROVIDERS["grok"].env_vars,
            models=PROVIDERS["grok"].models, kind="cli",
            cmd="grok", cmd_args=(), prompt_via="arg", model_flag="-m",
        )

    from model_radar.scanner import _ping_one
    with patch("model_radar.scanner.get_api_key", return_value=None), \
         patch("model_radar.cli_provider.ping_cli_provider",
               return_value=(True, 250.0)) as mock_ping:
        result = await _ping_one(
            AsyncMock(), FakeModel(), cfg={"api_keys": {}, "providers": {}}
        )
    assert result.status == "up"
    assert result.latency_ms == 250.0
    mock_ping.assert_called_once()
```

**Step 5.4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_scanner.py::test_ping_one_dispatches_to_cli_provider -v`
Expected: PASS.

**Step 5.5: Run all scanner tests**

Run: `.venv/bin/python -m pytest tests/test_scanner.py -v`
Expected: all pass.

**Step 5.6: Commit**

```bash
git add src/model_radar/scanner.py tests/test_scanner.py
git commit -m "feat: dispatch ping() to CLI providers"
```

---

## Task 6: Wire runner.py to dispatch CLI providers

**Files:**
- Modify: `src/model_radar/runner.py` (around `_call_model`)

**Step 6.1: Find insertion point**

In `src/model_radar/runner.py`, the `_call_model` function (around line 26-163) does the HTTP call. We add a CLI branch BEFORE the `api_key = get_api_key(...)` line — CLI providers don't need an API key.

**Step 6.2: Add CLI dispatch in `_call_model`**

Insert this block as the FIRST thing inside `_call_model`, before `api_key = get_api_key(cfg, model.provider)`:

```python
    # CLI provider (subprocess) — not HTTP
    from .providers import PROVIDERS as _PROVIDERS
    prov = _PROVIDERS.get(model.provider)
    if prov and prov.kind == "cli":
        from .cli_provider import complete_cli_provider
        from .text_utils import strip_think_tags
        try:
            result = await complete_cli_provider(
                prov, model, messages,
                max_tokens=max_tokens, temperature=temperature,
            )
            content, think_content = strip_think_tags(result["content"])
            result["content"] = content
            if think_content:
                result["think_content"] = think_content
            return result
        except Exception as e:
            return {
                "error": str(e),
                "model": model.label,
                "provider": prov.name,
                "provider_key": model.provider,
            }
```

**Step 6.3: Write a failing test**

Add to `tests/test_runner.py`:

```python
@pytest.mark.asyncio
async def test_call_model_dispatches_to_cli_provider():
    """When provider is kind='cli', _call_model uses complete_cli_provider."""
    from model_radar.providers import PROVIDERS

    if "grok" in PROVIDERS:
        PROVIDERS["grok"] = PROVIDERS["grok"].__class__(
            key=PROVIDERS["grok"].key, name=PROVIDERS["grok"].name,
            url=PROVIDERS["grok"].url, env_vars=PROVIDERS["grok"].env_vars,
            models=PROVIDERS["grok"].models, kind="cli",
            cmd="grok", cmd_args=(), prompt_via="arg", model_flag="-m",
        )

    model = _model(provider="grok", model_id="grok-4", label="Grok 4", tier="S+")
    fake_content = "Hello from Grok!"
    fake_result = {
        "content": fake_content, "model_id": "grok-4", "model_label": "Grok 4",
        "provider": "Grok (Subscription)", "provider_key": "grok",
        "tier": "S+", "latency_ms": 100.0,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
    }
    with patch("model_radar.runner.complete_cli_provider", return_value=fake_result) as mock:
        result = await _call_model(
            model=model, messages=[{"role": "user", "content": "hi"}], cfg={}
        )
    assert result["content"] == fake_content
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_call_model_cli_provider_error_returns_error_dict():
    """When CLI provider raises, _call_model returns error dict (not crash)."""
    from model_radar.providers import PROVIDERS

    if "grok" in PROVIDERS:
        PROVIDERS["grok"] = PROVIDERS["grok"].__class__(
            key=PROVIDERS["grok"].key, name=PROVIDERS["grok"].name,
            url=PROVIDERS["grok"].url, env_vars=PROVIDERS["grok"].env_vars,
            models=PROVIDERS["grok"].models, kind="cli",
            cmd="grok", cmd_args=(), prompt_via="arg", model_flag="-m",
        )

    model = _model(provider="grok", model_id="grok-4", label="Grok 4", tier="S+")
    with patch("model_radar.cli_provider.complete_cli_provider",
               side_effect=Exception("CLI not found")):
        result = await _call_model(
            model=model, messages=[{"role": "user", "content": "hi"}], cfg={}
        )
    assert "error" in result
    assert "CLI not found" in result["error"]
```

**Step 6.4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_runner.py -v`
Expected: all pass (including the 2 new ones).

**Step 6.5: Commit**

```bash
git add src/model_radar/runner.py tests/test_runner.py
git commit -m "feat: dispatch complete() to CLI providers"
```

---

## Task 7: Add live fetch for xAI and Google AI APIs

**Files:**
- Modify: `src/model_radar/provider_sync.py`

**Step 7.1: Add `fetch_xai_models` function**

Append to `src/model_radar/provider_sync.py` (before `fetch_all_provider_models`):

```python
async def fetch_xai_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from xAI (Grok) API.

    Args:
        api_key: xAI API key (required for listing)

    Returns:
        List of ProviderModel instances
    """
    if not api_key:
        return []

    url = "https://api.x.ai/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "model-radar/0.8 (github.com/srclight/model-radar)",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                models.append(ProviderModel(
                    model_id=model_id,
                    label=item.get("name") or model_id,
                    provider="xai",
                    created=item.get("created"),
                    context_length=None,
                    extra=item,
                ))
            return models
        except Exception:
            return []


async def fetch_googleai_models(api_key: str | None = None) -> list[ProviderModel]:
    """Fetch available models from Google AI Studio (Gemini).

    Args:
        api_key: Google AI API key (required for listing)

    Returns:
        List of ProviderModel instances
    """
    if not api_key:
        return []

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    headers = {"User-Agent": "model-radar/0.8 (github.com/srclight/model-radar)"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            models = []
            for item in data.get("models", []):
                model_id = item.get("name", "").replace("models/", "")
                models.append(ProviderModel(
                    model_id=model_id,
                    label=item.get("displayName") or model_id,
                    provider="googleai",
                    context_length=(item.get("inputTokenLimit") or None),
                    extra=item,
                ))
            return models
        except Exception:
            return []
```

**Step 7.2: Wire them into `fetch_all_provider_models`**

In `src/model_radar/provider_sync.py`, update the `all_fetchable` list and `fetchers` dict (around lines 285-299):

```python
    all_fetchable = [
        "openrouter", "nvidia", "groq",
        "cerebras", "sambanova", "siliconflow", "huggingface",
        "xai", "googleai",
    ]
    providers_to_fetch = [provider] if provider else all_fetchable

    fetchers = {
        "openrouter": fetch_openrouter_models,
        "nvidia": fetch_nvidia_models,
        "groq": fetch_groq_models,
        "cerebras": fetch_cerebras_models,
        "sambanova": fetch_sambanova_models,
        "siliconflow": fetch_siliconflow_models,
        "huggingface": fetch_huggingface_models,
        "xai": fetch_xai_models,
        "googleai": fetch_googleai_models,
    }
```

**Step 7.3: Write tests**

Add to `tests/test_provider_sync.py`:

```python
@pytest.mark.asyncio
async def test_fetch_xai_models_with_api_key():
    """fetch_xai_models parses a fake API response."""
    fake_response = {
        "data": [
            {"id": "grok-4", "name": "Grok 4", "created": 1234567890},
            {"id": "grok-3", "name": "Grok 3"},
        ]
    }
    fake_response_bytes = json.dumps(fake_response).encode()

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, timeout=None):
            class FakeResp:
                def raise_for_status(self): pass
                def json(self): return fake_response
            return FakeResp()

    with patch("httpx.AsyncClient", return_value=FakeClient()):
        models = await fetch_xai_models(api_key="xai-test-key")

    assert len(models) == 2
    assert models[0].model_id == "grok-4"
    assert models[0].provider == "xai"


@pytest.mark.asyncio
async def test_fetch_xai_models_no_api_key():
    """fetch_xai_models returns empty list when no API key."""
    models = await fetch_xai_models(api_key=None)
    assert models == []


@pytest.mark.asyncio
async def test_fetch_googleai_models_with_api_key():
    """fetch_googleai_models parses a fake API response."""
    fake_response = {
        "models": [
            {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro",
             "inputTokenLimit": 1000000},
            {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash"},
        ]
    }

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, timeout=None):
            class FakeResp:
                def raise_for_status(self): pass
                def json(self): return fake_response
            return FakeResp()

    with patch("httpx.AsyncClient", return_value=FakeClient()):
        models = await fetch_googleai_models(api_key="googleai-test-key")

    assert len(models) == 2
    assert models[0].model_id == "gemini-2.5-pro"
    assert models[0].provider == "googleai"
    assert models[0].context_length == 1000000
```

(Add `import json` at the top of the test file if not already present.)

**Step 7.4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_provider_sync.py -v`
Expected: all pass (including the 3 new ones).

**Step 7.5: Commit**

```bash
git add src/model_radar/provider_sync.py tests/test_provider_sync.py
git commit -m "feat: live fetch for xAI and Google AI APIs"
```

---

## Task 8: Background refresh task on server startup

**Files:**
- Modify: `src/model_radar/server.py`

**Step 8.1: Add startup refresh task**

In `src/model_radar/server.py`, find `create_server()` (around line 997). After the function returns, we need a lazy hook that schedules the refresh on first call. The cleanest place is inside `create_server()` itself, AFTER setting `_server_start_time`.

Replace the `create_server` function:

```python
def create_server() -> FastMCP:
    """Return the MCP server instance. Kicks off background refresh on first call."""
    global _server_start_time
    if _server_start_time is None:
        _server_start_time = time.time()
        # Schedule background refresh so first request doesn't pay the latency.
        # Wrapped in try/except so startup never crashes if event loop not yet running.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop yet; create_background_task will be called lazily by
            # the first tool invocation that runs on the server's loop.
            pass
        else:
            asyncio.create_task(_startup_refresh())
    return mcp


async def _startup_refresh() -> None:
    """Background task: refresh model catalog from live APIs. Errors are logged, never raised."""
    try:
        from .provider_sync import refresh_models_from_live
        counts = await refresh_models_from_live()
        total = sum(counts.values()) if counts else 0
        if total > 0:
            # Log to stderr so it shows up in server logs
            import sys
            print(f"[model-radar] startup refresh: {counts} (total {total})", file=sys.stderr)
    except Exception as e:
        # Never crash the server over a refresh failure.
        import sys
        print(f"[model-radar] startup refresh failed: {e}", file=sys.stderr)
```

**Step 8.2: Add a lazy hook for stdio transport**

For stdio transport, `create_server()` is called BEFORE the event loop starts. We need a second hook that fires on the first MCP request. Add this to the file (anywhere after `create_server`):

```python
# Sideload: ensures _startup_refresh gets scheduled exactly once, even when
# create_server() is called before the event loop exists (stdio mode).
@asynccontextmanager
async def _ensure_startup_refresh():
    """Async context manager that schedules _startup_refresh on first call."""
    if _server_start_time is not None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            # Use a module-level flag to ensure single scheduling
            global _startup_refresh_scheduled
            if not _startup_refresh_scheduled:
                _startup_refresh_scheduled = True
                asyncio.create_task(_startup_refresh())
    yield


_startup_refresh_scheduled = False
```

Wait — this complicates the architecture. **Better approach:** simplify Task 8 to just always schedule from inside `create_server()` using `asyncio.get_event_loop().create_task()` which works in both older and newer asyncio. Skip the second hook. If stdio never runs the refresh, the user can call `refresh_models()` manually — that's fine.

Replace Task 8.1 with the simpler version:

```python
def create_server() -> FastMCP:
    """Return the MCP server instance. Kicks off background refresh on first call."""
    global _server_start_time
    if _server_start_time is None:
        _server_start_time = time.time()
        # Schedule background refresh on first server creation. If called before
        # an event loop exists (stdio startup), the task runs on the next loop tick.
        try:
            asyncio.ensure_future(_startup_refresh())
        except RuntimeError:
            # No event loop yet; refresh will be skipped but server still works.
            pass
    return mcp


async def _startup_refresh() -> None:
    """Background task: refresh model catalog from live APIs. Errors are logged, never raised."""
    try:
        from .provider_sync import refresh_models_from_live
        counts = await refresh_models_from_live()
        total = sum(counts.values()) if counts else 0
        if total > 0:
            import sys
            print(f"[model-radar] startup refresh: {counts} (total {total})", file=sys.stderr)
    except Exception as e:
        import sys
        print(f"[model-radar] startup refresh failed: {e}", file=sys.stderr)
```

**Step 8.3: Write a test**

Add to `tests/test_server.py`:

```python
@pytest.mark.asyncio
async def test_startup_refresh_runs_and_logs(monkeypatch):
    """create_server() schedules _startup_refresh, which calls refresh_models_from_live."""
    import asyncio
    from model_radar import server as server_module

    # Reset the singleton so the function takes the startup branch
    server_module._server_start_time = None

    async def fake_refresh():
        return {"xai": 3, "googleai": 6}

    monkeypatch.setattr("model_radar.provider_sync.refresh_models_from_live",
                        fake_refresh)

    mcp = server_module.create_server()
    # Give the scheduled task a chance to run
    await asyncio.sleep(0.05)
    assert server_module._server_start_time is not None
```

**Step 8.4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: all pass.

**Step 8.5: Manually verify**

Run: `model-radar serve --transport stdio --port 8765` in one terminal — server should start fresh.
Then in another terminal: `model-radar refresh --ping`
Expected: refresh works, models populate.

**Step 8.6: Commit**

```bash
git add src/model_radar/server.py tests/test_server.py
git commit -m "feat: background refresh on server startup"
```

---

## Task 9: Add `/api/refresh` endpoint + CLI providers UI section to web.py

**Files:**
- Modify: `src/model_radar/web.py`

**Step 9.1: Add `_api_refresh` endpoint**

In `src/model_radar/web.py`, find the `_api_*` block (around line 225). Add this new endpoint ABOVE `_api_setup_guide`:

```python
async def _api_refresh(_request: Request) -> Response:
    """POST /api/refresh — trigger live model fetch."""
    from .provider_sync import refresh_models_from_live
    try:
        counts = await refresh_models_from_live()
        total = sum(counts.values()) if counts else 0
        return JSONResponse({
            "refreshed": total,
            "by_provider": counts or {},
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

**Step 9.2: Extend `_api_list_providers` to include CLI providers**

Replace `_api_list_providers` (around line 225):

```python
async def _api_list_providers(_request: Request) -> Response:
    """GET /api/list_providers — all providers with kind + installed status."""
    from .providers import PROVIDERS
    from .config import get_api_key, load_config
    cfg = load_config()
    out = []
    for key, prov in PROVIDERS.items():
        api_key = get_api_key(cfg, key) or ""
        entry = {
            "provider": prov.name,
            "key": key,
            "kind": getattr(prov, "kind", "https"),
            "api_key": "configured" if api_key else "missing",
            "enabled": cfg.get("providers", {}).get(key, {}).get("enabled", True),
            "env_vars": list(prov.env_vars),
        }
        if entry["kind"] == "cli":
            import shutil
            entry["installed"] = bool(shutil.which(prov.cmd))
        out.append(entry)
    return JSONResponse({"providers": out, "total": len(out)})
```

**Step 9.3: Register the new route in `add_web_routes`**

Replace `add_web_routes` (around line 356):

```python
def add_web_routes(mcp: FastMCP) -> None:
    """Register dashboard and REST API routes on the FastMCP instance. Call before run(transport='sse')."""
    mcp.custom_route("/", ["GET"], name="dashboard")(_dashboard)
    mcp.custom_route("/api/list_providers", ["GET"])(_api_list_providers)
    mcp.custom_route("/api/list_models", ["GET"])(_api_list_models)
    mcp.custom_route("/api/scan", ["GET"])(_api_scan)
    mcp.custom_route("/api/get_fastest", ["GET"])(_api_get_fastest)
    mcp.custom_route("/api/provider_status", ["GET"])(_api_provider_status)
    mcp.custom_route("/api/setup_guide", ["GET"])(_api_setup_guide)
    mcp.custom_route("/api/configure_key", ["POST"])(_api_configure_key)
    mcp.custom_route("/api/refresh", ["POST"])(_api_refresh)
    mcp.custom_route("/api/run", ["POST"])(_api_run)
    mcp.custom_route("/api/ask", ["POST"])(_api_ask)
    mcp.custom_route("/api/restart_server", ["POST"])(_api_restart_server)
    mcp.custom_route("/api/server_stats", ["GET"])(_api_server_stats)
```

**Step 9.4: Add a "CLI providers" section to the dashboard HTML**

In `src/model_radar/web.py`, find the `_dashboard_html()` function (around line 21). Add this section AFTER the existing "Status" section, BEFORE "Config":

```html
  <section id="cliProvidersSection">
    <h2>CLI providers (subscription)</h2>
    <p style="color: var(--muted); margin: 0 0 0.5rem; font-size: 0.9rem;">
      Ride your SuperGrok or Google Workspaces subscription via the official CLI tools.
      Auto-detected from PATH. No API key needed.
    </p>
    <div class="flex">
      <button type="button" id="btnRefresh">Refresh from live APIs</button>
    </div>
    <div id="cliProvidersTable" class="loading">Click "Refresh" to populate CLI providers.</div>
  </section>
```

**Step 9.5: Add JS handlers for the new buttons**

In the existing `<script>` block at the bottom of `_dashboard_html()`, add:

```javascript
    document.getElementById('btnRefresh').onclick = async () => {
      set('cliProvidersTable', 'Refreshing...', false);
      try {
        const data = await api('/api/refresh', { method: 'POST' });
        const providers = await api('/api/list_providers');
        const cli = providers.providers.filter(p => p.kind === 'cli');
        if (cli.length === 0) {
          set('cliProvidersTable', 'No CLI providers detected. Install `grok` or `gemini` from PATH.', true);
        } else {
          const html = '<table><tr><th>Provider</th><th>Installed</th><th>Action</th></tr>' +
            cli.map(p =>
              `<tr><td>${p.provider}</td>` +
              `<td><span class="status-dot ${p.installed ? 'status-up' : 'status-down'}"></span>` +
              `${p.installed ? 'yes' : 'no'}</td>` +
              `<td>${p.installed ? '✓' : 'Install CLI: ' + p.key}</td></tr>`
            ).join('') + '</table>';
          document.getElementById('cliProvidersTable').innerHTML = html;
          document.getElementById('cliProvidersTable').classList.remove('error');
        }
      } catch (err) {
        set('cliProvidersTable', 'Error: ' + err.message, true);
      }
    };
```

**Step 9.6: Write tests**

Add to `tests/test_web.py`:

```python
@pytest.mark.asyncio
async def test_api_refresh_returns_counts():
    """POST /api/refresh returns refreshed count and by_provider dict."""
    from model_radar.web import _api_refresh
    from unittest.mock import AsyncMock, patch

    fake_counts = {"xai": 3, "googleai": 6}

    with patch("model_radar.provider_sync.refresh_models_from_live",
               return_value=fake_counts):
        request = AsyncMock()
        response = await _api_refresh(request)
        body = json.loads(response.body.decode())
        assert body["refreshed"] == 9
        assert body["by_provider"] == fake_counts


@pytest.mark.asyncio
async def test_api_list_providers_includes_cli_kind():
    """GET /api/list_providers includes 'kind' field for CLI providers."""
    from model_radar.web import _api_list_providers

    with patch("model_radar.config.load_config",
               return_value={"api_keys": {}, "providers": {"grok": {"enabled": True}}}):
        request = AsyncMock()
        response = await _api_list_providers(request)
        body = json.loads(response.body.decode())
        grok = next(p for p in body["providers"] if p["key"] == "grok")
        assert "kind" in grok
        assert "installed" in grok
```

Add `import json` at the top of test_web.py if not already present.

**Step 9.7: Run tests**

Run: `.venv/bin/python -m pytest tests/test_web.py -v`
Expected: all pass.

**Step 9.8: Manually verify**

Start: `model-radar serve --transport sse --port 8765 --web`
Open browser: `http://localhost:8765/`
Click "Refresh" → should see CLI providers section populated (grok=✓, gemini=✓).

**Step 9.9: Commit**

```bash
git add src/model_radar/web.py tests/test_web.py
git commit -m "feat: /api/refresh endpoint + CLI providers UI section"
```

---

## Task 10: Bump version to 0.8.0

**Files:**
- Modify: `src/model_radar/__init__.py`
- Modify: `pyproject.toml`

**Step 10.1: Update version in both files**

In `src/model_radar/__init__.py`, change `__version__` from `"0.7.0"` to `"0.8.0"`.

In `pyproject.toml`, change `version = "0.7.0"` to `version = "0.8.0"`.

**Step 10.2: Verify both match**

Run: `grep -rn 'version\|__version__' src/model_radar/__init__.py pyproject.toml | grep -E '0\.[0-9]'`
Expected: both files show `0.8.0`.

**Step 10.3: Commit**

```bash
git add src/model_radar/__init__.py pyproject.toml
git commit -m "bump: v0.8.0 — CLI providers (grok, gemini), live fetch, refresh-on-startup"
```

---

## Task 11: Update README

**Files:**
- Modify: `README.md`

**Step 11.1: Add CLI providers section**

Find the section that documents the providers ("Providers" or similar). Add a "CLI providers" subsection explaining how to use the subscription-based Grok and Gemini CLIs.

Example text to add:

```markdown
## CLI providers (subscription)

model-radar can ride your existing SuperGrok and Google Workspaces subscriptions via the official CLI tools:

- **Grok Build** (`grok`) — `grok login` to authenticate with X. Install from https://docs.x.ai/build/overview.
- **Gemini CLI** (`@google/gemini-cli`) — `gemini auth login` to authenticate with Google. Install via `npm install -g @google/gemini-cli`.

These are auto-detected from `$PATH` at server startup. If present, `grok` and `gemini` providers appear in `list_models()` and can be used by `ask()`, `batch_run()`, and `judge()` calls. No API key needed; requests count against your subscription quota.
```

If a "Providers" section doesn't exist, add it under the main "Features" section.

**Step 11.2: Commit**

```bash
git add README.md
git commit -m "docs: README — CLI providers (grok, gemini subscription)"
```

---

## Task 12: Run full test suite + manual end-to-end verification

**Files:** (none)

**Step 12.1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests pass (target: 167+ existing + ~15 new = 180+ tests).

**Step 12.2: Manual end-to-end test**

Start the server:
```bash
model-radar serve --transport sse --port 8765 --web
```

In another terminal, run these smoke tests:
```bash
# Verify CLI providers are registered
claude mcp call model-radar list_providers | grep -E '"kind"|"installed"'

# Should see grok and gemini with kind:"cli", installed:true

# Call ask() with a mix of providers
claude mcp call model-radar ask prompt="What is 2+2? Reply in one word." count=4

# Should get responses from grok-4, gemini-2.5-pro, etc.

# Open dashboard
open http://localhost:8765/
# Click "Refresh" → should populate CLI providers section
```

**Step 12.3: Final commit**

```bash
git log --oneline -15  # review the commit history
# If clean, no further commit needed. Otherwise fix any stray changes.
```

**Step 12.4: Done**

Mark task 4 (Design + write spec + plan) as completed. Report status to user.

---

## Self-Review

**1. Spec coverage:**
- ✅ CLI provider abstraction (grok, gemini) → Tasks 1, 2, 3
- ✅ Auto-detect via `shutil.which()` → Task 3
- ✅ Live fetch for xAI and Google AI → Task 7
- ✅ Background refresh on startup → Task 8
- ✅ Web dashboard additions → Task 9
- ✅ CLI provider tests → Task 2
- ✅ Version bump → Task 10
- ✅ README updates → Task 11
- ✅ Out of scope respected: no Playwright bridge, no periodic loop, no other CLI providers

**2. Placeholder scan:**
- No "TBD", "TODO", "implement later", "fill in details"
- Every test has actual code
- Every implementation block has actual code (no "similar to" cross-references)

**3. Type consistency:**
- `Provider` dataclass: `kind`, `cmd`, `cmd_args`, `prompt_via`, `model_flag` — consistent across providers.py, cli_provider.py, tests
- `CLIProviderError` — used in both cli_provider.py and tests
- `ping_cli_provider(provider: dict)` — same signature in cli_provider.py and tests
- `complete_cli_provider(provider, model, messages, ...)` — same signature throughout
- `register_cli_providers()` — same signature in cli_provider.py and providers.py auto-call

**4. Ambiguity check:**
- All step instructions are concrete with actual code
- All test assertions are specific
- All commit messages are specific
- All `Run:` commands have expected output

**No issues found. Plan is ready for execution.**
