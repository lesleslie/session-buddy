#!/usr/bin/env python3
"""Admin shell session tracking MCP tools.

This module provides MCP tools for tracking admin shell session lifecycle events
from Mahavishnu, Session-Buddy, Oneiric, and other admin shells.

Event Flow:
    1. Admin shell starts → emits SessionStartEvent
    2. track_session_start MCP tool receives event → validates with Pydantic
    3. SessionTracker handles event → creates session record
    4. Returns SessionStartResult with session_id
    5. Admin shell exits → emits SessionEndEvent
    6. track_session_end MCP tool receives event → validates with Pydantic
    7. SessionTracker handles event → updates session record
    8. Returns SessionEndResult with status

Authentication:
    Both tools require JWT authentication via @require_auth() decorator when
    SESSION_BUDDY_SECRET environment variable is set.

Example:
    >>> from fastmcp import FastMCP
    >>> from session_buddy.mcp.tools.session.admin_shell_tracking_tools import register_admin_shell_tracking_tools
    >>>
    >>> mcp_server = FastMCP("session-buddy")
    >>> register_admin_shell_tracking_tools(mcp_server)
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from session_buddy.di import get_sync_typed
from session_buddy.di.container import depends

if TYPE_CHECKING:
    from fastmcp import FastMCP

from session_buddy.core import SessionLifecycleManager
from session_buddy.mcp.auth import require_auth
from session_buddy.mcp.event_models import (
    EnvironmentInfo,
    SessionEndEvent,
    SessionEndResult,
    SessionStartEvent,
    SessionStartResult,
    UserInfo,
)
from session_buddy.mcp.session_tracker import SessionTracker

# ============================================================================
# Logger
# ============================================================================


def get_logger() -> logging.Logger:
    """Get the logger instance for admin shell tracking tools."""
    return logging.getLogger(__name__)


# ============================================================================
# Service Resolution
# ============================================================================


def _get_session_manager() -> SessionLifecycleManager:
    """Get or create SessionLifecycleManager instance.

    Note:
        Uses the Oneiric-backed service container for singleton resolution.

    Returns:
        SessionLifecycleManager instance

    Example:
        >>> mgr = _get_session_manager()
        >>> isinstance(mgr, SessionLifecycleManager)
        True
    """
    with suppress(Exception):
        manager = get_sync_typed(SessionLifecycleManager)  # type: ignore[no-any-return]
        if isinstance(manager, SessionLifecycleManager):
            return manager

    manager = SessionLifecycleManager()
    depends.set(SessionLifecycleManager, manager)
    return manager


def _get_session_tracker() -> SessionTracker:
    """Get or create SessionTracker instance.

    Note:
        Uses the Oneiric-backed service container for singleton resolution.

    Returns:
        SessionTracker instance

    Example:
        >>> tracker = _get_session_tracker()
        >>> isinstance(tracker, SessionTracker)
        True
    """
    with suppress(Exception):
        # Try to get from container if already registered
        from session_buddy.di import depends

        tracker = depends.get(SessionTracker, None)
        if tracker is not None:
            return tracker

    # Create new tracker with session manager
    session_manager = _get_session_manager()
    tracker = SessionTracker(session_manager, logger=get_logger())
    depends.set(SessionTracker, tracker)
    return tracker


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_admin_shell_tracking_tools(mcp_server: FastMCP) -> None:
    """Register admin shell session tracking tools with the MCP server.

    This function registers two MCP tools:
    - track_session_start: Track admin shell session start events
    - track_session_end: Track admin shell session end events

    Both tools require JWT authentication when SESSION_BUDDY_SECRET is set.

    Args:
        mcp_server: FastMCP server instance

    Example:
        >>> from fastmcp import FastMCP
        >>> from session_buddy.mcp.tools.session.admin_shell_tracking_tools import register_admin_shell_tracking_tools
        >>>
        >>> mcp_server = FastMCP("session-buddy")
        >>> register_admin_shell_tracking_tools(mcp_server)
    """

    @mcp_server.tool()
    @require_auth()
    async def track_session_start(
        event_version: str,
        event_id: str,
        event_type: str,
        component_name: str,
        shell_type: str,
        timestamp: str,
        pid: int,
        user: dict[str, str],
        hostname: str,
        environment: dict[str, str],
        metadata: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Record admin shell session start events with validation and auth."""
        logger = get_logger()
        tracker = _get_session_tracker()

        try:
            # Build SessionStartEvent from parameters
            # Pydantic will validate all fields
            event = SessionStartEvent(
                event_version=event_version,
                event_id=event_id,
                event_type=event_type,
                component_name=component_name,
                shell_type=shell_type,
                timestamp=timestamp,
                pid=pid,
                user=UserInfo(**user),
                hostname=hostname,
                environment=EnvironmentInfo(**environment),
                metadata=metadata or {},
            )

            # Handle event via SessionTracker
            result = await tracker.handle_session_start(event)

            # Log tracking event
            logger.info(
                "Session start tracked: session_id=%s, component=%s, shell_type=%s, pid=%d, status=%s",
                result.session_id,
                component_name,
                shell_type,
                pid,
                result.status,
            )

            # Return as dict for JSON serialization
            return result.model_dump()

        except Exception as e:
            error_msg = f"Session start tracking failed: {str(e)}"
            logger.exception(
                "Session start tracking exception: component=%s, shell_type=%s, pid=%d, error=%s",
                component_name,
                shell_type,
                pid,
                str(e),
            )
            # Return error result
            return SessionStartResult(
                session_id=None,
                status="error",
                error=error_msg,
            ).model_dump()

    @mcp_server.tool()
    @require_auth()
    async def track_session_end(
        session_id: str,
        timestamp: str,
        event_type: str = "session_end",
        metadata: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Track admin shell session end event."""
        logger = get_logger()
        tracker = _get_session_tracker()

        try:
            # Build SessionEndEvent from parameters
            # Pydantic will validate all fields
            event = SessionEndEvent(
                session_id=session_id,
                timestamp=timestamp,
                event_type=event_type,
                metadata=metadata or {},
            )

            # Handle event via SessionTracker
            result = await tracker.handle_session_end(event)

            # Log tracking event
            logger.info(
                "Session end tracked: session_id=%s, status=%s",
                session_id,
                result.status,
            )

            # Return as dict for JSON serialization
            return result.model_dump()

        except Exception as e:
            error_msg = f"Session end tracking failed: {str(e)}"
            logger.exception(
                "Session end tracking exception: session_id=%s, error=%s",
                session_id,
                str(e),
            )
            # Return error result
            return SessionEndResult(
                session_id=session_id,
                status="error",
                error=error_msg,
            ).model_dump()


# ============================================================================
# Exports
# ============================================================================


__all__ = [
    "register_admin_shell_tracking_tools",
]
