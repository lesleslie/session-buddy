"""Unit tests for search utilities module.

Tests functions in session_buddy.utils.search.utilities:
- extract_technical_terms
- truncate_content
- ensure_timezone
- parse_timeframe_single
- parse_timeframe
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


class TestExtractTechnicalTerms:
    """Tests for extract_technical_terms function."""

    def test_extract_python_code(self):
        """Test extraction of Python code patterns."""
        from session_buddy.utils.search.utilities import extract_technical_terms

        content = """
        def calculate_sum(a: int, b: int) -> int:
            return a + b

        class DataProcessor:
            pass
        """
        terms = extract_technical_terms(content)

        assert "python" in terms
        assert any("function:calculate_sum" in t for t in terms)
        assert any("class:DataProcessor" in t for t in terms)

    def test_extract_javascript_code(self):
        """Test extraction of JavaScript patterns."""
        from session_buddy.utils.search.utilities import extract_technical_terms

        content = """
        function hello() {
            console.log("Hello");
        }

        const foo = require('bar');
        """
        terms = extract_technical_terms(content)

        assert "javascript" in terms

    def test_extract_sql_code(self):
        """Test extraction of SQL patterns."""
        from session_buddy.utils.search.utilities import extract_technical_terms

        content = "SELECT * FROM users WHERE id = 1"
        terms = extract_technical_terms(content)

        assert "sql" in terms

    def test_extract_file_extensions(self):
        """Test extraction of file extensions."""
        from session_buddy.utils.search.utilities import extract_technical_terms

        content = """
        import os
        from pathlib import Path

        def read_file():
            with open("test.py", "r") as f:
                return f.read()
        """
        terms = extract_technical_terms(content)

        # Should detect file extensions
        ext_terms = [t for t in terms if t.startswith("filetype:")]
        assert any("py" in t for t in ext_terms)

    def test_extract_no_code(self):
        """Test extraction with no code patterns."""
        from session_buddy.utils.search.utilities import extract_technical_terms

        content = "This is plain text without any code patterns"
        terms = extract_technical_terms(content)

        # Should not have many terms
        assert len(terms) <= 20

    def test_extract_term_limit(self):
        """Test that terms are limited to 20."""
        from session_buddy.utils.search.utilities import extract_technical_terms

        content = """
        class Class1: pass
        class Class2: pass
        class Class3: pass
        class Class4: pass
        class Class5: pass
        class Class6: pass
        class Class7: pass
        class Class8: pass
        class Class9: pass
        class Class10: pass
        """
        terms = extract_technical_terms(content)

        assert len(terms) <= 20


class TestTruncateContent:
    """Tests for truncate_content function."""

    def test_truncate_short_content(self):
        """Test truncation of short content."""
        from session_buddy.utils.search.utilities import truncate_content

        content = "short text"
        result = truncate_content(content, max_length=100)

        assert result == content
        assert "..." not in result

    def test_truncate_long_content(self):
        """Test truncation of long content."""
        from session_buddy.utils.search.utilities import truncate_content

        content = "a" * 600
        result = truncate_content(content, max_length=500)

        assert result.endswith("...")
        assert len(result) == 503  # 500 + "..."

    def test_truncate_at_exact_length(self):
        """Test truncation when content equals max_length."""
        from session_buddy.utils.search.utilities import truncate_content

        content = "a" * 500
        result = truncate_content(content, max_length=500)

        assert result == content

    def test_truncate_custom_max_length(self):
        """Test truncation with custom max_length."""
        from session_buddy.utils.search.utilities import truncate_content

        content = "hello world test"
        result = truncate_content(content, max_length=5)

        assert result == "hello..."
        assert len(result) == 8


class TestEnsureTimezone:
    """Tests for ensure_timezone function."""

    def test_ensure_timezone_naive(self):
        """Test adding timezone to naive datetime."""
        from session_buddy.utils.search.utilities import ensure_timezone

        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        result = ensure_timezone(naive_dt)

        assert result.tzinfo == UTC

    def test_ensure_timezone_aware(self):
        """Test that aware datetime is unchanged."""
        from session_buddy.utils.search.utilities import ensure_timezone

        aware_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = ensure_timezone(aware_dt)

        assert result == aware_dt

    def test_ensure_timezone_preserves_time(self):
        """Test that time values are preserved."""
        from session_buddy.utils.search.utilities import ensure_timezone

        naive_dt = datetime(2024, 6, 15, 14, 30, 45)
        result = ensure_timezone(naive_dt)

        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45


class TestParseTimeframeSingle:
    """Tests for parse_timeframe_single function."""

    def test_parse_days(self):
        """Test parsing days timeframe."""
        from session_buddy.utils.search.utilities import parse_timeframe_single

        result = parse_timeframe_single("7d")
        assert result is not None

        # Should be approximately 7 days ago
        now = datetime.now(UTC)
        diff = now - result
        assert 6 <= diff.days <= 7

    def test_parse_hours(self):
        """Test parsing hours timeframe."""
        from session_buddy.utils.search.utilities import parse_timeframe_single

        result = parse_timeframe_single("3h")
        assert result is not None

        now = datetime.now(UTC)
        diff = now - result
        assert diff.total_seconds() >= 3 * 3600 - 60  # 3 hours minus 1 minute margin
        assert diff.total_seconds() <= 3 * 3600 + 60  # 3 hours plus 1 minute margin

    def test_parse_weeks(self):
        """Test parsing weeks timeframe."""
        from session_buddy.utils.search.utilities import parse_timeframe_single

        result = parse_timeframe_single("2w")
        assert result is not None

        now = datetime.now(UTC)
        diff = now - result
        assert 13 <= diff.days <= 15  # ~2 weeks

    def test_parse_months(self):
        """Test parsing months timeframe."""
        from session_buddy.utils.search.utilities import parse_timeframe_single

        result = parse_timeframe_single("3m")
        assert result is not None

        now = datetime.now(UTC)
        diff = now - result
        assert diff.days >= 85  # ~3 months (30 days each)

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        from session_buddy.utils.search.utilities import parse_timeframe_single

        result = parse_timeframe_single("invalid")
        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        from session_buddy.utils.search.utilities import parse_timeframe_single

        result = parse_timeframe_single("")
        assert result is None


class TestParseTimeframe:
    """Tests for parse_timeframe function."""

    def test_parse_range_format(self):
        """Test parsing date range format."""
        from session_buddy.utils.search.utilities import parse_timeframe

        result = parse_timeframe("2024-01-01..2024-01-31")

        assert result.start.year == 2024
        assert result.start.month == 1
        assert result.start.day == 1
        assert result.end.month == 1
        assert result.end.day == 31

    def test_parse_relative_days(self):
        """Test parsing relative days format."""
        from session_buddy.utils.search.utilities import parse_timeframe

        result = parse_timeframe("7d")

        assert result.start < result.end
        diff = result.end - result.start
        assert 6 <= diff.days <= 7

    def test_parse_year_only(self):
        """Test parsing year only format."""
        from session_buddy.utils.search.utilities import parse_timeframe

        result = parse_timeframe("2024")

        assert result.start.year == 2024
        assert result.start.month == 1
        assert result.start.day == 1
        assert result.end.year == 2025

    def test_parse_year_month(self):
        """Test parsing year-month format."""
        from session_buddy.utils.search.utilities import parse_timeframe

        result = parse_timeframe("2024-03")

        assert result.start.year == 2024
        assert result.start.month == 3
        assert result.start.day == 1
        assert result.end.month == 4
        assert result.end.day == 1

    def test_parse_year_month_december(self):
        """Test parsing December correctly."""
        from session_buddy.utils.search.utilities import parse_timeframe

        result = parse_timeframe("2024-12")

        assert result.start.year == 2024
        assert result.start.month == 12
        assert result.start.day == 1
        assert result.end.year == 2025
        assert result.end.month == 1

    def test_parse_default_fallback(self):
        """Test default fallback to 7 days."""
        from session_buddy.utils.search.utilities import parse_timeframe

        result = parse_timeframe("unknown")

        assert result.start < result.end
        diff = result.end - result.start
        assert diff.days == 7


class TestTimeRangeIntegration:
    """Integration tests for TimeRange usage."""

    def test_time_range_creation(self):
        """Test TimeRange object creation."""
        from session_buddy.session_types import TimeRange

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        time_range = TimeRange(start=start, end=end)

        assert time_range.start == start
        assert time_range.end == end

    def test_parse_timeframe_returns_time_range(self):
        """Test that parse_timeframe returns TimeRange."""
        from session_buddy.session_types import TimeRange
        from session_buddy.utils.search.utilities import parse_timeframe

        result = parse_timeframe("2024-01")

        assert isinstance(result, TimeRange)