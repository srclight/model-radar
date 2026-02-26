"""
Deterministic setup workflow for guiding host agents (and users) to install
provider API keys. Covers Playwright readiness, listing unconfigured providers,
login instructions per provider, and where to save keys.

Designed so the host agent can run steps in order and prompt the user when
needed (e.g. to choose which providers to set up).
"""

from __future__ import annotations

from .config import CONFIG_PATH, get_api_key, load_config
from .guides import get_setup_guide
from .providers import PROVIDERS

# Providers that support "Sign in with GitHub" (user may only need to click Allow)
GITHUB_SSO_PROVIDERS = frozenset({
    "groq",
    "openrouter",
    "huggingface",  # HF often has GitHub OAuth
    "deepinfra",
    "fireworks",
    "together",
})


def get_workflow_step(
    step: int,
    provider_selection: list[str] | None = None,
) -> dict:
    """
    Return structured instructions for one step of the setup workflow.

    Step 1: Check/install Playwright (for optional browser automation on the host).
    Step 2: List remaining (unconfigured) providers; host should show user and get selection.
    Step 3: Login instructions for selected providers + where to save keys.
    Step 4: Explicit "where to save keys" summary (path, tool, env vars).
    Step 5: Where to search the host machine to swap in a model (Cursor, Claude Code,
            Open Interpreter, OpenClaw) and what base_url + model_id to set; includes
            model_radar key locations. Optional provider_selection ignored; use
            host_swap_instructions(model_id?, provider?, min_tier?) for custom pick.

    Args:
        step: 1, 2, 3, 4, or 5.
        provider_selection: For step 3, list of provider keys to get instructions for.
            If omitted for step 3, response tells host to prompt user to select from step 2 list.
    """
    if step == 1:
        return _step1_playwright()
    if step == 2:
        return _step2_remaining_providers()
    if step == 3:
        return _step3_login_instructions(provider_selection)
    if step == 4:
        return _step4_where_to_save()
    if step == 5:
        return _step5_host_swap()
    return {
        "error": "Invalid step",
        "valid_steps": [1, 2, 3, 4, 5],
        "usage": "step 1: Playwright check/install. step 2: List unconfigured providers. "
                "step 3: Login instructions (pass provider_selection from step 2). step 4: Where to save keys. "
                "step 5: Host swap instructions (where to search machine, base_url + model_id).",
    }


def _step1_playwright() -> dict:
    """Instructions for host to check/install Playwright (optional for browser-assisted signup)."""
    return {
        "step": 1,
        "title": "Playwright check and install",
        "purpose": "Playwright is optional. Use it on the host if you want to automate or assist browser sign-in flows (e.g. GitHub SSO).",
        "check_command": "python -c \"import playwright; print('ok')\"",
        "install_commands": [
            "pip install playwright",
            "playwright install chromium",
        ],
        "verify_command": "playwright install chromium  # no-op if already installed",
        "host_instructions": (
            "Run the check_command. If it fails, run install_commands in order, then verify_command. "
            "If the host does not use Playwright, skip to step 2 and use manual signup URLs only."
        ),
    }


def _step2_remaining_providers() -> dict:
    """List providers that do not have an API key configured."""
    data = get_setup_guide()
    unconfigured = list(data.get("unconfigured") or [])
    for entry in unconfigured:
        pkey = entry.get("provider")
        entry["provider_key"] = pkey
        entry["github_sso"] = pkey in GITHUB_SSO_PROVIDERS if pkey else False
    return {
        "step": 2,
        "title": "Remaining providers (no API key configured)",
        "unconfigured": unconfigured,
        "host_instructions": (
            "Show the user the list above (provider_key, name, signup_url, priority). "
            "Prompt the user to choose which providers they want to set up (e.g. by provider_key). "
            "Then call step 3 with provider_selection set to that list of provider keys."
        ),
    }


def _step3_login_instructions(provider_selection: list[str] | None) -> dict:
    """Per-provider login steps and where to save the key."""
    if not provider_selection:
        return {
            "step": 3,
            "error": "provider_selection required",
            "host_instructions": (
                "First call step 2 to get unconfigured providers. Prompt the user to select which ones to set up, "
                "then call step 3 with provider_selection=[...] (list of provider_key strings)."
            ),
        }

    cfg = load_config()
    results = []
    invalid = []
    for pkey in provider_selection:
        if pkey not in PROVIDERS:
            invalid.append(pkey)
            continue
        if get_api_key(cfg, pkey) is not None:
            results.append({
                "provider_key": pkey,
                "name": PROVIDERS[pkey].name,
                "already_configured": True,
                "message": "Already has API key; skip or replace if desired.",
            })
            continue
        guide = get_setup_guide(pkey)
        if not guide or guide.get("error") or guide.get("message"):
            results.append({
                "provider_key": pkey,
                "name": PROVIDERS[pkey].name,
                "error": guide.get("message") or "No setup guide for this provider.",
            })
            continue
        env_var = guide.get("env_var", "")
        results.append({
            "provider_key": pkey,
            "name": guide.get("name", pkey),
            "signup_url": guide.get("signup_url"),
            "steps": guide.get("steps", []),
            "key_format": guide.get("key_format"),
            "github_sso": pkey in GITHUB_SSO_PROVIDERS,
            "where_to_save": {
                "config_path": str(CONFIG_PATH),
                "tool_call": f'configure_key(provider="{pkey}", api_key="<paste key here>")',
                "env_var": env_var,
                "note": f"Keys are stored in {CONFIG_PATH} (0o600) or can be set via env var {env_var}.",
            },
        })

    return {
        "step": 3,
        "title": "Login instructions and where to save keys",
        "providers": results,
        "invalid_keys": invalid if invalid else None,
        "host_instructions": (
            "For each provider, direct the user to signup_url and have them follow steps. "
            "If github_sso is true, the user may only need to click 'Sign in with GitHub' and approve. "
            "After the user obtains each API key, save it using configure_key(provider, api_key) or set the env var."
        ),
    }


def _step4_where_to_save() -> dict:
    """Single place documenting where keys are stored and how."""
    return {
        "step": 4,
        "title": "Where to save API keys",
        "config_path": str(CONFIG_PATH),
        "permissions_note": "File is created with 0o600 (read/write owner only). Never commit this file.",
        "methods": [
            "MCP tool: configure_key(provider, api_key) — writes to config_path.",
            "Environment variable: Set the provider's env var (e.g. GROQ_API_KEY). Overrides config.",
            "Manual: Edit config_path and add under \"api_keys\": { \"provider_key\": \"value\" }.",
        ],
        "security": [
            "Do not log or echo API keys in tool responses or terminal output.",
            "Do not store keys in the project repo or in the Vault; only in config_path or env.",
            "Local ./config.json in a project overrides ~/.model-radar/config.json for that project.",
        ],
    }


def _step5_host_swap() -> dict:
    """Host swap: where to search the machine and what endpoint/model to set."""
    from .host_swap import get_host_swap_instructions

    result = get_host_swap_instructions(min_tier="A")
    result["step"] = 5
    result["title"] = "Where to swap in a model (host machine)"
    result["host_instructions_short"] = (
        "Search search_locations for your platform (linux/mac/windows/wsl). "
        "Use openai_endpoint.base_url and model_id; API key from model_radar_key_locations. "
        "For a specific or fastest model, call host_swap_instructions(model_id=..., min_tier=...) instead."
    )
    return result
