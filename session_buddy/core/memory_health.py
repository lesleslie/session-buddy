"""Memory health metrics for reflection and error monitoring.

This module provides comprehensive health analysis for the session memory system:
- Stale reflection detection and cleanup recommendations
- Error hot-spot identification from causal chain data
- Reflection database statistics and maintenance insights
- Memory optimization recommendations

Architecture:
    MemoryHealthAnalyzer → HealthMetrics → MemoryHealthStore
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReflectionHealthMetrics:
    """Health metrics for the reflection database.

    Attributes:
        total_reflections: Total number of stored reflections
        stale_reflections: Number of reflections older than threshold
        stale_threshold_days: Days before reflection is considered stale
        avg_reflection_age_days: Average age of all reflections
        tags_distribution: Count of reflections per tag
        storage_size_bytes: Estimated database storage size
        last_reflection_timestamp: Most recent reflection timestamp
        first_reflection_timestamp: Oldest reflection timestamp
    """

    total_reflections: int
    stale_reflections: int
    stale_threshold_days: int
    avg_reflection_age_days: float
    tags_distribution: dict[str, int]
    storage_size_bytes: int
    last_reflection_timestamp: datetime | None
    first_reflection_timestamp: datetime | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_reflections": self.total_reflections,
            "stale_reflections": self.stale_reflections,
            "stale_threshold_days": self.stale_threshold_days,
            "avg_reflection_age_days": self.avg_reflection_age_days,
            "tags_distribution": self.tags_distribution,
            "storage_size_mb": round(self.storage_size_bytes / 1024 / 1024, 2),
            "last_reflection_timestamp": (
                self.last_reflection_timestamp.isoformat()
                if self.last_reflection_timestamp
                else None
            ),
            "first_reflection_timestamp": (
                self.first_reflection_timestamp.isoformat()
                if self.first_reflection_timestamp
                else None
            ),
        }


@dataclass(frozen=True)
class ErrorHotSpotMetrics:
    """Metrics for error patterns and hot-spots.

    Attributes:
        total_errors: Total unique errors tracked
        most_common_error_types: Error types with frequency
        avg_resolution_time_minutes: Average time to fix errors
        fastest_resolution_minutes: Quickest fix time
        slowest_resolution_minutes: Longest fix time
        unresolved_errors: Number of errors without successful fix
        recent_error_rate: Errors per day in last 30 days
    """

    total_errors: int
    most_common_error_types: list[tuple[str, int]]
    avg_resolution_time_minutes: float
    fastest_resolution_minutes: float | None
    slowest_resolution_minutes: float | None
    unresolved_errors: int
    recent_error_rate: float  # errors per day

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_errors": self.total_errors,
            "most_common_error_types": [
                {"error_type": error_type, "count": count}
                for error_type, count in self.most_common_error_types
            ],
            "avg_resolution_time_minutes": round(self.avg_resolution_time_minutes, 2),
            "fastest_resolution_minutes": round(self.fastest_resolution_minutes, 2)
            if self.fastest_resolution_minutes
            else None,
            "slowest_resolution_minutes": round(self.slowest_resolution_minutes, 2)
            if self.slowest_resolution_minutes
            else None,
            "unresolved_errors": self.unresolved_errors,
            "recent_error_rate": round(self.recent_error_rate, 2),
        }


class MemoryHealthAnalyzer:
    """Analyze memory health and error patterns.

    Provides comprehensive health analysis for:
        - Reflection database maintenance
        - Error pattern detection
        - Storage optimization recommendations

    Usage:
        >>> analyzer = MemoryHealthAnalyzer()
        >>> await analyzer.initialize()
        >>> reflection_health = await analyzer.get_reflection_health()
        >>> error_hotspots = await analyzer.get_error_hotspots()
    """

    def __init__(
        self,
        db_path: str = "~/.claude/data/memory",
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize memory health analyzer.

        Args:
            db_path: Path to memory database directory
            logger: Optional logger instance
        """
        import os

        self.db_path = os.path.expanduser(db_path)
        self.logger = logger or logging.getLogger(__name__)
        self._conn: Any = None

    def _get_conn(self) -> Any:
        """Get or create database connection."""
        if self._conn is None:
            # Connect to reflection database
            db_file = f"{self.db_path}/reflections.db"
            self._conn = duckdb.connect(db_file)  # type: ignore[attr-defined]
        return self._conn

    async def initialize(self) -> None:
        """Initialize analyzer (ensures database is ready)."""
        _ = self._get_conn()
        self.logger.info("Memory health analyzer initialized")

    async def get_reflection_health(
        self, stale_threshold_days: int = 90
    ) -> ReflectionHealthMetrics:
        """Analyze reflection database health.

        Args:
            stale_threshold_days: Days before reflection is considered stale

        Returns:
            Reflection health metrics with staleness analysis
        """
        conn = self._get_conn()

        # Check if reflections table exists
        table_check = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'reflections'
        """
        ).fetchone()

        if not table_check:
            # No reflections table yet
            return ReflectionHealthMetrics(
                total_reflections=0,
                stale_reflections=0,
                stale_threshold_days=stale_threshold_days,
                avg_reflection_age_days=0.0,
                tags_distribution={},
                storage_size_bytes=0,
                last_reflection_timestamp=None,
                first_reflection_timestamp=None,
            )

        # Total reflections
        total_result = conn.execute("SELECT COUNT(*) FROM reflections").fetchone()
        total_reflections = total_result[0] if total_result else 0

        if total_reflections == 0:
            return ReflectionHealthMetrics(
                total_reflections=0,
                stale_reflections=0,
                stale_threshold_days=stale_threshold_days,
                avg_reflection_age_days=0.0,
                tags_distribution={},
                storage_size_bytes=0,
                last_reflection_timestamp=None,
                first_reflection_timestamp=None,
            )

        # Timestamp range
        timestamps = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM reflections"
        ).fetchone()

        first_timestamp, last_timestamp = timestamps

        # Calculate stale reflections
        stale_cutoff = datetime.now(UTC) - timedelta(days=stale_threshold_days)
        stale_result = conn.execute(
            """
            SELECT COUNT(*)
            FROM reflections
            WHERE timestamp < ?
        """,
            [stale_cutoff],
        ).fetchone()
        stale_reflections = stale_result[0] if stale_result else 0

        # Average age
        avg_age_result = conn.execute(
            """
            SELECT AVG(DATEDIFF('day', timestamp, CURRENT_TIMESTAMP))
            FROM reflections
        """
        ).fetchone()
        avg_age = (
            float(avg_age_result[0]) if avg_age_result and avg_age_result[0] else 0.0
        )

        # Tag distribution
        tags_result = conn.execute(
            """
            SELECT unnest(tags) as tag, COUNT(*) as count
            FROM reflections
            GROUP BY tag
            ORDER BY count DESC
        """
        ).fetchall()

        tags_distribution = {row[0]: row[1] for row in tags_result}

        # Storage size (estimated)
        size_result = conn.execute(
            """
            SELECT pg_size FROM pg_database_size('reflections.db')
        """
        ).fetchone()
        storage_size = size_result[0] if size_result else 0

        return ReflectionHealthMetrics(
            total_reflections=total_reflections,
            stale_reflections=stale_reflections,
            stale_threshold_days=stale_threshold_days,
            avg_reflection_age_days=abs(avg_age),
            tags_distribution=tags_distribution,
            storage_size_bytes=storage_size,
            last_reflection_timestamp=last_timestamp,
            first_reflection_timestamp=first_timestamp,
        )

    async def get_error_hotspots(self) -> ErrorHotSpotMetrics:
        """Analyze error patterns and hot-spots.

        Returns:
            Error hot-spot metrics with pattern analysis
        """
        conn = self._get_conn()

        # Check if causal chain tables exist
        error_table_check = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'causal_error_events'
        """
        ).fetchone()

        if not error_table_check:
            # No error tracking yet
            return ErrorHotSpotMetrics(
                total_errors=0,
                most_common_error_types=[],
                avg_resolution_time_minutes=0.0,
                fastest_resolution_minutes=None,
                slowest_resolution_minutes=None,
                unresolved_errors=0,
                recent_error_rate=0.0,
            )

        # Total unique errors
        total_errors_result = conn.execute(
            "SELECT COUNT(*) FROM causal_error_events"
        ).fetchone()
        total_errors = total_errors_result[0] if total_errors_result else 0

        if total_errors == 0:
            return ErrorHotSpotMetrics(
                total_errors=0,
                most_common_error_types=[],
                avg_resolution_time_minutes=0.0,
                fastest_resolution_minutes=None,
                slowest_resolution_minutes=None,
                unresolved_errors=0,
                recent_error_rate=0.0,
            )

        # Most common error types
        error_types_result = conn.execute(
            """
            SELECT error_type, COUNT(*) as count
            FROM causal_error_events
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10
        """
        ).fetchall()

        most_common_error_types = [(row[0], row[1]) for row in error_types_result]

        # Resolution time statistics
        resolution_stats = conn.execute(
            """
            SELECT
                MIN(resolution_time_minutes) as min_time,
                MAX(resolution_time_minutes) as max_time,
                AVG(resolution_time_minutes) as avg_time
            FROM causal_chains
        """
        ).fetchone()

        min_time, max_time, avg_time = resolution_stats

        # Unresolved errors (errors without causal chain)
        unresolved_result = conn.execute(
            """
            SELECT COUNT(DISTINCT e.id)
            FROM causal_error_events e
            LEFT JOIN causal_chains c ON e.id = c.error_id
            WHERE c.id IS NULL
        """
        ).fetchone()
        unresolved_errors = unresolved_result[0] if unresolved_result else 0

        # Recent error rate (last 30 days)
        recent_cutoff = datetime.now(UTC) - timedelta(days=30)
        recent_errors_result = conn.execute(
            """
            SELECT COUNT(*)
            FROM causal_error_events
            WHERE timestamp >= ?
        """,
            [recent_cutoff],
        ).fetchone()
        recent_error_count = recent_errors_result[0] if recent_errors_result else 0
        recent_error_rate = recent_error_count / 30.0  # errors per day

        return ErrorHotSpotMetrics(
            total_errors=total_errors,
            most_common_error_types=most_common_error_types,
            avg_resolution_time_minutes=float(avg_time or 0),
            fastest_resolution_minutes=float(min_time) if min_time else None,
            slowest_resolution_minutes=float(max_time) if max_time else None,
            unresolved_errors=unresolved_errors,
            recent_error_rate=recent_error_rate,
        )

    async def get_cleanup_recommendations(self) -> list[dict[str, Any]]:
        """Generate cleanup and optimization recommendations.

        Returns:
            List of recommendation dictionaries with action, priority, and details
        """
        recommendations = []

        # Analyze reflection health
        reflection_health = await self.get_reflection_health()
        error_hotspots = await self.get_error_hotspots()

        # Stale reflection cleanup
        if reflection_health.stale_reflections > 0:
            stale_pct = (
                reflection_health.stale_reflections
                / reflection_health.total_reflections
                * 100
                if reflection_health.total_reflections > 0
                else 0
            )
            recommendations.append(
                {
                    "action": "clean_stale_reflections",
                    "priority": "medium" if stale_pct < 20 else "high",
                    "category": "maintenance",
                    "details": (
                        f"Remove {reflection_health.stale_reflections} stale reflections "
                        f"({stale_pct:.1f}% of total) older than "
                        f"{reflection_health.stale_threshold_days} days"
                    ),
                    "estimated_impact": "Reduces database size by unknown amount",
                }
            )

        # Large storage size
        storage_mb = reflection_health.storage_size_bytes / 1024 / 1024
        if storage_mb > 100:  # 100MB threshold
            recommendations.append(
                {
                    "action": "optimize_storage",
                    "priority": "low" if storage_mb < 500 else "medium",
                    "category": "optimization",
                    "details": f"Database size is {storage_mb:.1f}MB - consider archiving old reflections",
                    "estimated_impact": "Reduces storage requirements",
                }
            )

        # High error rate
        if error_hotspots.recent_error_rate > 2.0:
            recommendations.append(
                {
                    "action": "investigate_error_pattern",
                    "priority": "high",
                    "category": "quality",
                    "details": (
                        f"High error rate: {error_hotspots.recent_error_rate:.1f} errors/day "
                        f"over last 30 days"
                    ),
                    "estimated_impact": "Improves code quality and development velocity",
                }
            )

        # Unresolved errors
        if error_hotspots.unresolved_errors > 5:
            recommendations.append(
                {
                    "action": "review_unresolved_errors",
                    "priority": "medium",
                    "category": "debugging",
                    "details": (
                        f"{error_hotspots.unresolved_errors} errors have no recorded fix - "
                        "review and document solutions"
                    ),
                    "estimated_impact": "Builds debugging intelligence knowledge base",
                }
            )

        # Common error types
        if error_hotspots.most_common_error_types:
            top_error_type, top_count = error_hotspots.most_common_error_types[0]
            if top_count >= 3:
                recommendations.append(
                    {
                        "action": "address_recurring_error",
                        "priority": "high" if top_count >= 5 else "medium",
                        "category": "quality",
                        "details": (
                            f"'{top_error_type}' occurs {top_count} times - "
                            "consider systemic fix or improved documentation"
                        ),
                        "estimated_impact": "Reduces recurring debugging time",
                    }
                )

        return recommendations

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# Dependency injection key
DEPENDENCY_KEY = "memory_health_analyzer"


def get_memory_health_analyzer() -> MemoryHealthAnalyzer:
    """Get or create memory health analyzer instance.

    This is the preferred way to access the analyzer,
    using dependency injection for testability.

    Returns:
        Shared MemoryHealthAnalyzer instance
    """
    from session_buddy.di import depends

    analyzer = depends.get_sync(MemoryHealthAnalyzer)
    if analyzer is None:
        analyzer = MemoryHealthAnalyzer()
    return analyzer  # type: ignore[no-any-return]
