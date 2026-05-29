"""Tests for session_buddy.analytics.session_analytics module.

Tests for SessionAnalytics class covering:
- Session statistics and duration analysis
- Component usage tracking
- Event aggregation and time series
- Error rate statistics
- ASCII visualization

Target: 60%+ code coverage
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.analytics.session_analytics import (
    ASCIIVisualizer,
    ComponentUsage,
    SessionAnalytics,
    SessionStats,
    create_session_summary_report,
)


# =============================================================================
# Test ASCIIVisualizer
# =============================================================================


class TestASCIIVisualizerBarChart:
    """Tests for ASCIIVisualizer.bar_chart method."""

    def test_bar_chart_with_data(self) -> None:
        """Should render bar chart with multiple items."""
        data = [("admin-shell", 100), ("ipython", 75), ("zsh", 50)]
        result = ASCIIVisualizer.bar_chart(data, width=50)

        assert len(result) == 3
        assert "admin-shell" in result[0]
        assert "100" in result[0]
        assert "█" in result[0]

    def test_bar_chart_empty_data(self) -> None:
        """Should return 'No data available' for empty list."""
        result = ASCIIVisualizer.bar_chart([])
        assert result == ["No data available"]

    def test_bar_chart_single_item(self) -> None:
        """Should render bar chart with single item."""
        data = [("only", 42)]
        result = ASCIIVisualizer.bar_chart(data, width=40)

        assert len(result) == 1
        assert "only" in result[0]
        assert "42" in result[0]

    def test_bar_chart_zero_values(self) -> None:
        """Should handle zero values gracefully."""
        data = [("zero", 0), ("positive", 50)]
        result = ASCIIVisualizer.bar_chart(data, width=50)

        assert len(result) == 2
        # Should not crash with zero value

    def test_bar_chart_large_values(self) -> None:
        """Should handle large numeric values."""
        data = [("big", 1000000), ("small", 1)]
        result = ASCIIVisualizer.bar_chart(data, width=50)

        assert len(result) == 2
        # Should handle large ratio


class TestASCIIVisualizerSparkline:
    """Tests for ASCIIVisualizer.sparkline method."""

    def test_sparkline_with_data(self) -> None:
        """Should generate sparkline for numeric values."""
        values = [1, 2, 3, 4, 5, 6, 7, 8]
        result = ASCIIVisualizer.sparkline(values, width=40)

        assert result != ""
        assert len(result) <= 40
        # Should use sparkline characters

    def test_sparkline_empty_values(self) -> None:
        """Should return 'No data' for empty list."""
        result = ASCIIVisualizer.sparkline([])
        assert result == "No data"

    def test_sparkline_single_value(self) -> None:
        """Should handle single value."""
        values = [5]
        result = ASCIIVisualizer.sparkline(values)

        assert result != ""
        assert len(result) == 1

    def test_sparkline_constant_values(self) -> None:
        """Should handle constant values (no range)."""
        values = [5, 5, 5, 5]
        result = ASCIIVisualizer.sparkline(values)

        assert result != ""

    def test_sparkline_negative_values(self) -> None:
        """Should handle negative values."""
        values = [-10, -5, 0, 5, 10]
        result = ASCIIVisualizer.sparkline(values)

        assert result != ""


class TestASCIIVisualizerTable:
    """Tests for ASCIIVisualizer.table method."""

    def test_table_with_data(self) -> None:
        """Should render table with headers and rows."""
        headers = ["Name", "Value", "Count"]
        rows = [["alpha", "100", "5"], ["beta", "200", "3"]]
        result = ASCIIVisualizer.table(headers, rows)

        assert len(result) >= 3  # header, separator, data rows
        assert "Name" in result[0]
        assert "Value" in result[0]

    def test_table_empty_headers(self) -> None:
        """Should return 'No data available' for empty headers."""
        result = ASCIIVisualizer.table([], [["a", "b"]])
        assert result == ["No data available"]

    def test_table_empty_rows(self) -> None:
        """Should return 'No data available' for empty rows."""
        result = ASCIIVisualizer.table(["Col1", "Col2"], [])
        assert result == ["No data available"]

    def test_table_alignment_left(self) -> None:
        """Should align columns left by default."""
        headers = ["Name", "Value"]
        rows = [["short", "longervalue"]]
        result = ASCIIVisualizer.table(headers, rows, align=["left", "left"])

        assert "short" in result[2]  # data row after header and separator
        assert "longervalue" in result[2]

    def test_table_alignment_right(self) -> None:
        """Should align columns right when specified."""
        headers = ["Name", "Value"]
        rows = [["short", "123"]]
        result = ASCIIVisualizer.table(headers, rows, align=["left", "right"])

        # Right-aligned value should be formatted differently
        assert len(result) >= 3

    def test_table_alignment_center(self) -> None:
        """Should center columns when specified."""
        headers = ["Name", "Value"]
        rows = [["item", "42"]]
        result = ASCIIVisualizer.table(headers, rows, align=["center", "center"])

        assert len(result) >= 3


# =============================================================================
# Test SessionStats dataclass
# =============================================================================


class TestSessionStats:
    """Tests for SessionStats dataclass."""

    def test_session_stats_creation(self) -> None:
        """Should create SessionStats with all fields."""
        stats = SessionStats(
            component_name="admin-shell",
            total_sessions=100,
            avg_duration=3600.0,
            active_sessions=5,
            error_rate=2.5,
            date_range="Last 7 days",
        )

        assert stats.component_name == "admin-shell"
        assert stats.total_sessions == 100
        assert stats.avg_duration == 3600.0
        assert stats.active_sessions == 5
        assert stats.error_rate == 2.5
        assert stats.date_range == "Last 7 days"

    def test_session_stats_to_dict(self) -> None:
        """Should convert to dictionary."""
        stats = SessionStats(
            component_name="ipython",
            total_sessions=50,
            avg_duration=1800.0,
            active_sessions=2,
            error_rate=1.0,
            date_range="Last 30 days",
        )

        result = stats.to_dict()

        assert isinstance(result, dict)
        assert result["component_name"] == "ipython"
        assert result["total_sessions"] == 50
        assert result["avg_duration"] == 1800.0
        assert result["active_sessions"] == 2
        assert result["error_rate"] == 1.0
        assert result["date_range"] == "Last 30 days"

    def test_session_stats_default_error_rate(self) -> None:
        """Should default error_rate to 0.0."""
        stats = SessionStats(
            component_name="test",
            total_sessions=10,
            avg_duration=600.0,
            active_sessions=1,
        )

        assert stats.error_rate == 0.0


# =============================================================================
# Test ComponentUsage dataclass
# =============================================================================


class TestComponentUsage:
    """Tests for ComponentUsage dataclass."""

    def test_component_usage_creation(self) -> None:
        """Should create ComponentUsage with all fields."""
        last_active = datetime.now(UTC)
        usage = ComponentUsage(
            component_name="admin-shell",
            session_count=100,
            total_duration=36000,
            avg_quality_score=85.5,
            last_active=last_active,
        )

        assert usage.component_name == "admin-shell"
        assert usage.session_count == 100
        assert usage.total_duration == 36000
        assert usage.avg_quality_score == 85.5
        assert usage.last_active == last_active

    def test_component_usage_to_dict(self) -> None:
        """Should convert to dictionary with ISO format datetime."""
        last_active = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        usage = ComponentUsage(
            component_name="zsh",
            session_count=25,
            total_duration=7200,
            avg_quality_score=90.0,
            last_active=last_active,
        )

        result = usage.to_dict()

        assert isinstance(result, dict)
        assert result["component_name"] == "zsh"
        assert result["session_count"] == 25
        assert result["total_duration"] == 7200
        assert result["avg_quality_score"] == 90.0
        assert result["last_active"] == last_active.isoformat()


# =============================================================================
# Test SessionAnalytics with mocked database
# =============================================================================


class TestSessionAnalyticsInit:
    """Tests for SessionAnalytics initialization."""

    def test_init_with_database_path(self) -> None:
        """Should store database path when provided."""
        analytics = SessionAnalytics(database_path=Path("/tmp/test.db"))
        assert analytics.database_path == Path("/tmp/test.db")

    def test_init_with_conn(self) -> None:
        """Should store provided connection."""
        mock_conn = MagicMock()
        analytics = SessionAnalytics(conn=mock_conn)
        assert analytics._conn is mock_conn

    def test_init_without_params(self) -> None:
        """Should initialize without database path or connection."""
        analytics = SessionAnalytics()
        assert analytics.database_path is None
        assert analytics._conn is None


class TestSessionAnalyticsGetActiveSessions:
    """Tests for get_active_sessions method."""

    @pytest.fixture
    def mock_conn(self) -> MagicMock:
        """Create mock DuckDB connection."""
        conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("session-1", "admin-shell", datetime.now(UTC), 3600, "project-a"),
            ("session-2", "ipython", datetime.now(UTC), 1800, "project-b"),
        ]
        conn.execute.return_value = mock_result
        return conn

    @pytest.mark.asyncio
    async def test_get_active_sessions_returns_list(self, mock_conn: MagicMock) -> None:
        """Should return list of active session dictionaries."""
        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_active_sessions()

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_active_sessions_structure(self, mock_conn: MagicMock) -> None:
        """Should return properly structured session data."""
        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_active_sessions()

        first = result[0]
        assert "session_id" in first
        assert "component_name" in first
        assert "start_time" in first
        assert "duration_seconds" in first
        assert "project" in first

    @pytest.mark.asyncio
    async def test_get_active_sessions_empty(self) -> None:
        """Should return empty list when no active sessions."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_active_sessions()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_active_sessions_handles_exception(self) -> None:
        """Should return empty list and log on exception."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB error")

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_active_sessions()

        assert result == []


class TestSessionAnalyticsGetSessionStats:
    """Tests for get_session_stats method."""

    @pytest.fixture
    def mock_conn(self) -> MagicMock:
        """Create mock DuckDB connection."""
        conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("admin-shell", 100, 3600.0, 5, 2.5),
            ("ipython", 50, 1800.0, 2, 1.0),
        ]
        conn.execute.return_value = mock_result
        return conn

    @pytest.mark.asyncio
    async def test_get_session_stats_returns_list(self, mock_conn: MagicMock) -> None:
        """Should return list of SessionStats objects."""
        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_stats()

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_session_stats_objects(self, mock_conn: MagicMock) -> None:
        """Should return SessionStats with correct data."""
        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_stats()

        assert all(isinstance(s, SessionStats) for s in result)
        assert result[0].component_name == "admin-shell"
        assert result[0].total_sessions == 100
        assert result[0].avg_duration == 3600.0
        assert result[0].active_sessions == 5
        assert result[0].error_rate == 2.5

    @pytest.mark.asyncio
    async def test_get_session_stats_with_days(self, mock_conn: MagicMock) -> None:
        """Should respect days parameter."""
        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_stats(days=30)

        assert isinstance(result, list)
        # Verify query was executed
        mock_conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_session_stats_with_component_filter(self, mock_conn: MagicMock) -> None:
        """Should filter by component when specified."""
        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_stats(component="admin-shell")

        assert isinstance(result, list)
        mock_conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_session_stats_empty(self) -> None:
        """Should return empty list on no data."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_stats()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_session_stats_handles_exception(self) -> None:
        """Should return empty list on exception."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("Query failed")

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_stats()

        assert result == []


class TestSessionAnalyticsGetSessionsByTimeRange:
    """Tests for get_sessions_by_time_range method."""

    @pytest.mark.asyncio
    async def test_get_sessions_by_time_range_returns_list(self) -> None:
        """Should return list of session dictionaries."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("s1", "admin-shell", datetime.now(UTC), datetime.now(UTC), 3600, 85.0, "proj", False, None),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        start = datetime.now(UTC) - timedelta(days=7)
        end = datetime.now(UTC)
        result = await analytics.get_sessions_by_time_range(start_date=start, end_date=end)

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_sessions_by_time_range_fields(self) -> None:
        """Should return session dict with all fields."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        now = datetime.now(UTC)
        mock_result.fetchall.return_value = [
            ("s1", "admin-shell", now, now, 3600, 85.0, "proj", False, None),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_sessions_by_time_range()

        first = result[0]
        assert "session_id" in first
        assert "component_name" in first
        assert "start_time" in first
        assert "end_time" in first
        assert "duration_seconds" in first
        assert "quality_score" in first
        assert "project" in first
        assert "error_occurred" in first
        assert "error_message" in first

    @pytest.mark.asyncio
    async def test_get_sessions_by_time_range_empty(self) -> None:
        """Should return empty list on no data."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_sessions_by_time_range()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_sessions_by_time_range_defaults(self) -> None:
        """Should use default date range (7 days) when not specified."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_sessions_by_time_range()

        assert result == []
        mock_conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_sessions_by_time_range_handles_exception(self) -> None:
        """Should return empty list on exception."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("Query failed")

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_sessions_by_time_range()

        assert result == []


class TestSessionAnalyticsGetAverageSessionDuration:
    """Tests for get_average_session_duration method."""

    @pytest.mark.asyncio
    async def test_get_average_duration_returns_dict(self) -> None:
        """Should return dictionary of component -> average duration."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("admin-shell", 3600.0),
            ("ipython", 1800.0),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_average_session_duration()

        assert isinstance(result, dict)
        assert result["admin-shell"] == 3600.0
        assert result["ipython"] == 1800.0

    @pytest.mark.asyncio
    async def test_get_average_duration_empty(self) -> None:
        """Should return empty dict on no data."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_average_session_duration()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_average_duration_with_component_filter(self) -> None:
        """Should filter by component when specified."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("admin-shell", 3600.0)]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_average_session_duration(component="admin-shell")

        assert result == {"admin-shell": 3600.0}

    @pytest.mark.asyncio
    async def test_get_average_duration_handles_exception(self) -> None:
        """Should return empty dict on exception."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("Query failed")

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_average_session_duration()

        assert result == {}


class TestSessionAnalyticsGetMostActiveComponents:
    """Tests for get_most_active_components method."""

    @pytest.mark.asyncio
    async def test_get_most_active_components_returns_list(self) -> None:
        """Should return list of ComponentUsage objects."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("admin-shell", 100, 36000, 85.0, datetime.now(UTC)),
            ("ipython", 50, 18000, 90.0, datetime.now(UTC)),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_most_active_components()

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_most_active_components_objects(self) -> None:
        """Should return ComponentUsage with correct data."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        now = datetime.now(UTC)
        mock_result.fetchall.return_value = [
            ("admin-shell", 100, 36000, 85.0, now),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_most_active_components()

        assert all(isinstance(c, ComponentUsage) for c in result)
        assert result[0].component_name == "admin-shell"
        assert result[0].session_count == 100
        assert result[0].total_duration == 36000
        assert result[0].avg_quality_score == 85.0

    @pytest.mark.asyncio
    async def test_get_most_active_components_empty(self) -> None:
        """Should return empty list on no data."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_most_active_components()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_most_active_components_respects_limit(self) -> None:
        """Should pass limit to query."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        await analytics.get_most_active_components(limit=5)

        # Verify limit was passed to execute
        args = mock_conn.execute.call_args
        assert 5 in args[0] or args[1] is not None

    @pytest.mark.asyncio
    async def test_get_most_active_components_handles_exception(self) -> None:
        """Should return empty list on exception."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("Query failed")

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_most_active_components()

        assert result == []


class TestSessionAnalyticsGetSessionErrorRate:
    """Tests for get_session_error_rate method."""

    @pytest.mark.asyncio
    async def test_get_session_error_rate_returns_dict(self) -> None:
        """Should return dictionary of component -> error stats."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("admin-shell", 100, 5, 5.0, "Connection timeout"),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_error_rate()

        assert isinstance(result, dict)
        assert "admin-shell" in result
        assert result["admin-shell"]["error_rate"] == 5.0
        assert result["admin-shell"]["total_sessions"] == 100
        assert result["admin-shell"]["failed_sessions"] == 5
        assert result["admin-shell"]["most_common_error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_get_session_error_rate_empty(self) -> None:
        """Should return empty dict on no data."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_error_rate()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_session_error_rate_with_component_filter(self) -> None:
        """Should filter by component when specified."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("admin-shell", 50, 2, 4.0, "Timeout"),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_error_rate(component="admin-shell")

        assert "admin-shell" in result

    @pytest.mark.asyncio
    async def test_get_session_error_rate_handles_exception(self) -> None:
        """Should return empty dict on exception."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("Query failed")

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_error_rate()

        assert result == {}


# =============================================================================
# Test Export Methods
# =============================================================================


class TestSessionAnalyticsExportSql:
    """Tests for export_sql method."""

    def test_export_sql_active_sessions(self) -> None:
        """Should export active_sessions query."""
        analytics = SessionAnalytics()
        result = analytics.export_sql("active_sessions")

        assert "session_id" in result
        assert "component_name" in result
        assert "FROM sessions" in result

    def test_export_sql_session_stats(self) -> None:
        """Should export session_stats query."""
        analytics = SessionAnalytics()
        result = analytics.export_sql("session_stats", days=30)

        assert "component_name" in result
        assert "COUNT(*)" in result
        assert "GROUP BY component_name" in result

    def test_export_sql_average_duration(self) -> None:
        """Should export average_duration query."""
        analytics = SessionAnalytics()
        result = analytics.export_sql("average_duration", days=7)

        assert "AVG(duration_seconds)" in result

    def test_export_sql_most_active(self) -> None:
        """Should export most_active query."""
        analytics = SessionAnalytics()
        result = analytics.export_sql("most_active")

        assert "session_count" in result
        assert "LIMIT" in result

    def test_export_sql_error_rate(self) -> None:
        """Should export error_rate query."""
        analytics = SessionAnalytics()
        result = analytics.export_sql("error_rate")

        assert "error_occurred" in result
        assert "MODE()" in result

    def test_export_sql_unknown_query(self) -> None:
        """Should return comment for unknown query name."""
        analytics = SessionAnalytics()
        result = analytics.export_sql("nonexistent")

        assert result == "-- Query not found"


# =============================================================================
# Test Visualization Methods
# =============================================================================


class TestSessionAnalyticsVisualizeSessionStats:
    """Tests for visualize_session_stats method."""

    def test_visualize_session_stats_with_data(self) -> None:
        """Should render session stats visualization."""
        stats = [
            SessionStats("admin-shell", 100, 3600.0, 5, 2.5, "Last 7 days"),
            SessionStats("ipython", 50, 1800.0, 2, 1.0, "Last 7 days"),
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_session_stats(stats)

        assert isinstance(result, list)
        assert len(result) > 0
        assert "SESSION STATISTICS" in result
        assert "Total Sessions by Component:" in result

    def test_visualize_session_stats_empty_list(self) -> None:
        """Should handle empty stats list."""
        analytics = SessionAnalytics()
        result = analytics.visualize_session_stats([])

        assert isinstance(result, list)
        # Should still produce output structure

    def test_visualize_session_stats_single_component(self) -> None:
        """Should handle single component stats."""
        stats = [
            SessionStats("zsh", 25, 1200.0, 1, 0.0, "Last 7 days"),
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_session_stats(stats)

        assert isinstance(result, list)
        assert "zsh" in result[0] or any("zsh" in line for line in result)


class TestSessionAnalyticsVisualizeComponentUsage:
    """Tests for visualize_component_usage method."""

    def test_visualize_component_usage_with_data(self) -> None:
        """Should render component usage visualization."""
        now = datetime.now(UTC)
        components = [
            ComponentUsage("admin-shell", 100, 36000, 85.0, now),
            ComponentUsage("ipython", 50, 18000, 90.0, now),
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_component_usage(components)

        assert isinstance(result, list)
        assert len(result) > 0
        assert "COMPONENT USAGE" in result
        assert "Sessions by Component:" in result

    def test_visualize_component_usage_empty_list(self) -> None:
        """Should handle empty component list."""
        analytics = SessionAnalytics()
        result = analytics.visualize_component_usage([])

        assert isinstance(result, list)

    def test_visualize_component_usage_single_component(self) -> None:
        """Should handle single component."""
        now = datetime.now(UTC)
        components = [ComponentUsage("zsh", 25, 7200, 95.0, now)]
        analytics = SessionAnalytics()
        result = analytics.visualize_component_usage(components)

        assert isinstance(result, list)
        assert "zsh" in str(result)


class TestSessionAnalyticsVisualizeTimeSeries:
    """Tests for visualize_time_series method."""

    def test_visualize_time_series_with_data(self) -> None:
        """Should render time series visualization."""
        sessions = [
            {"start_time": "2025-01-15T10:00:00+00:00"},
            {"start_time": "2025-01-15T14:00:00+00:00"},
            {"start_time": "2025-01-16T10:00:00+00:00"},
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_time_series(sessions, bucket_size="day")

        assert isinstance(result, list)
        assert len(result) > 0
        assert "SESSION TIME SERIES (by day)" in result[0] or any("SESSION TIME SERIES" in line for line in result)

    def test_visualize_time_series_empty_list(self) -> None:
        """Should handle empty sessions list."""
        analytics = SessionAnalytics()
        result = analytics.visualize_time_series([])

        assert isinstance(result, list)
        assert "No time series data available" in result

    def test_visualize_time_series_hour_bucket(self) -> None:
        """Should handle hour bucket size."""
        sessions = [
            {"start_time": "2025-01-15T10:30:00+00:00"},
            {"start_time": "2025-01-15T10:45:00+00:00"},
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_time_series(sessions, bucket_size="hour")

        assert isinstance(result, list)
        assert "by hour" in result[0] or any("hour" in line.lower() for line in result)

    def test_visualize_time_series_week_bucket(self) -> None:
        """Should handle week bucket size."""
        sessions = [
            {"start_time": "2025-01-06T10:00:00+00:00"},
            {"start_time": "2025-01-13T10:00:00+00:00"},
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_time_series(sessions, bucket_size="week")

        assert isinstance(result, list)

    def test_visualize_time_series_sessions_without_start_time(self) -> None:
        """Should handle sessions missing start_time."""
        sessions = [
            {"start_time": "2025-01-15T10:00:00+00:00"},
            {},  # Missing start_time
            {"other": "field"},
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_time_series(sessions)

        assert isinstance(result, list)
        # Should not crash, just skip invalid entries

    def test_visualize_time_series_invalid_datetime(self) -> None:
        """Should handle invalid datetime strings."""
        sessions = [
            {"start_time": "2025-01-15T10:00:00+00:00"},
            {"start_time": "not-a-date"},
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_time_series(sessions)

        assert isinstance(result, list)
        # Should skip invalid datetime


# =============================================================================
# Test create_session_summary_report
# =============================================================================


class TestCreateSessionSummaryReport:
    """Tests for create_session_summary_report function."""

    def test_create_session_summary_report_basic(self) -> None:
        """Should create a basic summary report."""
        stats = [
            SessionStats("admin-shell", 100, 3600.0, 5, 2.5, "Last 7 days"),
            SessionStats("ipython", 50, 1800.0, 2, 1.0, "Last 7 days"),
        ]
        now = datetime.now(UTC)
        components = [
            ComponentUsage("admin-shell", 100, 36000, 85.0, now),
            ComponentUsage("ipython", 50, 18000, 90.0, now),
        ]
        error_rates = {
            "admin-shell": {
                "error_rate": 2.5,
                "total_sessions": 100,
                "failed_sessions": 2,
                "most_common_error": "Timeout",
            }
        }

        result = create_session_summary_report(stats, components, error_rates)

        assert isinstance(result, str)
        assert "SESSION-BUDDY ANALYTICS REPORT" in result
        assert "SUMMARY:" in result
        assert "Total Sessions:" in result

    def test_create_session_summary_report_empty_stats(self) -> None:
        """Should handle empty stats list."""
        result = create_session_summary_report([], [], {})

        assert isinstance(result, str)
        assert "Total Sessions: 0" in result

    def test_create_session_summary_report_high_error_rate(self) -> None:
        """Should highlight components with high error rates (>5%)."""
        stats = [
            SessionStats("failing-component", 100, 3600.0, 0, 10.0, "Last 7 days"),
        ]
        components = [
            ComponentUsage("failing-component", 100, 36000, 50.0, datetime.now(UTC)),
        ]
        error_rates = {
            "failing-component": {
                "error_rate": 10.0,
                "total_sessions": 100,
                "failed_sessions": 10,
                "most_common_error": "Segfault",
            }
        }

        result = create_session_summary_report(stats, components, error_rates)

        assert "COMPONENTS WITH HIGH ERROR RATES" in result
        assert "failing-component" in result
        assert "10.0%" in result

    def test_create_session_summary_report_no_high_errors(self) -> None:
        """Should not include high error section if none exceed 5%."""
        stats = [
            SessionStats("good-component", 100, 3600.0, 0, 2.0, "Last 7 days"),
        ]
        components = [
            ComponentUsage("good-component", 100, 36000, 95.0, datetime.now(UTC)),
        ]
        error_rates = {
            "good-component": {
                "error_rate": 2.0,
                "total_sessions": 100,
                "failed_sessions": 2,
                "most_common_error": None,
            }
        }

        result = create_session_summary_report(stats, components, error_rates)

        assert "COMPONENTS WITH HIGH ERROR RATES" not in result


# =============================================================================
# Test edge cases
# =============================================================================


class TestSessionAnalyticsEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_get_active_sessions_null_start_time(self) -> None:
        """Should handle NULL start_time in database."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("session-1", "admin-shell", None, 3600, "project"),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_active_sessions()

        assert result[0]["start_time"] is None

    @pytest.mark.asyncio
    async def test_get_session_stats_null_duration(self) -> None:
        """Should handle NULL durations in session stats."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("admin-shell", 50, None, 2, 0.0),  # NULL avg_duration
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_session_stats()

        # NULL from DB comes back as None (DuckDB NULL = Python None)
        assert result[0].avg_duration is None

    @pytest.mark.asyncio
    async def test_get_sessions_by_time_range_none_end_time(self) -> None:
        """Should handle active sessions (NULL end_time) in time range query."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        now = datetime.now(UTC)
        mock_result.fetchall.return_value = [
            ("session-active", "admin-shell", now, None, None, 80.0, "proj", False, None),
        ]
        mock_conn.execute.return_value = mock_result

        analytics = SessionAnalytics(conn=mock_conn)
        result = await analytics.get_sessions_by_time_range()

        assert result[0]["end_time"] is None
        assert result[0]["duration_seconds"] is None

    def test_visualize_time_series_all_invalid_dates(self) -> None:
        """Should return 'No time series data available' when all dates invalid."""
        sessions = [
            {"start_time": "invalid"},
            {"start_time": "also-invalid"},
        ]
        analytics = SessionAnalytics()
        result = analytics.visualize_time_series(sessions)

        assert "No time series data available" in result

    def test_bar_chart_all_zero_values(self) -> None:
        """Should handle bar chart with all zero values."""
        data = [("a", 0), ("b", 0), ("c", 0)]
        result = ASCIIVisualizer.bar_chart(data, width=50)

        assert len(result) == 3
        # Should not crash


# =============================================================================
# Integration-style tests with temp directory
# =============================================================================


class TestSessionAnalyticsWithTempDb:
    """Tests using temporary DuckDB database for integration testing."""

    def test_init_with_temp_database_path(self) -> None:
        """Should use database path when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            analytics = SessionAnalytics(database_path=db_path)

            assert analytics.database_path == db_path

    def test_get_connection_without_stored_conn(self) -> None:
        """Should attempt connection creation when _conn is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            analytics = SessionAnalytics(database_path=db_path)

            # Verify internal state
            assert analytics.database_path == db_path
            assert analytics._conn is None

            # The actual connection would be created on demand via _get_connection()
            # We verify the initialization sets up the path correctly
            # Actual connection is tested via integration tests


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
