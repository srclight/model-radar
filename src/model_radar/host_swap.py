"""
Instructions for host agents on where to search the user's machine for
config files that can be updated to use a model-radar model (OpenAI-compatible
endpoint + model id). Includes Cursor, Claude Code, Open Interpreter, OpenClaw.
"""

from __future__ import annotations

from .config import CONFIG_PATH, load_config
from .db import get_models_for_discovery
from .endpoints import get_openai_endpoint_for_model
from .providers import TIER_ORDER

# Where model-radar stores API keys (so host can tell user or read for swap)
MODEL_RADAR_KEY_LOCATIONS = {
    "primary_config": str(CONFIG_PATH),
    "primary_config_note": "0o600, contains api_keys per provider. Prefer env vars to avoid writing keys to disk.",
    "env_override": "Per-provider env vars (e.g. GROQ_API_KEY) override config. See list_providers() for env_vars.",
    "local_override": "Project ./config.json in cwd overrides ~/.model-radar/config.json when present.",
}

# Apps that can use an OpenAI-compatible endpoint + model id.
# Paths are per-platform; {home} = $HOME (Linux/Mac) or %USERPROFILE% (Windows).
# WSL: both Linux ~ and Windows /mnt/c/Users/<user> may exist.
HOST_SWAP_LOCATIONS = [
    {
        "app": "Cursor",
        "description": "Cursor IDE model / custom API settings. May use Settings UI or config files.",
        "platforms": [
            {
                "platform": "linux",
                "paths": [
                    "~/.cursor/",
                    "~/.config/Cursor/User/settings.json",
                ],
                "notes": "MCP servers: ~/.cursor/mcp.json or project .cursor/mcp.json. Model/base URL often in Settings > Models.",
            },
            {
                "platform": "mac",
                "paths": [
                    "~/.cursor/",
                    "~/Library/Application Support/Cursor/User/settings.json",
                ],
                "notes": "Same as Linux for MCP. Custom API base URL and model in Cursor Settings > Models.",
            },
            {
                "platform": "windows",
                "paths": [
                    "%USERPROFILE%\\.cursor\\",
                    "%APPDATA%\\Cursor\\User\\settings.json",
                ],
                "notes": "Typical: C:\\Users\\<username>\\.cursor\\ and C:\\Users\\<username>\\AppData\\Roaming\\Cursor\\User\\. MCP: .cursor\\mcp.json.",
            },
            {
                "platform": "wsl",
                "paths": [
                    "~/.cursor/",
                    "/mnt/c/Users/<WindowsUsername>/.cursor/",
                    "/mnt/c/Users/<WindowsUsername>/AppData/Roaming/Cursor/User/settings.json",
                ],
                "notes": "Check both WSL home and Windows mount. Replace <WindowsUsername> with actual Windows user (e.g. timuy).",
            },
        ],
        "what_to_set": "Custom API base URL (base_url from model-radar), model name (model_id), and API key from model-radar config or env.",
    },
    {
        "app": "Claude Code",
        "description": "Claude Code (claude.dev) uses Anthropic by default; custom OpenAI-compatible endpoint support may be limited.",
        "platforms": [
            {
                "platform": "linux",
                "paths": [
                    "~/.claude/settings.json",
                    "~/.claude/settings.local.json",
                ],
                "notes": "Project-level: .claude/settings.json, .claude/settings.local.json. Model in settings or ANTHROPIC_MODEL env.",
            },
            {
                "platform": "mac",
                "paths": [
                    "~/.claude/settings.json",
                    "~/.claude/settings.local.json",
                ],
                "notes": "Same as Linux.",
            },
            {
                "platform": "windows",
                "paths": [
                    "%USERPROFILE%\\.claude\\settings.json",
                    "%USERPROFILE%\\.claude\\settings.local.json",
                ],
                "notes": "Typical: C:\\Users\\<username>\\.claude\\. Credentials: .credentials.json (Linux/Windows).",
            },
            {
                "platform": "wsl",
                "paths": [
                    "~/.claude/settings.json",
                    "/mnt/c/Users/<WindowsUsername>/.claude/settings.json",
                ],
                "notes": "Check WSL and Windows user dir. Claude Code may prefer Anthropic; document base_url/model for tools that support it.",
            },
        ],
        "what_to_set": "If Claude Code supports custom OpenAI endpoint: base_url, model_id, and API key. Otherwise use for reference only.",
    },
    {
        "app": "Open Interpreter",
        "description": "Open Interpreter (interpreter) uses OpenAI-compatible api_base and model in profiles.",
        "platforms": [
            {
                "platform": "linux",
                "paths": [
                    "~/.config/open-interpreter/",
                    "Run: interpreter --profiles  # opens profiles directory",
                ],
                "notes": "Profiles are YAML or Python. In YAML: llm.api_base, llm.model, (optional) llm.api_key. Use api_base = model-radar base_url, model = model_id.",
            },
            {
                "platform": "mac",
                "paths": [
                    "~/.config/open-interpreter/",
                    "Run: interpreter --profiles",
                ],
                "notes": "Same as Linux.",
            },
            {
                "platform": "windows",
                "paths": [
                    "%USERPROFILE%\\.config\\open-interpreter\\",
                    "Run: interpreter --profiles",
                ],
                "notes": "Or %APPDATA%\\open-interpreter. interpreter --profiles opens the actual dir.",
            },
            {
                "platform": "wsl",
                "paths": [
                    "~/.config/open-interpreter/",
                    "Run: interpreter --profiles",
                ],
                "notes": "If interpreter is run from Windows, check /mnt/c/Users/<user>/AppData/Roaming or .config equivalent.",
            },
        ],
        "what_to_set": "In profile YAML: llm.api_base = <base_url>, llm.model = <model_id>. API key: llm.api_key or env VAR from model-radar.",
    },
    {
        "app": "OpenClaw / Claws / Zero / Nano",
        "description": "OpenClaw and similar CLI/desktop tools. MCP config in openclaw.json; model/endpoint may be in app settings or env.",
        "platforms": [
            {
                "platform": "linux",
                "paths": [
                    "~/.openclaw/openclaw.json",
                ],
                "notes": "MCP servers in openclaw.json. For custom model/endpoint, check app docs or settings under ~/.openclaw/ or ~/.config/.",
            },
            {
                "platform": "mac",
                "paths": [
                    "~/.openclaw/openclaw.json",
                ],
                "notes": "Same as Linux.",
            },
            {
                "platform": "windows",
                "paths": [
                    "%USERPROFILE%\\.openclaw\\openclaw.json",
                ],
                "notes": "C:\\Users\\<username>\\.openclaw\\. Check for settings.json or similar for model/API.",
            },
            {
                "platform": "wsl",
                "paths": [
                    "~/.openclaw/openclaw.json",
                    "/mnt/c/Users/<WindowsUsername>/.openclaw/openclaw.json",
                ],
                "notes": "Check both WSL and Windows paths if the app runs on either side.",
            },
        ],
        "what_to_set": "Where supported: OpenAI base URL and model id; API key from model-radar config or env.",
    },
]


def get_host_swap_instructions(
    model_id: str | None = None,
    provider: str | None = None,
    min_tier: str | None = "A",
) -> dict:
    """
    Return instructions for the host agent on where to search the machine and what to set.

    If model_id (and optionally provider) is given, returns endpoint info for that model.
    Otherwise suggests a high-tier model and returns its endpoint info. Also returns
    model-radar key locations and per-app, per-platform paths to search/update.

    Args:
        model_id: Specific model_id (e.g. "llama-3.3-70b-versatile"). If omitted, no specific endpoint is chosen.
        provider: Restrict to this provider when picking a default model.
        min_tier: When not specifying model_id, pick from this tier or better (default "A").
    """
    cfg = load_config()
    endpoint_info = None
    chosen_model = None

    if model_id:
        for m in get_models_for_discovery():
            if m.model_id == model_id and (provider is None or m.provider == provider):
                chosen_model = m
                break
        if chosen_model:
            endpoint_info = get_openai_endpoint_for_model(chosen_model, cfg)
    else:
        # Pick a default: first min_tier or better (sorted by tier quality, then label)
        models = get_models_for_discovery(provider=provider, min_tier=min_tier or "A")
        if models and (min_tier or "A") in TIER_ORDER:
            models.sort(key=lambda m: (TIER_ORDER.get(m.tier, 99), m.label))
            chosen_model = models[0]
            endpoint_info = get_openai_endpoint_for_model(chosen_model, cfg)

    return {
        "model_radar_key_locations": MODEL_RADAR_KEY_LOCATIONS,
        "openai_endpoint": endpoint_info,
        "chosen_model": {
            "model_id": chosen_model.model_id,
            "label": chosen_model.label,
            "provider": chosen_model.provider,
            "tier": chosen_model.tier,
        } if chosen_model else None,
        "search_locations": HOST_SWAP_LOCATIONS,
        "host_instructions": (
            "Search the paths above for the current platform (and on WSL, check both ~ and /mnt/c/Users/<user>). "
            "Use openai_endpoint.base_url and openai_endpoint.model_id to set the custom API endpoint and model. "
            "API key: use the value from model_radar_key_locations (config file or env var per provider). "
            "Do not log or echo API keys."
        ),
    }


