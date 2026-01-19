"""Tests for session_analytics module.

Tests session analytics including:
- Session length distribution analysis
- Temporal pattern detection (time of day, day of week)
- Activity correlations analysis
- Session streak detection
- Productivity insights generation

Phase: Week 4 - Monitoring & Organization Testing
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.core.session_analytics import (
    SessionAnalytics,
    SessionLengthDistribution,
    TemporalPatterns,
    ActivityCorrelations,
    SessionStreaks,
    ProductivityInsights,
)


class TestSessionAnalytics:
    """Test SessionAnalytics class for workflow analytics."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database connection."""
        db = MagicMock()

        # Create a mock result that behaves like fetchall/fetchone
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[])
        mock_result.fetchone = MagicMock(return_value=None)

        # Make execute return the mock result
        db.execute = MagicMock(return_value=mock_result)
        db.fetchall = MagicMock(return_value=[])
        db.fetchone = MagicMock(return_value=None)

        return db

    @pytest.fixture
    def analytics(self, mock_db: MagicMock) -> SessionAnalytics:
        """Create SessionAnalytics instance with mock database."""
        with patch("session_buddy.core.session_analytics.duckdb.connect", return_value=mock_db):
            analytics = SessionAnalytics(db_path=":memory:")
            # Pre-set the connection to our mock
            analytics._conn = mock_db
            return analytics

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should create session_metrics table on initialization."""
        await analytics.initialize()

        # Verify connection was established
        assert analytics._conn is not None

    @pytest.mark.asyncio
    async def test_get_session_length_distribution_with_data(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should return session length distribution."""
        # Mock query result with durations in minutes
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = [
            (15.0,),  # short
            (45.0,),  # medium
            (90.0,),  # medium
            (150.0,),  # long
            (20.0,),  # short
        ]

        result = await analytics.get_session_length_distribution(project_path="/test/project", days_back=30)

        assert isinstance(result, SessionLengthDistribution)
        assert result.total_sessions == 5
        assert result.short_sessions == 2
        assert result.medium_sessions == 2
        assert result.long_sessions == 1
        assert result.short_percentage == 40.0
        assert result.medium_percentage == 40.0
        assert result.long_percentage == 20.0

    @pytest.mark.asyncio
    async def test_get_session_length_distribution_no_data(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should return zeros when no session data exists."""
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = []

        result = await analytics.get_session_length_distribution(project_path="/test/project", days_back=30)

        assert isinstance(result, SessionLengthDistribution)
        assert result.total_sessions == 0
        assert result.short_sessions == 0
        assert result.medium_sessions == 0
        assert result.long_sessions == 0

    @pytest.mark.asyncio
    async def test_get_temporal_patterns(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should analyze temporal patterns by time of day and day of week."""
        # Mock query results - need to match SQL query output format
        mock_result = mock_db.execute.return_value

        # Multiple queries in get_temporal_patterns:
        # 1. Time of day distribution
        # 2. Day of week distribution
        # 3. Peak hour (fetchone)
        # 4. Most productive time slot (fetchone)
        # 5. Frequency trend (from _calculate_frequency_trend)
        mock_result.fetchall.side_effect = [
            # Time of day query returns (time_of_day string, count)
            [("morning", 30), ("afternoon", 45), ("evening", 20)],
            # Day of week query returns (strftime number, count)
            [("1", 15), ("2", 18), ("3", 20)],  # Monday=1, Tuesday=2, Wednesday=3
            # Frequency trend query returns (week, count)
            [("2025-W01", 5), ("2025-W02", 7), ("2025-W03", 6)],  # For _calculate_frequency_trend
        ]

        # Mock fetchone for peak hour query
        mock_result.fetchone.side_effect = [
            (10,),  # Peak hour at 10am
            ("morning on Monday",),  # Most productive time slot
        ]

        result = await analytics.get_temporal_patterns(project_path="/test/project", days_back=30)

        assert isinstance(result, TemporalPatterns)
        assert "morning" in result.time_of_day_distribution or "afternoon" in result.time_of_day_distribution
        assert "Monday" in result.day_of_week_distribution or "Tuesday" in result.day_of_week_distribution
        assert result.avg_sessions_per_day > 0

    @pytest.mark.asyncio
    async def test_get_activity_correlations(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should calculate activity correlations."""
        # Mock query results with quality, commits, and duration
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = [
            (75.0, 5, 60.0),  # quality, commits, duration
            (80.0, 8, 90.0),
            (70.0, 3, 45.0),
            (85.0, 10, 120.0),
            (65.0, 2, 30.0),
        ]

        result = await analytics.get_activity_correlations(project_path="/test/project", days_back=30)

        assert isinstance(result, ActivityCorrelations)
        assert -1 <= result.duration_quality_correlation <= 1
        assert -1 <= result.duration_commits_correlation <= 1
        assert -1 <= result.quality_commits_correlation <= 1
        assert result.high_quality_sessions >= 0
        assert result.low_quality_sessions >= 0

    @pytest.mark.asyncio
    async def test_get_session_streaks(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should detect session streaks and consistency."""
        # Mock query results with session dates - DATE() returns date objects
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = [
            (datetime(2025, 1, 6, tzinfo=UTC).date(),),  # Active day
            (datetime(2025, 1, 7, tzinfo=UTC).date(),),  # Active day
            (datetime(2025, 1, 8, tzinfo=UTC).date(),),  # Active day
            (datetime(2025, 1, 10, tzinfo=UTC).date(),),  # Gap day
            (datetime(2025, 1, 11, tzinfo=UTC).date(),),  # Active day
        ]

        result = await analytics.get_session_streaks(project_path="/test/project", days_back=30)

        assert isinstance(result, SessionStreaks)
        assert result.longest_streak_days >= 0
        assert result.current_streak_days >= 0
        assert result.total_active_days == 5
        assert isinstance(result.consistent_daily_sessions, bool)

    @pytest.mark.asyncio
    async def test_get_productivity_insights(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should generate productivity insights."""
        # Mock query results for productivity analysis
        # get_productivity_insights calls:
        # 1. get_session_length_distribution (1 fetchall)
        # 2. get_temporal_patterns (3 fetchall + 2 fetchone)
        # 3. get_activity_correlations (1 fetchall)
        mock_result = mock_db.execute.return_value

        mock_result.fetchall.side_effect = [
            # 1. Duration data for session_length_distribution
            [(30.0,), (60.0,), (90.0,), (120.0,)],
            # 2a. Time of day distribution for get_temporal_patterns
            [("morning", 30), ("afternoon", 45)],
            # 2b. Day of week distribution for get_temporal_patterns
            [("1", 15), ("2", 18), ("3", 20)],
            # 2c. Frequency trend for get_temporal_patterns
            [("2025-W01", 5), ("2025-W02", 7), ("2025-W03", 6)],
            # 3. Activity correlations data
            [(60.0, 85.0, 8), (90.0, 80.0, 6), (75.0, 90.0, 10)],
        ]

        # Mock fetchone for peak hour queries (2 per call to get_temporal_patterns)
        mock_result.fetchone.side_effect = [
            (10,),  # Peak hour (call 1)
            ("morning on Monday",),  # Most productive time slot (call 1)
            (10,),  # Peak hour (call 2)
            ("morning on Monday",),  # Most productive time slot (call 2)
        ]

        result = await analytics.get_productivity_insights(project_path="/test/project", days_back=30)

        assert isinstance(result, ProductivityInsights)
        assert result.best_performance_window is not None
        assert result.recommended_session_length is not None
        assert result.optimal_break_interval > 0
        assert isinstance(result.peak_productivity_periods, list)
        assert isinstance(result.quality_factors, list)
        assert isinstance(result.improvement_suggestions, list)

    @pytest.mark.asyncio
    async def test_session_length_to_dict(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should convert SessionLengthDistribution to dict."""
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = [(30.0,), (60.0,), (90.0,)]

        result = await analytics.get_session_length_distribution(project_path="/test/project", days_back=30)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "short_sessions" in result_dict
        assert "medium_sessions" in result_dict
        assert "long_sessions" in result_dict
        assert "total_sessions" in result_dict
        assert "avg_duration_minutes" in result_dict

    @pytest.mark.asyncio
    async def test_temporal_patterns_to_dict(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should convert TemporalPatterns to dict."""
        mock_result = mock_db.execute.return_value
        # Time of day and day of week distribution + frequency trend
        mock_result.fetchall.side_effect = [
            [("morning", 30), ("afternoon", 45)],
            [("1", 15), ("2", 18)],
            [("2025-W01", 5), ("2025-W02", 7)],  # Frequency trend data
        ]
        # Peak hour queries
        mock_result.fetchone.side_effect = [
            (10,),
            ("morning on Monday",),
        ]

        result = await analytics.get_temporal_patterns(project_path="/test/project", days_back=30)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "time_of_day_distribution" in result_dict
        assert "day_of_week_distribution" in result_dict
        assert "peak_productivity_hour" in result_dict
        assert "peak_productivity_day" in result_dict

    @pytest.mark.asyncio
    async def test_activity_correlations_to_dict(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should convert ActivityCorrelations to dict."""
        mock_result = mock_db.execute.return_value
        mock_result.fetchall.return_value = [(75.0, 5, 60.0)]

        result = await analytics.get_activity_correlations(project_path="/test/project", days_back=30)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "duration_quality_correlation" in result_dict
        assert "duration_commits_correlation" in result_dict
        assert "quality_commits_correlation" in result_dict
        assert "high_quality_sessions" in result_dict

    @pytest.mark.asyncio
    async def test_session_streaks_to_dict(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should convert SessionStreaks to dict."""
        mock_result = mock_db.execute.return_value
        # Date objects from DATE() function
        mock_result.fetchall.return_value = [(datetime(2025, 1, 6, tzinfo=UTC).date(),)]

        result = await analytics.get_session_streaks(project_path="/test/project", days_back=30)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "longest_streak_days" in result_dict
        assert "current_streak_days" in result_dict
        assert "total_active_days" in result_dict
        assert "consistent_daily_sessions" in result_dict

    @pytest.mark.asyncio
    async def test_productivity_insights_to_dict(self, analytics: SessionAnalytics, mock_db: MagicMock) -> None:
        """Should convert ProductivityInsights to dict."""
        mock_result = mock_db.execute.return_value
        # Multiple queries for productivity insights (same pattern as test_get_productivity_insights)
        mock_result.fetchall.side_effect = [
            [(30.0,), (60.0,), (90.0,)],  # Durations
            [("morning", 30), ("afternoon", 45)],  # Time of day
            [("1", 15), ("2", 18)],  # Day of week
            [("2025-W01", 5), ("2025-W02", 7)],  # Frequency trend
            [(60.0, 85.0, 8), (90.0, 80.0, 6)],  # Activity correlations
        ]
        mock_result.fetchone.side_effect = [
            (10,),  # Peak hour (call 1)
            ("morning on Monday",),  # Most productive slot (call 1)
            (10,),  # Peak hour (call 2)
            ("morning on Monday",),  # Most productive slot (call 2)
        ]

        result = await analytics.get_productivity_insights(project_path="/test/project", days_back=30)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "best_performance_window" in result_dict
        assert "recommended_session_length" in result_dict
        assert "optimal_break_interval" in result_dict
        assert "peak_productivity_periods" in result_dict


class TestSessionLengthDistribution:
    """Test SessionLengthDistribution dataclass."""

    def test_session_length_distribution_creation(self) -> None:
        """Should create SessionLengthDistribution with valid data."""
        distribution = SessionLengthDistribution(
            short_sessions=10,
            medium_sessions=20,
            long_sessions=5,
            total_sessions=35,
            short_percentage=28.6,
            medium_percentage=57.1,
            long_percentage=14.3,
            avg_duration_minutes=65.5,
            median_duration_minutes=60.0,
        )

        assert distribution.total_sessions == 35
        assert distribution.short_percentage + distribution.medium_percentage + distribution.long_percentage == pytest.approx(100.0, rel=0.1)

    def test_session_length_distribution_to_dict(self) -> None:
        """Should convert to dictionary for JSON serialization."""
        distribution = SessionLengthDistribution(
            short_sessions=10,
            medium_sessions=20,
            long_sessions=5,
            total_sessions=35,
            short_percentage=28.6,
            medium_percentage=57.1,
            long_percentage=14.3,
            avg_duration_minutes=65.5,
            median_duration_minutes=60.0,
        )

        result = distribution.to_dict()

        assert isinstance(result, dict)
        assert result["total_sessions"] == 35
        assert result["avg_duration_minutes"] == 65.5


class TestTemporalPatterns:
    """Test TemporalPatterns dataclass."""

    def test_temporal_patterns_creation(self) -> None:
        """Should create TemporalPatterns with valid data."""
        patterns = TemporalPatterns(
            time_of_day_distribution={"morning": 30, "afternoon": 45, "evening": 20},
            day_of_week_distribution={"Monday": 15, "Tuesday": 18, "Wednesday": 20},
            peak_productivity_hour=10,
            peak_productivity_day="Wednesday",
            most_productive_time_slot="Wednesday morning",
            avg_sessions_per_day=3.5,
            session_frequency_trend="stable",
        )

        assert patterns.peak_productivity_hour == 10
        assert patterns.most_productive_time_slot == "Wednesday morning"
        assert patterns.avg_sessions_per_day == 3.5


class TestActivityCorrelations:
    """Test ActivityCorrelations dataclass."""

    def test_activity_correlations_creation(self) -> None:
        """Should create ActivityCorrelations with valid data."""
        correlations = ActivityCorrelations(
            duration_quality_correlation=0.65,
            duration_commits_correlation=0.45,
            quality_commits_correlation=0.78,
            high_quality_sessions=20,
            low_quality_sessions=5,
            high_commit_sessions=15,
            long_high_quality_sessions=8,
        )

        assert -1 <= correlations.duration_quality_correlation <= 1
        assert correlations.high_quality_sessions == 20
        assert correlations.long_high_quality_sessions == 8


class TestSessionStreaks:
    """Test SessionStreaks dataclass."""

    def test_session_streaks_creation(self) -> None:
        """Should create SessionStreaks with valid data."""
        streaks = SessionStreaks(
            longest_streak_days=14,
            current_streak_days=7,
            avg_gap_between_sessions_hours=24.5,
            longest_gap_hours=72.0,
            consistent_daily_sessions=True,
            most_consistent_week="2025-W03",
            total_active_days=21,
        )

        assert streaks.longest_streak_days == 14
        assert streaks.current_streak_days == 7
        assert streaks.longest_streak_days >= streaks.current_streak_days
        assert streaks.consistent_daily_sessions is True


class TestProductivityInsights:
    """Test ProductivityInsights dataclass."""

    def test_productivity_insights_creation(self) -> None:
        """Should create ProductivityInsights with valid data."""
        insights = ProductivityInsights(
            best_performance_window="Tuesday 9am-12pm",
            recommended_session_length="60-90 minutes",
            optimal_break_interval=45.0,
            peak_productivity_periods=["Tuesday morning", "Wednesday afternoon"],
            quality_factors=["Adequate sleep", "Regular breaks"],
            improvement_suggestions=["Take more breaks", "Stay hydrated"],
        )

        assert insights.best_performance_window == "Tuesday 9am-12pm"
        assert insights.optimal_break_interval == 45.0
        assert len(insights.peak_productivity_periods) == 2
        assert len(insights.improvement_suggestions) == 2
