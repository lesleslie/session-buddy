"""Verify channel_session_state persists across a simulated process restart.

Task 4 of the S-CHANNEL-DURABLE plan — the demonstrable-by test for
the durability-across-restart Integration Contract.

The round-trip is now demonstrable via ``test_channel_session_state_round_trip``.
Producer emits ``channel-sessions/{channel_id}/{sender_id}`` (no trailing
slash); consumer reads back via ``from_dict`` and returns the validated
struct as a dict.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

# Skip the whole module when the installed dhara distribution does not
# expose ``dhara.schema``. D-OBJ-SCHEMA has shipped at head but session-buddy
# pins an older version in its lockfile; tracked as a separate dependency
# bump. The skip keeps the suite green while the bump lands.
pytest.importorskip("dhara.schema", reason="dhara.schema not in session-buddy's pinned dhara version")


def _build_substrate() -> tuple[Any, Any, list[str]]:
    """Build a dict-backed put + get + key recorder (round-trip enabled).

    Returns a ``(put, get, keys_seen)`` triple. ``put`` closes over a
    shared ``dict`` so the producer's write survives within the test
    process; ``get`` reads back from the same dict so the consumer can
    observe the write. ``keys_seen`` is a list reference for assertions
    on the exact persistence keys the producer emits.
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
    get: Any | None = None,
) -> None:
    """Patch the substrate-compat handles the producer and consumer read.

    Task 148 moved from the import-time ``_dhara_put`` snapshot to a
    call-time ``getattr(dhara, "put", None)`` gate implemented via the
    ``session_buddy._dhara_substrate_compat`` helpers. We stamp a
    ``put`` binding onto the live ``dhara`` module so the producer's
    gate finds it. The consumer (``channel_session_get_state_tool``)
    reads via the same call-time gate, so when ``get`` is provided we
    stamp it the same way.

    The earlier shape of this helper did
    ``monkeypatch.setattr(state_writer.dhara, ...)``, but ``state_writer``
    no longer carries a ``dhara`` attribute — the producer resolves
    substrate attrs via ``dhara_calltime`` against the live ``dhara``
    module. We patch the module directly, mirroring the unit-test pattern
    in ``tests/unit/channel/test_state_writer.py``.
    """
    import dhara

    monkeypatch.setattr(dhara, "put", put, raising=False)
    if get is not None:
        monkeypatch.setattr(dhara, "get", get, raising=False)


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
    put, _get, keys_seen = _build_substrate()
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
    put, _get, keys_seen = _build_substrate()
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


def test_channel_session_state_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-trip via the producer + the restored consumer (Task 154).

    Builds a dict-backed substrate with both ``put`` and ``get`` (the
    ``get`` reads back from the same shared dict), wires both producer
    and consumer bindings, then exercises the full
    write-validate/read-reconstruct flow. The producer's
    ``record_channel_session_state`` returns a
    ``ChannelSessionState`` struct; the consumer's
    ``channel_session_get_state_tool`` reads it back via ``from_dict``
    and returns the validated shape as a dict.

    The producer-half ``payload`` dict written into the substrate is
    the producer's internal representation; the consumer's
    reconstructed dict uses the dhara schema registry's normalized
    shape (datetime -> ISO string, etc.). The assertion compares the
    reconstructed dict's identity fields (channel_id, sender_id,
    channel_type) so the test does not couple to whatever the
    registry's normalization produces today.
    """
    put, get, keys_seen = _build_substrate()
    _wire_substrate(monkeypatch, put, get)

    from session_buddy.channel.state_writer import record_channel_session_state
    from session_buddy.mcp.tools.session.channel_session_state_tools import (
        register_channel_session_state_tools,
    )

    written = record_channel_session_state(
        channel_type="slack",
        channel_id="C-ROUNDTRIP-RESTART",
        sender_id="U-ROUNDTRIP-RESTART",
        last_event_at=datetime(2026, 8, 11, 9, 0, 0, tzinfo=UTC),
        metadata={"branch_reason": "integration round-trip"},
    )

    # Producer must have emitted the no-trailing-slash key (same pin
    # as ``test_channel_session_state_producer_emits_correct_key``).
    assert keys_seen == [
        "channel-sessions/C-ROUNDTRIP-RESTART/U-ROUNDTRIP-RESTART"
    ]

    # Register the consumer on a MockServer (mirrors the unit test
    # harness so we do not spin up a real FastMCP server here).
    tools: dict[str, Any] = {}

    class _MockServer:
        def tool(self):
            def decorator(fn: Any) -> Any:
                tools[fn.__name__] = fn
                return fn

            return decorator

    register_channel_session_state_tools(_MockServer())  # type: ignore[arg-type]

    tool = tools["channel_session_get_state_tool"]
    result = asyncio.run(
        tool(channel_id="C-ROUNDTRIP-RESTART", sender_id="U-ROUNDTRIP-RESTART")
    )

    # The consumer returns the validated struct as a dict (via
    # ``to_dict``). The registry's normalization can include default
    # keys or formatting we do not want to pin here — compare the
    # identity fields the schema enforces, plus the original metadata.
    assert result is not None
    assert result["channel_id"] == "C-ROUNDTRIP-RESTART"
    assert result["sender_id"] == "U-ROUNDTRIP-RESTART"
    assert result["channel_type"] == "slack"
    assert result["metadata"] == {"branch_reason": "integration round-trip"}
    # The producer-returned struct's to_dict form is the source of
    # truth for the round-trip contract; if both halves agree on the
    # canonical dict, the round-trip is demonstrable. ``to_dict`` is a
    # free function from ``dhara.schema`` (not a method on the struct),
    # mirroring how the consumer in ``channel_session_state_tools.py``
    # reconstructs the canonical shape.
    from dhara.schema import to_dict

    assert result == to_dict(written)
