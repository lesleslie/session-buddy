"""Session lifecycle event tracking for admin shells.

This module provides the SessionTracker class that wraps SessionLifecycleManager
to handle session lifecycle events from admin shells (Mahavishnu, Session-Buddy,
Oneiric, etc.) via MCP tools.

Event Flow:
    1. Admin shell starts → emits SessionStartEvent
    2. MCP tool receives event → validates with Pydantic
    3. SessionTracker.handle_session_start() creates session record
    4. Returns SessionStartResult with session_id
    5. Admin shell exits → emits SessionEndEvent
    6. MCP tool receives event → validates with Pydantic
    7. SessionTracker.handle_session_end() updates record
    8. Returns SessionEndResult with status

Example:
    >>> from session_buddy.core import SessionLifecycleManager
    >>> from session_buddy.mcp.session_tracker import SessionTracker
    >>> from session_buddy.mcp.event_models import SessionStartEvent
    >>>
    >>> lifecycle_mgr = SessionLifecycleManager()
    >>> tracker = SessionTracker(lifecycle_mgr)
    >>>
    >>> event = SessionStartEvent(
    ...     event_version="1.0",
    ...     event_id="550e8400-e29b-41d4-a716-446655440000",
    ...     component_name="mahavishnu",
    ...     shell_type="MahavishnuShell",
    ...     timestamp="2026-02-06T12:34:56.789Z",
    ...     pid=12345,
    ...     user=UserInfo(username="john", home="/home/john"),
    ...     hostname="server01",
    ...     environment=EnvironmentInfo(
    ...         python_version="3.13.0",
    ...         platform="Linux-6.5.0-x86_64",
    ...         cwd="/home/john/projects/mahavishnu"
    ...     )
    ... )
    >>> result = await tracker.handle_session_start(event)
    >>> print(result.session_id)
    sess_abc123
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from session_buddy.core import SessionLifecycleManager
from session_buddy.mcp.event_models import (
    SessionEndEvent,
    SessionEndResult,
    SessionStartEvent,
    SessionStartResult,
)

# Import metrics module with graceful degradation
try:
    from session_buddy.mcp.metrics import get_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


def get_session_tracker_logger() -> logging.Logger:
    """Get the session tracker logger instance.

    This function is used in tests for mocking purposes.
    """
    return logging.getLogger(__name__)


class SessionTracker:
    """Handles session lifecycle events from admin shells.

    This class wraps SessionLifecycleManager to provide a clean interface
    for handling session start and end events received via MCP tools from
    admin shells (Mahavishnu, Session-Buddy, Oneiric, etc.).

    The tracker validates all incoming events using Pydantic models and
    returns structured results for MCP tool responses.

    Attributes:
        session_manager: SessionLifecycleManager instance for session operations
        logger: Logger instance for tracking operations
        metrics: SessionMetrics instance for Prometheus metrics (optional)

    Example:
        >>> lifecycle_mgr = SessionLifecycleManager()
        >>> tracker = SessionTracker(lifecycle_mgr)
        >>> start_result = await tracker.handle_session_start(start_event)
        >>> end_result = await tracker.handle_session_end(end_event)
    """

    def __init__(
        self,
        session_manager: SessionLifecycleManager,
        logger: logging.Logger | None = None,
        enable_metrics: bool = True,
    ) -> None:
        """Initialize session tracker.

        Args:
            session_manager: SessionLifecycleManager instance for session operations
            logger: Optional logger instance (defaults to module logger)
            enable_metrics: Enable Prometheus metrics collection (default: True)

        Example:
            >>> from session_buddy.core import SessionLifecycleManager
            >>> mgr = SessionLifecycleManager()
            >>> tracker = SessionTracker(mgr, enable_metrics=True)
        """
        self.session_manager = session_manager
        self.logger = logger or get_session_tracker_logger()
        self.enable_metrics = enable_metrics and METRICS_AVAILABLE

        # Initialize metrics if available and enabled
        if self.enable_metrics:
            try:
                self.metrics = get_metrics()
                self.logger.debug("SessionMetrics initialized for SessionTracker")
            except Exception as e:
                self.logger.warning(
                    "Failed to initialize SessionMetrics, metrics disabled: %s",
                    str(e),
                )
                self.enable_metrics = False
                self.metrics = None
        else:
            self.metrics = None

    async def handle_session_start(
        self,
        event: SessionStartEvent,
    ) -> SessionStartResult:
        """Handle session start event from admin shell.

        This method validates the incoming event (Pydantic handles validation
        automatically), initializes a new session via SessionLifecycleManager,
        records Prometheus metrics, and returns a structured result.

        Args:
            event: Validated SessionStartEvent from admin shell

        Returns:
            SessionStartResult with session_id if successful, error details if failed

        Example:
            >>> event = SessionStartEvent(
            ...     event_version="1.0",
            ...     event_id="550e8400-e29b-41d4-a716-446655440000",
            ...     component_name="mahavishnu",
            ...     shell_type="MahavishnuShell",
            ...     timestamp="2026-02-06T12:34:56.789Z",
            ...     pid=12345,
            ...     user=UserInfo(username="john", home="/home/john"),
            ...     hostname="server01",
            ...     environment=EnvironmentInfo(
            ...         python_version="3.13.0",
            ...         platform="Linux-6.5.0-x86_64",
            ...         cwd="/home/john/projects/mahavishnu"
            ...     )
            ... )
            >>> result = await tracker.handle_session_start(event)
            >>> assert result.status == "tracked"
            >>> assert result.session_id is not None
        """
        start_time = time.time()

        try:
            # Extract working directory from event
            working_directory = event.environment.cwd

            # Initialize session via lifecycle manager
            init_result = await self.session_manager.initialize_session(
                working_directory=working_directory,
            )

            # Check if initialization succeeded
            if not init_result.get("success", False):
                error_msg = init_result.get("error", "Unknown initialization error")

                # Record metrics for failed session start
                if self.enable_metrics and self.metrics:
                    duration = time.time() - start_time
                    try:
                        self.metrics.record_session_start(
                            component_name=event.component_name,
                            shell_type=event.shell_type,
                        )
                        self.metrics.record_session_end(
                            component_name=event.component_name,
                            status="error",
                            duration_seconds=duration,
                        )
                    except Exception as metrics_error:
                        self.logger.warning(
                            "Failed to record metrics for failed session start: %s",
                            str(metrics_error),
                        )

                self.logger.error(
                    "Session start failed: %s, component=%s, shell_type=%s, pid=%d",
                    error_msg,
                    event.component_name,
                    event.shell_type,
                    event.pid,
                )
                return SessionStartResult(
                    session_id=None,
                    status="error",
                    error=error_msg,
                )

            # Generate session ID from event data
            # Format: {component_name}-{timestamp_YYYYMMDD-HHMMSS}
            timestamp = datetime.fromisoformat(
                event.timestamp.replace("Z", "+00:00")
            ).strftime("%Y%m%d-%H%M%S")
            session_id = f"{event.component_name}-{timestamp}"

            # Record session start metrics
            if self.enable_metrics and self.metrics:
                try:
                    self.metrics.record_session_start(
                        component_name=event.component_name,
                        shell_type=event.shell_type,
                    )

                    # Record quality score metric if available
                    quality_score = init_result.get("quality_score")
                    if quality_score is not None:
                        self.metrics.set_session_quality_score(
                            component_name=event.component_name,
                            quality_score=float(quality_score),
                        )

                except Exception as metrics_error:
                    self.logger.warning(
                        "Failed to record session start metrics: %s",
                        str(metrics_error),
                    )

            self.logger.info(
                "Session started: session_id=%s, component=%s, shell_type=%s, pid=%d, user=%s, hostname=%s, cwd=%s",
                session_id,
                event.component_name,
                event.shell_type,
                event.pid,
                event.user.username,
                event.hostname,
                working_directory,
            )

            return SessionStartResult(
                session_id=session_id,
                status="tracked",
            )

        except Exception as e:
            error_msg = f"Session start failed: {str(e)}"

            # Record metrics for exception
            if self.enable_metrics and self.metrics:
                duration = time.time() - start_time
                try:
                    self.metrics.record_mcp_event_emit_failure(
                        component_name=event.component_name,
                        event_type="session_start",
                        error_type=type(e).__name__,
                        duration_seconds=duration,
                    )
                except Exception as metrics_error:
                    self.logger.warning(
                        "Failed to record exception metrics: %s",
                        str(metrics_error),
                    )

            self.logger.exception(
                "Session start exception: component=%s, shell_type=%s, pid=%d, error=%s",
                event.component_name,
                event.shell_type,
                event.pid,
                str(e),
            )
            return SessionStartResult(
                session_id=None,
                status="error",
                error=error_msg,
            )

    async def handle_session_end(
        self,
        event: SessionEndEvent,
    ) -> SessionEndResult:
        """Handle session end event from admin shell.

        This method validates the incoming event (Pydantic handles validation
        automatically), updates the session record via SessionLifecycleManager,
        records Prometheus metrics, and returns a structured result.

        Args:
            event: Validated SessionEndEvent from admin shell

        Returns:
            SessionEndResult with status (ended, error, or not_found)

        Example:
            >>> event = SessionEndEvent(
            ...     session_id="mahavishnu-20260206-123456",
            ...     timestamp="2026-02-06T13:45:67.890Z",
            ...     metadata={"exit_reason": "user_exit"}
            ... )
            >>> result = await tracker.handle_session_end(event)
            >>> assert result.status == "ended"
        """
        start_time = time.time()
        component_name = event.session_id.split("-")[0] if "-" in event.session_id else "unknown"

        try:
            # For now, we use SessionLifecycleManager.end_session()
            # which doesn't look up sessions by session_id
            # In the future, this should query a session database

            # Parse timestamp for logging
            # Parse timestamp for future duration calculation
            # End session via lifecycle manager
            # Note: This doesn't use the session_id yet, but generates its own
            end_result = await self.session_manager.end_session(
                working_directory=None,  # Uses current directory
            )

            # Check if session end succeeded
            if not end_result.get("success", False):
                error_msg = end_result.get("error", "Unknown session end error")

                # Record metrics for failed session end
                if self.enable_metrics and self.metrics:
                    duration = time.time() - start_time
                    try:
                        self.metrics.record_session_end(
                            component_name=component_name,
                            status="error",
                            duration_seconds=duration,
                        )
                    except Exception as metrics_error:
                        self.logger.warning(
                            "Failed to record metrics for failed session end: %s",
                            str(metrics_error),
                        )

                self.logger.error(
                    "Session end failed: session_id=%s, error=%s",
                    event.session_id,
                    error_msg,
                )
                return SessionEndResult(
                    session_id=event.session_id,
                    status="error",
                    error=error_msg,
                )

            # Calculate duration if we have quality score data
            duration = time.time() - start_time
            summary = end_result.get("summary", {})

            # Record session end metrics
            if self.enable_metrics and self.metrics:
                try:
                    self.metrics.record_session_end(
                        component_name=component_name,
                        status="success",
                        duration_seconds=duration,
                    )

                    # Update quality score metric
                    quality_score = summary.get("final_quality_score")
                    if quality_score is not None:
                        self.metrics.set_session_quality_score(
                            component_name=component_name,
                            quality_score=float(quality_score),
                        )

                except Exception as metrics_error:
                    self.logger.warning(
                        "Failed to record session end metrics: %s",
                        str(metrics_error),
                    )

            self.logger.info(
                "Session ended: session_id=%s, timestamp=%s",
                event.session_id,
                event.timestamp,
            )

            # Extract summary data if available
            if summary:
                self.logger.debug(
                    "Session summary: project=%s, quality_score=%d, working_dir=%s",
                    summary.get("project"),
                    summary.get("final_quality_score", 0),
                    summary.get("working_directory"),
                )

            return SessionEndResult(
                session_id=event.session_id,
                status="ended",
            )

        except Exception as e:
            error_msg = f"Session end failed: {str(e)}"

            # Record metrics for exception
            if self.enable_metrics and self.metrics:
                duration = time.time() - start_time
                try:
                    self.metrics.record_mcp_event_emit_failure(
                        component_name=component_name,
                        event_type="session_end",
                        error_type=type(e).__name__,
                        duration_seconds=duration,
                    )
                except Exception as metrics_error:
                    self.logger.warning(
                        "Failed to record exception metrics: %s",
                        str(metrics_error),
                    )

            self.logger.exception(
                "Session end exception: session_id=%s, error=%s",
                event.session_id,
                str(e),
            )
            return SessionEndResult(
                session_id=event.session_id,
                status="error",
                error=error_msg,
            )
