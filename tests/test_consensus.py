"""Tests for the consensus (ask) module."""

from unittest.mock import AsyncMock, patch

import pytest

from model_radar.consensus import ask_models
from model_radar.providers import Model
from model_radar.scanner import PingResult


def _model(provider="nvidia", model_id="test/model-1", label="Model 1",
           tier="A", swe="45.0%", ctx="128k"):
    return Model(model_id=model_id, label=label, tier=tier,
                 swe_score=swe, context=ctx, provider=provider)


def _make_response(model_id, content):
    return {
        "content": content,
        "model_id": model_id,
        "model_label": f"Model {model_id}",
        "provider": "NIM",
        "provider_key": "nvidia",
        "tier": "A",
        "latency_ms": 500.0,
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


@pytest.mark.asyncio
async def test_ask_no_models():
    """Should return error when no models available."""
    with patch("model_radar.consensus.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.consensus.scan_models", return_value=[]):
        result = await ask_models(prompt="hello", count=3)
    assert "error" in result


@pytest.mark.asyncio
async def test_ask_multiple_models():
    """Should query multiple models and return all responses."""
    models = [
        _model(model_id="m1", label="Model A"),
        _model(model_id="m2", label="Model B"),
        _model(model_id="m3", label="Model C"),
    ]
    ping_results = [PingResult(model=m, status="up", latency_ms=100) for m in models]

    call_count = 0
    async def mock_call(model, messages, cfg, max_tokens, temperature):
        nonlocal call_count
        call_count += 1
        return _make_response(model.model_id, f"Answer from {model.label}")

    with patch("model_radar.consensus.load_config", return_value={"api_keys": {"nvidia": "k"}, "providers": {}}), \
         patch("model_radar.consensus.scan_models", return_value=ping_results), \
         patch("model_radar.consensus._call_model", side_effect=mock_call), \
         patch("model_radar.consensus.get_model_quality", return_value=None):
        result = await ask_models(prompt="hello", count=3)

    assert result["models_queried"] == 3
    assert result["models_responded"] == 3
    assert result["models_failed"] == 0
    assert len(result["responses"]) == 3
    assert all(r["content"].startswith("Answer from") for r in result["responses"])


@pytest.mark.asyncio
async def test_ask_partial_failure():
    """Should handle some models failing."""
    models = [
        _model(model_id="m1", label="Model A"),
        _model(model_id="m2", label="Model B"),
    ]
    ping_results = [PingResult(model=m, status="up", latency_ms=100) for m in models]

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        if model.model_id == "m1":
            return _make_response(model.model_id, "Good answer")
        return {"error": "HTTP 429", "model": model.label, "provider": "NIM"}

    with patch("model_radar.consensus.load_config", return_value={"api_keys": {"nvidia": "k"}, "providers": {}}), \
         patch("model_radar.consensus.scan_models", return_value=ping_results), \
         patch("model_radar.consensus._call_model", side_effect=mock_call), \
         patch("model_radar.consensus.get_model_quality", return_value=None):
        result = await ask_models(prompt="hello", count=2)

    assert result["models_responded"] == 1
    assert result["models_failed"] == 1
