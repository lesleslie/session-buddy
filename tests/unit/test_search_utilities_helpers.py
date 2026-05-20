from __future__ import annotations

from datetime import UTC, datetime, timedelta

from session_buddy.session_types import TimeRange
from session_buddy.utils.search import utilities


class _PatternStub:
    def __init__(
        self,
        *,
        search_result: bool = False,
        findall_result: list[str] | None = None,
    ) -> None:
        self._search_result = search_result
        self._findall_result = findall_result or []

    def search(self, content: str) -> bool:
        return self._search_result

    def findall(self, content: str) -> list[str]:
        return list(self._findall_result)


def test_extract_technical_terms(monkeypatch) -> None:
    monkeypatch.setitem(
        utilities.SAFE_PATTERNS,
        "python_code",
        _PatternStub(search_result=True),
    )
    monkeypatch.setitem(
        utilities.SAFE_PATTERNS,
        "javascript_code",
        _PatternStub(search_result=True),
    )
    monkeypatch.setitem(utilities.SAFE_PATTERNS, "sql_code", _PatternStub())
    monkeypatch.setitem(
        utilities.SAFE_PATTERNS,
        "error_keywords",
        _PatternStub(search_result=True),
    )
    monkeypatch.setitem(
        utilities.SAFE_PATTERNS,
        "function_definition",
        _PatternStub(
            findall_result=["alpha", "beta", "gamma", "delta", "epsilon", "zeta"],
        ),
    )
    monkeypatch.setitem(
        utilities.SAFE_PATTERNS,
        "class_definition",
        _PatternStub(findall_result=["One", "Two", "Three"]),
    )
    monkeypatch.setitem(
        utilities.SAFE_PATTERNS,
        "file_extension",
        _PatternStub(findall_result=["py", "md", "py", "txt"]),
    )

    terms = utilities.extract_technical_terms("ignored content")

    assert terms[:3] == ["python", "javascript", "error"]
    assert "function:alpha" in terms
    assert "function:epsilon" in terms
    assert "function:zeta" not in terms
    assert "class:One" in terms
    assert "class:Three" in terms
    assert {"filetype:py", "filetype:md", "filetype:txt"}.issubset(set(terms))


def test_truncate_content() -> None:
    assert utilities.truncate_content("abc", 5) == "abc"
    assert utilities.truncate_content("abcdef", 3) == "abc..."


def test_ensure_timezone() -> None:
    naive = datetime(2026, 5, 17, 12, 0, 0)
    aware = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    assert utilities.ensure_timezone(naive).tzinfo == UTC
    assert utilities.ensure_timezone(aware) is aware


def test_parse_timeframe_single() -> None:
    before = datetime.now(UTC)
    result = utilities.parse_timeframe_single("1d")

    assert result is not None
    delta = before - result
    assert abs(delta - timedelta(days=1)) < timedelta(seconds=5)

    before = datetime.now(UTC)
    result = utilities.parse_timeframe_single("2h")
    assert result is not None
    assert abs((before - result) - timedelta(hours=2)) < timedelta(seconds=5)

    before = datetime.now(UTC)
    result = utilities.parse_timeframe_single("2w")
    assert result is not None
    assert abs((before - result) - timedelta(weeks=2)) < timedelta(seconds=5)

    before = datetime.now(UTC)
    result = utilities.parse_timeframe_single("2m")
    assert result is not None
    assert abs((before - result) - timedelta(days=60)) < timedelta(seconds=5)

    assert utilities.parse_timeframe_single("invalid") is None


def test_parse_timeframe_branches() -> None:
    range_result = utilities.parse_timeframe("2024-01-01..2024-01-31")
    assert isinstance(range_result, TimeRange)
    assert range_result.start == datetime(2024, 1, 1, tzinfo=UTC)
    assert range_result.end == datetime(2024, 1, 31, tzinfo=UTC)

    year_result = utilities.parse_timeframe("2024")
    assert year_result.start == datetime(2024, 1, 1, tzinfo=UTC)
    assert year_result.end == datetime(2025, 1, 1, tzinfo=UTC)

    month_result = utilities.parse_timeframe("2024-02")
    assert month_result.start == datetime(2024, 2, 1, tzinfo=UTC)
    assert month_result.end == datetime(2024, 3, 1, tzinfo=UTC)

    december_result = utilities.parse_timeframe("2024-12")
    assert december_result.start == datetime(2024, 12, 1, tzinfo=UTC)
    assert december_result.end == datetime(2025, 1, 1, tzinfo=UTC)

    relative_result = utilities.parse_timeframe("7d")
    assert isinstance(relative_result, TimeRange)
    assert relative_result.end is not None
    assert relative_result.start is not None
    assert relative_result.end > relative_result.start

    default_result = utilities.parse_timeframe("not-a-timeframe")
    assert isinstance(default_result, TimeRange)
    assert default_result.end is not None
    assert default_result.start is not None
    assert default_result.end - default_result.start == timedelta(days=7)
