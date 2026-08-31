"""ironmcp conformance: every model-radar tool enforces ADVERTISEMENT == RUNTIME
(unknown args refused, not silently dropped) through a real client<->server session."""

from ironmcp import aassert_enforces_v2

from model_radar.server import create_server


async def test_all_tools_enforce_closed_contract():
    app = create_server()
    enforced = await aassert_enforces_v2(app)
    # model-radar advertises ~27 tools; every one must enforce a closed contract.
    assert enforced >= 20, f"expected ~27 tools to enforce advertise==runtime, got {enforced}"
