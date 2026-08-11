"""Verify record_channel_session_state validates and persists ChannelSessionState.

Deviates from the brief by:
- Omitting ``started_at`` — the substrate ``ChannelSessionState`` has no such
  field (only ``channel_id``, ``channel_type``, ``sender_id``,
  ``last_event_at``, ``metadata``).
- Adding substrate-compat coverage for the missing ``dhara.put`` attribute
  (the installed Bodai dhara 0.14.0 has no persistence backend wired).
- Covering G6 contract: ``dhara.put`` failures must NOT propagate to the
  channel event handler that called this writer.
- Covering the ``S_CHANNEL_DURABLE_V1_ENABLED`` feature flag (default True).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from dhara.schema import ChannelSessionState


@pytest.fixture
def dhara_put(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch ``dhara.put`` into ``state_writer``'s module namespace."""
    mock_put = MagicMock()
    monkeypatch.setattr(
        "session_buddy.channel.state_writer._dhara_put", mock_put, raising=False
    )
    return mock_put


@pytest.fixture
def enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the feature flag is on for tests that exercise the happy path."""
    monkeypatch.setattr(
        "session_buddy.channel.state_writer.S_CHANNEL_DURABLE_V1_ENABLED", True
    )


def test_record_persists_validated_struct(
    dhara_put: MagicMock, enable_flag: None
) -> None:
    """Happy path: validate, persist, return the typed struct."""
    from session_buddy.channel.state_writer import record_channel_session_state

    record = record_channel_session_state(
        channel_type="slack",
        channel_id="C123",
        sender_id="U456",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert isinstance(record, ChannelSessionState)
    assert record.channel_type == "slack"
    assert record.channel_id == "C123"
    assert record.sender_id == "U456"
    assert dhara_put.call_count == 1


def test_record_persists_metadata_when_provided(
    dhara_put: MagicMock, enable_flag: None
) -> None:
    """``metadata`` argument is forwarded into the persisted struct."""
    from session_buddy.channel.state_writer import record_channel_session_state

    record = record_channel_session_state(
        channel_type="signal",
        channel_id="sig-1",
        sender_id="+15555550100",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
        metadata={"branch_reason": "escalation"},
    )

    assert record.metadata == {"branch_reason": "escalation"}
    assert dhara_put.call_count == 1


def test_record_swallows_dhara_put_errors(
    monkeypatch: pytest.MonkeyPatch, enable_flag: None
) -> None:
    """G6 contract: substrate failures must NOT crash the channel tracking path."""
    from session_buddy.channel import state_writer

    failing_put = MagicMock(side_effect=RuntimeError("backend offline"))
    monkeypatch.setattr(state_writer, "_dhara_put", failing_put, raising=False)

    # Must not raise
    record = state_writer.record_channel_session_state(
        channel_type="slack",
        channel_id="C123",
        sender_id="U456",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert isinstance(record, ChannelSessionState)
    assert failing_put.call_count == 1


def test_record_skips_put_when_dhara_put_missing(
    monkeypatch: pytest.MonkeyPatch, enable_flag: None
) -> None:
    """Substrate-compat: dhara backend not wired → skip put, still validate."""
    from session_buddy.channel import state_writer

    monkeypatch.setattr(state_writer, "_dhara_put", None, raising=False)

    record = state_writer.record_channel_session_state(
        channel_type="terminal",
        channel_id="term-1",
        sender_id="les",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert isinstance(record, ChannelSessionState)


def test_record_respects_disabled_feature_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag off → no validation, no persistence, returns None."""
    from session_buddy.channel import state_writer

    monkeypatch.setattr(state_writer, "S_CHANNEL_DURABLE_V1_ENABLED", False)
    sentinel = MagicMock()
    monkeypatch.setattr(state_writer, "_dhara_put", sentinel, raising=False)

    result = state_writer.record_channel_session_state(
        channel_type="slack",
        channel_id="C123",
        sender_id="U456",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert result is None
    assert sentinel.call_count == 0