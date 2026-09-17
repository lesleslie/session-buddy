"""Channel session state writer — validate-on-write at event boundaries.

Producer for the S-CHANNEL-DURABLE plan. Channel event handlers
(Slack/Signal/terminal) call :func:`record_channel_session_state`
with the actor/context observed from a channel event; this module
validates the payload against the locally-owned
:class:`session_buddy.channel._models.ChannelSessionState` schema
and persists the typed struct via ``dhara.put``.

Per Phase 8 Task 7: the entity type moved from ``dhara.schema``
to a session-buddy-local msgspec.Struct (mirrors the architectural
decision made for mahavishnu's WorkflowOutcome/ApprovalLog/
WebhookIngress — see plan Task 2 for the rationale).

Substrate failures are swallowed (G6 contract): a persistence
backend outage MUST NOT crash the channel tracking path, which
would drop the event handler's heartbeat and (worse) cascade into
the calling nanobot. Validation failures DO propagate — those
indicate a programming error in the caller.

The feature flag (``CHANNEL_SESSION_STATE_V1_ENABLED``) is
consulted at the *call site* — see
``session_buddy/mcp/tools/session/channel_tracking_tools.py:track_channel_session``.
The producer itself does not read the env var; this keeps the
producer a pure validate-and-persist function whose only side
effect is the substrate write.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import msgspec
from oneiric.core.logging import get_logger

from session_buddy._dhara_substrate_compat import dhara_calltime
from session_buddy._producer_metrics import COUNTERS
from session_buddy.channel._models import ChannelSessionState

logger = get_logger(__name__)

# Producer name used for Prometheus label cardinality.
_PRODUCER_NAME = "channel_session_state_writer"


def _channel_session_state_v1_enabled() -> bool:
    """Read the CHANNEL_SESSION_STATE_V1_ENABLED env var (default 'true').

    Mirrors ``_approval_log_v1_enabled`` at
    ``mahavishnu/core/approval_manager.py:22-30``. The flag is
    consulted at the call site
    (``channel_tracking_tools.py:track_channel_session``); this
    helper is exported alongside ``record_channel_session_state``
    so the call site can import both from the same module.
    Only the literal ``"false"`` (case-insensitive) disables the
    gate — any other value (including unset) keeps it on, matching
    the consumer pattern's conservative default-on posture.
    """
    import os

    return os.environ.get("CHANNEL_SESSION_STATE_V1_ENABLED", "true").lower() != "false"


def record_channel_session_state(
    channel_type: str,
    channel_id: str,
    sender_id: str,
    last_event_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> ChannelSessionState:
    """Validate the channel session state payload and persist via dhara.put.

    Returns the validated :class:`ChannelSessionState` struct. The
    caller (``channel_tracking_tools.py:track_channel_session``)
    owns the feature-flag gate; this function unconditionally
    validates and (best-effort) persists.

    Persistence errors are logged and swallowed (G6 contract);
    validation errors propagate as :class:`msgspec.ValidationError`.
    When ``dhara.put`` is unbound (no persistence backend wired),
    a structured warning is emitted so operators can observe the
    no-op in Dhara/Akosha traces without the call crashing.
    """
    payload: dict[str, Any] = {
        "channel_type": channel_type,
        "channel_id": channel_id,
        "sender_id": sender_id,
        "last_event_at": last_event_at,
        "metadata": metadata or {},
    }
    validated: ChannelSessionState = msgspec.convert(payload, ChannelSessionState)  # ty: ignore[invalid-assignment]

    # Substrate-compat gate: only persist when dhara.put is exposed.
    put: Any = dhara_calltime("put")
    COUNTERS.attempted.labels(producer=_PRODUCER_NAME).inc()
    if put is not None:
        key = f"channel-sessions/{channel_id}/{sender_id}"
        try:
            put(key, validated)
            COUNTERS.succeeded.labels(producer=_PRODUCER_NAME).inc()
        except Exception as exc:  # noqa: BLE001 — G6 contract: substrate
            # failures must not crash the channel tracking path.
            # NOTE: swallowed substrate failures are not represented in the
            # 3-counter shape (attempted/succeeded/skipped) — only the
            # unbound skip branch increments skipped. A 4th "failed" counter
            # is a future-work item.
            logger.warning(
                "channel_session_state_persistence_failed",
                extra={
                    "channel_type": channel_type,
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "exception_type": type(exc).__name__,
                },
            )
    else:
        COUNTERS.skipped.labels(producer=_PRODUCER_NAME).inc()
        logger.warning(
            "channel_session_state_persistence_skipped",
            extra={
                "channel_id": channel_id,
                "sender_id": sender_id,
                "reason": "dhara.put_unbound",
            },
        )

    return validated
