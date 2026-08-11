"""Channel session state writer — validate-on-write at event boundaries.

Producer for the S-CHANNEL-DURABLE plan. Channel event handlers
(Slack/Signal/terminal) call :func:`record_channel_session_state`
with the actor/context observed from a channel event; this module
validates the payload against the Bodai dhara schema registry
(``channel_session_state``) and persists the typed struct via
``dhara.put``.

Substrate failures are swallowed (G6 contract): a persistence
backend outage MUST NOT crash the channel tracking path, which
would drop the event handler's heartbeat and (worse) cascade into
the calling nanobot. Validation failures DO propagate — those
indicate a programming error in the caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import dhara
from dhara.schema import ChannelSessionState, validate
from oneiric.core.logging import get_logger

logger = get_logger(__name__)


# Feature flag — defaults on. Flip to False to disable durable
# channel state recording entirely (no validation, no persistence).
S_CHANNEL_DURABLE_V1_ENABLED: bool = True


# Resolved at import time so tests can monkeypatch this module's
# attribute. The Bodai dhara 0.14.0 distribution ships without a
# persistence backend wired, so ``dhara.put`` is typically absent;
# we treat that as a no-op rather than blowing up at import.
_dhara_put: Any = getattr(dhara, "put", None)


def record_channel_session_state(
    channel_type: str,
    channel_id: str,
    sender_id: str,
    last_event_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> ChannelSessionState | None:
    """Validate the channel session state payload and persist via dhara.put.

    Returns the validated :class:`ChannelSessionState` struct on
    success, or ``None`` when the feature flag is disabled.

    Persistence errors are logged and swallowed (G6 contract);
    validation errors propagate as :class:`SchemaValidationError`.
    """
    if not S_CHANNEL_DURABLE_V1_ENABLED:
        return None

    payload: dict[str, Any] = {
        "channel_type": channel_type,
        "channel_id": channel_id,
        "sender_id": sender_id,
        "last_event_at": last_event_at,
        "metadata": metadata or {},
    }
    validated = validate("channel_session_state", payload)

    if _dhara_put is not None:
        key = f"channel-sessions/{channel_id}/{sender_id}"
        try:
            _dhara_put(key, validated)
        except Exception as exc:  # noqa: BLE001 — G6 contract: substrate
            # failures must not crash the channel tracking path.
            logger.warning(
                "channel_session_state_persistence_failed",
                extra={
                    "channel_type": channel_type,
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "exception_type": type(exc).__name__,
                },
            )

    return validated
