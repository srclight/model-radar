"""
Provider setup guides for AI agents.

Returns structured instructions that an AI agent can relay to its user
to configure additional free model providers. Written for agent consumption,
not human reading.
"""

from __future__ import annotations

from .cli_provider import CLI_SPEC_BY_KEY, is_cli_provider
from .config import get_api_key, load_config
from .providers import PROVIDERS

# Signup instructions per provider, written for an AI agent to relay
_GUIDES: dict[str, dict] = {
    "nvidia": {
        "name": "NVIDIA NIM",
        "free_tier": "Unlimited free access for dev/prototyping. ~40 requests/minute rate limit.",
        "model_count_note": "41 coding-focused models including S+ tier (DeepSeek, Qwen3, Step Flash).",
        "signup_url": "https://build.nvidia.com",
        "steps": [
            "Go to build.nvidia.com and create an NVIDIA developer account.",
            "Click your profile icon → API Keys → Generate API Key.",
            "Copy the key (starts with 'nvapi-').",
        ],
        "env_var": "NVIDIA_API_KEY",
        "key_format": "nvapi-...",
        "priority": "HIGH — best free tier, most models, fastest.",
    },
    "groq": {
        "name": "Groq",
        "free_tier": "Free tier with rate limits. Known for extremely fast inference (LPU hardware).",
        "model_count_note": "Fast inference for Llama, Mixtral, Gemma models.",
        "signup_url": "https://console.groq.com",
        "steps": [
            "Go to console.groq.com and sign up (Google/GitHub SSO available).",
            "Navigate to API Keys in the left sidebar.",
            "Create a new API key and copy it (starts with 'gsk_').",
        ],
        "env_var": "GROQ_API_KEY",
        "key_format": "gsk_...",
        "priority": "HIGH — extremely fast inference, easy signup.",
    },
    "cerebras": {
        "name": "Cerebras",
        "free_tier": "Free tier available. Wafer-scale hardware, very fast inference.",
        "model_count_note": "Llama and other open models at high speed.",
        "signup_url": "https://cloud.cerebras.ai",
        "steps": [
            "Go to cloud.cerebras.ai and create an account.",
            "Navigate to API Keys section.",
            "Generate and copy your API key.",
        ],
        "env_var": "CEREBRAS_API_KEY",
        "key_format": "csk-...",
        "priority": "MEDIUM — fast inference, smaller model catalog.",
    },
    "sambanova": {
        "name": "SambaNova",
        "free_tier": "Free tier with rate limits.",
        "model_count_note": "Llama and other open models.",
        "signup_url": "https://cloud.sambanova.ai",
        "steps": [
            "Go to cloud.sambanova.ai and sign up.",
            "Navigate to API section.",
            "Generate and copy your API key.",
        ],
        "env_var": "SAMBANOVA_API_KEY",
        "key_format": "standard key",
        "priority": "MEDIUM — decent speed, free tier.",
    },
    "openrouter": {
        "name": "OpenRouter",
        "free_tier": "Some models are free (marked ':free'). Others require credits.",
        "model_count_note": "200+ models aggregated from many providers. 14 free models in our catalog.",
        "signup_url": "https://openrouter.ai",
        "steps": [
            "Go to openrouter.ai and sign up (Google/GitHub SSO available).",
            "Navigate to Keys in your account.",
            "Create an API key and copy it (starts with 'sk-or-').",
        ],
        "env_var": "OPENROUTER_API_KEY",
        "key_format": "sk-or-...",
        "priority": "MEDIUM — many free models, good fallback provider.",
    },
    "huggingface": {
        "name": "Hugging Face Inference",
        "free_tier": "Free tier with rate limits for hosted models.",
        "model_count_note": "Popular open models via Inference API.",
        "signup_url": "https://huggingface.co/settings/tokens",
        "steps": [
            "Go to huggingface.co and create an account.",
            "Navigate to Settings → Access Tokens.",
            "Create a new token with 'read' scope and copy it (starts with 'hf_').",
        ],
        "env_var": "HUGGINGFACE_API_KEY",
        "key_format": "hf_...",
        "priority": "LOW — slower inference, but wide model selection.",
    },
    "deepinfra": {
        "name": "DeepInfra",
        "free_tier": "Free credits on signup. Pay-as-you-go after.",
        "model_count_note": "Wide selection of open models.",
        "signup_url": "https://deepinfra.com",
        "steps": [
            "Go to deepinfra.com and sign up.",
            "Navigate to API Keys in dashboard.",
            "Copy your API key.",
        ],
        "env_var": "DEEPINFRA_API_KEY",
        "key_format": "standard key",
        "priority": "LOW — free credits on signup, not perpetually free.",
    },
    "fireworks": {
        "name": "Fireworks AI",
        "free_tier": "Free tier with rate limits.",
        "model_count_note": "Fast inference, popular open models.",
        "signup_url": "https://fireworks.ai",
        "steps": [
            "Go to fireworks.ai and sign up.",
            "Navigate to API Keys.",
            "Generate and copy your API key (starts with 'fw_').",
        ],
        "env_var": "FIREWORKS_API_KEY",
        "key_format": "fw_...",
        "priority": "LOW — fast, but limited free tier.",
    },
    "codestral": {
        "name": "Codestral (Mistral)",
        "free_tier": "Free access to Codestral coding model.",
        "model_count_note": "Mistral's dedicated coding model.",
        "signup_url": "https://console.mistral.ai",
        "steps": [
            "Go to console.mistral.ai and sign up.",
            "Navigate to API Keys.",
            "Generate a Codestral-specific API key.",
        ],
        "env_var": "CODESTRAL_API_KEY",
        "key_format": "standard key",
        "priority": "MEDIUM — excellent coding model, easy setup.",
    },
    "googleai": {
        "name": "Google AI Studio",
        "free_tier": "Free tier with generous rate limits for Gemini models.",
        "model_count_note": "Gemini Pro and Flash models.",
        "signup_url": "https://aistudio.google.com/apikey",
        "steps": [
            "Go to aistudio.google.com/apikey.",
            "Sign in with Google account.",
            "Click 'Create API key' and copy it.",
        ],
        "env_var": "GOOGLE_AI_API_KEY",
        "key_format": "AIza...",
        "priority": "HIGH — Gemini models are strong, generous free tier.",
    },
    "together": {
        "name": "Together AI",
        "free_tier": "Free credits on signup ($5-25). Pay-as-you-go after.",
        "model_count_note": "Wide selection of open models.",
        "signup_url": "https://api.together.xyz",
        "steps": [
            "Go to api.together.xyz and sign up.",
            "Navigate to Settings → API Keys.",
            "Copy your API key.",
        ],
        "env_var": "TOGETHER_API_KEY",
        "key_format": "standard key",
        "priority": "LOW — free credits on signup, not perpetually free.",
    },
    "siliconflow": {
        "name": "SiliconFlow",
        "free_tier": "Free tier available.",
        "model_count_note": "Chinese and international open models.",
        "signup_url": "https://siliconflow.cn",
        "steps": [
            "Go to siliconflow.cn and sign up.",
            "Navigate to API Keys section.",
            "Generate and copy your API key.",
        ],
        "env_var": "SILICONFLOW_API_KEY",
        "key_format": "sk-...",
        "priority": "LOW — useful for Chinese models like Qwen, DeepSeek.",
    },
    "ollama": {
        "name": "Ollama (local)",
        "free_tier": "Runs on your machine. No API key. Pull models with `ollama pull`.",
        "model_count_note": "Whatever you have pulled; embeddings are skipped.",
        "signup_url": "https://ollama.com/download",
        "steps": [
            "Install Ollama from https://ollama.com/download (or your package manager).",
            "Start the daemon so http://127.0.0.1:11434/api/tags answers.",
            "Pull a chat model, e.g. `ollama pull gemma3:27b` or `ollama pull mistral-small`.",
            "Restart model-radar. No configure_key needed.",
        ],
        "env_var": "OLLAMA_API_KEY",
        "key_format": "none — local, optional dummy key",
        "priority": "HIGH — free local models you already have pulled.",
    },
    "xai": {
        "name": "xAI (API key)",
        "free_tier": "Pay-as-you-go Grok API. Prefer the grok CLI if you have SuperGrok.",
        "model_count_note": "Grok models via api.x.ai.",
        "signup_url": "https://console.x.ai",
        "steps": [
            "Go to console.x.ai and sign in with your X account.",
            "Open API Keys and create a key.",
            "Copy the key and call configure_key(provider='xai', api_key=...).",
        ],
        "env_var": "XAI_API_KEY",
        "key_format": "xai-...",
        "priority": "LOW — only needed if you want the API instead of SuperGrok.",
    },
    "grok": {
        "name": "Grok (Subscription)",
        "free_tier": "Rides your SuperGrok / grok.com subscription. No API key.",
        "model_count_note": "grok-4.6, grok-4.5 via the grok CLI.",
        "signup_url": "https://docs.x.ai/build/overview",
        "steps": [
            "Install the Grok Build CLI from https://docs.x.ai/build/overview (or `grok` on PATH).",
            "Run `grok login` and complete the X OAuth flow.",
            "Verify with `grok models`. model-radar picks it up on the next server start.",
        ],
        "env_var": "",
        "key_format": "none — subscription login",
        "priority": "HIGH — use this if you already pay for SuperGrok.",
    },
    "gemini": {
        "name": "Gemini (Antigravity Subscription)",
        "free_tier": "Rides your Google AI Pro/Ultra or Gemini subscription via Antigravity CLI (`agy`). No API key. The old `gemini` CLI was deprecated June 2026.",
        "model_count_note": "Gemini 3.x plus other models on the Antigravity plan (`agy models`). Codex may appear as an in-app conversation, not always as an `agy` model id.",
        "signup_url": "https://antigravity.google/docs/cli/install",
        "steps": [
            "Install Antigravity CLI: `curl -fsSL https://antigravity.google/cli/install.sh | bash`.",
            "Put `~/.local/bin` on PATH if needed, then run `agy` once and sign in with Google in the browser.",
            "Verify with `agy models`. Restart model-radar so the `gemini` provider appears.",
            "If the splash says Codex is included, use the standalone `codex` CLI for model-radar — `agy models` may not list gpt-5.6-terra.",
        ],
        "env_var": "",
        "key_format": "none — subscription login",
        "priority": "HIGH — use this if you already pay for Gemini / Google AI Pro/Ultra.",
    },
    "claude": {
        "name": "Claude (Subscription)",
        "free_tier": "Rides your Claude Pro/Max subscription via Claude Code. No API key.",
        "model_count_note": "opus / sonnet / haiku aliases.",
        "signup_url": "https://docs.anthropic.com/en/docs/claude-code",
        "steps": [
            "Install Claude Code from https://docs.anthropic.com/en/docs/claude-code.",
            "Run `claude auth login` (or use an existing Claude Code login).",
            "Verify with `claude --version`. Restart model-radar to register it.",
        ],
        "env_var": "",
        "key_format": "none — subscription login",
        "priority": "HIGH — use this if you already pay for Claude Pro/Max.",
    },
    "minimax": {
        "name": "MiniMax",
        "free_tier": "Pay-as-you-go on api.minimax.io. M3 is the current frontier coding/agent model (1M context).",
        "model_count_note": "MiniMax-M3, M2.7, M2.5 and highspeed variants. Live list from GET /v1/models.",
        "signup_url": "https://platform.minimax.io",
        "steps": [
            "Go to platform.minimax.io and create an account.",
            "Open API Keys and create a key.",
            "Call configure_key(provider='minimax', api_key=...).",
            "Do not put this token in ANTHROPIC_AUTH_TOKEN globally — that hijacks Claude Code. MiniMax's Anthropic shim is https://api.minimax.io/anthropic if you want it only in a dedicated Claude Code profile.",
        ],
        "env_var": "MINIMAX_API_KEY",
        "key_format": "sk-cp-... or sk-api-...",
        "priority": "HIGH — first-party MiniMax M3, not the NVIDIA/OpenRouter resale.",
    },
    "codex": {
        "name": "Codex (Subscription)",
        "free_tier": "Rides your ChatGPT Plus/Pro subscription via the Codex CLI. No API key.",
        "model_count_note": "ChatGPT models via `codex`.",
        "signup_url": "https://github.com/openai/codex",
        "steps": [
            "Install the Codex CLI (`npm install -g @openai/codex` or see GitHub).",
            "Run `codex login` and complete the ChatGPT OAuth flow.",
            "Restart model-radar so it registers the binary.",
        ],
        "env_var": "",
        "key_format": "none — subscription login",
        "priority": "HIGH — use this if you already pay for ChatGPT Plus/Pro.",
    },
}

# Providers with no guide yet (uncommon or complex setup)
_NO_GUIDE = {"replicate", "hyperbolic", "scaleway", "cloudflare", "perplexity"}


def get_setup_guide(provider_key: str | None = None) -> dict:
    """
    Get setup instructions for one or all unconfigured providers.

    If provider_key is given, returns guide for that specific provider.
    Otherwise, returns guides for all unconfigured providers, prioritized.
    """
    cfg = load_config()

    if provider_key:
        guide = _GUIDES.get(provider_key)
        if provider_key not in PROVIDERS and provider_key not in CLI_SPEC_BY_KEY:
            available = ", ".join(sorted(set(PROVIDERS) | set(CLI_SPEC_BY_KEY)))
            return {
                "error": f"Unknown provider '{provider_key}'. Available: {available}",
            }
        if not guide:
            return {
                "provider": provider_key,
                "message": f"No setup guide available for {provider_key} yet.",
            }
        if is_cli_provider(provider_key) or provider_key in CLI_SPEC_BY_KEY:
            installed = provider_key in PROVIDERS
            return {
                "provider": provider_key,
                "already_configured": installed,
                "access": "cli",
                **guide,
                "configure_command": (
                    "Already installed — restart model-radar if it is not listed."
                    if installed
                    else "Install the CLI and log in (no API key). Then restart model-radar."
                ),
            }
        has_key = get_api_key(cfg, provider_key) is not None
        return {
            "provider": provider_key,
            "already_configured": has_key,
            **guide,
            "configure_command": f'After obtaining the key, call: configure_key(provider="{provider_key}", api_key="YOUR_KEY")'
            if not has_key else "Already configured.",
        }

    # Return all unconfigured providers, sorted by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    unconfigured = []
    configured = []

    for pkey in PROVIDERS:
        guide = _GUIDES.get(pkey)
        if not guide:
            continue
        entry = {
            "provider": pkey,
            "name": guide["name"],
            "priority": guide["priority"],
            "free_tier": guide["free_tier"],
            "signup_url": guide["signup_url"],
            "access": "cli" if is_cli_provider(pkey) else "api_key",
        }
        if is_cli_provider(pkey) or get_api_key(cfg, pkey) is not None:
            configured.append(pkey)
        else:
            unconfigured.append(entry)

    # Subscription CLIs not on PATH still get a guide so the host can tell the user.
    for spec in CLI_SPEC_BY_KEY.values():
        if spec.key in PROVIDERS:
            continue
        guide = _GUIDES.get(spec.key)
        if not guide:
            continue
        unconfigured.append({
            "provider": spec.key,
            "name": guide["name"],
            "priority": guide["priority"],
            "free_tier": guide["free_tier"],
            "signup_url": guide["signup_url"],
            "access": "cli",
        })

    unconfigured.sort(key=lambda x: priority_order.get(
        x["priority"].split(" ")[0], 9))

    return {
        "configured_providers": configured,
        "unconfigured_count": len(unconfigured),
        "setup_instructions": (
            "To add a provider, direct your user to the signup_url below. "
            "Once they have an API key, call configure_key(provider, api_key) to save it. "
            "Providers marked HIGH priority offer the best free tiers and should be set up first."
        ),
        "unconfigured": unconfigured,
    }
