"""Unit tests for session_buddy.mcp.tools.session.channel_tracking_tools.

Lifts coverage on ``channel_tracking_tools`` from the existing baseline
(88%) to 100% by re-hitting every branch in the scoped test directory.
Mirrors ``tests/unit/test_channel_tracking_tools.py`` with extra
coverage for branches the parallel test file leaves untouched:

- ``DharaChannelPublisher.__aenter__`` / ``__aexit__`` / ``aclose``
- ``_ChannelSessionStore.query`` filter branches (channel_id, sender_id, scope)
- ``_parse_event_timestamp`` fallback when the input is malformed
- ``track_channel_session`` exception paths
- ``get_channel_sessions`` exception path
- ``_make_dhara_publisher`` when ``SESSION_BUDDY_DHARA_URL`` is unset
"""

from __future__ import annotations

import asyncio as _asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest

from session_buddy.mcp.event_models import ChannelSessionEvent
from session_buddy.mcp.tools.session import channel_tracking_tools as mod
from session_buddy.mcp.tools.session.channel_tracking_tools import (
    DharaChannelPublisher,
    _ChannelSessionStore,
    _make_dhara_publisher,
    _parse_event_timestamp,
    register_channel_tracking_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Captures every decorated callable into ``tools``."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture
def fresh_store(monkeypatch: pytest.MonkeyPatch):
    """Reset the module-level ``_store`` between tests."""
    new_store = _ChannelSessionStore()
    monkeypatch.setattr(mod, "_store", new_store)
    return new_store


def _event(**overrides: Any) -> ChannelSessionEvent:
    defaults: dict[str, Any] = {
        "event_id": "evt-1",
        "event_type": "channel_session_start",
        "channel_type": "slack",
        "channel_id": "D0ABC",
        "sender_id": "U0XYZ",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    defaults.update(overrides)
    return ChannelSessionEvent(**defaults)


# ---------------------------------------------------------------------------
# _ChannelSessionStore — extra filter branches
# ---------------------------------------------------------------------------


class TestStoreQueryFilterBranches:
    """Cover every filter branch in ``_ChannelSessionStore.query``."""

    def _seed(self) -> _ChannelSessionStore:
        store = _ChannelSessionStore()
        ts = datetime.now(UTC).isoformat()
        store.start(
            _event(
                channel_type="slack",
                channel_id="D1",
                sender_id="U1",
                session_scope="conversation",
                timestamp=ts,
            )
        )
        store.start(
            _event(
                channel_type="slack",
                channel_id="D2",
                sender_id="U2",
                session_scope="thread",
                thread_id="T1",
                timestamp=ts,
            )
        )
        store.start(
            _event(
                channel_type="signal",
                channel_id="D3",
                sender_id="U3",
                session_scope="conversation",
                timestamp=ts,
            )
        )
        return store

    def test_filter_by_channel_id(self) -> None:
        results = self._seed().query(channel_id="D2")
        assert len(results) == 1
        assert results[0]["channel_id"] == "D2"

    def test_filter_by_sender_id(self) -> None:
        results = self._seed().query(sender_id="U3")
        assert len(results) == 1
        assert results[0]["sender_id"] == "U3"

    def test_filter_by_session_scope(self) -> None:
        results = self._seed().query(session_scope="thread")
        assert len(results) == 1
        assert results[0]["session_scope"] == "thread"

    def test_filter_no_match_returns_empty(self) -> None:
        results = self._seed().query(channel_type="telegram")
        assert results == []

    def test_filter_limit_truncates(self) -> None:
        results = self._seed().query(limit=1)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# _ChannelSessionStore — start idempotency + heartbeat/end on unknown
# ---------------------------------------------------------------------------


class TestStoreStartIdempotencyAndMissing:
    """Branch coverage for ``start`` early-return and ``heartbeat``/``end`` None."""

    def test_start_returns_existing_session_id_when_key_already_active(self) -> None:
        """Calling ``start`` twice on the same key returns the original session_id."""
        store = _ChannelSessionStore()
        ev = _event()
        sid_first = store.start(ev)
        sid_second = store.start(ev)
        assert sid_first == sid_second

    def test_heartbeat_returns_none_when_no_active_session(self) -> None:
        store = _ChannelSessionStore()
        result = store.heartbeat(_event(event_type="channel_heartbeat"))
        assert result is None

    def test_end_returns_none_when_no_active_session(self) -> None:
        store = _ChannelSessionStore()
        result = store.end(_event(event_type="channel_session_end"))
        assert result is None


# ---------------------------------------------------------------------------
# DharaChannelPublisher — async context manager + aclose
# ---------------------------------------------------------------------------


class TestDharaChannelPublisherAsyncContextManager:
    """``__aenter__`` / ``__aexit__`` / ``aclose`` are uncovered in the baseline."""

    @pytest.mark.asyncio
    async def test_aclose_calls_underlying_client(self) -> None:
        pub = DharaChannelPublisher(dhara_url="http://localhost:8683")
        pub._client = AsyncMock()
        await pub.aclose()
        pub._client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aenter_returns_self(self) -> None:
        pub = DharaChannelPublisher(dhara_url="http://localhost:8683")
        result = await pub.__aenter__()
        assert result is pub

    @pytest.mark.asyncio
    async def test_aexit_closes_client(self) -> None:
        pub = DharaChannelPublisher(dhara_url="http://localhost:8683")
        pub._client = AsyncMock()
        # ``__aexit__`` accepts (*exc_info) positional args
        await pub.__aexit__(None, None, None)
        pub._client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_with_statement_closes_client(self) -> None:
        pub = DharaChannelPublisher(dhara_url="http://localhost:8683")
        pub._client = AsyncMock()
        async with pub as bound:
            assert bound is pub
        pub._client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# _parse_event_timestamp — malformed input fallback
# ---------------------------------------------------------------------------


class TestParseEventTimestamp:
    def test_valid_iso_string_passes_through(self) -> None:
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = _parse_event_timestamp(ts.isoformat())
        assert result == ts

    def test_garbage_string_returns_now(self) -> None:
        before = datetime.now(UTC)
        result = _parse_event_timestamp("not-a-timestamp")
        after = datetime.now(UTC)
        # Should be ~now, not garbage
        assert before <= result <= after

    def test_non_string_returns_now(self) -> None:
        """Non-string input (None / int) returns ``datetime.now(UTC)``."""
        before = datetime.now(UTC)
        result = _parse_event_timestamp(None)  # type: ignore[arg-type]
        after = datetime.now(UTC)
        assert before <= result <= after


# ---------------------------------------------------------------------------
# track_channel_session — exception paths + S-CHANNEL-DURABLE flag
# ---------------------------------------------------------------------------


class TestTrackChannelSessionExceptions:
    @pytest.fixture(autouse=True)
    def _setup(self, fresh_store):
        server = _FakeMCP()
        register_channel_tracking_tools(server)
        self.tools = server.tools
        self.store = fresh_store

    async def _call(self, **kwargs: Any) -> dict[str, Any]:
        defaults = {
            "event_id": "evt-1",
            "event_type": "channel_session_start",
            "channel_type": "slack",
            "channel_id": "D0ABC",
            "sender_id": "U0XYZ",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return await self.tools["track_channel_session"](**(defaults | kwargs))

    @pytest.mark.asyncio
    async def test_track_session_returns_heartbeat_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Heartbeat on an existing session returns status='heartbeat'."""
        # Pre-seed an active session so heartbeat finds it.
        self.store.start(_event())

        result = await self._call(event_type="channel_heartbeat")
        assert result["status"] == "heartbeat"

    @pytest.mark.asyncio
    async def test_track_session_heartbeat_unknown_falls_back_to_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Heartbeat on a missing session falls back to ``_store.start`` (status='tracked')."""
        # Empty store — heartbeat finds nothing, falls through to line 305-307.
        result = await self._call(event_type="channel_heartbeat")
        assert result["status"] == "tracked"
        assert result["session_id"] is not None

    @pytest.mark.asyncio
    async def test_track_session_end_unknown_session(self) -> None:
        """End on a missing session returns status='not_found'."""
        result = await self._call(event_type="channel_session_end")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_track_session_returns_internal_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An exception inside ``try`` returns the structured error envelope."""
        # Patch ``record_channel_session_state`` (which IS called in the v1
        # default-on path) to raise; this exercises the catch-all
        # ``except Exception`` branch on line 360-366.
        def _raise(**_kwargs: Any) -> None:
            msg = "synthetic pydantic boom"
            raise ValueError(msg)

        monkeypatch.setattr(mod, "record_channel_session_state", _raise)
        result = await self._call()
        assert result["status"] == "error"
        assert "synthetic pydantic boom" in result["error"]

    @pytest.mark.asyncio
    async def test_track_session_records_state_when_v1_flag_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the S-CHANNEL-DURABLE v1 flag is on, ``record_channel_session_state`` runs."""
        called: dict[str, Any] = {}

        def _record(**kwargs: Any) -> Any:
            called.update(kwargs)
            return None

        monkeypatch.setattr(mod, "_channel_session_state_v1_enabled", lambda: True)
        monkeypatch.setattr(mod, "record_channel_session_state", _record)

        await self._call()
        assert called["channel_id"] == "D0ABC"
        assert called["sender_id"] == "U0XYZ"
        assert called["channel_type"] == "slack"

    @pytest.mark.asyncio
    async def test_track_session_skips_state_recording_when_flag_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the S-CHANNEL-DURABLE v1 flag is off, no state is recorded."""
        called = {"count": 0}

        def _record(**kwargs: Any) -> Any:
            called["count"] += 1
            return None

        monkeypatch.setattr(mod, "_channel_session_state_v1_enabled", lambda: False)
        monkeypatch.setattr(mod, "record_channel_session_state", _record)

        await self._call()
        assert called["count"] == 0

    @pytest.mark.asyncio
    async def test_track_session_invalid_event_type_returns_error(self) -> None:
        """Invalid ``event_type`` short-circuits with a structured error."""
        result = await self._call(event_type="bad_type")
        assert result["status"] == "error"
        assert "event_type" in result["error"]

    @pytest.mark.asyncio
    async def test_track_session_invalid_session_scope_returns_error(self) -> None:
        """Invalid ``session_scope`` short-circuits with a structured error."""
        result = await self._call(session_scope="invalid")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_track_session_fires_dhara_publisher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``dhara_publisher`` is injected, ``publish`` is fired."""
        publisher = MagicMock()
        publisher.publish = AsyncMock()

        server = _FakeMCP()
        register_channel_tracking_tools(server, dhara_publisher=publisher)
        tools = server.tools

        await tools["track_channel_session"](
            event_id="evt-dhara",
            event_type="channel_session_start",
            channel_type="slack",
            channel_id="D-DHARA",
            sender_id="U-DHARA",
            timestamp="2026-09-05T08:00:00Z",
            token=None,
        )
        # Drain fire-and-forget tasks
        pending = [
            t for t in _asyncio.all_tasks() if t is not _asyncio.current_task()
        ]
        if pending:
            await _asyncio.gather(*pending, return_exceptions=True)
        publisher.publish.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_channel_sessions — exception path
# ---------------------------------------------------------------------------


class TestGetChannelSessionsExceptions:
    @pytest.fixture(autouse=True)
    def _setup(self, fresh_store):
        server = _FakeMCP()
        register_channel_tracking_tools(server)
        self.tools = server.tools
        self.store = fresh_store

    @pytest.mark.asyncio
    async def test_internal_error_returns_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _explode(**_kw: Any) -> Any:
            msg = "store boom"
            raise RuntimeError(msg)

        # Production reads ``_store`` from the module, not ``self.store``;
        # patching the bound method on the instance does not affect the
        # module-level reference. Patch the module-level ``_store.query``
        # instead.
        monkeypatch.setattr(mod, "_store", SimpleNamespace(query=_explode))
        result = await self.tools["get_channel_sessions"]()
        assert result["status"] == "error"
        assert "store boom" in result["error"]

    @pytest.mark.asyncio
    async def test_limit_too_high_returns_error(self) -> None:
        result = await self.tools["get_channel_sessions"](limit=999)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_limit_zero_returns_error(self) -> None:
        result = await self.tools["get_channel_sessions"](limit=0)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_session_scope_returns_error(self) -> None:
        result = await self.tools["get_channel_sessions"](session_scope="bad")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_valid_query_returns_success_envelope(self) -> None:
        result = await self.tools["get_channel_sessions"]()
        assert result["status"] == "success"
        assert "queried_at" in result


# ---------------------------------------------------------------------------
# register_channel_tracking_tools — happy paths
# ---------------------------------------------------------------------------


def test_register_attaches_both_tools() -> None:
    server = _FakeMCP()
    register_channel_tracking_tools(server)
    assert "track_channel_session" in server.tools
    assert "get_channel_sessions" in server.tools


# ---------------------------------------------------------------------------
# _make_dhara_publisher — env var unset
# ---------------------------------------------------------------------------


class TestMakeDharaPublisher:
    def test_env_unset_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SESSION_BUDDY_DHARA_URL", raising=False)

        # Force get_settings() to also report no URL by mocking the import.
        class _Settings:
            dhara_url = ""

        monkeypatch.setattr(
            "session_buddy.settings.get_settings",
            lambda: _Settings(),
        )
        result = _make_dhara_publisher()
        assert result is None

    def test_env_set_returns_publisher(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "http://example.invalid:8683")
        result = _make_dhara_publisher()
        assert isinstance(result, DharaChannelPublisher)
        assert result.dhara_url == "http://example.invalid:8683"

    def test_env_strips_trailing_slash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "http://example.invalid:8683/")
        result = _make_dhara_publisher()
        assert isinstance(result, DharaChannelPublisher)
        # The trailing slash should be stripped.
        assert result.dhara_url == "http://example.invalid:8683"

    def test_whitespace_only_env_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "   ")
        result = _make_dhara_publisher()
        # Whitespace-only is treated as empty.
        assert result is None

    def test_settings_url_used_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When env is unset, ``get_settings().dhara_url`` is consulted."""

        class _Settings:
            dhara_url = "http://settings.invalid:8683"

        monkeypatch.delenv("SESSION_BUDDY_DHARA_URL", raising=False)
        # The function does ``from session_buddy.settings import get_settings``
        # inside the block — patching at the source module path intercepts it.
        monkeypatch.setattr(
            "session_buddy.settings.get_settings",
            lambda: _Settings(),
        )
        result = _make_dhara_publisher()
        assert isinstance(result, DharaChannelPublisher)
        assert result.dhara_url == "http://settings.invalid:8683"


# ---------------------------------------------------------------------------
# DharaChannelPublisher.publish — exception path with custom httpx error
# ---------------------------------------------------------------------------


class TestDharaChannelPublisherPublishEdgeCases:
    @pytest.mark.asyncio
    async def test_publish_handles_request_exception(self) -> None:
        """Publish swallows httpx.RequestError so a Dhara outage is non-fatal."""
        import httpx2 as httpx

        pub = DharaChannelPublisher(dhara_url="http://example.invalid:8683")
        pub._client = AsyncMock()
        pub._client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        # MUST NOT raise
        await pub.publish("metric", "entity-1", {"k": "v"})

    @pytest.mark.asyncio
    async def test_publish_uses_correct_endpoint(self) -> None:
        pub = DharaChannelPublisher(dhara_url="http://example.invalid:8683")
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        pub._client = mock_client

        await pub.publish(
            "session_buddy.channel_event",
            "chan_xyz",
            {"event_type": "channel_session_start"},
        )
        mock_client.post.assert_awaited_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == "http://example.invalid:8683/tools/call"
        body = kwargs.get("json") or args[1]
        assert body["name"] == "record_time_series"
        assert body["arguments"]["metric_type"] == "session_buddy.channel_event"
        assert body["arguments"]["entity_id"] == "chan_xyz"
        assert body["arguments"]["record"]["event_type"] == "channel_session_start"