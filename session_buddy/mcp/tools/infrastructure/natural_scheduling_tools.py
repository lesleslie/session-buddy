"""Natural-language scheduling MCP tools.

Wraps :class:`session_buddy.natural_scheduler.ReminderScheduler` and
the :class:`NaturalLanguageParser` as MCP tools for create / list /
cancel reminders plus natural-language time parsing.

Closes the gap identified in
``docs/feature-tracking/TOOL_REGISTRATION_GAPS.md`` (2026-09-09).
"""

from __future__ import annotations

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
_parser: NaturalLanguageParser | None = None


def _set_scheduler_for_testing(scheduler: ReminderScheduler | None) -> None:
    """Inject a scheduler for tests. ``None`` resets the cache."""
    global _scheduler
    _scheduler = scheduler


def _set_parser_for_testing(parser: NaturalLanguageParser | None) -> None:
    """Inject a parser for tests. ``None`` resets the cache."""
    global _parser
    _parser = parser


def _get_scheduler() -> ReminderScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = _build_scheduler()
    return _scheduler


def _get_parser() -> NaturalLanguageParser:
    global _parser
    if _parser is None:
        _parser = _build_parser()
    return _parser


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

        async def operation() -> str:
            scheduler = _get_scheduler()
            reminder_id = await scheduler.create_reminder(
                title=title,
                time_expression=time_expression,
                description=description,
                user_id=user_id,
                project_id=project_id,
                context_triggers=context_triggers,
            )
            if reminder_id is None:
                return (
                    f"❌ Could not parse time expression: {time_expression!r}"
                )
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

        async def operation() -> str:
            scheduler = _get_scheduler()
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
            scheduler = _get_scheduler()
            reminders = await scheduler.get_due_reminders()
            return json.dumps(reminders, default=str)

        return await _run("List due reminders", operation)

    @mcp.tool()
    async def cancel_reminder(reminder_id: str) -> str:
        """Cancel a pending reminder.

        Args:
            reminder_id: Identifier returned by :func:`create_reminder`.

        Returns:
            JSON string with ``{"reminder_id": ..., "cancelled": bool}``.
        """

        async def operation() -> str:
            scheduler = _get_scheduler()
            success = await scheduler.cancel_reminder(reminder_id=reminder_id)
            return json.dumps(
                {"reminder_id": reminder_id, "cancelled": success}
            )

        return await _run("Cancel reminder", operation)

    @mcp.tool()
    async def execute_reminder(reminder_id: str) -> str:
        """Force-execute a reminder now (independent of scheduled time).

        Args:
            reminder_id: Identifier returned by :func:`create_reminder`.

        Returns:
            JSON string with ``{"reminder_id": ..., "executed": bool}``.
        """

        async def operation() -> str:
            scheduler = _get_scheduler()
            success = await scheduler.execute_reminder(reminder_id=reminder_id)
            return json.dumps(
                {"reminder_id": reminder_id, "executed": success}
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

        def operation() -> str:
            parser = _get_parser()
            parsed: datetime | None = parser.parse_time_expression(
                time_expression
            )
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
