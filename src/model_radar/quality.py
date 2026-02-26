"""
Persistent quality memory for model-radar.

Stores benchmark scores per model so get_fastest and scan can factor in
proven quality, not just latency. Scores persist across MCP sessions in
~/.model-radar/quality.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import CONFIG_DIR

QUALITY_PATH = CONFIG_DIR / "quality.json"


def load_quality() -> dict:
    """Load quality scores from disk. Returns {model_id: {...}}."""
    if QUALITY_PATH.exists():
        try:
            data = json.loads(QUALITY_PATH.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_quality(data: dict) -> None:
    """Write quality scores to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        QUALITY_PATH.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def record_benchmark(model_id: str, passed: int, total: int,
                     details: list[dict] | None = None) -> None:
    """Record a benchmark result for a model."""
    data = load_quality()
    data[model_id] = {
        "passed": passed,
        "total": total,
        "pct": round(passed / total * 100) if total > 0 else 0,
        "last_benchmarked": datetime.now(timezone.utc).isoformat(),
        "details": details,
    }
    save_quality(data)


def get_model_quality(model_id: str) -> dict | None:
    """Get stored quality score for a model, or None if never benchmarked."""
    data = load_quality()
    return data.get(model_id)


def get_quality_summary() -> dict:
    """Get summary of all benchmarked models."""
    data = load_quality()
    if not data:
        return {
            "benchmarked_models": 0,
            "message": "No models benchmarked yet. Run benchmark() to test model quality.",
        }
    good = [mid for mid, q in data.items() if q.get("pct", 0) >= 80]
    ok = [mid for mid, q in data.items() if 40 <= q.get("pct", 0) < 80]
    bad = [mid for mid, q in data.items() if q.get("pct", 0) < 40]
    return {
        "benchmarked_models": len(data),
        "good": good,
        "mediocre": ok,
        "bad": bad,
    }
