"""Event payload schemas + field sanitizer for task-system events.

All task-system events are emitted on the ``bodai:events`` Redis Stream
under the ``task.*`` namespace (no mixed prefixes).

This module is dependency-light (no DB, no redis client) so it can be
imported by tool bodies, tests, and downstream publisher wiring without
spinning up subsystems.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from session_buddy.mcp.events.bodai_events_publisher import BodaiEventsPublisher
from session_buddy.mcp.tools.tasks_models import TASK_ID_PATTERN

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field sanitizer
# ---------------------------------------------------------------------------

# Strip every ASCII control char except tab (\x09) and newline (\x0a).
# \x7f (DEL) is also in the strip set.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Cap any single field at 4 KiB — bounds Redis Stream entry size + the
# downstream embedding budget for log dedup.
_MAX_FIELD_BYTES = 4096


def serialize_event_field(value: str | None) -> str | None:
    """Strip control chars except tab/newline; cap at 4096 bytes.

    ``None`` is preserved (not coerced to ``""``) so callers can encode
    "absent" distinctly from "present-but-empty".
    """
    if value is None:
        return None
    s = _CONTROL_CHARS.sub("", value)
    encoded = s.encode("utf-8")[:_MAX_FIELD_BYTES]
    return encoded.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Event payload models (one per task-event type)
# ---------------------------------------------------------------------------


class TaskCreatedPayload(BaseModel):
    """Emitted when a task is first created."""

    model_config = ConfigDict(extra="forbid")

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    owner: str
    actor: str  # == owner for create; auth-derived on server side
    created_at: datetime
    content_hash: str  # sha256 hex digest of content for log dedup


class TaskUpdatedPayload(BaseModel):
    """Emitted on every successful task mutation."""

    model_config = ConfigDict(extra="forbid")

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    actor: str
    updated_at: datetime
    diff: dict[str, tuple[Any, Any]]


class TaskCompletedPayload(BaseModel):
    """Emitted when a task transitions to ``done`` or ``cancelled``."""

    model_config = ConfigDict(extra="forbid")

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    actor: str
    completed_at: datetime
    has_workflow_id: bool  # whether task.workflow_id is set


class TaskHandoffStartedPayload(BaseModel):
    """Emitted when a task is dispatched to a workflow adapter."""

    model_config = ConfigDict(extra="forbid")

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    workflow_id: str
    actor: str
    adapter: Literal["prefect", "llamaindex", "agno"]
    started_at: datetime


class TaskHandoffCompletedPayload(BaseModel):
    """Emitted when the dispatched workflow reports success."""

    model_config = ConfigDict(extra="forbid")

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    workflow_id: str
    actor: str
    completed_at: datetime


class TaskHandoffOrphanPayload(BaseModel):
    """Emitted when a workflow dispatched on behalf of a task never
    reports back (caller disconnected, session-buddy down at step 3,
    or step 3 update failed). ``reason`` carries the canonical enum so
    downstream dashboards can group orphans."""

    model_config = ConfigDict(extra="forbid")

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    workflow_id: str
    actor: str
    reason: Literal[
        "step_3_update_failed",
        "caller_disconnected",
        "session_buddy_down_at_step_3",
    ]
    orphaned_at: datetime


# ---------------------------------------------------------------------------
# Publish wiring (T3 — publisher lives in session_buddy.mcp.events)
# ---------------------------------------------------------------------------


# Maps the public event-type string to the envelope class that should wrap
# a raw payload before it is XADD'd. ``task.cancelled`` deliberately reuses
# ``TaskCompletedPayload`` (spec is silent on a dedicated cancelled model).
_ENVELOPE_BY_EVENT_TYPE: dict[str, type[BaseModel]] = {
    "task.created": TaskCreatedPayload,
    "task.updated": TaskUpdatedPayload,
    "task.completed": TaskCompletedPayload,
    "task.cancelled": TaskCompletedPayload,
    "task.handoff_started": TaskHandoffStartedPayload,
    "task.handoff_completed": TaskHandoffCompletedPayload,
    "task.handoff_orphan": TaskHandoffOrphanPayload,
}

# Module-level slot for the singleton publisher. Task 4 wires a real
# ``BodaiEventsPublisher`` into this slot from
# ``_lifespan_with_dhara_cleanup``; until then ``publish_task_event`` and
# ``publish_task_event_raw`` are typed no-ops.
_publisher: BodaiEventsPublisher | None = None


def _get_publisher() -> BodaiEventsPublisher | None:
    """Return the current ``BodaiEventsPublisher`` (or ``None`` if not yet initialized)."""
    return _publisher


async def publish_task_event(
    event_type: Literal[
        "task.created",
        "task.updated",
        "task.completed",
        "task.cancelled",
        "task.handoff_started",
        "task.handoff_completed",
        "task.handoff_orphan",
    ],
    payload: BaseModel,
    redis: Any = None,
) -> None:
    """Publish a typed ``task.*`` envelope via the configured publisher.

    No-op when ``_publisher`` is ``None`` (Task 4 wires it). The ``redis``
    parameter is preserved for API compatibility — direct-publish support
    is deferred until the typed envelope is replaced by a struct without a
    Pydantic dependency on the cross-package path.

    Note: ``event_type="task.cancelled"`` reuses ``TaskCompletedPayload``
    (spec is silent on a dedicated cancelled payload model).
    """
    publisher = _get_publisher()
    if publisher is None:
        return
    try:
        await publisher.publish(event_type, payload)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully per spec
        logger.warning("bodai_events: publish %s failed: %s", event_type, exc)


async def publish_task_event_raw(
    event_type: str,
    payload: Mapping[str, Any],
    redis: Any = None,
) -> None:
    """Publish a task.* event with a raw dict payload (cross-package API).

    Looks up the envelope class via ``_ENVELOPE_BY_EVENT_TYPE``, sanitizes
    string fields through ``serialize_event_field``, instantiates the
    envelope, and delegates to ``BodaiEventsPublisher.publish``. Unknown
    event types log + return without touching the publisher.

    The ``redis`` parameter is currently unused (kept for future direct-publish
    support and API compatibility with ``publish_task_event``).
    """
    payload_class = _ENVELOPE_BY_EVENT_TYPE.get(event_type)
    if payload_class is None:
        logger.warning("bodai_events: unknown event_type %r", event_type)
        return
    publisher = _get_publisher()
    if publisher is None:
        return
    try:
        sanitized = {
            k: serialize_event_field(v) if isinstance(v, str) else v
            for k, v in payload.items()
        }
        envelope = payload_class(**sanitized)
        await publisher.publish(event_type, envelope)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully per spec
        logger.warning("bodai_events: raw publish %s failed: %s", event_type, exc)
