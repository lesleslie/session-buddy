"""Session Analytics for detailed pattern detection and trend analysis.

This module provides comprehensive session analytics including:
- Session length distribution analysis (short/medium/long patterns)
- Temporal pattern detection (time-of-day, day-of-week trends)
- Activity correlation analysis (commits vs quality vs duration)
- Session frequency and streak tracking
- Productivity pattern identification

Architecture:
- SessionAnalytics: Core analytics engine
- SessionPatternDetector: Pattern detection algorithms
- SessionDistribution: Statistical analysis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionLengthDistribution:
    """Distribution of sessions by length categories."""

    short_sessions: int  # < 30 minutes
    medium_sessions: int  # 30-120 minutes
    long_sessions: int  # > 120 minutes
    total_sessions: int
    short_percentage: float
    medium_percentage: float
    long_percentage: float
    avg_duration_minutes: float
    median_duration_minutes: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "short_sessions": self.short_sessions,
            "medium_sessions": self.medium_sessions,
            "long_sessions": self.long_sessions,
            "total_sessions": self.total_sessions,
            "short_percentage": round(self.short_percentage, 1),
            "medium_percentage": round(self.medium_percentage, 1),
            "long_percentage": round(self.long_percentage, 1),
            "avg_duration_minutes": round(self.avg_duration_minutes, 1),
            "median_duration_minutes": round(self.median_duration_minutes, 1),
        }


@dataclass(frozen=True)
class TemporalPatterns:
    """Temporal patterns in session activity."""

    time_of_day_distribution: dict[str, int]  # morning/afternoon/evening/night
    day_of_week_distribution: dict[str, int]  # Mon-Sun
    peak_productivity_hour: int  # 0-23
    peak_productivity_day: str  # Monday-Sunday
    most_productive_time_slot: str  # "Tuesday morning"
    avg_sessions_per_day: float
    session_frequency_trend: str  # "increasing", "stable", "decreasing"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "time_of_day_distribution": self.time_of_day_distribution,
            "day_of_week_distribution": self.day_of_week_distribution,
            "peak_productivity_hour": self.peak_productivity_hour,
            "peak_productivity_day": self.peak_productivity_day,
            "most_productive_time_slot": self.most_productive_time_slot,
            "avg_sessions_per_day": round(self.avg_sessions_per_day, 2),
            "session_frequency_trend": self.session_frequency_trend,
        }


@dataclass(frozen=True)
class ActivityCorrelations:
    """Correlations between session activities."""

    duration_quality_correlation: float  # -1 to 1
    duration_commits_correlation: float  # -1 to 1
    quality_commits_correlation: float  # -1 to 1
    high_quality_sessions: int  # quality >= 80
    low_quality_sessions: int  # quality < 60
    high_commit_sessions: int  # commits >= 10
    long_high_quality_sessions: int  # long + high quality

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "duration_quality_correlation": round(self.duration_quality_correlation, 3),
            "duration_commits_correlation": round(self.duration_commits_correlation, 3),
            "quality_commits_correlation": round(self.quality_commits_correlation, 3),
            "high_quality_sessions": self.high_quality_sessions,
            "low_quality_sessions": self.low_quality_sessions,
            "high_commit_sessions": self.high_commit_sessions,
            "long_high_quality_sessions": self.long_high_quality_sessions,
        }


@dataclass(frozen=True)
class SessionStreaks:
    """Session streak and consistency metrics."""

    longest_streak_days: int
    current_streak_days: int
    avg_gap_between_sessions_hours: float
    longest_gap_hours: float
    consistent_daily_sessions: bool  # sessions on 5+ consecutive days
    most_consistent_week: str  # "2025-W03"
    total_active_days: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "longest_streak_days": self.longest_streak_days,
            "current_streak_days": self.current_streak_days,
            "avg_gap_between_sessions_hours": round(
                self.avg_gap_between_sessions_hours, 1
            ),
            "longest_gap_hours": round(self.longest_gap_hours, 1),
            "consistent_daily_sessions": self.consistent_daily_sessions,
            "most_consistent_week": self.most_consistent_week,
            "total_active_days": self.total_active_days,
        }


@dataclass(frozen=True)
class ProductivityInsights:
    """Actionable insights from session analytics."""

    best_performance_window: str  # "Tuesday 9am-12pm"
    recommended_session_length: str  # "60-90 minutes"
    optimal_break_interval: float  # minutes
    peak_productivity_periods: list[str]
    quality_factors: list[str]  # factors correlated with high quality
    improvement_suggestions: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "best_performance_window": self.best_performance_window,
            "recommended_session_length": self.recommended_session_length,
            "optimal_break_interval": round(self.optimal_break_interval, 0),
            "peak_productivity_periods": self.peak_productivity_periods,
            "quality_factors": self.quality_factors,
            "improvement_suggestions": self.improvement_suggestions,
        }


class SessionAnalytics:
    """Comprehensive session analytics engine.

    Provides detailed analysis of session patterns including:
    - Length distribution and trends
    - Temporal patterns (time of day, day of week)
    - Activity correlations and relationships
    - Session streaks and consistency
    - Actionable productivity insights
    """

    def __init__(
        self,
        db_path: str = "~/.claude/data/workflow_metrics.db",
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize session analytics engine.

        Args:
            db_path: Path to workflow metrics database
            logger: Optional logger instance
        """
        import os

        self.db_path = os.path.expanduser(db_path)
        self.logger = logger or logging.getLogger(__name__)
        self._conn: Any = None

    def _get_conn(self) -> Any:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path)  # type: ignore[attr-defined]
        return self._conn

    async def initialize(self) -> None:
        """Initialize analytics engine (ensures database is ready)."""
        _ = self._get_conn()
        self.logger.info("Session analytics engine initialized")

    async def get_session_length_distribution(
        self, project_path: str | None = None, days_back: int = 30
    ) -> SessionLengthDistribution:
        """Analyze session length distribution.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Session length distribution metrics
        """
        conn = self._get_conn()

        # Build query with optional filters
        where_clauses = []
        params: list[Any] = []

        if project_path:
            where_clauses.append("project_path = ?")
            params.append(project_path)

        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
        where_clauses.append("started_at >= ?")
        params.append(cutoff_date)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Query session length distribution
        result = conn.execute(
            f"""
            SELECT
                duration_minutes
            FROM session_metrics
            {where_sql}
            """,
            params,
        ).fetchall()

        if not result:
            return SessionLengthDistribution(
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

        durations = [row[0] for row in result if row[0] is not None]

        # Categorize sessions
        short = sum(1 for d in durations if d < 30)
        medium = sum(1 for d in durations if 30 <= d <= 120)
        long = sum(1 for d in durations if d > 120)
        total = len(durations)

        # Calculate statistics
        avg_duration = sum(durations) / total if total > 0 else 0

        # Calculate median
        sorted_durations = sorted(durations)
        median = sorted_durations[total // 2] if total > 0 else 0

        return SessionLengthDistribution(
            short_sessions=short,
            medium_sessions=medium,
            long_sessions=long,
            total_sessions=total,
            short_percentage=(short / total * 100) if total > 0 else 0,
            medium_percentage=(medium / total * 100) if total > 0 else 0,
            long_percentage=(long / total * 100) if total > 0 else 0,
            avg_duration_minutes=avg_duration,
            median_duration_minutes=median,
        )

    async def get_temporal_patterns(
        self, project_path: str | None = None, days_back: int = 30
    ) -> TemporalPatterns:
        """Analyze temporal patterns in session activity.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Temporal pattern metrics
        """
        conn = self._get_conn()

        # Build query with optional filters
        where_clauses = []
        params: list[Any] = []

        if project_path:
            where_clauses.append("project_path = ?")
            params.append(project_path)

        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
        where_clauses.append("started_at >= ?")
        params.append(cutoff_date)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Time of day distribution
        tod_result = conn.execute(
            f"""
            SELECT
                time_of_day,
                COUNT(*) as count
            FROM session_metrics
            {where_sql}
            GROUP BY time_of_day
            """,
            params,
        ).fetchall()

        time_of_day_dist = {row[0]: row[1] for row in tod_result}

        # Day of week distribution
        dow_result = conn.execute(
            f"""
            SELECT
                strftime('%w', started_at) as day_of_week,
                COUNT(*) as count
            FROM session_metrics
            {where_sql}
            GROUP BY day_of_week
            ORDER BY day_of_week
            """,
            params,
        ).fetchall()

        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        day_of_week_dist = {day_names[int(row[0])]: row[1] for row in dow_result}

        # Find peak productivity hour (hour with most commits/checkpoints)
        hour_result = conn.execute(
            f"""
            SELECT
                CAST(strftime('%H', started_at) AS INTEGER) as hour,
                SUM(commit_count + checkpoint_count) as productivity
            FROM session_metrics
            {where_sql}
            GROUP BY hour
            ORDER BY productivity DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        peak_hour = hour_result[0] if hour_result else 9

        # Find peak productivity day
        if day_of_week_dist:
            peak_day = max(day_of_week_dist.keys(), key=lambda k: day_of_week_dist[k])
        else:
            peak_day = "Monday"

        # Most productive time slot
        slot_result = conn.execute(
            f"""
            SELECT
                time_of_day || ' on ' || strftime('%A', started_at) as time_slot,
                AVG(commit_count + checkpoint_count) as avg_productivity
            FROM session_metrics
            {where_sql}
            GROUP BY time_slot
            ORDER BY avg_productivity DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        most_productive_slot = slot_result[0] if slot_result else "Unknown"

        # Calculate average sessions per day
        total_sessions = sum(time_of_day_dist.values())
        avg_sessions_per_day = total_sessions / days_back if days_back > 0 else 0

        # Determine session frequency trend
        frequency_trend = await self._calculate_frequency_trend(
            where_sql, params, days_back
        )

        return TemporalPatterns(
            time_of_day_distribution=time_of_day_dist,
            day_of_week_distribution=day_of_week_dist,
            peak_productivity_hour=peak_hour,
            peak_productivity_day=peak_day,
            most_productive_time_slot=most_productive_slot,
            avg_sessions_per_day=avg_sessions_per_day,
            session_frequency_trend=frequency_trend,
        )

    async def _calculate_frequency_trend(
        self, where_sql: str, params: list[Any], days_back: int
    ) -> str:
        """Calculate session frequency trend over time.

        Returns:
            "increasing", "stable", or "decreasing"
        """
        conn = self._get_conn()

        # Get session counts per week
        result = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', started_at) as week,
                COUNT(*) as session_count
            FROM session_metrics
            {where_sql}
            GROUP BY week
            ORDER BY week ASC
            """,
            params,
        ).fetchall()

        if len(result) < 2:
            return "stable"

        counts = [row[1] for row in result]

        # Simple trend detection
        if len(counts) >= 3:
            recent_avg = sum(counts[-3:]) / 3
            earlier_avg = (
                sum(counts[:-3]) / len(counts[:-3]) if len(counts) > 3 else counts[0]
            )

            if recent_avg > earlier_avg * 1.2:
                return "increasing"
            elif recent_avg < earlier_avg * 0.8:
                return "decreasing"

        return "stable"

    async def get_activity_correlations(
        self, project_path: str | None = None, days_back: int = 30
    ) -> ActivityCorrelations:
        """Analyze correlations between session activities.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Activity correlation metrics
        """
        conn = self._get_conn()

        # Build query with optional filters
        where_clauses = []
        params: list[Any] = []

        if project_path:
            where_clauses.append("project_path = ?")
            params.append(project_path)

        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
        where_clauses.append("started_at >= ?")
        params.append(cutoff_date)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Get all session data for correlation calculation
        result = conn.execute(
            f"""
            SELECT
                duration_minutes,
                avg_quality,
                commit_count
            FROM session_metrics
            {where_sql}
            """,
            params,
        ).fetchall()

        if not result or len(result) < 2:
            return ActivityCorrelations(
                duration_quality_correlation=0.0,
                duration_commits_correlation=0.0,
                quality_commits_correlation=0.0,
                high_quality_sessions=0,
                low_quality_sessions=0,
                high_commit_sessions=0,
                long_high_quality_sessions=0,
            )

        durations = [row[0] for row in result if row[0] is not None]
        qualities = [row[1] for row in result if row[1] is not None]
        commits = [row[2] for row in result if row[2] is not None]

        # Calculate correlations (simplified Pearson correlation)
        dur_qual_corr = self._calculate_correlation(durations, qualities)
        dur_comm_corr = self._calculate_correlation(durations, commits)
        qual_comm_corr = self._calculate_correlation(qualities, commits)

        # Count high/low quality sessions
        high_quality = sum(1 for q in qualities if q >= 80)
        low_quality = sum(1 for q in qualities if q < 60)
        high_commit = sum(1 for c in commits if c >= 10)

        # Count long + high quality sessions
        long_high_quality = sum(
            1
            for i, row in enumerate(result)
            if row[0] and row[0] > 120 and row[1] and row[1] >= 80
        )

        return ActivityCorrelations(
            duration_quality_correlation=dur_qual_corr,
            duration_commits_correlation=dur_comm_corr,
            quality_commits_correlation=qual_comm_corr,
            high_quality_sessions=high_quality,
            low_quality_sessions=low_quality,
            high_commit_sessions=high_commit,
            long_high_quality_sessions=long_high_quality,
        )

    def _calculate_correlation(self, x: list[float], y: list[float]) -> float:
        """Calculate Pearson correlation coefficient.

        Args:
            x: First variable
            y: Second variable

        Returns:
            Correlation coefficient (-1 to 1)
        """
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)

        # Calculate means
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        # Calculate correlation
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        sum_xx = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_yy = sum((y[i] - mean_y) ** 2 for i in range(n))

        denominator = (sum_xx * sum_yy) ** 0.5

        if denominator == 0:
            return 0.0

        return numerator / denominator  # type: ignore[no-any-return]

    async def get_session_streaks(
        self, project_path: str | None = None, days_back: int = 30
    ) -> SessionStreaks:
        """Analyze session streaks and consistency.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Session streak metrics
        """
        conn = self._get_conn()

        # Build query with optional filters
        where_clauses = []
        params: list[Any] = []

        if project_path:
            where_clauses.append("project_path = ?")
            params.append(project_path)

        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
        where_clauses.append("started_at >= ?")
        params.append(cutoff_date)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Get session dates
        result = conn.execute(
            f"""
            SELECT DISTINCT
                DATE(started_at) as session_date
            FROM session_metrics
            {where_sql}
            ORDER BY session_date ASC
            """,
            params,
        ).fetchall()

        if not result:
            return SessionStreaks(
                longest_streak_days=0,
                current_streak_days=0,
                avg_gap_between_sessions_hours=0.0,
                longest_gap_hours=0.0,
                consistent_daily_sessions=False,
                most_consistent_week="",
                total_active_days=0,
            )

        session_dates = [row[0] for row in result]

        # Calculate longest streak
        longest_streak = 0
        current_streak = 0

        today = datetime.now(UTC).date()
        for i, date in enumerate(reversed(session_dates)):
            days_ago = (today - date).days
            if days_ago == i:
                current_streak += 1
            else:
                break

        # Find longest consecutive streak
        current_streak_temp = 1
        max_streak = 1

        for i in range(1, len(session_dates)):
            if (session_dates[i] - session_dates[i - 1]).days == 1:
                current_streak_temp += 1
                max_streak = max(max_streak, current_streak_temp)
            else:
                current_streak_temp = 1

        longest_streak = max(max_streak, current_streak, 1)

        # Calculate gaps between sessions
        gaps = [
            (session_dates[i] - session_dates[i - 1]).total_seconds() / 3600
            for i in range(1, len(session_dates))
        ]

        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        longest_gap = max(gaps) if gaps else 0

        # Check for consistent daily sessions (5+ days in a row)
        consistent = longest_streak >= 5

        # Find most consistent week
        week_result = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', started_at) as week,
                COUNT(DISTINCT DATE(started_at)) as active_days
            FROM session_metrics
            {where_sql}
            GROUP BY week
            ORDER BY active_days DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        most_consistent_week = week_result[0] if week_result else ""

        return SessionStreaks(
            longest_streak_days=longest_streak,
            current_streak_days=current_streak,
            avg_gap_between_sessions_hours=avg_gap,
            longest_gap_hours=longest_gap,
            consistent_daily_sessions=consistent,
            most_consistent_week=most_consistent_week,
            total_active_days=len(session_dates),
        )

    async def get_productivity_insights(
        self, project_path: str | None = None, days_back: int = 30
    ) -> ProductivityInsights:
        """Generate actionable productivity insights.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Actionable productivity insights
        """
        # Get all analytics data
        length_dist = await self.get_session_length_distribution(
            project_path, days_back
        )
        temporal = await self.get_temporal_patterns(project_path, days_back)
        correlations = await self.get_activity_correlations(project_path, days_back)

        # Determine best performance window
        best_window = temporal.most_productive_time_slot

        # Recommend session length based on data
        if length_dist.medium_percentage > 50:
            recommended = "60-90 minutes (your most common session length)"
        elif length_dist.long_percentage > 40:
            recommended = "60-90 minutes (consider shorter sessions for better focus)"
        else:
            recommended = "60-90 minutes (optimal for sustained focus)"

        # Calculate optimal break interval
        optimal_break = 90.0  # Default 90 minutes

        if length_dist.avg_duration_minutes > 0:
            optimal_break = min(length_dist.avg_duration_minutes, 120.0)

        # Identify peak productivity periods
        peak_periods = []
        if temporal.time_of_day_distribution:
            peak_time = max(
                temporal.time_of_day_distribution.keys(),
                key=lambda k: temporal.time_of_day_distribution[k],
            )
            peak_day = max(
                temporal.day_of_week_distribution.keys(),
                key=lambda k: temporal.day_of_week_distribution[k],
            )
            peak_periods.append(f"{peak_day} {peak_time}s")

        # Identify quality factors
        quality_factors = []
        if correlations.duration_quality_correlation > 0.3:
            quality_factors.append("Longer sessions correlate with higher quality")
        elif correlations.duration_quality_correlation < -0.3:
            quality_factors.append("Shorter sessions correlate with higher quality")

        if correlations.quality_commits_correlation > 0.3:
            quality_factors.append("Higher commit rates correlate with quality")

        # Generate improvement suggestions
        suggestions = []

        if length_dist.short_percentage > 60:
            suggestions.append(
                "Consider extending sessions to 60-90 minutes for deeper work"
            )
        elif length_dist.long_percentage > 40:
            suggestions.append(
                "Try breaking long sessions into focused 90-minute blocks"
            )

        if temporal.avg_sessions_per_day < 1:
            suggestions.append("Aim for at least one focused session per day")
        elif temporal.avg_sessions_per_day > 4:
            suggestions.append("Ensure you're taking adequate breaks between sessions")

        if correlations.long_high_quality_sessions == 0:
            suggestions.append("Balance session length - avoid marathon sessions")

        return ProductivityInsights(
            best_performance_window=best_window,
            recommended_session_length=recommended,
            optimal_break_interval=optimal_break,
            peak_productivity_periods=peak_periods,
            quality_factors=quality_factors,
            improvement_suggestions=suggestions,
        )

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# Dependency injection key
DEPENDENCY_KEY = "session_analytics"


def get_session_analytics() -> SessionAnalytics:
    """Get or create session analytics instance.

    This is the preferred way to access the analytics engine,
    using dependency injection for testability.

    Returns:
        Shared SessionAnalytics instance
    """
    from session_buddy.di import depends

    analytics = depends.get_sync(SessionAnalytics)
    if analytics is None:
        analytics = SessionAnalytics()
    return analytics  # type: ignore[no-any-return]
