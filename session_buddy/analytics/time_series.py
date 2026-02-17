"""Time-series analysis for skill metrics trends.

This module provides time-series aggregation and trend detection for
skill performance metrics over time.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from scipy import stats

if TYPE_CHECKING:
    pass


@dataclass
class HourlyMetrics:
    """Aggregated metrics for a single hour.

    Attributes:
        timestamp: Hour timestamp (ISO format)
        skill_name: Name of skill
        invocation_count: Number of invocations in hour
        completion_rate: Success rate (0.0 to 1.0)
        avg_duration_seconds: Average duration in seconds
        unique_sessions: Number of unique sessions
    """

    timestamp: str
    skill_name: str
    invocation_count: int
    completion_rate: float
    avg_duration_seconds: float
    unique_sessions: int


@dataclass
class TrendAnalysis:
    """Result of trend detection analysis.

    Attributes:
        trend: Trend direction ("improving", "declining", "stable", "insufficient_data")
        slope: Linear regression slope (change per day)
        start_value: Metric value at start of window
        end_value: Metric value at end of window
        change_percent: Percentage change from start to end
        confidence: Statistical confidence (p-value)
    """

    trend: Literal["improving", "declining", "stable", "insufficient_data"]
    slope: float
    start_value: float
    end_value: float
    change_percent: float
    confidence: float


class TimeSeriesAnalyzer:
    """Analyze time-series data for skill metrics.

    Provides hourly aggregation and trend detection using linear regression
    to identify improving, declining, or stable performance patterns.

    Example:
        >>> analyzer = TimeSeriesAnalyzer(Path("skills.db"))
        >>> # Get hourly metrics for last 24 hours
        >>> hourly = analyzer.aggregate_hourly_metrics(hours=24)
        >>> for h in hourly:
        ...     print(f"{h.timestamp}: {h.completion_rate:.1%}")
        >>> # Detect trends
        >>> trend = analyzer.detect_trend("pytest-run", "completion_rate", window_days=7)
        >>> print(f"Trend: {trend.trend} ({trend.change_percent:.1f}%)")
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize time-series analyzer.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def aggregate_hourly_metrics(
        self,
        skill_name: str | None = None,
        hours: int = 24,
    ) -> list[HourlyMetrics]:
        """Aggregate metrics by hour for time-series analysis.

        Args:
            skill_name: Optional skill name filter (None = all skills)
            hours: Number of hours to aggregate

        Returns:
            List of hourly metrics, sorted by timestamp ascending
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build query based on skill filter
            if skill_name:
                cursor.execute(
                    f"""
                    SELECT
                        strftime('%Y-%m-%dT%H:00:00', invoked_at) as hour_timestamp,
                        skill_name,
                        COUNT(*) as invocation_count,
                        AVG(CASE WHEN completed = 1 THEN 1.0 ELSE 0.0 END) as completion_rate,
                        AVG(duration_seconds) as avg_duration_seconds,
                        COUNT(DISTINCT session_id) as unique_sessions
                    FROM skill_invocation
                    WHERE skill_name = ?
                    AND datetime(invoked_at) >= datetime('now', '-{hours} hours')
                    GROUP BY skill_name, hour_timestamp
                    ORDER BY hour_timestamp ASC
                    """
                )
            else:
                cursor.execute(
                    f"""
                    SELECT
                        strftime('%Y-%m-%dT%H:00:00', invoked_at) as hour_timestamp,
                        skill_name,
                        COUNT(*) as invocation_count,
                        AVG(CASE WHEN completed = 1 THEN 1.0 ELSE 0.0 END) as completion_rate,
                        AVG(duration_seconds) as avg_duration_seconds,
                        COUNT(DISTINCT session_id) as unique_sessions
                    FROM skill_invocation
                    WHERE datetime(invoked_at) >= datetime('now', '-{hours} hours')
                    GROUP BY skill_name, hour_timestamp
                    ORDER BY skill_name, hour_timestamp ASC
                    """
                )

            rows = cursor.fetchall()

        return [
            HourlyMetrics(
                timestamp=row["hour_timestamp"],
                skill_name=row["skill_name"],
                invocation_count=row["invocation_count"],
                completion_rate=row["completion_rate"] or 0.0,
                avg_duration_seconds=row["avg_duration_seconds"] or 0.0,
                unique_sessions=row["unique_sessions"],
            )
            for row in rows
        ]

    def detect_trend(
        self,
        skill_name: str,
        metric: str = "completion_rate",
        window_days: int = 7,
    ) -> TrendAnalysis:
        """Detect trend direction using linear regression.

        Analyzes metrics over a time window to determine if performance
        is improving, declining, or stable using statistical testing.

        Args:
            skill_name: Name of skill to analyze
            metric: Metric to analyze ("completion_rate", "avg_duration_seconds")
            window_days: Number of days to analyze

        Returns:
            TrendAnalysis with trend direction and statistics
        """
        # Query time-series data
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Map metric name to column
            metric_column = {
                "completion_rate": "AVG(CASE WHEN completed = 1 THEN 1.0 ELSE 0.0 END)",
                "avg_duration_seconds": "AVG(duration_seconds)",
            }.get(metric, metric)

            cursor.execute(
                f"""
                SELECT
                    DATE(invoked_at) as date,
                    {metric_column} as value
                FROM skill_invocation
                WHERE skill_name = ?
                AND datetime(invoked_at) >= datetime('now', '-{window_days} days')
                GROUP BY DATE(invoked_at)
                ORDER BY date ASC
                """,
                (skill_name,),
            )

            rows = cursor.fetchall()

        # Check for sufficient data
        if len(rows) < 3:
            return TrendAnalysis(
                trend="insufficient_data",
                slope=0.0,
                start_value=0.0,
                end_value=0.0,
                change_percent=0.0,
                confidence=1.0,
            )

        # Extract values and timestamps
        dates = [row["date"] for row in rows]
        values = [
            float(row["value"]) if row["value"] is not None else 0.0 for row in rows
        ]

        # Convert dates to numeric (days since first data point)
        start_date = datetime.fromisoformat(dates[0])
        x = np.array(
            [(datetime.fromisoformat(d) - start_date).days for d in dates], dtype=float
        )
        y = np.array(values)

        # Perform linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # Calculate start and end values
        start_value = float(y[0])
        end_value = float(y[-1])

        # Calculate percentage change
        if start_value != 0:
            change_percent = ((end_value - start_value) / abs(start_value)) * 100
        else:
            change_percent = 0.0

        # Determine trend direction
        # Use p-value < 0.05 for statistical significance
        if p_value < 0.05:
            if metric == "completion_rate":
                # Higher is better
                if slope > 0:
                    trend = "improving"
                else:
                    trend = "declining"
            elif metric == "avg_duration_seconds":
                # Lower is better (faster)
                if slope < 0:
                    trend = "improving"
                else:
                    trend = "declining"
            else:
                # Default: higher is better
                if slope > 0:
                    trend = "improving"
                else:
                    trend = "declining"
        else:
            # Not statistically significant
            trend = "stable"

        return TrendAnalysis(
            trend=trend,
            slope=float(slope),
            start_value=start_value,
            end_value=end_value,
            change_percent=change_percent,
            confidence=float(p_value),
        )

    def get_multi_skill_trends(
        self,
        metric: str = "completion_rate",
        window_days: int = 7,
        min_invocations: int = 10,
    ) -> dict[str, TrendAnalysis]:
        """Get trends for all skills with sufficient data.

        Args:
            metric: Metric to analyze
            window_days: Number of days to analyze
            min_invocations: Minimum invocations required

        Returns:
            Dictionary mapping skill names to trend analysis
        """
        # Get skills with sufficient data
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                f"""
                SELECT skill_name, COUNT(*) as count
                FROM skill_invocation
                WHERE datetime(invoked_at) >= datetime('now', '-{window_days} days')
                GROUP BY skill_name
                HAVING COUNT(*) >= ?
                ORDER BY count DESC
                """,
                (min_invocations,),
            )

            rows = cursor.fetchall()

        # Analyze trends for each skill
        trends = {}
        for row in rows:
            skill_name = row["skill_name"]
            try:
                trend = self.detect_trend(skill_name, metric, window_days)
                trends[skill_name] = trend
            except Exception:
                # Skip skills that fail analysis
                continue

        return trends

    def get_anomaly_detection(
        self,
        skill_name: str,
        metric: str = "completion_rate",
        window_hours: int = 24,
        z_threshold: float = 2.0,
    ) -> list[dict[str, object]]:
        """Detect anomalies in skill metrics using Z-score.

        Identifies hours where metrics deviate significantly from the mean.

        Args:
            skill_name: Name of skill to analyze
            metric: Metric to analyze
            window_hours: Hours to analyze
            z_threshold: Z-score threshold for anomaly detection

        Returns:
            List of anomalies with timestamps and scores
        """
        # Get hourly metrics
        hourly = self.aggregate_hourly_metrics(
            skill_name=skill_name, hours=window_hours
        )

        if not hourly:
            return []

        # Extract metric values
        metric_values = {
            "completion_rate": [h.completion_rate for h in hourly],
            "avg_duration_seconds": [h.avg_duration_seconds for h in hourly],
        }.get(metric, [])

        if not metric_values:
            return []

        # Calculate mean and std dev
        mean = np.mean(metric_values)
        std = np.std(metric_values)

        if std == 0:
            return []

        # Find anomalies
        anomalies = []
        for h, value in zip(hourly, metric_values):
            z_score = (value - mean) / std
            if abs(z_score) >= z_threshold:
                anomalies.append(
                    {
                        "timestamp": h.timestamp,
                        "skill_name": h.skill_name,
                        "metric": metric,
                        "value": value,
                        "z_score": z_score,
                        "deviation_type": "high" if z_score > 0 else "low",
                    }
                )

        return anomalies

    def get_time_series_plot_data(
        self,
        skill_name: str,
        metric: str = "completion_rate",
        hours: int = 168,  # 7 days
    ) -> dict[str, list]:
        """Get data formatted for time-series plotting.

        Args:
            skill_name: Name of skill
            metric: Metric to plot
            hours: Number of hours to include

        Returns:
            Dictionary with timestamps and values for plotting
        """
        hourly = self.aggregate_hourly_metrics(skill_name=skill_name, hours=hours)

        metric_values = {
            "completion_rate": [h.completion_rate for h in hourly],
            "avg_duration_seconds": [h.avg_duration_seconds for h in hourly],
            "invocation_count": [h.invocation_count for h in hourly],
        }.get(metric, [])

        return {
            "timestamps": [h.timestamp for h in hourly],
            "values": metric_values,
            "skill_name": skill_name,
            "metric": metric,
        }


def get_analyzer(db_path: Path | None = None) -> TimeSeriesAnalyzer:
    """Get or create time-series analyzer instance.

    Args:
        db_path: Path to database file. Defaults to
            `.session-buddy/skills.db` in current directory.

    Returns:
        TimeSeriesAnalyzer instance
    """
    if db_path is None:
        db_path = Path.cwd() / ".session-buddy" / "skills.db"

    return TimeSeriesAnalyzer(db_path=db_path)
