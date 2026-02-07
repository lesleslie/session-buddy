#!/usr/bin/env python3
"""Serverless session management MCP tools.

This module provides tools for managing serverless sessions with external storage
following crackerjack architecture patterns.

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Any

from session_buddy.utils.error_management import _get_logger
from session_buddy.utils.instance_managers import (
    get_serverless_manager as resolve_serverless_manager,
)
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastmcp import FastMCP


# ============================================================================
# Service Resolution
# ============================================================================


async def _require_serverless_manager() -> Any:
    """Get serverless manager instance or raise error."""
    manager = await resolve_serverless_manager()
    if manager is None:
        msg = "Serverless mode not available. Install dependencies: pip install redis boto3"
        raise RuntimeError(msg)
    return manager


async def _execute_serverless_operation(
    operation_name: str, operation: Callable[[Any], Awaitable[str]]
) -> str:
    """Execute a serverless operation with error handling."""
    try:
        manager = await _require_serverless_manager()
        return await operation(manager)
    except RuntimeError as e:
        return f"❌ {e!s}"
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


# ============================================================================
# Session Operations
# ============================================================================


async def _create_serverless_session_operation(
    manager: Any,
    user_id: str,
    project_id: str,
    session_data: dict[str, Any] | None,
    ttl_hours: int,
) -> str:
    """Create a new serverless session with external storage."""
    session_id = await manager.create_session(
        user_id=user_id,
        project_id=project_id,
        session_data=session_data,
        ttl_hours=ttl_hours,
    )
    return f"✅ Created serverless session: {session_id}\n🕐 TTL: {ttl_hours} hours"


async def _create_serverless_session_impl(
    user_id: str,
    project_id: str,
    session_data: dict[str, Any] | None = None,
    ttl_hours: int = 24,
) -> str:
    """Create a new serverless session with external storage."""

    async def operation_wrapper(manager: Any) -> str:
        return await _create_serverless_session_operation(
            manager, user_id, project_id, session_data, ttl_hours
        )

    return await _execute_serverless_operation(
        "Create serverless session",
        operation_wrapper,
    )


async def _get_serverless_session_operation(manager: Any, session_id: str) -> str:
    """Get serverless session state."""
    session = await manager.get_session(session_id)

    if not session:
        return f"❌ Session not found: {session_id}"

    lines = [
        f"📦 Serverless Session: {session_id}",
        "",
        f"👤 User ID: {session['user_id']}",
        f"📁 Project ID: {session['project_id']}",
        f"📅 Created: {session['created_at']}",
        f"⏱️ Expires: {session['expires_at']}",
        "",
        "📊 Session Data:",
    ]

    data = session.get("session_data", {})
    for key, value in data.items():
        lines.append(f"   • {key}: {value}")

    return "\n".join(lines)


async def _get_serverless_session_impl(session_id: str) -> str:
    """Get serverless session state."""

    async def operation_wrapper(manager: Any) -> str:
        return await _get_serverless_session_operation(manager, session_id)

    return await _execute_serverless_operation(
        "Get serverless session",
        operation_wrapper,
    )


async def _update_serverless_session_operation(
    manager: Any,
    session_id: str,
    session_data: dict[str, Any],
    extend_ttl_hours: int | None,
) -> str:
    """Update serverless session data."""
    success = await manager.update_session(
        session_id=session_id,
        session_data=session_data,
        extend_ttl_hours=extend_ttl_hours,
    )

    if not success:
        return f"❌ Session not found: {session_id}"

    lines = [f"✅ Updated session: {session_id}"]
    if extend_ttl_hours:
        lines.append(f"⏱️ Extended TTL by {extend_ttl_hours} hours")
    return "\n".join(lines)


async def _update_serverless_session_impl(
    session_id: str,
    session_data: dict[str, Any],
    extend_ttl_hours: int | None = None,
) -> str:
    """Update serverless session data."""

    async def operation_wrapper(manager: Any) -> str:
        return await _update_serverless_session_operation(
            manager, session_id, session_data, extend_ttl_hours
        )

    return await _execute_serverless_operation(
        "Update serverless session",
        operation_wrapper,
    )


async def _delete_serverless_session_operation(manager: Any, session_id: str) -> str:
    """Delete a serverless session."""
    success = await manager.delete_session(session_id)

    if not success:
        return f"❌ Session not found: {session_id}"

    return f"✅ Deleted session: {session_id}"


async def _delete_serverless_session_impl(session_id: str) -> str:
    """Delete a serverless session."""

    async def operation_wrapper(manager: Any) -> str:
        return await _delete_serverless_session_operation(manager, session_id)

    return await _execute_serverless_operation(
        "Delete serverless session",
        operation_wrapper,
    )


# ============================================================================
# List and Cleanup Operations
# ============================================================================


async def _list_serverless_sessions_operation(
    manager: Any,
    user_id: str | None,
    project_id: str | None,
    include_expired: bool,
) -> str:
    """List serverless sessions with optional filtering."""
    sessions = await manager.list_sessions(
        user_id=user_id,
        project_id=project_id,
        include_expired=include_expired,
    )

    if not sessions:
        filters = []
        if user_id:
            filters.append(f"user_id={user_id}")
        if project_id:
            filters.append(f"project_id={project_id}")
        filter_str = f" ({', '.join(filters)})" if filters else ""
        return f"🔍 No sessions found{filter_str}"

    lines = [
        f"📦 Found {len(sessions)} serverless session(s):",
        "",
    ]

    for session in sessions:
        lines.extend(
            [
                f"• Session ID: {session['session_id']}",
                f"  User: {session['user_id']}",
                f"  Project: {session['project_id']}",
                f"  Expires: {session['expires_at']}",
                "",
            ]
        )

    return "\n".join(lines)


async def _list_serverless_sessions_impl(
    user_id: str | None = None,
    project_id: str | None = None,
    include_expired: bool = False,
) -> str:
    """List serverless sessions with optional filtering."""

    async def operation_wrapper(manager: Any) -> str:
        return await _list_serverless_sessions_operation(
            manager, user_id, project_id, include_expired
        )

    return await _execute_serverless_operation(
        "List serverless sessions",
        operation_wrapper,
    )


async def _cleanup_serverless_sessions_operation(manager: Any) -> str:
    """Clean up expired serverless sessions."""
    deleted_count = await manager.cleanup_expired_sessions()
    return f"✅ Cleaned up {deleted_count} expired session(s)"


async def _cleanup_serverless_sessions_impl() -> str:
    """Clean up expired serverless sessions."""
    return await _execute_serverless_operation(
        "Cleanup serverless sessions",
        _cleanup_serverless_sessions_operation,
    )


# ============================================================================
# Storage Testing and Configuration
# ============================================================================


def _format_storage_test_results(results: dict[str, Any]) -> list[str]:
    """Format storage backend test results."""
    lines = [
        "🧪 Storage Backend Test Results:",
        "",
    ]

    for backend, result in results.items():
        status = "✅" if result["available"] else "❌"
        lines.append(f"{status} {backend.upper()}:")

        if result["available"]:
            lines.extend(
                (
                    f"   Latency: {result.get('latency_ms', 'N/A')} ms",
                    f"   Status: {result.get('status', 'OK')}",
                )
            )
        else:
            lines.append(f"   Error: {result.get('error', 'Unknown')}")

        lines.append("")

    return lines


async def _test_serverless_storage_operation(manager: Any) -> str:
    """Test all configured storage backends."""
    results = await manager.test_storage_backends()

    lines = _format_storage_test_results(results)

    # Add recommendation
    available = [name for name, res in results.items() if res["available"]]
    if available:
        fastest = min(
            [
                (name, res["latency_ms"])
                for name, res in results.items()
                if res["available"]
            ],
            key=operator.itemgetter(1),
        )
        lines.append(f"💡 Recommended: {fastest[0].upper()} (lowest latency)")
    else:
        lines.append("⚠️ No storage backends available")

    return "\n".join(lines)


async def _test_serverless_storage_impl() -> str:
    """Test all configured storage backends."""
    return await _execute_serverless_operation(
        "Test serverless storage",
        _test_serverless_storage_operation,
    )


async def _configure_serverless_storage_operation(
    manager: Any,
    backend: str,
    config: dict[str, Any],
) -> str:
    """Configure storage backend for serverless sessions."""
    success = await manager.configure_storage(backend=backend, config=config)

    if not success:
        return f"❌ Failed to configure {backend} storage"

    return "\n".join(
        [
            f"✅ Configured {backend.upper()} storage backend",
            "",
            "⚙️ Configuration:",
            *[f"   • {key}: {value}" for key, value in config.items()],
        ]
    )


async def _configure_serverless_storage_impl(
    backend: str,
    config: dict[str, Any],
) -> str:
    """Configure storage backend for serverless sessions."""

    async def operation_wrapper(manager: Any) -> str:
        return await _configure_serverless_storage_operation(manager, backend, config)

    return await _execute_serverless_operation(
        "Configure serverless storage",
        operation_wrapper,
    )


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_serverless_tools(mcp: FastMCP) -> None:
    """Register all serverless session management tools."""

    @mcp.tool()  # type: ignore[misc]
    async def create_serverless_session(
        user_id: str,
        project_id: str,
        session_data: dict[str, Any] | None = None,
        ttl_hours: int = 24,
    ) -> str:
        """Create a new serverless session with external storage."""
        return await _create_serverless_session_impl(
            user_id, project_id, session_data, ttl_hours
        )

    @mcp.tool()  # type: ignore[misc]
    async def get_serverless_session(session_id: str) -> str:
        """Get serverless session state from external storage."""
        return await _get_serverless_session_impl(session_id)

    @mcp.tool()  # type: ignore[misc]
    async def update_serverless_session(
        session_id: str,
        session_data: dict[str, Any],
        extend_ttl_hours: int | None = None,
    ) -> str:
        """Update serverless session data and optionally extend TTL."""
        return await _update_serverless_session_impl(
            session_id, session_data, extend_ttl_hours
        )

    @mcp.tool()  # type: ignore[misc]
    async def delete_serverless_session(session_id: str) -> str:
        """Delete a serverless session from external storage."""
        return await _delete_serverless_session_impl(session_id)

    @mcp.tool()  # type: ignore[misc]
    async def list_serverless_sessions(
        user_id: str | None = None,
        project_id: str | None = None,
        include_expired: bool = False,
    ) -> str:
        """List serverless sessions with optional filtering."""
        return await _list_serverless_sessions_impl(
            user_id, project_id, include_expired
        )

    @mcp.tool()  # type: ignore[misc]
    async def cleanup_serverless_sessions() -> str:
        """Clean up expired serverless sessions from storage."""
        return await _cleanup_serverless_sessions_impl()

    @mcp.tool()  # type: ignore[misc]
    async def test_serverless_storage() -> str:
        """Test all configured storage backends (Redis, S3, local)."""
        return await _test_serverless_storage_impl()

    @mcp.tool()  # type: ignore[misc]
    async def configure_serverless_storage(
        backend: str,
        config: dict[str, Any],
    ) -> str:
        """Configure storage backend for serverless sessions."""
        return await _configure_serverless_storage_impl(backend, config)
