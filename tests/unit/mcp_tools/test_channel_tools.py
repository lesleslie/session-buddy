"""Verify ``channel_session_get_state`` reads back a persisted ChannelSessionState.

Deviates from the brief by:

- **Payload**: The brief's payload includes ``started_at``, but the
  substrate ``ChannelSessionState`` (see
  ``dhara/schema/channel_session_state.py``) has no such field. With
  ``forbid_unknown_fields=False``, extra fields are silently dropped,
  so the test still passes structurally — but only the four fields
  the struct actually owns are asserted here.
- **Persistence key**: The brief's reference impl uses a trailing
  slash (``channel-sessions/<id>/<sender>/``). Task 1's producer
  (``state_writer.record_channel_session_state``) writes without a
  trailing slash. The consumer must match the producer's format or
  every read silently misses. The test pins the no-trailing-slash
  format.
- **Mocker strategy**: We patch ``dhara.get`` via
  ``monkeypatch.setattr(..., raising=False)`` because the
  substrate-compat gate in the impl uses ``getattr(dhara, "get", None)``
  at every call — caching the resolved attribute at module load would
  defeat the patch and is exactly what the substrate-compat pattern
  was designed to avoid.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from dhara.schema import ChannelSessionState


@pytest.fixture
def valid_payload() -> dict:
    """A substrate-conformant payload — only fields the struct owns."""
    return {
        "channel_type": "slack",
        "channel_id": "C123",
        "sender_id": "U456",
        "last_event_at": datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC).isoformat(),
        "metadata": {},
    }


def test_channel_session_get_state_returns_validated_struct(
    monkeypatch: pytest.MonkeyPatch, valid_payload: dict
) -> None:
    """Happy path: a present payload decodes into a typed struct."""
    mock_get = MagicMock(return_value=valid_payload)
    monkeypatch.setattr(
        "session_buddy.mcp_tools.channel_tools.dhara.get",
        mock_get,
        raising=False,
    )

    from session_buddy.mcp_tools.channel_tools import channel_session_get_state

    result = channel_session_get_state("C123", "U456")

    assert isinstance(result, ChannelSessionState)
    assert result.channel_type == "slack"
    assert result.channel_id == "C123"
    assert result.sender_id == "U456"
    assert result.last_event_at == datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC)


def test_channel_session_get_state_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substrate returns None → consumer returns None (not a crash)."""
    mock_get = MagicMock(return_value=None)
    monkeypatch.setattr(
        "session_buddy.mcp_tools.channel_tools.dhara.get",
        mock_get,
        raising=False,
    )

    from session_buddy.mcp_tools.channel_tools import channel_session_get_state

    result = channel_session_get_state("missing-channel", "missing-sender")

    assert result is None
    mock_get.assert_called_once_with("channel-sessions/missing-channel/missing-sender")


def test_channel_session_get_state_uses_matching_persistence_key(
    monkeypatch: pytest.MonkeyPatch, valid_payload: dict
) -> None:
    """Pin the persistence key format to Task 1's producer contract.

    Task 1's ``state_writer.record_channel_session_state`` writes to
    ``channel-sessions/{channel_id}/{sender_id}`` — no trailing slash.
    A consumer that reads with a trailing slash silently misses every
    record. This test is the contract.
    """
    mock_get = MagicMock(return_value=valid_payload)
    monkeypatch.setattr(
        "session_buddy.mcp_tools.channel_tools.dhara.get",
        mock_get,
        raising=False,
    )

    from session_buddy.mcp_tools.channel_tools import channel_session_get_state

    channel_session_get_state("C-abc", "U-xyz")

    mock_get.assert_called_once_with("channel-sessions/C-abc/U-xyz")
