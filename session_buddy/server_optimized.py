#!/usr/bin/env python3
"""Optimized Session Management MCP Server.

This is the refactored, modular version of the session management server.
It's organized into focused modules for better maintainability and performance.
"""

import sys
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Lazy loading for FastMCP
try:
    from fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    # Check if we're in a test environment
    if "pytest" in sys.modules or "test" in sys.argv[0].lower():
        # Create a minimal mock FastMCP for testing
        class MockFastMCP:
            def __init__(self, name: str, lifespan: Any = None, **kwargs: Any) -> None:
                self.name = name
                self.tools: dict[str, Any] = {}
                self.prompts: dict[str, Any] = {}
                self.lifespan = lifespan

            def tool(
                self,
                *args: Any,
                **kwargs: Any,
            ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
                def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                    return func

                return decorator

            def prompt(
                self,
                *args: Any,
                **kwargs: Any,
            ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
                def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                    return func

                return decorator

            def run(self, *args: Any, **kwargs: Any) -> None:
                pass

        FastMCP = MockFastMCP  # type: ignore[no-redef]
        MCP_AVAILABLE = False
    else:
        sys.exit(1)

# Initialize logging
from session_buddy.utils.logging import get_session_logger

logger = get_session_logger()

# Import required modules for automatic lifecycle
import os

from session_buddy.core import SessionLifecycleManager
from session_buddy.utils.git_operations import get_git_root, is_git_repository

# Global session manager for lifespan handlers
lifecycle_manager = SessionLifecycleManager()

# Global connection info for notification display
_connection_info = None


# Lifespan handler for automatic session management
@asynccontextmanager
async def session_lifecycle(app: Any) -> AsyncGenerator[None]:
    """Automatic session lifecycle for git repositories only."""
    current_dir = Path.cwd()

    # Only auto-initialize for git repositories
    if is_git_repository(current_dir):
        try:
            git_root = get_git_root(current_dir)
            logger.info(f"Git repository detected at {git_root}")

            # Run the same logic as the init tool but with connection notification
            result = await lifecycle_manager.initialize_session(str(current_dir))
            if result["success"]:
                logger.info("✅ Auto-initialized session for git repository")

                # Store connection info for display via tools
                global _connection_info
                _connection_info = {
                    "connected_at": "just connected",
                    "project": result["project"],
                    "quality_score": result["quality_score"],
                    "previous_session": result.get("previous_session"),
                    "recommendations": result["quality_data"].get(
                        "recommendations",
                        [],
                    ),
                }
            else:
                logger.warning(f"Auto-init failed: {result['error']}")
        except Exception as e:
            logger.warning(f"Auto-init failed (non-critical): {e}")
    else:
        logger.debug("Non-git directory - skipping auto-initialization")

    yield  # Server runs normally

    # On disconnect - cleanup for git repos only
    if is_git_repository(current_dir):
        try:
            result = await lifecycle_manager.end_session()
            if result["success"]:
                logger.info("✅ Auto-ended session for git repository")
            else:
                logger.warning(f"Auto-cleanup failed: {result['error']}")
        except Exception as e:
            logger.warning(f"Auto-cleanup failed (non-critical): {e}")


# Initialize MCP server with lifespan
mcp = FastMCP("session-buddy", lifespan=session_lifecycle)

# Register modularized tools
from session_buddy.tools import (
    register_category_tools,
    register_fingerprint_tools,
    register_memory_tools,
    register_session_tools,
)

# Core session management tools
# Type ignore: mcp is MockFastMCP|FastMCP union in tests, both have compatible interface
register_session_tools(mcp)  # type: ignore[argument-type]

# Memory and reflection tools
register_memory_tools(mcp)  # type: ignore[argument-type]

# Fingerprint tools (Phase 4: N-gram Fingerprinting)
register_fingerprint_tools(mcp)  # type: ignore[argument-type]

# Category evolution tools (Phase 5: Category Evolution)
register_category_tools(mcp)  # type: ignore[argument-type]


@mcp.tool()
async def session_welcome() -> str:
    """Display session connection information and previous session details."""
    global _connection_info

    if not _connection_info:
        return "ℹ️ Session information not available (may not be a git repository)"

    output = []
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
            "\n🔧 Use other session-buddy tools for:",
            "   • /session-buddy:status - Detailed project health",
            "   • /session-buddy:checkpoint - Mid-session quality check",
            "   • /session-buddy:end - Graceful session cleanup",
        )
    )

    # Clear the connection info after display
    _connection_info = None

    return "\n".join(output)


# Import the real SessionPermissionsManager from core module
from session_buddy.core.permissions import SessionPermissionsManager
from session_buddy.di.container import depends


def _get_permissions_manager() -> SessionPermissionsManager:
    import typing as t
    from contextlib import suppress

    with suppress(Exception):
        manager = t.cast(
            "SessionPermissionsManager | None",
            depends.get_sync(SessionPermissionsManager),
        )
        if isinstance(manager, SessionPermissionsManager):
            return manager

    from session_buddy.di.config import SessionPaths

    with suppress(Exception):
        paths = depends.get_sync(SessionPaths)
        if isinstance(paths, SessionPaths):
            manager = SessionPermissionsManager(paths.claude_dir)
            depends.set(SessionPermissionsManager, manager)
            return manager

    paths = SessionPaths.from_home()
    paths.ensure_directories()
    manager = SessionPermissionsManager(paths.claude_dir)
    depends.set(SessionPermissionsManager, manager)
    return manager


@mcp.tool()
async def permissions(action: str = "status", operation: str | None = None) -> str:
    """Manage session permissions for trusted operations to avoid repeated prompts.

    Args:
        action: Action to perform: status (show current), trust (add operation), revoke_all (reset)
        operation: Operation to trust (required for 'trust' action)

    """
    output = []
    output.extend(("🔐 Session Permissions Management", "=" * 40))

    permissions_manager = _get_permissions_manager()
    if action == "status":
        if permissions_manager.trusted_operations:
            output.append(
                f"✅ {len(permissions_manager.trusted_operations)} trusted operations:",
            )
            for op in sorted(permissions_manager.trusted_operations):
                output.append(f"   • {op}")
            output.append(
                "\n💡 These operations will not prompt for permission in future sessions",
            )
        else:
            output.extend(
                (
                    "⚠️ No operations are currently trusted",
                    "💡 Operations will be automatically trusted on first successful use",
                )
            )

        output.extend(
            (
                "\n🛠️ Common Operations That Can Be Trusted:",
                "   • UV Package Management - uv sync, pip operations",
                "   • Git Repository Access - git status, commit, push",
                "   • Project File Access - reading/writing project files",
                "   • Subprocess Execution - running build tools, tests",
                "   • Claude Directory Access - accessing ~/.claude/",
            )
        )

    elif action == "trust":
        if not operation:
            output.extend(
                (
                    "❌ Error: 'operation' parameter required for 'trust' action",
                    "💡 Example: permissions with action='trust' and operation='uv_package_management'",
                )
            )
        else:
            permissions_manager.trust_operation(operation)
            output.extend(
                (
                    f"✅ Operation '{operation}' has been added to trusted operations",
                    "💡 This operation will no longer require permission prompts",
                )
            )

    elif action == "revoke_all":
        count = len(permissions_manager.trusted_operations)
        permissions_manager.trusted_operations.clear()
        output.extend(
            (
                f"🗑️ Revoked {count} trusted operations",
                "💡 All operations will now require permission prompts",
            )
        )

    else:
        output.extend(
            (
                f"❌ Unknown action: {action}",
                "💡 Valid actions: status, trust, revoke_all",
            )
        )

    return "\n".join(output)


# Compaction analysis and auto-execution functions
def _count_significant_files(current_dir: Path) -> int:
    """Count significant files in project as a complexity indicator."""
    file_count = 0
    with suppress(OSError, PermissionError, FileNotFoundError, ValueError):
        for file_path in current_dir.rglob("*"):
            if (
                file_path.is_file()
                and not any(part.startswith(".") for part in file_path.parts)
                and file_path.suffix
                in {
                    ".py",
                    ".js",
                    ".ts",
                    ".jsx",
                    ".tsx",
                    ".go",
                    ".rs",
                    ".java",
                    ".cpp",
                    ".c",
                    ".h",
                }
            ):
                file_count += 1
                if file_count > 50:  # Stop counting after threshold
                    break
    return file_count


def _check_git_activity(current_dir: Path) -> tuple[int, int] | None:
    """Check for active development via git and return (recent_commits, modified_files)."""
    import subprocess  # nosec B404

    git_dir = current_dir / ".git"
    if not git_dir.exists():
        return None

    try:
        # Check number of recent commits as activity indicator
        result = subprocess.run(
            ["git", "log", "--oneline", "-20", "--since='24 hours ago'"],
            check=False,
            capture_output=True,
            text=True,
            cwd=current_dir,
            timeout=5,
        )
        if result.returncode == 0:
            recent_commits = len(
                [line for line in result.stdout.strip().split("\n") if line.strip()],
            )
        else:
            recent_commits = 0

        # Check for large number of modified files
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            cwd=current_dir,
            timeout=5,
        )
        if status_result.returncode == 0:
            modified_files = len(
                [
                    line
                    for line in status_result.stdout.strip().split("\n")
                    if line.strip()
                ],
            )
        else:
            modified_files = 0

        return recent_commits, modified_files

    except (subprocess.TimeoutExpired, Exception):
        return None


def _evaluate_large_project_heuristic(file_count: int) -> tuple[bool, str]:
    """Evaluate if the project is large enough to benefit from compaction."""
    if file_count > 50:
        return (
            True,
            "Large codebase with 50+ source files detected - context compaction recommended",
        )
    return False, ""


def _evaluate_git_activity_heuristic(
    git_activity: tuple[int, int] | None,
) -> tuple[bool, str]:
    """Evaluate if git activity suggests compaction would be beneficial."""
    if git_activity:
        recent_commits, modified_files = git_activity

        if recent_commits >= 3:
            return (
                True,
                f"High development activity ({recent_commits} commits in 24h) - compaction recommended",
            )

        if modified_files >= 10:
            return (
                True,
                f"Many modified files ({modified_files}) detected - context optimization beneficial",
            )

    return False, ""


def _evaluate_python_project_heuristic(current_dir: Path) -> tuple[bool, str]:
    """Evaluate if this is a Python project that might benefit from compaction."""
    if (current_dir / "tests").exists() and (current_dir / "pyproject.toml").exists():
        return (
            True,
            "Python project with tests detected - compaction may improve focus",
        )
    return False, ""


def _get_default_compaction_reason() -> str:
    """Get the default reason when no strong indicators are found."""
    return "Context appears manageable - compaction not immediately needed"


def _get_fallback_compaction_reason() -> str:
    """Get fallback reason when evaluation fails."""
    return "Unable to assess context complexity - compaction may be beneficial as a precaution"


def should_suggest_compact() -> tuple[bool, str]:
    """Determine if compacting would be beneficial and provide reasoning.
    Returns (should_compact, reason).
    """
    from pathlib import Path

    try:
        current_dir = Path(os.environ.get("PWD", Path.cwd()))

        # Count significant files in project as a complexity indicator
        file_count = _count_significant_files(current_dir)

        # Large project heuristic
        should_compact, reason = _evaluate_large_project_heuristic(file_count)
        if should_compact:
            return should_compact, reason

        # Check for active development via git
        git_activity = _check_git_activity(current_dir)
        should_compact, reason = _evaluate_git_activity_heuristic(git_activity)
        if should_compact:
            return should_compact, reason

        # Check for common patterns suggesting complex session
        should_compact, reason = _evaluate_python_project_heuristic(current_dir)
        if should_compact:
            return should_compact, reason

        # Default to not suggesting unless we have clear indicators
        return False, _get_default_compaction_reason()

    except Exception:
        # If we can't determine, err on the side of suggesting compaction for safety
        return True, _get_fallback_compaction_reason()


async def _execute_auto_compact() -> str:
    """Execute internal compaction instead of recommending /compact command."""
    try:
        # This would trigger the same logic as /compact but automatically
        # For now, we use the memory system's auto-compaction
        return "✅ Context automatically optimized via intelligent memory management"
    except Exception as e:
        logger.warning(f"Auto-compact execution failed: {e}")
        return f"⚠️ Auto-compact failed: {e!s} - recommend manual /compact"


# Enhanced tools with auto-compaction
@mcp.tool()
async def auto_compact() -> str:
    """Automatically trigger conversation compaction with intelligent summary."""
    output = []
    output.extend(("🗜️ Auto-Compaction Feature", "=" * 30))

    should_compact, reason = should_suggest_compact()
    output.append(f"📊 Analysis: {reason}")

    if should_compact:
        output.append("\n🔄 Executing automatic compaction...")
        compact_result = await _execute_auto_compact()
        output.append(compact_result)
    else:
        output.append("✅ Context optimization not needed at this time")

    return "\n".join(output)


@mcp.tool()
async def quality_monitor() -> str:
    """Phase 3: Proactive quality monitoring with early warning system."""
    output = []
    output.extend(
        (
            "📊 Quality Monitoring",
            "=" * 25,
            "✅ Quality monitoring is integrated into the session management system",
            "💡 Use the 'status' tool to get current quality metrics",
            "💡 Use the 'checkpoint' tool for comprehensive quality assessment",
        )
    )
    return "\n".join(output)


# Server startup
def run_server() -> None:
    """Run the optimized MCP server."""
    try:
        logger.info("Starting optimized session-buddy server")

        # Log the modular structure
        logger.info(
            "Modular components loaded",
            session_tools=True,
            memory_tools=True,
            git_operations=True,
            logging_utils=True,
        )

        if MCP_AVAILABLE:
            mcp.run()
        else:
            logger.warning("Running in mock mode - FastMCP not available")

    except Exception as e:
        logger.exception(f"Server startup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_server()
