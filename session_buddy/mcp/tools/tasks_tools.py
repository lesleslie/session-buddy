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

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from mcp_common.fastmcp import Context
from pydantic import Field

from session_buddy.mcp.tools.tasks_events import (
    TaskCreatedPayload,
    publish_task_event,
)
from session_buddy.mcp.tools.tasks_identity import derive_caller_identity
from session_buddy.mcp.tools.tasks_models import (
    TASK_ID_PATTERN,
    JsonValue,
    Task,
    new_task_id,
)
from session_buddy.mcp.tools.tasks_security import (
    MAX_CONTENT_BYTES,
    MAX_TAG_LEN,
    RateLimiter,
    RateLimitError,
)

# Imported into the module namespace (rather than referenced as
# ``tasks_tools.store_reflection`` from a non-module path) so tests can
# ``patch.object(tasks_tools, "store_reflection", ...)`` and intercept the
# DB call without standing up a real reflection adapter.
from session_buddy.tools.memory_tools import store_reflection

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

    Auth middleware (out of scope for T4) populates
    ``ctx.request_state["auth"]`` with ``{"user_email": ...}`` and / or
    ``{"agent_id": ...}``. This helper bridges the gap so the rest of the
    task system can stay decoupled from FastMCP's request-state shape.
    """
    request_state = getattr(ctx, "request_state", None) or {}
    if not isinstance(request_state, dict):
        request_state = {}
    return {"auth": request_state.get("auth") or {}}


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
    uuid_alias = task.id[2:14]  # 12-hex compact form for display only
    await store_reflection(
        content=content,
        metadata={
            "kind": "task",
            "owner": task.owner,
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
# Registration stub
# ---------------------------------------------------------------------------


def register_tasks_tools(mcp: Any) -> None:
    """Register task-system MCP tools. T4 registers ``tasks_create``; T5-T9 add the rest.

    T12 wires this entry point into the FastMCP server. Until then the
    function body is intentionally a no-op so callers can import the
    symbol without side effects.
    """
    return