"""Conformance: EVERY tool advertises and enforces the shared argument contract.

Deliberately not a copy of mcpkit's suite (that tests the policy, in its own repo). This tests the
only thing mcpkit cannot: that *this server* actually uses it, across its whole tool surface.

Iterating every tool rather than sampling one is what catches the failures that actually occurred
elsewhere in the estate — five zero-parameter tools left open, and 0 of 42 tools advertising a
contract the runtime was enforcing. It also covers tools added later, and fails on tool #1 if the
server is ever reverted to a bare FastMCP while the vendored _mcpkit.py sits unused.

Scope: this is the TOP-LEVEL argument contract. A nested object argument is validated by its own
model, which this guard does not reach.
"""

import asyncio

from mcp.server.fastmcp.exceptions import ToolError

from model_radar.server import mcp


def test_the_daemons_own_object_is_the_strict_one():
    assert type(mcp).__name__ == "StrictArgsMCP", (
        f"the server object is {type(mcp).__name__}; the vendored policy is not in effect")


def test_every_tool_advertises_the_closed_contract():
    tools = asyncio.run(mcp.list_tools())
    assert tools, "no tools advertised — the server is not what this test thinks it is"
    unstamped = [t.name for t in tools if t.inputSchema.get("additionalProperties") is not False]
    assert not unstamped, (
        f"{len(unstamped)}/{len(tools)} advertise a permissive contract: {unstamped[:6]}")


def test_no_tool_accepts_an_unknown_argument():
    tools = asyncio.run(mcp.list_tools())
    accepted = []
    for t in tools:
        try:
            asyncio.run(mcp.call_tool(t.name, {"zz_bogus_arg_probe": 1}))
            accepted.append(t.name)      # returned a RESULT for an argument it does not have
        except ToolError:
            pass                          # refused: correct
        except Exception:
            pass                          # missing-required etc.: not this test's business
    assert not accepted, f"{len(accepted)} tool(s) accepted an unknown argument: {accepted[:6]}"
