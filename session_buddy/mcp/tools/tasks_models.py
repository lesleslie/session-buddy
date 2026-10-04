"""Pydantic models for the task-system MCP tools.

Implements the data model from
``docs/superpowers/specs/2026-09-29-task-system-design.md`` (Bodai Task
System Design, v1.1, commit b1e2ed76).

This module exposes the typed envelopes every other tasks_* module
imports from. Keep it dependency-light (no DB, no IO) so it can be
imported anywhere without spinning up subsystems.

Required exports (per Task 1 brief):

- Constants: ``TASK_ID_PATTERN``, ``OWNER_PATTERN``
- Helpers: ``new_task_id``
- Type aliases: ``JsonValue``
- Models: ``Task``, ``UpdateTaskRequest``, ``TaskListResult``,
  ``TaskHistoryResult``, ``TaskEvent``, ``HandoffParams``,
  ``HandoffResult``, ``LegacyTaskRow``
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import uuid7

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import JsonValue as _PydanticJsonValue

# ---------------------------------------------------------------------------
# ID + owner patterns (canonical)
# ---------------------------------------------------------------------------

# Full UUID7 hex without dashes, prefixed with ``t-``. 32 lowercase hex chars.
# See spec "ID format" — the 12-hex compact form is *display-only* and never
# a valid lookup key.
TASK_ID_PATTERN = r"^t-[0-9a-f]{32}$"

# Caller-supplied owner. Server-set owners (when derived from the
# authenticated MCP caller identity) bypass this since they're already
# trusted.
OWNER_PATTERN = r"^(user:[a-zA-Z0-9._@-]+|agent:[a-zA-Z0-9._:-]+)$"

# Recursive JSON value type. ``dict[str, JsonValue]`` keys must be ``str``;
# values may be any JSON scalar, list, or nested object. Used for ``metadata``
# and ``diff`` payloads.
#
# We re-export ``pydantic.JsonValue`` (which is defined as
# ``Union[List['JsonValue'], Dict[str, 'JsonValue'], str, int, float, bool, None]``)
# instead of redefining a custom union alias because Pydantic v2's schema
# generator has a special-cased code path for ``pydantic.JsonValue`` that
# handles the self-reference. A bare ``X | list["X"] | dict[str, "X"]``
# type alias triggers infinite recursion in the schema builder.
JsonValue = _PydanticJsonValue


def new_task_id() -> str:
    """Return a canonical task ID: ``t-{32 hex}`` (full UUID7 without dashes).

    The 32 hex chars carry the full UUID7 (74 random bits after the 48-bit
    timestamp prefix) — never truncate to a compact 12-hex form for lookup.
    Use ``metadata.uuid_alias`` for human display.
    """
    return f"t-{uuid7().hex}"


# ---------------------------------------------------------------------------
# Core task envelope
# ---------------------------------------------------------------------------


class Task(BaseModel):
    """A typed task record persisted in session-buddy reflections.

    Field-validators enforce the security-critical invariants called out in
    the design spec:

    - ``due_at`` must be timezone-aware (naive datetimes are rejected to
      prevent silent timezone drift between caller and server).
    - ``tags`` must include the ``"task"`` discriminator so reflection
      scans can filter task rows without parsing ``content``.
    - ``metadata`` serialized size is capped at 1 KiB to bound embedding
      budget and Redis-Stream payload size.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    content: Annotated[str, Field(min_length=1, max_length=4096)]
    owner: Annotated[str | None, Field(pattern=OWNER_PATTERN)] = None
    visibility: Literal["private", "team", "public"] = "private"
    status: Literal["open", "in_progress", "blocked", "done", "cancelled"] = "open"
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    effort: Literal["xs", "s", "m", "l", "xl"] | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=64)]]
    parent_task_id: Annotated[str | None, Field(pattern=TASK_ID_PATTERN)] = None
    workflow_id: str | None = None
    due_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    completed_at: datetime | None = None
    completed_by: str | None = None
    result_notes: Annotated[str | None, Field(max_length=4096)] = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("due_at must be timezone-aware (ISO 8601 with offset)")
        return value

    @field_validator("tags")
    @classmethod
    def tags_must_include_task_discriminator(cls, value: list[str]) -> list[str]:
        if "task" not in value:
            raise ValueError('tags must include "task" discriminator')
        return value

    @field_validator("metadata")
    @classmethod
    def metadata_size_cap(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        # Serialized JSON ≤ 1 KiB; bounds Redis Stream entry size + embedding budget.
        if len(json.dumps(value)) > 1024:
            raise ValueError("metadata serialized size > 1 KiB")
        return value


# ---------------------------------------------------------------------------
# Update envelope (bounded; immutable fields excluded)
# ---------------------------------------------------------------------------


class UpdateTaskRequest(BaseModel):
    """Bounded update payload. Excludes immutable fields (``id``,
    ``created_at``, ``created_by``, ``workflow_id``).

    ``workflow_id`` is server-set by ``tasks_handoff_to_workflow`` only and
    cannot be mutated via this envelope — caller-supplied values are
    silently dropped (the field is absent from this model).
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    content: str | None = None
    visibility: Literal["private", "team", "public"] | None = None
    status: Literal["open", "in_progress", "blocked", "done", "cancelled"] | None = None
    priority: Literal["critical", "high", "normal", "low"] | None = None
    effort: Literal["xs", "s", "m", "l", "xl"] | None = None
    due_at: datetime | None = None
    tags: list[str] | None = None
    parent_task_id: str | None = None
    result_notes: str | None = None
    metadata: dict[str, JsonValue] | None = None


class FieldDiff(BaseModel):
    """One field's before/after in a ``tasks_update`` mutation.

    Emitted as a single-entry ``diff`` dict on each ``TaskUpdatedPayload``
    (one event per changed field per spec §Update Task). Lives in
    ``tasks_models`` so both the tool module and the event payload module
    can import it without a circular import.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    field: str
    before: Any
    after: Any


# ---------------------------------------------------------------------------
# Task event (audit trail)
# ---------------------------------------------------------------------------


class TaskEvent(BaseModel):
    """Append-only audit event. Emitted on every ``tasks_*`` mutation.

    ``diff`` carries ``field → (old, new)`` tuples for ``updated`` events;
    ``None`` for ``created`` / ``completed`` / ``handoff_*`` events.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    event_type: Literal[
        "created",
        "updated",
        "completed",
        "cancelled",
        "handoff_started",
        "handoff_completed",
        "handoff_orphan",
    ]
    actor: str | None = None
    timestamp: datetime
    diff: dict[str, tuple[Any, Any]] | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# List / history results (paginated envelopes)
# ---------------------------------------------------------------------------


class TaskHistoryResult(BaseModel):
    """Paginated task-event history. No ``total`` — history is append-only
    and consumers page forward until ``next_cursor`` is ``None``."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    items: list[TaskEvent]
    next_cursor: str | None = None


class TaskListResult(BaseModel):
    """Paginated list of tasks. ``total`` is the *filtered* count, not the
    global one; ``next_cursor`` is ``None`` when the page exhausts results.

    ``items`` may include :class:`LegacyTaskRow` envelopes when the caller
    opted in via ``tasks_list(include_legacy=True)``; clients render them
    distinctly using the ``_coerced`` marker on the legacy rows."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    # ``LegacyTaskRow`` is defined further down in this module. The union
    # references it as a forward string; ``TaskListResult.model_rebuild()``
    # at the bottom of the file resolves the string once ``LegacyTaskRow``
    # is in scope.
    items: list[Task | LegacyTaskRow]
    next_cursor: str | None = None
    total: int


# Resolve forward references so the ``list[TaskEvent]`` /
# ``list[Task | LegacyTaskRow]`` annotations resolve at runtime. Must run
# AFTER ``LegacyTaskRow`` is defined (see the call at the bottom of this
# module).
TaskHistoryResult.model_rebuild()


# ---------------------------------------------------------------------------
# Handoff envelope (consumed by mahavishnu ``tasks_handoff_to_workflow``)
# ---------------------------------------------------------------------------


class HandoffParams(BaseModel):
    """Typed parameters for dispatch. Replaces free-form ``dict`` so the
    MCP schema advertises valid values to clients."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    timeout_seconds: int | None = None
    pool_selector: Literal["least_loaded", "round_robin", "affinity"] = "least_loaded"
    pool_name: str | None = None
    idempotency_key: str | None = None
    extra_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class HandoffResult(BaseModel):
    """Result envelope returned by ``tasks_handoff_to_workflow`` after
    step 2 (dispatch) succeeds. ``workflow_id`` is the upstream
    ``dispatch_to_pool`` identifier; step 3 (session-buddy update) stores
    it on the task via ``UpdateTaskRequest(metadata__workflow_id=...)``."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)]
    workflow_id: str
    adapter: Literal["prefect", "llamaindex", "agno"]
    started_at: datetime
    pool_name: str


# ---------------------------------------------------------------------------
# Legacy coercion envelope
# ---------------------------------------------------------------------------


class LegacyTaskRow(BaseModel):
    """Backwards-compat envelope for legacy ``store_reflection(tags=["todo"])``
    rows surfaced when ``tasks_list(include_legacy=True)``.

    This is *not* a ``Task`` — the ``id`` is a reflection ID, not a
    ``t-{hex}`` task ID, and the row may be missing typed fields like
    ``owner`` or ``priority``. The ``_coerced=True`` flag (serialized with
    its leading underscore to match the spec's surface) is the marker
    consumers use to render these distinctly and prompt the user to claim
    or delete them.
    """

    # ``populate_by_name`` lets the field be set/serialized under its
    # alias name (``_coerced``) while still accepting the python attribute
    # name (``coerced``) on construction. Pydantic v2 reserves
    # underscore-prefixed names for private attributes, so an alias is
    # required to publish ``_coerced`` in the JSON schema.
    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)

    id: str
    content: str
    tags: list[str]
    coerced: bool = Field(default=True, alias="_coerced")
    note: str = (
        "Legacy store_reflection row; not a typed Task. Use tasks_create for new work."
    )


# Materialise ``TaskListResult.items: list[Task | LegacyTaskRow]`` now
# that ``LegacyTaskRow`` is in scope. Without this ``model_rebuild``
# call, Pydantic's typing resolver raises ``PydanticUndefinedAnnotation``
# at first instantiation because ``from __future__ import annotations``
# keeps the union members as strings.
TaskListResult.model_rebuild()
