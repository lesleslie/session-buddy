"""MCP Server Core Infrastructure.

This module handles FastMCP initialization, server lifecycle management,
tool registration, and core infrastructure components.

Extracted Components:
- SessionPermissionsManager class (singleton permissions management)
- Configuration functions (_load_mcp_config, _detect_other_mcp_servers, etc.)
- Session lifecycle handler (session_lifecycle)
- Initialization functions (initialize_new_features, analyze_project_context)
- Health and status functions (health_check, _add_basic_status_info, etc.)
- Quality formatting functions (_format_quality_results, _perform_git_checkpoint)
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import warnings
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from mcp_common.ui import ServerPanels

    from session_buddy.core.permissions import SessionPermissionsManager
    from session_buddy.utils.logging import SessionLogger

# Re-export for backward compatibility in tests and integrations.

# Suppress transformers warnings
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message=".*PyTorch.*TensorFlow.*Flax.*")

# Import mcp-common ServerPanels for beautiful terminal UI
try:
    from mcp_common.ui import ServerPanels

    SERVERPANELS_AVAILABLE = True
except ImportError:
    SERVERPANELS_AVAILABLE = False

try:
    import tomli
except ImportError:
    tomli = None  # type: ignore[assignment]

# Import extracted modules


# =====================================
# Configuration and Detection Functions
# =====================================


def _detect_other_mcp_servers() -> dict[str, bool]:
    """Detect availability of other MCP servers by checking common paths and processes."""
    detected = {}

    # Check for crackerjack MCP server
    try:
        # Try to import crackerjack to see if it's available
        result = subprocess.run(
            ["crackerjack", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        detected["crackerjack"] = result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        detected["crackerjack"] = False

    return detected


def _generate_server_guidance(detected_servers: dict[str, bool]) -> list[str]:
    """Generate guidance messages based on detected servers."""
    guidance = []

    if detected_servers.get("crackerjack"):
        guidance.extend(
            [
                "💡 CRACKERJACK INTEGRATION DETECTED:",
                "   Enhanced commands available for better development experience:",
                "   • Use /session-buddy:crackerjack-run instead of /crackerjack:run",
                "   • Gets memory, analytics, and intelligent insights automatically",
                "   • View trends with /session-buddy:crackerjack-history",
                "   • Analyze patterns with /session-buddy:crackerjack-patterns",
            ],
        )

    return guidance


def _load_mcp_config() -> dict[str, Any]:
    """Load MCP server configuration from pyproject.toml."""
    # Look for pyproject.toml in the current project directory
    pyproject_path = Path.cwd() / "pyproject.toml"

    # If not found in cwd, look in parent directories (up to 3 levels)
    if not pyproject_path.exists():
        for parent in Path.cwd().parents[:3]:
            potential_path = parent / "pyproject.toml"
            if potential_path.exists():
                pyproject_path = potential_path
                break

    if not pyproject_path.exists() or not tomli:
        return {
            "http_port": 8678,
            "http_host": "127.0.0.1",
            "websocket_monitor_port": 8677,
            "http_enabled": False,
        }

    try:
        with pyproject_path.open("rb") as f:
            pyproject_data = tomli.load(f)

        session_config = pyproject_data.get("tool", {}).get("session-mgmt-mcp", {})

        return {
            "http_port": session_config.get("mcp_http_port", 8678),
            "http_host": session_config.get("mcp_http_host", "127.0.0.1"),
            "websocket_monitor_port": session_config.get(
                "websocket_monitor_port",
                8677,
            ),
            "http_enabled": session_config.get("http_enabled", False),
        }
    except Exception as e:
        if SERVERPANELS_AVAILABLE:
            ServerPanels.warning(
                title="Configuration Warning",
                message="Failed to load MCP config from pyproject.toml",
                details=[str(e), "Using default configuration values"],
            )
        return {
            "http_port": 8678,
            "http_host": "127.0.0.1",
            "websocket_monitor_port": 8677,
            "http_enabled": False,
        }


# =====================================
# Session Lifecycle Handler
# =====================================


@asynccontextmanager
async def session_lifecycle(
    app: Any,
    lifecycle_manager: Any,
    session_logger: SessionLogger,
) -> AsyncGenerator[None]:
    """Automatic session lifecycle for git repositories only.

    Args:
        app: FastMCP application instance
        lifecycle_manager: SessionLifecycleManager instance
        session_logger: SessionLogger instance

    Yields:
        None during server lifetime

    """
    # Import here to avoid circular dependencies
    from session_buddy.utils.git_worktrees import is_git_repository

    current_dir = Path.cwd()
    adapter_announcer = await _initialize_adapter_announcer(session_logger)

    # Initialize session for git repositories
    if is_git_repository(current_dir):
        await _initialize_git_session(current_dir, lifecycle_manager, session_logger)

    yield  # Server runs normally

    # Cleanup on disconnect
    await _cleanup_session_lifecycle(
        adapter_announcer, current_dir, lifecycle_manager, session_logger
    )


async def _initialize_adapter_announcer(
    session_logger: SessionLogger,
) -> Any:
    """Initialize the adapter announcer for registry integration.

    Args:
        session_logger: Logger instance

    Returns:
        AdapterAnnouncer instance or None if initialization failed
    """
    try:
        from .cli import SessionBuddySettings

        settings = SessionBuddySettings()

        if not settings.adapter_registry_enabled:
            return None

        return await _create_and_connect_announcer(settings, session_logger)

    except Exception as e:
        session_logger.warning(f"Failed to load settings for adapter announcer: {e}")
        return None


async def _create_and_connect_announcer(
    settings: Any, session_logger: SessionLogger
) -> Any:
    """Create and connect the adapter announcer.

    Args:
        settings: SessionBuddySettings instance
        session_logger: Logger instance

    Returns:
        Connected AdapterAnnouncer instance or None
    """
    try:
        from oneiric_mcp.client import AdapterAnnouncer

        announcer = AdapterAnnouncer(
            registry_host=settings.adapter_registry_host,
            registry_port=settings.adapter_registry_port,
        )
        await announcer.connect()
        session_logger.info(
            f"Adapter announcer initialized: {settings.adapter_registry_host}:{settings.adapter_registry_port}"
        )

        # Announce memory adapters
        adapter_id = await announcer.announce_adapter(
            project="session-buddy",
            domain="adapter",
            category="memory",
            provider="reflection",
            capabilities=["read", "write", "search", "checkpoint"],
            factory_path="session_buddy.adapters.reflection_adapter_oneiric:ReflectionAdapter",
        )
        session_logger.info(f"Announced memory adapter: {adapter_id}")

        # Start heartbeat
        await announcer.start_heartbeat(adapter_id=adapter_id, interval_sec=30)

        return announcer

    except ImportError:
        session_logger.warning(
            "oneiric_mcp not available - adapter announcement disabled"
        )
        return None
    except Exception as e:
        session_logger.warning(f"Failed to initialize adapter announcer: {e}")
        return None


async def _initialize_git_session(
    current_dir: Path,
    lifecycle_manager: Any,
    session_logger: SessionLogger,
) -> None:
    """Initialize session for a git repository.

    Args:
        current_dir: Current working directory
        lifecycle_manager: SessionLifecycleManager instance
        session_logger: Logger instance
    """
    from session_buddy.utils.git_worktrees import get_git_root

    try:
        git_root = get_git_root(current_dir)
        session_logger.info(f"Git repository detected at {git_root}")

        result = await lifecycle_manager.initialize_session(str(current_dir))
        if result["success"]:
            session_logger.info("Auto-initialized session for git repository")
            _store_connection_info(result)
        else:
            session_logger.warning(f"Auto-init failed: {result['error']}")

    except Exception as e:
        session_logger.warning(f"Auto-init failed (non-critical): {e}")


def _store_connection_info(result: dict[str, Any]) -> None:
    """Store connection info for display via tools.

    Args:
        result: Initialization result dictionary
    """
    from session_buddy.advanced_features import set_connection_info

    connection_info = {
        "connected_at": "just connected",
        "project": result["project"],
        "quality_score": result["quality_score"],
        "previous_session": result.get("previous_session"),
        "recommendations": result["quality_data"].get("recommendations", []),
    }
    set_connection_info(connection_info)


async def _cleanup_session_lifecycle(
    adapter_announcer: Any,
    current_dir: Path,
    lifecycle_manager: Any,
    session_logger: SessionLogger,
) -> None:
    """Cleanup adapter announcer and end session on disconnect.

    Args:
        adapter_announcer: AdapterAnnouncer instance or None
        current_dir: Current working directory
        lifecycle_manager: SessionLifecycleManager instance
        session_logger: Logger instance
    """
    await _close_adapter_announcer(adapter_announcer, session_logger)
    await _end_git_session(current_dir, lifecycle_manager, session_logger)


async def _close_adapter_announcer(
    adapter_announcer: Any, session_logger: SessionLogger
) -> None:
    """Close the adapter announcer connection.

    Args:
        adapter_announcer: AdapterAnnouncer instance or None
        session_logger: Logger instance
    """
    if not adapter_announcer:
        return

    try:
        await adapter_announcer.close()
        session_logger.info("Adapter announcer connection closed")
    except Exception as e:
        session_logger.warning(f"Failed to close adapter announcer: {e}")


async def _end_git_session(
    current_dir: Path,
    lifecycle_manager: Any,
    session_logger: SessionLogger,
) -> None:
    """End session for git repositories on disconnect.

    Args:
        current_dir: Current working directory
        lifecycle_manager: SessionLifecycleManager instance
        session_logger: Logger instance
    """
    from session_buddy.utils.git_worktrees import is_git_repository

    if not is_git_repository(current_dir):
        return

    try:
        result = await lifecycle_manager.end_session()
        if result["success"]:
            session_logger.info("Auto-ended session for git repository")
        else:
            session_logger.warning(f"Auto-cleanup failed: {result['error']}")
    except Exception as e:
        session_logger.warning(f"Auto-cleanup failed (non-critical): {e}")


# =====================================
# Initialization Functions
# =====================================


async def auto_setup_git_working_directory(session_logger: SessionLogger) -> None:
    """Auto-detect and setup git working directory for enhanced DX."""
    try:
        # Get current working directory
        current_dir = Path.cwd()

        # Import git utilities
        from session_buddy.utils.git_worktrees import (
            get_git_root,
            is_git_repository,
        )

        # Try to find git root from current directory
        git_root = None
        if is_git_repository(current_dir):
            git_root = get_git_root(current_dir)

        if git_root and git_root.exists():
            # Log the auto-setup action for Claude to see
            session_logger.info(f"🔧 Auto-detected git repository: {git_root}")
            session_logger.info(
                f"💡 Recommend: Use `mcp__git__git_set_working_dir` with path='{git_root}'",
            )

            # Also log to stderr for immediate visibility
            if SERVERPANELS_AVAILABLE:
                ServerPanels.info(
                    title="Git Repository Detected",
                    message=f"Repository root: {git_root}",
                    items={
                        "Auto-setup command": f"git_set_working_dir('{git_root}')",
                        "Auto-lifecycle": "Enabled (init, checkpoint, cleanup)",
                    },
                )
        else:
            session_logger.debug(
                "No git repository detected in current directory - skipping auto-setup",
            )

    except Exception as e:
        # Graceful fallback - don't break server startup
        session_logger.debug(f"Git auto-setup failed (non-critical): {e}")


async def initialize_new_features(
    session_logger: SessionLogger,
    multi_project_coordinator_ref: Any,
    advanced_search_engine_ref: Any,
    app_config_ref: Any,
) -> tuple[Any, Any, Any]:
    """Initialize multi-project coordination and advanced search features.

    Args:
        session_logger: Logger instance for diagnostics
        multi_project_coordinator_ref: Reference to store coordinator instance
        advanced_search_engine_ref: Reference to store search engine instance
        app_config_ref: Reference to store configuration

    Returns:
        Tuple of (multi_project_coordinator, advanced_search_engine, app_config)

    """
    # Import feature detection
    from session_buddy.core.features import get_feature_flags

    _features = get_feature_flags()
    advanced_search_available = _features["ADVANCED_SEARCH_AVAILABLE"]
    config_available = _features["CONFIG_AVAILABLE"]
    multi_project_available = _features["MULTI_PROJECT_AVAILABLE"]
    reflection_tools_available = _features["REFLECTION_TOOLS_AVAILABLE"]

    # Auto-setup git working directory for enhanced DX
    await auto_setup_git_working_directory(session_logger)

    # Initialize default return values
    multi_project_coordinator = multi_project_coordinator_ref
    advanced_search_engine = advanced_search_engine_ref
    app_config = app_config_ref

    # Load configuration
    if config_available:
        from session_buddy.settings import get_settings

        app_config = get_settings()

    # Initialize reflection database for new features
    if reflection_tools_available:
        with suppress(
            ImportError,
            ModuleNotFoundError,
            RuntimeError,
            AttributeError,
            OSError,
            ValueError,
        ):
            from session_buddy.reflection_tools import get_reflection_database

            db = await get_reflection_database()

            # Initialize multi-project coordinator
            if multi_project_available:
                from session_buddy.multi_project_coordinator import (
                    MultiProjectCoordinator,
                )

                multi_project_coordinator = MultiProjectCoordinator(db)

            # Initialize advanced search engine
            if advanced_search_available:
                from session_buddy.advanced_search import AdvancedSearchEngine

                # Type ignore: db is ReflectionDatabaseAdapterOneiric which is compatible
                advanced_search_engine = AdvancedSearchEngine(db)  # type: ignore[arg-type]

    return multi_project_coordinator, advanced_search_engine, app_config


# Re-export for backward compatibility
from session_buddy.utils.project_analysis import (
    analyze_project_context as _analyze_project_context,
)


async def analyze_project_context(project_dir: Path) -> dict[str, bool]:
    """Analyze project structure and context with enhanced error handling.

    This is a backward-compatibility wrapper that delegates to the utility module.
    Direct imports from session_buddy.utils.project_analysis are preferred.
    """
    return await _analyze_project_context(project_dir)


# =====================================
# Health & Status Functions
# =====================================


async def health_check(
    session_logger: SessionLogger,
    permissions_manager: SessionPermissionsManager,
    validate_claude_directory: Any,
) -> dict[str, Any]:
    """Comprehensive health check for MCP server and toolkit availability."""
    # Import feature detection
    from session_buddy.core.features import get_feature_flags

    _features = get_feature_flags()
    crackerjack_integration_available = _features["CRACKERJACK_INTEGRATION_AVAILABLE"]
    session_management_available = _features["SESSION_MANAGEMENT_AVAILABLE"]

    health_status: dict[str, Any] = {
        "overall_healthy": True,
        "checks": {},
        "warnings": [],
        "errors": [],
    }

    # MCP Server health
    try:
        # Test FastMCP availability
        health_status["checks"]["mcp_server"] = "✅ Active"
    except Exception as e:
        health_status["checks"]["mcp_server"] = "❌ Error"
        health_status["errors"].append(f"MCP server issue: {e}")
        health_status["overall_healthy"] = False

    # Session management toolkit health
    health_status["checks"]["session_toolkit"] = (
        "✅ Available" if session_management_available else "⚠️ Limited"
    )
    if not session_management_available:
        health_status["warnings"].append(
            "Session management toolkit not fully available",
        )

    # UV package manager health
    uv_available = shutil.which("uv") is not None
    health_status["checks"]["uv_manager"] = (
        "✅ Available" if uv_available else "❌ Missing"
    )
    if not uv_available:
        health_status["warnings"].append("UV package manager not found")

    # Claude directory health
    validate_claude_directory()
    health_status["checks"]["claude_directory"] = "✅ Valid"

    # Permissions system health
    try:
        permissions_status = permissions_manager.get_permission_status()
        health_status["checks"]["permissions_system"] = "✅ Active"
        health_status["checks"]["session_id"] = (
            f"Active ({permissions_status['session_id']})"
        )
    except Exception as e:
        health_status["checks"]["permissions_system"] = "❌ Error"
        health_status["errors"].append(f"Permissions system issue: {e}")
        health_status["overall_healthy"] = False

    # Crackerjack integration health
    health_status["checks"]["crackerjack_integration"] = (
        "✅ Available" if crackerjack_integration_available else "⚠️ Not Available"
    )
    if not crackerjack_integration_available:
        health_status["warnings"].append(
            "Crackerjack integration not available - quality monitoring disabled",
        )

    # Log health check results
    session_logger.info(
        "Health check completed",
        overall_healthy=health_status["overall_healthy"],
        warnings_count=len(health_status["warnings"]),
        errors_count=len(health_status["errors"]),
    )

    return health_status


async def _add_basic_status_info(
    output: list[str],
    current_dir: Path,
    current_project_ref: Any,
) -> None:
    """Add basic status information to output."""
    current_project_ref = current_dir.name

    output.extend(
        (
            f"📁 Current project: {current_project_ref}",
            f"🗂️ Working directory: {current_dir}",
            "🌐 MCP server: Active (Claude Session Management)",
        )
    )


async def _add_health_status_info(
    output: list[str],
    session_logger: SessionLogger,
    permissions_manager: SessionPermissionsManager,
    validate_claude_directory: Any,
) -> None:
    """Add health check information to output."""
    health_status = await health_check(
        session_logger,
        permissions_manager,
        validate_claude_directory,
    )

    output.append(
        f"\n🏥 System Health: {'✅ HEALTHY' if health_status['overall_healthy'] else '⚠️ ISSUES DETECTED'}",
    )

    # Display health check results
    for check_name, status in health_status["checks"].items():
        friendly_name = check_name.replace("_", " ").title()
        output.append(f"   • {friendly_name}: {status}")

    # Show warnings and errors
    if health_status["warnings"]:
        output.append("\n⚠️ Health Warnings:")
        for warning in health_status["warnings"][:3]:  # Limit to 3 warnings
            output.append(f"   • {warning}")

    if health_status["errors"]:
        output.append("\n❌ Health Errors:")
        for error in health_status["errors"][:3]:  # Limit to 3 errors
            output.append(f"   • {error}")


async def _get_project_context_info(
    current_dir: Path,
) -> tuple[dict[str, Any], int, int]:
    """Get project context information and scores."""
    project_context = await analyze_project_context(current_dir)
    context_score = sum(1 for detected in project_context.values() if detected)
    max_score = len(project_context)
    return project_context, context_score, max_score


# =====================================
# Quality & Formatting Functions
# =====================================


async def _format_quality_results(
    quality_score: int,
    quality_data: dict[str, Any],
    checkpoint_result: dict[str, Any] | None = None,
) -> list[str]:
    """Format quality assessment results for display."""
    output = []

    # Quality status with version indicator
    version = quality_data.get("version", "1.0")
    if quality_score >= 80:
        output.append(
            f"✅ Session quality: EXCELLENT (Score: {quality_score}/100) [V{version}]",
        )
    elif quality_score >= 60:
        output.append(
            f"✅ Session quality: GOOD (Score: {quality_score}/100) [V{version}]",
        )
    else:
        output.append(
            f"⚠️ Session quality: NEEDS ATTENTION (Score: {quality_score}/100) [V{version}]",
        )

    # Quality breakdown - V2 format (actual code quality metrics)
    output.append("\n📈 Quality breakdown (code health metrics):")
    breakdown = quality_data["breakdown"]
    output.extend(
        (
            f"   • Code quality: {breakdown['code_quality']:.1f}/40",
            f"   • Project health: {breakdown['project_health']:.1f}/30",
            f"   • Dev velocity: {breakdown['dev_velocity']:.1f}/20",
            f"   • Security: {breakdown['security']:.1f}/10",
        )
    )

    # Trust score (separate from quality)
    if "trust_score" in quality_data:
        trust = quality_data["trust_score"]
        output.extend(
            (
                f"\n🔐 Trust score: {trust['total']:.0f}/100 (separate metric)",
                f"   • Trusted operations: {trust['breakdown']['trusted_operations']:.0f}/40",
                f"   • Session features: {trust['breakdown']['session_availability']:.0f}/30",
                f"   • Tool ecosystem: {trust['breakdown']['tool_ecosystem']:.0f}/30",
            )
        )

    # Recommendations
    recommendations = quality_data["recommendations"]
    if recommendations:
        output.append("\n💡 Recommendations:")
        for rec in recommendations[:3]:
            output.append(f"   • {rec}")

    # Session management specific results
    if checkpoint_result:
        strengths = checkpoint_result.get("strengths", [])
        if strengths:
            output.append("\n🌟 Session strengths:")
            for strength in strengths[:3]:
                output.append(f"   • {strength}")

        session_stats = checkpoint_result.get("session_stats", {})
        if session_stats:
            output.extend(
                (
                    "\n⏱️ Session progress:",
                    f"   • Duration: {session_stats.get('duration_minutes', 0)} minutes",
                    f"   • Checkpoints: {session_stats.get('total_checkpoints', 0)}",
                    f"   • Success rate: {session_stats.get('success_rate', 0):.1f}%",
                )
            )

    return output


async def _perform_git_checkpoint(
    current_dir: Path,
    quality_score: int,
    project_name: str,
) -> list[str]:
    """Handle git operations for checkpoint commit."""
    output: list[str] = []
    output.extend(("\n" + "=" * 50, "📦 Git Checkpoint Commit", "=" * 50))

    # Use the proper checkpoint commit function from git_worktrees
    from session_buddy.utils.git_worktrees import create_checkpoint_commit

    success, result, commit_output = create_checkpoint_commit(
        current_dir,
        project_name,
        quality_score,
    )

    # Add the commit output to our output
    output.extend(commit_output)

    if success and result != "clean":
        output.append(f"✅ Checkpoint commit created: {result}")
    elif not success:
        output.append(f"⚠️ Failed to stage files: {result}")

    return output


async def _format_conversation_summary() -> list[str]:
    """Format the conversation summary section."""
    output = []
    with suppress(
        ImportError,
        ModuleNotFoundError,
        RuntimeError,
        AttributeError,
        ValueError,
    ):
        from session_buddy.quality_engine import summarize_current_conversation

        conversation_summary = await summarize_current_conversation()
        if conversation_summary["key_topics"]:
            output.append("\n💬 Current Session Focus:")
            for topic in conversation_summary["key_topics"][:3]:
                output.append(f"   • {topic}")

        if conversation_summary["decisions_made"]:
            output.append("\n✅ Key Decisions:")
            for decision in conversation_summary["decisions_made"][:2]:
                output.append(f"   • {decision}")
    return output


# =====================================
# Utility Functions
# =====================================


def _should_retry_search(error: Exception) -> bool:
    """Determine if a search error warrants a retry with cleanup."""
    # Retry for database connection issues or temporary errors
    error_msg = str(error).lower()
    retry_conditions = [
        "database is locked",
        "connection failed",
        "temporary failure",
        "timeout",
        "index not found",
    ]
    return any(condition in error_msg for condition in retry_conditions)


# =====================================
# Feature Detection (Phase 2.6)
# =====================================
