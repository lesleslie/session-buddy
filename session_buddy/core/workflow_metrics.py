"""Workflow Metrics Engine for tracking development velocity and quality trends.

This module provides comprehensive metrics collection and analysis:
- Session velocity metrics (commits/hour, checkpoints/hour)
- Quality trend analysis across checkpoints
- Session pattern detection (length, frequency, working hours)
- Historical performance tracking

Architecture:
- WorkflowMetricsEngine: Core metrics collection and analysis
- WorkflowMetricsStore: Database persistence layer
- VelocityCalculator: Statistical analysis of development speed
- QualityTrendAnalyzer: Pattern detection in quality scores
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import duckdb

from session_buddy.di import depends

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionMetrics:
    """Immutable metrics for a single session."""

    session_id: str
    project_path: str
    started_at: datetime
    ended_at: datetime | None
    duration_minutes: float | None
    checkpoint_count: int
    commit_count: int
    quality_start: float
    quality_end: float
    quality_delta: float
    avg_quality: float
    files_modified: int
    tools_used: list[str]
    primary_language: str | None
    time_of_day: str  # "morning", "afternoon", "evening", "night"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "project_path": self.project_path,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_minutes": self.duration_minutes,
            "checkpoint_count": self.checkpoint_count,
            "commit_count": self.commit_count,
            "quality_start": self.quality_start,
            "quality_end": self.quality_end,
            "quality_delta": self.quality_delta,
            "avg_quality": self.avg_quality,
            "files_modified": self.files_modified,
            "tools_used": self.tools_used,
            "primary_language": self.primary_language,
            "time_of_day": self.time_of_day,
        }


@dataclass(frozen=True)
class WorkflowMetrics:
    """Aggregated workflow metrics across sessions."""

    total_sessions: int
    avg_session_duration_minutes: float
    avg_checkpoints_per_session: float
    avg_commits_per_session: float
    avg_quality_score: float
    quality_trend: str  # "improving", "stable", "declining"
    most_productive_time_of_day: str
    most_used_tools: list[tuple[str, int]]
    total_files_modified: int
    avg_velocity_commits_per_hour: float
    active_projects: list[str]
    period_start: datetime
    period_end: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_sessions": self.total_sessions,
            "avg_session_duration_minutes": self.avg_session_duration_minutes,
            "avg_checkpoints_per_session": self.avg_checkpoints_per_session,
            "avg_commits_per_session": self.avg_commits_per_session,
            "avg_quality_score": self.avg_quality_score,
            "quality_trend": self.quality_trend,
            "most_productive_time_of_day": self.most_productive_time_of_day,
            "most_used_tools": [
                {"tool": tool, "usage_count": count}
                for tool, count in self.most_used_tools
            ],
            "total_files_modified": self.total_files_modified,
            "avg_velocity_commits_per_hour": self.avg_velocity_commits_per_hour,
            "active_projects": self.active_projects,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
        }


class WorkflowMetricsStore:
    """Database-backed storage for workflow metrics.

    Uses DuckDB for efficient analytics queries with time-series support.
    """

    def __init__(self, db_path: str = "~/.claude/data/workflow_metrics.db") -> None:
        """Initialize metrics store with database path.

        Args:
            db_path: Path to DuckDB database file (expanded for ~)
        """
        import os

        self.db_path = os.path.expanduser(db_path)
        self._conn: Any = None

    def _get_conn(self) -> Any:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path)  # type: ignore[attr-defined]
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._get_conn()

        # Session metrics table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_metrics (
                session_id TEXT PRIMARY KEY,
                project_path TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                duration_minutes FLOAT,
                checkpoint_count INTEGER DEFAULT 0,
                commit_count INTEGER DEFAULT 0,
                quality_start FLOAT DEFAULT 0,
                quality_end FLOAT DEFAULT 0,
                quality_delta FLOAT DEFAULT 0,
                avg_quality FLOAT DEFAULT 0,
                files_modified INTEGER DEFAULT 0,
                tools_used TEXT[],  -- Array of tool names
                primary_language TEXT,
                time_of_day TEXT,  -- morning/afternoon/evening/night
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for common queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_metrics_project
            ON session_metrics(project_path)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_metrics_started_at
            ON session_metrics(started_at DESC)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_metrics_time_of_day
            ON session_metrics(time_of_day)
        """)

        logger.info("Workflow metrics database schema initialized")

    async def store_session_metrics(self, metrics: SessionMetrics) -> None:
        """Store session metrics to database.

        Args:
            metrics: SessionMetrics to store
        """
        conn = self._get_conn()

        conn.execute(
            """
            INSERT INTO session_metrics (
                session_id, project_path, started_at, ended_at, duration_minutes,
                checkpoint_count, commit_count, quality_start, quality_end,
                quality_delta, avg_quality, files_modified, tools_used,
                primary_language, time_of_day
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                metrics.session_id,
                metrics.project_path,
                metrics.started_at,
                metrics.ended_at,
                metrics.duration_minutes,
                metrics.checkpoint_count,
                metrics.commit_count,
                metrics.quality_start,
                metrics.quality_end,
                metrics.quality_delta,
                metrics.avg_quality,
                metrics.files_modified,
                metrics.tools_used,  # DuckDB automatically converts list to TEXT[]
                metrics.primary_language,
                metrics.time_of_day,
            ],
        )

        logger.debug(f"Stored metrics for session {metrics.session_id}")

    async def get_workflow_metrics(
        self,
        project_path: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> WorkflowMetrics:
        """Calculate aggregated workflow metrics.

        Args:
            project_path: Optional filter by project path
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Aggregated WorkflowMetrics
        """
        conn = self._get_conn()

        # Build query with optional filters
        where_clauses = []
        params: list[Any] = []

        if project_path:
            where_clauses.append("project_path = ?")
            params.append(project_path)

        if start_date:
            where_clauses.append("started_at >= ?")
            params.append(start_date)

        if end_date:
            where_clauses.append("started_at <= ?")
            params.append(end_date)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Query aggregated metrics
        result = conn.execute(
            f"""
            SELECT
                COUNT(*) as total_sessions,
                AVG(duration_minutes) as avg_duration,
                AVG(checkpoint_count) as avg_checkpoints,
                AVG(commit_count) as avg_commits,
                AVG(avg_quality) as avg_quality,
                SUM(files_modified) as total_files,
                MIN(started_at) as period_start,
                MAX(started_at) as period_end
            FROM session_metrics
            {where_sql}
        """,
            params,
        ).fetchone()

        if not result or result[0] == 0:
            # No sessions found, return empty metrics
            return WorkflowMetrics(
                total_sessions=0,
                avg_session_duration_minutes=0.0,
                avg_checkpoints_per_session=0.0,
                avg_commits_per_session=0.0,
                avg_quality_score=0.0,
                quality_trend="stable",
                most_productive_time_of_day="unknown",
                most_used_tools=[],
                total_files_modified=0,
                avg_velocity_commits_per_hour=0.0,
                active_projects=[],
                period_start=datetime.now(UTC),
                period_end=datetime.now(UTC),
            )

        (
            total_sessions,
            avg_duration,
            avg_checkpoints,
            avg_commits,
            avg_quality,
            total_files,
            period_start,
            period_end,
        ) = result

        # Calculate velocity (commits per hour)
        avg_velocity = (
            (avg_commits / (avg_duration / 60))
            if avg_duration and avg_duration > 0
            else 0.0
        )

        # Determine quality trend
        quality_trend = await self._calculate_quality_trend(where_sql, params)

        # Find most productive time of day
        most_productive_time = await self._find_most_productive_time_of_day(
            where_sql, params
        )

        # Get most used tools
        most_used_tools = await self._get_most_used_tools(where_sql, params, limit=5)

        # Get active projects
        active_projects = await self._get_active_projects(where_sql, params)

        return WorkflowMetrics(
            total_sessions=int(total_sessions),
            avg_session_duration_minutes=float(avg_duration or 0),
            avg_checkpoints_per_session=float(avg_checkpoints or 0),
            avg_commits_per_session=float(avg_commits or 0),
            avg_quality_score=float(avg_quality or 0),
            quality_trend=quality_trend,
            most_productive_time_of_day=most_productive_time,
            most_used_tools=most_used_tools,
            total_files_modified=int(total_files or 0),
            avg_velocity_commits_per_hour=avg_velocity,
            active_projects=active_projects,
            period_start=period_start,
            period_end=period_end,
        )

    async def _calculate_quality_trend(self, where_sql: str, params: list[Any]) -> str:
        """Calculate quality trend direction.

        Returns:
            "improving", "stable", or "declining"
        """
        conn = self._get_conn()

        # Get quality scores ordered by time
        result = conn.execute(
            f"""
            SELECT avg_quality
            FROM session_metrics
            {where_sql}
            ORDER BY started_at ASC
            """,
            params,
        ).fetchall()

        if len(result) < 2:
            return "stable"

        qualities = [row[0] for row in result if row[0] is not None]

        if len(qualities) < 2:
            return "stable"

        # Calculate linear regression slope
        n = len(qualities)
        x = list(range(n))
        sum_x = sum(x)
        sum_y = sum(qualities)
        sum_xy = sum(x[i] * qualities[i] for i in range(n))
        sum_x_squared = sum(xi * xi for xi in x)

        denominator = n * sum_x_squared - sum_x * sum_x
        if denominator == 0:
            return "stable"

        slope = (n * sum_xy - sum_x * sum_y) / denominator

        # Determine trend based on slope
        if slope > 0.5:
            return "improving"
        elif slope < -0.5:
            return "declining"
        return "stable"

    async def _find_most_productive_time_of_day(
        self, where_sql: str, params: list[Any]
    ) -> str:
        """Find time of day with highest average velocity.

        Returns:
            Time of day string: "morning", "afternoon", "evening", "night"
        """
        conn = self._get_conn()

        result = conn.execute(
            f"""
            SELECT
                time_of_day,
                AVG(commit_count) as avg_commits,
                AVG(checkpoint_count) as avg_checkpoints
            FROM session_metrics
            {where_sql}
            GROUP BY time_of_day
            ORDER BY (avg_commits + avg_checkpoints) DESC
            LIMIT 1
        """,
            params,
        ).fetchone()

        if result and result[0]:
            return str(result[0])

        return "unknown"

    async def _get_most_used_tools(
        self, where_sql: str, params: list[Any], limit: int = 5
    ) -> list[tuple[str, int]]:
        """Get most frequently used tools.

        Returns:
            List of (tool_name, usage_count) tuples
        """
        conn = self._get_conn()

        result = conn.execute(
            f"""
            SELECT unnest(tools_used) as tool, COUNT(*) as usage_count
            FROM session_metrics
            {where_sql}
            GROUP BY tool
            ORDER BY usage_count DESC
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()

        return [(row[0], int(row[1])) for row in result if row[0]]

    async def _get_active_projects(
        self, where_sql: str, params: list[Any]
    ) -> list[str]:
        """Get list of active projects.

        Returns:
            List of unique project paths
        """
        conn = self._get_conn()

        result = conn.execute(
            f"""
            SELECT DISTINCT project_path
            FROM session_metrics
            {where_sql}
            ORDER BY project_path
            """,
            params,
        ).fetchall()

        return [row[0] for row in result]

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


class WorkflowMetricsEngine:
    """Core engine for workflow metrics collection and analysis.

    Coordinates metrics collection from sessions and provides
    analytics for workflow optimization.
    """

    def __init__(
        self,
        store: WorkflowMetricsStore | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize workflow metrics engine.

        Args:
            store: Optional metrics store (uses default if None)
            logger: Optional logger instance
        """
        self.store = store or WorkflowMetricsStore()
        self.logger = logger or logging.getLogger(__name__)

    async def initialize(self) -> None:
        """Initialize metrics engine (ensures database is ready)."""
        # Trigger database initialization
        _ = self.store._get_conn()
        self.logger.info("Workflow metrics engine initialized")

    async def collect_session_metrics(
        self,
        session_id: str,
        project_path: str,
        started_at: datetime,
        checkpoint_data: dict[str, Any],
    ) -> SessionMetrics:
        """Collect and store metrics from a completed session.

        Args:
            session_id: Unique session identifier
            project_path: Project working directory
            started_at: Session start time
            checkpoint_data: Checkpoint data with quality and history

        Returns:
            Collected SessionMetrics
        """
        # Extract metrics from checkpoint data
        ended_at = datetime.now(UTC)
        duration_minutes = (ended_at - started_at).total_seconds() / 60

        # Quality metrics
        quality_start = checkpoint_data.get("initial_quality_score", 0)
        quality_end = checkpoint_data.get("quality_score", 0)
        quality_delta = quality_end - quality_start
        avg_quality = (quality_start + quality_end) / 2

        # Activity metrics
        checkpoint_count = len(
            checkpoint_data.get("checkpoint_history", {}).get("checkpoints", [])
        )
        commit_count = checkpoint_data.get("git_commits", 0)

        # File and tool metrics
        edit_history = checkpoint_data.get("edit_history", [])
        files_modified = len({edit.get("file_path") for edit in edit_history})

        tool_usage = checkpoint_data.get("tool_usage", [])
        tools_used = list({tool.get("name") for tool in tool_usage})

        # Detect primary programming language
        primary_language = self._detect_primary_language(edit_history)

        # Determine time of day
        time_of_day = self._classify_time_of_day(started_at)

        # Create metrics object
        metrics = SessionMetrics(
            session_id=session_id,
            project_path=project_path,
            started_at=started_at,
            ended_at=ended_at,
            duration_minutes=duration_minutes,
            checkpoint_count=checkpoint_count,
            commit_count=commit_count,
            quality_start=quality_start,
            quality_end=quality_end,
            quality_delta=quality_delta,
            avg_quality=avg_quality,
            files_modified=files_modified,
            tools_used=tools_used,
            primary_language=primary_language,
            time_of_day=time_of_day,
        )

        # Store metrics
        await self.store.store_session_metrics(metrics)

        self.logger.info(
            f"Collected metrics for session {session_id}: "
            f"quality={avg_quality:.1f}, commits={commit_count}, "
            f"duration={duration_minutes:.0f}min"
        )

        return metrics

    def _detect_primary_language(
        self, edit_history: list[dict[str, Any]]
    ) -> str | None:
        """Detect primary programming language from edited files.

        Args:
            edit_history: List of edit operations

        Returns:
            Language name or None
        """
        language_extensions = {
            "Python": {".py"},
            "JavaScript": {".js", ".jsx", ".ts", ".tsx"},
            "Go": {".go"},
            "Rust": {".rs"},
            "Java": {".java"},
            "C/C++": {".c", ".cpp", ".h", ".hpp"},
            "Ruby": {".rb"},
            "PHP": {".php"},
        }

        extension_counts: dict[str, int] = {}

        for edit in edit_history:
            file_path = edit.get("file_path", "")
            _, ext = file_path.rsplit(".", 1) if "." in file_path else (None, None)

            if ext:
                ext_lower = f".{ext.lower()}"
                for lang, extensions in language_extensions.items():
                    if ext_lower in extensions:
                        extension_counts[lang] = extension_counts.get(lang, 0) + 1

        if not extension_counts:
            return None

        # Return language with most edits
        if extension_counts:
            return max(extension_counts.keys(), key=lambda x: extension_counts[x])
        return None

    def _classify_time_of_day(self, timestamp: datetime) -> str:
        """Classify timestamp into time of day category.

        Args:
            timestamp: Datetime to classify

        Returns:
            "morning", "afternoon", "evening", or "night"
        """
        hour = timestamp.hour

        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        return "night"

    async def get_workflow_metrics(
        self,
        project_path: str | None = None,
        days_back: int = 30,
    ) -> WorkflowMetrics:
        """Get workflow metrics for analysis.

        Args:
            project_path: Optional filter by project
            days_back: Number of days to look back (default: 30)

        Returns:
            Aggregated workflow metrics
        """
        end_date = datetime.now(UTC)
        start_date = end_date.replace(day=end_date.day - days_back)

        return await self.store.get_workflow_metrics(
            project_path=project_path,
            start_date=start_date,
            end_date=end_date,
        )

    def close(self) -> None:
        """Close metrics engine and release resources."""
        self.store.close()


# Dependency injection key
DEPENDENCY_KEY = "workflow_metrics_engine"


def get_workflow_metrics_engine() -> WorkflowMetricsEngine:
    """Get or create workflow metrics engine instance.

    This is the preferred way to access the metrics engine,
    using dependency injection for testability.

    Returns:
        Shared WorkflowMetricsEngine instance
    """
    engine = depends.get_sync(WorkflowMetricsEngine)
    if engine is None:
        engine = WorkflowMetricsEngine()
    return engine  # type: ignore[no-any-return]
