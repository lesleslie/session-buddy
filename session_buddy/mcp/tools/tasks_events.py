"""Event payload schemas + field sanitizer for task-system events.

All task-system events are emitted on the ``bodai:events`` Redis Stream
under the ``task.*`` namespace (no mixed prefixes).

This module is dependency-light (no DB, no redis client) so it can be
imported by tool bodies, tests, and downstream publisher wiring without
spinning up subsystems.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from session_buddy.mcp.tools.tasks_models import TASK_ID_PATTERN

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
# Publish stub (redis client wiring deferred to T4+)
# ---------------------------------------------------------------------------


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
    """Publish a task event to the ``bodai:events`` Redis Stream.

    Stub: redis client wiring deferred to T4+ (when the first tool that
    actually emits an event lands). For now, this is a typed no-op so
    downstream code can import the symbol and the call site has a stable
    shape.

    Note: ``event_type="task.cancelled"`` reuses ``TaskCompletedPayload``
    (spec is silent on a dedicated cancelled payload model).

    The ``redis`` parameter is accepted as ``Any`` so the stub does not
    force a redis import — T4+ will tighten this to the actual async
    redis client type once it lands.
    """
    return
