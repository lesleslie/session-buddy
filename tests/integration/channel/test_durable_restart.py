"""Verify channel_session_state persists across a simulated process restart.

Task 4 of the S-CHANNEL-DURABLE plan — the demonstrable-by test for
the durability-across-restart Integration Contract.

The test simulates a process restart by:

1. Spinning up an in-memory substrate backed by a ``dict`` that
   survives across the producer/consumer call sites within the test.
2. Calling ``record_channel_session_state`` (producer) once with a
   representative payload.
3. Calling ``channel_session_get_state`` (consumer) and asserting the
   returned ``ChannelSessionState`` struct is field-equal to what the
   producer wrote.

The substrate-compat gates (``getattr(dhara, "put", None)`` for writes,
``getattr(dhara, "get", None)`` for reads) are exercised here against
a synthetic substrate that records every key it sees. The test pins
the persistence-key contract ``channel-sessions/{channel_id}/{sender_id}``
(no trailing slash) that Task 1 + Task 2 negotiated.

Why an in-memory dict (not a real Dhara fixture)?  The Bodai dhara
0.14.0 distribution ships without a persistence backend wired (see
``session_buddy/channel/state_writer.py`` module docstring). True
cross-process durability can only be observed against a wired backend,
which is out of scope for this plan. The dict-backed substrate
proves the **producer/consumer contract** — payload shape, persistence
key, validation, struct reconstruction — which is what a fresh
``python -c`` invocation would exercise in production.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from dhara.schema import ChannelSessionState


def _build_substrate() -> tuple[Any, Any, Any]:
    """Build a dict-backed put/get pair plus a key recorder.

    Returns a ``(put, get, keys_seen)`` triple. ``put`` and ``get`` close
    over a shared ``dict`` so the producer's write is visible to the
    consumer's read without any module-level state leaking between
    tests. ``keys_seen`` is a list reference for assertions on the
    exact persistence keys the producer emits.
    """
    store: dict[str, dict[str, Any]] = {}
    keys_seen: list[str] = []

    def put(key: str, value: dict[str, Any]) -> None:
        keys_seen.append(key)
        store[key] = value

    def get(key: str) -> dict[str, Any] | None:
        return store.get(key)

    return put, get, keys_seen


def _wire_substrate(
    monkeypatch: pytest.MonkeyPatch,
    put: Any,
    get: Any,
) -> None:
    """Patch the substrate-compat handles the producer and consumer read.

    Producer (``state_writer._dhara_put``) — cached at import time as
    ``None`` because the installed dhara distribution has no ``put``
    attribute. We rebind it to the synthetic ``put``.

    Consumer (``channel_tools.dhara.get``) — looked up dynamically on
    every call via ``getattr(dhara, "get", None)``. We stamp a ``get``
    binding onto the live ``dhara`` module so the consumer's
    substrate-compat gate finds it.
    """
    from session_buddy.channel import state_writer
    from session_buddy.mcp_tools import channel_tools

    monkeypatch.setattr(state_writer, "_dhara_put", put, raising=False)
    monkeypatch.setattr(channel_tools.dhara, "get", get, raising=False)


def test_channel_session_state_survives_simulated_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write a state, read it back via the consumer; struct fields match.

    Steps map directly to the Integration Contract:

    * Producer (``record_channel_session_state``) writes the validated
      payload to ``channel-sessions/{channel_id}/{sender_id}``.
    * Consumer (``channel_session_get_state``) reads the same key and
      reconstructs the typed struct via ``from_dict``.
    * Field-by-field equality confirms the wire format the producer
      emits is what the consumer decodes — the contract Task 1 + Task 2
      pinned.
    """
    put, get, keys_seen = _build_substrate()
    _wire_substrate(monkeypatch, put, get)

    from session_buddy.channel.state_writer import record_channel_session_state
    from session_buddy.mcp_tools.channel_tools import channel_session_get_state

    # Producer side — represents process A before "restart".
    written = record_channel_session_state(
        channel_type="slack",
        channel_id="C-RESTART-1",
        sender_id="U-RESTART-1",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
        metadata={"branch_reason": "cross-process test"},
    )

    assert isinstance(written, ChannelSessionState)
    assert keys_seen == ["channel-sessions/C-RESTART-1/U-RESTART-1"], (
        "Producer must emit the no-trailing-slash key Task 2's consumer reads"
    )

    # Consumer side — represents process B after "restart". Substrate
    # handle is the same dict (process restart doesn't reset
    # durable storage), so the read finds the producer's write.
    read = channel_session_get_state("C-RESTART-1", "U-RESTART-1")

    assert read is not None, (
        "Consumer returned None — persistence key mismatch between producer "
        "and consumer would cause this. Verify no trailing slash."
    )
    assert isinstance(read, ChannelSessionState)
    assert read.channel_type == written.channel_type
    assert read.channel_id == written.channel_id
    assert read.sender_id == written.sender_id
    assert read.last_event_at == written.last_event_at
    assert read.metadata == written.metadata


def test_channel_session_state_unrelated_keys_do_not_collide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct (channel_id, sender_id) pairs occupy distinct substrate keys.

    Pins the substrate key naming — the producer MUST emit one key per
    (channel, sender) tuple so the consumer's ``get`` only retrieves
    its own pair. Without this, a heartbeat on ``(C-A, U-X)`` could
    overwrite or shadow a record on ``(C-B, U-X)``.
    """
    put, get, keys_seen = _build_substrate()
    _wire_substrate(monkeypatch, put, get)

    from session_buddy.channel.state_writer import record_channel_session_state
    from session_buddy.mcp_tools.channel_tools import channel_session_get_state

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

    # Producer emitted two distinct keys for the two channel/sender pairs.
    assert keys_seen == [
        "channel-sessions/C-A/U-X",
        "channel-sessions/C-B/U-X",
    ]

    # Each consumer read lands on its own slot — no cross-talk.
    read_a = channel_session_get_state("C-A", "U-X")
    read_b = channel_session_get_state("C-B", "U-X")

    assert read_a is not None and read_b is not None
    assert read_a.channel_id == "C-A"
    assert read_b.channel_id == "C-B"
    assert read_a.sender_id == read_b.sender_id == "U-X"