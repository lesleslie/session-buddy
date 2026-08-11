"""Verify track_channel_session emits ChannelSessionState on each event.

Task 3 of the S-CHANNEL-DURABLE plan: wires the
``record_channel_session_state`` producer (Task 1) into the existing
``track_channel_session`` MCP tool. The test patches the producer at
its import site inside ``channel_tracking_tools`` and asserts the
writer is invoked for start, heartbeat, and end events.

The brief's example test used a different module path
(``session_buddy.track_channel_session.record_channel_session_state``)
because the brief was written before the file was refactored into
``session_buddy/mcp/tools/session/channel_tracking_tools.py``. The
patch path here matches the actual wiring site.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.mcp.tools.session import channel_tracking_tools as ctt


def _make_server_and_tools() -> tuple[object, dict[str, object]]:
    """Create a mock FastMCP server and collect registered tools."""
    tools: dict = {}

    class MockServer:
        def tool(self):
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

    server = MockServer()
    ctt.register_channel_tracking_tools(server)  # type: ignore[arg-type]
    return server, tools


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level store between tests."""
    monkeypatch.setattr(ctt, "_store", ctt._ChannelSessionStore())


def _start_kwargs(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "event_id": "evt-001",
        "event_type": "channel_session_start",
        "channel_type": "slack",
        "channel_id": "C999",
        "sender_id": "U777",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return {**defaults, **overrides}


@pytest.mark.asyncio
async def test_track_channel_session_emits_state_on_start() -> None:
    """A start event triggers exactly one record_channel_session_state call."""
    _, tools = _make_server_and_tools()
    track = tools["track_channel_session"]  # type: ignore[index]

    with patch.object(ctt, "record_channel_session_state", MagicMock()) as mock_writer:
        result = await track(**_start_kwargs())  # type: ignore[func-returns-value]

    assert result["status"] == "tracked"
    mock_writer.assert_called_once()
    call_kwargs = mock_writer.call_args.kwargs
    assert call_kwargs["channel_type"] == "slack"
    assert call_kwargs["channel_id"] == "C999"
    assert call_kwargs["sender_id"] == "U777"
    assert "last_event_at" in call_kwargs


@pytest.mark.asyncio
async def test_track_channel_session_emits_state_on_heartbeat() -> None:
    """A heartbeat event (after a start) triggers a state write."""
    _, tools = _make_server_and_tools()
    track = tools["track_channel_session"]  # type: ignore[index]

    with patch.object(ctt, "record_channel_session_state", MagicMock()) as mock_writer:
        # Prime the store with a start
        await track(**_start_kwargs())  # type: ignore[func-returns-value]
        mock_writer.reset_mock()

        result = await track(  # type: ignore[func-returns-value]
            **_start_kwargs(
                event_id="evt-002",
                event_type="channel_heartbeat",
            )
        )

    assert result["status"] == "heartbeat"
    mock_writer.assert_called_once()


@pytest.mark.asyncio
async def test_track_channel_session_emits_state_on_end() -> None:
    """An end event (after a start) triggers a state write."""
    _, tools = _make_server_and_tools()
    track = tools["track_channel_session"]  # type: ignore[index]

    with patch.object(ctt, "record_channel_session_state", MagicMock()) as mock_writer:
        await track(**_start_kwargs())  # type: ignore[func-returns-value]
        mock_writer.reset_mock()

        result = await track(  # type: ignore[func-returns-value]
            **_start_kwargs(
                event_id="evt-003",
                event_type="channel_session_end",
            )
        )

    assert result["status"] == "ended"
    mock_writer.assert_called_once()
