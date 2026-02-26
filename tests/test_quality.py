"""Tests for the quality memory module."""

import json

import pytest

from model_radar.quality import (
    QUALITY_PATH,
    get_model_quality,
    get_quality_summary,
    load_quality,
    record_benchmark,
    save_quality,
)


@pytest.fixture(autouse=True)
def _patch_quality_path(tmp_path, monkeypatch):
    """Redirect quality storage to temp dir."""
    test_path = tmp_path / "quality.json"
    monkeypatch.setattr("model_radar.quality.QUALITY_PATH", test_path)
    monkeypatch.setattr("model_radar.quality.CONFIG_DIR", tmp_path)
    return test_path


def test_load_empty():
    assert load_quality() == {}


def test_save_and_load(tmp_path, _patch_quality_path):
    data = {"test/model": {"passed": 4, "total": 5, "pct": 80}}
    save_quality(data)
    loaded = load_quality()
    assert loaded["test/model"]["passed"] == 4


def test_record_benchmark():
    record_benchmark("test/model", passed=4, total=5,
                     details=[{"name": "math", "passed": True}])
    q = get_model_quality("test/model")
    assert q is not None
    assert q["passed"] == 4
    assert q["pct"] == 80
    assert "last_benchmarked" in q


def test_get_model_quality_missing():
    assert get_model_quality("nonexistent/model") is None


def test_quality_summary_empty():
    summary = get_quality_summary()
    assert summary["benchmarked_models"] == 0


def test_quality_summary_with_data():
    record_benchmark("good/model", passed=5, total=5)
    record_benchmark("ok/model", passed=3, total=5)
    record_benchmark("bad/model", passed=1, total=5)
    summary = get_quality_summary()
    assert summary["benchmarked_models"] == 3
    assert "good/model" in summary["good"]
    assert "ok/model" in summary["mediocre"]
    assert "bad/model" in summary["bad"]
