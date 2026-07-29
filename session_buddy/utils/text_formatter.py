#!/usr/bin/env python3
# ruff: noqa: EXE001
"""Formatting and output utilities for session management.

This module provides text formatting and display functionality following
crackerjack architecture patterns with single responsibility principle.
"""

from __future__ import annotations

from typing import Any


def _format_statistics_header(user_id: str) -> list[str]:
    """Format the header section for interruption statistics."""
    return [
        f"📊 **Interruption Statistics for {user_id}**",
        "",
    ]


def _format_session_statistics(sessions: dict[str, Any]) -> list[str]:
    """Format session-related statistics."""
    if not sessions:
        return ["📝 No session data available"]

    return [
        "**Session Activity:**",
        f"• Total sessions: {sessions.get('total', 0)}",
        f"• Average duration: {sessions.get('avg_duration_minutes', 0):.1f} minutes",
        f"• Longest session: {sessions.get('max_duration_minutes', 0):.1f} minutes",
        "",
    ]


def _format_interruption_type_details(by_type: list[Any]) -> list[str]:
    """Format interruption type breakdown."""
    if not by_type:
        return []

    lines = ["**Interruption Types:**"]
    for item in by_type[:5]:  # Show top 5
        lines.append(f"• {item['type']}: {item['count']} occurrences")

    lines.append("")
    return lines


def _format_interruption_statistics(interruptions: dict[str, Any]) -> list[str]:
    """Format interruption-related statistics."""
    if not interruptions:
        return ["🚫 No interruption data available"]

    lines = [
        "**Interruption Patterns:**",
        f"• Total interruptions: {interruptions.get('total', 0)}",
        f"• Average per session: {interruptions.get('avg_per_session', 0):.1f}",
        f"• Most active hour: {interruptions.get('peak_hour', 'Unknown')}",
        "",
    ]

    # Add type breakdown if available
    if "by_type" in interruptions:
        lines.extend(_format_interruption_type_details(interruptions["by_type"]))

    return lines


def _format_snapshot_statistics(snapshots: dict[str, Any]) -> list[str]:
    """Format snapshot-related statistics."""
    if not snapshots:
        return ["💾 No snapshot data available"]

    return [
        "**Context Snapshots:**",
        f"• Total snapshots: {snapshots.get('total', 0)}",
        f"• Successful restores: {snapshots.get('successful_restores', 0)}",
        f"• Average snapshot size: {snapshots.get('avg_size_kb', 0):.1f} KB",
        "",
    ]


def _calculate_efficiency_rates(
    sessions: dict[str, Any],
    interruptions: dict[str, Any],
    snapshots: dict[str, Any],
) -> dict[str, float]:
    """Calculate efficiency metrics from statistics."""
    efficiency = {
        "interruption_rate": 0.0,
        "recovery_rate": 0.0,
        "productivity_score": 0.0,
    }

    if sessions.get("total", 0) > 0:
        efficiency["interruption_rate"] = (
            interruptions.get("total", 0) / sessions["total"]
        )

    if snapshots.get("total", 0) > 0:
        efficiency["recovery_rate"] = (
            snapshots.get("successful_restores", 0) / snapshots["total"]
        )

    # Simple productivity score (inverse of interruption rate, scaled)
    efficiency["productivity_score"] = max(
        0,
        100 - (efficiency["interruption_rate"] * 20),
    )

    return efficiency


def _format_efficiency_metrics(
    sessions: dict[str, Any],
    interruptions: dict[str, Any],
    snapshots: dict[str, Any],
) -> list[str]:
    """Format efficiency and productivity metrics."""
    efficiency = _calculate_efficiency_rates(sessions, interruptions, snapshots)

    return [
        "**Efficiency Metrics:**",
        f"• Interruption rate: {efficiency['interruption_rate']:.2f} per session",
        f"• Context recovery rate: {efficiency['recovery_rate']:.1%}",
        f"• Productivity score: {efficiency['productivity_score']:.1f}/100",
        "",
    ]


def _has_statistics_data(
    sessions: dict[str, Any],
    interruptions: dict[str, Any],
    snapshots: dict[str, Any],
) -> bool:
    """Check if any meaningful statistics data exists."""
    return bool(
        sessions.get("total", 0) > 0
        or interruptions.get("total", 0) > 0
        or snapshots.get("total", 0) > 0,
    )


def _format_no_data_message(user_id: str) -> list[str]:
    """Format message when no statistics data is available."""
    return [
        f"📊 **No Statistics Available for {user_id}**",
        "",
        "No interruption monitoring data found. To start collecting statistics:",
        "• Use the start_interruption_monitoring tool",
        "• Work on development tasks with file monitoring enabled",
        "• Create session contexts to track productivity patterns",
        "",
        "Statistics will be available after some monitored activity.",
    ]


def _build_search_header(
    query: str,
    total_found: int,
    chunk_info: dict[str, Any] | None = None,
) -> list[str]:
    """Build formatted header for search results."""
    header = [f"🔍 **Search Results for: '{query}'**", ""]

    if chunk_info:
        current = chunk_info.get("current_chunk", 1)
        total = chunk_info.get("total_chunks", 1)
        header.extend(
            [
                f"📊 Found {total_found} results (Page {current}/{total})",
                "",
            ],
        )
    else:
        header.extend(
            [
                f"📊 Found {total_found} results",
                "",
            ],
        )

    return header


def _format_search_results(results: list[Any]) -> list[str]:
    """Format search results for display."""
    if not results:
        return ["No results found"]

    formatted = []

    for i, result in enumerate(results, 1):
        content = result.get("content", "").strip()
        project = result.get("project", "Unknown")
        timestamp = result.get("timestamp", "")

        # Truncate content for display
        if len(content) > 300:
            content = content[:297] + "..."

        formatted.extend(
            [
                f"**{i}. [{project}]** {timestamp}",
                f"   {content}",
                "",
            ],
        )

    return formatted


def _format_monitoring_status(quality_data: dict[str, Any]) -> list[str]:
    """Format current monitoring status information."""
    lines = [
        "📊 **Current Monitoring Status**",
        "",
    ]

    if quality_data.get("monitoring_active"):
        lines.extend(
            [
                "✅ Quality monitoring is active",
                f"• Last check: {quality_data.get('last_check', 'Unknown')}",
                f"• Checks performed: {quality_data.get('total_checks', 0)}",
            ],
        )
    else:
        lines.extend(
            [
                "⏸️ Quality monitoring is inactive",
                "• Use quality_monitor tool to start monitoring",
            ],
        )

    lines.append("")
    return lines


def _format_quality_trend(quality_data: dict[str, Any]) -> list[str]:
    """Format quality trend information."""
    trend = quality_data.get("trend", {})
    if not trend:
        return ["📈 No trend data available"]

    return [
        "📈 **Quality Trend Analysis**",
        "",
        f"• Current quality score: {trend.get('current_score', 0)}/100",
        f"• Trend direction: {trend.get('direction', 'Unknown')}",
        f"• Change from last check: {trend.get('change', 0):+.1f} points",
        "",
    ]


def _format_quality_alerts(quality_data: dict[str, Any]) -> list[str]:
    """Format quality alerts and warnings."""
    alerts = quality_data.get("alerts", [])
    if not alerts:
        return ["✅ No quality alerts"]

    lines = [
        "🚨 **Quality Alerts**",
        "",
    ]

    for alert in alerts:
        severity = alert.get("severity", "info")
        message = alert.get("message", "")
        icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(severity, "ℹ️")
        lines.append(f"{icon} {message}")

    lines.append("")
    return lines


def _format_proactive_recommendations(quality_data: dict[str, Any]) -> list[str]:
    """Format proactive quality improvement recommendations."""
    recommendations = quality_data.get("recommendations", [])
    if not recommendations:
        return ["💡 No recommendations at this time"]

    lines = [
        "💡 **Proactive Recommendations**",
        "",
    ]

    for i, rec in enumerate(recommendations, 1):
        lines.append(f"{i}. {rec}")

    lines.append("")
    return lines


def _format_monitor_usage_guidance() -> list[str]:
    """Format usage guidance for quality monitoring."""
    return [
        "📖 **Usage Guidance**",
        "",
        "• Run quality_monitor periodically to track project health",
        "• Monitor alerts for early warning of quality issues",
        "• Follow recommendations to maintain code quality",
        "• Use with Crackerjack integration for best results",
        "",
        "Quality monitoring helps maintain consistent development standards.",
    ]
