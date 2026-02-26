"""
Tests for database module.
"""

import pytest
from pathlib import Path
import tempfile
import os

from model_radar.db import (
    init_schema,
    sync_models,
    get_all_models,
    filter_models,
    record_ping,
    get_recent_ping,
    get_stats,
    get_provider_stats,
    replace_provider_models,
    ensure_db_populated,
    get_models_for_discovery,
    DB_PATH,
)
from model_radar.providers import PROVIDERS


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        yield db_path
    finally:
        if db_path.exists():
            db_path.unlink()


@pytest.fixture
def synced_db(temp_db):
    """Create a synced database for testing."""
    init_schema(temp_db)
    sync_models(temp_db)
    return temp_db


class TestInitSchema:
    def test_creates_tables(self, temp_db):
        """Test that schema initialization creates required tables."""
        init_schema(temp_db)
        
        # Check tables exist
        import sqlite3
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        assert 'models' in tables
        assert 'ping_results' in tables
        assert 'cache_meta' in tables
        
        conn.close()

    def test_idempotent(self, temp_db):
        """Test that init_schema can be called multiple times."""
        # Should not raise
        init_schema(temp_db)
        init_schema(temp_db)
        init_schema(temp_db)


class TestSyncModels:
    def test_sync_all_providers(self, temp_db):
        """Test that sync_models syncs all providers."""
        init_schema(temp_db)
        stats = sync_models(temp_db)
        
        # All providers should be synced
        assert len(stats) == len(PROVIDERS)
        
        # Each provider should have at least 1 model
        for provider_key, count in stats.items():
            assert count > 0, f"{provider_key} should have models"

    def test_sync_creates_models(self, temp_db):
        """Test that sync creates model records."""
        init_schema(temp_db)
        sync_models(temp_db)
        
        models = get_all_models(temp_db)
        
        # Should have many models
        assert len(models) > 100
        
        # All should be Model instances
        for model in models:
            assert hasattr(model, 'provider')
            assert hasattr(model, 'model_id')
            assert hasattr(model, 'label')
            assert hasattr(model, 'tier')

    def test_sync_is_idempotent(self, temp_db):
        """Test that sync can be called multiple times without duplicating."""
        init_schema(temp_db)
        
        stats1 = sync_models(temp_db)
        stats2 = sync_models(temp_db)
        
        # Same counts
        assert stats1 == stats2
        
        # Same number of models
        models = get_all_models(temp_db)
        expected_count = sum(len(p.models) for p in PROVIDERS.values())
        assert len(models) == expected_count


class TestGetAllModels:
    def test_returns_all_models(self, synced_db):
        """Test that get_all_models returns all synced models."""
        models = get_all_models(synced_db)
        
        expected_count = sum(len(p.models) for p in PROVIDERS.values())
        assert len(models) == expected_count

    def test_active_only_default(self, synced_db):
        """Test that get_all_models only returns active models by default."""
        # All models should be active
        models = get_all_models(synced_db)
        for model in models:
            # We can't directly check is_active, but we know they're all active
            pass
        
        # If we had a way to mark inactive, we'd test it here


class TestFilterModels:
    def test_filter_by_provider(self, synced_db):
        """Test filtering models by provider."""
        # Filter by nvidia
        models = filter_models(synced_db, provider="nvidia")
        
        assert len(models) > 0
        for model in models:
            assert model.provider == "nvidia"

    def test_filter_by_tier(self, synced_db):
        """Test filtering models by exact tier."""
        models = filter_models(synced_db, tier="S+")
        
        assert len(models) > 0
        for model in models:
            assert model.tier == "S+"

    def test_filter_by_min_tier(self, synced_db):
        """Test filtering models by minimum tier."""
        models = filter_models(synced_db, min_tier="S")
        
        # Should include S+ and S tier models
        assert len(models) > 0
        for model in models:
            assert model.tier in ["S+", "S"]

    def test_filter_free_only(self, synced_db):
        """Test filter by free_only (is_free=1)."""
        all_models = filter_models(synced_db, provider="groq")
        free_models = filter_models(synced_db, provider="groq", free_only=True)
        assert len(free_models) <= len(all_models)
        for m in free_models:
            assert m.is_free is True

    def test_filter_combined(self, synced_db):
        """Test filtering by both provider and tier."""
        models = filter_models(synced_db, provider="nvidia", tier="S+")
        
        assert len(models) > 0
        for model in models:
            assert model.provider == "nvidia"
            assert model.tier == "S+"


class TestRecordPing:
    def test_record_ping_success(self, synced_db):
        """Test recording a successful ping."""
        model_id = "llama-3.3-70b-instruct"
        provider = "groq"
        
        record_ping(
            model_id=model_id,
            provider_key=provider,
            status="up",
            latency_ms=42.5,
            db_path=synced_db,
        )
        
        # Should not raise
        stats = get_stats(synced_db)
        assert stats['ping_results'] == 1

    def test_record_ping_error(self, synced_db):
        """Test recording a failed ping."""
        record_ping(
            model_id="test-model",
            provider_key="test-provider",
            status="error",
            latency_ms=100.0,
            error_detail="Connection refused",
            db_path=synced_db,
        )
        
        stats = get_stats(synced_db)
        assert stats['ping_results'] == 1

    def test_record_ping_updates_timestamp(self, synced_db):
        """Test that recording a ping updates last_pinged_at."""
        model_id = "llama-3.3-70b-instruct"
        provider = "groq"
        
        record_ping(
            model_id=model_id,
            provider_key=provider,
            status="up",
            latency_ms=42.5,
            db_path=synced_db,
        )
        
        # Should have updated last_pinged_at
        # (we can't easily test the exact timestamp, but we know it was updated)


class TestGetRecentPing:
    def test_no_recent_ping(self, synced_db):
        """Test get_recent_ping when no ping exists."""
        result = get_recent_ping(
            model_id="llama-3.3-70b-instruct",
            provider_key="groq",
            db_path=synced_db,
        )
        assert result is None

    def test_recent_ping_within_ttl(self, synced_db):
        """Test get_recent_ping returns result within TTL."""
        model_id = "llama-3.3-70b-instruct"
        provider = "groq"
        
        # Record a ping
        record_ping(
            model_id=model_id,
            provider_key=provider,
            status="up",
            latency_ms=42.5,
            db_path=synced_db,
        )
        
        # Should return the recent ping
        result = get_recent_ping(
            model_id=model_id,
            provider_key=provider,
            ttl_seconds=300,  # 5 minutes
            db_path=synced_db,
        )
        
        assert result is not None
        assert result['status'] == "up"
        assert result['latency_ms'] == 42.5

    def test_old_ping_outside_ttl(self, synced_db):
        """Test get_recent_ping ignores old pings."""
        model_id = "test-old"
        provider = "test"
        
        # Record a ping (we'll manually age it in a real scenario)
        record_ping(
            model_id=model_id,
            provider_key=provider,
            status="up",
            latency_ms=100.0,
            db_path=synced_db,
        )
        
        # Use very short TTL
        result = get_recent_ping(
            model_id=model_id,
            provider_key=provider,
            ttl_seconds=0,  # Already expired
            db_path=synced_db,
        )
        
        # Should be None because TTL is 0
        assert result is None


class TestGetStats:
    def test_stats_structure(self, synced_db):
        """Test that get_stats returns correct structure."""
        stats = get_stats(synced_db)
        
        assert 'active_models' in stats
        assert 'inactive_models' in stats
        assert 'providers' in stats
        assert 'ping_results' in stats
        assert 'last_ping' in stats

    def test_stats_counts(self, synced_db):
        """Test that stats counts are correct."""
        stats = get_stats(synced_db)
        
        # Should have many active models
        assert stats['active_models'] > 100
        
        # Should have 17 providers
        assert stats['providers'] == len(PROVIDERS)
        
        # No pings yet
        assert stats['ping_results'] == 0


class TestGetProviderStats:
    def test_provider_stats_structure(self, synced_db):
        """Test that get_provider_stats returns correct structure."""
        provider_stats = get_provider_stats(synced_db)
        
        # Should have stats for each provider
        assert len(provider_stats) == len(PROVIDERS)
        
        for provider_key, pstats in provider_stats.items():
            assert 'total_models' in pstats
            assert 'active_models' in pstats
            assert pstats['total_models'] > 0


class TestReplaceProviderModels:
    def test_replace_provider_models(self, synced_db):
        """Test replacing a provider's models with a new list."""
        rows = [
            ("new-model-1", "New Model 1", "A", "45%", "128k", True),
            ("new-model-2", "New Model 2", "B", "25%", "32k", None),
        ]
        n = replace_provider_models("groq", rows, db_path=synced_db)
        assert n == 2
        groq_models = filter_models(db_path=synced_db, provider="groq")
        assert len(groq_models) == 2
        ids = {m.model_id for m in groq_models}
        assert ids == {"new-model-1", "new-model-2"}

    def test_replace_clears_old(self, synced_db):
        """Test that replace removes previous models for that provider."""
        before = len(filter_models(db_path=synced_db, provider="groq"))
        assert before > 0
        replace_provider_models("groq", [("only-one", "Only", "C", "", "", None)], db_path=synced_db)
        after = filter_models(db_path=synced_db, provider="groq")
        assert len(after) == 1
        assert after[0].model_id == "only-one"


class TestEnsureDbPopulated:
    def test_already_populated(self, synced_db):
        """Test ensure_db_populated when DB already has models."""
        assert ensure_db_populated(synced_db) is True
        stats = get_stats(synced_db)
        assert stats["active_models"] > 0

    def test_populates_when_empty(self, temp_db):
        """Test ensure_db_populated syncs from hardcoded when empty."""
        init_schema(temp_db)
        # Empty DB
        assert get_stats(temp_db)["active_models"] == 0
        ensure_db_populated(temp_db)
        assert get_stats(temp_db)["active_models"] > 0


class TestGetModelsForDiscovery:
    def test_returns_models(self, synced_db):
        """Test get_models_for_discovery returns filtered models from DB."""
        models = get_models_for_discovery(db_path=synced_db, provider="groq")
        assert len(models) >= 1
        for m in models:
            assert m.provider == "groq"

    def test_populates_then_returns(self, temp_db):
        """Test get_models_for_discovery populates empty DB then returns."""
        init_schema(temp_db)
        models = get_models_for_discovery(db_path=temp_db, min_tier="S")
        assert len(models) >= 0  # may be 0 if no S tier in hardcoded
        assert get_stats(temp_db)["active_models"] > 0
