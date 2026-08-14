"""credits() only reports hosts with a real API. No secrets."""

from unittest.mock import MagicMock, patch

from model_radar.credits import fetch_credits


def test_unknown_provider():
    out = fetch_credits("nvidia", cfg={"api_keys": {}})
    assert "error" in out
    assert "openrouter" in out["supported"]


def test_openrouter_remaining():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"data": {"total_credits": 10.0, "total_usage": 2.5}}
    cfg = {"api_keys": {"openrouter": "sk-or-test"}}
    with patch("model_radar.credits.httpx.get", return_value=mock):
        out = fetch_credits("openrouter", cfg=cfg)
    row = out["results"][0]
    assert row["ok"] is True
    assert row["remaining"] == 7.5


def test_skips_providers_without_keys():
    with patch("model_radar.credits.httpx.get") as get, \
         patch("model_radar.credits.httpx.post") as post:
        out = fetch_credits(cfg={"api_keys": {}})
    get.assert_not_called()
    post.assert_not_called()
    assert out["results"] == []
