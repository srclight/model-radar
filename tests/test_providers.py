"""Tests for provider data integrity."""

from model_radar.providers import (
    ALL_TIERS,
    PROVIDERS,
    TIER_ORDER,
    Model,
    filter_models,
    get_all_models,
)


def test_all_providers_defined():
    """All 17 providers should be registered."""
    expected = {
        "nvidia", "groq", "cerebras", "sambanova", "openrouter",
        "huggingface", "replicate", "deepinfra", "fireworks", "codestral",
        "hyperbolic", "scaleway", "googleai", "siliconflow", "together",
        "cloudflare", "perplexity",
    }
    assert set(PROVIDERS.keys()) == expected


def test_provider_has_models():
    """Every provider should have at least one model."""
    for key, prov in PROVIDERS.items():
        assert len(prov.models) > 0, f"Provider {key} has no models"


def test_provider_has_url():
    """Every provider should have an API URL."""
    for key, prov in PROVIDERS.items():
        assert prov.url.startswith("https://"), f"Provider {key} has invalid URL"


def test_provider_has_env_vars():
    """Every provider should declare at least one env var."""
    for key, prov in PROVIDERS.items():
        assert len(prov.env_vars) > 0, f"Provider {key} has no env vars"


def test_get_all_models():
    """Should return a flat list of all models."""
    models = get_all_models()
    assert len(models) > 100  # We expect 130+
    assert all(isinstance(m, Model) for m in models)


def test_model_tiers_valid():
    """All model tiers should be in the known set."""
    for m in get_all_models():
        assert m.tier in TIER_ORDER, f"Model {m.label} has unknown tier {m.tier}"


def test_model_tuples_correct_length():
    """Each model tuple in providers should have 5 elements."""
    for key, prov in PROVIDERS.items():
        for t in prov.models:
            assert len(t) == 5, f"Provider {key} model tuple has {len(t)} elements: {t}"


def test_filter_by_tier():
    """Filter should return only matching tier."""
    models = filter_models(tier="S+")
    assert len(models) > 0
    assert all(m.tier == "S+" for m in models)


def test_filter_by_provider():
    """Filter should return only matching provider."""
    models = filter_models(provider="nvidia")
    assert len(models) == len(PROVIDERS["nvidia"].models)
    assert all(m.provider == "nvidia" for m in models)


def test_filter_by_min_tier():
    """min_tier should include that tier and better."""
    models = filter_models(min_tier="A")
    allowed = {"S+", "S", "A+", "A"}
    assert all(m.tier in allowed for m in models)
    assert len(models) > 0


def test_tier_order():
    """Tier ordering should have S+ as best (0)."""
    assert TIER_ORDER["S+"] == 0
    assert TIER_ORDER["C"] == 7
    assert TIER_ORDER["S+"] < TIER_ORDER["A"]
