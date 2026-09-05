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

import dhara
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

        monkeypatch.setattr(dhara, "put", put, raising=False)
        monkeypatch.setattr(dhara, "get", get, raising=False)

        written = state_writer.record_channel_session_state(
            channel_type="slack",
            channel_id="C-ROUNDTRIP-1",
            sender_id="U-ROUNDTRIP-1",
            last_event_at=datetime(2026, 8, 11, 12, 5, 0, tzinfo=UTC),
            metadata={"branch_reason": "happy-path test"},
        )
        # Use the dhara registry's ``to_dict`` (the same serializer the
        # consumer tool invokes at read-time) to derive the expected
        # payload from the validated struct — ChannelSessionState is a
        # msgspec.Struct with no ``to_dict`` instance method.
        from dhara.schema import to_dict as dhara_to_dict

        expected = dhara_to_dict(written)

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

        monkeypatch.setattr(dhara, "get", None, raising=False)

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

        monkeypatch.setattr(dhara, "get", get, raising=False)

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

        monkeypatch.setattr(dhara, "get", get, raising=False)

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

    def test_schema_registry_unavailable_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When ``dhara.schema`` cannot be imported the tool returns ``None``.

        Exercises the second G6 short-circuit: even if the substrate read
        succeeded, the schema registry lazy-load can fail on session-buddy's
        pinned dhara version. The tool MUST NOT crash — it logs WARNING
        and returns ``None``.
        """
        from session_buddy.mcp.tools.session import channel_session_state_tools as mod

        # Substrate succeeds with a valid payload.
        def get(key: str) -> dict[str, Any] | None:
            return {"channel_id": "C-NOSCHEMA", "sender_id": "U-NOSCHEMA"}

        monkeypatch.setattr(dhara, "get", get, raising=False)

        # Force the schema-registry helper to return None (simulating
        # ``from dhara.schema import from_dict, to_dict`` raising ImportError).
        monkeypatch.setattr(mod, "_load_schema_registry", lambda: None)

        _server, tools = _make_server_and_tools()
        tool = tools["channel_session_get_state_tool"]

        import asyncio

        with caplog.at_level("WARNING"):
            result = asyncio.run(
                tool(channel_id="C-NOSCHEMA", sender_id="U-NOSCHEMA")
            )

        assert result is None
        # Check that the skip warning was emitted with the schema-unavailable
        # reason — the structured ``extra`` payload is JSON-encoded by the
        # oneiric logger so we look for the reason token in the formatted
        # message OR in the structured ``__dict__``.
        skip_logs = [
            r for r in caplog.records
            if "channel_session_state_read_skipped" in r.message
        ]
        assert skip_logs, "G6 contract requires a skip WARNING when schema is unavailable"
        skip_record = skip_logs[-1]
        extras_blob = (
            (skip_record.message or "")
            + " " + str(getattr(skip_record, "reason", "") or "")
        )
        # If the logger formatter exposes ``extra`` as a dict, check that too.
        for attr in ("__dict__",):
            extras_blob += " " + str(getattr(skip_record, attr, {}) or "")
        assert "dhara.schema_unavailable" in extras_blob, (
            f"G6 contract requires reason=dhara.schema_unavailable; got {extras_blob!r}"
        )

    def test_load_schema_registry_returns_none_on_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_load_schema_registry`` returns ``None`` when ``dhara.schema`` is missing."""
        from session_buddy.mcp.tools.session import channel_session_state_tools as mod

        # Simulate ImportError on the ``dhara.schema`` import.
        import builtins

        real_import = builtins.__import__

        def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "dhara.schema" or name.startswith("dhara.schema"):
                msg = "no dhara.schema"
                raise ImportError(msg)
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _guarded_import)

        assert mod._load_schema_registry() is None  # noqa: SLF001

    def test_load_schema_registry_returns_helpers_on_success(self) -> None:
        """``_load_schema_registry`` returns the ``(from_dict, to_dict)`` tuple."""
        from session_buddy.mcp.tools.session import channel_session_state_tools as mod

        # When dhara.schema IS importable, the helper returns the registry tuple.
        # Skip if the installed dhara distribution lacks ``dhara.schema``.
        try:
            from dhara.schema import from_dict, to_dict  # noqa: F401
        except ImportError:
            import pytest

            pytest.skip("dhara.schema not available in this environment")

        result = mod._load_schema_registry()  # noqa: SLF001
        assert result is not None
        from_dict, to_dict = result
        assert callable(from_dict)
        assert callable(to_dict)
