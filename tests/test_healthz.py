"""Always-on /healthz payload for update scripts."""

from model_radar.server import health_payload


def test_health_payload_reports_version_and_still_free():
    body = health_payload()
    assert body["ok"] is True
    assert body["version"]
    assert "still_free" in body["tools"]
    assert body["has_still_free"] is True
    assert body["listen"] == "127.0.0.1:8743"
