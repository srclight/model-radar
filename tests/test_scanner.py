"""Tests for the scanner module."""

from model_radar.providers import Model
from model_radar.scanner import PingResult, ScanState, format_result


def _model(provider="nvidia", model_id="test/model", label="Test Model",
           tier="A", swe="45.0%", ctx="128k"):
    return Model(model_id=model_id, label=label, tier=tier,
                 swe_score=swe, context=ctx, provider=provider)


def test_scan_state_record():
    state = ScanState()
    state.record("nvidia/test", True, 150.0)
    state.record("nvidia/test", True, 250.0)
    state.record("nvidia/test", False, None)

    assert state.ping_counts["nvidia/test"] == 3
    assert state.success_counts["nvidia/test"] == 2
    assert state.avg_latency("nvidia/test") == 200.0
    assert state.uptime_pct("nvidia/test") == pytest.approx(66.67, abs=0.1)


def test_scan_state_empty():
    state = ScanState()
    assert state.avg_latency("nonexistent") is None
    assert state.uptime_pct("nonexistent") is None


def test_format_result_up():
    m = _model()
    r = PingResult(model=m, status="up", latency_ms=123.456)
    d = format_result(r)
    assert d["status"] == "UP"
    assert d["latency_ms"] == 123.5
    assert d["label"] == "Test Model"
    assert d["tier"] == "A"


def test_format_result_with_error():
    m = _model()
    r = PingResult(model=m, status="error", latency_ms=None, error_detail="connection refused")
    d = format_result(r)
    assert d["status"] == "ERROR"
    assert d["error"] == "connection refused"
    assert d["latency_ms"] is None


def test_format_result_with_state():
    m = _model()
    state = ScanState()
    state.record("nvidia/test/model", True, 100.0)
    state.record("nvidia/test/model", True, 200.0)

    r = PingResult(model=m, status="up", latency_ms=150.0)
    d = format_result(r, state)
    assert d["avg_latency_ms"] == 150.0
    assert d["uptime_pct"] == 100.0


import pytest
