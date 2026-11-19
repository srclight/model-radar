"""The server and its outbound requests report the real package version."""

import re
from pathlib import Path

import model_radar
from model_radar import USER_AGENT, __version__

SRC = Path(model_radar.__file__).parent


def test_user_agent_carries_package_version():
    assert USER_AGENT.startswith(f"model-radar/{__version__} ")


def test_no_hardcoded_user_agent_versions():
    stale = re.compile(r"model-radar/\d+\.\d+")
    offenders = [p.name for p in SRC.glob("*.py") if stale.search(p.read_text())]
    assert offenders == []


def test_mcp_handshake_reports_version():
    from model_radar.server import create_server

    assert create_server().version == __version__


def test_pyproject_version_matches_package():
    pyproject = SRC.parent.parent / "pyproject.toml"
    if not pyproject.exists():  # installed from a wheel
        return
    m = re.search(r'^version = "([^"]+)"', pyproject.read_text(), re.M)
    assert m and m.group(1) == __version__
