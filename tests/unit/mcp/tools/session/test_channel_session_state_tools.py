"""Unit tests for the channel_session_get_state MCP tool (Phase 5).

Phase 5 of the UUID7-only migration plan (2026-10-11) deleted the
dhara substrate-compat shim (``session_buddy._dhara_substrate_compat``)
because the dhara substrate is being retired (per memory rule
``feedback-substrate-compat-shim-rot.md``). The tool therefore has
no backing store and always returns ``None`` with a structured INFO
log carrying the reason ``no_substrate_wired_post_phase5``. The
contract surface is preserved so downstream MCP clients do not
need to change.

Phase 8 Task 7 update: the schema-registry lazy-load (which used
``dhara.schema.from_dict / to_dict``) was removed in Phase 5 because
dhara is being retired. The consumer now short-circuits to
``return None`` after the structured log; there is no
``msgspec.convert`` call. Test cases that exercised the now-removed
substrate-round-trip path are dropped.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest


def _make_server_and_tools() -> tuple[Any, dict[str, Any]]:
    """Create a mock FastMCP server and collect registered tools.

    Mirrors the harness shape used by
    ``tests/unit/test_channel_tracking_tools.py``. The ``MockServer``
    captures every decorated callable into a dict keyed by
    ``fn.__name__`` so tests can assert on tool registration and
    invoke the coroutine directly without spinning up a real
    FastMCP server.

    The producer/consumer modules are imported lazily inside this
    helper (not at module top) so pytest collection doesn't transitively
    pull in ``session_buddy.mcp.tools.__init__`` → ``agents_tools`` →
    ``agent_schema`` (which has an mcp_common version-skew in the
    pinned env). Lazy import keeps this test collectible even when
    sibling MCP tool modules are broken at import time.
    """
    tools: dict[str, Any] = {}

    class MockServer:
        def tool(self):
            def decorator(fn: Any) -> Any:
                tools[fn.__name__] = fn
                return fn

            return decorator

    from session_buddy.mcp.tools.session.channel_session_state_tools import (
        register_channel_session_state_tools,
    )

    server = MockServer()
    register_channel_session_state_tools(server)  # type: ignore[arg-type]
    return server, tools


class TestChannelSessionGetStateTool:
    """Verify the channel_session_get_state MCP tool Phase 5 no-op contract."""

    def test_registers_tool_on_mcp_server(self) -> None:
        """Tool registration on a MockServer.

        The registrar MUST register exactly one tool whose name matches
        ``channel_session_get_state_tool``. The MCP layer wires the
        consumer alongside the producer's call site at
        ``channel_tracking_tools.track_channel_session`` so the read
        path is no longer dead code (resolves C1 from the multi-agent
        review). Phase 5 retains the registration so downstream MCP
        clients that call this tool do not need to change.
        """
        _server, tools = _make_server_and_tools()

        assert "channel_session_get_state_tool" in tools
        assert len(tools) == 1

    def test_always_returns_none_post_phase5(self) -> None:
        """Phase 5: no substrate wired. The tool returns ``None`` unconditionally.

        Previously, the tool returned ``None`` only when the dhara
        substrate was unbound. After Phase 5, "unbound" is the only
        state, so the unconditional return is the canonical
        representation of "no backing store available."
        """
        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        result = asyncio.run(
            tool(channel_id="C-ANY", sender_id="U-ANY")
        )

        assert result is None

    def test_logs_info_with_phase5_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Phase 5: the no-op is observable via structured INFO log.

        The log line carries ``reason: no_substrate_wired_post_phase5``
        so operators can distinguish "no record" from "substrate
        outage" (which is structurally impossible post-Phase-5) in
        the observability stream.

        Mocks the module-level ``logger`` (oneiric.core.logging
        handles records before they reach the stdlib root, so the
        pytest ``caplog`` fixture is unreliable here). Asserts on the
        ``logger.info.call_args`` instead.
        """
        from session_buddy.mcp.tools.session import (
            channel_session_state_tools as consumer_module,
        )

        fake_logger = MagicMock()
        monkeypatch.setattr(consumer_module, "logger", fake_logger)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        asyncio.run(tool(channel_id="C-OBS", sender_id="U-OBS"))

        fake_logger.info.assert_called_once()
        call_args = fake_logger.info.call_args
        assert call_args.args[0] == "channel_session_state_read_no_substrate"
        assert call_args.kwargs["extra"] == {
            "channel_id": "C-OBS",
            "sender_id": "U-OBS",
            "reason": "no_substrate_wired_post_phase5",
        }
