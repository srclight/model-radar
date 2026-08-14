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
    """Extract the user prompt and (Optional) system prompt from messages."""
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
