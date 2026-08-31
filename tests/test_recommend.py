"""recommend() picks a diverse chat lineup."""

from unittest.mock import patch

from model_radar.providers import Model
from model_radar.recommend import recommend_models, recommend_payload


def _m(provider, model_id, tier="C"):
    return Model(
        model_id=model_id, label=model_id, tier=tier,
        swe_score="", context="", provider=provider,
    )


def test_recommend_one_per_provider_skips_embeddings():
    pool = [
        _m("minimax", "MiniMax-M3", "S+"),
        _m("minimax", "MiniMax-M2.5"),
        _m("ollama", "qwen3-embedding:4b"),
        _m("ollama", "hy-mt-1.8b:latest"),
        _m("nvidia", "openai/gpt-oss-120b"),
        _m("grok", "grok-4.6"),
    ]
    cfg = {"api_keys": {}, "providers": {"minimax": {"funded": True, "spend_ok": False}}}
    with patch("model_radar.recommend.get_configured_providers",
               return_value=["minimax", "ollama", "nvidia", "grok"]), \
         patch("model_radar.recommend.get_models_for_discovery", return_value=pool), \
         patch("model_radar.recommend.load_config", return_value=cfg):
        picked = recommend_models(job="translate", count=6, include_subscriptions=False)
    ids = [(m.provider, m.model_id) for m in picked]
    assert ("ollama", "hy-mt-1.8b:latest") in ids
    assert ("nvidia", "openai/gpt-oss-120b") in ids
    assert all(p != "grok" for p, _ in ids)
    assert all(p != "minimax" for p, _ in ids)  # Lane C, spend_ok false
    assert all("embed" not in mid for _, mid in ids)
    providers = [p for p, _ in ids]
    assert len(providers) == len(set(providers))


def test_recommend_include_paid_uses_funded_lane_c():
    pool = [
        _m("minimax", "MiniMax-M3", "S+"),
        _m("ollama", "hy-mt-1.8b:latest"),
        _m("together", "openai/gpt-oss-120b"),
    ]
    cfg = {
        "providers": {
            "minimax": {"funded": True, "spend_ok": False},
            "together": {"funded": False, "spend_ok": False},
        },
    }
    with patch("model_radar.recommend.get_configured_providers",
               return_value=["minimax", "ollama", "together"]), \
         patch("model_radar.recommend.get_models_for_discovery", return_value=pool), \
         patch("model_radar.recommend.load_config", return_value=cfg):
        picked = recommend_models(job="code", count=6, include_paid=True)
    ids = [(m.provider, m.model_id) for m in picked]
    assert ("minimax", "MiniMax-M3") in ids
    assert ("ollama", "hy-mt-1.8b:latest") in ids
    assert all(p != "together" for p, _ in ids)


def test_recommend_skips_ollama_cloud_routes():
    pool = [
        _m("ollama", "minimax-m2:cloud"),
        _m("ollama", "gemma3:27b"),
        _m("groq", "openai/gpt-oss-120b", "S"),
    ]
    with patch("model_radar.recommend.get_configured_providers",
               return_value=["ollama", "groq"]), \
         patch("model_radar.recommend.get_models_for_discovery", return_value=pool), \
         patch("model_radar.recommend.load_config", return_value={"api_keys": {}, "providers": {}}):
        picked = recommend_models(job="dict", count=6, free_only=True)
    ids = [m.model_id for m in picked]
    assert "minimax-m2:cloud" not in ids
    assert "gemma3:27b" in ids


def test_recommend_dict_skips_giant_ultra():
    pool = [
        _m("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", "S+"),
        _m("groq", "openai/gpt-oss-120b", "S"),
        _m("codestral", "ministral-8b-latest", "A"),
    ]
    with patch("model_radar.recommend.get_configured_providers",
               return_value=["openrouter", "groq", "codestral"]), \
         patch("model_radar.recommend.get_models_for_discovery", return_value=pool), \
         patch("model_radar.recommend.load_config", return_value={"api_keys": {}, "providers": {}}):
        picked = recommend_models(job="dict", count=2, free_only=True)
    ids = [m.model_id for m in picked]
    assert "openai/gpt-oss-120b" in ids
    assert all("550b" not in i and "ultra" not in i.lower() for i in ids)


def test_recommend_payload_unknown_job_falls_back():
    with patch("model_radar.recommend.get_configured_providers", return_value=[]), \
         patch("model_radar.recommend.get_models_for_discovery", return_value=[]), \
         patch("model_radar.recommend.load_config", return_value={"api_keys": {}}):
        payload = recommend_payload(job="not-a-job")
    assert payload["job"] == "code"
    assert payload["count"] == 0
