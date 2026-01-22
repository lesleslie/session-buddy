"""Bottleneck detection for workflow impediment identification.

This module provides comprehensive bottleneck detection including:
- Quality drop detection and analysis
- Velocity stagnation identification
- Long-running session detection
- Checkpoint frequency issues
- Commit pattern anomalies
- Time-based bottleneck analysis

Architecture:
    BottleneckDetector → BottleneckMetrics → BottleneckStore
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QualityBottleneck:
    """Quality-related bottlenecks."""

    sudden_quality_drops: int  # Quality delta < -10
    consecutive_low_quality_sessions: int  # Sessions with quality < 60
    low_quality_periods: list[dict[str, Any]]  # Time ranges with quality < 60
    avg_recovery_time_hours: float  # Time to recover from quality drops
    most_common_quality_drop_cause: str | None  # Inferred from patterns

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sudden_quality_drops": self.sudden_quality_drops,
            "consecutive_low_quality_sessions": self.consecutive_low_quality_sessions,
            "low_quality_periods": self.low_quality_periods,
            "avg_recovery_time_hours": round(self.avg_recovery_time_hours, 1),
            "most_common_quality_drop_cause": self.most_common_quality_drop_cause,
        }


@dataclass(frozen=True)
class VelocityBottleneck:
    """Velocity-related bottlenecks."""

    low_velocity_sessions: int  # Commits/hour < threshold
    zero_commit_sessions: int  # Sessions with no commits
    long_sessions_without_commits: int  # >60min with 0 commits
    avg_commits_per_hour_low_periods: float  # During low velocity periods
    velocity_stagnation_days: int  # Days with declining velocity

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "low_velocity_sessions": self.low_velocity_sessions,
            "zero_commit_sessions": self.zero_commit_sessions,
            "long_sessions_without_commits": self.long_sessions_without_commits,
            "avg_commits_per_hour_low_periods": round(
                self.avg_commits_per_hour_low_periods, 2
            ),
            "velocity_stagnation_days": self.velocity_stagnation_days,
        }


@dataclass(frozen=True)
class SessionPatternBottleneck:
    """Session pattern bottlenecks."""

    marathon_sessions: int  # >4 hours without breaks
    fragmented_work_sessions: int  # <15 minutes multiple times
    infrequent_checkpoint_sessions: int  # Long sessions with few checkpoints
    excessive_session_gaps: float  # Avg hours between sessions (high = inconsistent)
    inconsistent_schedule_score: float  # 0-100, higher = more inconsistent

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "marathon_sessions": self.marathon_sessions,
            "fragmented_work_sessions": self.fragmented_work_sessions,
            "infrequent_checkpoint_sessions": self.infrequent_checkpoint_sessions,
            "excessive_session_gaps": round(self.excessive_session_gaps, 1),
            "inconsistent_schedule_score": round(self.inconsistent_schedule_score, 1),
        }


@dataclass(frozen=True)
class BottleneckInsights:
    """Actionable bottleneck insights."""

    critical_bottlenecks: list[str]  # High-impact issues
    improvement_recommendations: list[str]  # Specific actions
    workflow_optimization_opportunities: list[str]  # Process improvements
    estimated_impact_if_resolved: str  # Expected improvement

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "critical_bottlenecks": self.critical_bottlenecks,
            "improvement_recommendations": self.improvement_recommendations,
            "workflow_optimization_opportunities": self.workflow_optimization_opportunities,
            "estimated_impact_if_resolved": self.estimated_impact_if_resolved,
        }


class BottleneckDetector:
    """Detect workflow bottlenecks from session metrics.

    Analyzes session patterns to identify impediments including:
    - Quality drops and stagnation
    - Velocity issues (low commits/hour)
    - Session pattern problems (marathons, fragmentation)
    - Checkpoint frequency issues

    Usage:
        >>> detector = BottleneckDetector()
        >>> await detector.initialize()
        >>> quality_bottlenecks = await detector.detect_quality_bottlenecks()
        >>> velocity_bottlenecks = await detector.detect_velocity_bottlenecks()
    """

    def __init__(
        self,
        db_path: str = "~/.claude/data/workflow_metrics.db",
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize bottleneck detector.

        Args:
            db_path: Path to workflow metrics database
            logger: Optional logger instance
        """
        import os

        self.db_path = os.path.expanduser(db_path)
        self.logger = logger or logging.getLogger(__name__)
        self._conn: Any = None

        # Bottleneck thresholds
        self.QUALITY_DROP_THRESHOLD = -10  # Quality delta < -10 is sudden drop
        self.LOW_QUALITY_THRESHOLD = 60  # Quality < 60 is low quality
        self.LOW_VELOCITY_THRESHOLD = 2  # <2 commits/hour is low velocity
        self.MARATHON_SESSION_THRESHOLD = 240  # >4 hours is marathon
        self.FRAGMENTED_SESSION_THRESHOLD = 15  # <15 minutes is fragmented
        self.CHECKPOINT_FREQUENCY_THRESHOLD = 0.1  # Checkpoints per 10 minutes

    def _get_conn(self) -> Any:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path)  # type: ignore[attr-defined]
        return self._conn

    async def initialize(self) -> None:
        """Initialize detector (ensures database is ready)."""
        _ = self._get_conn()
        self.logger.info("Bottleneck detector initialized")

    async def detect_quality_bottlenecks(
        self, project_path: str | None = None, days_back: int = 30
    ) -> QualityBottleneck:
        """Detect quality-related bottlenecks.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Quality bottleneck metrics
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

        # Sudden quality drops (quality_delta < -10)
        sudden_drops_result = conn.execute(
            f"""
            SELECT COUNT(*) as count
            FROM session_metrics
            {where_sql}
            AND quality_delta < ?
            """,
            params + [self.QUALITY_DROP_THRESHOLD],
        ).fetchone()
        sudden_quality_drops = sudden_drops_result[0] if sudden_drops_result else 0

        # Consecutive low quality sessions
        low_quality_result = conn.execute(
            f"""
            SELECT
                started_at,
                avg_quality,
                LAG(avg_quality, 1) OVER (ORDER BY started_at) as prev_quality
            FROM session_metrics
            {where_sql}
            ORDER BY started_at
            """,
            params,
        ).fetchall()

        consecutive_low = 0
        max_consecutive_low = 0
        for row in low_quality_result:
            if row[1] < self.LOW_QUALITY_THRESHOLD:
                if row[2] and row[2] < self.LOW_QUALITY_THRESHOLD:
                    consecutive_low += 1
                    max_consecutive_low = max(max_consecutive_low, consecutive_low)
                else:
                    consecutive_low = 1
            else:
                consecutive_low = 0

        # Low quality periods (time ranges)
        low_quality_periods_result = conn.execute(
            f"""
            SELECT
                DATE(started_at) as date,
                COUNT(*) as session_count,
                AVG(avg_quality) as avg_quality
            FROM session_metrics
            {where_sql}
            AND avg_quality < ?
            GROUP BY DATE(started_at)
            ORDER BY date DESC
            """,
            params + [self.LOW_QUALITY_THRESHOLD],
        ).fetchall()

        low_quality_periods = [
            {
                "date": row[0].isoformat() if row[0] else None,
                "session_count": row[1],
                "avg_quality": round(row[2], 1) if row[2] else 0,
            }
            for row in low_quality_periods_result
        ]

        # Average recovery time (time from quality drop to recovery)
        recovery_times_result = conn.execute(
            f"""
            WITH quality_drops AS (
                SELECT
                    started_at,
                    avg_quality,
                    LAG(avg_quality, 1) OVER (ORDER BY started_at) as prev_quality
                FROM session_metrics
                {where_sql}
            ),
            recovery_periods AS (
                SELECT
                    started_at,
                    prev_quality,
                    LEAD(started_at, 1) OVER (ORDER BY started_at) as recovery_time
                FROM quality_drops
                WHERE prev_quality >= avg_quality + 10
            )
            SELECT
                AVG(EXTRACT(EPOCH FROM (recovery_time - started_at)) / 3600) as avg_hours
            FROM recovery_periods
            WHERE recovery_time IS NOT NULL
            """,
            params,
        ).fetchone()

        avg_recovery_time = (
            float(recovery_times_result[0])
            if recovery_times_result and recovery_times_result[0]
            else 0
        )

        # Most common quality drop cause (inferred from tool usage)
        cause_result = conn.execute(
            f"""
            SELECT
                tools_used[1] as primary_tool,
                COUNT(*) as drop_count
            FROM session_metrics
            {where_sql}
            AND quality_delta < ?
            AND TOOLS_USED IS NOT NULL
            AND ARRAY_LENGTH(tools_used) > 0
            GROUP BY tools_used[1]
            ORDER BY drop_count DESC
            LIMIT 1
            """,
            params + [self.QUALITY_DROP_THRESHOLD],
        ).fetchone()

        most_common_cause = cause_result[0] if cause_result else None

        return QualityBottleneck(
            sudden_quality_drops=sudden_quality_drops,
            consecutive_low_quality_sessions=max_consecutive_low,
            low_quality_periods=low_quality_periods,
            avg_recovery_time_hours=avg_recovery_time,
            most_common_quality_drop_cause=most_common_cause,
        )

    async def detect_velocity_bottlenecks(
        self, project_path: str | None = None, days_back: int = 30
    ) -> VelocityBottleneck:
        """Detect velocity-related bottlenecks.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Velocity bottleneck metrics
        """
        conn = self._get_conn()

        where_clauses = []
        params: list[Any] = []

        if project_path:
            where_clauses.append("project_path = ?")
            params.append(project_path)

        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
        where_clauses.append("started_at >= ?")
        params.append(cutoff_date)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Low velocity sessions (< 2 commits/hour)
        low_velocity_result = conn.execute(
            f"""
            SELECT COUNT(*) as count
            FROM session_metrics
            {where_sql}
            AND duration_minutes > 0
            AND (commit_count::FLOAT / duration_minutes * 60) < ?
            """,
            params + [self.LOW_VELOCITY_THRESHOLD],
        ).fetchone()
        low_velocity_sessions = low_velocity_result[0] if low_velocity_result else 0

        # Zero commit sessions
        zero_commit_result = conn.execute(
            f"""
            SELECT COUNT(*) as count
            FROM session_metrics
            {where_sql}
            AND commit_count = 0
            """,
            params,
        ).fetchone()
        zero_commit_sessions = zero_commit_result[0] if zero_commit_result else 0

        # Long sessions without commits (>60min, 0 commits)
        long_no_commit_result = conn.execute(
            f"""
            SELECT COUNT(*) as count
            FROM session_metrics
            {where_sql}
            AND duration_minutes > 60
            AND commit_count = 0
            """,
            params,
        ).fetchone()
        long_without_commits = long_no_commit_result[0] if long_no_commit_result else 0

        # Average commits/hour during low velocity periods
        low_velocity_avg_result = conn.execute(
            f"""
            SELECT AVG(commit_count::FLOAT / duration_minutes * 60) as avg_velocity
            FROM session_metrics
            {where_sql}
            AND duration_minutes > 0
            AND (commit_count::FLOAT / duration_minutes * 60) < ?
            """,
            params + [self.LOW_VELOCITY_THRESHOLD],
        ).fetchone()

        avg_commits_per_hour_low = (
            float(low_velocity_avg_result[0])
            if low_velocity_avg_result and low_velocity_avg_result[0]
            else 0
        )

        # Velocity stagnation days (days with declining velocity)
        stagnation_result = conn.execute(
            f"""
            WITH daily_velocity AS (
                SELECT
                    DATE(started_at) as date,
                    SUM(commit_count)::FLOAT / SUM(duration_minutes) * 60 as commits_per_hour
                FROM session_metrics
                {where_sql}
                AND duration_minutes > 0
                GROUP BY DATE(started_at)
            ),
            velocity_trend AS (
                SELECT
                    date,
                    commits_per_hour,
                    LAG(commits_per_hour, 1) OVER (ORDER BY date) as prev_velocity
                FROM daily_velocity
            )
            SELECT COUNT(*) as stagnation_days
            FROM velocity_trend
            WHERE prev_velocity IS NOT NULL
              AND commits_per_hour < prev_velocity
            """,
            params,
        ).fetchone()

        velocity_stagnation_days = stagnation_result[0] if stagnation_result else 0

        return VelocityBottleneck(
            low_velocity_sessions=low_velocity_sessions,
            zero_commit_sessions=zero_commit_sessions,
            long_sessions_without_commits=long_without_commits,
            avg_commits_per_hour_low_periods=avg_commits_per_hour_low,
            velocity_stagnation_days=velocity_stagnation_days,
        )

    async def detect_session_pattern_bottlenecks(
        self, project_path: str | None = None, days_back: int = 30
    ) -> SessionPatternBottleneck:
        """Detect session pattern bottlenecks.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Session pattern bottleneck metrics
        """
        conn = self._get_conn()

        where_clauses = []
        params: list[Any] = []

        if project_path:
            where_clauses.append("project_path = ?")
            params.append(project_path)

        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
        where_clauses.append("started_at >= ?")
        params.append(cutoff_date)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Marathon sessions (>4 hours)
        marathon_result = conn.execute(
            f"""
            SELECT COUNT(*) as count
            FROM session_metrics
            {where_sql}
            AND duration_minutes > ?
            """,
            params + [self.MARATHON_SESSION_THRESHOLD],
        ).fetchone()
        marathon_sessions = marathon_result[0] if marathon_result else 0

        # Fragmented work sessions (<15 minutes, occurring multiple times)
        fragmented_result = conn.execute(
            f"""
            WITH short_sessions AS (
                SELECT
                    DATE(started_at) as date,
                    COUNT(*) as short_count
                FROM session_metrics
                {where_sql}
                AND duration_minutes < ?
                GROUP BY DATE(started_at)
                HAVING COUNT(*) >= 3
            )
            SELECT SUM(short_count) as total_fragments
            FROM short_sessions
            """,
            params + [self.FRAGMENTED_SESSION_THRESHOLD],
        ).fetchone()

        fragmented_sessions = (
            int(fragmented_result[0])
            if fragmented_result and fragmented_result[0]
            else 0
        )

        # Infrequent checkpoint sessions (long sessions with few checkpoints)
        infrequent_checkpoint_result = conn.execute(
            f"""
            SELECT COUNT(*) as count
            FROM session_metrics
            {where_sql}
            AND duration_minutes > 60
            AND checkpoint_count < (duration_minutes / 60 * ?)
            """,
            params + [self.CHECKPOINT_FREQUENCY_THRESHOLD],
        ).fetchone()
        infrequent_checkpoints = (
            infrequent_checkpoint_result[0] if infrequent_checkpoint_result else 0
        )

        # Excessive session gaps (avg hours between consecutive sessions)
        gaps_result = conn.execute(
            f"""
            WITH session_gaps AS (
                SELECT
                    started_at,
                    LAG(started_at, 1) OVER (ORDER BY started_at) as prev_start
                FROM session_metrics
                {where_sql}
            )
            SELECT AVG(EXTRACT(EPOCH FROM (started_at - prev_start)) / 3600) as avg_gap_hours
            FROM session_gaps
            WHERE prev_start IS NOT NULL
            """,
            params,
        ).fetchone()

        avg_gap_hours = float(gaps_result[0]) if gaps_result and gaps_result[0] else 0

        # Inconsistent schedule score (based on session time variance)
        inconsistency_result = conn.execute(
            f"""
            WITH hourly_distribution AS (
                SELECT
                    EXTRACT(HOUR FROM started_at) as hour,
                    COUNT(*) as session_count
                FROM session_metrics
                {where_sql}
                GROUP BY EXTRACT(HOUR FROM started_at)
            ),
            stats AS (
                SELECT
                    AVG(session_count) as avg_count,
                    STDDEV(session_count) as stddev_count
                FROM hourly_distribution
            )
            SELECT
                CASE
                    WHEN stddev_count IS NULL THEN 0
                    WHEN avg_count = 0 THEN 100
                    ELSE LEAST((stddev_count / avg_count) * 100, 100)
                END as inconsistency_score
            FROM stats
            """,
            params,
        ).fetchone()

        inconsistency_score = (
            float(inconsistency_result[0]) if inconsistency_result else 0
        )

        return SessionPatternBottleneck(
            marathon_sessions=marathon_sessions,
            fragmented_work_sessions=fragmented_sessions,
            infrequent_checkpoint_sessions=infrequent_checkpoints,
            excessive_session_gaps=avg_gap_hours,
            inconsistent_schedule_score=inconsistency_score,
        )

    async def get_bottleneck_insights(
        self, project_path: str | None = None, days_back: int = 30
    ) -> BottleneckInsights:
        """Generate actionable bottleneck insights.

        Args:
            project_path: Optional filter by project
            days_back: Days to analyze (default: 30)

        Returns:
            Actionable insights and recommendations
        """
        quality_bottlenecks = await self.detect_quality_bottlenecks(
            project_path=project_path, days_back=days_back
        )
        velocity_bottlenecks = await self.detect_velocity_bottlenecks(
            project_path=project_path, days_back=days_back
        )
        pattern_bottlenecks = await self.detect_session_pattern_bottlenecks(
            project_path=project_path, days_back=days_back
        )

        critical_bottlenecks = []
        improvement_recommendations = []
        optimization_opportunities = []

        # Quality bottlenecks
        if quality_bottlenecks.sudden_quality_drops > 3:
            critical_bottlenecks.append(
                f"Multiple quality drops ({quality_bottlenecks.sudden_quality_drops} instances)"
            )
            improvement_recommendations.append(
                "Review quality drop patterns to identify root causes"
            )

        if quality_bottlenecks.consecutive_low_quality_sessions >= 3:
            critical_bottlenecks.append(
                f"Sustained low quality periods ({quality_bottlenecks.consecutive_low_quality_sessions}+ sessions)"
            )
            improvement_recommendations.append(
                "Take breaks or switch tasks during quality decline streaks"
            )

        # Velocity bottlenecks
        if velocity_bottlenecks.zero_commit_sessions > 5:
            critical_bottlenecks.append(
                f"High number of zero-commit sessions ({velocity_bottlenecks.zero_commit_sessions})"
            )
            improvement_recommendations.append(
                "Break larger tasks into smaller commit-ready units"
            )

        if velocity_bottlenecks.long_sessions_without_commits > 2:
            critical_bottlenecks.append(
                f"Long sessions without progress ({velocity_bottlenecks.long_sessions_without_commits} sessions)"
            )
            optimization_opportunities.append(
                "Set checkpoints during long sessions to track progress"
            )

        # Pattern bottlenecks
        if pattern_bottlenecks.marathon_sessions > 2:
            critical_bottlenecks.append(
                f"Frequent marathon sessions ({pattern_bottlenecks.marathon_sessions} sessions)"
            )
            improvement_recommendations.append(
                "Implement forced breaks after 2-3 hours of focused work"
            )

        if pattern_bottlenecks.fragmented_work_sessions > 5:
            critical_bottlenecks.append(
                f"Highly fragmented work ({pattern_bottlenecks.fragmented_work_sessions} short sessions)"
            )
            improvement_recommendations.append(
                "Block dedicated focus time (60-90 minutes) for deep work"
            )

        if pattern_bottlenecks.inconsistent_schedule_score > 70:
            critical_bottlenecks.append(
                f"Highly inconsistent schedule (score: {pattern_bottlenecks.inconsistent_schedule_score:.0}/100)"
            )
            optimization_opportunities.append(
                "Establish regular session schedule for improved momentum"
            )

        # Estimate impact
        total_critical = len(critical_bottlenecks)
        if total_critical == 0:
            impact = "Minor - no critical bottlenecks detected"
        elif total_critical <= 2:
            impact = "Moderate - addressing bottlenecks could improve velocity 20-30%"
        else:
            impact = "Significant - addressing bottlenecks could improve velocity 50%+"

        return BottleneckInsights(
            critical_bottlenecks=critical_bottlenecks,
            improvement_recommendations=improvement_recommendations,
            workflow_optimization_opportunities=optimization_opportunities,
            estimated_impact_if_resolved=impact,
        )

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# Dependency injection key
DEPENDENCY_KEY = "bottleneck_detector"


def get_bottleneck_detector() -> BottleneckDetector:
    """Get or create bottleneck detector instance.

    This is the preferred way to access the detector,
    using dependency injection for testability.

    Returns:
        Shared BottleneckDetector instance
    """
    from session_buddy.di import depends

    detector = depends.get_sync(BottleneckDetector)
    if detector is None:
        detector = BottleneckDetector()
    return detector  # type: ignore[no-any-return]
