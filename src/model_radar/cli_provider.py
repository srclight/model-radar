"""
CLI subscription adapter — run local CLIs (grok, agy, claude, codex) as
single-turn completions so model-radar can ride a user's monthly subscription
instead of pay-as-you-go API credits.

HTTPS API keys stay the default for free-tier hosts. CLI is a second access
method for the same vendor (xai vs grok, anthropic vs claude), registered
only when the binary is on PATH.

Kind dispatch happens in scanner.py and runner.py.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PING_TIMEOUT_SECONDS = 5.0
COMPLETE_TIMEOUT_SECONDS = 120.0


class CLIProviderError(Exception):
    """Raised when a CLI provider subprocess fails or returns unparseable output."""


@dataclass(frozen=True)
class CliSpec:
    """One subscription CLI. Adding a vendor is a new row, not a new code path."""

    key: str
    name: str
    cmd: str
    models: tuple
    model_flag: str = "-m"
    prompt_flag: str = "-p"
    cmd_args: tuple[str, ...] = ()
    login_hint: str = ""
    install_hint: str = ""
    last_message_file: str | None = None  # if set, read this file in cwd instead of JSON stdout


# Subscription CLIs only — binaries that ride a monthly plan, not an API key.
CLI_SPECS: tuple[CliSpec, ...] = (
    CliSpec(
        key="grok",
        name="Grok (Subscription)",
        cmd="grok",
        model_flag="-m",
        prompt_flag="-p",
        cmd_args=("--output-format", "json", "--permission-mode", "plan", "--verbatim"),
        models=(
            ("grok-4.6", "Grok 4.6 (Subscription)", "S+", "72.0%", "256k"),
            ("grok-4.5", "Grok 4.5 (Subscription)", "S+", "70.0%", "256k"),
        ),
        login_hint="grok login",
        install_hint="https://docs.x.ai/build/overview",
    ),
    CliSpec(
        # Google deprecated Gemini CLI (June 2026) in favor of Antigravity (`agy`).
        # Provider key stays "gemini" so ask(providers=["gemini"]) still means
        # the Google subscription; the binary is `agy`.
        key="gemini",
        name="Gemini (Antigravity Subscription)",
        cmd="agy",
        model_flag="--model",
        prompt_flag="-p",
        cmd_args=("--output-format", "json", "--mode", "plan", "--disable-slash-commands"),
        models=(
            ("gemini-3.1-pro-high", "Gemini 3.1 Pro High (Subscription)", "S+", "70.0%", "1M"),
            ("gemini-3.7-flash-high", "Gemini 3.7 Flash High (Subscription)", "S", "60.0%", "1M"),
            ("gemini-3.7-flash-medium", "Gemini 3.7 Flash Medium (Subscription)", "A+", "55.0%", "1M"),
            ("gemini-3.6-flash-high", "Gemini 3.6 Flash High (Subscription)", "S", "60.0%", "1M"),
        ),
        login_hint="agy  (first interactive session signs in via browser)",
        install_hint="curl -fsSL https://antigravity.google/cli/install.sh | bash",
    ),
    CliSpec(
        key="claude",
        name="Claude (Subscription)",
        cmd="claude",
        model_flag="--model",
        prompt_flag="-p",
        cmd_args=(
            "--output-format", "json",
            "--bare",
            "--tools", "",
            "--permission-mode", "plan",
        ),
        models=(
            ("opus", "Claude Opus (Subscription)", "S+", "72.0%", "200k"),
            ("sonnet", "Claude Sonnet (Subscription)", "S", "65.0%", "200k"),
            ("haiku", "Claude Haiku (Subscription)", "A+", "50.0%", "200k"),
        ),
        login_hint="claude auth login",
        install_hint="https://docs.anthropic.com/en/docs/claude-code",
    ),
    CliSpec(
        key="codex",
        name="Codex (Subscription)",
        cmd="codex",
        model_flag="-m",
        prompt_flag="",  # prompt is the last positional; -p is --profile
        cmd_args=(
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s", "read-only",
            "--output-last-message", "last.txt",
        ),
        models=(
            ("gpt-5.6-terra", "GPT-5.6 Terra (Subscription)", "S+", "72.0%", "256k"),
        ),
        login_hint="codex login",
        install_hint="https://github.com/openai/codex",
        last_message_file="last.txt",
    ),
)

CLI_SPEC_BY_KEY = {s.key: s for s in CLI_SPECS}

# Kept for tests that import the old names.
GROK_CLI_MODELS = CLI_SPEC_BY_KEY["grok"].models
GEMINI_CLI_MODELS = CLI_SPEC_BY_KEY["gemini"].models
CLAUDE_CLI_MODELS = CLI_SPEC_BY_KEY["claude"].models


def _as_mapping(provider: Any) -> dict:
    """Accept a Provider dataclass or a plain dict (tests pass dicts)."""
    if isinstance(provider, dict):
        return provider
    return {
        "key": getattr(provider, "key", ""),
        "name": getattr(provider, "name", ""),
        "kind": getattr(provider, "kind", "cli"),
        "cmd": getattr(provider, "cmd", None),
        "cmd_args": getattr(provider, "cmd_args", ()),
        "prompt_via": getattr(provider, "prompt_via", "arg"),
        "model_flag": getattr(provider, "model_flag", "-m"),
        "prompt_flag": getattr(provider, "prompt_flag", "-p"),
        "last_message_file": getattr(provider, "last_message_file", None),
    }


def is_cli_provider(provider_key: str) -> bool:
    from .providers import PROVIDERS
    prov = PROVIDERS.get(provider_key)
    return bool(prov and getattr(prov, "kind", "https") == "cli")


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
    """Build the (args, kwargs) for asyncio.create_subprocess_exec.

    Subscription CLIs are headless single-turn: `-p <prompt>`, not a TUI.
    """
    cmd = provider["cmd"]
    cmd_args = list(provider.get("cmd_args", ()))
    model_flag = provider.get("model_flag", "-m")
    prompt_flag = provider.get("prompt_flag", "-p")
    args = [cmd, *cmd_args, model_flag, model_id]
    kwargs: dict = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
    if provider.get("prompt_via", "arg") == "stdin":
        if prompt_flag:
            args.append(prompt_flag)
        kwargs["stdin"] = asyncio.subprocess.PIPE
    elif prompt_flag:
        args.extend([prompt_flag, prompt])
    else:
        args.append(prompt)
    return args, kwargs


def _extract_response_text(stdout: bytes, provider_key: str) -> str:
    """Parse JSON output. Handles gemini {response}, claude {result}, grok choices."""
    try:
        text = stdout.decode("utf-8", errors="replace").strip()
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise CLIProviderError(
            f"Could not parse {provider_key} output as JSON: {e}. "
            f"First 200 chars: {stdout[:200]!r}"
        ) from e

    if isinstance(data, dict):
        for key in ("response", "result", "content", "text", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                inner = value.get("content") or value.get("text") or value.get("result")
                if isinstance(inner, str) and inner.strip():
                    return inner

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


def _auth_error_message(provider: dict, stderr: str) -> str | None:
    lowered = stderr.lower()
    if not any(tok in lowered for tok in ("login", "not authenticated", "unauthorized", "auth")):
        return None
    spec = CLI_SPEC_BY_KEY.get(provider.get("key", ""))
    hint = spec.login_hint if spec and spec.login_hint else f"{provider.get('cmd')} login"
    return f"Not authenticated — run `{hint}` first. {stderr[-300:]}"


async def ping_cli_provider(provider: Any) -> tuple[bool, float]:
    """Run `cmd --version` to check the binary is on PATH and runnable.

    This is an install check, not a latency sample. Auto-pick paths
    (get_fastest, default ask) must not rank CLI providers by this number.
    """
    provider = _as_mapping(provider)
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
            _stdout, _stderr = await asyncio.wait_for(
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
    provider: Any,
    model: Any,
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> dict:
    """Spawn the CLI with the prompt, capture stdout, parse JSON, return response.

    Isolated in a temp cwd so the subscription CLI cannot see the caller's repo.
    Tools/permissions are denied via cmd_args (plan mode / --bare / empty --tools).
    """
    provider = _as_mapping(provider)
    cmd = provider.get("cmd")
    if not cmd or not shutil.which(cmd):
        spec = CLI_SPEC_BY_KEY.get(provider.get("key", ""))
        extra = f" Install: {spec.install_hint}." if spec and spec.install_hint else ""
        raise CLIProviderError(
            f"CLI '{cmd}' not found on PATH.{extra} "
            f"Or disable the provider in config."
        )

    prompt, _ = _read_text_message(messages)
    model_id = model.model_id if hasattr(model, "model_id") else str(model)

    spec = CLI_SPEC_BY_KEY.get(provider.get("key", ""))
    last_file = spec.last_message_file if spec else None

    args, kwargs = _build_subprocess_args(provider, model_id, prompt)
    with tempfile.TemporaryDirectory(prefix="mr-cli-") as tmp:
        kwargs["cwd"] = tmp
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(*args, **kwargs)
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
            auth = _auth_error_message(provider, err)
            raise CLIProviderError(auth or f"CLI '{cmd}' exit {proc.returncode}: {err}")

        content = None
        if last_file:
            path = Path(tmp) / last_file
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    content = text
        if content is None:
            if not stdout:
                raise CLIProviderError(f"CLI '{cmd}' returned empty stdout")
            content = _extract_response_text(stdout, provider["key"])

    return {
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


def register_cli_providers() -> None:
    """Walk PATH for subscription CLIs and register each one found.

    Safe to call multiple times (idempotent — overwrites if already registered).
    """
    from .providers import _p

    for spec in CLI_SPECS:
        if not shutil.which(spec.cmd):
            continue
        _p(
            spec.key, spec.name, url=None, env_vars=(), models=spec.models,
            kind="cli", cmd=spec.cmd,
            cmd_args=spec.cmd_args,
            prompt_via="arg",
            model_flag=spec.model_flag,
            prompt_flag=spec.prompt_flag,
        )
