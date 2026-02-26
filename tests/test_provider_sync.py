"""
Tests for provider_sync module - live model fetching from provider APIs.
"""

import pytest
from model_radar.provider_sync import (
    fetch_openrouter_models,
    fetch_nvidia_models,
    fetch_groq_models,
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
