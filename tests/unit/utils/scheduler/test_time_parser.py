"""Comprehensive unit tests for NaturalLanguageParser.

Targets line coverage >=95% and branch coverage >=90% on
``session_buddy/utils/scheduler/time_parser.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from session_buddy.utils.scheduler import time_parser
from session_buddy.utils.scheduler.time_parser import NaturalLanguageParser


def test_smoke_and_constants() -> None:
    parser = NaturalLanguageParser()
    assert parser is not None and isinstance(parser.time_patterns, dict)
    assert isinstance(parser.recurrence_patterns, dict)
    assert isinstance(time_parser.DATEUTIL_AVAILABLE, bool)


def test_pattern_dicts_structure() -> None:
    p = NaturalLanguageParser()
    for k, v in p.time_patterns.items():
        assert isinstance(k, str) and callable(v)
    assert "every (day|daily)" in p.recurrence_patterns
    assert "every (week|weekly)" in p.recurrence_patterns
    assert "every (month|monthly)" in p.recurrence_patterns


@pytest.mark.parametrize(
    ("pat", "expr", "expected"),
    [
        (r"in (\d+) (minute|min|minutes|mins)", "in 5 minutes", timedelta(minutes=5)),
        (r"in (\d+) (minute|min|minutes|mins)", "in 5 min", timedelta(minutes=5)),
        (r"in (\d+) (hour|hours|hr|hrs)", "in 2 hours", timedelta(hours=2)),
        (r"in (\d+) (hour|hours|hr|hrs)", "in 3 hr", timedelta(hours=3)),
        (r"in (\d+) (day|days)", "in 5 days", timedelta(days=5)),
        (r"in (\d+) (week|weeks)", "in 2 weeks", timedelta(weeks=2)),
        (r"end of (session|work)", "end of session", timedelta(hours=2)),
        (r"end of (session|work)", "end of work", timedelta(hours=2)),
        (r"after (break|lunch)", "after break", timedelta(hours=1)),
        (r"after (break|lunch)", "after lunch", timedelta(hours=1)),
        (r"before (meeting|call)", "before meeting", timedelta(minutes=15)),
        (r"before (meeting|call)", "before call", timedelta(minutes=15)),
    ],
)
def test_relative_time_handlers(pat: str, expr: str, expected: timedelta) -> None:
    p = NaturalLanguageParser()
    match = p._try_pattern_match(pat, expr)
    assert match is not None and p.time_patterns[pat](match) == expected


def test_month_handler_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", False)
    p = NaturalLanguageParser()
    handler = p.time_patterns[r"in (\d+) (month|months)"]
    match = p._try_pattern_match(r"in (\d+) (month|months)", "in 3 months")
    assert match is not None and handler(match) == timedelta(days=3 * 30)


def test_month_handler_relativedelta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", True)
    p = NaturalLanguageParser()
    handler = p.time_patterns[r"in (\d+) (month|months)"]
    match = p._try_pattern_match(r"in (\d+) (month|months)", "in 3 months")
    assert match is not None
    result = handler(match)
    assert hasattr(result, "months") and result.months == 3


@pytest.mark.parametrize(
    ("pat", "expr", "expected"),
    [
        (
            r"every (\d+) (minute|minutes)",
            "every 15 minutes",
            "FREQ=MINUTELY;INTERVAL=15",
        ),
        (r"every (\d+) (hour|hours)", "every 2 hours", "FREQ=HOURLY;INTERVAL=2"),
        (r"every (\d+) (day|days)", "every 3 days", "FREQ=DAILY;INTERVAL=3"),
    ],
)
def test_recurrence_callable_handlers(pat: str, expr: str, expected: str) -> None:
    p = NaturalLanguageParser()
    handler = p.recurrence_patterns[pat]
    match = p._try_pattern_match(pat, expr)
    assert match is not None and handler(match) == expected


def test_recurrence_string_literal() -> None:
    p = NaturalLanguageParser()
    handler = p.recurrence_patterns[r"every (day|daily)"]
    assert isinstance(handler, str) and handler == "FREQ=DAILY"


def test_pattern_match_valid_and_invalid() -> None:
    p = NaturalLanguageParser()
    m = p._try_pattern_match(r"in (\d+) minutes", "in 5 minutes")
    assert m is not None and m.group(1) == "5"
    assert p._try_pattern_match(r"in (\d+) minutes", "no match") is None


@pytest.mark.parametrize(
    "exc_type", [TypeError, ValueError, RuntimeError, AttributeError]
)
def test_process_pattern_handler_swallows(exc_type: type) -> None:
    p = NaturalLanguageParser()

    def bad(m: Any) -> Any:
        raise exc_type("boom")

    assert p._process_pattern_handler(bad, None) is None  # type: ignore[arg-type]


def test_process_pattern_handler_callable_returns() -> None:
    p = NaturalLanguageParser()

    def good(m: Any) -> str:
        return "ok"

    assert p._process_pattern_handler(good, None) == "ok"  # type: ignore[arg-type]


def test_convert_result_branches() -> None:
    p = NaturalLanguageParser()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert p._convert_result_to_datetime(timedelta(hours=1), base) == base + timedelta(hours=1)
    target = datetime(2027, 6, 15, 9, 0, 0, tzinfo=UTC)
    assert p._convert_result_to_datetime(target, base) == target
    assert p._convert_result_to_datetime(object(), base) is None


def test_convert_result_relativedelta(monkeypatch: pytest.MonkeyPatch) -> None:
    """An object with .months (relativedelta) hits the hasattr branch (line 130)."""
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", True)
    p = NaturalLanguageParser()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    handler = p.time_patterns[r"in (\d+) (month|months)"]
    match = p._try_pattern_match(r"in (\d+) (month|months)", "in 3 months")
    assert match is not None
    converted = p._convert_result_to_datetime(handler(match), base)
    assert converted is not None and converted.year == 2026 and converted.month == 4


def test_absolute_date_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    p = NaturalLanguageParser()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", False)
    assert p._try_parse_absolute_date("2026-12-25", base) is None
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", True)
    r = p._try_parse_absolute_date("December 25 2026", base)
    assert r is not None and r.tzinfo is UTC and r.year == 2026 and r.month == 12 and r.day == 25
    base2 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    assert p._try_parse_absolute_date("2020-01-01", base2) is None


@pytest.mark.parametrize("exc_type", [ValueError, TypeError])
def test_absolute_date_parser_exception(
    monkeypatch: pytest.MonkeyPatch, exc_type: type
) -> None:
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", True)

    def fake_parse(*args: Any, **kwargs: Any) -> datetime:
        raise exc_type("bad")

    monkeypatch.setattr(time_parser.date_parser, "parse", fake_parse)

    p = NaturalLanguageParser()
    assert p._try_parse_absolute_date("x", datetime(2026, 1, 1, 12, tzinfo=UTC)) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   \t\n", None),
        ("  In 5 Minutes  ", "in 5 minutes"),
        ("  hello  ", "hello"),
    ],
)
def test_validate_input(raw: str, expected: str | None) -> None:
    assert NaturalLanguageParser()._validate_input(raw) == expected


def test_try_parsing_strategies_all_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    p = NaturalLanguageParser()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", False)
    assert p._try_parsing_strategies("in 5 minutes", base) == base + timedelta(
        minutes=5
    )
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", True)
    r = p._try_parsing_strategies("December 25 2026", base)
    assert r is not None and r.month == 12 and r.day == 25
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", False)
    assert p._try_parsing_strategies("unparsable", base) is None


def test_parse_time_expression_empty_and_whitespace() -> None:
    p = NaturalLanguageParser()
    assert p.parse_time_expression("") is None
    assert p.parse_time_expression("   ") is None


def test_parse_time_expression_base_time_and_utc_now() -> None:
    p = NaturalLanguageParser()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert p.parse_time_expression("in 5 minutes", base_time=base) == base + timedelta(
        minutes=5
    )
    before = datetime.now(UTC)
    result = p.parse_time_expression("in 1 hour")
    after = datetime.now(UTC)
    assert result is not None
    assert before + timedelta(hours=1) <= result <= after + timedelta(hours=1)


def test_parse_time_expression_lowercases_and_strips() -> None:
    p = NaturalLanguageParser()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert p.parse_time_expression(
        "  IN 5 MINUTES  ", base_time=base
    ) == base + timedelta(minutes=5)


def test_parse_recurrence_branches() -> None:
    p = NaturalLanguageParser()
    assert p.parse_recurrence("") is None
    assert p.parse_recurrence("every day") == "FREQ=DAILY"
    assert p.parse_recurrence("every week") == "FREQ=WEEKLY"
    assert p.parse_recurrence("every month") == "FREQ=MONTHLY"
    assert p.parse_recurrence("every 15 minutes") == "FREQ=MINUTELY;INTERVAL=15"
    assert p.parse_recurrence("every 2 hours") == "FREQ=HOURLY;INTERVAL=2"
    assert p.parse_recurrence("every 3 days") == "FREQ=DAILY;INTERVAL=3"
    assert p.parse_recurrence("gibberish") is None
    assert p.parse_recurrence("  EVERY DAY  ") == "FREQ=DAILY"


def test_parse_recurrence_callable_returning_non_string_falls_through() -> None:
    p = NaturalLanguageParser()

    def bad(m: Any) -> int:
        return 42

    original = p.recurrence_patterns[r"every (day|daily)"]
    p.recurrence_patterns[r"every (day|daily)"] = bad
    try:
        assert p.parse_recurrence("every day") is None
    finally:
        p.recurrence_patterns[r"every (day|daily)"] = original


@pytest.mark.parametrize(
    ("expr", "hour", "minute"),
    [
        ("tomorrow", 9, 0),
        ("tomorrow at 9:00am", 9, 0),
        ("tomorrow at 3:00pm", 15, 0),
        ("tomorrow at 12:00pm", 12, 0),
        ("tomorrow at 12:00am", 0, 0),
        ("tomorrow at 2:30pm", 14, 30),
    ],
)
def test_parse_tomorrow(expr: str, hour: int, minute: int) -> None:
    p = NaturalLanguageParser()
    match = p._try_pattern_match(r"tomorrow( at (\d{1,2}):?(\d{2})?)?(am|pm)?", expr)
    assert match is not None
    result = p._parse_tomorrow(match)
    assert result.hour == hour and result.minute == minute


@pytest.mark.parametrize(
    ("weekday", "expected"),
    [
        ("monday", 0),
        ("tuesday", 1),
        ("wednesday", 2),
        ("thursday", 3),
        ("friday", 4),
        ("saturday", 5),
        ("sunday", 6),
    ],
)
def test_parse_next_weekday(weekday: str, expected: int) -> None:
    p = NaturalLanguageParser()
    match = p._try_pattern_match(
        r"next (monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        f"next {weekday}",
    )
    assert match is not None
    result = p._parse_next_weekday(match)
    assert result.weekday() == expected and result > datetime.now(UTC)


@pytest.mark.parametrize(
    ("expr", "hour"),
    [("at 9am", 9), ("at 3pm", 15), ("at 12pm", 12), ("at 12am", 0), ("at 3:30pm", 15)],
)
def test_parse_specific_time(expr: str, hour: int) -> None:
    p = NaturalLanguageParser()
    match = p._try_pattern_match(r"at (\d{1,2}):?(\d{2})?\s*(am|pm)?", expr)
    assert match is not None and p._parse_specific_time(match).hour == hour


def test_parse_specific_time_past_rolls_to_tomorrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        time_parser, "utc_now", lambda: datetime(2026, 1, 1, 23, 0, 0, tzinfo=UTC)
    )
    p = NaturalLanguageParser()
    match = p._try_pattern_match(r"at (\d{1,2}):?(\d{2})?\s*(am|pm)?", "at 9am")
    assert match is not None
    result = p._parse_specific_time(match)
    assert result.day == 2 and result.hour == 9


def test_parse_weekday_time() -> None:
    p = NaturalLanguageParser()
    pat = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday) at (\d{1,2}):?(\d{2})?\s*(am|pm)?"
    m1 = p._try_pattern_match(pat, "monday at 3pm")
    assert m1 is not None
    r1 = p._parse_weekday_time(m1)
    assert r1.weekday() == 0 and r1.hour == 15
    m2 = p._try_pattern_match(pat, "monday at 12am")
    assert m2 is not None and p._parse_weekday_time(m2).hour == 0


@pytest.mark.parametrize(
    ("w", "expected"),
    [
        ("monday", 0),
        ("tuesday", 1),
        ("wednesday", 2),
        ("thursday", 3),
        ("friday", 4),
        ("saturday", 5),
        ("sunday", 6),
    ],
)
def test_get_weekday_number(w: str, expected: int) -> None:
    assert NaturalLanguageParser()._get_weekday_number(w) == expected


@pytest.mark.parametrize(
    ("h", "m", "ap", "expected"),
    [
        ("3", "15", "pm", (15, 15)),
        ("12", None, "pm", (12, 0)),
        ("12", None, "am", (0, 0)),
        ("9", None, "am", (9, 0)),
        ("9", "30", None, (9, 30)),
        ("9", None, None, (9, 0)),
    ],
)
def test_parse_hour_minute(
    h: str, m: str | None, ap: str | None, expected: tuple[int, int]
) -> None:
    assert NaturalLanguageParser()._parse_hour_minute(h, m, ap) == expected


def test_calculate_days_ahead_branches() -> None:
    """2026-01-01 = Thursday = weekday 3. Covers all 4 branches."""
    today = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    p = NaturalLanguageParser()
    assert p._calculate_days_ahead(4, today, 9, 0) == 1
    assert p._calculate_days_ahead(3, today, 15, 0) == 0
    assert p._calculate_days_ahead(3, today, 9, 0) == 7
    assert p._calculate_days_ahead(0, today, 9, 0) == 4


def test_parse_time_expression_absolute_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = NaturalLanguageParser()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(time_parser, "DATEUTIL_AVAILABLE", True)
    r = p.parse_time_expression("December 25 2026", base_time=base)
    assert (
        r is not None
        and r.year == 2026
        and r.month == 12
        and r.day == 25
        and r.tzinfo is UTC
    )
    base2 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    assert p.parse_time_expression("2020-01-01", base_time=base2) is None
    assert p.parse_time_expression("zzz nonsense", base_time=base) is None
