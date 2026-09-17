"""Channel session state — locally vendored msgspec.Struct.

Per Phase 8 Task 7 of the Dhara MCP retirement plan: the durable
entity shape used by session-buddy's S-CHANNEL-DURABLE producer
(channel/state_writer.py) and consumer (mcp/tools/session/
channel_session_state_tools.py) is owned by this repo, not by
dhara.schema. Mirrors the architectural decision made for
mahavishnu/core/models/persistence.py (Task 2 of the plan):
"use oneiric models not equivalents" — oneiric stays a substrate
library; consumer-shaped types live in the consumer.

Mirrors ``dhara.schema.ChannelSessionState`` field-for-field:
``channel_id``, ``channel_type``, ``sender_id``, ``last_event_at``,
``metadata`` (default ``{}``). The ``msgspec.Struct(frozen=True)``
form is preserved so ``msgspec.to_builtins(local)`` produces
byte-identical output to ``msgspec.to_builtins(dhara)`` — see
``tests/unit/channel/test_models.py`` for the round-trip pin.

If a future contributor is tempted to "promote" this type to
oneiric, cite the plan's Task 2 architectural decision before
doing so.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import msgspec


class ChannelSessionState(msgspec.Struct, frozen=True):
    """Durable channel session record (S-MEM).

    Mirrors ``dhara.schema.ChannelSessionState`` field-for-field.
    The ``metadata`` field carries S-MEM-VERSIONS extension keys
    (version, parent_session_id, branch_reason).
    """

    channel_id: str
    channel_type: str
    sender_id: str
    last_event_at: datetime
    metadata: dict[str, Any] = msgspec.field(default_factory=dict)


__all__ = ["ChannelSessionState"]
