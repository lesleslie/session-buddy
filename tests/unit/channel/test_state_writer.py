"""Verify record_channel_session_state validates and persists ChannelSessionState.

v1.1 hardening coverage (multi-agent review addressed):
- env-var helper `_channel_session_state_v1_enabled()` reads
  CHANNEL_SESSION_STATE_V1_ENABLED correctly (default 'true')
- producer's call-time dhara_calltime("put") skips cleanly when
  the substrate is unbound
- producer's call site inherits from substrate-compat gate; raw
  substrate failures do not propagate to the channel event handler (G6)

The flag check itself lives at the call site
(channel_tracking_tools.py:track_channel_session), not in the producer body,
so the producer is exercised without consulting the flag here.

Phase 8 Task 7 update: patches now route through
``session_buddy._dhara_substrate_compat.dhara_calltime`` (the local
import in state_writer), not the live ``dhara`` module. The
``ChannelSessionState`` type comes from the local
``session_buddy.channel._models`` module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

import session_buddy.channel.state_writer as state_writer
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


# --- producer substrate-compat gate -----------------------------------------


def _patch_dhara_calltime(monkeypatch: pytest.MonkeyPatch, target: object | None) -> None:
    """Replace ``state_writer.dhara_calltime`` with a routing stub.

    Returns ``target`` when the producer asks for ``"put"``; returns
    ``None`` for everything else. Mirrors the pattern in
    ``tests/unit/test_webhooks_replay.py`` (mahavishnu).
    """
    def fake_calltime(name: str) -> object | None:
        return target if name == "put" else None

    monkeypatch.setattr(state_writer, "dhara_calltime", fake_calltime)


def test_record_persists_validated_struct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: validate, persist via call-time gate, return typed struct."""
    put_sentinel = MagicMock()
    _patch_dhara_calltime(monkeypatch, put_sentinel)

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
    _patch_dhara_calltime(monkeypatch, put_sentinel)

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
    _patch_dhara_calltime(monkeypatch, None)

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
    _patch_dhara_calltime(monkeypatch, failing_put)

    # Must not raise.
    record = record_channel_session_state(
        channel_type="slack",
        channel_id="C123",
        sender_id="U456",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert isinstance(record, ChannelSessionState)
    assert failing_put.call_count == 1
