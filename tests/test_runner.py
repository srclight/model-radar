"""Tests for the runner module."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from model_radar.providers import Model
from model_radar.runner import _call_model, _find_model, backtranslate_eval, run_on_fastest
from model_radar.scanner import PingResult


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


@pytest.mark.asyncio
async def test_fallback_on_failure():
    """Should retry on next model when first model fails."""
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
        if model.model_id == "m1":
            return {"error": "HTTP 429", "detail": "rate limited",
                    "model": model.label, "provider": "NIM"}
        return {
            "content": f"Response from {model.label}",
            "model_id": model.model_id,
            "model_label": model.label,
            "provider": "NIM", "provider_key": "nvidia",
            "tier": "A", "latency_ms": 500,
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        }

    with patch("model_radar.runner.load_config", return_value={"api_keys": {"nvidia": "k"}, "providers": {}}), \
         patch("model_radar.runner.scan_models", return_value=ping_results), \
         patch("model_radar.runner._call_model", side_effect=mock_call):
        result = await run_on_fastest(prompt="hello", max_retries=3)

    assert "error" not in result
    assert result["content"] == "Response from Model B"
    assert "retries" in result
    assert len(result["retries"]) == 1
    assert result["retries"][0]["model_id"] == "m1"


@pytest.mark.asyncio
async def test_fallback_all_fail():
    """Should return error with retry history when all models fail."""
    models = [
        _model(model_id="m1", label="Model A"),
        _model(model_id="m2", label="Model B"),
    ]
    ping_results = [PingResult(model=m, status="up", latency_ms=100) for m in models]

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return {"error": "HTTP 429", "detail": "rate limited",
                "model": model.label, "provider": "NIM"}

    with patch("model_radar.runner.load_config", return_value={"api_keys": {"nvidia": "k"}, "providers": {}}), \
         patch("model_radar.runner.scan_models", return_value=ping_results), \
         patch("model_radar.runner._call_model", side_effect=mock_call):
        result = await run_on_fastest(prompt="hello", max_retries=2)

    assert "error" in result
    assert "retries" in result
    assert len(result["retries"]) == 2


@pytest.mark.asyncio
async def test_backtranslate_eval_computes_overlap():
    """Should compute gloss overlap between original and back-translation."""
    async def mock_run(*args, **kwargs):
        return {
            "content": "father, head of a household",
            "model_id": "test/model",
            "model_label": "Test Model",
            "provider": "NIM",
            "latency_ms": 200.0,
        }

    with patch("model_radar.runner.run_on_fastest", side_effect=mock_run):
        result = await backtranslate_eval(
            text="father, head of household",
            translation="Vater, Haupt eines Haushalts",
            source_lang="English",
            target_lang="German",
        )

    assert "error" not in result
    assert result["gloss_overlap"] > 0.5
    assert "father," in result["matching_glosses"] or "father" in str(result["matching_glosses"])
    assert result["back_translation"] == "father, head of a household"
    assert result["model_id"] == "test/model"


@pytest.mark.asyncio
async def test_call_model_dispatches_to_cli_provider():
    """When provider is kind='cli', _call_model uses complete_cli_provider."""
    from model_radar.providers import PROVIDERS

    if "grok" in PROVIDERS:
        PROVIDERS["grok"] = PROVIDERS["grok"].__class__(
            key=PROVIDERS["grok"].key, name=PROVIDERS["grok"].name,
            url=PROVIDERS["grok"].url, env_vars=PROVIDERS["grok"].env_vars,
            models=PROVIDERS["grok"].models, kind="cli",
            cmd="grok", cmd_args=(), prompt_via="arg", model_flag="-m",
        )

    model = _model(provider="grok", model_id="grok-4", label="Grok 4", tier="S+")
    fake_content = "Hello from Grok!"
    fake_result = {
        "content": fake_content, "model_id": "grok-4", "model_label": "Grok 4",
        "provider": "Grok (Subscription)", "provider_key": "grok",
        "tier": "S+", "latency_ms": 100.0,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
    }
    with patch("model_radar.cli_provider.complete_cli_provider", return_value=fake_result) as mock:
        result = await _call_model(
            model=model, messages=[{"role": "user", "content": "hi"}], cfg={}
        )
    assert result["content"] == fake_content
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_call_model_cli_provider_error_returns_error_dict():
    """When CLI provider raises, _call_model returns error dict (not crash)."""
    from model_radar.providers import PROVIDERS

    if "grok" in PROVIDERS:
        PROVIDERS["grok"] = PROVIDERS["grok"].__class__(
            key=PROVIDERS["grok"].key, name=PROVIDERS["grok"].name,
            url=PROVIDERS["grok"].url, env_vars=PROVIDERS["grok"].env_vars,
            models=PROVIDERS["grok"].models, kind="cli",
            cmd="grok", cmd_args=(), prompt_via="arg", model_flag="-m",
        )

    model = _model(provider="grok", model_id="grok-4", label="Grok 4", tier="S+")
    with patch("model_radar.cli_provider.complete_cli_provider",
               side_effect=Exception("CLI not found")):
        result = await _call_model(
            model=model, messages=[{"role": "user", "content": "hi"}], cfg={}
        )
    assert "error" in result
    assert "CLI not found" in result["error"]
