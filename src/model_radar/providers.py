"""
Provider and model definitions for model-radar.

Ported from free-coding-models sources.js by vava-nessa.
Each model: (model_id, display_label, tier, swe_score, context_window)

Tier scale (based on SWE-bench Verified):
  S+: 70%+    (elite frontier coders)
  S:  60-70%  (excellent)
  A+: 50-60%  (great)
  A:  40-50%  (good)
  A-: 35-40%  (decent)
  B+: 30-35%  (average)
  B:  20-30%  (below average)
  C:  <20%    (lightweight/edge)

Source: https://www.swebench.com
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Model:
    model_id: str
    label: str
    tier: str
    swe_score: str
    context: str
    provider: str
    is_free: bool | None = None  # True=free, False=paid, None=unknown (from API or heuristic)


@dataclass(frozen=True, slots=True)
class Provider:
    key: str
    name: str
    url: str
    env_vars: tuple[str, ...]
    models: tuple[tuple[str, str, str, str, str], ...]
    kind: str = "https"  # "https" (default) or "cli" (rides a user subscription)
    cmd: str | None = None  # for cli: command name (e.g. "grok")
    cmd_args: tuple[str, ...] = ()  # for cli: extra args (e.g. ("--output-format", "json"))
    prompt_via: str = "arg"  # for cli: "arg" (prompt_flag + prompt) or "stdin"
    model_flag: str = "-m"  # for cli: how to pass model id
    prompt_flag: str = "-p"  # for cli: headless/single-turn flag (grok/gemini/claude)


# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, Provider] = {}

# Frozen seed tuples from the first _p() for each key. Live refresh overwrites
# PROVIDERS[key].models but must not lose SWE-bench overlays for known ids.
SEED_MODELS: dict[str, tuple] = {}


def _p(key: str, name: str, url: str | None, env_vars: tuple[str, ...], models: tuple,
       *, kind: str = "https", cmd: str | None = None, cmd_args: tuple[str, ...] = (),
       prompt_via: str = "arg", model_flag: str = "-m", prompt_flag: str = "-p"):
    if key not in SEED_MODELS:
        SEED_MODELS[key] = models
    PROVIDERS[key] = Provider(
        key=key, name=name, url=url, env_vars=env_vars, models=models,
        kind=kind, cmd=cmd, cmd_args=cmd_args, prompt_via=prompt_via,
        model_flag=model_flag, prompt_flag=prompt_flag,
    )


def set_provider_models(key: str, models: tuple) -> None:
    """Replace a provider's model tuple (live catalog). Other fields stay put."""
    old = PROVIDERS[key]
    PROVIDERS[key] = Provider(
        key=old.key, name=old.name, url=old.url, env_vars=old.env_vars,
        models=models, kind=old.kind, cmd=old.cmd, cmd_args=old.cmd_args,
        prompt_via=old.prompt_via, model_flag=old.model_flag,
        prompt_flag=old.prompt_flag,
    )


# --- NVIDIA NIM ---
_p("nvidia", "NIM", "https://integrate.api.nvidia.com/v1/chat/completions",
   ("NVIDIA_API_KEY",), (
    ("minimaxai/minimax-m3", "MiniMax M3", "S+", "74.0%", "1M"),
    ("moonshotai/kimi-k2.6", "Kimi K2.6", "S+", "76.8%", "128k"),
    ("z-ai/glm-5.2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("stepfun-ai/step-3.7-flash", "Step 3.7 Flash", "S+", "74.4%", "256k"),
    ("nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra 550B", "S+", "70.0%", "128k"),
    ("deepseek-ai/deepseek-v4-flash-0731", "DeepSeek V4 Flash", "S+", "73.0%", "128k"),
    ("nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super 120B", "S", "60.0%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("nvidia/llama-3.1-nemotron-ultra-253b-v1", "Nemotron Ultra 253B", "A+", "56.0%", "128k"),
    ("google/gemma-4-31b-it", "Gemma 4 31B", "A+", "50.0%", "128k"),
    ("nvidia/nemotron-3-nano-30b-a3b", "Nemotron 3 Nano 30B", "A", "43.0%", "128k"),
    ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "Nemotron Super 49B", "A", "49.0%", "128k"),
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("meta/llama-3.3-70b-instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("meta/llama-3.1-8b-instruct", "Llama 3.1 8B", "B", "28.8%", "128k"),
))

# --- Groq ---
_p("groq", "Groq", "https://api.groq.com/openai/v1/chat/completions",
   ("GROQ_API_KEY",), (
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("qwen/qwen3.6-27b", "Qwen3.6 27B", "A+", "50.0%", "131k"),
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("llama-3.3-70b-versatile", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("llama-3.1-8b-instant", "Llama 3.1 8B", "B", "28.8%", "128k"),
))

# --- Cerebras ---
_p("cerebras", "Cerebras", "https://api.cerebras.ai/v1/chat/completions",
   ("CEREBRAS_API_KEY",), (
    ("gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("gemma-4-31b", "Gemma 4 31B", "A+", "50.0%", "128k"),
    ("zai-glm-4.7", "Z.ai GLM 4.7", "S+", "73.8%", "128k"),
))

# --- SambaNova ---
_p("sambanova", "SambaNova", "https://api.sambanova.ai/v1/chat/completions",
   ("SAMBANOVA_API_KEY",), (
    ("DeepSeek-V3.2", "DeepSeek V3.2", "S+", "73.1%", "128k"),
    ("MiniMax-M2.7", "MiniMax M2.7", "S+", "74.0%", "200k"),
    ("DeepSeek-V3.1", "DeepSeek V3.1", "S", "62.0%", "128k"),
    ("gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("gemma-4-31B-it", "Gemma 4 31B", "A+", "50.0%", "128k"),
    ("Meta-Llama-3.3-70B-Instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
))

# --- OpenRouter ---
_p("openrouter", "OpenRouter", "https://openrouter.ai/api/v1/chat/completions",
   ("OPENROUTER_API_KEY",), (
    ("nvidia/nemotron-3-ultra-550b-a55b:free", "Nemotron 3 Ultra 550B", "S+", "70.0%", "128k"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "Nemotron Super 120B", "S", "60.0%", "128k"),
    ("google/gemma-4-31b-it:free", "Gemma 4 31B", "A+", "50.0%", "128k"),
    ("nvidia/nemotron-3-nano-30b-a3b:free", "Nemotron Nano 30B", "A", "43.0%", "128k"),
    ("openai/gpt-oss-20b:free", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("google/gemma-4-26b-a4b-it:free", "Gemma 4 26B", "A", "40.0%", "128k"),
    ("poolside/laguna-s-2.1:free", "Laguna S 2.1", "A", "40.0%", "128k"),
    ("nvidia/nemotron-nano-9b-v2:free", "Nemotron Nano 9B", "B", "28.0%", "128k"),
))

# --- Hugging Face ---
_p("huggingface", "Hugging Face", "https://router.huggingface.co/v1/chat/completions",
   ("HUGGINGFACE_API_KEY", "HF_TOKEN"), (
    # S+ tier
    ("zai-org/GLM-5", "GLM 5", "S+", "77.8%", "200k"),
    ("moonshotai/Kimi-K2.5", "Kimi K2.5", "S+", "76.8%", "128k"),
    ("MiniMaxAI/MiniMax-M2.5", "MiniMax M2.5", "S+", "74.0%", "200k"),
    ("MiniMaxAI/MiniMax-M2.1", "MiniMax M2.1", "S+", "74.0%", "200k"),
    ("stepfun-ai/Step-3.5-Flash", "Step 3.5 Flash", "S+", "74.4%", "256k"),
    ("Qwen/Qwen3-Coder-480B-A35B-Instruct", "Qwen3 Coder 480B", "S+", "70.6%", "256k"),
    ("deepseek-ai/DeepSeek-V3.2", "DeepSeek V3.2", "S+", "73.1%", "128k"),
    ("Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("zai-org/GLM-4.7", "GLM 4.7", "S+", "73.8%", "200k"),
    # S tier
    ("deepseek-ai/DeepSeek-V3.1-Terminus", "DeepSeek V3.1 Term", "S", "68.4%", "128k"),
    ("moonshotai/Kimi-K2-Instruct-0905", "Kimi K2 Instruct", "S", "65.8%", "131k"),
    ("Qwen/Qwen3-Next-80B-A3B-Instruct", "Qwen3 80B Instruct", "S", "65.0%", "128k"),
    ("deepseek-ai/DeepSeek-V3.1", "DeepSeek V3.1", "S", "62.0%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("deepseek-ai/DeepSeek-R1-0528", "DeepSeek R1 0528", "S", "61.0%", "128k"),
    ("deepseek-ai/DeepSeek-R1", "DeepSeek R1", "S", "61.0%", "128k"),
    ("MiniMaxAI/MiniMax-M2", "MiniMax M2", "S", "69.4%", "128k"),
    # A+ tier
    ("MiniMaxAI/MiniMax-M3", "MiniMax M3", "S+", "74.0%", "1M"),
    ("MiniMaxAI/MiniMax-M2.7", "MiniMax M2.7", "S+", "74.0%", "1M"),
    ("moonshotai/Kimi-K3", "Kimi K3", "S+", "76.8%", "128k"),
    ("zai-org/GLM-5.2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("deepseek-ai/DeepSeek-V4-Pro", "DeepSeek V4 Pro", "S+", "73.0%", "128k"),
    ("Qwen/Qwen3-32B", "Qwen3 32B", "A+", "50.0%", "128k"),
    # A tier
    ("meta-llama/Llama-4-Scout-17B-16E-Instruct", "Llama 4 Scout", "A", "44.0%", "10M"),
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen2.5 Coder 32B", "A", "46.0%", "32k"),
    ("deepseek-ai/DeepSeek-R1-Distill-Llama-70B", "R1 Distill 70B", "A", "43.9%", "128k"),
    # A- tier
    ("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    # B tier
    ("meta-llama/Llama-3.1-8B-Instruct", "Llama 3.1 8B", "B", "28.8%", "128k"),
))

# --- Replicate ---
_p("replicate", "Replicate", "https://api.replicate.com/v1/predictions",
   ("REPLICATE_API_TOKEN",), (
    ("codellama/CodeLlama-70b-Instruct-hf", "CodeLlama 70B", "A-", "39.0%", "16k"),
))

# --- DeepInfra ---
_p("deepinfra", "DeepInfra", "https://api.deepinfra.com/v1/openai/chat/completions",
   ("DEEPINFRA_API_KEY", "DEEPINFRA_TOKEN"), (
    ("zai-org/GLM-5.2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("moonshotai/Kimi-K3", "Kimi K3", "S+", "76.8%", "128k"),
    ("MiniMaxAI/MiniMax-M3", "MiniMax M3", "S+", "74.0%", "1M"),
    ("deepseek-ai/DeepSeek-V4-Pro", "DeepSeek V4 Pro", "S+", "73.0%", "128k"),
    ("Qwen/Qwen3.5-397B-A17B", "Qwen3.5 400B", "S", "68.0%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B", "A-", "39.5%", "128k"),
))

# --- Fireworks ---
_p("fireworks", "Fireworks", "https://api.fireworks.ai/inference/v1/chat/completions",
   ("FIREWORKS_API_KEY",), (
    ("accounts/fireworks/models/kimi-k3", "Kimi K3", "S+", "76.8%", "128k"),
    ("accounts/fireworks/models/glm-5p2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("accounts/fireworks/models/minimax-m3", "MiniMax M3", "S+", "74.0%", "1M"),
    ("accounts/fireworks/models/deepseek-v4-pro", "DeepSeek V4 Pro", "S+", "73.0%", "128k"),
    ("accounts/fireworks/models/kimi-k2p6", "Kimi K2.6", "S+", "76.8%", "128k"),
    ("accounts/fireworks/models/minimax-m2p7", "MiniMax M2.7", "S+", "74.0%", "1M"),
    ("accounts/fireworks/models/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("accounts/fireworks/models/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
))

# --- Mistral (Codestral) ---
_p("codestral", "Mistral", "https://api.mistral.ai/v1/chat/completions",
   ("CODESTRAL_API_KEY",), (
    ("mistral-large-latest", "Mistral Large", "S", "60.7%", "128k"),
    ("glm-5-2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("mistral-medium-latest", "Mistral Medium", "A+", "55.0%", "128k"),
    ("devstral-latest", "Devstral", "A+", "55.2%", "128k"),
    ("mistral-small-latest", "Mistral Small", "A", "40.0%", "128k"),
    ("codestral-latest", "Codestral", "B+", "34.0%", "256k"),
    ("magistral-small-latest", "Magistral Small", "A", "45.0%", "40k"),
    ("ministral-8b-latest", "Ministral 8B", "B", "25.0%", "128k"),
))

# --- Hyperbolic ---
_p("hyperbolic", "Hyperbolic", "https://api.hyperbolic.xyz/v1/chat/completions",
   ("HYPERBOLIC_API_KEY",), (
    ("Qwen/Qwen3-Coder-480B-A35B-Instruct", "Qwen3 Coder 480B", "S+", "70.6%", "256k"),
    ("deepseek-ai/DeepSeek-R1-0528", "DeepSeek R1 0528", "S", "61.0%", "128k"),
    ("deepseek-ai/DeepSeek-R1", "DeepSeek R1", "S", "61.0%", "128k"),
    ("deepseek-ai/DeepSeek-V3-0324", "DeepSeek V3 0324", "S", "62.0%", "128k"),
    ("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
))

# --- Scaleway ---
_p("scaleway", "Scaleway", "https://api.scaleway.ai/v1/chat/completions",
   ("SCALEWAY_API_KEY",), (
    ("glm-5.2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("qwen3-235b-a22b-instruct-2507", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("deepseek-v4-flash-0731", "DeepSeek V4 Flash", "S+", "73.0%", "128k"),
    ("qwen3.5-397b-a17b", "Qwen3.5 400B", "S", "68.0%", "128k"),
    ("gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("qwen3-coder-30b-a3b-instruct", "Qwen3 Coder 30B", "A+", "55.0%", "32k"),
    ("gemma-4-26b-a4b-it", "Gemma 4 26B", "A", "40.0%", "128k"),
    ("llama-3.3-70b-instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("mistral-small-3.2-24b-instruct-2506", "Mistral Small 3.2", "B+", "30.0%", "128k"),
))

# --- Google AI ---
_p("googleai", "Google AI", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
   ("GOOGLE_API_KEY",), (
    ("gemini-3.1-pro-preview", "Gemini 3.1 Pro", "S+", "70.0%", "1M"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro", "S+", "70.0%", "1M"),
    ("gemini-3.7-flash", "Gemini 3.7 Flash", "S", "60.0%", "1M"),
    ("gemini-3.6-flash", "Gemini 3.6 Flash", "S", "60.0%", "1M"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash", "S", "60.0%", "1M"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash", "S", "60.0%", "1M"),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite", "A+", "55.0%", "1M"),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite", "A+", "55.0%", "1M"),
))

# --- SiliconFlow ---
_p("siliconflow", "SiliconFlow", "https://api.siliconflow.com/v1/chat/completions",
   ("SILICONFLOW_API_KEY",), (
    ("zai-org/GLM-5.2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("zai-org/GLM-5", "GLM 5", "S+", "77.8%", "200k"),
    ("moonshotai/Kimi-K3", "Kimi K3", "S+", "76.8%", "128k"),
    ("moonshotai/Kimi-K2.6", "Kimi K2.6", "S+", "76.8%", "128k"),
    ("moonshotai/Kimi-K2.5", "Kimi K2.5", "S+", "76.8%", "128k"),
    ("MiniMaxAI/MiniMax-M3", "MiniMax M3", "S+", "74.0%", "1M"),
    ("MiniMaxAI/MiniMax-M2.5", "MiniMax M2.5", "S+", "74.0%", "200k"),
    ("deepseek-ai/DeepSeek-V4-Pro", "DeepSeek V4 Pro", "S+", "73.0%", "128k"),
    ("deepseek-ai/DeepSeek-V3.2", "DeepSeek V3.2", "S+", "73.1%", "128k"),
    ("Qwen/Qwen3.5-397B-A17B", "Qwen3.5 400B", "S", "68.0%", "128k"),
    ("deepseek-ai/DeepSeek-V3.1", "DeepSeek V3.1", "S", "62.0%", "128k"),
    ("deepseek-ai/DeepSeek-R1", "DeepSeek R1", "S", "61.0%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("Qwen/Qwen3-Coder-30B-A3B-Instruct", "Qwen3 Coder 30B", "A+", "55.0%", "32k"),
    ("Qwen/Qwen3.6-27B", "Qwen3.6 27B", "A+", "50.0%", "128k"),
    ("Qwen/Qwen3-32B", "Qwen3 32B", "A+", "50.0%", "128k"),
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
))

# --- Together AI ---
_p("together", "Together AI", "https://api.together.xyz/v1/chat/completions",
   ("TOGETHER_API_KEY",), (
    ("moonshotai/Kimi-K2.5", "Kimi K2.5", "S+", "76.8%", "128k"),
    ("Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8", "Qwen3 Coder 480B", "S+", "70.6%", "256k"),
    ("deepseek-ai/DeepSeek-V3.1", "DeepSeek V3.1", "S", "62.0%", "128k"),
    ("deepseek-ai/DeepSeek-R1", "DeepSeek R1", "S", "61.0%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B", "A-", "39.5%", "128k"),
))

# --- Cloudflare ---
_p("cloudflare", "Cloudflare AI",
   "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions",
   ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_KEY"), (
    ("@cf/openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("@cf/nvidia/nemotron-3-120b-a12b", "Nemotron 3 120B", "A+", "50.0%", "128k"),
    ("@cf/qwen/qwen2.5-coder-32b-instruct", "Qwen2.5 Coder 32B", "A", "46.0%", "32k"),
    ("@cf/qwen/qwq-32b", "QwQ 32B", "A", "46.0%", "32k"),
    ("@cf/deepseek-ai/deepseek-r1-distill-qwen-32b", "R1 Distill 32B", "A", "43.9%", "128k"),
    ("@cf/openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("@cf/mistralai/mistral-small-3.1-24b-instruct", "Mistral Small 3.1 24B", "A", "40.0%", "128k"),
    ("@cf/meta/llama-3.3-70b-instruct-fp8-fast", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("@cf/meta/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B", "A-", "38.0%", "512k"),
    ("@cf/qwen/qwen3-30b-a3b-fp8", "Qwen3 30B MoE", "A-", "36.0%", "128k"),
    ("@cf/google/gemma-3-12b-it", "Gemma 3 12B", "B+", "34.0%", "128k"),
    ("@cf/zai-org/glm-4.7-flash", "GLM 4.7 Flash", "B+", "30.0%", "128k"),
    ("@cf/ibm-granite/granite-4.0-h-micro", "Granite 4.0 Micro", "B", "25.0%", "128k"),
    ("@cf/meta/llama-3.1-8b-instruct", "Llama 3.1 8B", "B", "28.8%", "128k"),
))

# --- xAI ---
_p("xai", "xAI", "https://api.x.ai/v1/chat/completions",
   ("XAI_API_KEY",), (
    ("grok-4.6", "Grok 4.6", "S+", "72.0%", "256k"),
    ("grok-4", "Grok 4", "S+", "72.0%", "256k"),
    ("grok-3-mini", "Grok 3 Mini", "A+", "55.0%", "128k"),
))

# --- Inference.net ---
_p("inferencenet", "Inference.net", "https://api.inference.net/v1/chat/completions",
   ("INFERENCE_NET_API_KEY",), (
    ("kimi-k3", "Kimi K3", "S+", "76.8%", "128k"),
    ("glm-5.2", "GLM 5.2", "S+", "77.8%", "200k"),
    ("deepseek-v4-pro", "DeepSeek V4 Pro", "S+", "73.0%", "128k"),
    ("gemini-3.1-pro-preview", "Gemini 3.1 Pro", "S+", "70.0%", "1M"),
    ("grok-4.5", "Grok 4.5", "S+", "70.0%", "256k"),
    ("gpt-5.6-terra", "GPT-5.6 Terra", "S+", "72.0%", "256k"),
    ("qwen3.7-plus", "Qwen3.7 Plus", "S", "65.0%", "128k"),
    ("gemini-3.6-flash", "Gemini 3.6 Flash", "S", "60.0%", "1M"),
))

# --- SEA-LION ---
_p("sealion", "SEA-LION", "https://api.sea-lion.ai/v1/chat/completions",
   ("SEALION_API_KEY",), (
    ("aisingapore/Qwen-SEA-LION-v4.5-27B-IT", "Qwen SEA-LION v4.5 27B", "A", "40.0%", "128k"),
    ("aisingapore/Qwen-SEA-LION-v4-32B-IT", "Qwen SEA-LION v4 32B", "A", "40.0%", "128k"),
    ("aisingapore/Gemma-SEA-LION-v4-27B-IT", "Gemma SEA-LION v4 27B", "B+", "30.0%", "128k"),
    ("aisingapore/Llama-SEA-LION-v3-70B-IT", "Llama SEA-LION v3 70B", "A-", "35.0%", "128k"),
))

# --- Ollama (local, no key) ---
# Catalog is whatever THIS machine has pulled. Empty until /api/tags answers.
_p("ollama", "Ollama", "http://127.0.0.1:11434/v1/chat/completions",
   ("OLLAMA_API_KEY",), ())

# --- MiniMax (api.minimax.io; same token works on /anthropic for Claude Code) ---
_p("minimax", "MiniMax", "https://api.minimax.io/v1/chat/completions",
   ("MINIMAX_API_KEY",), (
    ("MiniMax-M3", "MiniMax M3", "S+", "74.0%", "1M"),
    ("MiniMax-M2.7", "MiniMax M2.7", "S+", "74.0%", "1M"),
    ("MiniMax-M2.7-highspeed", "MiniMax M2.7 Highspeed", "S+", "74.0%", "1M"),
    ("MiniMax-M2.5", "MiniMax M2.5", "S+", "74.0%", "200k"),
    ("MiniMax-M2.5-highspeed", "MiniMax M2.5 Highspeed", "S", "69.4%", "200k"),
    ("MiniMax-M2.1", "MiniMax M2.1", "S+", "74.0%", "200k"),
    ("MiniMax-M2.1-highspeed", "MiniMax M2.1 Highspeed", "S", "69.4%", "200k"),
    ("MiniMax-M2", "MiniMax M2", "S", "69.4%", "128k"),
))

# --- Perplexity ---
_p("perplexity", "Perplexity", "https://api.perplexity.ai/chat/completions",
   ("PERPLEXITY_API_KEY", "PPLX_API_KEY"), (
    ("sonar-reasoning-pro", "Sonar Reasoning Pro", "A+", "50.0%", "128k"),
    ("sonar-reasoning", "Sonar Reasoning", "A", "45.0%", "128k"),
    ("sonar-pro", "Sonar Pro", "B+", "32.0%", "128k"),
    ("sonar", "Sonar", "B", "25.0%", "128k"),
))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_ollama_embedding(name: str) -> bool:
    """True if an Ollama tag is an embedding model, not a chat model."""
    lower = (name or "").lower()
    return any(tok in lower for tok in ("embed", "bge-", "e5-", "minilm", "nomic-embed"))


def refresh_ollama_catalog_from_daemon(timeout: float = 1.5) -> int:
    """Replace the ollama seed with whatever /api/tags reports. Returns model count."""
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=timeout) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return 0
    rows = []
    for item in data.get("models") or []:
        mid = item.get("name") or item.get("model") or ""
        if not mid or is_ollama_embedding(mid):
            continue
        rows.append((mid, mid, "A", "", "128k"))
    if not rows:
        return 0
    models = tuple(rows)
    set_provider_models("ollama", models)
    try:
        from .db import replace_provider_models
        replace_provider_models("ollama", [
            (mid, label, tier, swe, ctx, True) for mid, label, tier, swe, ctx in models
        ])
    except Exception:
        pass
    return len(rows)


def _model_id_suggests_free(model_id: str) -> bool | None:
    """Return True if model_id suggests free tier, False if paid, None if unknown."""
    if not model_id:
        return None
    lower = model_id.lower()
    if ":free" in lower or "-free" in lower or lower.endswith("free"):
        return True
    return None


# ---------------------------------------------------------------------------
# Tier ordering for sorting/filtering
# ---------------------------------------------------------------------------

TIER_ORDER = {"S+": 0, "S": 1, "A+": 2, "A": 3, "A-": 4, "B+": 5, "B": 6, "C": 7}

ALL_TIERS = tuple(TIER_ORDER.keys())


def get_all_models() -> list[Model]:
    """Flatten all provider models into a single list."""
    models = []
    for pkey, prov in PROVIDERS.items():
        for model_id, label, tier, swe, ctx in prov.models:
            is_free = _model_id_suggests_free(model_id)
            if is_free is None and getattr(prov, "kind", "https") == "cli":
                is_free = True  # subscription CLI = free to the user
            if is_free is None and pkey == "ollama":
                is_free = True  # local Ollama = free to the user
            models.append(Model(
                model_id=model_id, label=label, tier=tier,
                swe_score=swe, context=ctx, provider=pkey,
                is_free=is_free,
            ))
    return models


def filter_models(
    tier: str | None = None,
    provider: str | None = None,
    min_tier: str | None = None,
) -> list[Model]:
    """Filter models by exact tier, provider, or minimum tier."""
    models = get_all_models()
    if provider:
        models = [m for m in models if m.provider == provider]
    if tier:
        models = [m for m in models if m.tier == tier]
    elif min_tier and min_tier in TIER_ORDER:
        max_ord = TIER_ORDER[min_tier]
        models = [m for m in models if TIER_ORDER.get(m.tier, 99) <= max_ord]
    return models


# ---------------------------------------------------------------------------
# CLI providers — subscription riders, auto-detected via PATH (grok, agy, claude, codex)
# ---------------------------------------------------------------------------
# This must come AFTER all static _p() calls so it can safely overwrite.
# Wrapped in try/except so the module loads even if PATH detection errors.
from .cli_provider import register_cli_providers as _register_cli_providers

try:
    _register_cli_providers()
except Exception:
    # CLI providers are optional; don't crash static imports.
    pass

try:
    refresh_ollama_catalog_from_daemon()
except Exception:
    pass
