"""
Tests for provider_sync module - live model fetching from provider APIs.
"""

import json
from unittest.mock import patch

import pytest
from model_radar.provider_sync import (
    fetch_openrouter_models,
    fetch_nvidia_models,
    fetch_groq_models,
    fetch_xai_models,
    fetch_googleai_models,
    fetch_ollama_models,
    compare_models,
    ProviderModel,
)


class TestProviderModel:
    def test_creation(self):
        """Test ProviderModel creation."""
        model = ProviderModel(
            model_id="test-model",
            label="Test Model",
            provider="test",
        )
        
        assert model.model_id == "test-model"
        assert model.label == "Test Model"
        assert model.provider == "test"
        assert model.created is None
        assert model.context_length is None
        assert model.extra is None


class TestCompareModels:
    def test_no_difference(self):
        """Test comparison when models match."""
        hardcoded = [
            ProviderModel("model-1", provider="test"),
            ProviderModel("model-2", provider="test"),
        ]
        live = [
            ProviderModel("model-1", provider="test"),
            ProviderModel("model-2", provider="test"),
        ]
        
        result = compare_models(hardcoded, live)
        
        assert result["missing"] == []  # Nothing missing from live
        assert result["extra"] == []    # Nothing extra in hardcoded
        assert len(result["matched"]) == 2

    def test_new_models_in_live(self):
        """Test detecting new models in live API."""
        hardcoded = [
            ProviderModel("model-1", provider="test"),
        ]
        live = [
            ProviderModel("model-1", provider="test"),
            ProviderModel("model-2", provider="test"),
            ProviderModel("model-3", provider="test"),
        ]
        
        result = compare_models(hardcoded, live)
        
        assert len(result["missing"]) == 2  # 2 new in live
        assert "model-2" in result["missing"]
        assert "model-3" in result["missing"]
        assert result["extra"] == []
        assert len(result["matched"]) == 1

    def test_missing_from_live(self):
        """Test detecting models missing from live API."""
        hardcoded = [
            ProviderModel("model-1", provider="test"),
            ProviderModel("model-2", provider="test"),
            ProviderModel("model-3", provider="test"),
        ]
        live = [
            ProviderModel("model-1", provider="test"),
        ]
        
        result = compare_models(hardcoded, live)
        
        assert result["missing"] == []
        assert len(result["extra"]) == 2  # 2 missing from live
        assert "model-2" in result["extra"]
        assert "model-3" in result["extra"]
        assert len(result["matched"]) == 1

    def test_complex_scenario(self):
        """Test complex comparison scenario."""
        hardcoded = [
            ProviderModel("model-1", provider="test"),
            ProviderModel("model-2", provider="test"),
            ProviderModel("model-3", provider="test"),
        ]
        live = [
            ProviderModel("model-1", provider="test"),
            ProviderModel("model-4", provider="test"),
            ProviderModel("model-5", provider="test"),
        ]
        
        result = compare_models(hardcoded, live)
        
        assert len(result["missing"]) == 2  # model-4, model-5
        assert len(result["extra"]) == 2    # model-2, model-3
        assert len(result["matched"]) == 1  # model-1


class TestFetchOpenRouter:
    @pytest.mark.asyncio
    async def test_fetch_without_key(self):
        """Test fetching OpenRouter models without API key."""
        models = await fetch_openrouter_models(api_key=None)
        # Should return empty list without key
        assert isinstance(models, list)
    
    @pytest.mark.asyncio
    async def test_fetch_with_invalid_key(self):
        """Test fetching OpenRouter models with invalid key."""
        models = await fetch_openrouter_models(api_key="invalid-key")
        # Should return empty list on error
        assert isinstance(models, list)


class TestFetchNvidia:
    @pytest.mark.asyncio
    async def test_fetch_without_key(self):
        """Test fetching NVIDIA models without API key."""
        models = await fetch_nvidia_models(api_key=None)
        # Should return empty list without key
        assert isinstance(models, list)
    
    @pytest.mark.asyncio
    async def test_fetch_with_invalid_key(self):
        """Test fetching NVIDIA models with invalid key."""
        models = await fetch_nvidia_models(api_key="invalid-key")
        # Should return empty list on error
        assert isinstance(models, list)


class TestFetchGroq:
    @pytest.mark.asyncio
    async def test_fetch_without_key(self):
        """Test fetching Groq models without API key."""
        models = await fetch_groq_models(api_key=None)
        # Should return empty list without key
        assert isinstance(models, list)

    @pytest.mark.asyncio
    async def test_fetch_with_invalid_key(self):
        """Test fetching Groq models with invalid key."""
        models = await fetch_groq_models(api_key="invalid-key")
        # Should return empty list on error
        assert isinstance(models, list)


@pytest.mark.asyncio
async def test_fetch_xai_models_with_api_key():
    """fetch_xai_models parses a fake API response."""
    fake_response = {
        "data": [
            {"id": "grok-4", "name": "Grok 4", "created": 1234567890},
            {"id": "grok-3", "name": "Grok 3"},
        ]
    }

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, timeout=None):
            class FakeResp:
                def raise_for_status(self): pass
                def json(self): return fake_response
            return FakeResp()

    with patch("httpx.AsyncClient", return_value=FakeClient()):
        models = await fetch_xai_models(api_key="xai-test-key")

    assert len(models) == 2
    assert models[0].model_id == "grok-4"
    assert models[0].provider == "xai"


@pytest.mark.asyncio
async def test_fetch_xai_models_no_api_key():
    """fetch_xai_models returns empty list when no API key."""
    models = await fetch_xai_models(api_key=None)
    assert models == []


@pytest.mark.asyncio
async def test_fetch_googleai_models_with_api_key():
    """fetch_googleai_models parses a fake API response."""
    fake_response = {
        "models": [
            {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro",
             "inputTokenLimit": 1000000},
            {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash"},
        ]
    }

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, timeout=None):
            class FakeResp:
                def raise_for_status(self): pass
                def json(self): return fake_response
            return FakeResp()

    with patch("httpx.AsyncClient", return_value=FakeClient()):
        models = await fetch_googleai_models(api_key="googleai-test-key")

    assert len(models) == 2
    assert models[0].model_id == "gemini-2.5-pro"
    assert models[0].provider == "googleai"
    assert models[0].context_length == 1000000


@pytest.mark.asyncio
async def test_fetch_ollama_models_skips_embeddings():
    """fetch_ollama_models keeps chat models and drops embedding tags."""
    fake_response = {
        "models": [
            {"name": "gemma3:27b"},
            {"name": "qwen3-embedding:4b"},
            {"name": "mistral-small:22b"},
        ]
    }

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, timeout=None):
            class FakeResp:
                def raise_for_status(self): pass
                def json(self): return fake_response
            return FakeResp()

    with patch("httpx.AsyncClient", return_value=FakeClient()):
        models = await fetch_ollama_models()

    ids = [m.model_id for m in models]
    assert ids == ["gemma3:27b", "mistral-small:22b"]
    assert all(m.provider == "ollama" for m in models)


@pytest.mark.asyncio
async def test_fetch_ollama_models_down_returns_empty():
    """Unreachable daemon yields an empty list, not an exception."""
    class BoomClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, timeout=None):
            raise OSError("connection refused")

    with patch("httpx.AsyncClient", return_value=BoomClient()):
        models = await fetch_ollama_models()
    assert models == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
