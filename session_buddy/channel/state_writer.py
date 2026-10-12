"""Channel session state writer — validate-on-write at event boundaries.

Producer for the S-CHANNEL-DURABLE plan. Channel event handlers
(Slack/Signal/terminal) call :func:`record_channel_session_state`
with the actor/context observed from a channel event; this module
validates the payload against the locally-owned
:class:`session_buddy.channel._models.ChannelSessionState` schema.

Per Phase 8 Task 7: the entity type moved from ``dhara.schema``
to a session-buddy-local msgspec.Struct (mirrors the architectural
decision made for mahavishnu's WorkflowOutcome/ApprovalLog/
WebhookIngress — see plan Task 2 for the rationale).

Phase 5 of the UUID7-only migration plan (2026-10-11) deleted the
dhara substrate-compat shim (``session_buddy._dhara_substrate_compat``)
because the dhara substrate is being retired (per memory rule
``feedback-substrate-compat-shim-rot.md``, confirmed 2026-10-11 in
the Bodai ULID→UUID7 migration). Channel session state
persistence is therefore a no-op until a replacement substrate is
wired. The validation path remains — invalid payloads still raise
:class:`msgspec.ValidationError` so caller-side bugs surface.

The feature flag (``CHANNEL_SESSION_STATE_V1_ENABLED``) is
consulted at the *call site* — see
``session_buddy/mcp/tools/session/channel_tracking_tools.py:track_channel_session``.
The producer itself does not read the env var; this keeps the
producer a pure validate function whose only side effects are the
counter increment and the structured log line.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import msgspec
from oneiric.core.logging import get_logger

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
    """Validate the channel session state payload; persistence is a no-op.

    Returns the validated :class:`ChannelSessionState` struct. The
    caller (``channel_tracking_tools.py:track_channel_session``)
    owns the feature-flag gate; this function unconditionally
    validates.

    Phase 5 post-state: there is no substrate wired (dhara retired).
    The function still validates the payload (so caller bugs
    surface as :class:`msgspec.ValidationError`) and increments the
    ``attempted`` + ``skipped`` Prometheus counters. The structured
    log line keeps operator observability continuous with the
    pre-Phase-5 unbound-skip branch.
    """
    payload: dict[str, Any] = {
        "channel_type": channel_type,
        "channel_id": channel_id,
        "sender_id": sender_id,
        "last_event_at": last_event_at,
        "metadata": metadata or {},
    }
    validated: ChannelSessionState = msgspec.convert(payload, ChannelSessionState)  # ty: ignore[invalid-assignment]

    # Phase 5: no substrate wired. Counter + log are the only side effects
    # until a replacement substrate is wired. The pre-Phase-5 "dhara.put
    # unbound" branch is structurally identical to this one — what
    # changed is that the unbound state is now permanent.
    COUNTERS.attempted.labels(producer=_PRODUCER_NAME).inc()
    COUNTERS.skipped.labels(producer=_PRODUCER_NAME).inc()
    logger.warning(
        "channel_session_state_persistence_skipped",
        extra={
            "channel_type": channel_type,
            "channel_id": channel_id,
            "sender_id": sender_id,
            "reason": "no_substrate_wired_post_phase5",
        },
    )

    return validated
