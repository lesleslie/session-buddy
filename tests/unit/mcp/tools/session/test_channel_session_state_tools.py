"""Unit tests for the channel_session_get_state MCP tool.

Read-back consumer for the S-CHANNEL-DURABLE plan lineage v1.2
(Task 154 — restoration of the consumer deleted in commit 7b5c746a).
Mirrors the producer-side pattern in
``session_buddy/channel/state_writer.py`` and uses the same
``_dhara_substrate_compat`` helpers so the call-time ``getattr(dhara,
"get", None)`` gate short-circuits cleanly when the substrate is
unbound (G6 contract — read failures must not crash the MCP layer).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

# Skip the whole module when the installed dhara distribution does not
# expose ``dhara.schema``. D-OBJ-SCHEMA has shipped at head but session-buddy
# pins an older version in its lockfile; tracked as a separate dependency
# bump. The skip keeps the suite green while the bump lands.
pytest.importorskip(
    "dhara.schema",
    reason="dhara.schema not in session-buddy's pinned dhara version",
)


def _make_server_and_tools() -> tuple[Any, dict[str, Any]]:
    """Create a mock FastMCP server and collect registered tools.

    Mirrors the harness shape used by
    ``tests/unit/test_channel_tracking_tools.py``. The ``MockServer``
    captures every decorated callable into a dict keyed by
    ``fn.__name__`` so tests can assert on tool registration and
    invoke the coroutine directly without spinning up a real
    FastMCP server.
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
    """Verify the channel_session_get_state MCP tool registration and behavior."""

    def test_registers_tool_on_mcp_server(self) -> None:
        """Tool registration on a MockServer.

        The registrar MUST register exactly one tool whose name matches
        ``channel_session_get_state_tool``. The MCP layer wires the
        consumer alongside the producer's call site at
        ``channel_tracking_tools.track_channel_session`` so the read
        path is no longer dead code (resolves C1 from the multi-agent
        review).
        """
        _server, tools = _make_server_and_tools()

        assert "channel_session_get_state_tool" in tools
        assert len(tools) == 1

    def test_happy_path_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Round-trip via the producer + consumer.

        Writes a payload through the producer's substrate-compat gate
        (a dict-backed ``put``), then resolves the same record via the
        consumer and asserts the returned dict matches the producer's
        ``to_dict`` form.
        """
        from session_buddy.channel import state_writer

        store: dict[str, dict[str, Any]] = {}

        def put(key: str, value: dict[str, Any]) -> None:
            store[key] = value

        def get(key: str) -> dict[str, Any] | None:
            return store.get(key)

        monkeypatch.setattr(state_writer.dhara, "put", put, raising=False)
        monkeypatch.setattr(state_writer.dhara, "get", get, raising=False)

        written = state_writer.record_channel_session_state(
            channel_type="slack",
            channel_id="C-ROUNDTRIP-1",
            sender_id="U-ROUNDTRIP-1",
            last_event_at=datetime(2026, 8, 11, 12, 5, 0, tzinfo=UTC),
            metadata={"branch_reason": "happy-path test"},
        )
        expected = written.to_dict()

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        import asyncio

        result = asyncio.run(
            tool(channel_id="C-ROUNDTRIP-1", sender_id="U-ROUNDTRIP-1")
        )

        assert result == expected
        assert result["channel_id"] == "C-ROUNDTRIP-1"
        assert result["sender_id"] == "U-ROUNDTRIP-1"
        assert result["channel_type"] == "slack"

    def test_substrate_unbound_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``dhara.get`` is ``None`` the tool returns ``None`` without raising.

        The call-time ``getattr`` gate MUST short-circuit cleanly when
        no persistence backend is wired. Matches the producer's
        ``dhara.put is None`` skip branch.
        """
        from session_buddy.channel import state_writer

        monkeypatch.setattr(state_writer.dhara, "get", None, raising=False)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        import asyncio

        result = asyncio.run(
            tool(channel_id="C-MISSING", sender_id="U-MISSING")
        )

        assert result is None

    def test_missing_record_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``dhara.get(key)`` returns ``None`` the tool returns ``None``.

        No error envelope — callers handle missing records cleanly.
        Mirrors the producer's "no-op when substrate unbound" branch:
        neither half crashes the calling MCP client.
        """
        from session_buddy.channel import state_writer

        def get(key: str) -> dict[str, Any] | None:
            return None

        monkeypatch.setattr(state_writer.dhara, "get", get, raising=False)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        import asyncio

        result = asyncio.run(
            tool(channel_id="C-ABSENT", sender_id="U-ABSENT")
        )

        assert result is None

    def test_substrate_exception_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When ``dhara.get`` raises, the tool returns ``None`` and logs WARNING.

        G6 contract: read failures must not crash the consumer. The
        structured warning lets operators observe the failure in
        Dhara/Akosha traces without the call propagating into the
        calling MCP client.
        """
        from session_buddy.channel import state_writer

        def get(key: str) -> dict[str, Any] | None:
            msg = "synthetic substrate outage"
            raise RuntimeError(msg)

        monkeypatch.setattr(state_writer.dhara, "get", get, raising=False)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        import asyncio

        with caplog.at_level("WARNING"):
            result = asyncio.run(
                tool(channel_id="C-BOOM", sender_id="U-BOOM")
            )

        assert result is None
        assert any(
            "channel_session_state_read_failed" in record.message
            for record in caplog.records
        ), "G6 contract requires WARNING log on substrate failure"