"""Tests for the runner module."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from model_radar.providers import Model
from model_radar.runner import _call_model, run_on_fastest


def _model(provider="nvidia", model_id="test/model", label="Test Model",
           tier="A", swe="45.0%", ctx="128k"):
    return Model(model_id=model_id, label=label, tier=tier,
                 swe_score=swe, context=ctx, provider=provider)


@pytest.mark.asyncio
async def test_run_on_fastest_no_keys():
    """Should return error when no providers are configured."""
    with patch("model_radar.runner.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.runner.scan_models", return_value=[]):
        result = await run_on_fastest(prompt="hello")
        assert "error" in result


@pytest.mark.asyncio
async def test_run_on_fastest_model_not_found():
    """Should return error for unknown model_id."""
    with patch("model_radar.runner.load_config", return_value={"api_keys": {}, "providers": {}}):
        result = await run_on_fastest(prompt="hello", model_id="nonexistent/model")
        assert "error" in result
        assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_call_model_no_key():
    """Should return error when provider has no key."""
    m = _model()
    cfg = {"api_keys": {}, "providers": {}}
    with patch("model_radar.runner.get_api_key", return_value=None):
        result = await _call_model(m, [{"role": "user", "content": "hi"}], cfg)
        assert "error" in result
        assert "No API key" in result["error"]


@pytest.mark.asyncio
async def test_call_model_success():
    """Should parse a successful OpenAI-compatible response."""
    import httpx

    m = _model()
    cfg = {"api_keys": {"nvidia": "test-key"}, "providers": {}}

    mock_response = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Hello! I'm a test response."}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        },
        request=httpx.Request("POST", "https://example.com"),
    )

    with patch("model_radar.runner.get_api_key", return_value="test-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await _call_model(
            m, [{"role": "user", "content": "hi"}], cfg,
        )
        assert result["content"] == "Hello! I'm a test response."
        assert result["model_label"] == "Test Model"
        assert result["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_call_model_http_error():
    """Should return error on non-200 response."""
    import httpx

    m = _model()
    cfg = {"api_keys": {"nvidia": "test-key"}, "providers": {}}

    mock_response = httpx.Response(
        429,
        text="Rate limited",
        request=httpx.Request("POST", "https://example.com"),
    )

    with patch("model_radar.runner.get_api_key", return_value="test-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await _call_model(
            m, [{"role": "user", "content": "hi"}], cfg,
        )
        assert "error" in result
        assert "429" in result["error"]
