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
    """All known providers should be registered. CLI providers (grok, gemini) are
    conditionally registered when their binaries are on PATH, so they're checked
    separately."""
    expected = {
        "nvidia", "groq", "cerebras", "sambanova", "openrouter",
        "huggingface", "replicate", "deepinfra", "fireworks", "codestral",
        "hyperbolic", "scaleway", "googleai", "siliconflow", "together",
        "cloudflare", "perplexity", "xai", "inferencenet", "sealion",
        "ollama",
    }
    # CLI providers may or may not be registered depending on PATH; allow extras.
    assert set(PROVIDERS.keys()) >= expected
    # CLI providers should be present if their binaries are on PATH
    import shutil
    if shutil.which("grok"):
        assert "grok" in PROVIDERS
    if shutil.which("agy"):
        assert "gemini" in PROVIDERS
        assert PROVIDERS["gemini"].cmd == "agy"
    if shutil.which("claude"):
        assert "claude" in PROVIDERS
    if shutil.which("codex"):
        assert "codex" in PROVIDERS


def test_provider_has_models():
    """Every provider should have at least one model, except local catalogs
    that are filled from the user's machine (Ollama may be empty if the
    daemon is down)."""
    for key, prov in PROVIDERS.items():
        if key == "ollama":
            continue
        assert len(prov.models) > 0, f"Provider {key} has no models"


def test_provider_has_url():
    """HTTPS providers should have an API URL; CLI providers have url=None."""
    for key, prov in PROVIDERS.items():
        if prov.kind == "cli":
            assert prov.url is None, f"CLI provider {key} should have url=None"
        else:
            assert prov.url.startswith("http://") or prov.url.startswith("https://"), f"Provider {key} has invalid URL"


def test_provider_has_env_vars():
    """HTTPS providers should declare at least one env var; CLI providers have none."""
    for key, prov in PROVIDERS.items():
        if prov.kind == "cli":
            assert len(prov.env_vars) == 0, f"CLI provider {key} should have env_vars=()"
        else:
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
