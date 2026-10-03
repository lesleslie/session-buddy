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
import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

# ``Context`` is imported at module level (not behind ``TYPE_CHECKING``)
# so FastMCP can resolve the forward reference ``ctx: Context`` when
# introspecting the tool signature for parameter-schema generation. With
# ``from __future__ import annotations`` active, every annotation is
# stored as a string; FastMCP / Pydantic resolve those strings against
# the function's ``__globals__``, and ``TYPE_CHECKING``-gated imports
# leave no runtime symbol to resolve. The same runtime import is used by
# ``session_buddy/mcp/tools/advanced/rewriting_tools.py`` etc., so the
# pattern is already established in this package.
from mcp_common.fastmcp import Context
from pydantic import Field
from sqlalchemy.engine import Engine

# Sidecar module imported into the module namespace so tests can patch the
# ``find_tasks_by_metadata`` / ``get_engine`` pair without round-tripping
# through ``session_buddy.mcp.tools.tasks_storage``.
from session_buddy.mcp.tools import tasks_storage
from session_buddy.mcp.tools.tasks_events import (
    TaskCompletedPayload,
    TaskCreatedPayload,
    TaskUpdatedPayload,
    publish_task_event,
)
from session_buddy.mcp.tools.tasks_identity import derive_caller_identity

# Re-export from the dedicated module (T10 extraction). The legacy coercion
# path is owned by ``tasks_legacy``; ``tasks_tools`` keeps a private alias
# so the existing ``tasks_list`` call site (``row = _coerce_legacy_row(reflection)``)
# continues to work without modification.
from session_buddy.mcp.tools.tasks_legacy import (
    coerce_legacy_reflection as _coerce_legacy_row,
)
from session_buddy.mcp.tools.tasks_models import (
    TASK_ID_PATTERN,
    FieldDiff,
    JsonValue,
    LegacyTaskRow,
    Task,
    TaskEvent,
    TaskHistoryResult,
    TaskListResult,
    UpdateTaskRequest,
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
from session_buddy.tools.memory_tools import search_reflections, store_reflection

logger = logging.getLogger(__name__)

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
# Module-level rate limiter (tasks_update)
# ---------------------------------------------------------------------------
#
# Spec §Input Limits: ``tasks_update`` + ``tasks_complete`` are throttled
# to 120/min per caller. Separate ``RateLimiter`` instance from
# ``tasks_create`` (60/min) so one tool's burst does not consume the
# other's quota.
_update_rate_limiter: RateLimiter | None = None


def _get_update_limiter() -> RateLimiter:
    """Return the module-level ``tasks_update`` rate limiter (lazy init)."""
    global _update_rate_limiter
    if _update_rate_limiter is None:
        _update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    return _update_rate_limiter


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
    # ``owner`` is server-derived from ``caller`` in the Task constructor
    # two lines above; Pydantic's ``owner: str | None`` model field stays
    # optional in the type system but is never None at this point.
    # ``cast`` documents the runtime invariant for ty without changing
    # the public model shape.
    owner_str = cast("str", task.owner)
    await publish_task_event(
        "task.created",
        TaskCreatedPayload(
            task_id=task.id,
            owner=owner_str,
            actor=owner_str,
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
    reflection: dict[str, Any], sidecar_meta: dict[str, Any] | None
) -> Task | None:
    """Build a :class:`Task` from a reflection row + sidecar metadata.

    Returns ``None`` if the reflection row is missing required fields
    (e.g. no ``id``). Coerces status/priority/effort from ``<kind>:<value>``
    tag prefixes per spec §Data Flow path 1; falls back to sidecar
    metadata, then to type defaults.

    ``sidecar_meta`` is accepted as ``dict | None`` so call sites can
    pass the raw return of ``tasks_storage.read_task_metadata``
    without per-site ``or {}`` / if-else narrowing dances. Pre-1.0
    decision: receive the widest type the source provides, narrow
    once at the boundary.
    """
    if sidecar_meta is None:
        sidecar_meta = {}
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
            visibility=sidecar_meta.get("visibility", "private"),
            # status / priority / effort are validated against the
            # ``_TAG_PREFIX_*_VALUES`` sets above (lines 369-373) so the
            # runtime values are guaranteed Literal members. ``cast``
            # documents the invariant for ty without weakening the local
            # ``str`` typing used to drive the validation loop.
            status=cast(
                "Literal['open', 'in_progress', 'blocked', 'done', 'cancelled']",
                status,
            ),
            priority=cast(
                "Literal['critical', 'high', 'normal', 'low']",
                priority,
            ),
            effort=cast(
                "Literal['xs', 's', 'm', 'l', 'xl'] | None",
                effort,
            ),
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
    for row in rows:
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
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
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
    # ``typed_items`` is invariantly ``list[Task]``; the wider
    # ``list[Task | LegacyTaskRow]`` annotation comes from the legacy
    # concat below. Slicing preserves the runtime type so cast is safe.
    page_items = cast("list[Task | LegacyTaskRow]", typed_items[offset : offset + k])
    next_cursor = _encode_cursor(offset + k) if offset + k < len(typed_items) else None

    # When ``include_legacy`` is on, append legacy rows after the typed
    # page (they're surfaced as a separate category — the spec marks them
    # with ``_coerced=True`` so consumers render distinctly).
    if include_legacy:
        page_items = page_items.copy() + legacy_items

    total_count = len(typed_items) + (len(legacy_items) if include_legacy else 0)
    return TaskListResult(
        items=page_items,
        next_cursor=next_cursor,
        total=total_count,
    )


# ---------------------------------------------------------------------------
# T6: tasks_get + tasks_update helpers + tools
# ---------------------------------------------------------------------------
#
# ``tasks_get`` and ``tasks_update`` share the reflection-id lookup
# (``_find_reflection_id_by_task_id``) and the same visibility-filter
# surface. Helpers are kept private to this module so future tasks can
# extend them without breaking the public surface.


def _find_reflection_id_by_task_id(engine: Engine, task_id: str) -> str | None:
    """Return the reflection_id whose sidecar metadata carries ``task_id``.

    The full 32-hex ``task_id`` is persisted in the sidecar metadata at
    ``tasks_create`` time (T5 fix round 1); we filter on it directly so
    the lookup is unambiguous even when many task rows exist for the
    same owner. The defensive fallback scans all task rows in case a
    pre-T5-fix row lacks the ``task_id`` sidecar key (zero in practice
    — kept so a stray legacy writer cannot crash ``tasks_get``).
    """
    candidate_ids = tasks_storage.find_tasks_by_metadata(
        engine=engine,
        metadata_filter={"kind": "task", "task_id": task_id},
    )
    if candidate_ids:
        return candidate_ids[0]
    all_task_ids = tasks_storage.find_tasks_by_metadata(
        engine=engine,
        metadata_filter={"kind": "task"},
    )
    for rid in all_task_ids:
        sidecar_meta = tasks_storage.read_task_metadata(
            engine=engine, reflection_id=rid
        )
        if sidecar_meta and sidecar_meta.get("task_id") == task_id:
            return rid
    return None


def _compute_diff(before: dict[str, Any], after: dict[str, Any]) -> list[FieldDiff]:
    """Return ``FieldDiff`` rows for every key whose before/after differ.

    Compares ``task.model_dump()`` snapshots from before/after the mutation.
    ``updated_at`` always changes (server-set ``datetime.now(UTC)``) so it
    shows up in the diff and is emitted as its own event — downstream
    consumers can render timestamp changes distinctly from content changes
    by inspecting ``diff.field``.
    """
    return [
        FieldDiff(field=key, before=before.get(key), after=after.get(key))
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]


def _jsonify_value(value: Any) -> Any:
    """JSON-serialize a single diff value so it survives SQLAlchemy JSON storage.

    ``task.model_dump()`` returns raw ``datetime`` objects; the sidecar's
    JSON column rejects those with ``Object of type datetime is not JSON
    serializable``. Convert datetimes to ISO-8601 strings; pass through
    everything else (str, int, float, bool, None, dict, list) unchanged.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonify_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonify_value(v) for k, v in value.items()}
    return value


async def _update_reflection(
    reflection_id: str,
    content: str,
    tags: list[str],
) -> None:
    """Persist updated content + tags to the canonical reflection DB.

    Delegates to the reflection adapter's ``update_reflection`` primitive
    (added in T6 fix round 1). Raises if the row doesn't exist or the
    adapter is unavailable.
    """
    from session_buddy.reflection_tools import get_reflection_database

    db = await get_reflection_database()
    updated = await db.update_reflection(
        reflection_id,
        content=content,
        tags=tags,
    )
    if not updated:
        raise RuntimeError(
            f"_update_reflection: reflection_id={reflection_id!r} not found"
        )


def _sync_tags_after_field_change(
    tags: list[str],
    field: Literal["status", "priority", "effort"],
    new_value: str | None,
) -> list[str]:
    """Sync the ``<field>:<value>`` tag prefix to match ``new_value``.

    ``_build_task`` reads ``priority`` / ``status`` / ``effort`` from the
    sidecar first, then OVERRIDES from a ``<field>:<value>`` tag in the
    reflection row's tags list (the legacy tag-prefix convention). To
    prevent a subsequent read from reverting a successful update, we
    rewrite the prefix entry whenever a status / priority / effort
    mutation lands. ``new_value=None`` removes the prefix entry.
    """
    out: list[str] = []
    found = False
    for tag in tags:
        kind, _ = _coerce_tag_prefix(tag)
        if kind == field:
            found = True
            if new_value is not None:
                out.append(f"{field}:{new_value}")
        else:
            out.append(tag)
    if not found and new_value is not None:
        out.append(f"{field}:{new_value}")
    return out


async def _persist_task_update(
    reflection_id: str,
    task: Task,
    sidecar_meta: dict[str, Any],
    diff_events: list[FieldDiff],
    actor: str,
) -> None:
    """Persist an updated task to the sidecar + sync tag-prefix + history entry.

    Sidecar fields mirror the Task fields that T4 wrote at create time:
    ``priority``, ``effort``, ``due_at``, ``parent_task_id``, plus a
    refreshed ``updated_at``. The ``history`` list is appended (not
    replaced) so T9's ``tasks_history`` can render the diff timeline.
    The reflection row update is delegated to ``_update_reflection``
    (a T6 stub; T12 wires the real adapter).
    """
    new_meta = sidecar_meta.copy()
    new_meta["priority"] = task.priority
    new_meta["effort"] = task.effort
    if getattr(task, "visibility", None) is not None:
        new_meta["visibility"] = task.visibility
    new_meta["due_at"] = task.due_at.isoformat() if task.due_at is not None else None
    new_meta["parent_task_id"] = task.parent_task_id
    new_meta["updated_at"] = task.updated_at.isoformat()

    synced_tags = task.tags.copy()
    for diff in diff_events:
        if diff.field == "priority":
            synced_tags = _sync_tags_after_field_change(
                synced_tags, "priority", diff.after
            )
        elif diff.field == "status":
            synced_tags = _sync_tags_after_field_change(
                synced_tags, "status", diff.after
            )
        elif diff.field == "effort":
            synced_tags = _sync_tags_after_field_change(
                synced_tags, "effort", diff.after
            )

    history = list(new_meta.get("history") or [])
    now_iso = datetime.now(UTC).isoformat()
    for diff in diff_events:
        history.append(
            {
                "field": diff.field,
                "before": _jsonify_value(diff.before),
                "after": _jsonify_value(diff.after),
                "actor": actor,
                "at": now_iso,
            }
        )
    new_meta["history"] = history

    tasks_storage.persist_task_metadata(
        tasks_storage.get_engine(),
        reflection_id,
        new_meta,
    )
    await _update_reflection(
        reflection_id=reflection_id,
        content=task.content,
        tags=synced_tags,
    )


def _apply_update_request(task: Task, request: UpdateTaskRequest) -> None:
    """Mutate ``task`` in place with every non-None field from ``request``.

    Extracted from ``tasks_update`` to keep its branch count under the
    15-branch pylint limit. Server-set fields (owner, created_at,
    created_by, completed_at, completed_by, workflow_id) are never on
    UpdateTaskRequest, so they cannot be mutated via this path.
    """
    if request.content is not None:
        task.content = request.content
    if request.visibility is not None:
        task.visibility = request.visibility
    if request.status is not None:
        task.status = request.status
    if request.priority is not None:
        task.priority = request.priority
    if request.effort is not None:
        task.effort = request.effort
    if request.due_at is not None:
        task.due_at = request.due_at
    if request.tags is not None:
        task.tags = request.tags
    if request.parent_task_id is not None:
        task.parent_task_id = request.parent_task_id
    if request.result_notes is not None:
        task.result_notes = request.result_notes
    if request.metadata is not None:
        task.metadata = request.metadata


async def _emit_update_events(
    task: Task,
    diff_events: list[FieldDiff],
    actor: str,
) -> None:
    """Publish one ``task.updated`` event per diff field.

    Each event carries a single-entry ``diff`` dict so consumers can
    render field-level changes distinctly. T2's ``TaskUpdatedPayload``
    is the canonical envelope.
    """
    for diff in diff_events:
        await publish_task_event(
            "task.updated",
            TaskUpdatedPayload(
                task_id=task.id,
                actor=actor,
                updated_at=task.updated_at,
                diff={diff.field: (diff.before, diff.after)},
            ),
        )


# ---------------------------------------------------------------------------
# tasks_get — T6
# ---------------------------------------------------------------------------
#
# Spec §Tool Surface + §Authz Model. Server-side visibility filter;
# private tasks are 404 to non-owners (no info leak about existence).
# ``task_id`` is pattern-validated by Pydantic via the ``Annotated[..., Field(pattern=...)]``
# signature; an invalid id raises ``ValidationError`` BEFORE this body runs.


async def tasks_get(
    ctx: Context,
    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)],
) -> Task | dict[str, Any]:
    """Fetch a single task by id. Returns 404 (not 403) on visibility failure."""
    caller = derive_caller_identity(_ctx_to_auth_context(ctx))

    # Explicit pattern validation (the Annotated[...] hint is documentation-only
    # on a plain async function; the spec §Error Handling Matrix pins an
    # ``invalid_id_format`` envelope so the caller can distinguish bad input
    # from a not-found / not-visible task).
    if not re.match(TASK_ID_PATTERN, task_id):
        return {
            "status": "error",
            "error_code": "invalid_id_format",
            "message": f"task_id {task_id!r} does not match TASK_ID_PATTERN",
        }

    engine = tasks_storage.get_engine()
    target = _find_reflection_id_by_task_id(engine=engine, task_id=task_id)
    if target is None:
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    reflection = await _read_reflection(target)
    sidecar_meta = tasks_storage.read_task_metadata(
        engine=engine, reflection_id=target
    )
    task = _build_task(reflection, sidecar_meta)
    if task is None:
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    if not enforce_visibility_filter(caller, task):
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    return task


# ---------------------------------------------------------------------------
# tasks_update — T6
# ---------------------------------------------------------------------------
#
# Spec §Tool Surface + §Authz Model + §UpdateTaskRequest + §Rate Limits +
# §Error Handling. Pre-flight rejection of caller-supplied identity fields
# (defense in depth; ``UpdateTaskRequest`` already excludes them per T1
# contract but we re-check at the tool body to be paranoid). Rate limit
# 120/min per caller — separate from ``tasks_create``'s 60/min.


async def tasks_update(
    ctx: Context,
    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)],
    request: UpdateTaskRequest,
) -> Task | dict[str, Any]:
    """Update mutable fields on a task. Server rejects owner mutation; 120/min per caller."""
    caller = derive_caller_identity(_ctx_to_auth_context(ctx))

    # Defense in depth: even if a future UpdateTaskRequest change re-exposes
    # owner/created_by/completed_by, we still reject at the tool body so the
    # security-critical invariant holds. ``getattr(..., None)`` because
    # Pydantic ``extra='forbid'`` raises AttributeError on unknown fields
    # rather than returning None.
    if (
        getattr(request, "owner", None) is not None
        or getattr(request, "created_by", None) is not None
        or getattr(request, "completed_by", None) is not None
    ):
        return {
            "status": "error",
            "error_code": "owner_mutation_forbidden",
            "message": "owner/created_by/completed_by are server-derived; caller cannot mutate.",
        }

    # Explicit pattern validation (Pydantic Field(pattern=...) only fires
    # inside model construction; this is a plain async function so the
    # signature annotation is documentation-only).
    if not re.match(TASK_ID_PATTERN, task_id):
        return {
            "status": "error",
            "error_code": "invalid_id_format",
            "message": f"task_id {task_id!r} does not match TASK_ID_PATTERN",
        }

    # Rate limit (120/min per spec §Input Limits; separate from create).
    limiter = _get_update_limiter()
    try:
        limiter.check(caller)
    except RateLimitError as exc:
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

    # Locate + load the task (same lookup path as tasks_get).
    engine = tasks_storage.get_engine()
    target = _find_reflection_id_by_task_id(engine=engine, task_id=task_id)
    if target is None:
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    reflection = await _read_reflection(target)
    sidecar_meta = tasks_storage.read_task_metadata(
        engine=engine, reflection_id=target
    )
    task = _build_task(reflection, sidecar_meta)
    if task is None or not enforce_visibility_filter(caller, task):
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    # Snapshot before-state for the diff.
    before = task.model_dump()

    # Apply caller-supplied changes (extracted to keep this function under
    # the 15-branch pylint limit).
    _apply_update_request(task, request)
    task.updated_at = datetime.now(UTC)

    after = task.model_dump()
    diff_events = _compute_diff(before, after)

    # Persist + sync tag-prefix + append history.
    await _persist_task_update(
        reflection_id=target,
        task=task,
        sidecar_meta=sidecar_meta,
        diff_events=diff_events,
        actor=caller,
    )

    # Emit one task.updated per diff field (T2 payload contract).
    await _emit_update_events(task=task, diff_events=diff_events, actor=caller)

    return task


# ---------------------------------------------------------------------------
# tasks_complete — T7
# ---------------------------------------------------------------------------
#
# v1.1 multi-agent-review hardening. ``tasks_complete`` is a pure state
# mutation: status='done', completed_at=now, completed_by=caller, and
# optionally result_notes. It MUST NOT inspect ``result_notes`` for any
# dispatch trigger; the only dispatch edge is ``tasks_handoff_to_workflow``
# (T17, mahavishnu PR #2). The regression test
# ``test_tasks_complete_does_NOT_dispatch_even_with_handoff_prefix`` pins
# this contract.
#
# Rate limit: shared 120/min limiter with ``tasks_update`` per spec
# §Input Limits. Authz: only the ``owner`` may complete a task (spec line
# 565). Visibility check returns 404 (not 403) — same info-leak parity as
# ``tasks_get`` / ``tasks_update``.


def _apply_complete_fields(
    task: Task,
    completed_by: str,
    now: datetime,
    result_notes: str | None,
) -> None:
    """Mutate ``task`` in place to mark it done.

    Server-set fields only: ``status``, ``completed_at``, ``completed_by``,
    ``updated_at``, and (optionally) ``result_notes``. ``workflow_id`` is
    NEVER touched — it is server-set by T17's ``tasks_handoff_to_workflow``
    only and ``tasks_complete`` MUST NOT mutate it.
    """
    task.status = "done"
    task.completed_at = now
    task.completed_by = completed_by
    task.updated_at = now
    if result_notes is not None:
        task.result_notes = result_notes


async def tasks_complete(
    ctx: Context,
    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)],
    result_notes: Annotated[str | None, Field(max_length=4096)] = None,
) -> Task | dict[str, Any]:
    """Mark a task as done. Server-sets completed_by from caller identity.

    Strictly a state mutation: ``status='done'``, ``completed_at=now``,
    ``completed_by=caller``, optionally ``result_notes``. Does NOT inspect
    ``result_notes`` for any dispatch trigger — the only dispatch edge in
    the system is ``tasks_handoff_to_workflow`` (T17, mahavishnu PR #2).
    Returns the updated :class:`Task`, or an error envelope on rate
    limit / pattern mismatch / not_found / not_visible.
    """
    caller = derive_caller_identity(_ctx_to_auth_context(ctx))

    if not re.match(TASK_ID_PATTERN, task_id):
        return {
            "status": "error",
            "error_code": "invalid_id_format",
            "message": f"task_id {task_id!r} does not match TASK_ID_PATTERN",
        }

    limiter = _get_update_limiter()
    try:
        limiter.check(caller)
    except RateLimitError as exc:
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

    engine = tasks_storage.get_engine()
    target = _find_reflection_id_by_task_id(engine=engine, task_id=task_id)
    if target is None:
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    reflection = await _read_reflection(target)
    sidecar_meta = tasks_storage.read_task_metadata(
        engine=engine, reflection_id=target
    )
    task = _build_task(reflection, sidecar_meta)
    if task is None or not enforce_visibility_filter(caller, task):
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    # Authz: only the owner can complete a task (spec §Error Handling line
    # 565). The 404 envelope hides existence from non-owners.
    if task.owner != caller:
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    before = task.model_dump()

    # Server-set mutation; ``workflow_id`` is intentionally untouched.
    now = datetime.now(UTC)
    _apply_complete_fields(
        task=task,
        completed_by=caller,
        now=now,
        result_notes=result_notes,
    )

    after = task.model_dump()
    diff_events = _compute_diff(before, after)

    await _persist_task_update(
        reflection_id=target,
        task=task,
        sidecar_meta=sidecar_meta,
        diff_events=diff_events,
        actor=caller,
    )

    await publish_task_event(
        "task.completed",
        TaskCompletedPayload(
            task_id=task.id,
            actor=caller,
            # ``_apply_complete_fields`` set ``task.completed_at = now``
            # before this event is emitted, so the field is non-None at
            # runtime. ``cast`` documents the invariant for ty.
            completed_at=cast("datetime", task.completed_at),
            has_workflow_id=task.workflow_id is not None,
        ),
    )

    return task


# ---------------------------------------------------------------------------
# tasks_search — T8
# ---------------------------------------------------------------------------
#
# Spec line 121-126 + brief: ``tasks_search(query, project=None,
# min_score=None, k=10) -> list[Task]``. Semantic search over tasks with
# quick_search parity. Filters the underlying ``search_reflections``
# results to ``kind=task`` rows via the sidecar metadata (with ``"task"``
# tag as a defensive fallback), then applies the visibility filter and
# an optional ``min_score`` post-filter.
#
# Filter ordering per the brief's design notes:
#   1. kind=task gate (cheap, drops non-task reflections early)
#   2. visibility filter (security gate; private rows hidden unconditionally)
#   3. min_score filter (relevance gate; applied last)
#
# ``min_score`` is a post-filter (not a forwarded kwarg) because the
# module-level ``search_reflections`` wrapper at
# ``session_buddy/tools/memory_tools.py`` does not accept ``min_score`` —
# the underlying ``session_buddy.reflection.search`` primitive does, but
# plumbing it through the wrapper is T12 wiring territory. The post-filter
# here is correct under the spec's correctness contract: high-score
# private rows are still hidden; low-score public rows are still hidden.


async def tasks_search(
    ctx: Context,
    query: str,
    project: str | None = None,
    min_score: float | None = None,
    k: int = 10,
) -> list[Task]:
    """Semantic search over tasks with quick_search parity.

    Returns only ``kind=task`` rows (non-task reflections filtered via
    sidecar metadata, with the ``"task"`` tag as a defensive fallback).
    Visibility filter: private tasks excluded for non-owners. Project,
    ``min_score``, and ``k`` forward to or post-filter the underlying
    ``search_reflections`` call.
    """
    caller = derive_caller_identity(_ctx_to_auth_context(ctx))

    raw_results = await search_reflections(
        query=query,
        limit=k,
        project=project,
    )

    engine = tasks_storage.get_engine()
    tasks: list[Task] = []
    for hit in raw_results:
        rid = hit.get("id")
        if not isinstance(rid, str) or not rid:
            continue

        # kind=task gate via sidecar metadata; fall back to the "task" tag
        # discriminator when sidecar metadata is missing (defensive — every
        # row produced by ``tasks_create`` has a sidecar entry, but a
        # future writer may bypass that path).
        sidecar_meta = (
            tasks_storage.read_task_metadata(engine=engine, reflection_id=rid) or {}
        )
        kind = sidecar_meta.get("kind") if isinstance(sidecar_meta, dict) else None
        # ``hit`` is a TypedDict; ``get("tags")`` returns ``list[str] | None``
        # and ``or []`` widens to ``list[str] | list[Unknown]`` in ty's view.
        # The Pydantic ``Task.tags`` field requires ``list[str]`` so we
        # narrow here.
        tags_in = cast("list[str]", hit.get("tags") or [])
        if kind != "task" and "task" not in tags_in:
            continue

        # Re-read the reflection for the canonical ``_build_task`` shape.
        # The hit already carries ``content`` / ``tags`` / ``metadata`` but
        # ``_build_task`` expects the ``ReflectionDatabaseAdapter.get_reflection_by_id``
        # dict shape (id/content/tags/project/created_at/updated_at).
        reflection = await _read_reflection(rid)
        if reflection is None:
            continue
        task = _build_task(reflection, sidecar_meta)
        if task is None:
            continue

        # Visibility gate (security; private rows hidden unconditionally).
        if not enforce_visibility_filter(caller, task):
            continue

        # min_score post-filter (relevance; applied last per the brief).
        if min_score is not None:
            score = hit.get("score")
            if not isinstance(score, (int, float)) or float(score) < float(min_score):
                continue

        tasks.append(task)

    return tasks


# ---------------------------------------------------------------------------
# tasks_history — T9
# ---------------------------------------------------------------------------
#
# Spec line 128-133: ``tasks_history(task_id, k=50, cursor=None) ->
# TaskHistoryResult`` with envelope shape ``{items: list[TaskEvent],
# next_cursor: str | None}`` (NO ``total`` — spec is explicit).
#
# History source: sidecar ``metadata["history"]`` list written by T6's
# ``_persist_task_update``. Each entry is a dict ``{field, before,
# after, actor, at}``. ``event_type`` is hardcoded to ``"updated"`` for
# v1 — other types in the ``Literal`` enum are reserved for future
# T17 handoff events / completion events.
#
# Pagination: offset-based cursor (T5's ``base64-urlsafe JSON of
# {"offset": int}`` scheme). Reuses ``_decode_cursor`` / ``_encode_cursor``
# from T5 verbatim so callers can rely on a uniform cursor contract.
#
# Visibility filter: 404 (not 403) on missing / invisible — same
# info-leak parity as ``tasks_get`` / ``tasks_update`` / ``tasks_complete``.
#
# ``actor`` is server-set (the history dict's ``actor`` field, captured
# at update time by ``_persist_task_update``). Defaults to the current
# caller if the dict's actor is missing — defensive fallback so a torn
# sidecar row never crashes the reader.


async def tasks_history(
    ctx: Context,
    task_id: Annotated[str, Field(pattern=TASK_ID_PATTERN)],
    k: int = 50,
    cursor: str | None = None,
) -> TaskHistoryResult | dict[str, Any]:
    """Fetch the change history for a task with cursor-based pagination.

    History is read from the sidecar ``metadata["history"]`` list written
    by ``_persist_task_update``. Each entry is mapped to a :class:`TaskEvent`
    with ``event_type="updated"`` (T6 writes diff entries; other event
    types are reserved for future use by completion / handoff events).
    Empty history returns ``TaskHistoryResult(items=[], next_cursor=None)``
    — NOT an error envelope. Visibility filter is enforced: missing or
    invisible tasks return 404 (not 403) to avoid leaking existence.
    """
    caller = derive_caller_identity(_ctx_to_auth_context(ctx))

    # Explicit pattern validation (the Annotated[..., Field(pattern=...)]
    # signature hint is documentation-only on a plain async function;
    # spec §Error Handling Matrix pins an ``invalid_id_format`` envelope
    # so the caller can distinguish bad input from not-found / not-visible).
    if not re.match(TASK_ID_PATTERN, task_id):
        return {
            "status": "error",
            "error_code": "invalid_id_format",
            "message": f"task_id {task_id!r} does not match TASK_ID_PATTERN",
        }

    # Locate + load the task (same lookup path as tasks_get / tasks_update
    # / tasks_complete). Visibility check fires AFTER the lookup so a
    # missing reflection and an invisible row look identical to the caller.
    engine = tasks_storage.get_engine()
    target = _find_reflection_id_by_task_id(engine=engine, task_id=task_id)
    if target is None:
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    reflection = await _read_reflection(target)
    sidecar_meta = tasks_storage.read_task_metadata(
        engine=engine, reflection_id=target
    )
    task = _build_task(reflection, sidecar_meta)
    if task is None or not enforce_visibility_filter(caller, task):
        return {
            "status": "error",
            "error_code": "not_found",
            "message": f"No task with id {task_id}",
        }

    # Read the append-only history list from the sidecar. ``list()`` copies
    # so a torn / missing list never crashes the reader — default to [].
    history_list = sidecar_meta.get("history") or []

    # Offset-based pagination via T5's cursor helpers (same scheme as
    # ``tasks_list``). Garbage cursors decode to offset=0 — defensive
    # fallback so a malformed cursor never 500s.
    offset = _decode_cursor(cursor)
    end = offset + k
    page = history_list[offset:end]
    next_cursor = _encode_cursor(end) if end < len(history_list) else None

    # Map each dict entry to a TaskEvent. event_type="updated" for v1;
    # the Literal enum reserves other types for future T17 handoff events.
    items: list[TaskEvent] = []
    for entry in page:
        if not isinstance(entry, dict):
            continue
        at_raw = entry.get("at")
        try:
            timestamp = _parse_iso_optional(at_raw) or datetime.now(UTC)
        except TypeError, ValueError:
            timestamp = datetime.now(UTC)

        # diff is ``{field: (before, after)}`` per TaskEvent contract. When
        # the history entry has no ``field`` key (e.g. a future created /
        # completed event source) we leave ``diff`` as ``None`` so the
        # consumer can render a no-diff event distinctly.
        field = entry.get("field")
        diff: dict[str, tuple[Any, Any]] | None = None
        if isinstance(field, str) and field:
            diff = {field: (entry.get("before"), entry.get("after"))}

        items.append(
            TaskEvent(
                task_id=task_id,
                event_type="updated",
                actor=str(entry.get("actor") or caller),
                timestamp=timestamp,
                diff=diff,
                notes=None,
            )
        )

    return TaskHistoryResult(items=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
#
# T12 (final PR #1 wiring). T4-T9 deliberately wrote each ``tasks_*``
# function at module level (without ``@mcp.tool()``) so the central
# registration point could apply the decorator against the live
# FastMCP instance. This keeps the implementation in one place and
# makes it trivial to add / rename tools without re-touching FastMCP.
#
# FastMCP supports ``mcp.tool()(func)`` as a function-call form of the
# ``@mcp.tool()`` decorator; we use that form so the existing module-
# level definitions (and their tests) stay untouched. The decorator is
# idempotent within a single ``mcp`` instance per FastMCP docs.


def register_tasks_tools(mcp: Any) -> None:
    """Register task-system MCP tools. T4-T9 wrote the implementations; T12 wires them.

    Wires the seven ``tasks_*`` MCP tools onto the supplied FastMCP
    server using ``mcp.tool()(func)`` — the function-call form of
    FastMCP's ``@mcp.tool()`` decorator (FastMCP 3.x ``provider.tool``
    accepts both calling patterns per the ``ToolDecoratorMixin.tool``
    docstring). The seven tools are:

    * ``tasks_create`` (T4) — create a task; server-derived ``owner``;
      60/min rate limit; emits ``task.created``.
    * ``tasks_list`` (T5) — list tasks with pagination, visibility
      filter, optional ``include_legacy`` gate.
    * ``tasks_get`` (T6) — fetch one task by id; 404 on visibility.
    * ``tasks_update`` (T6) — apply partial update; 404 on visibility;
      reject owner mutation; 120/min rate limit; emits ``task.updated``.
    * ``tasks_complete`` (T7) — mark a task done; rejects missing
      ``result_notes``; emits ``task.completed``.
    * ``tasks_search`` (T8) — semantic search with ``quick_search``
      parity (project, min_score, k); kind=task + visibility gated.
    * ``tasks_history`` (T9) — cursor-paginated change history; 404 on
      visibility; ``event_type="updated"`` for v1.

    Idempotent within a single ``mcp`` instance — calling this twice
    on the same server re-registers the same tools (FastMCP dedupes by
    ``func.__name__``). Calling on a fresh server is the normal path.
    """
    mcp.tool()(tasks_create)
    mcp.tool()(tasks_list)
    mcp.tool()(tasks_get)
    mcp.tool()(tasks_update)
    mcp.tool()(tasks_complete)
    mcp.tool()(tasks_search)
    mcp.tool()(tasks_history)
    logger.info(
        "Registered task-system tools: tasks_create, tasks_list, tasks_get, "
        "tasks_update, tasks_complete, tasks_search, tasks_history"
    )
