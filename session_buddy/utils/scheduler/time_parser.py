"""Natural language time expression parser.

This module provides the NaturalLanguageParser class for parsing
natural language time expressions into datetime objects.
"""

from __future__ import annotations

import contextlib
import re
from datetime import datetime, timedelta
from re import Match
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dateutil import parser as date_parser
    from dateutil.relativedelta import relativedelta

# Try to import dateutil for better date handling
try:
    from dateutil import parser as date_parser
    from dateutil.relativedelta import relativedelta

    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False


class NaturalLanguageParser:
    """Parses natural language time expressions."""

    def __init__(self) -> None:
        """Initialize natural language parser."""
        self.time_patterns = self._create_time_patterns()
        self.recurrence_patterns = self._create_recurrence_patterns()

    def _create_time_patterns(self) -> dict[str, Any]:
        """Create time parsing patterns dictionary."""
        patterns = {}

        # Add relative time patterns
        patterns.update(self._get_relative_time_patterns())

        # Add specific time patterns
        patterns.update(self._get_specific_time_patterns())

        # Add session-relative patterns
        patterns.update(self._get_session_relative_patterns())

        return patterns

    def _get_relative_time_patterns(self) -> dict[str, Any]:
        """Get relative time patterns (in X minutes/hours/days)."""
        return {
            r"in (\d+) (minute|min|minutes|mins)": lambda m: timedelta(
                minutes=int(m.group(1))
            ),
            r"in (\d+) (hour|hours|hr|hrs)": lambda m: timedelta(hours=int(m.group(1))),
            r"in (\d+) (day|days)": lambda m: timedelta(days=int(m.group(1))),
            r"in (\d+) (week|weeks)": lambda m: timedelta(weeks=int(m.group(1))),
            r"in (\d+) (month|months)": self._create_month_handler(),
        }

    def _get_specific_time_patterns(self) -> dict[str, Any]:
        """Get specific time patterns (tomorrow, next monday, etc)."""
        return {
            r"tomorrow( at (\d{1,2}):?(\d{2})?)?(am|pm)?": self._parse_tomorrow,
            r"next (monday|tuesday|wednesday|thursday|friday|saturday|sunday)": self._parse_next_weekday,
            r"at (\d{1,2}):?(\d{2})?\s*(am|pm)?": self._parse_specific_time,
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday) at (\d{1,2}):?(\d{2})?\s*(am|pm)?": self._parse_weekday_time,
        }

    def _get_session_relative_patterns(self) -> dict[str, Any]:
        """Get session-relative time patterns."""
        return {
            r"end of (session|work)": lambda m: timedelta(hours=2),
            r"after (break|lunch)": lambda m: timedelta(hours=1),
            r"before (meeting|call)": lambda m: timedelta(minutes=15),
        }

    def _create_month_handler(self) -> Any:
        """Create month duration handler with dateutil fallback."""
        if DATEUTIL_AVAILABLE:
            return lambda m: relativedelta(months=int(m.group(1)))
        return lambda m: timedelta(days=int(m.group(1)) * 30)

    def _create_recurrence_patterns(self) -> dict[str, Any]:
        """Create recurrence parsing patterns dictionary."""
        return {
            r"every (day|daily)": "FREQ=DAILY",
            r"every (week|weekly)": "FREQ=WEEKLY",
            r"every (month|monthly)": "FREQ=MONTHLY",
            r"every (\d+) (minute|minutes)": lambda m: f"FREQ=MINUTELY;INTERVAL={m.group(1)}",
            r"every (\d+) (hour|hours)": lambda m: f"FREQ=HOURLY;INTERVAL={m.group(1)}",
            r"every (\d+) (day|days)": lambda m: f"FREQ=DAILY;INTERVAL={m.group(1)}",
        }

    def _try_parse_relative_pattern(
        self, expression: str, base_time: datetime, time_patterns: dict[str, Any]
    ) -> datetime | None:
        """Try to parse the expression using relative time patterns."""
        for pattern, handler in time_patterns.items():
            match = self._try_pattern_match(pattern, expression)
            if match:
                result = self._process_pattern_handler(handler, match)
                if result:
                    return self._convert_result_to_datetime(result, base_time)
        return None

    def _try_pattern_match(self, pattern: str, expression: str) -> Match[str] | None:
        """Try to match a pattern against the expression."""
        return re.search(pattern, expression, re.IGNORECASE)  # REGEX OK: Time parsing

    def _process_pattern_handler(self, handler: Any, match: Match[str]) -> Any:
        """Process a pattern handler with exception handling."""
        with contextlib.suppress(TypeError, ValueError, RuntimeError, AttributeError):
            if callable(handler):
                return handler(match)  # type: ignore[no-untyped-call]
        return None

    def _convert_result_to_datetime(
        self, result: Any, base_time: datetime
    ) -> datetime | None:
        """Convert handler result to datetime with base time."""
        if isinstance(result, timedelta):
            return base_time + result
        if isinstance(result, datetime):
            return result
        if hasattr(result, "days") or hasattr(result, "months"):
            return base_time + result  # type: ignore[no-any-return]
        return None

    def _try_parse_absolute_date(
        self, expression: str, base_time: datetime
    ) -> datetime | None:
        """Try to parse the expression using absolute date parsing."""
        if DATEUTIL_AVAILABLE:
            try:
                parsed_date = date_parser.parse(expression, default=base_time)
                # Ensure parsed_date is a datetime object
                if (
                    isinstance(parsed_date, datetime) and parsed_date > base_time
                ):  # Only future dates
                    return datetime(
                        parsed_date.year,
                        parsed_date.month,
                        parsed_date.day,
                        parsed_date.hour,
                        parsed_date.minute,
                        parsed_date.second,
                    )
            except (ValueError, TypeError):
                with contextlib.suppress(ValueError, TypeError):
                    pass
        return None

    def _validate_input(self, expression: str) -> str | None:
        """Validate and normalize input expression."""
        if not expression or not expression.strip():
            return None
        return expression.lower().strip()

    def _try_parsing_strategies(
        self, expression: str, base_time: datetime
    ) -> datetime | None:
        """Try multiple parsing strategies in order."""
        # Strategy 1: Relative patterns
        result = self._try_parse_relative_pattern(
            expression, base_time, self.time_patterns
        )
        if result:
            return result

        # Strategy 2: Absolute date parsing
        result = self._try_parse_absolute_date(expression, base_time)
        if result:
            return result

        return None

    def parse_time_expression(
        self,
        expression: str,
        base_time: datetime | None = None,
    ) -> datetime | None:
        """Parse natural language time expression."""
        normalized_expression = self._validate_input(expression)
        if not normalized_expression:
            return None

        base_time = base_time or datetime.now()
        return self._try_parsing_strategies(normalized_expression, base_time)

    def parse_recurrence(self, expression: str) -> str | None:
        """Parse recurrence pattern from natural language."""
        if not expression:
            return None

        expression = expression.lower().strip()

        for pattern, handler in self.recurrence_patterns.items():
            match = re.search(
                pattern, expression, re.IGNORECASE
            )  # REGEX OK: Recurrence parsing
            if match:
                if callable(handler):
                    result = handler(match)
                    if isinstance(result, str):
                        return result
                elif isinstance(handler, str):
                    return handler

        return None

    def _parse_tomorrow(self, match: Match[str]) -> datetime:
        """Parse 'tomorrow' with optional time."""
        tomorrow = datetime.now() + timedelta(days=1)

        if match.group(2) and match.group(3):  # Has time
            hour = int(match.group(2))
            minute = int(match.group(3))
            am_pm = match.group(4)

            if am_pm and am_pm.lower() == "pm" and hour != 12:
                hour += 12
            elif am_pm and am_pm.lower() == "am" and hour == 12:
                hour = 0

            return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # Default to 9 AM tomorrow
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

    def _parse_next_weekday(self, match: Match[str]) -> datetime:
        """Parse 'next monday', etc."""
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        target_weekday = weekdays[match.group(1)]
        today = datetime.now()
        days_ahead = target_weekday - today.weekday()

        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7

        return today + timedelta(days=days_ahead)

    def _parse_specific_time(self, match: Match[str]) -> datetime:
        """Parse 'at 3:30pm' for today."""
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        am_pm = match.group(3)

        if am_pm and am_pm.lower() == "pm" and hour != 12:
            hour += 12
        elif am_pm and am_pm.lower() == "am" and hour == 12:
            hour = 0

        target_time = datetime.now().replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        # If time has passed today, schedule for tomorrow
        if target_time <= datetime.now():
            target_time += timedelta(days=1)

        return target_time

    def _parse_weekday_time(self, match: Match[str]) -> datetime:
        """Parse 'monday at 3pm'."""
        target_weekday = self._get_weekday_number(match.group(1))
        hour, minute = self._parse_hour_minute(
            match.group(2), match.group(3), match.group(4)
        )

        today = datetime.now()
        days_ahead = self._calculate_days_ahead(target_weekday, today, hour, minute)

        target_date = today + timedelta(days=days_ahead)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _get_weekday_number(self, weekday_name: str) -> int:
        """Get weekday number from name."""
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        return weekdays[weekday_name]

    def _parse_hour_minute(
        self, hour_str: str, minute_str: str | None, am_pm: str | None
    ) -> tuple[int, int]:
        """Parse hour and minute from time components."""
        hour = int(hour_str)
        minute = int(minute_str) if minute_str else 0

        if am_pm and am_pm.lower() == "pm" and hour != 12:
            hour += 12
        elif am_pm and am_pm.lower() == "am" and hour == 12:
            hour = 0

        return hour, minute

    def _calculate_days_ahead(
        self, target_weekday: int, today: datetime, hour: int, minute: int
    ) -> int:
        """Calculate how many days ahead the target weekday is."""
        days_ahead = target_weekday - today.weekday()

        if days_ahead < 0:  # Target day already happened this week
            days_ahead += 7
        elif days_ahead == 0:  # Today - check if time has passed
            target_time = today.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if target_time <= today:
                days_ahead = 7

        return days_ahead
