"""Cost class and chat-model filters."""

from model_radar.cost import cost_class, default_is_free, is_chat_model, model_card
from model_radar.providers import Model


def test_cost_class_by_provider():
    assert cost_class("ollama", "qwen2.5:3b-instruct") == "local"
    assert cost_class("grok", "grok-4.6") == "subscription"
    assert cost_class("minimax", "MiniMax-M3") == "paid"
    assert cost_class("cerebras", "gpt-oss-120b") == "paid"
    assert cost_class("nvidia", "openai/gpt-oss-120b") == "free_tier"
    assert cost_class("openrouter", "google/gemma-4-31b-it:free", True) == "zero"
    assert cost_class("openrouter", "some/paid-model", False) == "paid"


def test_default_is_free():
    assert default_is_free("ollama") is True
    assert default_is_free("groq") is True
    assert default_is_free("cerebras") is False
    assert default_is_free("minimax") is False
    assert default_is_free("openrouter") is None


def test_is_chat_model_skips_embeddings():
    assert is_chat_model("MiniMax-M3") is True
    assert is_chat_model("qwen3-embedding:4b") is False
    assert is_chat_model("whisper-large-v3") is False
    assert is_chat_model("bge-m3:latest") is False
    assert is_chat_model("anthropic/claude-sonnet-5:batch") is False


def test_model_card_includes_cost_class():
    m = Model(
        model_id="MiniMax-M3", label="M3", tier="S+", swe_score="",
        context="1M", provider="minimax", is_free=False,
    )
    card = model_card(m)
    assert card["cost_class"] == "paid"
    assert card["ref"] == "minimax/MiniMax-M3"
    assert card["is_free"] is False
