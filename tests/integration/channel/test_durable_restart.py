"""Verify channel_session_state persists across a simulated process restart.

Task 4 of the S-CHANNEL-DURABLE plan — the demonstrable-by test for
the durability-across-restart Integration Contract.

.. note::
   The round-trip assertions below depend on ``channel_session_get_state``
   (the consumer) and on ``state_writer._dhara_put`` (the producer's
   import-time substrate snapshot). Both have since changed:

   1. Task 147 (commit 7b5c746a) deleted the orphan ``mcp_tools/``
      package because ``channel_session_get_state`` had zero callers in
      the canonical MCP registry — the parallel-package hazard from the
      multi-agent review. Round-trip is no longer demonstrable without a
      consumer.
   2. Task 148 (commit 109b1d98) replaced the import-time
      ``state_writer._dhara_put`` snapshot with call-time
      ``getattr(dhara, "put", None)`` — the patch in
      ``_wire_substrate`` no longer targets a live attribute.

   The test is preserved (with these modules removed) so the producer
   half of the contract (key shape, payload validation) is still
   demonstrable. Restore the consumer and re-introduce the round-trip
   once a follow-up task re-implements ``channel_session_get_state``
   under ``session_buddy/mcp/tools/session/``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

# Skip the whole module when the installed dhara distribution does not
# expose ``dhara.schema``. D-OBJ-SCHEMA has shipped at head but session-buddy
# pins an older version in its lockfile; tracked as a separate dependency
# bump. The skip keeps the suite green while the bump lands.
pytest.importorskip("dhara.schema", reason="dhara.schema not in session-buddy's pinned dhara version")

# ``dhara.schema.ChannelSessionState`` is also referenced by the round-trip
# assertions below; we no longer import it because the consumer half is
# removed. The producer half still uses the import-less payload shape
# (dict) so this is fine.


def _build_substrate() -> tuple[Any, list[str]]:
    """Build a dict-backed put + key recorder (consumer half removed).

    Returns a ``(put, keys_seen)`` pair. ``put`` closes over a shared
    ``dict`` so the producer's write survives within the test process.
    ``keys_seen`` is a list reference for assertions on the exact
    persistence keys the producer emits.
    """
    store: dict[str, dict[str, Any]] = {}
    keys_seen: list[str] = []

    def put(key: str, value: dict[str, Any]) -> None:
        keys_seen.append(key)
        store[key] = value

    return put, keys_seen


def _wire_substrate(
    monkeypatch: pytest.MonkeyPatch,
    put: Any,
) -> None:
    """Patch the substrate-compat handle the producer reads.

    Task 148 moved from the import-time ``_dhara_put`` snapshot to a
    call-time ``getattr(dhara, "put", None)`` gate. We stamp a ``put``
    binding onto the live ``dhara`` module so the producer's gate finds
    it. (The consumer ``get`` binding is no longer needed — see the
    module docstring.)
    """
    from session_buddy.channel import state_writer

    monkeypatch.setattr(state_writer.dhara, "put", put, raising=False)


def test_channel_session_state_producer_emits_correct_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Producer half of the round-trip — pinned persistence key.

    With the consumer deleted (Task 147), the round-trip cannot be
    demonstrated in-process. This test pins the producer half: the
    producer MUST emit ``channel-sessions/{channel_id}/{sender_id}``
    (no trailing slash). A future consumer restoration
    (under ``session_buddy/mcp/tools/session/``) can re-introduce the
    read-back assertion.
    """
    put, keys_seen = _build_substrate()
    _wire_substrate(monkeypatch, put)

    from session_buddy.channel.state_writer import record_channel_session_state

    written = record_channel_session_state(
        channel_type="slack",
        channel_id="C-RESTART-1",
        sender_id="U-RESTART-1",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
        metadata={"branch_reason": "cross-process test"},
    )

    # Producer must emit the no-trailing-slash key. The returned struct
    # validates that the payload round-trips through msgspec cleanly.
    from dhara.schema import ChannelSessionState

    assert isinstance(written, ChannelSessionState)
    assert keys_seen == ["channel-sessions/C-RESTART-1/U-RESTART-1"], (
        "Producer must emit the no-trailing-slash key pinned in Task 1+2"
    )


def test_channel_session_state_distinct_keys_do_not_collide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct (channel_id, sender_id) pairs occupy distinct substrate keys.

    Pins the producer's key naming — one key per (channel, sender) tuple
    so a future consumer's ``get`` only retrieves its own pair. Without
    this, a heartbeat on ``(C-A, U-X)`` could overwrite or shadow a
    record on ``(C-B, U-X)``.
    """
    put, keys_seen = _build_substrate()
    _wire_substrate(monkeypatch, put)

    from session_buddy.channel.state_writer import record_channel_session_state

    record_channel_session_state(
        channel_type="slack",
        channel_id="C-A",
        sender_id="U-X",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )
    record_channel_session_state(
        channel_type="slack",
        channel_id="C-B",
        sender_id="U-X",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )

    assert keys_seen == [
        "channel-sessions/C-A/U-X",
        "channel-sessions/C-B/U-X",
    ]