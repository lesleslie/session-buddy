"""Verify record_channel_session_state validates and persists ChannelSessionState.

v1.1 hardening coverage (multi-agent review addressed):
- env-var helper `_channel_session_state_v1_enabled()` reads
  CHANNEL_SESSION_STATE_V1_ENABLED correctly (default 'true')
- producer's call-time getattr(dhara, "put", None) skips cleanly when
  dhara.put is unbound
- producer's call site inherits from substrate-compat gate; raw
  substrate failures do not propagate to the channel event handler (G6)

The flag check itself lives at the call site
(channel_tracking_tools.py:track_channel_session), not in the producer body,
so the producer is exercised without consulting the flag here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

import dhara
import session_buddy.channel.state_writer as state_writer
from session_buddy.channel.state_writer import (
    _channel_session_state_v1_enabled,
    record_channel_session_state,
)
from dhara.schema import ChannelSessionState


# --- env-var helper ----------------------------------------------------------


def test_v1_enabled_helper_defaults_true_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With CHANNEL_SESSION_STATE_V1_ENABLED unset, the helper returns True."""
    monkeypatch.delenv("CHANNEL_SESSION_STATE_V1_ENABLED", raising=False)
    assert _channel_session_state_v1_enabled() is True


def test_v1_enabled_helper_reads_true_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With CHANNEL_SESSION_STATE_V1_ENABLED='true', the helper returns True."""
    monkeypatch.setenv("CHANNEL_SESSION_STATE_V1_ENABLED", "true")
    assert _channel_session_state_v1_enabled() is True


def test_v1_enabled_helper_reads_false_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With CHANNEL_SESSION_STATE_V1_ENABLED='False' (any non-'true' value), False.

    Only the literal 'false' (case-insensitive) disables the gate — any
    other value (including unset) keeps it on, matching the conservative
    default-on posture of `_approval_log_v1_enabled` in mahavishnu.
    """
    monkeypatch.setenv("CHANNEL_SESSION_STATE_V1_ENABLED", "FALSE")
    assert _channel_session_state_v1_enabled() is False


# --- producer substrate-compat gate -----------------------------------------


def test_record_persists_validated_struct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: validate, persist via call-time getattr, return typed struct."""
    put_sentinel = MagicMock()
    monkeypatch.setattr(dhara, "put", put_sentinel, raising=True)

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
    assert put_sentinel.call_count == 1


def test_record_persists_metadata_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``metadata`` argument is forwarded into the persisted struct."""
    put_sentinel = MagicMock()
    monkeypatch.setattr(dhara, "put", put_sentinel, raising=True)

    record = record_channel_session_state(
        channel_type="signal",
        channel_id="sig-1",
        sender_id="+15555550100",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
        metadata={"branch_reason": "escalation"},
    )

    assert record.metadata == {"branch_reason": "escalation"}
    assert put_sentinel.call_count == 1


def test_record_skips_put_when_dhara_put_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substrate-compat: dhara backend not wired → skip put, still validate."""
    monkeypatch.setattr(dhara, "put", None, raising=True)

    record = record_channel_session_state(
        channel_type="terminal",
        channel_id="term-1",
        sender_id="les",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    # Validation succeeded; nothing propagated.
    assert isinstance(record, ChannelSessionState)


def test_record_swallows_dhara_put_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G6 contract: substrate failures must NOT crash the channel tracking path."""
    failing_put = MagicMock(side_effect=RuntimeError("backend offline"))
    monkeypatch.setattr(dhara, "put", failing_put, raising=True)

    # Must not raise.
    record = record_channel_session_state(
        channel_type="slack",
        channel_id="C123",
        sender_id="U456",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert isinstance(record, ChannelSessionState)
    assert failing_put.call_count == 1
