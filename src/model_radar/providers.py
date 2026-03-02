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


# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, Provider] = {}


def _p(key: str, name: str, url: str, env_vars: tuple[str, ...], models: tuple):
    PROVIDERS[key] = Provider(key=key, name=name, url=url, env_vars=env_vars, models=models)


# --- NVIDIA NIM ---
_p("nvidia", "NIM", "https://integrate.api.nvidia.com/v1/chat/completions",
   ("NVIDIA_API_KEY",), (
    # S+ tier
    ("deepseek-ai/deepseek-v3.2", "DeepSeek V3.2", "S+", "73.1%", "128k"),
    ("moonshotai/kimi-k2.5", "Kimi K2.5", "S+", "76.8%", "128k"),
    ("z-ai/glm5", "GLM 5", "S+", "77.8%", "128k"),
    ("z-ai/glm4.7", "GLM 4.7", "S+", "73.8%", "200k"),
    ("moonshotai/kimi-k2-thinking", "Kimi K2 Thinking", "S+", "71.3%", "256k"),
    ("minimaxai/minimax-m2.1", "MiniMax M2.1", "S+", "74.0%", "200k"),
    ("stepfun-ai/step-3.5-flash", "Step 3.5 Flash", "S+", "74.4%", "256k"),
    ("qwen/qwen3-coder-480b-a35b-instruct", "Qwen3 Coder 480B", "S+", "70.6%", "256k"),
    ("qwen/qwen3-235b-a22b", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("mistralai/devstral-2-123b-instruct-2512", "Devstral 2 123B", "S+", "72.2%", "256k"),
    # S tier
    ("deepseek-ai/deepseek-v3.1-terminus", "DeepSeek V3.1 Term", "S", "68.4%", "128k"),
    ("moonshotai/kimi-k2-instruct", "Kimi K2 Instruct", "S", "65.8%", "128k"),
    ("minimaxai/minimax-m2", "MiniMax M2", "S", "69.4%", "128k"),
    ("qwen/qwen3-next-80b-a3b-thinking", "Qwen3 80B Thinking", "S", "68.0%", "128k"),
    ("qwen/qwen3-next-80b-a3b-instruct", "Qwen3 80B Instruct", "S", "65.0%", "128k"),
    ("qwen/qwen3.5-397b-a17b", "Qwen3.5 400B VLM", "S", "68.0%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("meta/llama-4-maverick-17b-128e-instruct", "Llama 4 Maverick", "S", "62.0%", "1M"),
    ("deepseek-ai/deepseek-v3.1", "DeepSeek V3.1", "S", "62.0%", "128k"),
    # A+ tier
    ("nvidia/llama-3.1-nemotron-ultra-253b-v1", "Nemotron Ultra 253B", "A+", "56.0%", "128k"),
    ("mistralai/mistral-large-3-675b-instruct-2512", "Mistral Large 675B", "A+", "58.0%", "256k"),
    ("qwen/qwq-32b", "QwQ 32B", "A+", "50.0%", "131k"),
    ("igenius/colosseum_355b_instruct_16k", "Colosseum 355B", "A+", "52.0%", "16k"),
    # A tier
    ("mistralai/mistral-medium-3-instruct", "Mistral Medium 3", "A", "48.0%", "128k"),
    ("mistralai/magistral-small-2506", "Magistral Small", "A", "45.0%", "32k"),
    ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "Nemotron Super 49B", "A", "49.0%", "128k"),
    ("nvidia/nemotron-3-nano-30b-a3b", "Nemotron Nano 30B", "A", "43.0%", "128k"),
    ("deepseek-ai/deepseek-r1-distill-qwen-32b", "R1 Distill 32B", "A", "43.9%", "128k"),
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("qwen/qwen2.5-coder-32b-instruct", "Qwen2.5 Coder 32B", "A", "46.0%", "32k"),
    # A- tier
    ("meta/llama-3.3-70b-instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("deepseek-ai/deepseek-r1-distill-qwen-14b", "R1 Distill 14B", "A-", "37.7%", "64k"),
    ("bytedance/seed-oss-36b-instruct", "Seed OSS 36B", "A-", "38.0%", "32k"),
    ("stockmark/stockmark-2-100b-instruct", "Stockmark 100B", "A-", "36.0%", "32k"),
    # B+ tier
    ("mistralai/mixtral-8x22b-instruct-v0.1", "Mixtral 8x22B", "B+", "32.0%", "64k"),
    ("mistralai/ministral-14b-instruct-2512", "Ministral 14B", "B+", "34.0%", "32k"),
    # B tier
    ("deepseek-ai/deepseek-r1-distill-llama-8b", "R1 Distill 8B", "B", "28.2%", "32k"),
    ("deepseek-ai/deepseek-r1-distill-qwen-7b", "R1 Distill 7B", "B", "22.6%", "32k"),
    # C tier
    ("google/gemma-2-9b-it", "Gemma 2 9B", "C", "18.0%", "8k"),
    ("microsoft/phi-3.5-mini-instruct", "Phi 3.5 Mini", "C", "12.0%", "128k"),
    ("microsoft/phi-4-mini-instruct", "Phi 4 Mini", "C", "14.0%", "128k"),
))

# --- Groq ---
_p("groq", "Groq", "https://api.groq.com/openai/v1/chat/completions",
   ("GROQ_API_KEY",), (
    ("llama-3.3-70b-versatile", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("meta-llama/llama-4-scout-17b-16e-preview", "Llama 4 Scout", "A", "44.0%", "10M"),
    ("meta-llama/llama-4-maverick-17b-128e-preview", "Llama 4 Maverick", "S", "62.0%", "1M"),
    ("deepseek-r1-distill-llama-70b", "R1 Distill 70B", "A", "43.9%", "128k"),
    ("qwen-qwq-32b", "QwQ 32B", "A+", "50.0%", "131k"),
    ("moonshotai/kimi-k2-instruct", "Kimi K2 Instruct", "S", "65.8%", "131k"),
    ("llama-3.1-8b-instant", "Llama 3.1 8B", "B", "28.8%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("qwen/qwen3-32b", "Qwen3 32B", "A+", "50.0%", "131k"),
))

# --- Cerebras ---
_p("cerebras", "Cerebras", "https://api.cerebras.ai/v1/chat/completions",
   ("CEREBRAS_API_KEY",), (
    ("qwen-3-235b-a22b-instruct-2507", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("zai-glm-4.7", "GLM 4.7", "S+", "73.8%", "200k"),
    ("gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("llama3.1-8b", "Llama 3.1 8B", "B", "28.8%", "128k"),
))

# --- SambaNova ---
_p("sambanova", "SambaNova", "https://api.sambanova.ai/v1/chat/completions",
   ("SAMBANOVA_API_KEY",), (
    # S+ tier
    ("DeepSeek-V3.2", "DeepSeek V3.2", "S+", "73.1%", "128k"),
    ("Qwen3-235B", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("MiniMax-M2.5", "MiniMax M2.5", "S+", "74.0%", "200k"),
    # S tier
    ("DeepSeek-V3.1-Terminus", "DeepSeek V3.1 Term", "S", "68.4%", "128k"),
    ("DeepSeek-V3.1", "DeepSeek V3.1", "S", "62.0%", "128k"),
    ("DeepSeek-V3-0324", "DeepSeek V3 0324", "S", "62.0%", "128k"),
    ("Llama-4-Maverick-17B-128E-Instruct", "Llama 4 Maverick", "S", "62.0%", "1M"),
    ("DeepSeek-R1-0528", "DeepSeek R1 0528", "S", "61.0%", "128k"),
    ("gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    # A+ tier
    ("Qwen3-32B", "Qwen3 32B", "A+", "50.0%", "128k"),
    # A tier
    ("DeepSeek-R1-Distill-Llama-70B", "R1 Distill 70B", "A", "43.9%", "128k"),
    # A- tier
    ("Meta-Llama-3.3-70B-Instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("Llama-3.3-Swallow-70B-Instruct-v0.4", "Llama Swallow 70B", "A-", "38.0%", "128k"),
    # B tier
    ("Meta-Llama-3.1-8B-Instruct", "Llama 3.1 8B", "B", "28.8%", "128k"),
))

# --- OpenRouter ---
_p("openrouter", "OpenRouter", "https://openrouter.ai/api/v1/chat/completions",
   ("OPENROUTER_API_KEY",), (
    ("qwen/qwen3-coder:480b-free", "Qwen3 Coder 480B", "S+", "70.6%", "256k"),
    ("mistralai/devstral-2-free", "Devstral 2", "S+", "72.2%", "256k"),
    ("mimo-v2-flash-free", "Mimo V2 Flash", "A", "45.0%", "128k"),
    ("stepfun/step-3.5-flash:free", "Step 3.5 Flash", "S+", "74.4%", "256k"),
    ("deepseek/deepseek-r1-0528:free", "DeepSeek R1 0528", "S", "61.0%", "128k"),
    ("qwen/qwen3-next-80b-a3b-instruct:free", "Qwen3 80B Instruct", "S", "65.0%", "128k"),
    ("openai/gpt-oss-120b:free", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("openai/gpt-oss-20b:free", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("nvidia/nemotron-3-nano-30b-a3b:free", "Nemotron Nano 30B", "A", "43.0%", "128k"),
    ("meta-llama/llama-3.3-70b-instruct:free", "Llama 3.3 70B", "A-", "39.5%", "128k"),
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
    ("Qwen/QwQ-32B", "QwQ 32B", "A+", "50.0%", "131k"),
    ("Qwen/Qwen3-32B", "Qwen3 32B", "A+", "50.0%", "128k"),
    # A tier
    ("meta-llama/Llama-4-Maverick-17B-128E-Instruct", "Llama 4 Maverick", "S", "62.0%", "1M"),
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
    ("mistralai/Mixtral-8x22B-Instruct-v0.1", "Mixtral Code", "B+", "32.0%", "64k"),
    ("meta-llama/Meta-Llama-3.1-70B-Instruct", "Llama 3.1 70B", "A-", "39.5%", "128k"),
))

# --- Fireworks ---
_p("fireworks", "Fireworks", "https://api.fireworks.ai/inference/v1/chat/completions",
   ("FIREWORKS_API_KEY",), (
    ("accounts/fireworks/models/deepseek-v3", "DeepSeek V3", "S", "62.0%", "128k"),
    ("accounts/fireworks/models/deepseek-r1", "DeepSeek R1", "S", "61.0%", "128k"),
))

# --- Codestral ---
_p("codestral", "Codestral", "https://codestral.mistral.ai/v1/chat/completions",
   ("CODESTRAL_API_KEY",), (
    ("codestral-latest", "Codestral", "B+", "34.0%", "256k"),
))

# --- Hyperbolic ---
_p("hyperbolic", "Hyperbolic", "https://api.hyperbolic.xyz/v1/chat/completions",
   ("HYPERBOLIC_API_KEY",), (
    ("qwen/qwen3-coder-480b-a35b-instruct", "Qwen3 Coder 480B", "S+", "70.6%", "256k"),
    ("deepseek-ai/DeepSeek-R1-0528", "DeepSeek R1 0528", "S", "61.0%", "128k"),
    ("moonshotai/Kimi-K2-Instruct", "Kimi K2 Instruct", "S", "65.8%", "131k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("Qwen/Qwen3-235B-A22B", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("qwen/qwen3-next-80b-a3b-instruct", "Qwen3 80B Instruct", "S", "65.0%", "128k"),
    ("deepseek-ai/DeepSeek-V3-0324", "DeepSeek V3 0324", "S", "62.0%", "128k"),
    ("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen2.5 Coder 32B", "A", "46.0%", "32k"),
    ("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("meta-llama/Meta-Llama-3.1-405B-Instruct", "Llama 3.1 405B", "A", "44.0%", "128k"),
))

# --- Scaleway ---
_p("scaleway", "Scaleway", "https://api.scaleway.ai/v1/chat/completions",
   ("SCALEWAY_API_KEY",), (
    ("devstral-2-123b-instruct-2512", "Devstral 2 123B", "S+", "72.2%", "256k"),
    ("qwen3-235b-a22b-instruct-2507", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("qwen3-coder-30b-a3b-instruct", "Qwen3 Coder 30B", "A+", "55.0%", "32k"),
    ("llama-3.3-70b-instruct", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("deepseek-r1-distill-llama-70b", "R1 Distill 70B", "A", "43.9%", "128k"),
    ("mistral-small-3.2-24b-instruct-2506", "Mistral Small 3.2", "B+", "30.0%", "128k"),
))

# --- Google AI ---
_p("googleai", "Google AI", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
   ("GOOGLE_API_KEY",), (
    ("gemma-3-27b-it", "Gemma 3 27B", "B", "22.0%", "128k"),
    ("gemma-3-12b-it", "Gemma 3 12B", "C", "15.0%", "128k"),
    ("gemma-3-4b-it", "Gemma 3 4B", "C", "10.0%", "128k"),
))

# --- SiliconFlow ---
_p("siliconflow", "SiliconFlow", "https://api.siliconflow.com/v1/chat/completions",
   ("SILICONFLOW_API_KEY",), (
    # S+ tier
    ("zai-org/GLM-5", "GLM 5", "S+", "77.8%", "200k"),
    ("MiniMaxAI/MiniMax-M2.5", "MiniMax M2.5", "S+", "74.0%", "200k"),
    ("MiniMaxAI/MiniMax-M2.1", "MiniMax M2.1", "S+", "74.0%", "200k"),
    ("moonshotai/Kimi-K2.5", "Kimi K2.5", "S+", "76.8%", "128k"),
    ("stepfun-ai/Step-3.5-Flash", "Step 3.5 Flash", "S+", "74.4%", "256k"),
    ("Qwen/Qwen3-Coder-480B-A35B-Instruct", "Qwen3 Coder 480B", "S+", "70.6%", "256k"),
    ("deepseek-ai/DeepSeek-V3.2", "DeepSeek V3.2", "S+", "73.1%", "128k"),
    ("Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen3 235B", "S+", "70.0%", "128k"),
    ("zai-org/GLM-4.7", "GLM 4.7", "S+", "73.8%", "200k"),
    # S tier
    ("deepseek-ai/DeepSeek-V3.1", "DeepSeek V3.1", "S", "62.0%", "128k"),
    ("deepseek-ai/DeepSeek-V3.1-Terminus", "DeepSeek V3.1 Term", "S", "68.4%", "128k"),
    ("moonshotai/Kimi-K2-Instruct", "Kimi K2 Instruct", "S", "65.8%", "128k"),
    ("deepseek-ai/DeepSeek-R1", "DeepSeek R1", "S", "61.0%", "128k"),
    ("openai/gpt-oss-120b", "GPT OSS 120B", "S", "60.0%", "128k"),
    ("Qwen/Qwen3-Next-80B-A3B-Instruct", "Qwen3 80B Instruct", "S", "65.0%", "128k"),
    # A+ tier
    ("Qwen/Qwen3-Coder-30B-A3B-Instruct", "Qwen3 Coder 30B", "A+", "55.0%", "32k"),
    ("Qwen/QwQ-32B", "QwQ 32B", "A+", "50.0%", "131k"),
    ("Qwen/Qwen3-32B", "Qwen3 32B", "A+", "50.0%", "128k"),
    # A tier
    ("openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen2.5 Coder 32B", "A", "46.0%", "32k"),
    ("baidu/ERNIE-4.5-300B-A47B", "ERNIE 4.5 300B", "A", "42.0%", "128k"),
    # A- tier
    ("ByteDance-Seed/Seed-OSS-36B-Instruct", "Seed OSS 36B", "A-", "38.0%", "32k"),
    ("tencent/Hunyuan-A13B-Instruct", "Hunyuan A13B", "A-", "36.0%", "32k"),
    ("THUDM/GLM-4-32B-0414", "GLM 4 32B", "A-", "38.0%", "32k"),
    # B tier
    ("meta-llama/Meta-Llama-3.1-8B-Instruct", "Llama 3.1 8B", "B", "28.8%", "128k"),
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
    ("@cf/qwen/qwen2.5-coder-32b-instruct", "Qwen2.5 Coder 32B", "A", "46.0%", "32k"),
    ("@cf/deepseek-ai/deepseek-r1-distill-qwen-32b", "R1 Distill 32B", "A", "43.9%", "128k"),
    ("@cf/openai/gpt-oss-20b", "GPT OSS 20B", "A", "42.0%", "128k"),
    ("@cf/meta/llama-3.3-70b-instruct-fp8-fast", "Llama 3.3 70B", "A-", "39.5%", "128k"),
    ("@cf/meta/llama-3.1-8b-instruct", "Llama 3.1 8B", "B", "28.8%", "128k"),
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
