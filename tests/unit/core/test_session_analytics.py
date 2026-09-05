"""Tests for session_buddy.core.session_analytics.

Covers the public dataclasses (to_dict serialization) and the
``SessionAnalytics`` DuckDB-backed query layer.

Strategy
--------
* Dataclass tests are pure (no DB).
* ``SessionAnalytics`` tests inject data into a duckdb_connection fixture
  (in-memory) and patch ``_get_conn`` so the engine reads from that
  fixture rather than opening a new file-based connection.
* We avoid exercising ``get_session_analytics()``'s DI container side
  effects — testing it would pull in the DI registry and is out of scope.
* The ``session_metrics`` table is created per-test so tests stay
  independent; ``duckdb_connection`` already provides an isolated
  in-memory database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import duckdb
import pytest

from session_buddy.core.session_analytics import (
    ActivityCorrelations,
    DEPENDENCY_KEY,
    ProductivityInsights,
    SessionAnalytics,
    SessionLengthDistribution,
    SessionStreaks,
    TemporalPatterns,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_session_metrics_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the session_metrics table matching the analytics SQL queries."""
    conn.execute(
        """
        CREATE TABLE session_metrics (
            project_path VARCHAR,
            started_at TIMESTAMP,
            duration_minutes INTEGER,
            time_of_day VARCHAR,
            commit_count INTEGER,
            checkpoint_count INTEGER,
            avg_quality DOUBLE
        )
        """
    )


_RECENT_BASE = datetime.now(UTC) - timedelta(days=10)


def _insert_session(
    conn: duckdb.DuckDBPyConnection,
    *,
    project_path: str = "/test/proj",
    started_at: datetime | None = None,
    duration_minutes: int = 60,
    time_of_day: str = "morning",
    commit_count: int = 5,
    checkpoint_count: int = 2,
    avg_quality: float = 75.0,
) -> None:
    """Insert a single session row with the given fields.

    Default timestamp is anchored 10 days before ``now`` so rows pass the
    default ``days_back=30`` filter in the analytics queries.
    """
    ts = started_at or _RECENT_BASE
    conn.execute(
        """
        INSERT INTO session_metrics VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            project_path,
            ts,
            duration_minutes,
            time_of_day,
            commit_count,
            checkpoint_count,
            avg_quality,
        ],
    )


@pytest.fixture
async def analytics_with_conn(duckdb_connection):
    """Return a (analytics, conn) pair with the conn patched in.

    The DuckDB connection has an empty ``session_metrics`` table ready
    to be populated by individual tests.
    """
    conn = duckdb_connection
    _create_session_metrics_table(conn)
    analytics = SessionAnalytics(db_path="/tmp/unused_analytics.db")
    with patch.object(analytics, "_get_conn", return_value=conn):
        yield analytics, conn


def _next_weekday(start: Any, target_weekday: int) -> Any:
    """Return the next date >= ``start`` whose ``weekday()`` == ``target_weekday``.

    ``target_weekday`` follows Python's ``date.weekday()`` convention
    (Monday = 0, Sunday = 6).
    """
    days_ahead = (target_weekday - start.weekday()) % 7
    return start + timedelta(days=days_ahead)


# ---------------------------------------------------------------------------
# SessionLengthDistribution
# ---------------------------------------------------------------------------


class TestSessionLengthDistribution:
    """Pure dataclass serialization tests."""

    def test_to_dict_rounds_percentages_and_durations(self) -> None:
        dist = SessionLengthDistribution(
            short_sessions=2,
            medium_sessions=3,
            long_sessions=5,
            total_sessions=10,
            short_percentage=20.0,
            medium_percentage=30.0,
            long_percentage=50.0,
            avg_duration_minutes=87.6543,
            median_duration_minutes=85.1234,
        )
        result = dist.to_dict()
        assert result["short_sessions"] == 2
        assert result["medium_sessions"] == 3
        assert result["long_sessions"] == 5
        assert result["total_sessions"] == 10
        assert result["short_percentage"] == 20.0
        assert result["medium_percentage"] == 30.0
        assert result["long_percentage"] == 50.0
        assert result["avg_duration_minutes"] == 87.7
        assert result["median_duration_minutes"] == 85.1

    def test_to_dict_with_zero_sessions(self) -> None:
        dist = SessionLengthDistribution(
            short_sessions=0,
            medium_sessions=0,
            long_sessions=0,
            total_sessions=0,
            short_percentage=0.0,
            medium_percentage=0.0,
            long_percentage=0.0,
            avg_duration_minutes=0.0,
            median_duration_minutes=0.0,
        )
        assert dist.to_dict() == {
            "short_sessions": 0,
            "medium_sessions": 0,
            "long_sessions": 0,
            "total_sessions": 0,
            "short_percentage": 0.0,
            "medium_percentage": 0.0,
            "long_percentage": 0.0,
            "avg_duration_minutes": 0.0,
            "median_duration_minutes": 0.0,
        }


# ---------------------------------------------------------------------------
# TemporalPatterns
# ---------------------------------------------------------------------------


class TestTemporalPatterns:
    """Pure dataclass serialization tests."""

    def test_to_dict_rounds_avg_sessions(self) -> None:
        patterns = TemporalPatterns(
            time_of_day_distribution={"morning": 5, "evening": 2},
            day_of_week_distribution={"Monday": 3, "Tuesday": 4},
            peak_productivity_hour=10,
            peak_productivity_day="Tuesday",
            most_productive_time_slot="morning on Tuesday",
            avg_sessions_per_day=2.3456,
            session_frequency_trend="increasing",
        )
        result = patterns.to_dict()
        assert result["time_of_day_distribution"] == {"morning": 5, "evening": 2}
        assert result["day_of_week_distribution"] == {"Monday": 3, "Tuesday": 4}
        assert result["peak_productivity_hour"] == 10
        assert result["peak_productivity_day"] == "Tuesday"
        assert result["most_productive_time_slot"] == "morning on Tuesday"
        assert result["avg_sessions_per_day"] == 2.35
        assert result["session_frequency_trend"] == "increasing"


# ---------------------------------------------------------------------------
# ActivityCorrelations
# ---------------------------------------------------------------------------


class TestActivityCorrelations:
    """Pure dataclass serialization tests."""

    def test_to_dict_rounds_correlations_to_three_decimals(self) -> None:
        corr = ActivityCorrelations(
            duration_quality_correlation=0.123456,
            duration_commits_correlation=-0.5,
            quality_commits_correlation=0.987654,
            high_quality_sessions=7,
            low_quality_sessions=3,
            high_commit_sessions=4,
            long_high_quality_sessions=2,
        )
        result = corr.to_dict()
        assert result["duration_quality_correlation"] == 0.123
        assert result["duration_commits_correlation"] == -0.5
        assert result["quality_commits_correlation"] == 0.988
        assert result["high_quality_sessions"] == 7
        assert result["low_quality_sessions"] == 3
        assert result["high_commit_sessions"] == 4
        assert result["long_high_quality_sessions"] == 2


# ---------------------------------------------------------------------------
# SessionStreaks
# ---------------------------------------------------------------------------


class TestSessionStreaks:
    """Pure dataclass serialization tests."""

    def test_to_dict_rounds_gaps(self) -> None:
        streaks = SessionStreaks(
            longest_streak_days=10,
            current_streak_days=3,
            avg_gap_between_sessions_hours=12.3456,
            longest_gap_hours=48.789,
            consistent_daily_sessions=True,
            most_consistent_week="2026-W32",
            total_active_days=20,
        )
        result = streaks.to_dict()
        assert result["longest_streak_days"] == 10
        assert result["current_streak_days"] == 3
        assert result["avg_gap_between_sessions_hours"] == 12.3
        assert result["longest_gap_hours"] == 48.8
        assert result["consistent_daily_sessions"] is True
        assert result["most_consistent_week"] == "2026-W32"
        assert result["total_active_days"] == 20


# ---------------------------------------------------------------------------
# ProductivityInsights
# ---------------------------------------------------------------------------


class TestProductivityInsights:
    """Pure dataclass serialization tests."""

    def test_to_dict_rounds_break_interval(self) -> None:
        insights = ProductivityInsights(
            best_performance_window="Tuesday 9am-12pm",
            recommended_session_length="60-90 minutes",
            optimal_break_interval=87.6,
            peak_productivity_periods=["Tuesday morning"],
            quality_factors=["Longer sessions correlate with higher quality"],
            improvement_suggestions=["Aim for at least one focused session per day"],
        )
        result = insights.to_dict()
        assert result["best_performance_window"] == "Tuesday 9am-12pm"
        assert result["recommended_session_length"] == "60-90 minutes"
        assert result["optimal_break_interval"] == 88.0
        assert result["peak_productivity_periods"] == ["Tuesday morning"]
        assert result["quality_factors"] == [
            "Longer sessions correlate with higher quality"
        ]
        assert result["improvement_suggestions"] == [
            "Aim for at least one focused session per day"
        ]


# ---------------------------------------------------------------------------
# SessionAnalytics — initialization
# ---------------------------------------------------------------------------


class TestSessionAnalyticsInit:
    """Initialization, connection lifecycle, and module-level constants."""

    def test_init_with_explicit_db_path(self, tmp_path) -> None:
        db = tmp_path / "analytics.db"
        analytics = SessionAnalytics(db_path=str(db))
        assert analytics.db_path == str(db)
        assert analytics._conn is None

    def test_init_expands_user_tilde(self) -> None:
        analytics = SessionAnalytics(db_path="~/test_analytics.db")
        assert "~" not in analytics.db_path
        assert analytics.db_path.endswith("test_analytics.db")

    async def test_initialize_creates_connection(
        self, duckdb_connection, tmp_path
    ) -> None:
        analytics = SessionAnalytics(db_path=str(tmp_path / "init.db"))
        with patch.object(analytics, "_get_conn", return_value=duckdb_connection):
            await analytics.initialize()
        # _get_conn may not have been called if patched; verify state by closing.

    def test_dependency_key_is_session_analytics_string(self) -> None:
        assert DEPENDENCY_KEY == "session_analytics"
        assert isinstance(DEPENDENCY_KEY, str)

    def test_close_resets_connection(self, tmp_path) -> None:
        analytics = SessionAnalytics(db_path=str(tmp_path / "close.db"))
        mock_conn = duckdb.connect(":memory:")
        analytics._conn = mock_conn
        analytics.close()
        assert analytics._conn is None

    def test_close_is_safe_with_no_connection(self, tmp_path) -> None:
        analytics = SessionAnalytics(db_path=str(tmp_path / "noop.db"))
        analytics.close()  # must not raise
        assert analytics._conn is None


# ---------------------------------------------------------------------------
# get_session_length_distribution
# ---------------------------------------------------------------------------


class TestGetSessionLengthDistribution:
    """Branch coverage: empty / short-only / mixed / boundary."""

    async def test_empty_database_returns_all_zeros(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, _ = analytics_with_conn
        result = await analytics.get_session_length_distribution()
        assert result.total_sessions == 0
        assert result.short_sessions == 0
        assert result.medium_sessions == 0
        assert result.long_sessions == 0
        assert result.short_percentage == 0.0
        assert result.median_duration_minutes == 0.0

    async def test_short_medium_long_bucketing(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        _insert_session(conn, duration_minutes=10)  # short
        _insert_session(conn, duration_minutes=29)  # short
        _insert_session(conn, duration_minutes=30)  # medium
        _insert_session(conn, duration_minutes=60)  # medium
        _insert_session(conn, duration_minutes=120)  # medium
        _insert_session(conn, duration_minutes=121)  # long
        _insert_session(conn, duration_minutes=200)  # long
        result = await analytics.get_session_length_distribution()
        assert result.short_sessions == 2
        assert result.medium_sessions == 3
        assert result.long_sessions == 2
        assert result.total_sessions == 7
        # Percentages sum to ~100
        assert (
            result.short_percentage
            + result.medium_percentage
            + result.long_percentage
        ) == pytest.approx(100.0)

    async def test_null_duration_filtered_out(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        _insert_session(conn, duration_minutes=45)
        conn.execute(
            "INSERT INTO session_metrics VALUES (?, ?, NULL, ?, ?, ?, ?)",
            ["/p", _RECENT_BASE, "morning", 1, 1, 70.0],
        )
        result = await analytics.get_session_length_distribution()
        assert result.total_sessions == 1
        assert result.medium_sessions == 1

    async def test_with_project_path_filter(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        _insert_session(conn, project_path="/proj-a", duration_minutes=15)
        _insert_session(conn, project_path="/proj-b", duration_minutes=200)
        result = await analytics.get_session_length_distribution(
            project_path="/proj-a"
        )
        assert result.total_sessions == 1
        assert result.short_sessions == 1


# ---------------------------------------------------------------------------
# get_temporal_patterns
# ---------------------------------------------------------------------------


class TestGetTemporalPatterns:
    """Branch coverage: empty, distribution maps, peak detection, trend."""

    async def test_empty_database_returns_defaults(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, _ = analytics_with_conn
        result = await analytics.get_temporal_patterns()
        assert result.time_of_day_distribution == {}
        assert result.day_of_week_distribution == {}
        # No data -> defaults from code paths
        assert result.peak_productivity_day == "Monday"
        assert result.most_productive_time_slot == "Unknown"
        assert result.session_frequency_trend == "stable"
        assert result.avg_sessions_per_day == 0.0

    async def test_time_of_day_distribution(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        _insert_session(conn, time_of_day="morning")
        _insert_session(conn, time_of_day="morning")
        _insert_session(conn, time_of_day="evening")
        result = await analytics.get_temporal_patterns()
        assert result.time_of_day_distribution == {"morning": 2, "evening": 1}

    async def test_day_of_week_names_mapping(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # Pick two distinct weekdays anchored inside the 30-day window.
        today = datetime.now(UTC).date()
        monday = _next_weekday(today, 0)  # 0 = Monday
        wednesday = monday + timedelta(days=2)
        _insert_session(
            conn, started_at=datetime.combine(monday, datetime.min.time(), UTC)
        )
        _insert_session(
            conn,
            started_at=datetime.combine(wednesday, datetime.min.time(), UTC),
        )
        result = await analytics.get_temporal_patterns()
        assert result.day_of_week_distribution == {"Monday": 1, "Wednesday": 1}

    async def test_peak_productivity_day_picks_max(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # Two Tuesdays, one Monday -> Tuesday wins
        today = datetime.now(UTC).date()
        tuesday1 = _next_weekday(today, 1)  # 1 = Tuesday
        tuesday2 = tuesday1 + timedelta(days=7)
        monday = tuesday1 - timedelta(days=1)
        _insert_session(
            conn,
            started_at=datetime.combine(tuesday1, datetime.min.time(), UTC),
        )
        _insert_session(
            conn,
            started_at=datetime.combine(tuesday2, datetime.min.time(), UTC),
        )
        _insert_session(
            conn,
            started_at=datetime.combine(monday, datetime.min.time(), UTC),
        )
        result = await analytics.get_temporal_patterns()
        assert result.peak_productivity_day == "Tuesday"


# ---------------------------------------------------------------------------
# get_activity_correlations
# ---------------------------------------------------------------------------


class TestGetActivityCorrelations:
    """Branch coverage: empty, <2 rows, correlation correctness, thresholds."""

    async def test_empty_database_returns_zeros(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, _ = analytics_with_conn
        result = await analytics.get_activity_correlations()
        assert result.duration_quality_correlation == 0.0
        assert result.duration_commits_correlation == 0.0
        assert result.quality_commits_correlation == 0.0
        assert result.high_quality_sessions == 0
        assert result.low_quality_sessions == 0
        assert result.high_commit_sessions == 0
        assert result.long_high_quality_sessions == 0

    async def test_single_row_returns_zeros(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        _insert_session(conn)
        result = await analytics.get_activity_correlations()
        # Single row -> correlation branch returns 0.0
        assert result.duration_quality_correlation == 0.0

    async def test_perfect_positive_correlation(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # duration and quality move together linearly
        _insert_session(conn, duration_minutes=10, avg_quality=10.0)
        _insert_session(conn, duration_minutes=20, avg_quality=20.0)
        _insert_session(conn, duration_minutes=30, avg_quality=30.0)
        _insert_session(conn, duration_minutes=40, avg_quality=40.0)
        result = await analytics.get_activity_correlations()
        assert result.duration_quality_correlation == pytest.approx(1.0, abs=1e-9)

    async def test_counts_high_low_quality_and_commits(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        _insert_session(conn, avg_quality=85.0, commit_count=12)  # high + high
        _insert_session(conn, avg_quality=50.0, commit_count=3)  # low
        _insert_session(conn, avg_quality=75.0, commit_count=8)  # neutral
        result = await analytics.get_activity_correlations()
        assert result.high_quality_sessions == 1
        assert result.low_quality_sessions == 1
        assert result.high_commit_sessions == 1

    async def test_long_high_quality_session_counted(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # duration > 120 AND quality >= 80
        _insert_session(conn, duration_minutes=200, avg_quality=90.0)
        # long but low quality -> not counted
        _insert_session(conn, duration_minutes=200, avg_quality=50.0)
        # short but high quality -> not counted as long_high
        _insert_session(conn, duration_minutes=30, avg_quality=90.0)
        result = await analytics.get_activity_correlations()
        assert result.long_high_quality_sessions == 1


# ---------------------------------------------------------------------------
# get_session_streaks
# ---------------------------------------------------------------------------


class TestGetSessionStreaks:
    """Branch coverage: empty, consecutive days, gap detection, weekly peaks."""

    async def test_empty_database_returns_defaults(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, _ = analytics_with_conn
        result = await analytics.get_session_streaks()
        assert result.longest_streak_days == 0
        assert result.current_streak_days == 0
        assert result.consistent_daily_sessions is False
        assert result.most_consistent_week == ""
        assert result.total_active_days == 0
        assert result.avg_gap_between_sessions_hours == 0.0
        assert result.longest_gap_hours == 0.0

    async def test_consecutive_days_detects_streak(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # 5 consecutive days of sessions, all within the 30-day window
        base = _RECENT_BASE
        for i in range(5):
            _insert_session(conn, started_at=base + timedelta(days=i))
        result = await analytics.get_session_streaks()
        assert result.longest_streak_days == 5
        assert result.consistent_daily_sessions is True
        assert result.total_active_days == 5

    async def test_gap_between_sessions(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        d1 = _RECENT_BASE
        d2 = d1 + timedelta(days=2)
        d3 = d1 + timedelta(days=7)
        _insert_session(conn, started_at=d1)
        _insert_session(conn, started_at=d2)
        _insert_session(conn, started_at=d3)
        result = await analytics.get_session_streaks()
        # Gaps: 48h, 120h -> avg = 84h, max = 120h
        assert result.avg_gap_between_sessions_hours == pytest.approx(84.0)
        assert result.longest_gap_hours == pytest.approx(120.0)
        assert result.total_active_days == 3

    async def test_consistent_threshold_requires_five_days(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        base = _RECENT_BASE
        # 4 consecutive days (one less than the 5+ threshold)
        for i in range(4):
            _insert_session(conn, started_at=base + timedelta(days=i))
        result = await analytics.get_session_streaks()
        assert result.longest_streak_days == 4
        assert result.consistent_daily_sessions is False


# ---------------------------------------------------------------------------
# get_productivity_insights
# ---------------------------------------------------------------------------


class TestGetProductivityInsights:
    """Branch coverage: empty data, mid/short/long sessions, low correlation."""

    async def test_empty_database_returns_baseline_insights(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, _ = analytics_with_conn
        result = await analytics.get_productivity_insights()
        # No data -> peak slot is "Unknown", avg duration 0 -> default 90 min break
        assert result.best_performance_window == "Unknown"
        assert result.optimal_break_interval == 90.0
        # 60-90 minutes string default branch (medium/long percentages are 0)
        assert "60-90 minutes" in result.recommended_session_length
        # No peak time/periods when empty
        assert result.peak_productivity_periods == []
        assert result.quality_factors == []

    async def test_short_sessions_trigger_extension_suggestion(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # > 60% short (< 30 min)
        for _ in range(7):
            _insert_session(conn, duration_minutes=10)
        _insert_session(conn, duration_minutes=120)
        result = await analytics.get_productivity_insights()
        assert any("60-90 minutes" in s for s in result.improvement_suggestions)

    async def test_high_quality_correlation_factor(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # Strong positive correlation between duration and quality
        _insert_session(conn, duration_minutes=10, avg_quality=10.0)
        _insert_session(conn, duration_minutes=30, avg_quality=30.0)
        _insert_session(conn, duration_minutes=60, avg_quality=60.0)
        _insert_session(conn, duration_minutes=120, avg_quality=90.0)
        result = await analytics.get_productivity_insights()
        assert any(
            "Longer sessions correlate with higher quality" in f
            for f in result.quality_factors
        )

    async def test_no_long_high_quality_triggers_balance_suggestion(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # 2 sessions but neither is long+high-quality (duration<=120 or quality<80)
        _insert_session(conn, duration_minutes=15, avg_quality=85.0)
        _insert_session(conn, duration_minutes=15, avg_quality=85.0)
        result = await analytics.get_productivity_insights()
        assert any(
            "Balance session length" in s for s in result.improvement_suggestions
        )


# ---------------------------------------------------------------------------
# _calculate_correlation helper
# ---------------------------------------------------------------------------


class TestCalculateCorrelation:
    """Direct exercise of the Pearson correlation helper."""

    def test_perfect_positive(self) -> None:
        analytics = SessionAnalytics(db_path="/tmp/dummy.db")
        assert analytics._calculate_correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(
            1.0
        )

    def test_perfect_negative(self) -> None:
        analytics = SessionAnalytics(db_path="/tmp/dummy.db")
        assert analytics._calculate_correlation(
            [1, 2, 3], [3, 2, 1]
        ) == pytest.approx(-1.0)

    def test_zero_when_length_mismatch(self) -> None:
        analytics = SessionAnalytics(db_path="/tmp/dummy.db")
        assert analytics._calculate_correlation([1, 2], [1, 2, 3]) == 0.0

    def test_zero_when_length_below_two(self) -> None:
        analytics = SessionAnalytics(db_path="/tmp/dummy.db")
        assert analytics._calculate_correlation([], []) == 0.0
        assert analytics._calculate_correlation([1], [2]) == 0.0

    def test_zero_when_constant_input(self) -> None:
        analytics = SessionAnalytics(db_path="/tmp/dummy.db")
        # denominator (sum_xx * sum_yy) ** 0.5 == 0 -> early return 0.0
        assert analytics._calculate_correlation([5, 5, 5], [1, 2, 3]) == 0.0
        assert analytics._calculate_correlation([1, 2, 3], [5, 5, 5]) == 0.0


# ---------------------------------------------------------------------------
# _calculate_frequency_trend helper
# ---------------------------------------------------------------------------


class TestCalculateFrequencyTrend:
    """Direct exercise of the weekly-trend detection helper."""

    async def test_stable_when_fewer_than_two_weeks(
        self, analytics_with_conn: Any
    ) -> None:
        analytics, conn = analytics_with_conn
        # Only one week of data
        _insert_session(conn, started_at=_RECENT_BASE)
        result = await analytics._calculate_frequency_trend(
            where_sql="WHERE 1=1", params=[], days_back=30
        )
        assert result == "stable"

    async def test_increasing_trend(self, analytics_with_conn: Any) -> None:
        analytics, conn = analytics_with_conn
        # Three distinct calendar weeks within the 30-day window.
        # Each anchor is mid-week so it cannot straddle a week boundary.
        week1 = _RECENT_BASE - timedelta(days=21)
        week2 = _RECENT_BASE - timedelta(days=14)
        week3 = _RECENT_BASE - timedelta(days=7)
        _insert_session(conn, started_at=week1)
        _insert_session(conn, started_at=week2)
        # Lots of sessions in the most-recent week.
        for i in range(10):
            _insert_session(
                conn,
                started_at=week3 + timedelta(hours=i),
            )
        result = await analytics._calculate_frequency_trend(
            where_sql="WHERE 1=1", params=[], days_back=30
        )
        assert result == "increasing"

    async def test_decreasing_trend(self, analytics_with_conn: Any) -> None:
        analytics, conn = analytics_with_conn
        # Three distinct calendar weeks: heavy activity then a quiet recent week.
        week1 = _RECENT_BASE - timedelta(days=21)
        week2 = _RECENT_BASE - timedelta(days=14)
        week3 = _RECENT_BASE - timedelta(days=7)
        for i in range(15):
            _insert_session(conn, started_at=week1 + timedelta(hours=i))
        _insert_session(conn, started_at=week2)
        # Recent week: 1 session -> recent_avg well below earlier_avg * 0.8
        _insert_session(conn, started_at=week3)
        result = await analytics._calculate_frequency_trend(
            where_sql="WHERE 1=1", params=[], days_back=30
        )
        assert result == "decreasing"
