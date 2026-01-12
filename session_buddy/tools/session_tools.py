#!/usr/bin/env python3
"""Session management MCP tools.

This module provides tools for managing Claude session lifecycle including
initialization, checkpoints, and cleanup.

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from session_buddy.di import get_sync_typed
from session_buddy.di.container import depends

if TYPE_CHECKING:
    from fastmcp import FastMCP

from session_buddy.core import SessionLifecycleManager
from session_buddy.utils.error_handlers import _get_logger


@dataclass
class SessionOutputBuilder:
    """Centralized output formatting with consistent styling."""

    sections: list[str] = field(default_factory=list)

    def add_header(self, title: str, separator_char: str = "=") -> None:
        """Add formatted header."""
        separator = separator_char * len(title)
        self.sections.extend([title, separator])

    def add_section(self, title: str, items: list[str]) -> None:
        """Add formatted section with items."""
        if title:
            self.sections.append(f"\n{title}:")
        self.sections.extend(items)

    def add_status_item(self, name: str, status: bool, value: str = "") -> None:
        """Add status indicator item."""
        icon = "✅" if status else "❌"
        display = f"   • {name}: {icon}"
        if value:
            display += f" {value}"
        self.sections.append(display)

    def add_simple_item(self, item: str) -> None:
        """Add simple item."""
        self.sections.append(item)

    def build(self) -> str:
        """Build final output string."""
        return "\n".join(self.sections)


@dataclass
class SessionSetupResults:
    """Results from session setup operations."""

    uv_setup: list[str] = field(default_factory=list)
    shortcuts_result: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


# ============================================================================
# Service Resolution
# ============================================================================


def _get_session_manager() -> SessionLifecycleManager:
    """Get or create SessionLifecycleManager instance.

    Note:
        Uses the Oneiric-backed service container for singleton resolution.

    """
    with suppress(Exception):
        manager = get_sync_typed(SessionLifecycleManager)  # type: ignore[no-any-return]
        if isinstance(manager, SessionLifecycleManager):
            return manager

    manager = SessionLifecycleManager()
    depends.set(SessionLifecycleManager, manager)
    return manager


# ============================================================================
# Session Shortcuts Management
# ============================================================================


def _create_session_shortcuts() -> dict[str, Any]:
    """Create Claude Code slash command shortcuts for session management.

    Creates /start, /checkpoint, and /end shortcuts in ~/.claude/commands/
    that map to session-mgmt MCP tools.

    Returns:
        Dict with 'created' bool, 'existed' bool, and 'shortcuts' list

    """
    claude_home = Path.home() / ".claude"
    commands_dir = claude_home / "commands"

    # Create commands directory if it doesn't exist
    commands_dir.mkdir(parents=True, exist_ok=True)

    shortcuts = {
        "start": {
            "file": "start.md",
            "content": """---
description: Start session management for current project
---

Please use the `mcp__session-buddy__start` tool to initialize session management for the current project.

This will:
1. Set up session tracking for the git repository
2. Initialize conversation memory and context
3. Prepare the project for enhanced Claude Code workflows
4. Install UV dependencies and automation tools
5. Create session management slash command shortcuts
""",
        },
        "checkpoint": {
            "file": "checkpoint.md",
            "content": """---
argument-hint: [checkpoint-name]
description: Create a session checkpoint with progress summary
---

Please use the `mcp__session-buddy__checkpoint` tool to create a session checkpoint.

This command will:
1. Create a checkpoint of the current development session
2. Analyze code quality and calculate quality scores
3. Summarize progress made so far
4. Document any pending tasks or context
5. Prepare for seamless session resumption

The tool will analyze the working directory and provide comprehensive quality metrics.
""",
        },
        "end": {
            "file": "end.md",
            "content": """---
description: End current session with cleanup and summary
---

Please use the `mcp__session-buddy__end` tool to gracefully end the current session.

This will:
1. Create a final checkpoint of all work completed
2. Generate session summary and insights
3. Clean up temporary resources
4. Prepare handoff documentation for next session
5. Store final quality metrics and learning data
""",
        },
    }

    created_shortcuts = []
    existing_shortcuts = []

    for shortcut_name, shortcut_data in shortcuts.items():
        shortcut_path = commands_dir / shortcut_data["file"]

        if shortcut_path.exists():
            existing_shortcuts.append(shortcut_name)
        else:
            try:
                shortcut_path.write_text(shortcut_data["content"])
                created_shortcuts.append(shortcut_name)
                _get_logger().info(f"Created slash command shortcut: /{shortcut_name}")
            except Exception as e:
                _get_logger().exception(
                    f"Failed to create shortcut /{shortcut_name}: {e}",
                )

    return {
        "created": bool(created_shortcuts),
        "existed": bool(existing_shortcuts) and not created_shortcuts,
        "shortcuts": created_shortcuts or existing_shortcuts,
    }


# ============================================================================
# Working Directory Detection
# ============================================================================


def _check_environment_variables() -> str | None:
    """Check for Claude Code environment variables."""
    import os

    for env_var in ("CLAUDE_WORKING_DIR", "CLIENT_PWD", "CLAUDE_PROJECT_DIR"):
        if env_var in os.environ:
            client_dir = os.environ[env_var]
            if client_dir and Path(client_dir).exists():
                return client_dir
    return None


def _check_working_dir_file() -> str | None:
    """Check for the temporary file used by Claude's auto-start scripts."""
    import tempfile

    working_dir_file = Path(tempfile.gettempdir()) / "claude-git-working-dir"
    if working_dir_file.exists():
        with suppress(OSError, PermissionError, ValueError, UnicodeDecodeError):
            stored_dir = working_dir_file.read_text().strip()
            # Only use if it's NOT the session-mgmt-mcp server directory
            if (
                stored_dir
                and Path(stored_dir).exists()
                and not stored_dir.endswith("session-mgmt-mcp")
            ):
                return stored_dir
    return None


def _check_parent_process_cwd() -> str | None:
    """Check parent process working directory (advanced)."""
    with suppress(ImportError, Exception):
        import psutil

        parent_process = psutil.Process().parent()
        if parent_process:
            parent_cwd = parent_process.cwd()
            # Only use if it's a different directory and exists
            if (
                parent_cwd
                and Path(parent_cwd).exists()
                and parent_cwd != str(Path.cwd())
                and not parent_cwd.endswith("session-mgmt-mcp")
            ):
                return parent_cwd
    return None


def _is_git_repository(repo_path: Path) -> bool:
    """Check if a path is a git repository."""
    return repo_path.is_dir() and (repo_path / ".git").exists()


def _safe_get_mtime(repo_path: Path) -> float | None:
    """Safely get modification time of a repository."""
    try:
        return repo_path.stat().st_mtime
    except Exception:
        return None


def _collect_git_repos(projects_path: Path) -> list[tuple[float, str]]:
    """Collect git repositories with modification times from a directory."""
    git_repos: list[tuple[float, str]] = []
    for repo_path in projects_path.iterdir():
        if _is_git_repository(repo_path):
            mtime = _safe_get_mtime(repo_path)
            if mtime is not None:
                git_repos.append((mtime, str(repo_path)))
    return git_repos


def _get_most_recent_client_repo(git_repos: list[tuple[float, str]]) -> str | None:
    """Get most recent repository excluding the server itself."""
    git_repos.sort(reverse=True)
    for _mtime, repo_path_str in git_repos:
        if not repo_path_str.endswith("session-mgmt-mcp"):
            return repo_path_str
    return None


def _find_recent_git_repository() -> str | None:
    """Look for recent git repositories in common project directories."""
    for projects_dir in ("/Users/les/Projects", str(Path.home() / "Projects")):
        projects_path = Path(projects_dir)
        if not projects_path.exists():
            continue

        git_repos = _collect_git_repos(projects_path)
        if git_repos:
            if repo := _get_most_recent_client_repo(git_repos):
                return repo

    return None


def _get_client_working_directory() -> str | None:
    """Auto-detect the client's working directory using multiple detection methods."""
    # Method 1: Check for Claude Code environment variables
    if client_dir := _check_environment_variables():
        return client_dir

    # Method 2: Check for the temporary file used by Claude's auto-start scripts
    if client_dir := _check_working_dir_file():
        return client_dir

    # Method 3: Check parent process working directory (advanced)
    if client_dir := _check_parent_process_cwd():
        return client_dir

    # Method 4: Look for recent git repositories in common project directories
    if client_dir := _find_recent_git_repository():
        return client_dir

    return None


# ============================================================================
# Environment Setup Operations
# ============================================================================


async def _perform_environment_setup(result: dict[str, Any]) -> SessionSetupResults:
    """Perform all environment setup tasks. Target complexity: ≤5."""
    working_dir = Path(result["working_directory"])

    uv_setup = _setup_uv_dependencies(working_dir)
    shortcuts_result = _create_session_shortcuts()
    recommendations = result["quality_data"].get("recommendations", [])

    return SessionSetupResults(
        uv_setup=uv_setup,
        shortcuts_result=shortcuts_result,
        recommendations=recommendations,
    )


def _setup_uv_dependencies(current_dir: Path) -> list[str]:
    """Set up UV dependencies and requirements.txt generation."""
    output = []
    output.extend(("\n" + "=" * 50, "📦 UV Package Management Setup", "=" * 50))

    # Check if uv is available
    uv_available = shutil.which("uv") is not None
    if not uv_available:
        output.extend(
            (
                "⚠️ UV not found in PATH",
                "💡 Install UV: curl -LsSf https://astral.sh/uv/install.sh | sh",
            )
        )
        return output

    # Check for pyproject.toml
    pyproject_path = current_dir / "pyproject.toml"
    if pyproject_path.exists():
        output.append("✅ Found pyproject.toml - UV project detected")

        # Run uv sync if dependencies need updating
        try:
            sync_result = subprocess.run(
                ["uv", "sync"],
                check=False,
                cwd=current_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if sync_result.returncode == 0:
                output.append("✅ UV dependencies synchronized")
            else:
                output.append(f"⚠️ UV sync had issues: {sync_result.stderr}")
        except subprocess.TimeoutExpired:
            output.append(
                "⚠️ UV sync timed out - dependencies may need manual attention",
            )
        except Exception as e:
            output.append(f"⚠️ UV sync error: {e}")
    else:
        output.extend(
            (
                "ℹ️ No pyproject.toml found",
                "💡 Consider running 'uv init' to create a new UV project",
            )
        )

    return output


# ============================================================================
# Output Formatting Helpers
# ============================================================================


def _add_session_info_to_output(
    output_builder: SessionOutputBuilder,
    result: dict[str, Any],
) -> None:
    """Add session information to output. Target complexity: ≤5."""
    output_builder.add_simple_item(f"📁 Current project: {result['project']}")
    output_builder.add_simple_item(
        f"📂 Working directory: {result['working_directory']}",
    )
    output_builder.add_simple_item(f"🏠 Claude directory: {result['claude_directory']}")
    output_builder.add_simple_item(
        f"📊 Initial quality score: {result['quality_score']}/100",
    )

    # Add project context info
    context = result["project_context"]
    context_items = sum(1 for detected in context.values() if detected)
    output_builder.add_simple_item(
        f"🎯 Project context: {context_items}/{len(context)} indicators detected",
    )


def _add_environment_info_to_output(
    output_builder: SessionOutputBuilder,
    setup_results: SessionSetupResults,
) -> None:
    """Add environment setup info to output. Target complexity: ≤5."""
    # Add UV setup
    output_builder.sections.extend(setup_results.uv_setup)

    # Add recommendations
    if setup_results.recommendations:
        output_builder.add_section(
            "💡 Setup recommendations",
            [f"   • {rec}" for rec in setup_results.recommendations[:3]],
        )

    # Add shortcuts
    shortcuts = setup_results.shortcuts_result
    if shortcuts.get("created"):
        output_builder.add_section(
            "🔧 Created session management shortcuts",
            [f"   • /{shortcut}" for shortcut in shortcuts["shortcuts"]],
        )
    elif shortcuts.get("existed"):
        output_builder.add_simple_item("\n✅ Session shortcuts already exist")


def _add_project_section_to_output(
    output_builder: SessionOutputBuilder,
    result: dict[str, Any],
) -> None:
    """Add project information to output. Target complexity: ≤3."""
    output_builder.add_simple_item(f"📁 Project: {result['project']}")
    output_builder.add_simple_item(
        f"📂 Working directory: {result['working_directory']}",
    )
    output_builder.add_simple_item(f"📊 Quality score: {result['quality_score']}/100")


def _add_quality_section_to_output(
    output_builder: SessionOutputBuilder,
    breakdown: dict[str, Any],
) -> None:
    """Add quality breakdown to output. Target complexity: ≤5."""
    quality_items = [
        f"   • Code quality: {breakdown['code_quality']:.1f}/40",
        f"   • Project health: {breakdown['project_health']:.1f}/30",
        f"   • Dev velocity: {breakdown['dev_velocity']:.1f}/20",
        f"   • Security: {breakdown['security']:.1f}/10",
    ]
    output_builder.add_section("📈 Quality breakdown", quality_items)


def _add_health_section_to_output(
    output_builder: SessionOutputBuilder,
    health: dict[str, Any],
) -> None:
    """Add system health to output. Target complexity: ≤5."""
    output_builder.add_section("🏥 System health", [])
    output_builder.add_status_item("UV package manager", health["uv_available"])
    output_builder.add_status_item("Git repository", health["git_repository"])
    output_builder.add_status_item("Claude directory", health["claude_directory"])


def _add_project_context_to_output(
    output_builder: SessionOutputBuilder,
    context: dict[str, Any],
) -> None:
    """Add project context to output. Target complexity: ≤5."""
    context_items = sum(1 for detected in context.values() if detected)
    output_builder.add_simple_item(
        f"\n🎯 Project context: {context_items}/{len(context)} indicators",
    )

    key_indicators = [
        ("pyproject.toml", context.get("has_pyproject_toml", False)),
        ("Git repository", context.get("has_git_repo", False)),
        ("Test suite", context.get("has_tests", False)),
        ("Documentation", context.get("has_docs", False)),
    ]

    for name, detected in key_indicators:
        output_builder.add_status_item(name, detected)


# ============================================================================
# Checkpoint-Specific Helpers
# ============================================================================


async def _handle_auto_store_reflection(
    result: dict[str, Any],
    output: list[str],
) -> None:
    """Handle selective auto-store reflection logic."""
    auto_store_decision = result.get("auto_store_decision")
    if not auto_store_decision:
        return

    if auto_store_decision.should_store:
        from session_buddy.reflection_tools import get_reflection_database
        from session_buddy.utils.reflection_utils import generate_auto_store_tags

        try:
            db = await get_reflection_database()

            # Create meaningful checkpoint summary
            checkpoint_content = f"Quality score: {result['quality_score']}/100. "
            if auto_store_decision.metadata.get("delta"):
                delta = auto_store_decision.metadata["delta"]
                direction = (
                    "improved"
                    if auto_store_decision.reason.value == "quality_improvement"
                    else "changed"
                )
                checkpoint_content += f"Quality {direction} by {delta} points. "

            checkpoint_content += (
                f"Project: {_get_session_manager().current_project or 'unknown'}. "
            )
            checkpoint_content += f"Timestamp: {result['timestamp']}"

            # Generate semantic tags
            tags = generate_auto_store_tags(
                reason=auto_store_decision.reason,
                project=_get_session_manager().current_project,
                quality_score=result["quality_score"],
            )

            # Store the reflection
            await db.store_reflection(checkpoint_content, tags)
            output.append(f"\n{result['auto_store_summary']}")
        except Exception as e:
            _get_logger().exception(f"Failed to store checkpoint reflection: {e}")
            output.append(f"⚠️ Reflection storage failed: {e}")
    else:
        # Show why we skipped auto-store
        output.append(f"\n{result.get('auto_store_summary', '')}")


async def _handle_auto_compaction(output: list[str]) -> None:
    """Handle automatic compaction analysis and execution."""
    from session_buddy.server_optimized import (
        _execute_auto_compact,
        should_suggest_compact,
    )

    should_compact, reason = should_suggest_compact()
    output.extend(("\n🔄 Automatic Compaction Analysis", f"📊 {reason}"))

    if should_compact:
        output.append("\n🔄 Executing automatic compaction...")
        try:
            await _execute_auto_compact()
            output.append("✅ Context automatically optimized")
        except Exception as e:
            output.extend(
                (
                    f"⚠️ Auto-compact skipped: {e!s}",
                    "💡 Consider running /compact manually",
                )
            )
    else:
        output.append("✅ Context appears well-optimized for current session")


# ============================================================================
# End Session Formatting Helpers
# ============================================================================


def _format_successful_end(summary: dict[str, Any]) -> list[str]:
    """Format successful session end output."""
    output = [
        f"📁 Project: {summary['project']}",
        f"📊 Final quality score: {summary['final_quality_score']}/100",
        f"⏰ Session ended: {summary['session_end_time']}",
    ]

    output.extend(_format_recommendations(summary.get("recommendations", [])))
    output.extend(_format_session_summary(summary))

    output.extend(
        [
            "\n✅ Session ended successfully!",
            "💡 Use the session data to improve future development workflows.",
        ],
    )

    return output


def _format_recommendations(recommendations: list[str]) -> list[str]:
    """Format recommendations section."""
    if not recommendations:
        return []

    output = ["\n🎯 Final recommendations for future sessions:"]
    output.extend(f"   • {rec}" for rec in recommendations[:5])
    return output


def _format_session_summary(summary: dict[str, Any]) -> list[str]:
    """Format session summary section."""
    output = [
        "\n📝 Session Summary:",
        f"   • Working directory: {summary['working_directory']}",
        "   • Session data has been logged for future reference",
        "   • All temporary resources have been cleaned up",
    ]

    # Add handoff documentation info
    handoff_doc = summary.get("handoff_documentation")
    if handoff_doc:
        output.append(f"   • Handoff documentation: {handoff_doc}")

    return output


# ============================================================================
# Tool Implementations
# ============================================================================


async def _start_impl(working_directory: str | None = None) -> str:
    """Initialize session with comprehensive setup. Target complexity: ≤8."""
    output_builder = SessionOutputBuilder()
    output_builder.add_header("🚀 Claude Session Initialization via MCP Server")

    try:
        result = await _get_session_manager().initialize_session(working_directory)

        if result["success"]:
            _add_session_info_to_output(output_builder, result)
            setup_results = await _perform_environment_setup(result)
            _add_environment_info_to_output(output_builder, setup_results)
            output_builder.add_simple_item(
                "\n✅ Session initialization completed successfully!",
            )
        else:
            output_builder.add_simple_item(
                f"❌ Session initialization failed: {result['error']}",
            )

    except Exception as e:
        _get_logger().exception("Session initialization error: %s", str(e))
        output_builder.add_simple_item(
            f"❌ Unexpected error during initialization: {e}",
        )

    return output_builder.build()


async def _checkpoint_impl(working_directory: str | None = None) -> str:
    """Implementation for checkpoint tool."""
    # Auto-detect client working directory if not provided
    if not working_directory:
        working_directory = _get_client_working_directory()

    output = []
    output.extend(
        (
            f"🔍 Claude Session Checkpoint - {_get_session_manager().current_project or 'Current Project'}",
            "=" * 50,
        )
    )

    try:
        # Determine if this is a manual checkpoint (always true for explicit tool calls)
        result = await _get_session_manager().checkpoint_session(
            working_directory,
            is_manual=True,
        )

        if result["success"]:
            # Add quality assessment output
            output.extend(result["quality_output"])

            # Add git checkpoint output
            output.extend(result["git_output"])

            # Handle selective auto-store reflection
            try:
                await _handle_auto_store_reflection(result, output)
            except Exception as e:
                _get_logger().warning(
                    f"Auto-store reflection error (non-critical): {e}"
                )
                # Continue - this is not critical for checkpoint success

            # Auto-compact when needed
            try:
                await _handle_auto_compaction(output)
            except Exception as e:
                _get_logger().warning(f"Auto-compaction error (non-critical): {e}")
                output.append(f"\n⚠️ Auto-compaction skipped: {e!s}")

            output.extend(
                (
                    f"\n⏰ Checkpoint completed at: {result['timestamp']}",
                    "\n💡 This checkpoint includes intelligent conversation management and optimization.",
                )
            )
        else:
            output.append(f"❌ Checkpoint failed: {result['error']}")

    except Exception as e:
        _get_logger().exception("Checkpoint error: %s", str(e))
        output.append(f"❌ Unexpected checkpoint error: {e}")

    return "\n".join(output)


async def _end_impl(working_directory: str | None = None) -> str:
    """Implementation for end tool."""
    # Auto-detect client working directory if not provided
    if not working_directory:
        working_directory = _get_client_working_directory()

    output = [
        "🏁 Claude Session End - Cleanup and Handoff",
        "=" * 50,
    ]

    try:
        result = await _get_session_manager().end_session(working_directory)

        if result["success"]:
            output.extend(_format_successful_end(result["summary"]))
        else:
            output.append(f"❌ Session end failed: {result['error']}")

    except Exception as e:
        _get_logger().exception("Session end error: %s", str(e))
        output.append(f"❌ Unexpected error during session end: {e}")

    return "\n".join(output)


async def _status_impl(working_directory: str | None = None) -> str:
    """Get comprehensive session status. Target complexity: ≤8."""
    output_builder = SessionOutputBuilder()
    output_builder.add_header("📊 Claude Session Status Report")

    try:
        result = await _get_session_manager().get_session_status(working_directory)

        if result["success"]:
            _add_project_section_to_output(output_builder, result)
            _add_quality_section_to_output(output_builder, result["quality_breakdown"])
            _add_health_section_to_output(output_builder, result["system_health"])
            _add_project_context_to_output(output_builder, result["project_context"])

            # Recommendations
            recommendations = result["recommendations"]
            if recommendations:
                output_builder.add_section(
                    "💡 Recommendations",
                    [f"   • {rec}" for rec in recommendations[:3]],
                )

            output_builder.add_simple_item(
                f"\n⏰ Status generated: {result['timestamp']}",
            )

        else:
            output_builder.add_simple_item(f"❌ Status check failed: {result['error']}")

    except Exception as e:
        _get_logger().exception("Status check error: %s", str(e))
        output_builder.add_simple_item(f"❌ Unexpected error during status check: {e}")

    return output_builder.build()


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_session_tools(mcp_server: FastMCP) -> None:
    """Register all session management tools with the MCP server."""

    @mcp_server.tool()
    async def start(working_directory: str | None = None) -> str:
        """Initialize Claude session with comprehensive setup including UV dependencies and automation tools.

        Args:
            working_directory: Optional working directory override (defaults to PWD environment variable or current directory)

        """
        return await _start_impl(working_directory)

    @mcp_server.tool()
    async def checkpoint(working_directory: str | None = None) -> str:
        """Perform mid-session quality checkpoint with workflow analysis and optimization recommendations.

        Args:
            working_directory: Optional working directory override (defaults to PWD environment variable or current directory)

        """
        return await _checkpoint_impl(working_directory)

    @mcp_server.tool()
    async def end(working_directory: str | None = None) -> str:
        """End Claude session with cleanup, learning capture, and handoff file creation.

        Args:
            working_directory: Optional working directory override (defaults to PWD environment variable or current directory)

        """
        return await _end_impl(working_directory)

    @mcp_server.tool()
    async def status(working_directory: str | None = None) -> str:
        """Get current session status and project context information with health checks.

        Args:
            working_directory: Optional working directory override (defaults to PWD environment variable or current directory)

        """
        return await _status_impl(working_directory)

    @mcp_server.tool()
    async def health_check() -> str:
        """Simple health check that doesn't require database or session context."""
        import os
        import platform
        import time

        try:
            working_directory = str(Path.cwd())
        except FileNotFoundError:
            # Handle case where current working directory doesn't exist
            working_directory = "[Current directory unavailable]"

        health_info = {
            "server_status": "✅ Active",
            "timestamp": time.time(),
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "process_id": os.getpid(),
            "working_directory": working_directory,
        }

        return f"""🏥 MCP Server Health Check
================================
Server Status: {health_info["server_status"]}
Platform: {health_info["platform"]}
Python: {health_info["python_version"]}
Process ID: {health_info["process_id"]}
Working Directory: {health_info["working_directory"]}
Timestamp: {health_info["timestamp"]}

✅ MCP server is operational and responding to requests."""

    @mcp_server.tool()
    async def server_info() -> str:
        """Get basic server information without requiring session context."""
        import time

        try:
            # Check if we can access basic file system info
            home_dir = Path.home()

            try:
                current_dir = Path.cwd()
            except FileNotFoundError:
                # Handle case where current working directory doesn't exist
                current_dir = Path("[Current directory unavailable]")

            return f"""📊 Session-mgmt MCP Server Information
===========================================
🏠 Home Directory: {home_dir}
📁 Current Directory: {current_dir}
🕐 Server Time: {time.strftime("%Y-%m-%d %H:%M:%S")}
🔧 FastMCP Framework: Active
🌐 Transport: streamable-http
📡 Endpoint: /mcp

✅ Server is running and accessible."""

        except Exception as e:
            return f"⚠️ Server info error: {e!s}"

    @mcp_server.tool()
    async def ping() -> str:
        """Simple ping endpoint to test MCP connectivity."""
        return "🏓 Pong! MCP server is responding"
