"""Advanced Feature Hub for MCP Tools.

This module provides advanced MCP tools for multi-project coordination,
git worktree management, natural language scheduling, and enhanced search.

Extracted from server.py Phase 2.4 - Contains 17 MCP tool implementations:
- Natural language reminder tools (5 MCP tools)
- Interruption management tools (1 MCP tool)
- Multi-project coordination (4 MCP tools)
- Advanced search capabilities (3 MCP tools)
- Git worktree management (3 MCP tools)
- Session welcome tool (1 MCP tool)
"""

from __future__ import annotations

import typing as t
from pathlib import Path

if t.TYPE_CHECKING:
    from session_buddy.utils.logging import SessionLogger


class AdvancedFeaturesHub:
    """Coordinator for advanced MCP feature tools.

    Provides lazy initialization and coordination for optional
    advanced features like multi-project support, worktrees, etc.
    """

    def __init__(self, logger: SessionLogger) -> None:
        """Initialize advanced features hub.

        Args:
            logger: Session logger for feature events

        """
        self.logger = logger
        self._multi_project_initialized = False
        self._advanced_search_initialized = False
        self._app_monitor_initialized = False

    async def initialize_multi_project(self) -> bool:
        """Initialize multi-project coordination features.

        Returns:
            True if initialized successfully

        """
        msg = "initialize_multi_project not yet implemented"
        raise NotImplementedError(msg)

    async def initialize_advanced_search(self) -> bool:
        """Initialize advanced search capabilities.

        Returns:
            True if initialized successfully

        """
        msg = "initialize_advanced_search not yet implemented"
        raise NotImplementedError(msg)

    async def initialize_app_monitor(self) -> bool:
        """Initialize application monitoring.

        Returns:
            True if initialized successfully

        """
        msg = "initialize_app_monitor not yet implemented"
        raise NotImplementedError(msg)


# ================================
# Natural Language Scheduling Tools
# ================================


async def create_natural_reminder(
    title: str,
    time_expression: str,
    description: str = "",
    user_id: str = "default",
    project_id: str | None = None,
    notification_method: str = "session",
) -> str:
    """Create reminder from natural language time expression."""
    try:
        from .natural_scheduler import (
            create_natural_reminder as _create_natural_reminder,
        )

        reminder_id = await _create_natural_reminder(
            title,
            time_expression,
            description,
            user_id,
            project_id,
            notification_method,
        )

        if reminder_id:
            output: list[str] = []
            output.extend(
                (
                    "⏰ Natural reminder created successfully!",
                    f"🆔 Reminder ID: {reminder_id}",
                    f"📝 Title: {title}",
                    f"📄 Description: {description}",
                    f"🕐 When: {time_expression}",
                    f"👤 User: {user_id}",
                )
            )
            if project_id:
                output.append(f"📁 Project: {project_id}")
            output.extend(
                (
                    f"📢 Notification: {notification_method}",
                    "🎯 Reminder will trigger automatically at the scheduled time",
                )
            )
            return "\n".join(output)
        return f"❌ Failed to parse time expression: '{time_expression}'\n💡 Try formats like 'in 30 minutes', 'tomorrow at 9am', 'every day at 5pm'"

    except ImportError:
        return "❌ Natural scheduling tools not available. Install: pip install python-dateutil schedule python-crontab"
    except Exception as e:
        return f"❌ Error creating reminder: {e}"


async def list_user_reminders(
    user_id: str = "default",
    project_id: str | None = None,
) -> str:
    """List pending reminders for user/project."""
    try:
        from .natural_scheduler import list_user_reminders as _list_user_reminders

        # Import formatting functions
        from .utils.server_helpers import (
            _format_no_reminders_message,
            _format_reminders_list,
        )

        reminders = await _list_user_reminders(user_id, project_id)

        if not reminders:
            output = _format_no_reminders_message(user_id, project_id)
            return "\n".join(output)

        output = _format_reminders_list(reminders, user_id, project_id)
        return "\n".join(output)

    except ImportError:
        return "❌ Natural scheduling tools not available"
    except Exception as e:
        return f"❌ Error listing reminders: {e}"


async def cancel_user_reminder(reminder_id: str) -> str:
    """Cancel a specific reminder."""
    try:
        from .natural_scheduler import cancel_user_reminder as _cancel_user_reminder

        success = await _cancel_user_reminder(reminder_id)

        if success:
            output: list[str] = []
            output.extend(
                (
                    "❌ Reminder cancelled successfully!",
                    f"🆔 Reminder ID: {reminder_id}",
                    "🚫 The reminder will no longer trigger",
                    "💡 You can create a new reminder if needed",
                )
            )
            return "\n".join(output)
        return f"❌ Failed to cancel reminder {reminder_id}. Check that the ID is correct and the reminder exists"

    except ImportError:
        return "❌ Natural scheduling tools not available"
    except Exception as e:
        return f"❌ Error cancelling reminder: {e}"


def _calculate_overdue_time(scheduled_for: str) -> str:
    """Calculate and format overdue time."""
    try:
        from datetime import datetime

        scheduled = datetime.fromisoformat(scheduled_for)
        now = datetime.now()
        overdue = now - scheduled

        if overdue.total_seconds() > 0:
            hours = int(overdue.total_seconds() // 3600)
            minutes = int((overdue.total_seconds() % 3600) // 60)
            if hours > 0:
                return f"⏱️ Overdue: {hours}h {minutes}m"
            return f"⏱️ Overdue: {minutes}m"
        return "⏱️ Not yet due"
    except Exception as e:
        return f"❌ Error checking due reminders: {e}"


async def start_reminder_service() -> str:
    """Start the background reminder service."""
    try:
        from .natural_scheduler import (
            register_session_notifications,
        )
        from .natural_scheduler import (
            start_reminder_service as _start_reminder_service,
        )

        # Register default session notifications
        register_session_notifications()

        # Start the service
        _start_reminder_service()

        output: list[str] = []
        output.extend(
            (
                "🚀 Natural reminder service started!",
                "⏰ Background scheduler is now active",
                "🔍 Checking for due reminders every minute",
                "📢 Session notifications are registered",
                "💡 Reminders will automatically trigger at their scheduled times",
                "🛑 Use 'stop_reminder_service' to stop the background service",
            )
        )

        return "\n".join(output)

    except ImportError:
        return "❌ Natural scheduling tools not available"
    except Exception as e:
        return f"❌ Error starting reminder service: {e}"


async def stop_reminder_service() -> str:
    """Stop the background reminder service."""
    try:
        from .natural_scheduler import stop_reminder_service as _stop_reminder_service

        _stop_reminder_service()

        output: list[str] = []
        output.extend(
            (
                "🛑 Natural reminder service stopped",
                "❌ Background scheduler is no longer active",
                "⚠️ Existing reminders will not trigger automatically",
                "🚀 Use 'start_reminder_service' to restart the service",
                "💡 You can still check due reminders manually with 'check_due_reminders'",
            )
        )

        return "\n".join(output)

    except ImportError:
        return "❌ Natural scheduling tools not available"
    except Exception as e:
        return f"❌ Error stopping reminder service: {e}"


# ================================
# Interruption Management Tools
# ================================


async def get_interruption_statistics(user_id: str) -> str:
    """Get comprehensive interruption and context preservation statistics."""
    try:
        from .interruption_manager import (
            get_interruption_statistics as _get_interruption_statistics,
        )

        # Import formatting functions
        from .utils import (
            _format_efficiency_metrics,
            _format_no_data_message,
            _format_statistics_header,
        )
        from .utils.server_helpers import (
            _format_interruption_statistics,
            _format_snapshot_statistics,
        )

        stats = await _get_interruption_statistics(user_id)
        output = _format_statistics_header(user_id)

        # Get statistics sections
        sessions = stats.get("sessions", {})
        interruptions = stats.get("interruptions", {})
        snapshots = stats.get("snapshots", {})
        by_type = interruptions.get("by_type", [])

        # Format all sections
        output.extend(_format_session_statistics(sessions))
        output.extend(_format_interruption_statistics(interruptions))
        output.extend(_format_snapshot_statistics(snapshots))
        output.extend(_format_efficiency_metrics(sessions, interruptions, by_type))

        # Check if we have any data
        if not _has_statistics_data(sessions, interruptions, snapshots):
            output = _format_no_data_message(user_id)

        return "\n".join(output)

    except ImportError:
        return "❌ Interruption management tools not available"
    except Exception as e:
        return f"❌ Error getting statistics: {e}"


def _format_session_statistics(sessions: dict[str, t.Any]) -> list[str]:
    """Format session statistics section."""
    output = []
    if sessions:
        output.append("\n📊 Session Statistics:")
        if "total_sessions" in sessions:
            output.append(f"   • Total sessions: {sessions['total_sessions']}")
        if "active_sessions" in sessions:
            output.append(f"   • Active sessions: {sessions['active_sessions']}")
        if "avg_duration" in sessions:
            output.append(f"   • Average duration: {sessions['avg_duration']}")
    return output


def _has_statistics_data(
    sessions: t.Any,
    interruptions: t.Any,
    snapshots: t.Any,
) -> bool:
    """Check if we have any statistics data to display."""
    return bool(sessions or interruptions or snapshots)


# ================================
# Multi-Project Coordination Tools
# ================================


async def create_project_group(
    name: str,
    projects: list[str],
    description: str = "",
) -> str:
    """Create a new project group for multi-project coordination."""
    # Lazy initialization

    multi_project_coordinator = await _get_multi_project_coordinator()
    if not multi_project_coordinator:
        return "❌ Multi-project coordination not available"

    try:
        group = await multi_project_coordinator.create_project_group(
            name=name,
            projects=projects,
            description=description,
        )

        return f"""✅ **Project Group Created**

**Group:** {group.name}
**Projects:** {", ".join(group.projects)}
**Description:** {group.description or "None"}
**ID:** {group.id}

The project group is now available for cross-project coordination and knowledge sharing."""

    except Exception as e:
        return f"❌ Failed to create project group: {e}"


async def add_project_dependency(
    source_project: str,
    target_project: str,
    dependency_type: t.Literal["uses", "extends", "references", "shares_code"],
    description: str = "",
) -> str:
    """Add a dependency relationship between projects."""
    multi_project_coordinator = await _get_multi_project_coordinator()
    if not multi_project_coordinator:
        return "❌ Multi-project coordination not available"

    try:
        dependency = await multi_project_coordinator.add_project_dependency(
            source_project=source_project,
            target_project=target_project,
            dependency_type=dependency_type,
            description=description,
        )

        return f"""✅ **Project Dependency Added**

**Source:** {dependency.source_project}
**Target:** {dependency.target_project}
**Type:** {dependency.dependency_type}
**Description:** {dependency.description or "None"}

This relationship will be used for cross-project search and coordination."""

    except Exception as e:
        return f"❌ Failed to add project dependency: {e}"


async def search_across_projects(
    query: str,
    current_project: str,
    limit: int = 10,
) -> str:
    """Search conversations across related projects."""
    multi_project_coordinator = await _get_multi_project_coordinator()
    if not multi_project_coordinator:
        return "❌ Multi-project coordination not available"

    try:
        results = await multi_project_coordinator.find_related_conversations(
            current_project=current_project,
            query=query,
            limit=limit,
        )

        if not results:
            return f"🔍 No results found for '{query}' across related projects"

        output = [f"🔍 **Cross-Project Search Results** ({len(results)} found)\n"]

        for i, result in enumerate(results, 1):
            project_indicator = (
                "📍 Current"
                if result["is_current_project"]
                else f"🔗 {result['source_project']}"
            )

            output.append(f"""**{i}.** {project_indicator}
**Score:** {result["score"]:.3f}
**Content:** {result["content"][:200]}{"..." if len(result["content"]) > 200 else ""}
**Timestamp:** {result.get("timestamp", "Unknown")}
---""")

        return "\n".join(output)

    except Exception as e:
        return f"❌ Search failed: {e}"


async def get_project_insights(projects: list[str], time_range_days: int = 30) -> str:
    """Get cross-project insights and collaboration opportunities."""
    multi_project_coordinator = await _get_multi_project_coordinator()
    if not multi_project_coordinator:
        return "❌ Multi-project coordination not available"

    try:
        from .utils.server_helpers import _format_project_insights

        insights = await multi_project_coordinator.get_cross_project_insights(
            projects=projects,
            time_range_days=time_range_days,
        )
        return _format_project_insights(insights, time_range_days)

    except Exception as e:
        return f"❌ Failed to get insights: {e}"


async def _get_multi_project_coordinator() -> t.Any:
    """Get or initialize multi-project coordinator."""
    try:
        from session_buddy.multi_project_coordinator import MultiProjectCoordinator
        from session_buddy.reflection_tools import get_reflection_database

        # Type ignore: get_reflection_database returns ReflectionDatabaseAdapter
        # which is compatible with ReflectionDatabaseProtocol
        db = await get_reflection_database()  # type: ignore[arg-type]
        return MultiProjectCoordinator(db)
    except Exception:
        return None


# ================================
# Advanced Search Tools
# ================================


async def advanced_search(
    query: str,
    content_type: str | None = None,
    project: str | None = None,
    timeframe: str | None = None,
    sort_by: str = "relevance",
    limit: int = 10,
) -> str:
    """Perform advanced search with faceted filtering."""
    advanced_search_engine = await _get_advanced_search_engine()
    if not advanced_search_engine:
        return "❌ Advanced search not available"

    try:
        from .utils.server_helpers import _format_advanced_search_results

        filters = _build_advanced_search_filters(content_type, project, timeframe)
        search_results = await advanced_search_engine.search(
            query=query,
            filters=filters,
            sort_by=sort_by,
            limit=limit,
            include_highlights=True,
        )

        results = search_results["results"]
        if not results:
            return f"🔍 No results found for '{query}'"

        return _format_advanced_search_results(results)

    except Exception as e:
        return f"❌ Advanced search failed: {e}"


def _build_advanced_search_filters(
    content_type: str | None,
    project: str | None,
    timeframe: str | None,
) -> list[t.Any]:
    """Build search filters from parameters."""
    filters = []

    if content_type:
        from session_buddy.advanced_search import SearchFilter

        filters.append(
            SearchFilter(field="content_type", operator="eq", value=content_type),
        )

    if project:
        from session_buddy.advanced_search import SearchFilter

        filters.append(SearchFilter(field="project", operator="eq", value=project))

    if timeframe:
        from session_buddy.advanced_search import SearchFilter

        # Get engine for timeframe parsing
        advanced_search_engine = _get_advanced_search_engine_sync()
        if advanced_search_engine:
            start_time, end_time = advanced_search_engine._parse_timeframe(timeframe)
            filters.append(
                SearchFilter(
                    field="timestamp",
                    operator="range",
                    value=(start_time, end_time),
                ),
            )

    return filters


async def search_suggestions(query: str, field: str = "content", limit: int = 5) -> str:
    """Get search completion suggestions."""
    advanced_search_engine = await _get_advanced_search_engine()
    if not advanced_search_engine:
        return "❌ Advanced search not available"

    try:
        suggestions = await advanced_search_engine.suggest_completions(
            query=query,
            field=field,
            limit=limit,
        )

        if not suggestions:
            return f"💡 No suggestions found for '{query}'"

        output = [f"💡 **Search Suggestions** for '{query}':\n"]

        for i, suggestion in enumerate(suggestions, 1):
            output.append(
                f"{i}. {suggestion['text']} (frequency: {suggestion['frequency']})",
            )

        return "\n".join(output)

    except Exception as e:
        return f"❌ Failed to get suggestions: {e}"


async def get_search_metrics(metric_type: str, timeframe: str = "30d") -> str:
    """Get search and activity metrics."""
    advanced_search_engine = await _get_advanced_search_engine()
    if not advanced_search_engine:
        return "❌ Advanced search not available"

    try:
        metrics = await advanced_search_engine.aggregate_metrics(
            metric_type=metric_type,
            timeframe=timeframe,
        )

        if "error" in metrics:
            return f"❌ {metrics['error']}"

        output = [f"📊 **{metric_type.title()} Metrics** ({timeframe})\n"]

        for item in metrics["data"][:10]:  # Top 10
            output.append(f"• **{item['key']}:** {item['value']}")

        if not metrics["data"]:
            output.append("No data available for the specified timeframe")

        return "\n".join(output)

    except Exception as e:
        return f"❌ Failed to get metrics: {e}"


async def _get_advanced_search_engine() -> t.Any:
    """Get or initialize advanced search engine."""
    try:
        from session_buddy.advanced_search import AdvancedSearchEngine
        from session_buddy.reflection_tools import get_reflection_database

        # Type ignore: get_reflection_database returns ReflectionDatabaseAdapter
        # which is compatible with AdvancedSearchEngine's expected type
        db = await get_reflection_database()  # type: ignore[arg-type]
        return AdvancedSearchEngine(db)  # type: ignore[arg-type]
    except Exception:
        return None


def _get_advanced_search_engine_sync() -> t.Any:
    """Synchronous helper to get advanced search engine."""
    try:
        import asyncio

        return asyncio.run(_get_advanced_search_engine())
    except Exception:
        return None


# ================================
# Git Worktree Management Tools
# ================================


def _get_worktree_indicators(is_main: bool, is_detached: bool) -> tuple[str, str]:
    """Get the main and detached indicators for a worktree."""
    main_indicator = " (main)" if is_main else ""
    detached_indicator = " (detached)" if is_detached else ""
    return main_indicator, detached_indicator


def _resolve_worktree_working_dir(working_directory: str | None) -> Path:
    """Resolve a safe working directory for git worktree operations."""
    if working_directory:
        return Path(working_directory)
    try:
        return Path.cwd()
    except FileNotFoundError:
        return Path.home()


async def git_worktree_add(
    branch: str,
    path: str,
    working_directory: str | None = None,
    create_branch: bool = False,
) -> str:
    """Create a new git worktree."""
    from .utils.logging import get_session_logger
    from .worktree_manager import WorktreeManager

    # Get session logger from DI container (using helper to avoid type conflicts)
    session_logger = get_session_logger()

    working_dir = _resolve_worktree_working_dir(working_directory)
    new_path = Path(path)

    if not new_path.is_absolute():
        new_path = working_dir.parent / path

    manager = WorktreeManager(session_logger=session_logger)

    try:
        result = await manager.create_worktree(
            repository_path=working_dir,
            new_path=new_path,
            branch=branch,
            create_branch=create_branch,
        )

        if not result["success"]:
            return f"❌ {result['error']}"

        output = [
            "🎉 **Worktree Created Successfully!**\n",
            f"🌿 Branch: {result['branch']}",
            f"📁 Path: {result['worktree_path']}",
            f"🎯 Created new branch: {'Yes' if create_branch else 'No'}",
        ]

        if result.get("output"):
            output.append(f"\n📝 Git output: {result['output']}")

        output.extend(
            (
                f"\n💡 To start working: cd {result['worktree_path']}",
                "💡 Use `git_worktree_list` to see all worktrees",
            )
        )

        return "\n".join(output)

    except Exception as e:
        session_logger.exception(f"git_worktree_add failed: {e}")
        return f"❌ Failed to create worktree: {e}"


async def git_worktree_remove(
    path: str,
    working_directory: str | None = None,
    force: bool = False,
) -> str:
    """Remove an existing git worktree."""
    from .utils.logging import get_session_logger
    from .worktree_manager import WorktreeManager

    # Get session logger from DI container (using helper to avoid type conflicts)
    session_logger = get_session_logger()

    working_dir = _resolve_worktree_working_dir(working_directory)
    remove_path = Path(path)

    if not remove_path.is_absolute():
        remove_path = working_dir.parent / path

    manager = WorktreeManager(session_logger=session_logger)

    try:
        result = await manager.remove_worktree(
            repository_path=working_dir,
            worktree_path=remove_path,
            force=force,
        )

        if not result["success"]:
            return f"❌ {result['error']}"

        output = [
            "🗑️ **Worktree Removed Successfully!**\n",
            f"📁 Removed path: {result['removed_path']}",
        ]

        if result.get("output"):
            output.append(f"📝 Git output: {result['output']}")

        output.extend(
            (
                f"\n💡 Used force removal: {'Yes' if force else 'No'}",
                "💡 Use `git_worktree_list` to see remaining worktrees",
            )
        )

        return "\n".join(output)

    except Exception as e:
        session_logger.exception(f"git_worktree_remove failed: {e}")
        return f"❌ Failed to remove worktree: {e}"


def _format_worktree_switch_result(result: dict[str, t.Any]) -> str:
    """Format worktree switch result into human-readable output."""
    output = [
        "**Worktree Context Switch Complete**\n",
        f" From: {result['from_worktree']['branch']} ({result['from_worktree']['path']})",
        f" To: {result['to_worktree']['branch']} ({result['to_worktree']['path']})",
    ]

    if result["context_preserved"]:
        output.extend(_format_context_preserved(result))
    else:
        output.extend(_format_context_failed(result))

    return "\n".join(output)


def _format_context_preserved(result: dict[str, t.Any]) -> list[str]:
    """Format preserved context information."""
    messages = [" Session context preserved during switch"]

    if result.get("session_state_saved"):
        messages.append(" Current session state saved")
    if result.get("session_state_restored"):
        messages.append(" Session state restored for target worktree")

    return messages


def _format_context_failed(result: dict[str, t.Any]) -> list[str]:
    """Format failed context information."""
    messages = [" Session context preservation failed (basic switch performed)"]

    if result.get("session_error"):
        messages.append(f"   Error: {result['session_error']}")

    return messages


async def git_worktree_switch(from_path: str, to_path: str) -> str:
    """Switch context between git worktrees with session preservation."""
    from .utils.logging import get_session_logger
    from .worktree_manager import WorktreeManager

    # Get session logger from DI container (using helper to avoid type conflicts)
    session_logger = get_session_logger()

    manager = WorktreeManager(session_logger=session_logger)

    try:
        result = await manager.switch_worktree_context(Path(from_path), Path(to_path))

        if not result["success"]:
            return f" {result['error']}"

        return _format_worktree_switch_result(result)

    except Exception as e:
        session_logger.exception(f"git_worktree_switch failed: {e}")
        return f"❌ Failed to switch worktree context: {e}"


# ================================
# Session Welcome Tool
# ================================

# Global connection info (will be set by server lifecycle)
_connection_info: dict[str, t.Any] | None = None


def set_connection_info(info: dict[str, t.Any]) -> None:
    """Set connection info for session welcome (called from server lifespan)."""
    global _connection_info
    _connection_info = info


async def session_welcome() -> str:
    """Display session connection information and previous session details."""
    global _connection_info

    if not _connection_info:
        return "ℹ️ Session information not available (may not be a git repository)"

    output: list[str] = []
    output.extend(("🚀 Session Management Connected!", "=" * 40))

    # Current session info
    output.extend(
        (
            f"📁 Project: {_connection_info['project']}",
            f"📊 Current quality score: {_connection_info['quality_score']}/100",
            f"🔗 Connection status: {_connection_info['connected_at']}",
        )
    )

    # Previous session info
    previous = _connection_info.get("previous_session")
    if previous:
        output.extend(("\n📋 Previous Session Summary:", "-" * 30))

        if "ended_at" in previous:
            output.append(f"⏰ Last session ended: {previous['ended_at']}")
        if "quality_score" in previous:
            output.append(f"📈 Final score: {previous['quality_score']}")
        if "top_recommendation" in previous:
            output.append(f"💡 Key recommendation: {previous['top_recommendation']}")

        output.append("\n✨ Session continuity restored - your progress is preserved!")
    else:
        output.extend(
            (
                "\n🌟 This is your first session in this project!",
                "💡 Session data will be preserved for future continuity",
            )
        )

    # Current recommendations
    recommendations = _connection_info.get("recommendations", [])
    if recommendations:
        output.append("\n🎯 Current Recommendations:")
        for i, rec in enumerate(recommendations[:3], 1):
            output.append(f"   {i}. {rec}")

    output.extend(
        (
            "\n🔧 Use other session-mgmt tools for:",
            "   • /session-buddy:status - Detailed project health",
            "   • /session-buddy:checkpoint - Mid-session quality check",
            "   • /session-buddy:end - Graceful session cleanup",
        )
    )

    # Clear the connection info after display
    _connection_info = None

    return "\n".join(output)
