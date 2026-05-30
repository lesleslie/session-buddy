"""Unit tests for search utilities module."""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _ensure_package(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


PROJECT_ROOT = Path(__file__).resolve().parents[2]

_ensure_package("session_buddy")
di_stub = types.ModuleType("session_buddy.di")
di_stub._configured = False


class _SessionPaths:
    pass


di_stub.SessionPaths = _SessionPaths
sys.modules["session_buddy.di"] = di_stub
_ensure_package("session_buddy.utils")
_ensure_package("session_buddy.utils.search")

session_types = _load_module(
    "session_buddy.session_types",
    PROJECT_ROOT / "session_buddy" / "session_types.py",
)

regex_stub = types.ModuleType("session_buddy.utils.regex_patterns")
regex_stub.SAFE_PATTERNS = {
    "python_code": re.compile(r"\bdef\s+[A-Za-z_]\w*\b"),
    "javascript_code": re.compile(r"\bfunction\b|\brequire\s*\("),
    "sql_code": re.compile(r"\bSELECT\b", re.IGNORECASE),
    "error_keywords": re.compile(r"\b(?:Error|Exception|Traceback)\b"),
    "function_definition": re.compile(r"\bdef\s+([A-Za-z_]\w*)"),
    "class_definition": re.compile(r"\bclass\s+([A-Za-z_]\w*)"),
    "file_extension": re.compile(r"\.([A-Za-z0-9]{1,10})\b"),
}
sys.modules["session_buddy.utils.regex_patterns"] = regex_stub

utilities = _load_module(
    "session_buddy.utils.search.utilities",
    PROJECT_ROOT / "session_buddy" / "utils" / "search" / "utilities.py",
)

extract_technical_terms = utilities.extract_technical_terms
truncate_content = utilities.truncate_content
ensure_timezone = utilities.ensure_timezone
parse_timeframe_single = utilities.parse_timeframe_single
parse_timeframe = utilities.parse_timeframe
TimeRange = session_types.TimeRange


class TestExtractTechnicalTerms:
    """Tests for extract_technical_terms function."""

    def test_extract_python_code(self):
        """Test extraction of Python code patterns."""
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
        content = "SELECT * FROM users WHERE id = 1"
        terms = extract_technical_terms(content)

        assert "sql" in terms

    def test_extract_file_extensions(self):
        """Test extraction of file extensions."""
        content = """
        import os
        from pathlib import Path

        def read_file():
            with open("test.py", "r") as f:
                return f.read()
        """
        terms = extract_technical_terms(content)

        ext_terms = [t for t in terms if t.startswith("filetype:")]
        assert any("py" in t for t in ext_terms)

    def test_extract_no_code(self):
        """Test extraction with no code patterns."""
        content = "This is plain text without any code patterns"
        terms = extract_technical_terms(content)

        assert len(terms) <= 20

    def test_extract_term_limit(self):
        """Test that terms are limited to 20."""
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
        content = "short text"
        result = truncate_content(content, max_length=100)

        assert result == content
        assert "..." not in result

    def test_truncate_long_content(self):
        """Test truncation of long content."""
        content = "a" * 600
        result = truncate_content(content, max_length=500)

        assert result.endswith("...")
        assert len(result) == 503

    def test_truncate_at_exact_length(self):
        """Test truncation when content equals max_length."""
        content = "a" * 500
        result = truncate_content(content, max_length=500)

        assert result == content

    def test_truncate_custom_max_length(self):
        """Test truncation with custom max_length."""
        content = "hello world test"
        result = truncate_content(content, max_length=5)

        assert result == "hello..."
        assert len(result) == 8


class TestEnsureTimezone:
    """Tests for ensure_timezone function."""

    def test_ensure_timezone_naive(self):
        """Test adding timezone to naive datetime."""
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        result = ensure_timezone(naive_dt)

        assert result.tzinfo == UTC

    def test_ensure_timezone_aware(self):
        """Test that aware datetime is unchanged."""
        aware_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = ensure_timezone(aware_dt)

        assert result == aware_dt

    def test_ensure_timezone_preserves_time(self):
        """Test that time values are preserved."""
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
        result = parse_timeframe_single("7d")
        assert result is not None

        now = datetime.now(UTC)
        diff = now - result
        assert 6 <= diff.days <= 7

    def test_parse_hours(self):
        """Test parsing hours timeframe."""
        result = parse_timeframe_single("3h")
        assert result is not None

        now = datetime.now(UTC)
        diff = now - result
        assert diff.total_seconds() >= 3 * 3600 - 60
        assert diff.total_seconds() <= 3 * 3600 + 60

    def test_parse_weeks(self):
        """Test parsing weeks timeframe."""
        result = parse_timeframe_single("2w")
        assert result is not None

        now = datetime.now(UTC)
        diff = now - result
        assert 13 <= diff.days <= 15

    def test_parse_months(self):
        """Test parsing months timeframe."""
        result = parse_timeframe_single("3m")
        assert result is not None

        now = datetime.now(UTC)
        diff = now - result
        assert diff.days >= 85

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        result = parse_timeframe_single("invalid")
        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_timeframe_single("")
        assert result is None


class TestParseTimeframe:
    """Tests for parse_timeframe function."""

    def test_parse_range_format(self):
        """Test parsing date range format."""
        result = parse_timeframe("2024-01-01..2024-01-31")

        assert result.start.year == 2024
        assert result.start.month == 1
        assert result.start.day == 1
        assert result.end.month == 1
        assert result.end.day == 31

    def test_parse_relative_days(self):
        """Test parsing relative days format."""
        result = parse_timeframe("7d")

        assert result.start < result.end
        diff = result.end - result.start
        assert 6 <= diff.days <= 7

    def test_parse_year_only(self):
        """Test parsing year only format."""
        result = parse_timeframe("2024")

        assert result.start.year == 2024
        assert result.start.month == 1
        assert result.start.day == 1
        assert result.end.year == 2025

    def test_parse_year_month(self):
        """Test parsing year-month format."""
        result = parse_timeframe("2024-03")

        assert result.start.year == 2024
        assert result.start.month == 3
        assert result.start.day == 1
        assert result.end.month == 4
        assert result.end.day == 1

    def test_parse_year_month_december(self):
        """Test parsing December correctly."""
        result = parse_timeframe("2024-12")

        assert result.start.year == 2024
        assert result.start.month == 12
        assert result.start.day == 1
        assert result.end.year == 2025
        assert result.end.month == 1

    def test_parse_invalid_year_month_fallback(self):
        """Test invalid year-month strings fall back to the default range."""
        result = parse_timeframe("2024-13")

        assert result.start < result.end
        diff = result.end - result.start
        assert diff.days == 7

    def test_parse_default_fallback(self):
        """Test default fallback to 7 days."""
        result = parse_timeframe("unknown")

        assert result.start < result.end
        diff = result.end - result.start
        assert diff.days == 7


class TestTimeRangeIntegration:
    """Integration tests for TimeRange usage."""

    def test_time_range_creation(self):
        """Test TimeRange object creation."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        time_range = TimeRange(start=start, end=end)

        assert time_range.start == start
        assert time_range.end == end

    def test_parse_timeframe_returns_time_range(self):
        """Test that parse_timeframe returns TimeRange."""
        result = parse_timeframe("2024-01")

        assert isinstance(result, TimeRange)
