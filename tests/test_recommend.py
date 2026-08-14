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


def test_recommend_payload_unknown_job_falls_back():
    with patch("model_radar.recommend.get_configured_providers", return_value=[]), \
         patch("model_radar.recommend.get_models_for_discovery", return_value=[]), \
         patch("model_radar.recommend.load_config", return_value={"api_keys": {}}):
        payload = recommend_payload(job="not-a-job")
    assert payload["job"] == "code"
    assert payload["count"] == 0
