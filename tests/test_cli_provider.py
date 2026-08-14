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

_CLI_KEYS = ("grok", "gemini", "claude", "codex")


@pytest.fixture
def restore_cli_providers():
    """Re-detect subscription CLIs after tests that mutate PROVIDERS."""
    yield
    from model_radar.providers import PROVIDERS
    for k in _CLI_KEYS:
        PROVIDERS.pop(k, None)
    register_cli_providers()


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
    assert result["latency_ms"] >= 0  # mocked subprocess is instantaneous
    # Headless subscription call: -p <prompt>, not a TUI positional.
    args = mock_exec.call_args.args
    assert "grok" in args
    assert "-m" in args
    assert "grok-4" in args
    assert "-p" in args
    assert args[args.index("-p") + 1] == "hi"


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
    msg = str(exc.value).lower()
    assert "not authenticated" in msg
    assert "grok login" in msg


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
    assert "timed out" in str(exc.value).lower()


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
    prompt_arg = args[args.index("-p") + 1]
    assert "Be brief." in prompt_arg
    assert "hi" in prompt_arg


def test_register_cli_providers_detects_grok(restore_cli_providers, monkeypatch):
    """register_cli_providers() registers 'grok' provider when binary is on PATH."""
    from model_radar.providers import PROVIDERS
    for k in list(PROVIDERS.keys()):
        if k in _CLI_KEYS:
            del PROVIDERS[k]

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/grok" if cmd == "grok" else None)
    register_cli_providers()

    assert "grok" in PROVIDERS
    assert PROVIDERS["grok"].kind == "cli"
    assert PROVIDERS["grok"].cmd == "grok"
    assert PROVIDERS["grok"].prompt_flag == "-p"


def test_register_cli_providers_detects_agy(restore_cli_providers, monkeypatch):
    """register_cli_providers() registers gemini provider when `agy` is on PATH."""
    from model_radar.providers import PROVIDERS
    for k in list(PROVIDERS.keys()):
        if k in _CLI_KEYS:
            del PROVIDERS[k]

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/agy" if cmd == "agy" else None)
    register_cli_providers()

    assert "gemini" in PROVIDERS
    assert PROVIDERS["gemini"].kind == "cli"
    assert PROVIDERS["gemini"].cmd == "agy"
    assert PROVIDERS["gemini"].model_flag == "--model"


def test_register_cli_providers_detects_claude(restore_cli_providers, monkeypatch):
    """register_cli_providers() registers 'claude' when Claude Code is on PATH."""
    from model_radar.providers import PROVIDERS
    for k in list(PROVIDERS.keys()):
        if k in _CLI_KEYS:
            del PROVIDERS[k]

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/claude" if cmd == "claude" else None)
    register_cli_providers()

    assert "claude" in PROVIDERS
    assert PROVIDERS["claude"].kind == "cli"
    assert PROVIDERS["claude"].cmd == "claude"
    assert PROVIDERS["claude"].model_flag == "--model"


def test_register_cli_providers_skips_missing(restore_cli_providers, monkeypatch):
    """register_cli_providers() skips subscription CLIs when binaries are absent."""
    from model_radar.providers import PROVIDERS
    for k in list(PROVIDERS.keys()):
        if k in _CLI_KEYS:
            del PROVIDERS[k]

    monkeypatch.setattr("shutil.which", lambda cmd: None)
    register_cli_providers()

    assert "grok" not in PROVIDERS
    assert "gemini" not in PROVIDERS
    assert "claude" not in PROVIDERS
    assert "codex" not in PROVIDERS


def test_complete_accepts_provider_dataclass():
    """Runner passes a Provider dataclass, not a dict."""
    from model_radar.cli_provider import _as_mapping
    from model_radar.providers import Provider

    prov = Provider(
        key="grok", name="Grok (Subscription)", url=None, env_vars=(),
        models=(), kind="cli", cmd="grok", cmd_args=("--output-format", "json"),
        prompt_via="arg", model_flag="-m", prompt_flag="-p",
    )
    mapped = _as_mapping(prov)
    assert mapped["cmd"] == "grok"
    assert mapped["prompt_flag"] == "-p"
