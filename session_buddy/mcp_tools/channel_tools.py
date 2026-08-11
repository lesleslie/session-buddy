"""``channel_session_get_state`` MCP tool — read-back-and-validate consumer.

The consumer half of the S-CHANNEL-DURABLE plan. Reads a persisted
:class:`ChannelSessionState` from the Bodai dhara substrate (the
resident durable store) and reconstructs the typed ``msgspec.Struct``
via :func:`from_dict` so the caller receives a validated object
rather than a raw dict.

Key format MUST match Task 1's producer:

    ``channel-sessions/{channel_id}/{sender_id}``

(no trailing slash — Task 1's ``state_writer.record_channel_session_state``
writes to that exact key. A mismatch would silently miss every read.)

Substrate-compat:

    The Bodai dhara 0.14.0 distribution ships without a persistence
    backend wired, so ``dhara.get`` is typically absent. We treat
    ``None`` returns and missing-backend cases identically: return
    ``None`` to the caller so MCP invocations do not crash when the
    substrate is offline. The G6 contract requires this — channel
    tracking must never go down because persistence is degraded.
"""

from __future__ import annotations

from typing import Any

import dhara
from dhara.schema import ChannelSessionState, from_dict

# Substrate-compat stamp: declared at module load so static checkers
# and runtime introspection both see ``dhara.get`` as a possibly-missing
# attribute. If the installed dhara distribution has no ``get`` binding,
# we stamp ``None`` so the runtime ``getattr`` gate below short-circuits.
if not hasattr(dhara, "get"):
    dhara.get = None  # type: ignore[attr-defined]


def channel_session_get_state(
    channel_id: str, sender_id: str
) -> ChannelSessionState | None:
    """Read back the persisted ChannelSessionState via ``from_dict``.

    Returns ``None`` when:

    * the substrate has no ``get`` binding (dhara backend not wired),
    * the persistence key is absent (no record for this channel/sender
      pair, or it was never written).

    Validation errors from :func:`from_dict` (e.g. payload corrupted on
    disk) propagate as :class:`SchemaValidationError` — those indicate
    a programming error or storage-layer corruption, not a normal
    "missing record" condition.
    """
    get_fn: Any = getattr(dhara, "get", None)
    if get_fn is None:
        return None

    payload: dict[str, Any] | None = get_fn(
        f"channel-sessions/{channel_id}/{sender_id}"
    )
    if payload is None:
        return None

    return from_dict("channel_session_state", payload)
