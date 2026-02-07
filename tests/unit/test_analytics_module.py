"""Unit tests for analytics.session_analytics module.

Tests the new SessionAnalytics class for session statistics,
visualization, and reporting capabilities.
"""

from __future__ import annotations

import typing as t
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from session_buddy.analytics.session_analytics import (
    ASCIIVisualizer,
    ComponentUsage,
    SessionAnalytics,
    SessionStats,
    create_session_summary_report,
)


class TestSessionAnalytics:
    """Test SessionAnalytics class."""

    @pytest.fixture
    def mock_connection(self):
        """Create mock database connection."""
        conn = MagicMock()
        return conn

    @pytest.fixture
    def analytics(self, mock_connection):
        """Create SessionAnalytics instance with mock connection."""
        return SessionAnalytics(conn=mock_connection)

    def test_init_with_database_path(self):
        """Test initialization with database path."""
        analytics = SessionAnalytics(database_path=Path("/tmp/test.duckdb"))
        assert analytics.database_path == Path("/tmp/test.duckdb")
        assert analytics._conn is None

    def test_init_with_connection(self, mock_connection):
        """Test initialization with existing connection."""
        analytics = SessionAnalytics(conn=mock_connection)
        assert analytics._conn == mock_connection

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, analytics, mock_connection):
        """Test getting active sessions."""
        # Mock query result
        mock_connection.execute.return_value.fetchall.return_value = [
            (
                "session-1",
                "admin-shell",
                datetime(2025, 1, 15, 14, 30, tzinfo=UTC),
                7200,
                "test-project",
            ),
            (
                "session-2",
                "ipython",
                datetime(2025, 1, 15, 15, 0, tzinfo=UTC),
                3600,
                "test-project",
            ),
        ]

        sessions = await analytics.get_active_sessions()

        assert len(sessions) == 2
        assert sessions[0]["session_id"] == "session-1"
        assert sessions[0]["component_name"] == "admin-shell"
        assert sessions[0]["duration_seconds"] == 7200
        assert sessions[1]["component_name"] == "ipython"

    @pytest.mark.asyncio
    async def test_get_session_stats(self, analytics, mock_connection):
        """Test getting session statistics."""
        mock_connection.execute.return_value.fetchall.return_value = [
            ("admin-shell", 100, 450.0, 5, 2.5),
            ("ipython", 80, 600.0, 3, 1.2),
        ]

        stats = await analytics.get_session_stats(days=7)

        assert len(stats) == 2
        assert stats[0].component_name == "admin-shell"
        assert stats[0].total_sessions == 100
        assert stats[0].avg_duration == 450.0
        assert stats[0].active_sessions == 5
        assert stats[0].error_rate == 2.5

    @pytest.mark.asyncio
    async def test_get_session_stats_with_component_filter(
        self, analytics, mock_connection
    ):
        """Test getting session stats with component filter."""
        mock_connection.execute.return_value.fetchall.return_value = [
            ("admin-shell", 50, 450.0, 2, 1.5),
        ]

        stats = await analytics.get_session_stats(days=7, component="admin-shell")

        assert len(stats) == 1
        assert stats[0].component_name == "admin-shell"

    @pytest.mark.asyncio
    async def test_get_sessions_by_time_range(self, analytics, mock_connection):
        """Test getting sessions by time range."""
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 31, tzinfo=UTC)

        mock_connection.execute.return_value.fetchall.return_value = [
            (
                "session-1",
                "admin-shell",
                datetime(2025, 1, 15, tzinfo=UTC),
                datetime(2025, 1, 15, 1, tzinfo=UTC),
                3600,
                85.0,
                "test-project",
                False,
                None,
            ),
        ]

        sessions = await analytics.get_sessions_by_time_range(
            start_date=start, end_date=end
        )

        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "session-1"
        assert sessions[0]["quality_score"] == 85.0

    @pytest.mark.asyncio
    async def test_get_average_session_duration(self, analytics, mock_connection):
        """Test getting average session duration."""
        mock_connection.execute.return_value.fetchall.return_value = [
            ("admin-shell", 450.0),
            ("ipython", 600.0),
        ]

        durations = await analytics.get_average_session_duration(days=7)

        assert durations["admin-shell"] == 450.0
        assert durations["ipython"] == 600.0

    @pytest.mark.asyncio
    async def test_get_most_active_components(self, analytics, mock_connection):
        """Test getting most active components."""
        mock_connection.execute.return_value.fetchall.return_value = [
            ("admin-shell", 100, 45000, 75.5, datetime(2025, 1, 15, tzinfo=UTC)),
            ("ipython", 80, 48000, 82.1, datetime(2025, 1, 14, tzinfo=UTC)),
        ]

        components = await analytics.get_most_active_components(days=7, limit=10)

        assert len(components) == 2
        assert components[0].component_name == "admin-shell"
        assert components[0].session_count == 100
        assert components[0].avg_quality_score == 75.5

    @pytest.mark.asyncio
    async def test_get_session_error_rate(self, analytics, mock_connection):
        """Test getting session error rate."""
        mock_connection.execute.return_value.fetchall.return_value = [
            ("admin-shell", 100, 5, 5.0, "Connection timeout"),
            ("ipython", 80, 1, 1.25, None),
        ]

        error_rates = await analytics.get_session_error_rate(days=7)

        assert len(error_rates) == 2
        assert error_rates["admin-shell"]["error_rate"] == 5.0
        assert error_rates["admin-shell"]["total_sessions"] == 100
        assert error_rates["admin-shell"]["failed_sessions"] == 5
        assert error_rates["admin-shell"]["most_common_error"] == "Connection timeout"

    def test_export_sql(self, analytics):
        """Test SQL export functionality."""
        sql = analytics.export_sql("active_sessions", days=7)

        assert "SELECT" in sql
        assert "FROM sessions" in sql
        assert "WHERE end_time IS NULL" in sql

    def test_export_sql_invalid_query(self, analytics):
        """Test SQL export with invalid query name."""
        sql = analytics.export_sql("invalid_query", days=7)

        assert sql == "-- Query not found"


class TestASCIIVisualizer:
    """Test ASCIIVisualizer class."""

    def test_bar_chart(self):
        """Test bar chart generation."""
        visualizer = ASCIIVisualizer()
        data = [("Component A", 100), ("Component B", 75), ("Component C", 50)]

        chart = visualizer.bar_chart(data, width=20)

        assert len(chart) == 3
        assert "Component A" in chart[0]
        assert "█" in chart[0]

    def test_bar_chart_empty_data(self):
        """Test bar chart with empty data."""
        visualizer = ASCIIVisualizer()
        chart = visualizer.bar_chart([])

        assert chart == ["No data available"]

    def test_sparkline(self):
        """Test sparkline generation."""
        visualizer = ASCIIVisualizer()
        values = [1, 2, 3, 5, 8, 13, 21, 13, 8, 5, 3, 2, 1]

        sparkline = visualizer.sparkline(values)

        assert len(sparkline) == len(values)
        assert "█" in sparkline

    def test_sparkline_empty(self):
        """Test sparkline with empty data."""
        visualizer = ASCIIVisualizer()
        sparkline = visualizer.sparkline([])

        assert sparkline == "No data"

    def test_table(self):
        """Test table generation."""
        visualizer = ASCIIVisualizer()
        headers = ["Name", "Value", "Status"]
        rows = [
            ["Item 1", "100", "Active"],
            ["Item 2", "75", "Pending"],
        ]

        table = visualizer.table(headers, rows)

        assert len(table) == 4  # header + separator + 2 rows
        assert "Name" in table[0]
        assert "Item 1" in table[2]

    def test_table_with_alignment(self):
        """Test table with custom alignment."""
        visualizer = ASCIIVisualizer()
        headers = ["Name", "Value"]
        rows = [["Item 1", "100"]]

        table = visualizer.table(headers, rows, align=["left", "right"])

        assert len(table) == 3


class TestDataClasses:
    """Test data classes."""

    def test_session_stats_to_dict(self):
        """Test SessionStats to_dict conversion."""
        stats = SessionStats(
            component_name="admin-shell",
            total_sessions=100,
            avg_duration=450.0,
            active_sessions=5,
            error_rate=2.5,
            date_range="Last 7 days",
        )

        data = stats.to_dict()

        assert data["component_name"] == "admin-shell"
        assert data["total_sessions"] == 100
        assert data["avg_duration"] == 450.0
        assert data["active_sessions"] == 5
        assert data["error_rate"] == 2.5

    def test_component_usage_to_dict(self):
        """Test ComponentUsage to_dict conversion."""
        usage = ComponentUsage(
            component_name="admin-shell",
            session_count=100,
            total_duration=45000,
            avg_quality_score=75.5,
            last_active=datetime(2025, 1, 15, tzinfo=UTC),
        )

        data = usage.to_dict()

        assert data["component_name"] == "admin-shell"
        assert data["session_count"] == 100
        assert data["total_duration"] == 45000
        assert data["avg_quality_score"] == 75.5
        assert "2025-01-15" in data["last_active"]


class TestVisualizationMethods:
    """Test visualization methods."""

    def test_visualize_session_stats(self):
        """Test session statistics visualization."""
        analytics = SessionAnalytics()
        stats = [
            SessionStats(
                component_name="admin-shell",
                total_sessions=100,
                avg_duration=450.0,
                active_sessions=5,
                error_rate=2.5,
            ),
            SessionStats(
                component_name="ipython",
                total_sessions=80,
                avg_duration=600.0,
                active_sessions=3,
                error_rate=1.2,
            ),
        ]

        output = analytics.visualize_session_stats(stats)

        assert len(output) > 0
        assert any("SESSION STATISTICS" in line for line in output)
        assert any("admin-shell" in line for line in output)

    def test_visualize_component_usage(self):
        """Test component usage visualization."""
        analytics = SessionAnalytics()
        components = [
            ComponentUsage(
                component_name="admin-shell",
                session_count=100,
                total_duration=45000,
                avg_quality_score=75.5,
                last_active=datetime(2025, 1, 15, tzinfo=UTC),
            ),
        ]

        output = analytics.visualize_component_usage(components)

        assert len(output) > 0
        assert any("COMPONENT USAGE" in line for line in output)
        assert any("admin-shell" in line for line in output)

    def test_visualize_time_series(self):
        """Test time series visualization."""
        analytics = SessionAnalytics()
        sessions = [
            {
                "session_id": "session-1",
                "start_time": "2025-01-15T14:30:00Z",
                "component_name": "admin-shell",
            },
            {
                "session_id": "session-2",
                "start_time": "2025-01-16T15:30:00Z",
                "component_name": "ipython",
            },
        ]

        output = analytics.visualize_time_series(sessions, bucket_size="day")

        assert len(output) > 0
        assert any("TIME SERIES" in line for line in output)


class TestReportGeneration:
    """Test report generation."""

    def test_create_session_summary_report(self):
        """Test comprehensive report generation."""
        stats = [
            SessionStats(
                component_name="admin-shell",
                total_sessions=100,
                avg_duration=450.0,
                active_sessions=5,
                error_rate=2.5,
            )
        ]

        components = [
            ComponentUsage(
                component_name="admin-shell",
                session_count=100,
                total_duration=45000,
                avg_quality_score=75.5,
                last_active=datetime(2025, 1, 15, tzinfo=UTC),
            )
        ]

        error_rates = {
            "admin-shell": {
                "error_rate": 2.5,
                "total_sessions": 100,
                "failed_sessions": 5,
                "most_common_error": "Connection timeout",
            }
        }

        report = create_session_summary_report(stats, components, error_rates)

        assert "SESSION-BUDDY ANALYTICS REPORT" in report
        assert "Total Sessions: 100" in report
        assert "admin-shell" in report
        assert "2.50%" in report
