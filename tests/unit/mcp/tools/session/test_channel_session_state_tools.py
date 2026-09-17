"""Unit tests for the channel_session_get_state MCP tool.

Read-back consumer for the S-CHANNEL-DURABLE plan lineage v1.2
(Task 154 — restoration of the consumer deleted in commit 7b5c746a).
Mirrors the producer-side pattern in
``session_buddy/channel/state_writer.py`` and uses the same
``_dhara_substrate_compat`` helpers so the call-time
``dhara_calltime("get")`` gate short-circuits cleanly when the
substrate is unbound (G6 contract — read failures must not crash
the MCP layer).

Phase 8 Task 7 update: the schema-registry lazy-load (which used
``dhara.schema.from_dict / to_dict``) was removed. The consumer
now uses ``msgspec.convert(payload, ChannelSessionState)`` +
``msgspec.to_builtins(struct)`` directly — no schema-registry
dependency, no "schema unavailable" branch. Test cases that
exercised the now-removed ``_load_schema_registry`` are dropped.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

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


def _patch_dhara_calltime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    put: Any = None,
    get: Any = None,
) -> None:
    """Replace ``state_writer.dhara_calltime`` and ``consumer_module.dhara_calltime``.

    Both modules are imported lazily so this helper doesn't trigger
    the broken mcp_common import chain at test-collection time.
    """
    import session_buddy.channel.state_writer as state_writer
    import session_buddy.mcp.tools.session.channel_session_state_tools as consumer_module

    def state_writer_fake(name: str) -> Any:
        return put if name == "put" else None

    def consumer_fake(name: str) -> Any:
        return get if name == "get" else None

    monkeypatch.setattr(state_writer, "dhara_calltime", state_writer_fake)
    monkeypatch.setattr(consumer_module, "dhara_calltime", consumer_fake)


def _make_payload(channel_id: str = "C-1", sender_id: str = "U-1") -> dict[str, Any]:
    """Return a wire-shape ChannelSessionState payload (matches msgspec.to_builtins output)."""
    return {
        "channel_id": channel_id,
        "channel_type": "slack",
        "sender_id": sender_id,
        "last_event_at": datetime(2026, 8, 11, 12, 5, 0, tzinfo=UTC).isoformat(),
        "metadata": {},
    }


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
        serialized form (``msgspec.to_builtins(struct)``).
        """
        import session_buddy.channel.state_writer as state_writer

        store: dict[str, dict[str, Any]] = {}

        def put(key: str, value: dict[str, Any]) -> None:
            store[key] = value

        def get(key: str) -> dict[str, Any] | None:
            return store.get(key)

        _patch_dhara_calltime(monkeypatch, put=put, get=get)

        written = state_writer.record_channel_session_state(
            channel_type="slack",
            channel_id="C-ROUNDTRIP-1",
            sender_id="U-ROUNDTRIP-1",
            last_event_at=datetime(2026, 8, 11, 12, 5, 0, tzinfo=UTC),
            metadata={"branch_reason": "happy-path test"},
        )

        # Expected payload is the producer's wire form: msgspec.to_builtins
        # on the validated struct. This is what the producer stores and
        # what the consumer's msgspec.convert round-trips back into a struct.
        import msgspec

        expected = msgspec.to_builtins(written)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

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

        The call-time gate MUST short-circuit cleanly when no
        persistence backend is wired. Matches the producer's
        ``dhara.put is None`` skip branch.
        """
        _patch_dhara_calltime(monkeypatch, get=None)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

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
        def get(key: str) -> dict[str, Any] | None:
            return None

        _patch_dhara_calltime(monkeypatch, get=get)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

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
        def get(key: str) -> dict[str, Any] | None:
            msg = "synthetic substrate outage"
            raise RuntimeError(msg)

        _patch_dhara_calltime(monkeypatch, get=get)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        with caplog.at_level("WARNING"):
            result = asyncio.run(
                tool(channel_id="C-BOOM", sender_id="U-BOOM")
            )

        assert result is None
        assert any(
            "channel_session_state_read_failed" in record.message
            for record in caplog.records
        ), "G6 contract requires WARNING log on substrate failure"

    def test_invalid_payload_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the substrate returns a payload missing required fields, msgspec.convert raises.

        Per the producer's docstring: "Validation failures DO propagate —
        those indicate a programming error in the caller." The consumer
        inherits the same contract: stale or malformed substrate payloads
        surface as ``msgspec.ValidationError`` rather than being silently
        coerced.
        """
        # Missing ``channel_type``, ``sender_id``, ``last_event_at``.
        def get(key: str) -> dict[str, Any] | None:
            return {"channel_id": "C-INVALID"}

        _patch_dhara_calltime(monkeypatch, get=get)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        import msgspec

        with pytest.raises(msgspec.ValidationError):
            asyncio.run(
                tool(channel_id="C-INVALID", sender_id="U-INVALID")
            )
