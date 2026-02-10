"""Session analytics and visualization for Session-Buddy.

This module provides comprehensive analytics capabilities for understanding
session patterns, component usage, and system performance.

Features:
- Query methods for session statistics and patterns
- Export capabilities (SQL, Python methods, CLI commands)
- ASCII visualization for terminal output
- Integration with external visualization tools (Grafana, etc.)
"""

from __future__ import annotations

import logging
import typing as t
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SessionStats:
    """Session statistics data structure.

    Attributes:
        component_name: Name of the component/shell type
        total_sessions: Total number of sessions
        avg_duration: Average session duration in seconds
        active_sessions: Number of currently active sessions
        error_rate: Error rate as percentage (0-100)
        date_range: Date range for these statistics
    """

    component_name: str
    total_sessions: int
    avg_duration: float
    active_sessions: int
    error_rate: float = 0.0
    date_range: str = ""

    def to_dict(self) -> dict[str, t.Any]:
        """Convert to dictionary for serialization."""
        return {
            "component_name": self.component_name,
            "total_sessions": self.total_sessions,
            "avg_duration": self.avg_duration,
            "active_sessions": self.active_sessions,
            "error_rate": self.error_rate,
            "date_range": self.date_range,
        }


@dataclass
class ComponentUsage:
    """Component usage statistics.

    Attributes:
        component_name: Name of the component
        session_count: Number of sessions
        total_duration: Total duration in seconds
        avg_quality_score: Average quality score
        last_active: Last active timestamp
    """

    component_name: str
    session_count: int
    total_duration: int
    avg_quality_score: float
    last_active: datetime

    def to_dict(self) -> dict[str, t.Any]:
        """Convert to dictionary for serialization."""
        return {
            "component_name": self.component_name,
            "session_count": self.session_count,
            "total_duration": self.total_duration,
            "avg_quality_score": self.avg_quality_score,
            "last_active": self.last_active.isoformat(),
        }


class ASCIIVisualizer:
    """ASCII chart visualization for terminal output."""

    @staticmethod
    def bar_chart(data: list[tuple[str, int]], width: int = 50) -> list[str]:
        """Generate horizontal bar chart.

        Args:
            data: List of (label, value) tuples
            width: Maximum bar width in characters

        Returns:
            List of strings representing the chart
        """
        if not data:
            return ["No data available"]

        max_value = max(value for _, value in data) if data else 1
        lines: list[str] = []

        for label, value in data:
            # Calculate bar length
            bar_length = int((value / max_value) * width) if max_value > 0 else 0
            bar = "█" * bar_length

            # Format line
            lines.append(f"{label:20} {value:6d} {bar}")

        return lines

    @staticmethod
    def sparkline(values: list[int], width: int = 40) -> str:
        """Generate sparkline for time series data.

        Args:
            values: List of numeric values
            width: Maximum width of sparkline

        Returns:
            Sparkline string using Unicode characters
        """
        if not values:
            return "No data"

        # Normalize values to 0-7 range for sparkline characters
        min_val = min(values)
        max_val = max(values)
        range_val = max_val - min_val if max_val != min_val else 1

        # Sparkline characters from lowest to highest
        spark_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

        sparkline = ""
        for value in values:
            normalized = int((value - min_val) / range_val * 7)
            sparkline += spark_chars[max(0, min(7, normalized))]

        return sparkline

    @staticmethod
    def table(
        headers: list[str], rows: list[list[str]], align: list[str] | None = None
    ) -> list[str]:
        """Generate ASCII table.

        Args:
            headers: Column headers
            rows: Table rows
            align: List of alignment strings ('left', 'right', 'center')

        Returns:
            List of strings representing the table
        """
        if not headers or not rows:
            return ["No data available"]

        # Calculate column widths
        col_widths = [
            max(len(str(headers[i])), max(len(str(row[i])) for row in rows))
            for i in range(len(headers))
        ]

        # Default alignment to left
        if align is None:
            align = ["left"] * len(headers)

        lines: list[str] = []

        # Header row
        header_parts = []
        for i, (header, width) in enumerate(zip(headers, col_widths)):
            if align[i] == "right":
                header_parts.append(f"{header:>{width}}")
            elif align[i] == "center":
                header_parts.append(f"{header:^{width}}")
            else:
                header_parts.append(f"{header:<{width}}")
        lines.append(" | ".join(header_parts))

        # Separator
        separator = " | ".join("-" * width for width in col_widths)
        lines.append(separator)

        # Data rows
        for row in rows:
            row_parts = []
            for i, (cell, width) in enumerate(zip(row, col_widths)):
                if align[i] == "right":
                    row_parts.append(f"{str(cell):>{width}}")
                elif align[i] == "center":
                    row_parts.append(f"{str(cell):^{width}}")
                else:
                    row_parts.append(f"{str(cell):<{width}}")
            lines.append(" | ".join(row_parts))

        return lines


class SessionAnalytics:
    """Session analytics and visualization for Session-Buddy.

    This class provides comprehensive query methods for analyzing session
    data, including active sessions, statistics, time ranges, durations,
    component usage, and error rates.

    Example usage:
        ```python
        from session_buddy.analytics.session_analytics import SessionAnalytics

        analytics = SessionAnalytics()

        # Get session statistics
        stats = await analytics.get_session_stats(days=7)

        # Get average duration
        durations = await analytics.get_average_session_duration()

        # Visualize component usage
        chart = analytics.visualize_component_usage()
        ```
    """

    def __init__(self, database_path: Path | None = None, conn=None) -> None:
        """Initialize session analytics.

        Args:
            database_path: Path to DuckDB database (optional, uses default if not provided)
            conn: Existing database connection (optional, for testing)
        """
        self.database_path = database_path
        self._conn = conn

    def _get_connection(self):
        """Get database connection, creating if needed.

        Returns:
            DuckDB connection object
        """
        if self._conn is not None:
            return self._conn

        try:
            import duckdb

            if self.database_path:
                conn = duckdb.connect(str(self.database_path))
            else:
                # Use default database path from settings
                from session_buddy.settings import get_settings

                settings = get_settings()
                conn = duckdb.connect(str(settings.database_path))

            return conn
        except ImportError:
            logger.error("DuckDB not installed. Install with: pip install duckdb")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def get_active_sessions(self) -> list[dict[str, t.Any]]:
        """Get currently active sessions.

        Active sessions are those without an end_time (NULL in database).

        Returns:
            List of active session dictionaries with keys:
            - session_id: Unique session identifier
            - component_name: Component or shell type
            - start_time: Session start timestamp
            - duration_seconds: Current duration in seconds
            - project: Associated project name
        """
        query = """
            SELECT
                session_id,
                component_name,
                start_time,
                CAST(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time)) AS INTEGER) as duration_seconds,
                project
            FROM sessions
            WHERE end_time IS NULL
            ORDER BY start_time DESC
        """

        try:
            conn = self._get_connection()
            result = conn.execute(query).fetchall()

            sessions = [
                {
                    "session_id": row[0],
                    "component_name": row[1],
                    "start_time": row[2].isoformat() if row[2] else None,
                    "duration_seconds": row[3],
                    "project": row[4],
                }
                for row in result
            ]

            logger.info(f"Found {len(sessions)} active sessions")
            return sessions

        except Exception as e:
            logger.error(f"Failed to get active sessions: {e}")
            return []

    async def get_session_stats(
        self, days: int = 7, component: str | None = None
    ) -> list[SessionStats]:
        """Get session statistics for the last N days.

        Args:
            days: Number of days to look back (default: 7)
            component: Optional component filter (e.g., 'admin-shell', 'ipython')

        Returns:
            List of SessionStats objects with aggregated statistics

        Example:
            ```python
            # Get stats for last 7 days
            stats = await analytics.get_session_stats(days=7)

            # Get stats for specific component
            stats = await analytics.get_session_stats(days=30, component='admin-shell')
            ```
        """
        # Build WHERE clause
        where_conditions = [f"start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'"]
        if component:
            where_conditions.append(f"component_name = '{component}'")

        where_clause = " AND ".join(where_conditions)

        query = f"""
            SELECT
                component_name,
                COUNT(*) as total_sessions,
                COALESCE(AVG(duration_seconds), 0) as avg_duration,
                COUNT(CASE WHEN end_time IS NULL THEN 1 END) as active_sessions,
                COALESCE(
                    COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0),
                    0.0
                ) as error_rate
            FROM sessions
            WHERE {where_clause}
            GROUP BY component_name
            ORDER BY total_sessions DESC
        """

        try:
            conn = self._get_connection()
            result = conn.execute(query).fetchall()

            stats = [
                SessionStats(
                    component_name=row[0],
                    total_sessions=row[1],
                    avg_duration=row[2],
                    active_sessions=row[3],
                    error_rate=row[4],
                    date_range=f"Last {days} days",
                )
                for row in result
            ]

            logger.info(
                f"Generated session stats for {len(stats)} components over {days} days"
            )
            return stats

        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")
            return []

    async def get_sessions_by_time_range(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, t.Any]]:
        """Get sessions within a specific time range.

        Args:
            start_date: Start of time range (default: 7 days ago)
            end_date: End of time range (default: now)

        Returns:
            List of session dictionaries with full session details

        Example:
            ```python
            from datetime import datetime, timedelta

            # Get sessions from last week
            start = datetime.now() - timedelta(days=7)
            sessions = await analytics.get_sessions_by_time_range(start_date=start)

            # Get sessions for specific date range
            start = datetime(2025, 1, 1)
            end = datetime(2025, 1, 31)
            sessions = await analytics.get_sessions_by_time_range(start_date=start, end_date=end)
            ```
        """
        # Default to last 7 days if not specified
        if start_date is None:
            start_date = datetime.now(UTC) - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now(UTC)

        query = """
            SELECT
                session_id,
                component_name,
                start_time,
                end_time,
                duration_seconds,
                quality_score,
                project,
                error_occurred,
                error_message
            FROM sessions
            WHERE start_time >= ? AND start_time <= ?
            ORDER BY start_time DESC
        """

        try:
            conn = self._get_connection()
            result = conn.execute(
                query, [start_date.isoformat(), end_date.isoformat()]
            ).fetchall()

            sessions = [
                {
                    "session_id": row[0],
                    "component_name": row[1],
                    "start_time": row[2].isoformat() if row[2] else None,
                    "end_time": row[3].isoformat() if row[3] else None,
                    "duration_seconds": row[4],
                    "quality_score": row[5],
                    "project": row[6],
                    "error_occurred": row[7],
                    "error_message": row[8],
                }
                for row in result
            ]

            logger.info(
                f"Found {len(sessions)} sessions between {start_date} and {end_date}"
            )
            return sessions

        except Exception as e:
            logger.error(f"Failed to get sessions by time range: {e}")
            return []

    async def get_average_session_duration(
        self, days: int = 7, component: str | None = None
    ) -> dict[str, float]:
        """Get average session duration by component.

        Args:
            days: Number of days to look back (default: 7)
            component: Optional component filter

        Returns:
            Dictionary mapping component_name to average duration in seconds

        Example:
            ```python
            durations = await analytics.get_average_session_duration(days=30)
            # Returns: {'admin-shell': 1800.5, 'ipython': 2400.0, ...}
            ```
        """
        where_conditions = [
            f"start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'",
            "end_time IS NOT NULL",  # Only completed sessions
            "duration_seconds IS NOT NULL",
        ]
        if component:
            where_conditions.append(f"component_name = '{component}'")

        where_clause = " AND ".join(where_conditions)

        query = f"""
            SELECT
                component_name,
                AVG(duration_seconds) as avg_duration
            FROM sessions
            WHERE {where_clause}
            GROUP BY component_name
            ORDER BY avg_duration DESC
        """

        try:
            conn = self._get_connection()
            result = conn.execute(query).fetchall()

            durations = {row[0]: row[1] for row in result}

            logger.info(f"Calculated average durations for {len(durations)} components")
            return durations

        except Exception as e:
            logger.error(f"Failed to get average session duration: {e}")
            return {}

    async def get_most_active_components(
        self, days: int = 7, limit: int = 10
    ) -> list[ComponentUsage]:
        """Get components with the most sessions.

        Args:
            days: Number of days to look back (default: 7)
            limit: Maximum number of components to return (default: 10)

        Returns:
            List of ComponentUsage objects sorted by session count

        Example:
            ```python
            # Get top 10 components from last 30 days
            components = await analytics.get_most_active_components(days=30, limit=10)
            ```
        """
        query = f"""
            SELECT
                component_name,
                COUNT(*) as session_count,
                COALESCE(SUM(duration_seconds), 0) as total_duration,
                COALESCE(AVG(quality_score), 0.0) as avg_quality_score,
                MAX(start_time) as last_active
            FROM sessions
            WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'
            GROUP BY component_name
            ORDER BY session_count DESC
            LIMIT ?
        """

        try:
            conn = self._get_connection()
            result = conn.execute(query, [limit]).fetchall()

            components = [
                ComponentUsage(
                    component_name=row[0],
                    session_count=row[1],
                    total_duration=row[2],
                    avg_quality_score=row[3],
                    last_active=row[4],
                )
                for row in result
            ]

            logger.info(
                f"Found top {len(components)} active components over {days} days"
            )
            return components

        except Exception as e:
            logger.error(f"Failed to get most active components: {e}")
            return []

    async def get_session_error_rate(
        self, days: int = 7, component: str | None = None
    ) -> dict[str, dict[str, t.Any]]:
        """Get error rate statistics by component.

        Args:
            days: Number of days to look back (default: 7)
            component: Optional component filter

        Returns:
            Dictionary mapping component_name to error statistics:
            - error_rate: Error percentage (0-100)
            - total_sessions: Total session count
            - failed_sessions: Number of failed sessions
            - most_common_error: Most frequent error message

        Example:
            ```python
            error_rates = await analytics.get_session_error_rate(days=30)
            # Returns: {
            #     'admin-shell': {'error_rate': 5.2, 'total_sessions': 100, ...},
            #     'ipython': {'error_rate': 2.1, 'total_sessions': 50, ...}
            # }
            ```
        """
        where_conditions = [f"start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'"]
        if component:
            where_conditions.append(f"component_name = '{component}'")

        where_clause = " AND ".join(where_conditions)

        query = f"""
            SELECT
                component_name,
                COUNT(*) as total_sessions,
                COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) as failed_sessions,
                COALESCE(
                    COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0),
                    0.0
                ) as error_rate,
                MODE() WITHIN GROUP (ORDER BY error_message) as most_common_error
            FROM sessions
            WHERE {where_clause}
            GROUP BY component_name
            ORDER BY error_rate DESC
        """

        try:
            conn = self._get_connection()
            result = conn.execute(query).fetchall()

            error_stats = {
                row[0]: {
                    "error_rate": row[3],
                    "total_sessions": row[1],
                    "failed_sessions": row[2],
                    "most_common_error": row[4],
                }
                for row in result
            }

            logger.info(f"Calculated error rates for {len(error_stats)} components")
            return error_stats

        except Exception as e:
            logger.error(f"Failed to get session error rate: {e}")
            return {}

    # Export methods

    def export_sql(self, query_name: str, days: int = 7, **kwargs: t.Any) -> str:
        """Export query as SQL string.

        Args:
            query_name: Name of the query to export
            days: Time range in days
            **kwargs: Additional query parameters

        Returns:
            SQL query string

        Example:
            ```python
            sql = analytics.export_sql('session_stats', days=30)
            print(sql)
            ```
        """
        queries = {
            "active_sessions": """
                SELECT
                    session_id,
                    component_name,
                    start_time,
                    CAST(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time)) AS INTEGER) as duration_seconds,
                    project
                FROM sessions
                WHERE end_time IS NULL
                ORDER BY start_time DESC
            """,
            "session_stats": f"""
                SELECT
                    component_name,
                    COUNT(*) as total_sessions,
                    COALESCE(AVG(duration_seconds), 0) as avg_duration,
                    COUNT(CASE WHEN end_time IS NULL THEN 1 END) as active_sessions,
                    COALESCE(
                        COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0),
                        0.0
                    ) as error_rate
                FROM sessions
                WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'
                GROUP BY component_name
                ORDER BY total_sessions DESC
            """,
            "average_duration": f"""
                SELECT
                    component_name,
                    AVG(duration_seconds) as avg_duration
                FROM sessions
                WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'
                    AND end_time IS NOT NULL
                    AND duration_seconds IS NOT NULL
                GROUP BY component_name
                ORDER BY avg_duration DESC
            """,
            "most_active": f"""
                SELECT
                    component_name,
                    COUNT(*) as session_count,
                    COALESCE(SUM(duration_seconds), 0) as total_duration,
                    COALESCE(AVG(quality_score), 0.0) as avg_quality_score,
                    MAX(start_time) as last_active
                FROM sessions
                WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'
                GROUP BY component_name
                ORDER BY session_count DESC
                LIMIT 10
            """,
            "error_rate": f"""
                SELECT
                    component_name,
                    COUNT(*) as total_sessions,
                    COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) as failed_sessions,
                    COALESCE(
                        COUNT(CASE WHEN error_occurred = TRUE THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0),
                        0.0
                    ) as error_rate,
                    MODE() WITHIN GROUP (ORDER BY error_message) as most_common_error
                FROM sessions
                WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '{days} days'
                GROUP BY component_name
                ORDER BY error_rate DESC
            """,
        }

        return queries.get(query_name, "-- Query not found")

    # Visualization methods

    def visualize_session_stats(
        self, stats: list[SessionStats], max_width: int = 60
    ) -> list[str]:
        """Generate ASCII visualization of session statistics.

        Args:
            stats: List of SessionStats objects
            max_width: Maximum bar width

        Returns:
            List of formatted strings for display

        Example:
            ```python
            stats = await analytics.get_session_stats(days=7)
            output = analytics.visualize_session_stats(stats)
            print("\\n".join(output))
            ```
        """
        visualizer = ASCIIVisualizer()
        output: list[str] = []

        output.append("=" * 80)
        output.append("SESSION STATISTICS")
        output.append("=" * 80)
        output.append("")

        # Prepare data for bar chart
        chart_data = [(s.component_name, s.total_sessions) for s in stats]

        output.append("Total Sessions by Component:")
        output.extend(visualizer.bar_chart(chart_data, width=max_width))
        output.append("")

        # Table view
        headers = ["Component", "Sessions", "Avg Duration", "Active", "Error Rate"]
        rows = [
            [
                s.component_name,
                str(s.total_sessions),
                f"{s.avg_duration:.0f}s",
                str(s.active_sessions),
                f"{s.error_rate:.1f}%",
            ]
            for s in stats
        ]

        output.append("Detailed Statistics:")
        output.extend(
            visualizer.table(
                headers, rows, align=["left", "right", "right", "right", "right"]
            )
        )
        output.append("")

        return output

    def visualize_component_usage(
        self, components: list[ComponentUsage], max_width: int = 60
    ) -> list[str]:
        """Generate ASCII visualization of component usage.

        Args:
            components: List of ComponentUsage objects
            max_width: Maximum bar width

        Returns:
            List of formatted strings for display
        """
        visualizer = ASCIIVisualizer()
        output: list[str] = []

        output.append("=" * 80)
        output.append("COMPONENT USAGE")
        output.append("=" * 80)
        output.append("")

        # Bar chart for session counts
        chart_data = [(c.component_name, c.session_count) for c in components]
        output.append("Sessions by Component:")
        output.extend(visualizer.bar_chart(chart_data, width=max_width))
        output.append("")

        # Table view
        headers = [
            "Component",
            "Sessions",
            "Total Duration",
            "Avg Quality",
            "Last Active",
        ]
        rows = [
            [
                c.component_name,
                str(c.session_count),
                f"{c.total_duration / 3600:.1f}h",
                f"{c.avg_quality_score:.1f}",
                c.last_active.strftime("%Y-%m-%d %H:%M") if c.last_active else "N/A",
            ]
            for c in components
        ]

        output.append("Detailed Usage:")
        output.extend(
            visualizer.table(
                headers, rows, align=["left", "right", "right", "right", "left"]
            )
        )
        output.append("")

        return output

    def visualize_time_series(
        self, sessions: list[dict[str, t.Any]], bucket_size: str = "day"
    ) -> list[str]:
        """Generate ASCII time series visualization.

        Args:
            sessions: List of session dictionaries with start_time
            bucket_size: Time bucket size ('hour', 'day', 'week')

        Returns:
            List of formatted strings for display
        """
        import collections

        output: list[str] = []

        output.append("=" * 80)
        output.append(f"SESSION TIME SERIES (by {bucket_size})")
        output.append("=" * 80)
        output.append("")

        # Group sessions by time bucket
        buckets: dict[str, int] = collections.defaultdict(int)

        for session in sessions:
            start_time = session.get("start_time")
            if not start_time:
                continue

            try:
                dt = datetime.fromisoformat(start_time)

                if bucket_size == "hour":
                    bucket = dt.strftime("%Y-%m-%d %H:00")
                elif bucket_size == "week":
                    week_start = dt - timedelta(days=dt.weekday())
                    bucket = week_start.strftime("%Y-%m-%d (Week %U)")
                else:  # day
                    bucket = dt.strftime("%Y-%m-%d")

                buckets[bucket] += 1
            except (ValueError, TypeError):
                continue

        if not buckets:
            output.append("No time series data available")
            return output

        # Sort by time
        sorted_buckets = sorted(buckets.items())

        # Generate sparkline
        values = [count for _, count in sorted_buckets]
        visualizer = ASCIIVisualizer()
        sparkline = visualizer.sparkline(values)

        output.append("Activity Sparkline:")
        output.append(sparkline)
        output.append("")

        # Table view
        headers = ["Time", "Sessions"]
        rows = [[bucket, str(count)] for bucket, count in sorted_buckets]

        output.append("Session Counts:")
        output.extend(visualizer.table(headers, rows, align=["left", "right"]))
        output.append("")

        return output


def create_session_summary_report(
    stats: list[SessionStats],
    components: list[ComponentUsage],
    error_rates: dict[str, dict[str, t.Any]],
) -> str:
    """Create a comprehensive session summary report.

    Args:
        stats: Session statistics
        components: Component usage data
        error_rates: Error rate statistics

    Returns:
        Formatted report string
    """
    lines: list[str] = []

    lines.append("=" * 80)
    lines.append("SESSION-BUDDY ANALYTICS REPORT")
    lines.append("=" * 80)
    lines.append("")

    # Summary statistics
    total_sessions = sum(s.total_sessions for s in stats)
    total_errors = sum(e.get("failed_sessions", 0) for e in error_rates.values())
    avg_error_rate = (
        sum(e.get("error_rate", 0) for e in error_rates.values()) / len(error_rates)
        if error_rates
        else 0
    )

    lines.append("SUMMARY:")
    lines.append(f"  Total Sessions: {total_sessions}")
    lines.append(f"  Components Analyzed: {len(stats)}")
    lines.append(f"  Total Errors: {total_errors}")
    lines.append(f"  Average Error Rate: {avg_error_rate:.2f}%")
    lines.append("")

    # Top components
    lines.append("TOP COMPONENTS (by session count):")
    for i, comp in enumerate(components[:5], 1):
        lines.append(
            f"  {i}. {comp.component_name}: {comp.session_count} sessions "
            f"(avg quality: {comp.avg_quality_score:.1f}/100)"
        )
    lines.append("")

    # Components with high error rates
    high_error = [
        (name, data)
        for name, data in error_rates.items()
        if data.get("error_rate", 0) > 5.0
    ]
    if high_error:
        lines.append("COMPONENTS WITH HIGH ERROR RATES:")
        for name, data in sorted(
            high_error, key=lambda x: x[1]["error_rate"], reverse=True
        ):
            lines.append(f"  • {name}: {data['error_rate']:.1f}%")
            if data.get("most_common_error"):
                lines.append(f"    Most common: {data['most_common_error']}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("End of Report")
    lines.append("=" * 80)

    return "\n".join(lines)
