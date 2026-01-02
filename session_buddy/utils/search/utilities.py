"""Utility functions for advanced search.

This module provides helper functions for content processing, time parsing,
and other search-related utilities.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta

from session_buddy.session_types import TimeRange
from session_buddy.utils.regex_patterns import SAFE_PATTERNS


def extract_technical_terms(content: str) -> list[str]:
    """Extract technical terms and patterns from content."""
    terms = []

    # Programming language detection
    lang_pattern_names = [
        "python_code",
        "javascript_code",
        "sql_code",
        "error_keywords",
    ]
    lang_mapping = {
        "python_code": "python",
        "javascript_code": "javascript",
        "sql_code": "sql",
        "error_keywords": "error",
    }

    for pattern_name in lang_pattern_names:
        pattern = SAFE_PATTERNS[pattern_name]
        if pattern.search(content):
            terms.append(lang_mapping[pattern_name])

    # Extract function names
    func_pattern = SAFE_PATTERNS["function_definition"]
    func_matches = func_pattern.findall(content)
    terms.extend([f"function:{func}" for func in func_matches[:5]])  # Limit to 5

    # Extract class names
    class_pattern = SAFE_PATTERNS["class_definition"]
    class_matches = class_pattern.findall(content)
    terms.extend([f"class:{cls}" for cls in class_matches[:5]])

    # Extract file extensions
    ext_pattern = SAFE_PATTERNS["file_extension"]
    file_matches = ext_pattern.findall(content)
    terms.extend([f"filetype:{ext}" for ext in set(file_matches[:10])])

    return terms[:20]  # Limit total terms


def truncate_content(content: str, max_length: int = 500) -> str:
    """Truncate content to maximum length."""
    return content[:max_length] + "..." if len(content) > max_length else content


def ensure_timezone(timestamp: datetime) -> datetime:
    """Ensure timestamp has timezone information."""
    return timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp


def parse_timeframe_single(timeframe: str) -> datetime | None:
    """Parse timeframe string into datetime."""
    with suppress(ValueError):
        if timeframe.endswith("d"):
            days = int(timeframe[:-1])
            return datetime.now(UTC) - timedelta(days=days)
        if timeframe.endswith("h"):
            hours = int(timeframe[:-1])
            return datetime.now(UTC) - timedelta(hours=hours)
        if timeframe.endswith("w"):
            weeks = int(timeframe[:-1])
            return datetime.now(UTC) - timedelta(weeks=weeks)
        if timeframe.endswith("m"):
            months = int(timeframe[:-1])
            return datetime.now(UTC) - timedelta(days=months * 30)
    return None


def parse_timeframe(timeframe: str) -> TimeRange:
    """Parse timeframe string into TimeRange object.

    Supports formats like:
    - '7d' (last 7 days)
    - '2024-01' (specific month)
    - '2024' (specific year)
    - '2024-01-01..2024-01-31' (date range)
    """
    # Range format: 'start..end'
    if ".." in timeframe:
        parts = timeframe.split("..")
        start = datetime.fromisoformat(parts[0]).replace(tzinfo=UTC)
        end = datetime.fromisoformat(parts[1]).replace(tzinfo=UTC)
        return TimeRange(start=start, end=end)

    # Relative timeframe: '7d', '2w', etc.
    if timeframe[-1] in "dhwm":
        end = datetime.now(UTC)
        relative_start: datetime | None = parse_timeframe_single(timeframe)
        if relative_start:
            return TimeRange(start=relative_start, end=end)

    # Year only: '2024'
    if len(timeframe) == 4 and timeframe.isdigit():
        year = int(timeframe)
        start = datetime(year, 1, 1, tzinfo=UTC)
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
        return TimeRange(start=start, end=end)

    # Year-month: '2024-01'
    if len(timeframe) == 7:
        year, month = map(int, timeframe.split("-"))
        start = datetime(year, month, 1, tzinfo=UTC)
        # Calculate next month
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)
        return TimeRange(start=start, end=end)

    # Default: last 7 days
    end = datetime.now(UTC)
    start = end - timedelta(days=7)
    return TimeRange(start=start, end=end)
