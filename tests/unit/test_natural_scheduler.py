"""Unit tests for natural_scheduler module.

Comprehensive tests covering:
- ReminderScheduler class and all public methods
- Public API functions
- Edge cases: empty inputs, None values, exceptions
- Error handling paths
"""

import asyncio
import json
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Mock the modules before importing the scheduler module
@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock all external dependencies."""
    with patch.dict("sys.modules", {
        "dateutil": MagicMock(),
        "dateutil.relativedelta": MagicMock(),
        "python_crontab": MagicMock(),
        "schedule": MagicMock(),
    }):
        yield


# Import after mocking
from session_buddy.natural_scheduler import (
    DATEUTIL_AVAILABLE,
    ReminderScheduler,
    cancel_user_reminder,
    check_due_reminders,
    create_natural_reminder,
    get_reminder_scheduler,
    list_user_reminders,
    register_session_notifications,
    start_reminder_service,
    stop_reminder_service,
)
from session_buddy.session_types import RecurrenceInterval
from session_buddy.utils.scheduler import (
    NaturalReminder,
    ReminderStatus,
    ReminderType,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test_scheduler.db")


@pytest.fixture
def mock_parser():
    """Create a mock NaturalLanguageParser."""
    parser = MagicMock()
    parser.parse_time_expression = MagicMock()
    parser.parse_recurrence = MagicMock()
    return parser


@pytest.fixture
def scheduler(temp_db, mock_parser):
    """Create a ReminderScheduler with mocked parser."""
    with patch(
        "session_buddy.natural_scheduler.NaturalLanguageParser",
        return_value=mock_parser,
    ):
        with patch("session_buddy.natural_scheduler.Path.mkdir"):
            with patch("sqlite3.connect") as mock_conn:
                mock_conn.return_value.__enter__ = MagicMock()
                mock_conn.return_value.__exit__ = MagicMock()
                sched = ReminderScheduler(db_path=temp_db)
                sched.parser = mock_parser
                yield sched


@pytest.fixture
def sample_reminder_data():
    """Sample reminder data for testing."""
    return {
        "reminder_id": "rem_1234567890",
        "reminder_type": ReminderType.TASK,
        "expression": "in 30 minutes",
        "scheduled_time": datetime.now() + timedelta(minutes=30),
        "action": "Test reminder",
        "status": ReminderStatus.PENDING,
        "created_at": datetime.now(),
        "executed_at": None,
        "recurrence_pattern": None,
        "metadata": {
            "title": "Test reminder",
            "description": "Test description",
            "user_id": "default",
            "project_id": None,
            "context_triggers": [],
            "notification_method": "session",
        },
    }


# ============================================================================
# Test Classes Grouped by Method/Feature
# ============================================================================


class TestReminderSchedulerInit:
    """Tests for ReminderScheduler.__init__."""

    def test_init_with_custom_db_path(self, temp_db, mock_parser):
        """Test initialization with custom db_path."""
        with patch(
            "session_buddy.natural_scheduler.NaturalLanguageParser",
            return_value=mock_parser,
        ):
            with patch("session_buddy.natural_scheduler.Path.mkdir"):
                with patch("sqlite3.connect"):
                    sched = ReminderScheduler(db_path=temp_db)
                    assert sched.db_path == temp_db
                    assert sched.parser == mock_parser
                    assert isinstance(sched._lock, type(threading.Lock()))
                    assert sched._running is False
                    assert sched._scheduler_thread is None

    def test_init_with_default_db_path(self, mock_parser):
        """Test initialization with default db_path."""
        with patch(
            "session_buddy.natural_scheduler.NaturalLanguageParser",
            return_value=mock_parser,
        ):
            with patch("session_buddy.natural_scheduler.Path") as mock_path:
                mock_path.home.return_value = Path("/home/user")
                mock_path.return_value.mkdir = MagicMock()
                with patch("sqlite3.connect"):
                    sched = ReminderScheduler()
                    expected_path = str(Path("/home/user/.claude/data/natural_scheduler.db"))
                    assert sched.db_path == expected_path

    def test_init_creates_lock(self, mock_parser):
        """Test that __init__ creates threading lock."""
        with patch(
            "session_buddy.natural_scheduler.NaturalLanguageParser",
            return_value=mock_parser,
        ):
            with patch("session_buddy.natural_scheduler.Path.mkdir"):
                with patch("sqlite3.connect"):
                    sched = ReminderScheduler()
                    assert hasattr(sched, "_lock")
                    assert isinstance(sched._lock, type(threading.Lock()))

    def test_init_sets_running_false(self, mock_parser):
        """Test that __init__ sets _running to False."""
        with patch(
            "session_buddy.natural_scheduler.NaturalLanguageParser",
            return_value=mock_parser,
        ):
            with patch("session_buddy.natural_scheduler.Path.mkdir"):
                with patch("sqlite3.connect"):
                    sched = ReminderScheduler()
                    assert sched._running is False

    def test_init_sets_callbacks_empty_dict(self, mock_parser):
        """Test that __init__ initializes empty callbacks dict."""
        with patch(
            "session_buddy.natural_scheduler.NaturalLanguageParser",
            return_value=mock_parser,
        ):
            with patch("session_buddy.natural_scheduler.Path.mkdir"):
                with patch("sqlite3.connect"):
                    sched = ReminderScheduler()
                    assert sched._callbacks == {}


class TestDatabaseInit:
    """Tests for _init_database method."""

    def test_init_database_creates_tables(self, temp_db, mock_parser):
        """Test database table creation."""
        with patch(
            "session_buddy.natural_scheduler.NaturalLanguageParser",
            return_value=mock_parser,
        ):
            with patch("session_buddy.natural_scheduler.Path") as mock_path:
                mock_path.mkdir = MagicMock()
                mock_path.return_value = MagicMock()
                mock_path.return_value.parent = MagicMock()
                with patch("sqlite3.connect") as mock_connect:
                    mock_conn = MagicMock()
                    mock_conn.execute = MagicMock()
                    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                    mock_connect.return_value.__exit__ = MagicMock(return_value=None)
                    sched = ReminderScheduler(db_path=temp_db)
                    sched.parser = mock_parser
                    # _init_database is called in __init__
                    assert mock_conn.execute.called


class TestCreateReminder:
    """Tests for create_reminder method."""

    @pytest.mark.asyncio
    async def test_create_reminder_success(self, scheduler, mock_parser):
        """Test successful reminder creation."""
        mock_parser.parse_time_expression.return_value = datetime.now() + timedelta(minutes=30)
        mock_parser.parse_recurrence.return_value = None

        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler.create_reminder(
                    title="Test Reminder",
                    time_expression="in 30 minutes",
                )

                assert result is not None
                assert result.startswith("rem_")

    @pytest.mark.asyncio
    async def test_create_reminder_invalid_time_expression(self, scheduler, mock_parser):
        """Test reminder creation with invalid time expression returns None."""
        mock_parser.parse_time_expression.return_value = None

        result = await scheduler.create_reminder(
            title="Test Reminder",
            time_expression="invalid time",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_create_reminder_with_recurrence(self, scheduler, mock_parser):
        """Test reminder creation with recurrence pattern."""
        mock_parser.parse_time_expression.return_value = datetime.now() + timedelta(minutes=30)
        mock_parser.parse_recurrence.return_value = "FREQ=DAILY"

        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler.create_reminder(
                    title="Recurring Reminder",
                    time_expression="every day at 9am",
                )

                assert result is not None

    @pytest.mark.asyncio
    async def test_create_reminder_with_metadata(self, scheduler, mock_parser):
        """Test reminder creation with metadata."""
        mock_parser.parse_time_expression.return_value = datetime.now() + timedelta(minutes=30)
        mock_parser.parse_recurrence.return_value = None
        custom_metadata = {"custom_key": "custom_value"}

        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler.create_reminder(
                    title="Test Reminder",
                    time_expression="in 30 minutes",
                    metadata=custom_metadata,
                )

                assert result is not None

    @pytest.mark.asyncio
    async def test_create_reminder_with_context_triggers(self, scheduler, mock_parser):
        """Test reminder creation with context triggers."""
        mock_parser.parse_time_expression.return_value = datetime.now() + timedelta(minutes=30)
        mock_parser.parse_recurrence.return_value = None
        context_triggers = ["file_edit", "git_commit"]

        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler.create_reminder(
                    title="Context Reminder",
                    time_expression="in 1 hour",
                    context_triggers=context_triggers,
                )

                assert result is not None

    @pytest.mark.asyncio
    async def test_create_reminder_empty_title_and_description(self, scheduler, mock_parser):
        """Test reminder creation with empty title and description."""
        mock_parser.parse_time_expression.return_value = datetime.now() + timedelta(minutes=30)
        mock_parser.parse_recurrence.return_value = None

        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler.create_reminder(
                    title="",
                    time_expression="in 30 minutes",
                    description="",
                )

                assert result is not None


class TestGetPendingReminders:
    """Tests for get_pending_reminders method."""

    @pytest.mark.asyncio
    async def test_get_pending_reminders_no_filters(self, scheduler):
        """Test get_pending_reminders with no filters."""
        mock_rows = [
            {
                "reminder_id": "rem_1",
                "reminder_type": "task",
                "expression": "in 30 minutes",
                "scheduled_time": datetime.now().isoformat(),
                "action": "Test",
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "executed_at": None,
                "recurrence_pattern": None,
                "metadata": '{"title": "Test"}',
                "context_triggers": "[]",
            }
        ]

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = mock_rows
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_pending_reminders()

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_pending_reminders_with_user_id_filter(self, scheduler):
        """Test get_pending_reminders filtered by user_id."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_pending_reminders(user_id="test_user")

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_pending_reminders_with_project_id_filter(self, scheduler):
        """Test get_pending_reminders filtered by project_id."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_pending_reminders(project_id="test_project")

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_pending_reminders_with_both_filters(self, scheduler):
        """Test get_pending_reminders filtered by both user_id and project_id."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_pending_reminders(
                user_id="test_user",
                project_id="test_project",
            )

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_pending_reminders_empty_result(self, scheduler):
        """Test get_pending_reminders with empty result."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_pending_reminders()

            assert result == []


class TestGetDueReminders:
    """Tests for get_due_reminders method."""

    @pytest.mark.asyncio
    async def test_get_due_reminders_default_time(self, scheduler):
        """Test get_due_reminders with default check_time."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_due_reminders()

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_due_reminders_custom_time(self, scheduler):
        """Test get_due_reminders with custom check_time."""
        custom_time = datetime.now()
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_due_reminders(check_time=custom_time)

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_due_reminders_with_due_items(self, scheduler):
        """Test get_due_reminders with due reminder items."""
        mock_rows = [
            {
                "reminder_id": "rem_1",
                "reminder_type": "task",
                "expression": "in 30 minutes",
                "scheduled_for": datetime.now().isoformat(),
                "action": "Test",
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "executed_at": None,
                "recurrence_pattern": None,
                "metadata": '{"title": "Test"}',
                "context_triggers": "[]",
            }
        ]

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = mock_rows
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler.get_due_reminders()

            assert isinstance(result, list)


class TestExecuteReminder:
    """Tests for execute_reminder method."""

    @pytest.mark.asyncio
    async def test_execute_reminder_not_found(self, scheduler):
        """Test execute_reminder when reminder not found."""
        with patch.object(scheduler, "_get_reminder_by_id", new_callable=AsyncMock, return_value=None):
            result = await scheduler.execute_reminder("nonexistent_id")
            assert result is False

    @pytest.mark.asyncio
    async def test_execute_reminder_success_non_recurring(self, scheduler, sample_reminder_data):
        """Test execute_reminder for non-recurring reminder."""
        sample_reminder_data["recurrence_pattern"] = None

        with patch.object(scheduler, "_get_reminder_by_id", new_callable=AsyncMock, return_value=sample_reminder_data):
            with patch.object(scheduler, "_execute_notification_callbacks", new_callable=AsyncMock):
                with patch.object(scheduler, "_mark_reminder_executed", new_callable=AsyncMock, return_value=True):
                    result = await scheduler.execute_reminder("rem_1234567890")
                    assert result is True

    @pytest.mark.asyncio
    async def test_execute_reminder_success_recurring(self, scheduler, sample_reminder_data):
        """Test execute_reminder for recurring reminder."""
        sample_reminder_data["recurrence_pattern"] = "FREQ=DAILY"

        with patch.object(scheduler, "_get_reminder_by_id", new_callable=AsyncMock, return_value=sample_reminder_data):
            with patch.object(scheduler, "_execute_notification_callbacks", new_callable=AsyncMock):
                with patch.object(scheduler, "_handle_recurring_reminder", new_callable=AsyncMock, return_value=True):
                    result = await scheduler.execute_reminder("rem_1234567890")
                    assert result is True

    @pytest.mark.asyncio
    async def test_execute_reminder_exception_handling(self, scheduler, sample_reminder_data):
        """Test execute_reminder exception handling."""
        sample_reminder_data["recurrence_pattern"] = None

        with patch.object(scheduler, "_get_reminder_by_id", new_callable=AsyncMock, return_value=sample_reminder_data):
            with patch.object(scheduler, "_execute_notification_callbacks", new_callable=AsyncMock, side_effect=Exception("Callback error")):
                with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
                    # When callbacks throw, execute_reminder catches and returns False
                    result = await scheduler.execute_reminder("rem_1234567890")
                    assert result is False

    @pytest.mark.asyncio
    async def test_execute_reminder_with_recurrence_rule_key(self, scheduler, sample_reminder_data):
        """Test execute_reminder when reminder has recurrence_rule key instead of recurrence_pattern."""
        del sample_reminder_data["recurrence_pattern"]
        sample_reminder_data["recurrence_rule"] = "FREQ=DAILY"

        with patch.object(scheduler, "_get_reminder_by_id", new_callable=AsyncMock, return_value=sample_reminder_data):
            with patch.object(scheduler, "_execute_notification_callbacks", new_callable=AsyncMock):
                with patch.object(scheduler, "_handle_recurring_reminder", new_callable=AsyncMock, return_value=True):
                    result = await scheduler.execute_reminder("rem_1234567890")
                    assert result is True


class TestGetReminderById:
    """Tests for _get_reminder_by_id method."""

    @pytest.mark.asyncio
    async def test_get_reminder_by_id_found(self, scheduler, sample_reminder_data):
        """Test _get_reminder_by_id when reminder exists."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_row = MagicMock()
            mock_row.__getitem__ = lambda s, k: sample_reminder_data.get(k)
            mock_conn.execute.return_value.fetchone.return_value = mock_row
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler._get_reminder_by_id("rem_1234567890")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_reminder_by_id_not_found(self, scheduler):
        """Test _get_reminder_by_id when reminder doesn't exist."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_conn.row_factory = sqlite3.Row
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            result = await scheduler._get_reminder_by_id("nonexistent_id")
            assert result is None


class TestExecuteNotificationCallbacks:
    """Tests for _execute_notification_callbacks method."""

    @pytest.mark.asyncio
    async def test_execute_callbacks_with_registered_callback(self, scheduler, sample_reminder_data):
        """Test _execute_notification_callbacks with registered callback."""
        callback = AsyncMock()
        scheduler._callbacks["session"] = [callback]
        sample_reminder_data["notification_method"] = "session"

        await scheduler._execute_notification_callbacks("rem_123", sample_reminder_data)

        callback.assert_called_once_with(sample_reminder_data)

    @pytest.mark.asyncio
    async def test_execute_callbacks_no_registered_callback(self, scheduler, sample_reminder_data):
        """Test _execute_notification_callbacks with no registered callback."""
        scheduler._callbacks = {}
        sample_reminder_data["notification_method"] = "session"

        # Should not raise
        await scheduler._execute_notification_callbacks("rem_123", sample_reminder_data)

    @pytest.mark.asyncio
    async def test_execute_callbacks_with_callback_exception(self, scheduler, sample_reminder_data):
        """Test _execute_notification_callbacks when callback raises exception."""
        callback = AsyncMock(side_effect=Exception("Callback error"))
        scheduler._callbacks["session"] = [callback]
        sample_reminder_data["notification_method"] = "session"

        # Should not raise - exceptions are logged
        await scheduler._execute_notification_callbacks("rem_123", sample_reminder_data)


class TestHandleRecurringReminder:
    """Tests for _handle_recurring_reminder method."""

    @pytest.mark.asyncio
    async def test_handle_recurring_with_next_occurrence(self, scheduler, sample_reminder_data):
        """Test _handle_recurring_reminder with next occurrence calculated."""
        sample_reminder_data["scheduled_time"] = datetime.now()
        next_time = datetime.now() + timedelta(days=1)

        with patch.object(scheduler, "_calculate_next_occurrence", return_value=next_time):
            with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
                with patch("sqlite3.connect") as mock_connect:
                    mock_conn = MagicMock()
                    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                    mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                    result = await scheduler._handle_recurring_reminder(
                        "rem_123",
                        sample_reminder_data,
                        "FREQ=DAILY",
                    )
                    assert result is True

    @pytest.mark.asyncio
    async def test_handle_recurring_without_next_occurrence(self, scheduler, sample_reminder_data):
        """Test _handle_recurring_reminder when no next occurrence is found."""
        sample_reminder_data["scheduled_time"] = datetime.now()

        with patch.object(scheduler, "_calculate_next_occurrence", return_value=None):
            with patch.object(scheduler, "_mark_reminder_executed", new_callable=AsyncMock, return_value=True):
                result = await scheduler._handle_recurring_reminder(
                    "rem_123",
                    sample_reminder_data,
                    "FREQ=UNKNOWN",
                )
                assert result is True


class TestMarkReminderExecuted:
    """Tests for _mark_reminder_executed method."""

    @pytest.mark.asyncio
    async def test_mark_reminder_executed_success(self, scheduler):
        """Test _mark_reminder_executed successfully."""
        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler._mark_reminder_executed("rem_123")
                assert result is True


class TestCancelReminder:
    """Tests for cancel_reminder method."""

    @pytest.mark.asyncio
    async def test_cancel_reminder_success(self, scheduler):
        """Test cancel_reminder successfully."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.rowcount = 1
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
                result = await scheduler.cancel_reminder("rem_123")
                assert result is True

    @pytest.mark.asyncio
    async def test_cancel_reminder_not_found(self, scheduler):
        """Test cancel_reminder when reminder doesn't exist."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.rowcount = 0
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
                result = await scheduler.cancel_reminder("nonexistent_id")
                assert result is False

    @pytest.mark.asyncio
    async def test_cancel_reminder_exception(self, scheduler):
        """Test cancel_reminder when exception occurs."""
        with patch("sqlite3.connect", side_effect=sqlite3.Error("Database error")):
            with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
                result = await scheduler.cancel_reminder("rem_123")
                assert result is False


class TestRegisterNotificationCallback:
    """Tests for register_notification_callback method."""

    def test_register_callback_new_method(self, scheduler):
        """Test register_notification_callback for new method."""
        callback = MagicMock()
        scheduler.register_notification_callback("email", callback)
        assert "email" in scheduler._callbacks
        assert callback in scheduler._callbacks["email"]

    def test_register_callback_existing_method(self, scheduler):
        """Test register_notification_callback for existing method."""
        callback1 = MagicMock()
        callback2 = MagicMock()
        scheduler.register_notification_callback("session", callback1)
        scheduler.register_notification_callback("session", callback2)
        assert len(scheduler._callbacks["session"]) == 2

    def test_register_callback_multiple_methods(self, scheduler):
        """Test register_notification_callback for multiple methods."""
        callback_session = MagicMock()
        callback_email = MagicMock()
        scheduler.register_notification_callback("session", callback_session)
        scheduler.register_notification_callback("email", callback_email)
        assert len(scheduler._callbacks) == 2


class TestStartScheduler:
    """Tests for start_scheduler method."""

    def test_start_scheduler_not_running(self, scheduler):
        """Test start_scheduler when not running."""
        with patch("threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            scheduler.start_scheduler()

            assert scheduler._running is True
            mock_thread.assert_called_once()

    def test_start_scheduler_already_running(self, scheduler):
        """Test start_scheduler when already running."""
        scheduler._running = True

        with patch("threading.Thread") as mock_thread:
            scheduler.start_scheduler()
            mock_thread.assert_not_called()


class TestStopScheduler:
    """Tests for stop_scheduler method."""

    def test_stop_scheduler_running(self, scheduler):
        """Test stop_scheduler when running."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        scheduler._running = True
        scheduler._scheduler_thread = mock_thread

        scheduler.stop_scheduler()

        assert scheduler._running is False
        mock_thread.join.assert_called_once_with(timeout=5.0)

    def test_stop_scheduler_thread_not_alive(self, scheduler):
        """Test stop_scheduler when thread is not alive."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        scheduler._running = True
        scheduler._scheduler_thread = mock_thread

        scheduler.stop_scheduler()

        assert scheduler._running is False

    def test_stop_scheduler_no_thread(self, scheduler):
        """Test stop_scheduler when no thread exists."""
        scheduler._running = False
        scheduler._scheduler_thread = None

        scheduler.stop_scheduler()

        assert scheduler._running is False


class TestCheckAndExecuteReminders:
    """Tests for _check_and_execute_reminders method."""

    @pytest.mark.asyncio
    async def test_check_and_execute_reminders_no_due(self, scheduler):
        """Test _check_and_execute_reminders when no reminders are due."""
        with patch.object(scheduler, "get_due_reminders", new_callable=AsyncMock, return_value=[]):
            await scheduler._check_and_execute_reminders()

    @pytest.mark.asyncio
    async def test_check_and_execute_reminders_with_due(self, scheduler):
        """Test _check_and_execute_reminders with due reminders."""
        due_reminders = [
            {"id": "rem_1", "title": "Reminder 1"},
            {"id": "rem_2", "title": "Reminder 2"},
        ]

        with patch.object(scheduler, "get_due_reminders", new_callable=AsyncMock, return_value=due_reminders):
            with patch.object(scheduler, "execute_reminder", new_callable=AsyncMock, return_value=True):
                await scheduler._check_and_execute_reminders()


class TestParseRecurrenceInterval:
    """Tests for _parse_recurrence_interval method."""

    def test_parse_recurrence_interval_with_freq_and_interval(self, scheduler):
        """Test _parse_recurrence_interval with FREQ and INTERVAL."""
        result = scheduler._parse_recurrence_interval("FREQ=DAILY;INTERVAL=2")
        assert result.frequency == "DAILY"
        assert result.interval == 2

    def test_parse_recurrence_interval_with_freq_only(self, scheduler):
        """Test _parse_recurrence_interval with FREQ only."""
        result = scheduler._parse_recurrence_interval("FREQ=HOURLY")
        assert result.frequency == "HOURLY"
        assert result.interval == 1  # Default

    def test_parse_recurrence_interval_with_interval_only(self, scheduler):
        """Test _parse_recurrence_interval with INTERVAL only."""
        result = scheduler._parse_recurrence_interval("INTERVAL=3")
        assert result.frequency is None
        assert result.interval == 3

    def test_parse_recurrence_interval_empty(self, scheduler):
        """Test _parse_recurrence_interval with empty string."""
        result = scheduler._parse_recurrence_interval("")
        assert result.frequency is None
        assert result.interval == 1  # Default


class TestCalculateSimpleOccurrence:
    """Tests for _calculate_simple_occurrence method."""

    def test_calculate_simple_occurrence_daily(self, scheduler):
        """Test _calculate_simple_occurrence for FREQ=DAILY."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_simple_occurrence(last_time, "FREQ=DAILY")
        assert result == datetime(2024, 1, 2, 9, 0, 0)

    def test_calculate_simple_occurrence_weekly(self, scheduler):
        """Test _calculate_simple_occurrence for FREQ=WEEKLY."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_simple_occurrence(last_time, "FREQ=WEEKLY")
        assert result == datetime(2024, 1, 8, 9, 0, 0)

    def test_calculate_simple_occurrence_monthly(self, scheduler):
        """Test _calculate_simple_occurrence for FREQ=MONTHLY."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        with patch("session_buddy.natural_scheduler.DATEUTIL_AVAILABLE", True):
            with patch("session_buddy.natural_scheduler.relativedelta") as mock_relativedelta:
                mock_relativedelta.return_value = timedelta(days=30)
                result = scheduler._calculate_simple_occurrence(last_time, "FREQ=MONTHLY")
                assert result is not None

    def test_calculate_simple_occurrence_unknown(self, scheduler):
        """Test _calculate_simple_occurrence for unknown pattern."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_simple_occurrence(last_time, "FREQ=UNKNOWN")
        assert result is None


class TestCalculateIntervalOccurrence:
    """Tests for _calculate_interval_occurrence method."""

    def test_calculate_interval_occurrence_hourly(self, scheduler):
        """Test _calculate_interval_occurrence for HOURLY."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_interval_occurrence(last_time, "FREQ=HOURLY;INTERVAL=2")
        assert result == datetime(2024, 1, 1, 11, 0, 0)

    def test_calculate_interval_occurrence_minutely(self, scheduler):
        """Test _calculate_interval_occurrence for MINUTELY."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_interval_occurrence(last_time, "FREQ=MINUTELY;INTERVAL=15")
        assert result == datetime(2024, 1, 1, 9, 15, 0)

    def test_calculate_interval_occurrence_daily(self, scheduler):
        """Test _calculate_interval_occurrence for DAILY with interval."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_interval_occurrence(last_time, "FREQ=DAILY;INTERVAL=3")
        assert result == datetime(2024, 1, 4, 9, 0, 0)

    def test_calculate_interval_occurrence_without_interval(self, scheduler):
        """Test _calculate_interval_occurrence without INTERVAL."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_interval_occurrence(last_time, "FREQ=DAILY")
        assert result is None


class TestCheckDateutilAvailability:
    """Tests for _check_dateutil_availability method."""

    def test_check_dateutil_available(self, scheduler):
        """Test _check_dateutil_availability when dateutil is available."""
        with patch("session_buddy.natural_scheduler.DATEUTIL_AVAILABLE", True):
            result = scheduler._check_dateutil_availability()
            assert result is True

    def test_check_dateutil_not_available(self, scheduler):
        """Test _check_dateutil_availability when dateutil is not available."""
        with patch("session_buddy.natural_scheduler.DATEUTIL_AVAILABLE", False):
            result = scheduler._check_dateutil_availability()
            assert result is False


class TestAttemptSimpleCalculation:
    """Tests for _attempt_simple_calculation method."""

    def test_attempt_simple_calculation_success(self, scheduler):
        """Test _attempt_simple_calculation success."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._attempt_simple_calculation(last_time, "FREQ=DAILY")
        assert result is not None

    def test_attempt_simple_calculation_exception(self, scheduler):
        """Test _attempt_simple_calculation with exception."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        with patch.object(
            scheduler,
            "_calculate_simple_occurrence",
            side_effect=Exception("Calculation error"),
        ):
            result = scheduler._attempt_simple_calculation(last_time, "FREQ=DAILY")
            assert result is None


class TestAttemptIntervalCalculation:
    """Tests for _attempt_interval_calculation method."""

    def test_attempt_interval_calculation_success(self, scheduler):
        """Test _attempt_interval_calculation success."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._attempt_interval_calculation(last_time, "FREQ=HOURLY;INTERVAL=2")
        assert result is not None

    def test_attempt_interval_calculation_exception(self, scheduler):
        """Test _attempt_interval_calculation with exception."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        with patch.object(
            scheduler,
            "_calculate_interval_occurrence",
            side_effect=Exception("Calculation error"),
        ):
            result = scheduler._attempt_interval_calculation(last_time, "FREQ=HOURLY;INTERVAL=2")
            assert result is None


class TestCalculateNextOccurrence:
    """Tests for _calculate_next_occurrence method."""

    def test_calculate_next_occurrence_dateutil_unavailable(self, scheduler):
        """Test _calculate_next_occurrence when dateutil is not available."""
        with patch("session_buddy.natural_scheduler.DATEUTIL_AVAILABLE", False):
            result = scheduler._calculate_next_occurrence(
                datetime(2024, 1, 1, 9, 0, 0),
                "FREQ=DAILY",
            )
            assert result is None

    def test_calculate_next_occurrence_simple_rule(self, scheduler):
        """Test _calculate_next_occurrence with simple rule."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        with patch("session_buddy.natural_scheduler.DATEUTIL_AVAILABLE", True):
            result = scheduler._calculate_next_occurrence(last_time, "FREQ=DAILY")
            assert result is not None

    def test_calculate_next_occurrence_interval_rule(self, scheduler):
        """Test _calculate_next_occurrence with interval rule."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        with patch("session_buddy.natural_scheduler.DATEUTIL_AVAILABLE", True):
            result = scheduler._calculate_next_occurrence(last_time, "FREQ=HOURLY;INTERVAL=2")
            assert result is not None

    def test_calculate_next_occurrence_exception(self, scheduler):
        """Test _calculate_next_occurrence with exception."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        with patch("session_buddy.natural_scheduler.DATEUTIL_AVAILABLE", True):
            with patch.object(
                scheduler,
                "_calculate_simple_occurrence",
                side_effect=Exception("Error"),
            ):
                result = scheduler._calculate_next_occurrence(last_time, "FREQ=DAILY")
                assert result is None


class TestLogReminderAction:
    """Tests for _log_reminder_action method."""

    @pytest.mark.asyncio
    async def test_log_reminder_action_success(self, scheduler):
        """Test _log_reminder_action successful logging."""
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_connect.return_value.__exit__ = MagicMock(return_value=None)

            await scheduler._log_reminder_action(
                "rem_123",
                "created",
                "success",
                {"key": "value"},
            )


# ============================================================================
# Public API Function Tests
# ============================================================================


class TestGetReminderScheduler:
    """Tests for get_reminder_scheduler function."""

    def test_get_reminder_scheduler_singleton(self):
        """Test that get_reminder_scheduler returns singleton."""
        # Reset global
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        with patch("session_buddy.natural_scheduler.ReminderScheduler"):
            result1 = get_reminder_scheduler()
            result2 = get_reminder_scheduler()
            assert result1 is result2

    def test_get_reminder_scheduler_creates_instance(self):
        """Test that get_reminder_scheduler creates instance if None."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        with patch("session_buddy.natural_scheduler.ReminderScheduler") as mock_sched:
            mock_instance = MagicMock()
            mock_sched.return_value = mock_instance
            result = get_reminder_scheduler()
            mock_sched.assert_called_once()


class TestCreateNaturalReminder:
    """Tests for create_natural_reminder function."""

    @pytest.mark.asyncio
    async def test_create_natural_reminder_success(self):
        """Test create_natural_reminder success."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.create_reminder = AsyncMock(return_value="rem_123")
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await create_natural_reminder(
                title="Test",
                time_expression="in 30 minutes",
            )
            assert result == "rem_123"

    @pytest.mark.asyncio
    async def test_create_natural_reminder_invalid_time(self):
        """Test create_natural_reminder with invalid time."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.create_reminder = AsyncMock(return_value=None)
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await create_natural_reminder(
                title="Test",
                time_expression="invalid",
            )
            assert result is None


class TestListUserReminders:
    """Tests for list_user_reminders function."""

    @pytest.mark.asyncio
    async def test_list_user_reminders_empty(self):
        """Test list_user_reminders with empty result."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.get_pending_reminders = AsyncMock(return_value=[])
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await list_user_reminders()
            assert result == []

    @pytest.mark.asyncio
    async def test_list_user_reminders_with_filters(self):
        """Test list_user_reminders with filters."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.get_pending_reminders = AsyncMock(return_value=[])
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await list_user_reminders(
                user_id="test_user",
                project_id="test_project",
            )
            mock_scheduler.get_pending_reminders.assert_called_once()


class TestCancelUserReminder:
    """Tests for cancel_user_reminder function."""

    @pytest.mark.asyncio
    async def test_cancel_user_reminder_success(self):
        """Test cancel_user_reminder success."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.cancel_reminder = AsyncMock(return_value=True)
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await cancel_user_reminder("rem_123")
            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_user_reminder_not_found(self):
        """Test cancel_user_reminder when not found."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.cancel_reminder = AsyncMock(return_value=False)
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await cancel_user_reminder("nonexistent")
            assert result is False


class TestCheckDueReminders:
    """Tests for check_due_reminders function."""

    @pytest.mark.asyncio
    async def test_check_due_reminders_empty(self):
        """Test check_due_reminders with empty result."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.get_due_reminders = AsyncMock(return_value=[])
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await check_due_reminders()
            assert result == []

    @pytest.mark.asyncio
    async def test_check_due_reminders_with_items(self):
        """Test check_due_reminders with items."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        due_items = [{"id": "rem_1"}, {"id": "rem_2"}]
        mock_scheduler = MagicMock()
        mock_scheduler.get_due_reminders = AsyncMock(return_value=due_items)
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            result = await check_due_reminders()
            assert result == due_items


class TestStartReminderService:
    """Tests for start_reminder_service function."""

    def test_start_reminder_service_calls_scheduler(self):
        """Test start_reminder_service calls start_scheduler."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            start_reminder_service()
            mock_scheduler.start_scheduler.assert_called_once()


class TestStopReminderService:
    """Tests for stop_reminder_service function."""

    def test_stop_reminder_service_calls_scheduler(self):
        """Test stop_reminder_service calls stop_scheduler."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            stop_reminder_service()
            mock_scheduler.stop_scheduler.assert_called_once()


class TestRegisterSessionNotifications:
    """Tests for register_session_notifications function."""

    def test_register_session_notifications_registers_callback(self):
        """Test register_session_notifications registers callback."""
        import session_buddy.natural_scheduler as ns
        ns._reminder_scheduler = None

        mock_scheduler = MagicMock()
        with patch.object(ns, "get_reminder_scheduler", return_value=mock_scheduler):
            register_session_notifications()
            mock_scheduler.register_notification_callback.assert_called_once()
            args = mock_scheduler.register_notification_callback.call_args
            assert args[0][0] == "session"
            assert asyncio.iscoroutinefunction(args[0][1])


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Edge case tests for various methods."""

    @pytest.mark.asyncio
    async def test_create_reminder_with_none_metadata(self, scheduler, mock_parser):
        """Test create_reminder with None metadata."""
        mock_parser.parse_time_expression.return_value = datetime.now() + timedelta(minutes=30)
        mock_parser.parse_recurrence.return_value = None

        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler.create_reminder(
                    title="Test",
                    time_expression="in 30 minutes",
                    metadata=None,
                )
                assert result is not None

    @pytest.mark.asyncio
    async def test_create_reminder_with_empty_context_triggers(self, scheduler, mock_parser):
        """Test create_reminder with empty context triggers list."""
        mock_parser.parse_time_expression.return_value = datetime.now() + timedelta(minutes=30)
        mock_parser.parse_recurrence.return_value = None

        with patch.object(scheduler, "_log_reminder_action", new_callable=AsyncMock):
            with patch("sqlite3.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_connect.return_value.__exit__ = MagicMock(return_value=None)

                result = await scheduler.create_reminder(
                    title="Test",
                    time_expression="in 30 minutes",
                    context_triggers=[],
                )
                assert result is not None

    def test_register_notification_callback_with_lambda(self, scheduler):
        """Test register_notification_callback with lambda function."""
        callback = lambda x: x
        scheduler.register_notification_callback("test", callback)
        assert "test" in scheduler._callbacks

    @pytest.mark.asyncio
    async def test_execute_reminder_with_missing_keys(self, scheduler):
        """Test execute_reminder when reminder_data has missing keys."""
        incomplete_data = {"reminder_id": "rem_123"}  # Missing most keys

        with patch.object(scheduler, "_get_reminder_by_id", new_callable=AsyncMock, return_value=incomplete_data):
            with patch.object(scheduler, "_execute_notification_callbacks", new_callable=AsyncMock):
                with patch.object(scheduler, "_mark_reminder_executed", new_callable=AsyncMock, return_value=True):
                    result = await scheduler.execute_reminder("rem_123")
                    assert result is True

    def test_parse_recurrence_interval_malformed_input(self, scheduler):
        """Test _parse_recurrence_interval with malformed input."""
        result = scheduler._parse_recurrence_interval("GARBAGE")
        assert result.frequency is None
        assert result.interval == 1

    def test_parse_recurrence_interval_multiple_intervals(self, scheduler):
        """Test _parse_recurrence_interval with multiple INTERVAL values."""
        result = scheduler._parse_recurrence_interval("FREQ=DAILY;INTERVAL=2;INTERVAL=3")
        assert result.frequency == "DAILY"
        assert result.interval == 3  # Last one wins

    def test_calculate_interval_occurrence_unknown_freq(self, scheduler):
        """Test _calculate_interval_occurrence with unknown frequency."""
        last_time = datetime(2024, 1, 1, 9, 0, 0)
        result = scheduler._calculate_interval_occurrence(last_time, "FREQ=UNKNOWN;INTERVAL=1")
        assert result is None