"""Verify record_channel_session_state validates payload post-Phase 5.

v1.1 hardening coverage (multi-agent review addressed):
- env-var helper `_channel_session_state_v1_enabled()` reads
  CHANNEL_SESSION_STATE_V1_ENABLED correctly (default 'true')
- producer validates the payload (caller bugs surface as
  ``msgspec.ValidationError``)
- producer emits the structured WARNING log on every call carrying
  ``reason: no_substrate_wired_post_phase5`` so operators can
  observe the no-op

Phase 5 of the UUID7-only migration plan (2026-10-11) deleted the
dhara substrate-compat shim (``session_buddy._dhara_substrate_compat``)
and the ``dhara.put`` call site. The producer's persistence is now
a structured log + counter increment — there is no substrate to put
to. Validation, counter, and log behavior is preserved.

The flag check itself lives at the call site
(channel_tracking_tools.py:track_channel_session), not in the
producer body, so the producer is exercised without consulting the
flag here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from session_buddy.channel import state_writer
from session_buddy.channel._models import ChannelSessionState
from session_buddy.channel.state_writer import (
    _channel_session_state_v1_enabled,
    record_channel_session_state,
)


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


# --- producer Phase 5 no-op contract -----------------------------------------


def test_record_validates_payload_post_phase5() -> None:
    """Phase 5: payload validation still surfaces caller bugs.

    The producer MUST raise ``msgspec.ValidationError`` when the
    payload is malformed — validation failures DO propagate (per the
    pre-Phase-5 contract) because they indicate a programming error
    in the caller. The dhara-persistence removal does not change
    this.
    """
    import msgspec

    with pytest.raises(msgspec.ValidationError):
        record_channel_session_state(
            channel_type="slack",
            channel_id="C-INVALID",
            sender_id="U-INVALID",
            last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
            metadata="this should be a dict not a str",  # type: ignore[arg-type]
        )


def test_record_returns_validated_struct_post_phase5() -> None:
    """Happy path: validate, log no-op, return typed struct.

    The producer's persistence side is now a structured log + counter
    increment. The returned struct carries the validated payload, so
    callers can build their own response without re-validating.
    """
    record = record_channel_session_state(
        channel_type="signal",
        channel_id="sig-1",
        sender_id="+15555550100",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
        metadata={"branch_reason": "escalation"},
    )

    assert isinstance(record, ChannelSessionState)
    assert record.channel_type == "signal"
    assert record.channel_id == "sig-1"
    assert record.sender_id == "+15555550100"
    assert record.metadata == {"branch_reason": "escalation"}


def test_record_logs_warning_with_phase5_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 5: every call logs a WARNING carrying the Phase 5 reason.

    Operator observability requires the structured log line on every
    call so the no-op behavior is observable in Dhara/Akosha traces.
    The ``reason`` field carries the canonical Phase 5 marker.

    Mocks the module-level ``logger`` (oneiric.core.logging handles
    records before they reach the stdlib root, so the pytest
    ``caplog`` fixture is unreliable here). Asserts on the
    ``logger.warning.call_args`` instead.
    """
    fake_logger = MagicMock()
    monkeypatch.setattr(state_writer, "logger", fake_logger)

    record_channel_session_state(
        channel_type="slack",
        channel_id="C-LOG",
        sender_id="U-LOG",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    fake_logger.warning.assert_called_once()
    call_args = fake_logger.warning.call_args
    assert call_args.args[0] == "channel_session_state_persistence_skipped"
    assert call_args.kwargs["extra"] == {
        "channel_type": "slack",
        "channel_id": "C-LOG",
        "sender_id": "U-LOG",
        "reason": "no_substrate_wired_post_phase5",
    }
