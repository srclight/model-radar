# Changelog

## 0.13.0 — 2026-08-31

- Migrated from the vendored v1 StrictArgsMCP (FastMCP) to **ironmcp** on mcp v2 (`strict_server`/`MCPServer`). All 27 tools verified working over a live session; `test_conformance.py` asserts advertise==runtime across the whole surface. Transport (streamable-http + sse + /healthz + web dashboard) migrated; `stateless_http` moved to the transport layer.


