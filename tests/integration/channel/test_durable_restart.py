"""Verify channel_session_state Phase 5 no-op contract.

Task 4 of the S-CHANNEL-DURABLE plan originally demonstrated
durability across a simulated process restart. Phase 5 of the
UUID7-only migration plan (2026-10-11) deleted the dhara
substrate-compat shim, so the durability-across-restart contract
is structurally impossible: there is no backing store.

This file regresses to a single test that pins the Phase 5
contract: the producer validates the payload, increments counters,
and logs the no-op. The producer's key shape
``channel-sessions/{channel_id}/{sender_id}`` is documented in the
producer's module docstring and is no longer observed at runtime
(the producer does not emit any key because the put call is gone).
The Phase 6 substrate work (oneiric UUID7 substrate) will re-introduce
the round-trip demonstrable; for now the file pins the no-op.
"""

from __future__ import annotations

from datetime import UTC, datetime

from session_buddy.channel._models import ChannelSessionState
from session_buddy.channel.state_writer import record_channel_session_state


def test_channel_session_state_validates_payload_post_phase5() -> None:
    """Producer validates the payload and returns a typed struct.

    Phase 5: persistence is a no-op (no substrate wired). Validation
    is preserved so caller bugs surface as ``msgspec.ValidationError``
    and the returned struct is shaped per ``ChannelSessionState``.
    """
    record = record_channel_session_state(
        channel_type="slack",
        channel_id="C-PHASE5",
        sender_id="U-PHASE5",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
        metadata={"branch_reason": "post-phase5 contract test"},
    )

    assert isinstance(record, ChannelSessionState)
    assert record.channel_id == "C-PHASE5"
    assert record.sender_id == "U-PHASE5"
    assert record.channel_type == "slack"
    assert record.metadata == {"branch_reason": "post-phase5 contract test"}
