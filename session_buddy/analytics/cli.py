"""CLI commands for session analytics.

Provides command-line interface for session analytics and visualization.

Commands:
    session-buddy analytics sessions    - Show session statistics
    session-buddy analytics duration    - Show duration stats
    session-buddy analytics components  - Show component usage
    session-buddy analytics errors      - Show error rates
    session-buddy analytics active      - Show active sessions
    session-buddy analytics report      - Generate comprehensive report
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from session_buddy.analytics.session_analytics import (
    SessionAnalytics,
    create_session_summary_report,
)

app = typer.Typer(
    name="analytics",
    help="Session analytics and visualization commands",
    add_completion=False,
)


def parse_days_option(days: int | None) -> int:
    """Validate and return days option."""
    if days is None:
        return 7  # Default to 7 days
    if days < 1:
        typer.echo("Error: days must be at least 1", err=True)
        raise typer.Exit(1)
    if days > 365:
        typer.echo("Error: days cannot exceed 365", err=True)
        raise typer.Exit(1)
    return days


@app.command("sessions")
def analytics_sessions(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
    component: str = typer.Option(None, "--component", "-c", help="Filter by component name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show session statistics.

    Displays total sessions, average duration, active sessions, and error rate
    for each component over the specified time period.

    Example:
        session-buddy analytics sessions --days 30
        session-buddy analytics sessions --component admin-shell
    """
    days = parse_days_option(days)

    async def run():
        analytics = SessionAnalytics()
        stats = await analytics.get_session_stats(days=days, component=component)

        if not stats:
            typer.echo("No session data found for the specified time period.")
            return

        if json_output:
            import json

            typer.echo(json.dumps([s.to_dict() for s in stats], indent=2))
        else:
            output = analytics.visualize_session_stats(stats)
            typer.echo("\n".join(output))

    asyncio.run(run())


@app.command("duration")
def analytics_duration(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
    component: str = typer.Option(None, "--component", "-c", help="Filter by component name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show average session duration by component.

    Displays average duration statistics for completed sessions.

    Example:
        session-buddy analytics duration --days 30
        session-buddy analytics duration --component ipython
    """
    days = parse_days_option(days)

    async def run():
        analytics = SessionAnalytics()
        durations = await analytics.get_average_session_duration(
            days=days, component=component
        )

        if not durations:
            typer.echo("No duration data found for the specified time period.")
            return

        if json_output:
            import json

            typer.echo(json.dumps(durations, indent=2))
        else:
            typer.echo("=" * 80)
            typer.echo("AVERAGE SESSION DURATION")
            typer.echo("=" * 80)
            typer.echo("")
            typer.echo(f"Time Period: Last {days} days")
            typer.echo("")

            for component_name, avg_duration in sorted(
                durations.items(), key=lambda x: x[1], reverse=True
            ):
                hours = int(avg_duration // 3600)
                minutes = int((avg_duration % 3600) // 60)
                seconds = int(avg_duration % 60)

                if hours > 0:
                    duration_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    duration_str = f"{minutes}m {seconds}s"
                else:
                    duration_str = f"{seconds}s"

                typer.echo(f"  {component_name:30} {duration_str:>20} ({avg_duration:.0f}s)")

            typer.echo("")

    asyncio.run(run())


@app.command("components")
def analytics_components(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum components to show"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show component usage statistics.

    Displays most active components by session count, total duration,
    and average quality score.

    Example:
        session-buddy analytics components --days 30 --limit 20
    """
    days = parse_days_option(days)

    if limit < 1 or limit > 100:
        typer.echo("Error: limit must be between 1 and 100", err=True)
        raise typer.Exit(1)

    async def run():
        analytics = SessionAnalytics()
        components = await analytics.get_most_active_components(days=days, limit=limit)

        if not components:
            typer.echo("No component usage data found for the specified time period.")
            return

        if json_output:
            import json

            typer.echo(json.dumps([c.to_dict() for c in components], indent=2))
        else:
            output = analytics.visualize_component_usage(components)
            typer.echo("\n".join(output))

    asyncio.run(run())


@app.command("errors")
def analytics_errors(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
    component: str = typer.Option(None, "--component", "-c", help="Filter by component name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show error rate statistics by component.

    Displays error rates, total sessions, failed sessions, and most common errors.

    Example:
        session-buddy analytics errors --days 30
        session-buddy analytics errors --component admin-shell
    """
    days = parse_days_option(days)

    async def run():
        analytics = SessionAnalytics()
        error_rates = await analytics.get_session_error_rate(
            days=days, component=component
        )

        if not error_rates:
            typer.echo("No error data found for the specified time period.")
            return

        if json_output:
            import json

            typer.echo(json.dumps(error_rates, indent=2))
        else:
            typer.echo("=" * 80)
            typer.echo("ERROR RATE STATISTICS")
            typer.echo("=" * 80)
            typer.echo("")
            typer.echo(f"Time Period: Last {days} days")
            typer.echo("")

            # Sort by error rate (highest first)
            for component_name, stats in sorted(
                error_rates.items(), key=lambda x: x[1]["error_rate"], reverse=True
            ):
                typer.echo(f"  {component_name}:")
                typer.echo(f"    Error Rate:    {stats['error_rate']:.2f}%")
                typer.echo(f"    Total Sessions: {stats['total_sessions']}")
                typer.echo(f"    Failed:        {stats['failed_sessions']}")

                if stats.get("most_common_error"):
                    typer.echo(
                        f"    Most Common:   {stats['most_common_error'][:60]}..."
                    )
                typer.echo("")

    asyncio.run(run())


@app.command("active")
def analytics_active(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show currently active sessions.

    Displays sessions that are currently running (no end_time).

    Example:
        session-buddy analytics active
    """
    async def run():
        analytics = SessionAnalytics()
        active = await analytics.get_active_sessions()

        if not active:
            typer.echo("No active sessions found.")
            return

        if json_output:
            import json

            typer.echo(json.dumps(active, indent=2))
        else:
            typer.echo("=" * 80)
            typer.echo(f"ACTIVE SESSIONS ({len(active)})")
            typer.echo("=" * 80)
            typer.echo("")

            for session in active:
                duration_seconds = session.get("duration_seconds", 0)
                hours = int(duration_seconds // 3600)
                minutes = int((duration_seconds % 3600) // 60)
                seconds = int(duration_seconds % 60)

                if hours > 0:
                    duration_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    duration_str = f"{minutes}m {seconds}s"
                else:
                    duration_str = f"{seconds}s"

                typer.echo(f"  Session: {session.get('session_id', 'unknown')}")
                typer.echo(f"    Component: {session.get('component_name', 'unknown')}")
                typer.echo(f"    Project:   {session.get('project', 'unknown')}")
                typer.echo(f"    Duration:  {duration_str}")
                typer.echo(f"    Started:   {session.get('start_time', 'unknown')}")
                typer.echo("")

    asyncio.run(run())


@app.command("report")
def analytics_report(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate comprehensive analytics report.

    Creates a detailed report combining session statistics, component usage,
    and error rates. Can optionally save to file.

    Example:
        session-buddy analytics report --days 30
        session-buddy analytics report --days 7 --output report.txt
    """
    days = parse_days_option(days)

    async def run():
        analytics = SessionAnalytics()

        typer.echo(f"Generating analytics report for last {days} days...", err=True)

        # Gather all data
        stats = await analytics.get_session_stats(days=days)
        components = await analytics.get_most_active_components(days=days, limit=10)
        error_rates = await analytics.get_session_error_rate(days=days)

        # Generate report
        report = create_session_summary_report(stats, components, error_rates)

        # Output report
        if output:
            output_path = Path(output)
            try:
                output_path.write_text(report)
                typer.echo(f"Report saved to: {output_path}", err=True)
            except Exception as e:
                typer.echo(f"Error saving report: {e}", err=True)
                raise typer.Exit(1)
        else:
            typer.echo("\n" + report)

    asyncio.run(run())


@app.command("sql")
def analytics_sql(
    query: str = typer.Argument(..., help="Query name (session_stats, active_sessions, etc.)"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
) -> None:
    """Export SQL query for use with external tools.

    Provides raw SQL queries that can be used with DuckDB directly or
    integrated with external visualization tools like Grafana.

    Available queries:
        - active_sessions: Currently active sessions
        - session_stats: Session statistics by component
        - average_duration: Average duration by component
        - most_active: Most active components
        - error_rate: Error rates by component

    Example:
        session-buddy analytics sql session_stats --days 30 > query.sql
    """
    days = parse_days_option(days)

    analytics = SessionAnalytics()
    sql = analytics.export_sql(query_name=query, days=days)

    typer.echo(sql)


def main() -> None:
    """Main entry point for analytics CLI."""
    app()


if __name__ == "__main__":
    main()
