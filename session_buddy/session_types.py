"""Type definitions for session management MCP server.

This module provides type-safe dataclass definitions to replace problematic
tuple/union return types that cause issues with type checkers like zuban.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TimeRange:
    """Represents a time range with optional start and end times.

    Used for temporal search and time-based filtering operations.
    """

    start: datetime | None = None
    end: datetime | None = None


@dataclass
class SQLCondition:
    """Represents a SQL condition with WHERE clause and parameters.

    Used for building parameterized SQL queries with type-safe parameter binding.
    """

    condition: str
    params: list[str | datetime]


@dataclass
class RecurrenceInterval:
    """Represents a parsed recurrence interval from a recurrence rule.

    Used for calculating next occurrences of recurring reminders.
    """

    frequency: str | None = None
    interval: int = 1
