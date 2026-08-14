"""Cost class for a model: how the user pays, not a marketing 'free' bit.

  zero          — $0/token (OpenRouter :free, HF $0 route)
  free_tier     — hosted free trial / rate-limited (Groq, Cerebras, NIM)
  subscription  — monthly CLI (claude, grok, agy, codex)
  local         — Ollama on this machine
  paid          — pay-as-you-go API
  unknown       — we have no signal
"""

from __future__ import annotations

from .cli_provider import is_cli_provider
from .lanes import LANE_A_PROVIDERS, lane_for
from .providers import PROVIDERS, Model

# Lane A hosted APIs (rate-limited / $0). Ollama is local, not free_tier.
FREE_TIER_PROVIDERS = frozenset(LANE_A_PROVIDERS - {"ollama"})

# Lane C hosts. OpenRouter is mixed; codestral/sambanova are Lane A.
PAID_PROVIDERS = frozenset({
    "minimax", "fireworks", "hyperbolic", "together", "deepinfra",
    "xai", "perplexity", "scaleway", "inferencenet", "cerebras",
    "replicate", "siliconflow", "sambanova",
})


def default_is_free(provider_key: str) -> bool | None:
    """Provider-level default when live pricing is missing."""
    if provider_key == "ollama" or is_cli_provider(provider_key):
        return True
    if provider_key in FREE_TIER_PROVIDERS:
        return True
    if provider_key in PAID_PROVIDERS:
        return False
    return None


def cost_class(
    provider_key: str,
    model_id: str = "",
    is_free: bool | None = None,
) -> str:
    """Return zero | free_tier | subscription | local | paid | unknown."""
    mid = (model_id or "").lower()
    if provider_key == "ollama":
        return "local"
    if is_cli_provider(provider_key):
        return "subscription"
    if is_free is True or ":free" in mid or "-free" in mid:
        if lane_for(provider_key, model_id) == "A" and ":free" not in mid:
            return "free_tier"
        return "zero"
    if is_free is False:
        return "paid"
    lane = lane_for(provider_key, model_id)
    if lane == "A" and provider_key != "ollama":
        return "free_tier"
    if lane == "C":
        return "paid"
    if provider_key in PAID_PROVIDERS:
        return "paid"
    return "unknown"


def is_chat_model(model_id: str) -> bool:
    """False for embeddings, ASR, TTS, rerankers, safety classifiers."""
    lower = (model_id or "").lower()
    skip = (
        "embed", "bge-", "e5-", "rerank", "whisper", "tts", "-asr",
        "moderat", "guard", "safety", "voxtral", "ocr",
        ":batch", "-image", "computer-use",
    )
    return not any(tok in lower for tok in skip)


def model_card(model: Model) -> dict:
    """Stable JSON card for list/recommend/ask."""
    name = PROVIDERS[model.provider].name if model.provider in PROVIDERS else model.provider
    cc = cost_class(model.provider, model.model_id, model.is_free)
    card = {
        "model_id": model.model_id,
        "label": model.label,
        "provider": name,
        "provider_key": model.provider,
        "tier": model.tier,
        "swe_score": model.swe_score,
        "context": model.context,
        "cost_class": cc,
        "ref": f"{model.provider}/{model.model_id}",
    }
    if model.is_free is not None:
        card["is_free"] = model.is_free
    return card
