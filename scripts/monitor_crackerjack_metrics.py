#!/usr/bin/env python3
"""Crackerjack Metrics Monitoring Dashboard.

This script analyzes historical Crackerjack execution data to provide:
- Quality score trends over time
- Command execution patterns
- Performance metrics
- Quality degradation alerts
- Improvement highlights
- Project-specific insights

Usage:
    python scripts/monitor_crackerjack_metrics.py                    # Full report
    python scripts/monitor_crackerjack_metrics.py --days 7           # Last 7 days
    python scripts/monitor_crackerjack_metrics.py --project /path    # Specific project
    python scripts/monitor_crackerjack_metrics.py --format json      # JSON output
    python scripts/monitor_crackerjack_metrics.py --alert-threshold 10  # Custom threshold
"""

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class MetricTrend:
    """Represents a metric trend over time."""
    metric_type: str
    current_value: float
    previous_value: float
    change: float
    change_percentage: float
    direction: str  # "improving", "declining", "stable"
    strength: str  # "strong", "moderate", "weak"
    data_points: int


@dataclass
class QualityAlert:
    """Represents a quality degradation alert."""
    severity: str  # "critical", "warning", "info"
    metric_type: str
    message: str
    current_value: float
    previous_value: float
    change_percentage: float
    timestamp: str


@dataclass
class CommandStats:
    """Statistics for a command type."""
    command: str
    total_executions: int
    successful_executions: int
    success_rate: float
    avg_execution_time: float
    failure_count: int


@dataclass
class MonitoringReport:
    """Comprehensive monitoring report."""
    report_generated: str
    analysis_period_days: int
    total_records: int
    database_path: str
    summary: dict[str, Any]
    metric_trends: dict[str, MetricTrend]
    command_statistics: list[CommandStats]
    quality_alerts: list[QualityAlert]
    project_insights: dict[str, dict[str, Any]]
    performance_metrics: dict[str, Any]
    recommendations: list[str]


class CrackerjackMetricsMonitor:
    """Monitor and analyze Crackerjack metrics."""

    def __init__(
        self,
        db_path: str | None = None,
        alert_threshold: float = 10.0,
    ):
        """Initialize the monitor.

        Args:
            db_path: Path to SQLite database (default: ~/.claude/data/crackerjack_integration.db)
            alert_threshold: Percentage change to trigger alerts (default: 10%%)
        """
        self.db_path = db_path or str(
            Path.home() / ".claude" / "data" / "crackerjack_integration.db"
        )
        self.alert_threshold = alert_threshold

        if not Path(self.db_path).exists():
            raise FileNotFoundError(
                f"Database not found: {self.db_path}\n"
                "Run some crackerjack commands first to populate data."
            )

    def generate_report(
        self,
        days: int = 30,
        project_filter: str | None = None,
    ) -> MonitoringReport:
        """Generate comprehensive monitoring report.

        Args:
            days: Number of days to analyze (default: 30)
            project_filter: Optional project path filter

        Returns:
            MonitoringReport with all analysis data
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            summary = self._analyze_summary(conn, days, project_filter)
            metric_trends = self._analyze_metric_trends(conn, days, project_filter)
            command_stats = self._analyze_command_statistics(conn, days, project_filter)
            quality_alerts = self._generate_quality_alerts(metric_trends, summary)
            project_insights = self._analyze_project_insights(conn, days)
            performance_metrics = self._analyze_performance_metrics(conn, days, project_filter)
            recommendations = self._generate_recommendations(
                metric_trends, command_stats, quality_alerts
            )

        return MonitoringReport(
            report_generated=datetime.now().isoformat(),
            analysis_period_days=days,
            total_records=summary.get("total_records", 0),
            database_path=self.db_path,
            summary=summary,
            metric_trends=metric_trends,
            command_statistics=command_stats,
            quality_alerts=quality_alerts,
            project_insights=project_insights,
            performance_metrics=performance_metrics,
            recommendations=recommendations,
        )

    def _analyze_summary(
        self,
        conn: sqlite3.Connection,
        days: int,
        project_filter: str | None = None,
    ) -> dict[str, Any]:
        """Analyze overall summary statistics."""
        since = (datetime.now() - timedelta(days=days)).isoformat()

        where_clause = "WHERE timestamp >= ?"
        params = [since]

        if project_filter:
            where_clause += " AND working_directory = ?"
            params.append(project_filter)

        # Get basic stats
        cursor = conn.execute(
            f"""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT command) as unique_commands,
                SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) as successful,
                ROUND(AVG(execution_time), 3) as avg_execution_time,
                MIN(timestamp) as first_record,
                MAX(timestamp) as last_record
            FROM crackerjack_results
            {where_clause}
            """,
            params,
        )
        row = cursor.fetchone()

        summary = dict(row) if row else {}

        # Calculate success rate
        if summary.get("total_records", 0) > 0:
            summary["success_rate"] = round(
                (summary.get("successful", 0) / summary["total_records"]) * 100, 2
            )
        else:
            summary["success_rate"] = 0.0

        # Get metrics history stats
        cursor = conn.execute(
            f"""
            SELECT
                COUNT(*) as metric_records,
                COUNT(DISTINCT metric_type) as metric_types
            FROM quality_metrics_history
            WHERE timestamp >= ?
            {" AND project_path = ?" if project_filter else ""}
            """,
            [since] + ([project_filter] if project_filter else []),
        )
        metrics_row = cursor.fetchone()
        if metrics_row:
            summary.update(dict(metrics_row))

        return summary

    def _analyze_metric_trends(
        self,
        conn: sqlite3.Connection,
        days: int,
        project_filter: str | None = None,
    ) -> dict[str, MetricTrend]:
        """Analyze quality metric trends over time."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        mid_point = (datetime.now() - timedelta(days=days // 2)).isoformat()

        where_clause = "WHERE timestamp >= ?"
        params = [since]

        if project_filter:
            where_clause += " AND project_path = ?"
            params.append(project_filter)

        query = f"""
            SELECT
                metric_type,
                AVG(CASE WHEN timestamp >= ? THEN metric_value ELSE NULL END) as current_avg,
                AVG(CASE WHEN timestamp < ? THEN metric_value ELSE NULL END) as previous_avg,
                COUNT(*) as data_points
            FROM quality_metrics_history
            {where_clause}
            GROUP BY metric_type
            HAVING current_avg IS NOT NULL AND previous_avg IS NOT NULL
        """

        cursor = conn.execute(query, [mid_point, mid_point] + params)
        trends = {}

        for row in cursor.fetchall():
            metric_type = row["metric_type"]
            current_avg = row["current_avg"] or 0
            previous_avg = row["previous_avg"] or 0
            change = current_avg - previous_avg
            change_percentage = (
                abs(change / previous_avg * 100) if previous_avg != 0 else 0
            )

            # Determine direction (for quality metrics, higher is usually better)
            # Except for complexity where lower is better
            if metric_type == "complexity_score":
                direction = "improving" if change < 0 else "declining" if change > 0 else "stable"
            else:
                direction = "improving" if change > 0 else "declining" if change < 0 else "stable"

            # Determine strength
            abs_change = abs(change_percentage)
            if abs_change > 5:
                strength = "strong"
            elif abs_change > 1:
                strength = "moderate"
            else:
                strength = "weak"

            trends[metric_type] = MetricTrend(
                metric_type=metric_type,
                current_value=round(current_avg, 2),
                previous_value=round(previous_avg, 2),
                change=round(change, 2),
                change_percentage=round(change_percentage, 2),
                direction=direction,
                strength=strength,
                data_points=row["data_points"],
            )

        return trends

    def _analyze_command_statistics(
        self,
        conn: sqlite3.Connection,
        days: int,
        project_filter: str | None = None,
    ) -> list[CommandStats]:
        """Analyze command execution statistics."""
        since = (datetime.now() - timedelta(days=days)).isoformat()

        where_clause = "WHERE timestamp >= ?"
        params = [since]

        if project_filter:
            where_clause += " AND working_directory = ?"
            params.append(project_filter)

        query = f"""
            SELECT
                command,
                COUNT(*) as total_executions,
                SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) as successful_executions,
                AVG(execution_time) as avg_execution_time
            FROM crackerjack_results
            {where_clause}
            GROUP BY command
            HAVING total_executions >= 3
            ORDER BY total_executions DESC
        """

        cursor = conn.execute(query, params)
        stats = []

        for row in cursor.fetchall():
            total = row["total_executions"]
            successful = row["successful_executions"]
            success_rate = round((successful / total) * 100, 2) if total > 0 else 0

            stats.append(
                CommandStats(
                    command=row["command"],
                    total_executions=total,
                    successful_executions=successful,
                    success_rate=success_rate,
                    avg_execution_time=round(row["avg_execution_time"] or 0, 3),
                    failure_count=total - successful,
                )
            )

        return stats

    def _generate_quality_alerts(
        self,
        trends: dict[str, MetricTrend],
        summary: dict[str, Any],
    ) -> list[QualityAlert]:
        """Generate quality alerts based on trends."""
        alerts = []
        now = datetime.now().isoformat()

        for metric_type, trend in trends.items():
            # Skip stable trends
            if trend.direction == "stable":
                continue

            # Check if change exceeds threshold
            if trend.change_percentage >= self.alert_threshold:
                # Determine severity
                if trend.change_percentage >= 20:
                    severity = "critical"
                elif trend.change_percentage >= 15:
                    severity = "warning"
                else:
                    severity = "info"

                # Generate alert message
                if trend.direction == "declining":
                    message = (
                        f"{metric_type} has declined by {trend.change_percentage:.1f}% "
                        f"(from {trend.previous_value} to {trend.current_value})"
                    )
                else:
                    message = (
                        f"{metric_type} has improved by {trend.change_percentage:.1f}% "
                        f"(from {trend.previous_value} to {trend.current_value})"
                    )

                alerts.append(
                    QualityAlert(
                        severity=severity,
                        metric_type=metric_type,
                        message=message,
                        current_value=trend.current_value,
                        previous_value=trend.previous_value,
                        change_percentage=trend.change_percentage,
                        timestamp=now,
                    )
                )

        # Sort by severity and change percentage
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(
            key=lambda a: (severity_order.get(a.severity, 3), -a.change_percentage)
        )

        return alerts

    def _analyze_project_insights(
        self,
        conn: sqlite3.Connection,
        days: int,
    ) -> dict[str, dict[str, Any]]:
        """Analyze insights per project."""
        since = (datetime.now() - timedelta(days=days)).isoformat()

        query = """
            SELECT
                working_directory as project_path,
                COUNT(*) as executions,
                SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) as successful,
                AVG(execution_time) as avg_time,
                MIN(timestamp) as first_run,
                MAX(timestamp) as last_run
            FROM crackerjack_results
            WHERE timestamp >= ?
            GROUP BY working_directory
            HAVING executions >= 3
            ORDER BY executions DESC
            LIMIT 20
        """

        cursor = conn.execute(query, [since])
        insights = {}

        for row in cursor.fetchall():
            project_path = row["project_path"]
            total = row["executions"]
            successful = row["successful"]

            insights[project_path] = {
                "executions": total,
                "success_rate": round((successful / total) * 100, 2) if total > 0 else 0,
                "avg_execution_time": round(row["avg_time"] or 0, 3),
                "first_run": row["first_run"],
                "last_run": row["last_run"],
                "days_active": (
                    datetime.fromisoformat(row["last_run"]) -
                    datetime.fromisoformat(row["first_run"])
                ).days + 1,
            }

        return insights

    def _analyze_performance_metrics(
        self,
        conn: sqlite3.Connection,
        days: int,
        project_filter: str | None = None,
    ) -> dict[str, Any]:
        """Analyze performance metrics."""
        since = (datetime.now() - timedelta(days=days)).isoformat()

        where_clause = "WHERE timestamp >= ? AND execution_time IS NOT NULL"
        params = [since]

        if project_filter:
            where_clause += " AND working_directory = ?"
            params.append(project_filter)

        # Overall performance
        cursor = conn.execute(
            f"""
            SELECT
                AVG(execution_time) as avg_time,
                MIN(execution_time) as min_time,
                MAX(execution_time) as max_time,
                COUNT(*) as total_executions
            FROM crackerjack_results
            {where_clause}
            """,
            params,
        )
        row = cursor.fetchone()

        metrics = {
            "avg_execution_time": round(row["avg_time"] or 0, 3),
            "min_execution_time": round(row["min_time"] or 0, 3),
            "max_execution_time": round(row["max_time"] or 0, 3),
            "total_executions": row["total_executions"],
        }

        # Slowest commands
        cursor = conn.execute(
            f"""
            SELECT
                command,
                AVG(execution_time) as avg_time,
                COUNT(*) as executions
            FROM crackerjack_results
            {where_clause}
            GROUP BY command
            HAVING executions >= 3
            ORDER BY avg_time DESC
            LIMIT 5
            """,
            params,
        )

        metrics["slowest_commands"] = [
            {"command": row["command"], "avg_time": round(row["avg_time"], 3)}
            for row in cursor.fetchall()
        ]

        # Fastest commands (with at least 3 executions)
        cursor = conn.execute(
            f"""
            SELECT
                command,
                AVG(execution_time) as avg_time,
                COUNT(*) as executions
            FROM crackerjack_results
            {where_clause}
            GROUP BY command
            HAVING executions >= 3
            ORDER BY avg_time ASC
            LIMIT 5
            """,
            params,
        )

        metrics["fastest_commands"] = [
            {"command": row["command"], "avg_time": round(row["avg_time"], 3)}
            for row in cursor.fetchall()
        ]

        return metrics

    def _generate_recommendations(
        self,
        trends: dict[str, MetricTrend],
        command_stats: list[CommandStats],
        alerts: list[QualityAlert],
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Quality-based recommendations
        declining_metrics = [
            (m, t) for m, t in trends.items() if t.direction == "declining"
        ]

        if declining_metrics:
            for metric_type, trend in declining_metrics:
                if trend.strength == "strong":
                    if metric_type == "build_status":
                        recommendations.append(
                            f"CRITICAL: Build success rate declining by "
                            f"{trend.change_percentage:.1f}% - investigate failing builds"
                        )
                    elif metric_type == "lint_score":
                        recommendations.append(
                            f"WARNING: Code quality declining - run 'crackerjack lint' "
                            f"and address issues"
                        )
                    elif metric_type == "security_score":
                        recommendations.append(
                            f"SECURITY: Security score declining - run "
                            f"'crackerjack security' and review findings"
                        )
                    elif metric_type == "complexity_score":
                        recommendations.append(
                            f"TECHNICAL DEBT: Complexity increasing - consider "
                            f"refactoring complex modules"
                        )

        # Command failure recommendations
        failing_commands = [c for c in command_stats if c.failure_count > 0]
        if failing_commands:
            worst = max(failing_commands, key=lambda c: c.failure_count)
            if worst.failure_count >= worst.total_executions * 0.3:
                recommendations.append(
                    f"High failure rate for '{worst.command}' command "
                    f"({worst.failure_count}/{worst.total_executions} failed) - investigate"
                )

        # Performance recommendations
        slow_commands = [c for c in command_stats if c.avg_execution_time > 30]
        if slow_commands:
            slowest = max(slow_commands, key=lambda c: c.avg_execution_time)
            recommendations.append(
                f"Performance: '{slowest.command}' averaging {slowest.avg_execution_time:.1f}s - "
                f"consider optimization"
            )

        # Positive reinforcement
        improving_metrics = [
            (m, t) for m, t in trends.items()
            if t.direction == "improving" and t.strength == "strong"
        ]

        if improving_metrics:
            for metric_type, trend in improving_metrics[:3]:  # Top 3
                recommendations.append(
                    f"EXCELLENT: {metric_type} improving by {trend.change_percentage:.1f}% - "
                    f"keep up the good work!"
                )

        # Default if everything is stable
        if not recommendations:
            recommendations.append(
                "All metrics stable - continue current development practices"
            )

        return recommendations


def format_markdown_report(report: MonitoringReport) -> str:
    """Format monitoring report as Markdown."""
    lines = [
        "# Crackerjack Metrics Monitoring Report",
        "",
        f"**Generated:** {report.report_generated}",
        f"**Analysis Period:** {report.analysis_period_days} days",
        f"**Total Records Analyzed:** {report.total_records:,}",
        "",
        "---",
        "",
    ]

    # Executive Summary
    lines.extend([
        "## Executive Summary",
        "",
        f"- **Total Executions:** {report.summary.get('total_records', 0):,}",
        f"- **Success Rate:** {report.summary.get('success_rate', 0):.1f}%",
        f"- **Unique Commands:** {report.summary.get('unique_commands', 0)}",
        f"- **Avg Execution Time:** {report.summary.get('avg_execution_time', 0):.3f}s",
        f"- **Metric Records:** {report.summary.get('metric_records', 0):,}",
        "",
    ])

    # Quality Alerts
    if report.quality_alerts:
        lines.extend([
            "## Quality Alerts",
            "",
        ])

        for alert in report.quality_alerts:
            emoji = "🔴" if alert.severity == "critical" else "🟡" if alert.severity == "warning" else "🟢"
            lines.extend([
                f"### {emoji} {alert.severity.upper()}: {alert.metric_type}",
                "",
                f"- **Message:** {alert.message}",
                f"- **Current Value:** {alert.current_value}",
                f"- **Previous Value:** {alert.previous_value}",
                f"- **Change:** {alert.change_percentage:.1f}%",
                "",
            ])
    else:
        lines.extend([
            "## Quality Alerts",
            "",
            "✅ No quality alerts - all metrics within normal thresholds",
            "",
        ])

    # Metric Trends
    if report.metric_trends:
        lines.extend([
            "## Metric Trends",
            "",
        ])

        for metric_type, trend in sorted(report.metric_trends.items()):
            direction_emoji = "📈" if trend.direction == "improving" else "📉" if trend.direction == "declining" else "➡️"
            strength_emoji = "⚡" if trend.strength == "strong" else "🔄" if trend.strength == "moderate" else "📍"

            lines.extend([
                f"### {direction_emoji} {metric_type} {strength_emoji}",
                "",
                f"- **Current:** {trend.current_value}",
                f"- **Previous:** {trend.previous_value}",
                f"- **Change:** {trend.change:+.2f} ({trend.change_percentage:+.1f}%)",
                f"- **Direction:** {trend.direction}",
                f"- **Strength:** {trend.strength}",
                f"- **Data Points:** {trend.data_points}",
                "",
            ])

    # Command Statistics
    if report.command_statistics:
        lines.extend([
            "## Command Statistics",
            "",
            "| Command | Executions | Success Rate | Avg Time | Failures |",
            "|---------|------------|--------------|----------|----------|",
        ])

        for stats in report.command_statistics[:15]:  # Top 15
            lines.append(
                f"| {stats.command} | {stats.total_executions} | "
                f"{stats.success_rate:.1f}% | {stats.avg_execution_time:.3f}s | "
                f"{stats.failure_count} |"
            )

        lines.append("")

    # Performance Metrics
    lines.extend([
        "## Performance Metrics",
        "",
        f"- **Average Execution Time:** {report.performance_metrics.get('avg_execution_time', 0):.3f}s",
        f"- **Min Execution Time:** {report.performance_metrics.get('min_execution_time', 0):.3f}s",
        f"- **Max Execution Time:** {report.performance_metrics.get('max_execution_time', 0):.3f}s",
        "",
    ])

    if report.performance_metrics.get("slowest_commands"):
        lines.extend([
            "### Slowest Commands",
            "",
            "| Command | Avg Time |",
            "|---------|----------|",
        ])
        for cmd in report.performance_metrics["slowest_commands"]:
            lines.append(f"| {cmd['command']} | {cmd['avg_time']:.3f}s |")
        lines.append("")

    if report.performance_metrics.get("fastest_commands"):
        lines.extend([
            "### Fastest Commands",
            "",
            "| Command | Avg Time |",
            "|---------|----------|",
        ])
        for cmd in report.performance_metrics["fastest_commands"]:
            lines.append(f"| {cmd['command']} | {cmd['avg_time']:.3f}s |")
        lines.append("")

    # Project Insights
    if report.project_insights:
        lines.extend([
            "## Project Insights",
            "",
            "| Project | Executions | Success Rate | Avg Time | Active Days |",
            "|---------|------------|--------------|----------|------------|",
        ])

        # Sort by executions
        sorted_projects = sorted(
            report.project_insights.items(),
            key=lambda x: x[1]["executions"],
            reverse=True,
        )[:10]

        for project_path, insights in sorted_projects:
            # Shorten path for display
            display_path = project_path if len(project_path) <= 50 else "..." + project_path[-47:]
            lines.append(
                f"| {display_path} | {insights['executions']} | "
                f"{insights['success_rate']:.1f}% | {insights['avg_execution_time']:.3f}s | "
                f"{insights['days_active']} |"
            )

        lines.append("")

    # Recommendations
    lines.extend([
        "## Recommendations",
        "",
    ])

    for i, rec in enumerate(report.recommendations, 1):
        lines.append(f"{i}. {rec}")

    lines.extend([
        "",
        "---",
        "",
        f"*Report generated by Crackerjack Metrics Monitor*",
        f"*Database: {report.database_path}*",
    ])

    return "\n".join(lines)


def format_json_report(report: MonitoringReport) -> str:
    """Format monitoring report as JSON."""
    # Convert dataclasses to dicts
    report_dict = asdict(report)

    # Convert metric_trends from dict to list for better JSON structure
    if "metric_trends" in report_dict:
        report_dict["metric_trends"] = {
            k: asdict(v) for k, v in report.metric_trends.items()
        }

    # Convert command_stats to list of dicts
    if "command_statistics" in report_dict:
        report_dict["command_statistics"] = [
            asdict(s) for s in report.command_statistics
        ]

    # Convert alerts to list of dicts
    if "quality_alerts" in report_dict:
        report_dict["quality_alerts"] = [
            asdict(a) for a in report.quality_alerts
        ]

    return json.dumps(report_dict, indent=2, default=str)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor and analyze Crackerjack metrics",
    epilog="""
Examples:
  python scripts/monitor_crackerjack_metrics.py                    # Full 30-day report
  python scripts/monitor_crackerjack_metrics.py --days 7           # Last 7 days
  python scripts/monitor_crackerjack_metrics.py --project /path    # Specific project
  python scripts/monitor_crackerjack_metrics.py --format json      # JSON output
  python scripts/monitor_crackerjack_metrics.py --alert-threshold 15  # 15%% threshold
  python scripts/monitor_crackerjack_metrics.py --output report.md # Save to file
    """,
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)",
    )

    parser.add_argument(
        "--project",
        type=str,
        help="Filter by project path",
    )

    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path (default: stdout)",
    )

    parser.add_argument(
        "--alert-threshold",
        type=float,
        default=10.0,
        help="Percentage change to trigger alerts (default: 10.0)",
    )

    parser.add_argument(
        "--db-path",
        type=str,
        help="Custom database path",
    )

    args = parser.parse_args()

    try:
        # Initialize monitor
        monitor = CrackerjackMetricsMonitor(
            db_path=args.db_path,
            alert_threshold=args.alert_threshold,
        )

        # Generate report
        report = monitor.generate_report(
            days=args.days,
            project_filter=args.project,
        )

        # Format output
        if args.format == "json":
            output = format_json_report(report)
        else:
            output = format_markdown_report(report)

        # Write output
        if args.output:
            Path(args.output).write_text(output)
            print(f"Report saved to: {args.output}", file=sys.stderr)
            return 0
        else:
            print(output)
            return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
