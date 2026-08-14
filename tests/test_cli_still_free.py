"""CLI still-free must ping by default (Click is_flag gotcha)."""

from unittest.mock import patch

from click.testing import CliRunner

from model_radar.cli import main


async def _fake(*, ping=True):
    return {"completion_calls": int(ping), "hosts": []}


def test_still_free_pings_by_default():
    runner = CliRunner()
    with patch("model_radar.sweep.still_free", new=_fake):
        result = runner.invoke(main, ["still-free"])
    assert result.exit_code == 0
    assert '"completion_calls": 1' in result.output


def test_still_free_no_ping_flag():
    runner = CliRunner()
    with patch("model_radar.sweep.still_free", new=_fake):
        result = runner.invoke(main, ["still-free", "--no-ping"])
    assert result.exit_code == 0
    assert '"completion_calls": 0' in result.output
