"""Comprehensive unit tests for ``session_buddy.utils.search.utilities``.

Covers every public function in the standalone module:
- ``extract_technical_terms``
- ``truncate_content``
- ``ensure_timezone``
- ``parse_timeframe_single``
- ``parse_timeframe``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from session_buddy.session_types import TimeRange
from session_buddy.utils.search import utilities
from session_buddy.utils.search.utilities import (
    ensure_timezone,
    extract_technical_terms,
    parse_timeframe,
    parse_timeframe_single,
    truncate_content,
)


# ---------------------------------------------------------------------------
# extract_technical_terms
# ---------------------------------------------------------------------------


class TestExtractTechnicalTerms:
    """Branch coverage for ``extract_technical_terms``."""

    def test_empty_content_returns_empty_list(self) -> None:
        assert extract_technical_terms("") == []

    def test_plain_text_returns_empty_list(self) -> None:
        # No keywords, no functions, no classes, no file extensions match.
        assert extract_technical_terms("just some plain prose here.") == []

    def test_detects_python_keyword(self) -> None:
        assert "python" in extract_technical_terms("def hello(): pass")

    def test_detects_javascript_keyword(self) -> None:
        assert "javascript" in extract_technical_terms("const x = 1")

    def test_detects_sql_keyword(self) -> None:
        assert "sql" in extract_technical_terms("SELECT * FROM users")

    def test_detects_error_keyword(self) -> None:
        assert "error" in extract_technical_terms("ValueError raised")

    def test_detects_multiple_languages(self) -> None:
        text = "def f(): pass\nconst y = 2\nSELECT id FROM t\nTraceback here"
        terms = extract_technical_terms(text)
        for tag in ("python", "javascript", "sql", "error"):
            assert tag in terms, f"expected {tag!r} in {terms}"

    def test_extracts_function_names(self) -> None:
        terms = extract_technical_terms("def my_func(): return 1\ndef other(): pass")
        assert "function:my_func" in terms
        assert "function:other" in terms

    def test_extracts_class_names(self) -> None:
        terms = extract_technical_terms("class MyClass: pass\nclass Other: pass")
        assert "class:MyClass" in terms
        assert "class:Other" in terms

    def test_extracts_file_extensions(self) -> None:
        terms = extract_technical_terms("see config.yaml and main.py")
        assert "filetype:yaml" in terms
        assert "filetype:py" in terms

    def test_file_extensions_deduplicated(self) -> None:
        # Repeated extension appears only once (uses set()).
        text = "a.py b.py c.py d.py e.py"
        terms = extract_technical_terms(text)
        py_terms = [t for t in terms if t == "filetype:py"]
        assert len(py_terms) == 1

    def test_function_match_capped_at_five(self) -> None:
        text = "\n".join(f"def func_{i}(): pass" for i in range(10))
        terms = extract_technical_terms(text)
        func_terms = [t for t in terms if t.startswith("function:")]
        assert len(func_terms) == 5

    def test_class_match_capped_at_five(self) -> None:
        text = "\n".join(f"class Cls_{i}: pass" for i in range(10))
        terms = extract_technical_terms(text)
        class_terms = [t for t in terms if t.startswith("class:")]
        assert len(class_terms) == 5

    def test_total_terms_capped_at_twenty(self) -> None:
        # Stuff that exceeds the global cap: many functions + extensions + langs.
        many_funcs = "\n".join(f"def f{i}(): pass" for i in range(20))
        exts = " ".join(f"f{i}.py" for i in range(20))
        terms = extract_technical_terms(f"{many_funcs} {exts}")
        assert len(terms) <= 20

    def test_returns_list_of_strings(self) -> None:
        terms = extract_technical_terms("def go(): pass")
        assert isinstance(terms, list)
        for term in terms:
            assert isinstance(term, str)


# ---------------------------------------------------------------------------
# truncate_content
# ---------------------------------------------------------------------------


class TestTruncateContent:
    """Branch coverage for ``truncate_content``."""

    def test_content_shorter_than_max_returned_unchanged(self) -> None:
        assert truncate_content("hello", max_length=500) == "hello"

    def test_content_equal_to_max_returned_unchanged(self) -> None:
        text = "a" * 500
        # len == max_length means the slice is the whole string, no ellipsis.
        assert truncate_content(text, max_length=500) == text

    def test_content_longer_than_max_is_truncated_with_ellipsis(self) -> None:
        text = "a" * 600
        result = truncate_content(text, max_length=500)
        assert result == "a" * 500 + "..."
        assert len(result) == 503

    def test_custom_max_length_respected(self) -> None:
        assert truncate_content("abcdefghij", max_length=5) == "abcde..."

    def test_max_length_one_returns_first_char_plus_ellipsis(self) -> None:
        # Boundary: every string longer than 1 char gets truncated.
        assert truncate_content("xy", max_length=1) == "x..."

    def test_default_max_length_is_500(self) -> None:
        # Default kwarg sanity: long content with no max_length argument truncates.
        text = "x" * 501
        assert truncate_content(text) == "x" * 500 + "..."

    def test_empty_string_returned_unchanged(self) -> None:
        assert truncate_content("", max_length=10) == ""


# ---------------------------------------------------------------------------
# ensure_timezone
# ---------------------------------------------------------------------------


class TestEnsureTimezone:
    """Branch coverage for ``ensure_timezone``."""

    def test_naive_datetime_gets_utc_tzinfo(self) -> None:
        naive = datetime(2024, 6, 1, 12, 0, 0)
        result = ensure_timezone(naive)
        assert result.tzinfo is UTC
        assert result == datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

    def test_aware_datetime_returned_unchanged(self) -> None:
        aware = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = ensure_timezone(aware)
        # Same object back — branch returns the input as-is.
        assert result is aware

    def test_aware_datetime_with_different_tz_preserved(self) -> None:
        other_tz = timezone(timedelta(hours=-5))
        aware = datetime(2024, 6, 1, 12, 0, 0, tzinfo=other_tz)
        result = ensure_timezone(aware)
        assert result.tzinfo is other_tz
        # Wall-clock values must not be mutated.
        assert result.year == 2024 and result.hour == 12

    def test_naive_datetime_at_microsecond_precision(self) -> None:
        naive = datetime(2024, 1, 1, 0, 0, 0, 123456)
        result = ensure_timezone(naive)
        assert result.microsecond == 123456
        assert result.tzinfo is UTC


# ---------------------------------------------------------------------------
# parse_timeframe_single
# ---------------------------------------------------------------------------


class TestParseTimeframeSingle:
    """Branch coverage for ``parse_timeframe_single``."""

    @pytest.mark.parametrize(
        "timeframe",
        ["7d", "30d", "1d", "365d"],
    )
    def test_days_format(self, timeframe: str) -> None:
        before = datetime.now(UTC)
        result = parse_timeframe_single(timeframe)
        after = datetime.now(UTC)
        assert result is not None
        days = int(timeframe[:-1])
        expected_min = before - timedelta(days=days)
        expected_max = after - timedelta(days=days)
        assert expected_min <= result <= expected_max

    @pytest.mark.parametrize(
        "timeframe",
        ["1h", "12h", "48h"],
    )
    def test_hours_format(self, timeframe: str) -> None:
        before = datetime.now(UTC)
        result = parse_timeframe_single(timeframe)
        after = datetime.now(UTC)
        assert result is not None
        hours = int(timeframe[:-1])
        expected_min = before - timedelta(hours=hours)
        expected_max = after - timedelta(hours=hours)
        assert expected_min <= result <= expected_max

    @pytest.mark.parametrize(
        "timeframe",
        ["1w", "2w", "4w"],
    )
    def test_weeks_format(self, timeframe: str) -> None:
        before = datetime.now(UTC)
        result = parse_timeframe_single(timeframe)
        after = datetime.now(UTC)
        assert result is not None
        weeks = int(timeframe[:-1])
        expected_min = before - timedelta(weeks=weeks)
        expected_max = after - timedelta(weeks=weeks)
        assert expected_min <= result <= expected_max

    @pytest.mark.parametrize(
        "timeframe",
        ["1m", "6m", "12m"],
    )
    def test_months_format_uses_30_day_approximation(self, timeframe: str) -> None:
        before = datetime.now(UTC)
        result = parse_timeframe_single(timeframe)
        after = datetime.now(UTC)
        assert result is not None
        months = int(timeframe[:-1])
        # Implementation treats 'm' as months * 30 days.
        expected_min = before - timedelta(days=months * 30)
        expected_max = after - timedelta(days=months * 30)
        assert expected_min <= result <= expected_max

    def test_zero_days_returns_essentially_now(self) -> None:
        before = datetime.now(UTC)
        result = parse_timeframe_single("0d")
        after = datetime.now(UTC)
        assert result is not None
        # 0-day window — result must fall between the two wall-clock reads.
        assert before <= result <= after

    @pytest.mark.parametrize(
        "timeframe",
        [
            "",  # Empty
            "abc",  # Garbage
            "7",  # Missing unit suffix
            "7x",  # Unsupported suffix
            "d",  # Just unit, no number
            "7days",  # Long form not supported
        ],
    )
    def test_invalid_timeframe_returns_none(self, timeframe: str) -> None:
        assert parse_timeframe_single(timeframe) is None

    def test_valueerror_on_non_integer_returns_none(self) -> None:
        # int("abc") raises ValueError; suppress swallows it -> None.
        assert parse_timeframe_single("abcd") is None


# ---------------------------------------------------------------------------
# parse_timeframe
# ---------------------------------------------------------------------------


class TestParseTimeframe:
    """Branch coverage for ``parse_timeframe``."""

    def test_range_format_returns_time_range(self) -> None:
        result = parse_timeframe("2024-01-01..2024-01-31")
        assert isinstance(result, TimeRange)
        assert result.start == datetime(2024, 1, 1, tzinfo=UTC)
        assert result.end == datetime(2024, 1, 31, tzinfo=UTC)

    def test_range_format_tzinfo_always_utc(self) -> None:
        result = parse_timeframe("2024-06-01T12:00:00..2024-06-30T12:00:00")
        assert result.start.tzinfo is UTC
        assert result.end.tzinfo is UTC

    @pytest.mark.parametrize(
        "timeframe",
        ["7d", "24h", "2w", "3m"],
    )
    def test_relative_format_dh(self, timeframe: str) -> None:
        before = datetime.now(UTC)
        result = parse_timeframe(timeframe)
        after = datetime.now(UTC)
        assert isinstance(result, TimeRange)
        assert before <= result.end <= after
        # End must be at-or-after start (start is in the past for relative).
        assert result.start <= result.end

    def test_year_only_format(self) -> None:
        result = parse_timeframe("2024")
        assert isinstance(result, TimeRange)
        assert result.start == datetime(2024, 1, 1, tzinfo=UTC)
        # End is exclusive — start of next year.
        assert result.end == datetime(2025, 1, 1, tzinfo=UTC)

    def test_year_month_format_regular_month(self) -> None:
        result = parse_timeframe("2024-06")
        assert isinstance(result, TimeRange)
        assert result.start == datetime(2024, 6, 1, tzinfo=UTC)
        assert result.end == datetime(2024, 7, 1, tzinfo=UTC)

    def test_year_month_format_december_wraps_year(self) -> None:
        # December branch: month+1 wraps to January of the following year.
        result = parse_timeframe("2024-12")
        assert isinstance(result, TimeRange)
        assert result.start == datetime(2024, 12, 1, tzinfo=UTC)
        assert result.end == datetime(2025, 1, 1, tzinfo=UTC)

    def test_year_month_invalid_returns_default_7_day_range(self) -> None:
        # "2024-99" — month 99 invalid; suppress(ValueError) swallows the
        # int() failure and execution falls through to the default branch.
        before = datetime.now(UTC)
        result = parse_timeframe("2024-99")
        after = datetime.now(UTC)
        assert isinstance(result, TimeRange)
        # Default branch returns last-7-days.
        assert before - timedelta(days=8) <= result.start <= before - timedelta(days=6)
        assert before <= result.end <= after

    def test_unknown_string_falls_back_to_seven_day_default(self) -> None:
        before = datetime.now(UTC)
        result = parse_timeframe("not-a-timeframe")
        after = datetime.now(UTC)
        assert isinstance(result, TimeRange)
        assert before - timedelta(days=8) <= result.start <= before - timedelta(days=6)
        assert before <= result.end <= after

    def test_empty_string_returns_default_seven_day_range(self) -> None:
        # After the production fix: an empty string skips the relative-time
        # branch (`timeframe[-1]` guarded by truthy check) and falls through
        # to the default "last 7 days" range.
        before = datetime.now(UTC)
        result = parse_timeframe("")
        after = datetime.now(UTC)
        assert isinstance(result, TimeRange)
        # Default window — both ends fall in the 7-day-ago..now range.
        assert before - timedelta(days=8) <= result.start <= before - timedelta(days=6)
        assert before <= result.end <= after

    def test_range_with_invalid_iso_falls_through(self) -> None:
        # First part of the range is not ISO parseable; ValueError propagates
        # out of fromisoformat (no suppress wrapper here) — caller would
        # observe the exception, which is the documented contract.
        with pytest.raises(ValueError):
            parse_timeframe("garbage..2024-01-31")
