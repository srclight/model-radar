"""
SQLite database for model-radar.

Stores model definitions synced from hardcoded providers, ping results,
and cache metadata. Database path: ~/.model-radar/models.db
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CONFIG_DIR
from .providers import PROVIDERS, Model

DB_PATH = CONFIG_DIR / "models.db"


@contextmanager
def get_connection(db_path: Path | None = None):
    """Get a database connection context manager."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_schema(db_path: Path | None = None) -> None:
    """Initialize database schema if tables don't exist."""
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_key TEXT NOT NULL,
                model_id TEXT NOT NULL,
                label TEXT NOT NULL,
                tier TEXT NOT NULL,
                swe_score TEXT,
                context_window TEXT,
                last_pinged_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider_key, model_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ping_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL,
                error_detail TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_models_active ON models(is_active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ping_results_model ON ping_results(model_id, provider_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ping_results_time ON ping_results(recorded_at DESC)")
        conn.commit()


def sync_models(db_path: Path | None = None) -> dict[str, int]:
    """
    Sync hardcoded provider models to database.
    
    Returns dict with counts per provider.
    """
    init_schema(db_path)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        stats = {}
        
        for provider_key, provider in PROVIDERS.items():
            count = 0
            for model_tuple in provider.models:
                model_id, label, tier, swe_score, context = model_tuple
                
                cursor.execute("""
                    INSERT INTO models (provider_key, model_id, label, tier, swe_score, context_window, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(provider_key, model_id) DO UPDATE SET
                        label = excluded.label,
                        tier = excluded.tier,
                        swe_score = excluded.swe_score,
                        context_window = excluded.context_window,
                        updated_at = CURRENT_TIMESTAMP
                """, (provider_key, model_id, label, tier, swe_score, context))
                count += 1
            
            stats[provider_key] = count
        
        conn.commit()
        return stats


def get_all_models(db_path: Path | None = None, active_only: bool = True) -> list[Model]:
    """Get all models from database."""
    init_schema(db_path)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if active_only:
            cursor.execute("""
                SELECT provider_key, model_id, label, tier, swe_score, context_window
                FROM models WHERE is_active = 1
            """)
        else:
            cursor.execute("""
                SELECT provider_key, model_id, label, tier, swe_score, context_window
                FROM models
            """)
        
        return [
            Model(
                provider=row[0],
                model_id=row[1],
                label=row[2],
                tier=row[3],
                swe_score=row[4],
                context=row[5],
            )
            for row in cursor.fetchall()
        ]


def filter_models(
    db_path: Path | None = None,
    tier: str | None = None,
    provider: str | None = None,
    min_tier: str | None = None,
    active_only: bool = True,
) -> list[Model]:
    """Filter models by tier, provider, or min_tier."""
    from .providers import TIER_ORDER
    
    init_schema(db_path)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT provider_key, model_id, label, tier, swe_score, context_window FROM models WHERE 1=1"
        params = []
        
        if active_only:
            query += " AND is_active = 1"
        
        if provider:
            query += " AND provider_key = ?"
            params.append(provider)
        
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        elif min_tier and min_tier in TIER_ORDER:
            min_ord = TIER_ORDER[min_tier]
            placeholders = ",".join("?" for t in TIER_ORDER if TIER_ORDER[t] <= min_ord)
            query += f" AND tier IN ({placeholders})"
            params.extend([t for t in TIER_ORDER if TIER_ORDER[t] <= min_ord])
        
        cursor.execute(query, params)
        
        return [
            Model(
                provider=row[0],
                model_id=row[1],
                label=row[2],
                tier=row[3],
                swe_score=row[4],
                context=row[5],
            )
            for row in cursor.fetchall()
        ]


def record_ping(
    model_id: str,
    provider_key: str,
    status: str,
    latency_ms: float | None = None,
    error_detail: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Record a ping result to the database."""
    init_schema(db_path)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ping_results (model_id, provider_key, status, latency_ms, error_detail)
            VALUES (?, ?, ?, ?, ?)
        """, (model_id, provider_key, status, latency_ms, error_detail))
        
        # Update last_pinged_at on models table
        cursor.execute("""
            UPDATE models SET last_pinged_at = CURRENT_TIMESTAMP
            WHERE provider_key = ? AND model_id = ?
        """, (provider_key, model_id))
        
        conn.commit()


def get_recent_ping(
    model_id: str,
    provider_key: str,
    ttl_seconds: int = 300,
    db_path: Path | None = None,
) -> dict | None:
    """
    Get most recent ping result if not expired.
    
    Returns None if no result or result is older than TTL.
    """
    init_schema(db_path)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, model_id, provider_key, status, latency_ms, error_detail, recorded_at
            FROM ping_results
            WHERE model_id = ? AND provider_key = ?
            ORDER BY recorded_at DESC
            LIMIT 1
        """, (model_id, provider_key))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        # Check TTL
        recorded_at_str = row[6]
        if recorded_at_str:
            # Handle both naive and aware datetimes
            recorded_at_str = recorded_at_str.replace("Z", "+00:00")
            if "+" not in recorded_at_str and "-" not in recorded_at_str[-6:]:
                # Naive datetime, assume UTC
                recorded_at = datetime.fromisoformat(recorded_at_str).replace(tzinfo=timezone.utc)
            else:
                recorded_at = datetime.fromisoformat(recorded_at_str)
            
            age = datetime.now(timezone.utc) - recorded_at
            if age.total_seconds() > ttl_seconds:
                return None
        
        return {
            "id": row[0],
            "model_id": row[1],
            "provider_key": row[2],
            "status": row[3],
            "latency_ms": row[4],
            "error_detail": row[5],
            "recorded_at": row[6],
        }


def get_stats(db_path: Path | None = None) -> dict[str, Any]:
    """Get database statistics."""
    init_schema(db_path)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM models WHERE is_active = 1")
        active_models = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM models WHERE is_active = 0")
        inactive_models = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT provider_key) FROM models WHERE is_active = 1")
        providers = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM ping_results")
        ping_results = cursor.fetchone()[0]
        
        cursor.execute("SELECT MAX(recorded_at) FROM ping_results")
        last_ping = cursor.fetchone()[0]
        
        return {
            "active_models": active_models,
            "inactive_models": inactive_models,
            "providers": providers,
            "ping_results": ping_results,
            "last_ping": last_ping,
        }


def get_provider_stats(db_path: Path | None = None) -> dict[str, dict]:
    """Get per-provider statistics."""
    init_schema(db_path)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT provider_key, COUNT(*) as model_count,
                   SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active_count
            FROM models
            GROUP BY provider_key
        """)
        
        return {
            row[0]: {
                "total_models": row[1],
                "active_models": row[2],
            }
            for row in cursor.fetchall()
        }
