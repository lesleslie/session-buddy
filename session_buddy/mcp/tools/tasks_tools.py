"""Task-system MCP tools — system of record for the Bodai task system.

Implements the spec at docs/superpowers/specs/2026-09-29-task-system-design.md
(v1.1, commit b1e2ed76).

Server-side identity derivation: ``owner`` / ``created_by`` are ALWAYS set
from the MCP caller identity, regardless of caller-supplied values. Caller
identity is NOT user-controlled — it comes from auth context carried on
the FastMCP ``Context.request_state``.

T4 lands ``tasks_create`` only. T5-T9 add the remaining ``tasks_*`` tools;
T12 wires ``register_tasks_tools(mcp)`` into the FastMCP server.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field

# Sidecar module imported into the module namespace so tests can patch the
# ``find_tasks_by_metadata`` / ``get_engine`` pair without round-tripping
# through ``session_buddy.mcp.tools.tasks_storage``.
from session_buddy.mcp.tools import tasks_storage
from session_buddy.mcp.tools.tasks_events import (
    TaskCreatedPayload,
    publish_task_event,
)
from session_buddy.mcp.tools.tasks_identity import derive_caller_identity
from session_buddy.mcp.tools.tasks_models import (
    TASK_ID_PATTERN,
    JsonValue,
    LegacyTaskRow,
    Task,
    TaskListResult,
    new_task_id,
)
from session_buddy.mcp.tools.tasks_security import (
    MAX_CONTENT_BYTES,
    MAX_TAG_LEN,
    RateLimiter,
    RateLimitError,
    enforce_visibility_filter,
)

# Imported into the module namespace (rather than referenced as
# ``tasks_tools.store_reflection`` from a non-module path) so tests can
# ``patch.object(tasks_tools, "store_reflection", ...)`` and intercept the
# DB call without standing up a real reflection adapter.
from session_buddy.tools.memory_tools import store_reflection

if TYPE_CHECKING:
    from mcp_common.fastmcp import Context

# ---------------------------------------------------------------------------
# Module-level rate limiter
# ---------------------------------------------------------------------------
#
# Spec §Input Limits: ``tasks_create`` is throttled to 60/min per caller.
# One limiter per process; tests reset it via ``tasks_tools._create_rate_limiter``.
_create_rate_limiter: RateLimiter | None = None


def _get_create_limiter() -> RateLimiter:
    """Return the module-level ``tasks_create`` rate limiter (lazy init).

    A module-scoped singleton is required by spec §Input Limits so that
    quota state survives across calls within a single process. Each
    per-caller bucket is keyed on the ``derive_caller_identity`` result
    (already namespaced as ``user:<email>`` or ``agent:<id>``), so two
    callers don't share state.
    """
    global _create_rate_limiter
    if _create_rate_limiter is None:
        _create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    return _create_rate_limiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx_to_auth_context(ctx: Context) -> dict[str, Any]:
    """Adapt a FastMCP ``Context`` to the dict shape ``derive_caller_identity`` expects.

    FastMCP's request state is exposed via ``Context.set_state(key, value)``
    / ``Context.get_state(key)`` — ``Context.request_state`` is a separate
    string-typed channel for the SEP-2322 multi-round-trip guard protocol
    and is NOT a middleware-injectable dict.

    Auth middleware (out of scope for T4) populates
    ``auth_user_email`` and ``auth_agent_id`` keys via ``ctx.set_state(...)``.
    This adapter reads those keys and packs them into the dict shape
    ``derive_caller_identity`` expects. Keys resolve to ``None`` for
    unauthenticated callers, which then fail closed in the spec §Authz
    Model invariant.
    """
    return {
        "auth": {
            "user_email": ctx.get_state("auth_user_email"),
            "agent_id": ctx.get_state("auth_agent_id"),
        },
    }


# ---------------------------------------------------------------------------
# tasks_create
# ---------------------------------------------------------------------------


async def tasks_create(
    ctx: Context,
    content: Annotated[str, Field(min_length=1, max_length=MAX_CONTENT_BYTES)],
    tags: list[Annotated[str, Field(min_length=1, max_length=MAX_TAG_LEN)]],
    owner: str | None = None,  # server overwrites with caller_identity
    due: datetime | None = None,
    priority: Literal["critical", "high", "normal", "low"] = "normal",
    effort: Literal["xs", "s", "m", "l", "xl"] | None = None,
    parent_task_id: Annotated[str | None, Field(pattern=TASK_ID_PATTERN)] = None,
    metadata: dict[str, JsonValue] | None = None,
) -> Task | dict[str, Any]:
    """Create a new task. ``owner`` / ``created_by`` are server-derived from caller identity.

    Returns either a :class:`Task` envelope on success or a
    ``{"status": "error", ...}`` envelope when the caller has exceeded
    the 60/min rate limit (spec §Input Limits + Error Handling Matrix).
    Pydantic ``ValidationError`` for missing ``"task"`` tag discriminator
    or oversize content propagates so the MCP layer surfaces a 400-class
    response to the caller.
    """
    caller = derive_caller_identity(_ctx_to_auth_context(ctx))

    try:
        limiter = _get_create_limiter()
        limiter.check(caller)
    except RateLimitError as exc:
        # Per spec Error Handling Matrix: rate limit returns a typed
        # envelope, NOT an exception. The MCP wrapper surfaces this dict
        # as the tool result so dashboards / clients can render the
        # retry-after hint without parsing tracebacks.
        return {
            "status": "error",
            "error_code": "rate_limited",
            "message": str(exc),
            "details": {
                "limit": limiter.limit,
                "window_seconds": limiter.window_seconds,
                "caller": caller,
            },
        }

    # Build Task. Pydantic validators enforce the "task" tag discriminator,
    # the tz-aware ``due_at``, the metadata size cap, and the
    # ``parent_task_id`` pattern. ValidationError intentionally propagates
    # (caller bug, not an internal failure).
    now = datetime.now(UTC)
    task = Task(
        id=new_task_id(),
        content=content,
        owner=caller,  # server-set; caller-supplied ``owner`` silently overwritten
        visibility="private",  # default per spec §Authz Model
        priority=priority,
        effort=effort,
        tags=tags,
        parent_task_id=parent_task_id,
        workflow_id=None,
        due_at=due,
        created_at=now,
        updated_at=now,
        created_by=caller,
        completed_at=None,
        completed_by=None,
        result_notes=None,
        metadata=metadata or {},
    )

    # Persist via the canonical reflection store. ``metadata.kind="task"``
    # is the discriminator that downstream ``tasks_list`` uses to scope
    # semantic searches (so an ``akosha`` query for ``task`` rows does
    # not return store_reflection rows written by other tools).
    # ``metadata.task_id`` carries the full 32-hex id so the list/get/
    # update round-trip in T5-T7 can recover the original id (the
    # compact ``uuid_alias`` is display-only per spec §Data Model).
    uuid_alias = task.id[2:14]  # 12-hex compact form for display only
    await store_reflection(
        content=content,
        metadata={
            "kind": "task",
            "owner": task.owner,
            "task_id": task.id,
            "uuid_alias": uuid_alias,
            "priority": priority,
            "effort": effort,
            "due_at": due.isoformat() if due is not None else None,
            "parent_task_id": parent_task_id,
            "workflow_id": None,
            "created_at": now.isoformat(),
        },
        tags=task.tags,
    )

    # Emit ``task.created`` with a typed payload per T2.
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    await publish_task_event(
        "task.created",
        TaskCreatedPayload(
            task_id=task.id,
            owner=task.owner,
            actor=task.owner,
            created_at=now,
            content_hash=content_hash,
        ),
    )

    return task


# ---------------------------------------------------------------------------
# tasks_list — T5
# ---------------------------------------------------------------------------
#
# Spec §Data Flow path 2 + §Authz Model + §Migration. Server-side:
# - ``owner`` filter is forced to ``caller_identity`` (the security-
#   critical invariant from §Authz Model; callers cannot read other
#   users' private tasks).
# - The visibility filter is enforced on every row.
# - ``include_legacy=True`` is the only way to surface legacy
#   ``tags=["todo"]`` rows (default ``False`` per spec §Migration).
# - ``tasks_list`` is read-only — no event emission.

# Status / priority / effort are stored as ``<kind>:<value>`` tag prefixes
# per spec §Data Flow path 1 ("strip priority:/status:/effort: tags"). The
# following Literal values are the only legal coercions.
_TAG_PREFIX_STATUS_VALUES = {"open", "in_progress", "blocked", "done", "cancelled"}
_TAG_PREFIX_PRIORITY_VALUES = {"critical", "high", "normal", "low"}
_TAG_PREFIX_EFFORT_VALUES = {"xs", "s", "m", "l", "xl"}


def _coerce_tag_prefix(tag: str) -> tuple[str | None, str | None]:
    """Parse a ``<kind>:<value>`` tag; return (kind, value) or (None, None).

    Tags without a recognised prefix are returned as ``(None, None)`` so
    callers can fall through to the literal list. Used to derive
    ``status``/``priority``/``effort`` from the legacy tag-prefix storage
    convention.
    """
    if ":" not in tag:
        return None, None
    kind, _, value = tag.partition(":")
    if not kind or not value:
        return None, None
    return kind, value


async def _read_reflection(reflection_id: str) -> dict[str, Any] | None:
    """Read a reflection row by ID; return None for orphans / deletions.

    Thin wrapper around ``ReflectionDatabaseAdapter.get_reflection_by_id``
    so tests can ``patch.object(tasks_tools, "_read_reflection", ...)``
    without standing up the canonical reflection adapter. Callers
    ``await`` this helper; tests that patch the symbol provide an
    ``AsyncMock``.
    """
    from session_buddy.reflection_tools import get_reflection_database

    db = await get_reflection_database()
    return await db.get_reflection_by_id(reflection_id)


def _synthetic_task_id(reflection_id: str) -> str:
    """Return a stable ``t-{32 hex}`` identifier derived from the reflection row.

    The original task ID is only stored compactly as ``uuid_alias`` (12 hex)
    on the sidecar; the full 32-hex form cannot be recovered, so list
    surfaces a deterministic synthetic id. The pattern check still passes.
    """
    digest = hashlib.sha256(reflection_id.encode("utf-8", "surrogatepass")).hexdigest()
    return f"t-{digest[:32]}"


def _parse_iso_optional(value: Any) -> datetime | None:
    """Parse an ISO-8601 string into a tz-aware ``datetime``; return None on missing/garbage."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except TypeError, ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _build_task(
    reflection: dict[str, Any], sidecar_meta: dict[str, Any]
) -> Task | None:
    """Build a :class:`Task` from a reflection row + sidecar metadata.

    Returns ``None`` if the reflection row is missing required fields
    (e.g. no ``id``). Coerces status/priority/effort from ``<kind>:<value>``
    tag prefixes per spec §Data Flow path 1; falls back to sidecar
    metadata, then to type defaults.
    """
    reflection_id = reflection.get("id")
    if not isinstance(reflection_id, str) or not reflection_id:
        return None
    content = reflection.get("content")
    if not isinstance(content, str) or not content:
        return None
    tags_in = list(reflection.get("tags") or [])
    if "task" not in tags_in:
        return None

    status: str = "open"
    priority: str = sidecar_meta.get("priority") or "normal"
    effort: str | None = sidecar_meta.get("effort")
    for tag in tags_in:
        kind, value = _coerce_tag_prefix(tag)
        if kind == "status" and value in _TAG_PREFIX_STATUS_VALUES:
            status = value
        elif kind == "priority" and value in _TAG_PREFIX_PRIORITY_VALUES:
            priority = value
        elif kind == "effort" and value in _TAG_PREFIX_EFFORT_VALUES:
            effort = value

    owner = sidecar_meta.get("owner")
    created_at = _parse_iso_optional(sidecar_meta.get("created_at")) or datetime.now(
        UTC
    )
    due_at = _parse_iso_optional(sidecar_meta.get("due_at"))
    parent_task_id = sidecar_meta.get("parent_task_id")
    workflow_id = sidecar_meta.get("workflow_id")

    # ``task_id`` is the full 32-hex id persisted at create time so the
    # list/get/update round-trip recovers the original id. The synthetic
    # SHA-256 fallback exists only for rows that pre-date the metadata
    # extension (should be zero in practice — kept for defensive
    # correctness so a stray legacy row can't crash ``tasks_list``).
    persisted_task_id = sidecar_meta.get("task_id")
    if isinstance(persisted_task_id, str) and persisted_task_id.startswith("t-"):
        resolved_id: str = persisted_task_id
    else:
        resolved_id = _synthetic_task_id(reflection_id)

    try:
        return Task(
            id=resolved_id,
            content=content,
            owner=str(owner) if owner else None,
            visibility="private",
            status=status,  # ty: ignore[arg-type]
            priority=priority,  # ty: ignore[arg-type]
            effort=effort,  # ty: ignore[arg-type]
            tags=tags_in,
            parent_task_id=str(parent_task_id) if parent_task_id else None,
            workflow_id=str(workflow_id) if workflow_id else None,
            due_at=due_at,
            created_at=created_at,
            updated_at=created_at,
            created_by=str(owner) if owner else None,
            completed_at=None,
            completed_by=None,
            result_notes=None,
            metadata={},
        )
    except ValueError, TypeError:
        return None


def _coerce_legacy_row(reflection: dict[str, Any]) -> LegacyTaskRow | None:
    """Coerce a legacy ``store_reflection(tags=["todo"])`` row.

    Per spec §Migration, the row's ``_coerced=True`` marker is the
    consumer's signal that this is a backwards-compat envelope, not a
    typed ``Task``.
    """
    reflection_id = reflection.get("id")
    content = reflection.get("content")
    if not isinstance(reflection_id, str) or not isinstance(content, str):
        return None
    return LegacyTaskRow(
        id=reflection_id,
        content=content,
        tags=list(reflection.get("tags") or []),
    )


async def _query_legacy_reflections(
    caller: str,
) -> list[tuple[str, dict[str, Any]]]:
    """Return legacy ``tags ⊇ ["todo"]`` reflections eligible for ``include_legacy``.

    Only returns rows whose coerced ``owner`` matches ``caller`` (the
    spec §Migration conservative default leaves unowned rows hidden).
    The actual SQL/IO is delegated to a helper so tests can stub it
    via ``patch.object(tasks_tools, "_query_legacy_reflections", ...)``.
    """
    from session_buddy.reflection_tools import get_reflection_database

    db = await get_reflection_database()
    rows = await db.search_reflections(query="", limit=1000, use_embeddings=False)
    out: list[tuple[str, dict[str, Any]]] = []
    for row in rows or []:
        tags = list(row.get("tags") or [])
        if "todo" not in tags or "task" in tags:
            continue  # exclude typed rows
        reflection = await _read_reflection(row["id"])
        if reflection is None:
            continue
        coerced_owner = reflection.get("project") or reflection.get("created_by")
        if coerced_owner != caller:
            continue
        out.append((row["id"], reflection))
    return out


# Pagination cursor: opaque, base64-urlsafe JSON of ``{"offset": int}``.
def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": int(offset)}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = json.loads(
            base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        )
    except ValueError, KeyError, TypeError:
        return 0
    offset = decoded.get("offset", 0)
    return int(offset) if isinstance(offset, int) and offset >= 0 else 0


def _passes_post_filters(
    task: Task,
    status: str | None,
    tag: str | None,
    parent_task_id: str | None,
) -> bool:
    if status is not None and task.status != status:
        return False
    if tag is not None and tag not in task.tags:
        return False
    return parent_task_id is None or task.parent_task_id == parent_task_id


async def tasks_list(
    ctx: Context,
    status: (
        Literal["open", "in_progress", "blocked", "done", "cancelled"] | None
    ) = None,
    owner: str | None = None,
    tag: str | None = None,
    parent_task_id: Annotated[str | None, Field(pattern=TASK_ID_PATTERN)] = None,
    include_legacy: bool = False,
    k: int = 20,
    cursor: str | None = None,
) -> TaskListResult:
    """List tasks owned by the caller with optional filters and pagination.

    Server-side (spec §Authz Model + §Migration):

    - ``owner`` filter is forced to ``caller_identity``. A caller-supplied
      ``owner`` that doesn't match the caller returns an empty result —
      callers cannot widen past their own privilege to read other users'
      private tasks.
    - ``enforce_visibility_filter(caller, task)`` is applied to every
      candidate row (public rows pass; private/team rows require owner
      match).
    - ``include_legacy=True`` is the only way to surface legacy
      ``tags=["todo"]`` rows (default ``False`` per §Migration).
    """
    caller = derive_caller_identity(_ctx_to_auth_context(ctx))

    # Security boundary: caller cannot filter by another user's owner. The
    # brief pins the empty-result behaviour; the spec is more nuanced
    # (return caller's rows + public ones) but the brief is the binding
    # contract for T5.
    if owner is not None and owner != caller:
        return TaskListResult(items=[], next_cursor=None, total=0)

    metadata_filter: dict[str, Any] = {"kind": "task", "owner": caller}
    candidate_ids = tasks_storage.find_tasks_by_metadata(
        tasks_storage.get_engine(),
        metadata_filter,
        limit=1000,
    )

    typed_items: list[Task] = []
    for rid in candidate_ids:
        reflection = await _read_reflection(rid)
        if reflection is None:
            continue  # orphan sidecar row — skip silently
        sidecar_meta = (
            tasks_storage.read_task_metadata(
                tasks_storage.get_engine(),
                rid,
            )
            or {}
        )
        task = _build_task(reflection, sidecar_meta)
        if task is None:
            continue
        if not enforce_visibility_filter(caller, task):
            continue
        if not _passes_post_filters(task, status, tag, parent_task_id):
            continue
        typed_items.append(task)

    legacy_items: list[LegacyTaskRow] = []
    if include_legacy:
        for rid, reflection in await _query_legacy_reflections(caller):
            row = _coerce_legacy_row(reflection)
            if row is not None:
                legacy_items.append(row)

    # Sort by created_at DESC. Legacy rows lack created_at; sort them last
    # (treated as oldest).
    typed_items.sort(key=lambda t: t.created_at, reverse=True)

    # Apply pagination to the typed list. Legacy rows are appended after
    # pagination since they bypass owner-side filtering at the sidecar
    # level (their visibility is enforced inside ``_query_legacy_reflections``).
    offset = _decode_cursor(cursor)
    page_items: list[Task | LegacyTaskRow]
    page_items = typed_items[offset : offset + k]
    next_cursor = _encode_cursor(offset + k) if offset + k < len(typed_items) else None

    # When ``include_legacy`` is on, append legacy rows after the typed
    # page (they're surfaced as a separate category — the spec marks them
    # with ``_coerced=True`` so consumers render distinctly).
    if include_legacy:
        page_items = list(page_items) + legacy_items

    total_count = len(typed_items) + (len(legacy_items) if include_legacy else 0)
    return TaskListResult(
        items=page_items,
        next_cursor=next_cursor,
        total=total_count,
    )


# ---------------------------------------------------------------------------
# Registration stub
# ---------------------------------------------------------------------------


def register_tasks_tools(mcp: Any) -> None:
    """Register task-system MCP tools. T4 registers ``tasks_create``; T5-T9 add the rest.

    T12 wires this entry point into the FastMCP server. Until then the
    function body is intentionally a no-op so callers can import the
    symbol without side effects.
    """
    return
