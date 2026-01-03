"""Natural Language Scheduling module for time-based reminders and triggers.

This module provides intelligent scheduling capabilities including:
- Natural language time parsing ("in 30 minutes", "tomorrow at 9am")
- Recurring reminders and cron-like scheduling
- Context-aware reminder triggers
- Integration with session workflow
"""

import asyncio
import importlib.util
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DATEUTIL_AVAILABLE = importlib.util.find_spec("dateutil") is not None
CRONTAB_AVAILABLE = importlib.util.find_spec("python_crontab") is not None
SCHEDULE_AVAILABLE = importlib.util.find_spec("schedule") is not None

if DATEUTIL_AVAILABLE:
    from dateutil.relativedelta import relativedelta

from .session_types import RecurrenceInterval
from .utils.scheduler import (
    NaturalLanguageParser,
    NaturalReminder,
    ReminderStatus,
    ReminderType,
)

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Manages scheduling and execution of reminders."""

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize reminder scheduler."""
        self.db_path = db_path or str(
            Path.home() / ".claude" / "data" / "natural_scheduler.db",
        )
        self.parser = NaturalLanguageParser()
        self._lock = threading.Lock()
        self._running = False
        self._scheduler_thread: threading.Thread | None = None
        self._callbacks: dict[str, list[Callable[..., Any]]] = {}
        self._init_database()

    def _init_database(self) -> None:
        """Initialize SQLite database for reminders."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    reminder_id TEXT PRIMARY KEY,
                    reminder_type TEXT NOT NULL,
                    expression TEXT,
                    scheduled_time TIMESTAMP NOT NULL,
                    action TEXT,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP,
                    executed_at TIMESTAMP,
                    recurrence_pattern TEXT,
                    failure_reason TEXT,
                    metadata TEXT  -- JSON object
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminder_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reminder_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TIMESTAMP,
                    result TEXT,
                    details TEXT  -- JSON object
                )
            """)

            # Create indices
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_scheduled ON reminders(scheduled_for)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_project ON reminders(project_id)",
            )

    async def create_reminder(
        self,
        title: str,
        time_expression: str,
        description: str = "",
        user_id: str = "default",
        project_id: str | None = None,
        notification_method: str = "session",
        context_triggers: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Create a new reminder from natural language."""
        # Parse the time expression
        scheduled_time = self.parser.parse_time_expression(time_expression)
        if not scheduled_time:
            return None

        # Check for recurrence
        recurrence_pattern = self.parser.parse_recurrence(time_expression)
        reminder_type = (
            ReminderType.RECURRING if recurrence_pattern else ReminderType.TASK
        )

        # Generate reminder ID
        reminder_id = f"rem_{int(time.time() * 1000)}"

        # Build metadata from additional fields
        reminder_metadata: dict[str, Any] = {
            "title": title,
            "description": description,
            "user_id": user_id,
            "project_id": project_id,
            "context_triggers": context_triggers or [],
            "notification_method": notification_method,
        }
        if metadata:
            reminder_metadata.update(metadata)

        reminder = NaturalReminder(
            reminder_id=reminder_id,
            reminder_type=reminder_type,
            expression=time_expression,
            scheduled_time=scheduled_time,
            action=title or description,
            status=ReminderStatus.PENDING,
            created_at=datetime.now(),
            executed_at=None,
            recurrence_pattern=recurrence_pattern,
            metadata=reminder_metadata,
        )

        # Store in database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO reminders (reminder_id, reminder_type, expression, scheduled_time, action,
                                     status, created_at, executed_at, recurrence_pattern, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    reminder.reminder_id,
                    reminder.reminder_type.value,
                    reminder.expression,
                    reminder.scheduled_time,
                    reminder.action,
                    reminder.status.value,
                    reminder.created_at,
                    reminder.executed_at,
                    reminder.recurrence_pattern,
                    json.dumps(reminder.metadata),
                ),
            )

        # Log creation
        await self._log_reminder_action(
            reminder_id,
            "created",
            "success",
            {
                "scheduled_for": scheduled_time.isoformat(),
                "time_expression": time_expression,
            },
        )

        return reminder_id

    async def get_pending_reminders(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get pending reminders."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where_conditions = ["status IN ('pending', 'active')"]
            params = []

            if user_id:
                where_conditions.append("user_id = ?")
                params.append(user_id)

            if project_id:
                where_conditions.append("project_id = ?")
                params.append(project_id)

            # Build SQL safely - all user input is parameterized via params list
            query = (
                "SELECT * FROM reminders WHERE "
                + " AND ".join(where_conditions)
                + " ORDER BY scheduled_for"
            )

            cursor = conn.execute(query, params)
            results = []

            for row in cursor.fetchall():
                result = dict(row)
                result["context_triggers"] = json.loads(
                    result["context_triggers"] or "[]",
                )
                result["metadata"] = json.loads(result["metadata"] or "{}")
                results.append(result)

            return results

    async def get_due_reminders(
        self,
        check_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get reminders that are due for execution."""
        check_time = check_time or datetime.now()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute(
                """
                SELECT * FROM reminders
                WHERE status = 'pending' AND scheduled_for <= ?
                ORDER BY scheduled_for
            """,
                (check_time,),
            )

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result["context_triggers"] = json.loads(
                    result["context_triggers"] or "[]",
                )
                result["metadata"] = json.loads(result["metadata"] or "{}")
                results.append(result)

            return results

    async def execute_reminder(self, reminder_id: str) -> bool:
        """Execute a due reminder."""
        try:
            # Get reminder details
            reminder_data = await self._get_reminder_by_id(reminder_id)
            if not reminder_data:
                return False

            # Execute callbacks
            await self._execute_notification_callbacks(reminder_id, reminder_data)

            # Handle recurring reminders or mark as executed
            recurrence_pattern = (
                reminder_data.get("recurrence_pattern")
                or reminder_data.get("recurrence_rule")  # type: ignore[arg-type]
            )
            if recurrence_pattern:
                return await self._handle_recurring_reminder(
                    reminder_id,
                    reminder_data,
                    recurrence_pattern,
                )
            return await self._mark_reminder_executed(reminder_id)

        except Exception as e:
            await self._log_reminder_action(
                reminder_id,
                "executed",
                "failed",
                {"error": str(e)},
            )
            return False

    async def _get_reminder_by_id(self, reminder_id: str) -> dict[str, Any] | None:
        """Fetch and parse reminder data from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?",
                (reminder_id,),
            ).fetchone()

            if not row:
                return None

            reminder_data = dict(row)
            reminder_data["context_triggers"] = json.loads(
                reminder_data.get("context_triggers") or "[]",
            )
            reminder_data["metadata"] = json.loads(
                reminder_data.get("metadata") or "{}",
            )
            return reminder_data

    async def _execute_notification_callbacks(
        self,
        reminder_id: str,
        reminder_data: dict[str, Any],
    ) -> None:
        """Execute all registered callbacks for a reminder."""
        callbacks = self._callbacks.get(
            reminder_data.get("notification_method", ""), []
        )
        for callback in callbacks:
            try:
                await callback(reminder_data)
            except Exception as e:
                logger.exception(f"Callback error for reminder {reminder_id}: {e}")

    async def _handle_recurring_reminder(
        self,
        reminder_id: str,
        reminder_data: dict[str, Any],
        recurrence_pattern: Any,
    ) -> bool:
        """Schedule next occurrence for recurring reminder."""
        next_time = self._calculate_next_occurrence(
            reminder_data.get("scheduled_time") or reminder_data.get("scheduled_for"),  # type: ignore[arg-type]
            recurrence_pattern,
        )

        if next_time:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE reminders
                    SET scheduled_for = ?, status = 'pending', executed_at = NULL
                    WHERE id = ?
                """,
                    (next_time, reminder_id),
                )

            await self._log_reminder_action(
                reminder_id,
                "rescheduled",
                "success",
                {"next_occurrence": next_time.isoformat()},
            )
            return True

        # If no next occurrence, mark as executed
        return await self._mark_reminder_executed(reminder_id)

    async def _mark_reminder_executed(self, reminder_id: str) -> bool:
        """Mark reminder as executed in database."""
        now = datetime.now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE reminders
                SET status = ?, executed_at = ?
                WHERE id = ?
            """,
                (ReminderStatus.EXECUTED.value, now, reminder_id),
            )

        await self._log_reminder_action(
            reminder_id,
            "executed",
            "success",
            {"executed_at": now.isoformat()},
        )
        return True

    async def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancel a pending reminder."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute(
                    """
                    UPDATE reminders
                    SET status = ?
                    WHERE id = ? AND status IN ('pending', 'active')
                """,
                    (ReminderStatus.CANCELLED.value, reminder_id),
                )

                success = result.rowcount > 0

            if success:
                await self._log_reminder_action(reminder_id, "cancelled", "success", {})

            return success

        except Exception as e:
            await self._log_reminder_action(
                reminder_id,
                "cancelled",
                "failed",
                {"error": str(e)},
            )
            return False

    def register_notification_callback(
        self,
        method: str,
        callback: Callable[..., Any],
    ) -> None:
        """Register callback for notification method."""
        if method not in self._callbacks:
            self._callbacks[method] = []
        self._callbacks[method].append(callback)

    def start_scheduler(self) -> None:
        """Start the background scheduler."""
        if self._running:
            return

        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
        )
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        """Stop the background scheduler."""
        self._running = False
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5.0)

    def _scheduler_loop(self) -> None:
        """Background scheduler loop."""
        while self._running:
            loop = None  # Initialize to prevent "possibly unbound" error
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._check_and_execute_reminders())
            except Exception as e:
                logger.exception(f"Scheduler loop error: {e}")
            finally:
                if loop and not loop.is_closed():
                    loop.close()
                time.sleep(60)  # Check every minute

    async def _check_and_execute_reminders(self) -> None:
        """Check for due reminders and execute them."""
        due_reminders = await self.get_due_reminders()

        for reminder in due_reminders:
            await self.execute_reminder(reminder["id"])

    def _parse_recurrence_interval(self, recurrence_rule: str) -> RecurrenceInterval:
        """Parse frequency and interval from recurrence rule."""
        parts = recurrence_rule.split(";")
        interval = 1
        freq = None

        for part in parts:
            if part.startswith("FREQ="):
                freq = part.split("=")[1]
            elif part.startswith("INTERVAL="):
                interval = int(part.split("=")[1])

        return RecurrenceInterval(frequency=freq, interval=interval)

    def _calculate_simple_occurrence(
        self,
        last_time: datetime,
        recurrence_rule: str,
    ) -> datetime | None:
        """Calculate simple recurrence occurrences (daily, weekly, monthly)."""
        if recurrence_rule.startswith("FREQ=DAILY"):
            return last_time + timedelta(days=1)  # type: ignore[no-any-return]
        if recurrence_rule.startswith("FREQ=WEEKLY"):
            return last_time + timedelta(weeks=1)  # type: ignore[no-any-return]
        if recurrence_rule.startswith("FREQ=MONTHLY"):
            return last_time + relativedelta(months=1)  # type: ignore[no-any-return]
        return None

    def _calculate_interval_occurrence(
        self,
        last_time: datetime,
        recurrence_rule: str,
    ) -> datetime | None:
        """Calculate interval-based recurrence occurrences."""
        if "INTERVAL=" in recurrence_rule:
            recurrence = self._parse_recurrence_interval(recurrence_rule)
            freq = recurrence.frequency
            interval = recurrence.interval

            if freq == "HOURLY":
                return last_time + timedelta(hours=interval)  # type: ignore[no-any-return]
            if freq == "MINUTELY":
                return last_time + timedelta(minutes=interval)  # type: ignore[no-any-return]
            if freq == "DAILY":
                return last_time + timedelta(days=interval)  # type: ignore[no-any-return]
        return None

    def _check_dateutil_availability(self) -> bool:
        """Check if dateutil is available for processing."""
        return DATEUTIL_AVAILABLE

    def _attempt_simple_calculation(
        self,
        last_time: datetime,
        recurrence_rule: str,
    ) -> datetime | None:
        """Attempt to calculate using simple occurrence rules."""
        try:
            return self._calculate_simple_occurrence(last_time, recurrence_rule)
        except Exception:
            return None

    def _attempt_interval_calculation(
        self,
        last_time: datetime,
        recurrence_rule: str,
    ) -> datetime | None:
        """Attempt to calculate using interval occurrence rules."""
        try:
            return self._calculate_interval_occurrence(last_time, recurrence_rule)
        except Exception:
            return None

    def _calculate_next_occurrence(
        self,
        last_time: datetime,
        recurrence_rule: str,
    ) -> datetime | None:
        """Calculate next occurrence for recurring reminder."""
        if not DATEUTIL_AVAILABLE:
            return None

        try:
            # Try simple rule parsing first
            result = self._calculate_simple_occurrence(last_time, recurrence_rule)
            if result:
                return result

            # Try interval-based recurrence rules
            result = self._calculate_interval_occurrence(last_time, recurrence_rule)
            if result:
                return result

        except Exception as e:
            logger.exception(f"Error calculating next occurrence: {e}")

        return None

    async def _log_reminder_action(
        self,
        reminder_id: str,
        action: str,
        result: str,
        details: dict[str, Any],
    ) -> None:
        """Log reminder action for audit trail."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO reminder_history (reminder_id, action, timestamp, result, details)
                VALUES (?, ?, ?, ?, ?)
            """,
                (reminder_id, action, datetime.now(), result, json.dumps(details)),
            )


# Global scheduler instance
_reminder_scheduler = None


def get_reminder_scheduler() -> "ReminderScheduler":
    """Get global reminder scheduler instance."""
    global _reminder_scheduler
    if _reminder_scheduler is None:
        _reminder_scheduler = ReminderScheduler()
    return _reminder_scheduler


# Public API functions for MCP tools
async def create_natural_reminder(
    title: str,
    time_expression: str,
    description: str = "",
    user_id: str = "default",
    project_id: str | None = None,
    notification_method: str = "session",
) -> str | None:
    """Create reminder from natural language time expression."""
    scheduler = get_reminder_scheduler()
    return await scheduler.create_reminder(
        title,
        time_expression,
        description,
        user_id,
        project_id,
        notification_method,
    )


async def list_user_reminders(
    user_id: str = "default",
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """List pending reminders for user/project."""
    scheduler = get_reminder_scheduler()
    return await scheduler.get_pending_reminders(user_id, project_id)


async def cancel_user_reminder(reminder_id: str) -> bool:
    """Cancel a specific reminder."""
    scheduler = get_reminder_scheduler()
    return await scheduler.cancel_reminder(reminder_id)


async def check_due_reminders() -> list[dict[str, Any]]:
    """Check for reminders that are due now."""
    scheduler = get_reminder_scheduler()
    return await scheduler.get_due_reminders()


def start_reminder_service() -> None:
    """Start the background reminder service."""
    scheduler = get_reminder_scheduler()
    scheduler.start_scheduler()


def stop_reminder_service() -> None:
    """Stop the background reminder service."""
    scheduler = get_reminder_scheduler()
    scheduler.stop_scheduler()


def register_session_notifications() -> None:
    """Register session-based notification callbacks."""
    scheduler = get_reminder_scheduler()

    async def session_notification(reminder_data: dict[str, Any]) -> None:
        """Default session notification handler."""
        logger.info(
            f"Reminder: {reminder_data['title']} - {reminder_data['description']}",
        )

    scheduler.register_notification_callback("session", session_notification)
