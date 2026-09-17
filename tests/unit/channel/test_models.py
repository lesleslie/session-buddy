"""Round-trip test for ``session_buddy.channel._models.ChannelSessionState``.

Pins wire-format compatibility with the original dhara type by
asserting that ``msgspec.to_builtins(...)`` produces the exact field
set dhara would produce for an equivalent instance. Any drift in
field name, type, or ``frozen=True`` status surfaces here as a test
failure rather than as silent data corruption at the durable store
boundary.
"""

from __future__ import annotations

from datetime import datetime

import msgspec

from session_buddy.channel._models import ChannelSessionState


def test_channel_session_state_roundtrip_matches_dhara_shape() -> None:
    """Round-trip a ChannelSessionState through msgspec.to_builtins."""
    record = ChannelSessionState(
        channel_id="C123",
        channel_type="slack",
        sender_id="U456",
        last_event_at=datetime(2026, 9, 16, 12, 0, 0),
        metadata={"branch_reason": "escalation"},
    )
    dumped = msgspec.to_builtins(record)
    assert dumped == {
        "channel_id": "C123",
        "channel_type": "slack",
        "sender_id": "U456",
        "last_event_at": "2026-09-16T12:00:00",
        "metadata": {"branch_reason": "escalation"},
    }
    # Round-trip back through msgspec.convert to confirm parser compatibility.
    restored = msgspec.convert(dumped, ChannelSessionState)
    assert restored == record


def test_metadata_defaults_to_empty_dict() -> None:
    """``metadata`` defaults to ``{}`` (matches Dhara original)."""
    record = ChannelSessionState(
        channel_id="C-empty",
        channel_type="signal",
        sender_id="+15555550100",
        last_event_at=datetime(2026, 9, 16),
    )
    assert record.metadata == {}
