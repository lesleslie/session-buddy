"""Natural-language scheduling MCP tools.

Wraps :class:`session_buddy.natural_scheduler.ReminderScheduler` and
the :class:`NaturalLanguageParser` as MCP tools for create / list /
cancel reminders plus natural-language time parsing.

Closes the gap identified in
``docs/feature-tracking/TOOL_REGISTRATION_GAPS.md`` (2026-09-09).
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from session_buddy.utils.error_management import _get_logger
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from mcp_common.fastmcp import FastMCP

    from session_buddy.natural_scheduler import ReminderScheduler
    from session_buddy.utils.scheduler import NaturalLanguageParser


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------
#
# ReminderScheduler initializes a SQLite database on construction. The
# default location is ``~/.claude/data/natural_scheduler.db``. For
# tests we honor ``SESSION_BUDDY_NATURAL_SCHEDULER_DB`` to point at a
# temporary file; production code uses the default location so existing
# reminders carry over.
# ---------------------------------------------------------------------------


def _scheduler_db_path() -> str:
    """Return the DB path honoring the override env var, else the default."""
    override = os.environ.get("SESSION_BUDDY_NATURAL_SCHEDULER_DB")
    if override:
        return override
    return str(Path.home() / ".claude" / "data" / "natural_scheduler.db")


def _build_scheduler() -> ReminderScheduler:
    from session_buddy.natural_scheduler import ReminderScheduler

    return ReminderScheduler(db_path=_scheduler_db_path())


def _build_parser() -> NaturalLanguageParser:
    from session_buddy.utils.scheduler import NaturalLanguageParser

    return NaturalLanguageParser()


_scheduler: ReminderScheduler | None = None
_scheduler_lock = asyncio.Lock()
_parser: NaturalLanguageParser | None = None


def _set_scheduler_for_testing(scheduler: ReminderScheduler | None) -> None:
    """Inject a scheduler for tests. ``None`` resets the cache and lock."""
    global _scheduler, _scheduler_lock
    _scheduler = scheduler
    if scheduler is None:
        # Reset the lock so a stale acquired-lock from an interrupted
        # concurrent get cannot deadlock the next call.
        _scheduler_lock = asyncio.Lock()


def _set_parser_for_testing(parser: NaturalLanguageParser | None) -> None:
    """Inject a parser for tests. ``None`` resets the cache."""
    global _parser
    _parser = parser


async def _get_scheduler() -> ReminderScheduler:
    """Return the cached scheduler, building one on first use.

    Uses asyncio.Lock with double-checked locking so two concurrent
    MCP tool calls landing before either has warmed the singleton both
    see the same ReminderScheduler (and thus the same SQLite
    connection), avoiding two-client WAL contention. ``_build_scheduler``
    is sync I/O, but it is fast in practice (<10ms for the schema
    CREATE TABLE/INDEX pair on a warm filesystem); we keep it inside
    the critical section rather than punting to ``run_in_executor`` to
    avoid scheduling overhead for what is effectively a one-shot init.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    async with _scheduler_lock:
        if _scheduler is None:
            _scheduler = _build_scheduler()
    return _scheduler


def _get_parser() -> NaturalLanguageParser:
    global _parser
    if _parser is None:
        _parser = _build_parser()
    return _parser


# ---------------------------------------------------------------------------
# Input length bounds — enforce at the MCP boundary so we never store
# unbounded text. These are deliberately tight; callers needing more
# can split their payload.
# ---------------------------------------------------------------------------


MAX_TITLE_CHARS = 200
MAX_TIME_EXPR_CHARS = 200
MAX_DESCRIPTION_CHARS = 1000
MAX_USER_ID_CHARS = 100
MAX_PROJECT_ID_CHARS = 100
MAX_REMINDER_ID_CHARS = 100
MAX_TRIGGER_ITEMS = 50
MAX_TRIGGER_ITEM_CHARS = 100


def _check_len(value: str, *, max_len: int, field_name: str) -> str | None:
    """Return an error envelope if ``value`` exceeds ``max_len``."""
    if len(value) > max_len:
        return (
            f"❌ {field_name} exceeds maximum length of {max_len} chars "
            f"(got {len(value)})"
        )
    return None


def _check_list_len(
    values: list[str], *, max_items: int, max_chars: int, field_name: str
) -> str | None:
    """Return an error envelope if a list exceeds size or any item exceeds chars."""
    if len(values) > max_items:
        return f"❌ {field_name} exceeds maximum {max_items} items (got {len(values)})"
    for i, v in enumerate(values):
        if len(v) > max_chars:
            return (
                f"❌ {field_name}[{i}] exceeds maximum {max_chars} chars (got {len(v)})"
            )
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dump_json(value: Any) -> str:
    """Serialize a model/dataclass/dict to JSON."""
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json()
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), default=str)
    return json.dumps(value, default=str)


async def _run(operation_name: str, operation: Any) -> str:
    """Run an async operation with the standard error envelope."""
    try:
        return await operation()
    except Exception as exc:  # noqa: BLE001 - MCP tool envelope must return a structured error string on any backend/runtime failure (sqlite, etc.)
        _get_logger().exception(f"Error in {operation_name}: {exc}")
        return ToolMessages.operation_failed(operation_name, exc)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register_natural_scheduling_tools(mcp: FastMCP) -> None:
    """Register natural-language scheduling MCP tools.

    Wraps :class:`ReminderScheduler` to expose reminder create / list /
    cancel operations and the natural-language time parser over MCP.

    The scheduler is built lazily on first tool invocation so that
    registration at startup never touches the SQLite database. Tests
    can inject a scheduler via :func:`_set_scheduler_for_testing`.
    """

    @mcp.tool()
    async def create_reminder(
        title: str,
        time_expression: str,
        description: str = "",
        user_id: str = "default",
        project_id: str | None = None,
        context_triggers: list[str] | None = None,
    ) -> str:
        """Create a new reminder from a natural-language description.

        Args:
            title: Short reminder title (used as the action payload).
            time_expression: Natural-language time expression, e.g.
                ``"in 30 minutes"``, ``"tomorrow at 9am"``,
                ``"every day at noon"``.
            description: Optional longer description.
            user_id: Owning user id (default ``"default"``).
            project_id: Optional project to scope the reminder.
            context_triggers: Optional list of trigger tokens to fire
                the reminder when context matches.

        Returns:
            JSON string with the created ``NaturalReminder`` record, or
            an error envelope if ``time_expression`` could not be
            parsed.
        """
        err = _check_len(title, max_len=MAX_TITLE_CHARS, field_name="title")
        if err:
            return err
        err = _check_len(
            time_expression,
            max_len=MAX_TIME_EXPR_CHARS,
            field_name="time_expression",
        )
        if err:
            return err
        err = _check_len(
            description,
            max_len=MAX_DESCRIPTION_CHARS,
            field_name="description",
        )
        if err:
            return err
        err = _check_len(
            user_id,
            max_len=MAX_USER_ID_CHARS,
            field_name="user_id",
        )
        if err:
            return err
        if project_id is not None:
            err = _check_len(
                project_id,
                max_len=MAX_PROJECT_ID_CHARS,
                field_name="project_id",
            )
            if err:
                return err
        if context_triggers is not None:
            err = _check_list_len(
                context_triggers,
                max_items=MAX_TRIGGER_ITEMS,
                max_chars=MAX_TRIGGER_ITEM_CHARS,
                field_name="context_triggers",
            )
            if err:
                return err

        async def operation() -> str:
            scheduler = await _get_scheduler()
            reminder_id = await scheduler.create_reminder(
                title=title,
                time_expression=time_expression,
                description=description,
                user_id=user_id,
                project_id=project_id,
                context_triggers=context_triggers,
            )
            if reminder_id is None:
                return f"❌ Could not parse time expression: {time_expression!r}"
            return json.dumps({"reminder_id": reminder_id, "title": title})

        return await _run("Create reminder", operation)

    @mcp.tool()
    async def list_reminders(
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """List pending reminders.

        Args:
            user_id: Optional user filter (AND-matched).
            project_id: Optional project filter (AND-matched).

        Returns:
            JSON string with an array of reminder records.
        """
        if user_id is not None:
            err = _check_len(
                user_id,
                max_len=MAX_USER_ID_CHARS,
                field_name="user_id",
            )
            if err:
                return err
        if project_id is not None:
            err = _check_len(
                project_id,
                max_len=MAX_PROJECT_ID_CHARS,
                field_name="project_id",
            )
            if err:
                return err

        async def operation() -> str:
            scheduler = await _get_scheduler()
            reminders = await scheduler.get_pending_reminders(
                user_id=user_id,
                project_id=project_id,
            )
            return json.dumps(reminders, default=str)

        return await _run("List reminders", operation)

    @mcp.tool()
    async def list_due_reminders() -> str:
        """List reminders whose scheduled time has elapsed.

        Returns:
            JSON string with an array of due reminder records.
        """

        async def operation() -> str:
            scheduler = await _get_scheduler()
            reminders = await scheduler.get_due_reminders()
            return json.dumps(reminders, default=str)

        return await _run("List due reminders", operation)

    @mcp.tool()
    async def cancel_reminder(
        reminder_id: str,
        user_id: str = "default",
    ) -> str:
        """Cancel a pending reminder.

        Args:
            reminder_id: Identifier returned by :func:`create_reminder`.
            user_id: Owning user id (default ``"default"``). Recorded
                as ``requested_user_id`` in the response envelope for
                forensic correlation; the system does **not** verify that
                this caller actually owns the reminder. Ownership
                verification (rejecting cancels from a non-owning user)
                is deferred until ``ReminderScheduler`` exposes a public
                ``get_reminder`` method that returns the owning
                ``user_id``.

        Returns:
            JSON string with
            ``{"reminder_id": ..., "requested_user_id": ...,
            "ownership_verified": false, "cancelled": bool}``.
            ``ownership_verified`` is always ``false`` until the deferred
            ownership check lands — see the deferred caveat above.
        """
        err = _check_len(
            reminder_id,
            max_len=MAX_REMINDER_ID_CHARS,
            field_name="reminder_id",
        )
        if err:
            return err
        err = _check_len(
            user_id,
            max_len=MAX_USER_ID_CHARS,
            field_name="user_id",
        )
        if err:
            return err

        async def operation() -> str:
            scheduler = await _get_scheduler()
            success = await scheduler.cancel_reminder(reminder_id=reminder_id)
            return json.dumps(
                {
                    "reminder_id": reminder_id,
                    "requested_user_id": user_id,
                    "ownership_verified": False,
                    "cancelled": success,
                }
            )

        return await _run("Cancel reminder", operation)

    @mcp.tool()
    async def execute_reminder(
        reminder_id: str,
        user_id: str = "default",
    ) -> str:
        """Force-execute a reminder now (independent of scheduled time).

        Args:
            reminder_id: Identifier returned by :func:`create_reminder`.
            user_id: Owning user id (default ``"default"``). Recorded
                as ``requested_user_id`` in the response envelope for
                forensic correlation; the system does **not** verify that
                this caller actually owns the reminder. Ownership
                verification (rejecting executes from a non-owning user)
                is deferred until ``ReminderScheduler`` exposes a public
                ``get_reminder`` method that returns the owning
                ``user_id``.

        Returns:
            JSON string with
            ``{"reminder_id": ..., "requested_user_id": ...,
            "ownership_verified": false, "executed": bool}``.
            ``ownership_verified`` is always ``false`` until the deferred
            ownership check lands — see the deferred caveat above.
        """
        err = _check_len(
            reminder_id,
            max_len=MAX_REMINDER_ID_CHARS,
            field_name="reminder_id",
        )
        if err:
            return err
        err = _check_len(
            user_id,
            max_len=MAX_USER_ID_CHARS,
            field_name="user_id",
        )
        if err:
            return err

        async def operation() -> str:
            scheduler = await _get_scheduler()
            success = await scheduler.execute_reminder(reminder_id=reminder_id)
            return json.dumps(
                {
                    "reminder_id": reminder_id,
                    "requested_user_id": user_id,
                    "ownership_verified": False,
                    "executed": success,
                }
            )

        return await _run("Execute reminder", operation)

    @mcp.tool()
    async def parse_natural_time(time_expression: str) -> str:
        """Parse a natural-language time expression to ISO-8601.

        Args:
            time_expression: Natural-language time such as
                ``"in 2 hours"`` or ``"tomorrow at 3pm"``.

        Returns:
            JSON string with ``{"expression": str, "parsed": str|None,
            "recurrence": str|None}``. ``parsed`` is ``None`` if the
            expression could not be parsed.
        """
        err = _check_len(
            time_expression,
            max_len=MAX_TIME_EXPR_CHARS,
            field_name="time_expression",
        )
        if err:
            return err

        def operation() -> str:
            parser = _get_parser()
            parsed: datetime | None = parser.parse_time_expression(time_expression)
            recurrence: str | None = parser.parse_recurrence(time_expression)
            payload: dict[str, Any] = {
                "expression": time_expression,
                "parsed": parsed.isoformat() if parsed is not None else None,
                "recurrence": recurrence,
            }
            return json.dumps(payload)

        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - MCP tool envelope must return a structured error string on any backend/runtime failure (sqlite, etc.)
            _get_logger().exception(f"Error in parse_natural_time: {exc}")
            return ToolMessages.operation_failed("Parse natural time", exc)
