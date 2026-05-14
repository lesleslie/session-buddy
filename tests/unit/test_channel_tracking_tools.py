"""Unit tests for channel session tracking tools."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.event_models import ChannelSessionEvent
from session_buddy.mcp.tools.session.channel_tracking_tools import (
    _ChannelSessionStore,
    register_channel_tracking_tools,
)

# ---------------------------------------------------------------------------
# _ChannelSessionStore unit tests
# ---------------------------------------------------------------------------


class TestChannelSessionStore:
    def _event(self, **overrides) -> ChannelSessionEvent:
        defaults = {
            "event_id": "evt-001",
            "event_type": "channel_session_start",
            "channel_type": "slack",
            "channel_id": "D0ABC123",
            "sender_id": "U0XYZ789",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return ChannelSessionEvent(**(defaults | overrides))

    def test_start_returns_session_id(self) -> None:
        store = _ChannelSessionStore()
        event = self._event()
        sid = store.start(event)
        assert sid.startswith("chan_")

    def test_start_idempotent(self) -> None:
        store = _ChannelSessionStore()
        event = self._event()
        sid1 = store.start(event)
        sid2 = store.start(event)
        assert sid1 == sid2

    def test_heartbeat_updates_existing(self) -> None:
        store = _ChannelSessionStore()
        event = self._event()
        sid = store.start(event)
        hb_event = self._event(event_type="channel_heartbeat", message_count=5)
        result_sid = store.heartbeat(hb_event)
        assert result_sid == sid

    def test_heartbeat_returns_none_for_unknown(self) -> None:
        store = _ChannelSessionStore()
        event = self._event(event_type="channel_heartbeat")
        assert store.heartbeat(event) is None

    def test_end_removes_session(self) -> None:
        store = _ChannelSessionStore()
        event = self._event()
        sid = store.start(event)
        end_event = self._event(event_type="channel_session_end")
        result_sid = store.end(end_event)
        assert result_sid == sid
        assert len(store._active) == 0

    def test_end_returns_none_for_unknown(self) -> None:
        store = _ChannelSessionStore()
        event = self._event(event_type="channel_session_end")
        assert store.end(event) is None

    def test_query_filters_by_channel_type(self) -> None:
        store = _ChannelSessionStore()
        store.start(self._event(channel_type="slack", channel_id="D1"))
        store.start(self._event(channel_type="signal", channel_id="D2"))
        results = store.query(channel_type="slack")
        assert len(results) == 1
        assert results[0]["channel_type"] == "slack"

    def test_query_respects_limit(self) -> None:
        store = _ChannelSessionStore()
        for i in range(5):
            store.start(self._event(channel_id=f"D{i}"))
        results = store.query(limit=3)
        assert len(results) == 3

    def test_thread_scoped_sessions_are_independent(self) -> None:
        store = _ChannelSessionStore()
        thread_event = self._event(session_scope="thread", thread_id="T0001")
        conv_event = self._event(session_scope="conversation")
        s1 = store.start(thread_event)
        s2 = store.start(conv_event)
        assert s1 != s2
        assert len(store._active) == 2


# ---------------------------------------------------------------------------
# MCP tool integration tests (via register_channel_tracking_tools)
# ---------------------------------------------------------------------------


def _make_server_and_tools():
    """Create a mock FastMCP server and collect registered tools."""
    tools: dict = {}

    class MockServer:
        def tool(self):
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

    server = MockServer()
    register_channel_tracking_tools(server)  # type: ignore[arg-type]
    return server, tools


class TestTrackChannelSessionTool:
    @pytest.fixture(autouse=True)
    def _fresh_store(self, monkeypatch):
        """Reset the module-level store between tests."""
        import session_buddy.mcp.tools.session.channel_tracking_tools as mod
        monkeypatch.setattr(mod, "_store", _ChannelSessionStore())

    def setup_method(self):
        _, self.tools = _make_server_and_tools()

    async def _call(self, **kwargs):
        defaults = {
            "event_id": "evt-001",
            "event_type": "channel_session_start",
            "channel_type": "slack",
            "channel_id": "D0ABC123",
            "sender_id": "U0XYZ789",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return await self.tools["track_channel_session"](**(defaults | kwargs))

    @pytest.mark.asyncio
    async def test_start_returns_tracked_status(self) -> None:
        result = await self._call()
        assert result["status"] == "tracked"
        assert result["session_id"] is not None

    @pytest.mark.asyncio
    async def test_end_returns_ended_status(self) -> None:
        await self._call(event_id="start")
        result = await self._call(event_id="end", event_type="channel_session_end")
        assert result["status"] == "ended"

    @pytest.mark.asyncio
    async def test_heartbeat_on_unknown_starts_session(self) -> None:
        result = await self._call(event_type="channel_heartbeat")
        assert result["status"] == "tracked"

    @pytest.mark.asyncio
    async def test_invalid_event_type_returns_error(self) -> None:
        result = await self._call(event_type="bad_type")
        assert result["status"] == "error"
        assert "event_type" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_session_scope_returns_error(self) -> None:
        result = await self._call(session_scope="invalid")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_message_preview_truncated(self) -> None:
        long_preview = "x" * 500
        result = await self._call(message_preview=long_preview)
        assert result["status"] == "tracked"


class TestGetChannelSessionsTool:
    @pytest.fixture(autouse=True)
    def _fresh_store(self, monkeypatch):
        import session_buddy.mcp.tools.session.channel_tracking_tools as mod
        monkeypatch.setattr(mod, "_store", _ChannelSessionStore())

    def setup_method(self):
        _, self.tools = _make_server_and_tools()

    @pytest.mark.asyncio
    async def test_empty_returns_no_sessions(self) -> None:
        result = await self.tools["get_channel_sessions"]()
        assert result["status"] == "success"
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_filter_by_channel_type(self) -> None:
        import session_buddy.mcp.tools.session.channel_tracking_tools as mod
        store = mod._store
        ts = datetime.now(UTC).isoformat()
        store.start(ChannelSessionEvent(
            event_id="e1", event_type="channel_session_start",
            channel_type="slack", channel_id="D1", sender_id="U1", timestamp=ts,
        ))
        store.start(ChannelSessionEvent(
            event_id="e2", event_type="channel_session_start",
            channel_type="signal", channel_id="D2", sender_id="U2", timestamp=ts,
        ))
        result = await self.tools["get_channel_sessions"](channel_type="slack")
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_invalid_limit_returns_error(self) -> None:
        result = await self.tools["get_channel_sessions"](limit=0)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_scope_returns_error(self) -> None:
        result = await self.tools["get_channel_sessions"](session_scope="bad")
        assert result["status"] == "error"


# ── Phase 2 tests ───────────────────────────────────────────────

class TestDharaChannelPublisher:
    """Unit tests for DharaChannelPublisher."""

    def test_publisher_init_stores_url(self) -> None:
        from session_buddy.mcp.tools.session.channel_tracking_tools import (
            DharaChannelPublisher,
        )
        pub = DharaChannelPublisher(dhara_url="http://localhost:8683")
        assert pub.dhara_url == "http://localhost:8683"

    @pytest.mark.asyncio
    async def test_publish_calls_record_time_series(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from session_buddy.mcp.tools.session.channel_tracking_tools import (
            DharaChannelPublisher,
        )
        pub = DharaChannelPublisher(dhara_url="http://localhost:8683")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        pub._client = mock_client
        await pub.publish("session_buddy.channel_event", "chan_abc", {"event_type": "channel_session_start"})
        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json") or (call_args.args[1] if len(call_args.args) > 1 else None)
        assert body is not None
        assert body["name"] == "record_time_series"
        assert body["arguments"]["metric_type"] == "session_buddy.channel_event"
        assert body["arguments"]["entity_id"] == "chan_abc"

    @pytest.mark.asyncio
    async def test_publish_swallows_http_errors(self) -> None:
        from unittest.mock import AsyncMock

        import httpx

        from session_buddy.mcp.tools.session.channel_tracking_tools import (
            DharaChannelPublisher,
        )
        pub = DharaChannelPublisher(dhara_url="http://localhost:8683")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        pub._client = mock_client
        # Should not raise
        await pub.publish("session_buddy.channel_event", "chan_abc", {"event_type": "channel_session_start"})

    @pytest.mark.asyncio
    async def test_track_tool_publishes_on_start(self) -> None:
        """track_channel_session fires Dhara publish when dhara_publisher is injected."""
        from session_buddy.mcp.tools.session.channel_tracking_tools import (
            DharaChannelPublisher,
            register_channel_tracking_tools,
        )

        pub = MagicMock(spec=DharaChannelPublisher)
        pub.publish = AsyncMock()

        tools: dict = {}

        class MockServer:
            def tool(self):
                def decorator(fn):
                    tools[fn.__name__] = fn
                    return fn
                return decorator

        server = MockServer()
        register_channel_tracking_tools(server, dhara_publisher=pub)  # type: ignore[arg-type]

        await tools["track_channel_session"](
            event_id="evt-001",
            event_type="channel_session_start",
            channel_type="slack",
            channel_id="C123",
            sender_id="U456",
            timestamp="2026-05-14T00:00:00Z",
            token=None,
        )
        # Yield to allow the fire-and-forget asyncio.create_task to execute
        import asyncio as _asyncio
        await _asyncio.sleep(0)
        pub.publish.assert_awaited_once()
        call_args = pub.publish.call_args
        assert call_args.args[0] == "session_buddy.channel_event"

    @pytest.mark.asyncio
    async def test_track_tool_works_without_publisher(self) -> None:
        """track_channel_session works normally when no dhara_publisher is given."""
        from session_buddy.mcp.tools.session.channel_tracking_tools import (
            register_channel_tracking_tools,
        )

        tools: dict = {}

        class MockServer:
            def tool(self):
                def decorator(fn):
                    tools[fn.__name__] = fn
                    return fn
                return decorator

        server = MockServer()
        register_channel_tracking_tools(server)  # type: ignore[arg-type]

        result = await tools["track_channel_session"](
            event_id="evt-002",
            event_type="channel_session_start",
            channel_type="slack",
            channel_id="C123",
            sender_id="U456",
            timestamp="2026-05-14T00:00:00Z",
            token=None,
        )
        assert result["status"] == "tracked"
