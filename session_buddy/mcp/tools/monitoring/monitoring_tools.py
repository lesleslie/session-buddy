#!/usr/bin/env python3
"""Application monitoring and activity tracking MCP tools.

This module provides tools for monitoring application activity, tracking interruptions,
and managing session context following crackerjack architecture patterns.

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from session_buddy.utils.error_management import _get_logger
from session_buddy.utils.instance_managers import (
    get_app_monitor as resolve_app_monitor,
)
from session_buddy.utils.instance_managers import (
    get_interruption_manager as resolve_interruption_manager,
)
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastmcp import FastMCP


# ============================================================================
# Service Resolution Helpers
# ============================================================================


async def _require_app_monitor() -> Any:
    """Get application monitor instance or raise error."""
    monitor = await resolve_app_monitor()
    if monitor is None:
        msg = "Application monitoring not available. Features may be limited"
        raise RuntimeError(msg)
    return monitor


async def _require_interruption_manager() -> Any:
    """Get interruption manager instance or raise error."""
    manager = await resolve_interruption_manager()
    if manager is None:
        msg = "Interruption management not available. Features may be limited"
        raise RuntimeError(msg)
    return manager


async def _execute_monitor_operation(
    operation_name: str, operation: Callable[[Any], Awaitable[str]]
) -> str:
    """Execute a monitoring operation with error handling."""
    try:
        monitor = await _require_app_monitor()
        return await operation(monitor)
    except RuntimeError as e:
        return f"❌ {e!s}"
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


async def _execute_interruption_operation(
    operation_name: str, operation: Callable[[Any], Awaitable[str]]
) -> str:
    """Execute an interruption management operation with error handling."""
    try:
        manager = await _require_interruption_manager()
        return await operation(manager)
    except RuntimeError as e:
        return f"❌ {e!s}"
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


# ============================================================================
# App Monitoring Tools
# ============================================================================


async def _start_app_monitoring_operation(
    monitor: Any, project_paths: list[str] | None
) -> str:
    """Start monitoring IDE activity and browser documentation usage."""
    await monitor.start_monitoring(project_paths=project_paths)

    lines = ["🔍 Application Monitoring Started", ""]

    if project_paths:
        lines.append("📁 Monitoring project paths:")
        lines.extend([f"   • {path}" for path in project_paths])
    else:
        lines.append("📁 Monitoring all accessible paths")

    lines.extend(
        [
            "",
            "👁️ Now tracking:",
            "   • IDE file access and editing patterns",
            "   • Browser documentation and research activity",
            "   • Application focus and context switches",
            "   • File system changes and development flow",
            "",
            "💡 Use `get_activity_summary` to view tracked activity",
            "💡 Use `stop_app_monitoring` to end tracking",
        ]
    )

    return "\n".join(lines)


async def _start_app_monitoring_impl(project_paths: list[str] | None = None) -> str:
    """Start monitoring IDE activity and browser documentation usage."""

    async def operation_wrapper(monitor: Any) -> str:
        return await _start_app_monitoring_operation(monitor, project_paths)

    return await _execute_monitor_operation(
        "Start app monitoring",
        operation_wrapper,
    )


async def _stop_app_monitoring_operation(monitor: Any) -> str:
    """Stop all application monitoring."""
    summary = await monitor.stop_monitoring()

    lines = [
        "⏹️ Application Monitoring Stopped",
        "",
        "📊 Session summary:",
        f"   • Duration: {summary.get('duration_minutes', 0):.1f} minutes",
        f"   • Files tracked: {summary.get('files_tracked', 0)}",
        f"   • Applications monitored: {summary.get('apps_monitored', 0)}",
        f"   • Context switches: {summary.get('context_switches', 0)}",
        "",
        "✅ All monitoring stopped successfully",
    ]

    return "\n".join(lines)


async def _stop_app_monitoring_impl() -> str:
    """Stop all application monitoring."""
    return await _execute_monitor_operation(
        "Stop app monitoring", _stop_app_monitoring_operation
    )


# ============================================================================
# Activity Summary Helpers
# ============================================================================


def _format_file_activity(files: list[dict[str, Any]]) -> list[str]:
    """Format file activity section."""
    if not files:
        return []

    lines = [f"📄 File Activity ({len(files)} files):"]
    for file_info in files[:10]:  # Show top 10
        lines.append(f"   • {file_info['path']} ({file_info['access_count']} accesses)")
    if len(files) > 10:
        lines.append(f"   • ... and {len(files) - 10} more files")
    return lines


def _format_app_activity(apps: list[dict[str, Any]]) -> list[str]:
    """Format application activity section."""
    if not apps:
        return []

    lines = ["\n🖥️ Application Focus:"]
    for app_info in apps[:5]:  # Show top 5
        duration = app_info["focus_time_minutes"]
        lines.append(f"   • {app_info['name']}: {duration:.1f} minutes")
    return lines


def _format_productivity_metrics(metrics: dict[str, Any]) -> list[str]:
    """Format productivity metrics section."""
    if not metrics:
        return []

    return [
        "\n📈 Productivity Metrics:",
        f"   • Focus time: {metrics.get('focus_time_minutes', 0):.1f} minutes",
        f"   • Context switches: {metrics.get('context_switches', 0)}",
        f"   • Deep work periods: {metrics.get('deep_work_periods', 0)}",
    ]


async def _get_activity_summary_operation(monitor: Any, hours: int) -> str:
    """Get activity summary for the specified number of hours."""
    summary = await monitor.get_activity_summary(hours=hours)
    lines = [f"📊 Activity Summary - Last {hours} Hours", ""]

    if not summary.get("has_data"):
        lines.extend(
            [
                "🔍 No activity data available",
                "💡 Start monitoring with `start_app_monitoring`",
            ]
        )
        return "\n".join(lines)

    # Add all sections
    lines.extend(_format_file_activity(summary.get("file_activity", [])))
    lines.extend(_format_app_activity(summary.get("app_activity", [])))
    lines.extend(_format_productivity_metrics(summary.get("productivity_metrics", {})))

    return "\n".join(lines)


async def _get_activity_summary_impl(hours: int = 2) -> str:
    """Get activity summary for the specified number of hours."""

    async def operation_wrapper(monitor: Any) -> str:
        return await _get_activity_summary_operation(monitor, hours)

    return await _execute_monitor_operation("Get activity summary", operation_wrapper)


# ============================================================================
# Context Insights
# ============================================================================


def _format_context_insights_output(insights: dict[str, Any], hours: int) -> list[str]:
    """Format context insights output."""
    lines = [f"🧠 Context Insights - Last {hours} Hours", ""]

    if not insights.get("has_data"):
        lines.append("🔍 No context data available")
        return lines

    # Current focus area
    focus = insights.get("current_focus")
    if focus:
        lines.extend(
            (
                f"🎯 Current Focus: {focus['area']}",
                f"   Duration: {focus['duration_minutes']:.1f} minutes",
            )
        )

    # Project patterns
    patterns = insights.get("project_patterns", [])
    if patterns:
        lines.append("\n📋 Project Patterns:")
        lines.extend([f"   • {pattern['description']}" for pattern in patterns[:3]])

    # Technology context
    tech_context = insights.get("technology_context", [])
    if tech_context:
        lines.append("\n⚙️ Technology Context:")
        lines.extend(
            [
                f"   • {tech['name']}: {tech['confidence']:.0%} confidence"
                for tech in tech_context[:5]
            ]
        )

    # Recommendations
    recommendations = insights.get("recommendations", [])
    if recommendations:
        lines.append("\n💡 Recommendations:")
        lines.extend([f"   • {rec}" for rec in recommendations[:3]])

    return lines


async def _get_context_insights_operation(monitor: Any, hours: int) -> str:
    """Get contextual insights from recent activity."""
    insights = await monitor.get_context_insights(hours=hours)
    lines = _format_context_insights_output(insights, hours)
    return "\n".join(lines)


async def _get_context_insights_impl(hours: int = 1) -> str:
    """Get contextual insights from recent activity."""

    async def operation_wrapper(monitor: Any) -> str:
        return await _get_context_insights_operation(monitor, hours)

    return await _execute_monitor_operation("Get context insights", operation_wrapper)


async def _get_active_files_operation(monitor: Any, minutes: int) -> str:
    """Get list of actively edited files in recent minutes."""
    files = await monitor.get_active_files(minutes=minutes)

    lines = [f"📄 Active Files - Last {minutes} Minutes", ""]

    if not files:
        lines.extend(
            [
                "🔍 No active files in this period",
                "💡 Files will appear here when you edit them during monitoring",
            ]
        )
        return "\n".join(lines)

    lines.append(f"📝 Found {len(files)} active files:")
    for file_info in files[:20]:  # Show top 20
        timestamp = file_info.get("last_modified", "Unknown")
        lines.extend(
            (
                f"   • {file_info['path']}",
                f"     Last modified: {timestamp}",
                f"     Changes: {file_info.get('change_count', 0)}",
            )
        )

    if len(files) > 20:
        lines.append(f"\n... and {len(files) - 20} more files")

    return "\n".join(lines)


async def _get_active_files_impl(minutes: int = 60) -> str:
    """Get list of actively edited files in recent minutes."""

    async def operation_wrapper(monitor: Any) -> str:
        return await _get_active_files_operation(monitor, minutes)

    return await _execute_monitor_operation("Get active files", operation_wrapper)


# ============================================================================
# Interruption Management Tools
# ============================================================================


async def _start_interruption_monitoring_operation(
    manager: Any, session_id: str, user_id: str
) -> str:
    """Start monitoring for interruptions and context switches."""
    await manager.start_monitoring(session_id=session_id, user_id=user_id)

    return "\n".join(
        [
            "🔔 Interruption Monitoring Started",
            "",
            f"📝 Session ID: {session_id}",
            f"👤 User: {user_id}",
            "",
            "🎯 Now detecting:",
            "   • System sleep/wake events",
            "   • Network disconnections",
            "   • Application crashes",
            "   • Long periods of inactivity",
            "",
            "💡 Context will be automatically preserved on interruptions",
            "💡 Use `get_interruption_history` to view past events",
        ]
    )


async def _start_interruption_monitoring_impl(
    session_id: str, user_id: str = "default_user"
) -> str:
    """Start monitoring for interruptions and context switches."""

    async def operation_wrapper(manager: Any) -> str:
        return await _start_interruption_monitoring_operation(
            manager, session_id, user_id
        )

    return await _execute_interruption_operation(
        "Start interruption monitoring",
        operation_wrapper,
    )


async def _stop_interruption_monitoring_operation(manager: Any) -> str:
    """Stop interruption monitoring."""
    summary = await manager.stop_monitoring()

    return "\n".join(
        [
            "⏹️ Interruption Monitoring Stopped",
            "",
            "📊 Session summary:",
            f"   • Duration: {summary.get('duration_minutes', 0):.1f} minutes",
            f"   • Interruptions detected: {summary.get('interruption_count', 0)}",
            f"   • Contexts preserved: {summary.get('contexts_saved', 0)}",
            "",
            "✅ Monitoring stopped successfully",
        ]
    )


async def _stop_interruption_monitoring_impl() -> str:
    """Stop interruption monitoring."""
    return await _execute_interruption_operation(
        "Stop interruption monitoring", _stop_interruption_monitoring_operation
    )


async def _create_session_context_operation(
    manager: Any, session_id: str, context_data: dict[str, Any]
) -> str:
    """Create a new session context snapshot."""
    context_id = await manager.create_context_snapshot(
        session_id=session_id, context_data=context_data
    )

    return "\n".join(
        [
            "📸 Session Context Created",
            "",
            f"🆔 Context ID: {context_id}",
            f"📝 Session: {session_id}",
            f"📦 Data items: {len(context_data)}",
            "",
            "✅ Context snapshot saved successfully",
            "💡 Use `restore_session_context` to restore this context",
        ]
    )


async def _create_session_context_impl(
    session_id: str, context_data: dict[str, Any]
) -> str:
    """Create a new session context snapshot."""

    async def operation_wrapper(manager: Any) -> str:
        return await _create_session_context_operation(
            manager, session_id, context_data
        )

    return await _execute_interruption_operation(
        "Create session context",
        operation_wrapper,
    )


async def _preserve_current_context_operation(
    manager: Any, session_id: str, reason: str
) -> str:
    """Preserve current development context before an interruption."""
    context_snapshot = await manager.preserve_context(
        session_id=session_id, interruption_reason=reason
    )

    return "\n".join(
        [
            "💾 Context Preserved",
            "",
            f"🆔 Snapshot ID: {context_snapshot['id']}",
            f"📝 Reason: {reason}",
            f"📦 Items preserved: {context_snapshot['item_count']}",
            "",
            "✅ Context saved successfully",
            "💡 Use `restore_session_context` to restore this context",
        ]
    )


async def _preserve_current_context_impl(
    session_id: str, reason: str = "manual_checkpoint"
) -> str:
    """Preserve current development context before an interruption."""

    async def operation_wrapper(manager: Any) -> str:
        return await _preserve_current_context_operation(manager, session_id, reason)

    return await _execute_interruption_operation(
        "Preserve current context",
        operation_wrapper,
    )


async def _restore_session_context_operation(manager: Any, session_id: str) -> str:
    """Restore a previously saved session context."""
    restored = await manager.restore_context(session_id=session_id)

    if not restored.get("success"):
        return f"❌ Failed to restore context: {restored.get('error', 'Unknown error')}"

    return "\n".join(
        [
            "♻️ Context Restored",
            "",
            f"📝 Session ID: {session_id}",
            f"📦 Items restored: {restored['item_count']}",
            f"📅 Original timestamp: {restored['original_timestamp']}",
            "",
            "✅ Context restored successfully",
            "💡 Resume work from where you left off",
        ]
    )


async def _restore_session_context_impl(session_id: str) -> str:
    """Restore a previously saved session context."""

    async def operation_wrapper(manager: Any) -> str:
        return await _restore_session_context_operation(manager, session_id)

    return await _execute_interruption_operation(
        "Restore session context",
        operation_wrapper,
    )


async def _get_interruption_history_operation(
    manager: Any, user_id: str, hours: int
) -> str:
    """Get history of interruptions for debugging and analysis."""
    history = await manager.get_interruption_history(user_id=user_id, hours=hours)

    lines = [f"📜 Interruption History - Last {hours} Hours", f"👤 User: {user_id}", ""]

    if not history:
        lines.extend(
            [
                "🔍 No interruptions recorded",
                "💡 Interruptions will appear here when detected during monitoring",
            ]
        )
        return "\n".join(lines)

    lines.append(f"⚠️ Found {len(history)} interruptions:")
    for event in history[:10]:  # Show last 10
        lines.extend(
            [
                f"\n📍 {event['timestamp']}",
                f"   Type: {event['type']}",
                f"   Reason: {event.get('reason', 'N/A')}",
                f"   Recovery: {event.get('recovery_action', 'None')}",
            ]
        )

    if len(history) > 10:
        lines.append(f"\n... and {len(history) - 10} more events")

    return "\n".join(lines)


async def _get_interruption_history_impl(user_id: str, hours: int = 24) -> str:
    """Get history of interruptions for debugging and analysis."""

    async def operation_wrapper(manager: Any) -> str:
        return await _get_interruption_history_operation(manager, user_id, hours)

    return await _execute_interruption_operation(
        "Get interruption history",
        operation_wrapper,
    )


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_monitoring_tools(mcp: FastMCP) -> None:
    """Register all monitoring and interruption management tools."""

    @mcp.tool()  # type: ignore[misc]
    async def start_app_monitoring(project_paths: list[str] | None = None) -> str:
        """Start monitoring IDE activity and browser documentation usage."""
        return await _start_app_monitoring_impl(project_paths)

    @mcp.tool()  # type: ignore[misc]
    async def stop_app_monitoring() -> str:
        """Stop all application monitoring."""
        return await _stop_app_monitoring_impl()

    @mcp.tool()  # type: ignore[misc]
    async def get_activity_summary(hours: int = 2) -> str:
        """Get activity summary for the specified number of hours."""
        return await _get_activity_summary_impl(hours)

    @mcp.tool()  # type: ignore[misc]
    async def get_context_insights(hours: int = 1) -> str:
        """Get contextual insights from recent activity."""
        return await _get_context_insights_impl(hours)

    @mcp.tool()  # type: ignore[misc]
    async def get_active_files(minutes: int = 60) -> str:
        """Get list of actively edited files in recent minutes."""
        return await _get_active_files_impl(minutes)

    @mcp.tool()  # type: ignore[misc]
    async def start_interruption_monitoring(
        session_id: str, user_id: str = "default_user"
    ) -> str:
        """Start monitoring for interruptions and context switches."""
        return await _start_interruption_monitoring_impl(session_id, user_id)

    @mcp.tool()  # type: ignore[misc]
    async def stop_interruption_monitoring() -> str:
        """Stop interruption monitoring."""
        return await _stop_interruption_monitoring_impl()

    @mcp.tool()  # type: ignore[misc]
    async def create_session_context(
        session_id: str, context_data: dict[str, Any]
    ) -> str:
        """Create a new session context snapshot."""
        return await _create_session_context_impl(session_id, context_data)

    @mcp.tool()  # type: ignore[misc]
    async def preserve_current_context(
        session_id: str, reason: str = "manual_checkpoint"
    ) -> str:
        """Preserve current development context before an interruption."""
        return await _preserve_current_context_impl(session_id, reason)

    @mcp.tool()  # type: ignore[misc]
    async def restore_session_context(session_id: str) -> str:
        """Restore a previously saved session context."""
        return await _restore_session_context_impl(session_id)

    @mcp.tool()  # type: ignore[misc]
    async def get_interruption_history(user_id: str, hours: int = 24) -> str:
        """Get history of interruptions for debugging and analysis."""
        return await _get_interruption_history_impl(user_id, hours)
