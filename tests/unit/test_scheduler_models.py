"""Unit tests for utils.scheduler.models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from session_buddy.utils.scheduler.models import (
    NaturalReminder,
    ReminderStatus,
    ReminderType,
    SchedulingContext,
)


class TestReminderType:
    """Tests for ReminderType enum."""

    def test_all_values_exist(self):
        """Verify all expected reminder types are defined."""
        assert hasattr(ReminderType, "TASK")
        assert hasattr(ReminderType, "DEADLINE")
        assert hasattr(ReminderType, "RECURRING")
        assert hasattr(ReminderType, "SESSION_RELATIVE")

    def test_value_strings(self):
        """Verify enum values have correct string representations."""
        assert ReminderType.TASK.value == "task"
        assert ReminderType.DEADLINE.value == "deadline"
        assert ReminderType.RECURRING.value == "recurring"
        assert ReminderType.SESSION_RELATIVE.value == "session_relative"

    def test_enum_is_iterable(self):
        """Verify we can iterate over all enum members."""
        members = list(ReminderType)
        assert len(members) == 4
        assert ReminderType.TASK in members
        assert ReminderType.DEADLINE in members
        assert ReminderType.RECURRING in members
        assert ReminderType.SESSION_RELATIVE in members


class TestReminderStatus:
    """Tests for ReminderStatus enum."""

    def test_all_values_exist(self):
        """Verify all expected reminder statuses are defined."""
        assert hasattr(ReminderStatus, "PENDING")
        assert hasattr(ReminderStatus, "EXECUTED")
        assert hasattr(ReminderStatus, "CANCELLED")
        assert hasattr(ReminderStatus, "FAILED")
        assert hasattr(ReminderStatus, "EXPIRED")

    def test_value_strings(self):
        """Verify enum values have correct string representations."""
        assert ReminderStatus.PENDING.value == "pending"
        assert ReminderStatus.EXECUTED.value == "executed"
        assert ReminderStatus.CANCELLED.value == "cancelled"
        assert ReminderStatus.FAILED.value == "failed"
        assert ReminderStatus.EXPIRED.value == "expired"

    def test_enum_is_iterable(self):
        """Verify we can iterate over all enum members."""
        members = list(ReminderStatus)
        assert len(members) == 5
        assert ReminderStatus.PENDING in members
        assert ReminderStatus.EXECUTED in members
        assert ReminderStatus.CANCELLED in members
        assert ReminderStatus.FAILED in members
        assert ReminderStatus.EXPIRED in members


class TestNaturalReminder:
    """Tests for NaturalReminder dataclass."""

    def test_default_values(self):
        """Verify default values for optional fields."""
        now = datetime.now()
        reminder = NaturalReminder(
            reminder_id="test-123",
            reminder_type=ReminderType.TASK,
            expression="do something",
            scheduled_time=now,
            action="notify",
        )

        assert reminder.reminder_id == "test-123"
        assert reminder.reminder_type == ReminderType.TASK
        assert reminder.expression == "do something"
        assert reminder.scheduled_time == now
        assert reminder.action == "notify"
        assert reminder.status == ReminderStatus.PENDING  # default
        assert reminder.created_at is not None
        assert reminder.executed_at is None  # default
        assert reminder.failure_reason is None  # default
        assert reminder.recurrence_pattern is None  # default
        assert reminder.metadata == {}  # default

    def test_all_fields_populated(self):
        """Verify all fields can be set with custom values."""
        now = datetime.now()
        executed = datetime.now()
        reminder = NaturalReminder(
            reminder_id="test-456",
            reminder_type=ReminderType.RECURRING,
            expression="every day",
            scheduled_time=now,
            action="email",
            status=ReminderStatus.EXECUTED,
            created_at=now,
            executed_at=executed,
            failure_reason=None,
            recurrence_pattern="0 9 * * *",
            metadata={"key": "value"},
        )

        assert reminder.reminder_id == "test-456"
        assert reminder.reminder_type == ReminderType.RECURRING
        assert reminder.expression == "every day"
        assert reminder.scheduled_time == now
        assert reminder.action == "email"
        assert reminder.status == ReminderStatus.EXECUTED
        assert reminder.created_at == now
        assert reminder.executed_at == executed
        assert reminder.failure_reason is None
        assert reminder.recurrence_pattern == "0 9 * * *"
        assert reminder.metadata == {"key": "value"}

    def test_failure_reason_set(self):
        """Verify failure_reason can be set for failed reminders."""
        reminder = NaturalReminder(
            reminder_id="test-fail",
            reminder_type=ReminderType.DEADLINE,
            expression="overdue task",
            scheduled_time=datetime.now(),
            action="alert",
            status=ReminderStatus.FAILED,
            failure_reason="SMTP connection refused",
        )

        assert reminder.status == ReminderStatus.FAILED
        assert reminder.failure_reason == "SMTP connection refused"

    def test_metadata_can_store_complex_data(self):
        """Verify metadata can store nested dictionaries."""
        complex_metadata = {
            "user_id": "user-789",
            "priority": 1,
            "tags": ["work", "urgent"],
            "nested": {"level": 2, "items": [1, 2, 3]},
        }

        reminder = NaturalReminder(
            reminder_id="test-meta",
            reminder_type=ReminderType.TASK,
            expression="complex task",
            scheduled_time=datetime.now(),
            action="slack",
            metadata=complex_metadata,
        )

        assert reminder.metadata == complex_metadata
        assert reminder.metadata["nested"]["level"] == 2


class TestSchedulingContext:
    """Tests for SchedulingContext dataclass."""

    def test_default_values(self):
        """Verify default values for all optional fields."""
        ctx = SchedulingContext()

        assert ctx.session_start is None
        assert ctx.session_end is None
        assert ctx.current_task is None
        assert ctx.project is None
        assert ctx.metadata == {}

    def test_all_fields_populated(self):
        """Verify all fields can be set with custom values."""
        now = datetime.now()
        later = datetime.now()
        ctx = SchedulingContext(
            session_start=now,
            session_end=later,
            current_task="writing tests",
            project="session-buddy",
            metadata={"env": "test"},
        )

        assert ctx.session_start == now
        assert ctx.session_end == later
        assert ctx.current_task == "writing tests"
        assert ctx.project == "session-buddy"
        assert ctx.metadata == {"env": "test"}

    def test_metadata_empty_dict_default(self):
        """Verify metadata defaults to empty dict, not None."""
        ctx = SchedulingContext()
        assert ctx.metadata is not None
        assert ctx.metadata == {}

    def test_partial_initialization(self):
        """Verify partial initialization works with only some fields."""
        now = datetime.now()
        ctx = SchedulingContext(
            session_start=now,
            current_task="coding",
        )

        assert ctx.session_start == now
        assert ctx.session_end is None
        assert ctx.current_task == "coding"
        assert ctx.project is None
        assert ctx.metadata == {}