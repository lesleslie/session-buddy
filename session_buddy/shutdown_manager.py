"""Graceful shutdown manager for session-mgmt-mcp.

Provides signal handling, cleanup task registration, and resource cleanup
for clean server shutdown.

Phase 10.2: Production Hardening - Graceful Shutdown
"""

from __future__ import annotations

import asyncio
import atexit
import signal
import typing as t
from contextlib import suppress
from dataclasses import dataclass

from session_buddy.utils.logging import get_session_logger


def _get_logger() -> t.Any:
    """Get logger with lazy initialization to avoid DI issues during import."""
    try:
        return get_session_logger()
    except Exception:  # noqa: BLE001 - logger probe: any DI/import failure must fall back to stdlib logger
        import logging

        return logging.getLogger(__name__)


@dataclass
class CleanupTask:
    """Represents a cleanup task to be executed during shutdown."""

    name: str
    """Human-readable name for the cleanup task."""

    callback: t.Callable[[], t.Awaitable[None] | None]
    """Cleanup function (sync or async)."""

    priority: int = 0
    """Priority for execution order (higher = earlier)."""

    timeout_seconds: float = 30.0
    """Maximum time allowed for cleanup task."""

    critical: bool = False
    """Whether failure of this task should stop other cleanups."""


@dataclass
class ShutdownStats:
    """Statistics about shutdown execution."""

    tasks_registered: int = 0
    """Total cleanup tasks registered."""

    tasks_executed: int = 0
    """Tasks successfully executed."""

    tasks_failed: int = 0
    """Tasks that failed during execution."""

    tasks_timeout: int = 0
    """Tasks that exceeded timeout."""

    total_duration_ms: float = 0.0
    """Total shutdown duration in milliseconds."""


class ShutdownManager:
    """Manages graceful shutdown with cleanup task coordination.

    Features:
        - Signal handler registration (SIGTERM, SIGINT, SIGQUIT)
        - Cleanup task registration with priorities
        - Async/sync cleanup task support
        - Timeout enforcement per task
        - Comprehensive error handling
        - Shutdown statistics tracking

    Example:
        >>> shutdown_mgr = ShutdownManager()
        >>>
        >>> # Register cleanup tasks
        >>> async def cleanup_database():
        ...     await db.close()
        >>>
        >>> shutdown_mgr.register_cleanup(
        ...     "database_cleanup", cleanup_database, priority=100
        ... )
        >>>
        >>> # Setup signal handlers
        >>> shutdown_mgr.setup_signal_handlers()
        >>>
        >>> # Cleanup happens automatically on shutdown

    """

    def __init__(self) -> None:
        """Initialize shutdown manager."""
        self._cleanup_tasks: list[CleanupTask] = []
        self._shutdown_initiated = False
        self._shutdown_lock = asyncio.Lock()
        self._original_handlers: dict[int, t.Any] = {}
        self._stats = ShutdownStats()

    def register_cleanup(
        self,
        name: str,
        callback: t.Callable[[], t.Awaitable[None] | None],
        priority: int = 0,
        timeout_seconds: float = 30.0,
        critical: bool = False,
    ) -> None:
        """Register a cleanup task to be executed during shutdown.

        Args:
            name: Human-readable name for logging
            callback: Cleanup function (async or sync)
            priority: Execution priority (higher = earlier), default 0
            timeout_seconds: Maximum execution time, default 30s
            critical: If True, failure stops other cleanups, default False

        Example:
            >>> async def close_database():
            ...     await db.close()
            >>>
            >>> shutdown_mgr.register_cleanup(
            ...     "database", close_database, priority=100, critical=True
            ... )

        """
        task = CleanupTask(
            name=name,
            callback=callback,
            priority=priority,
            timeout_seconds=timeout_seconds,
            critical=critical,
        )
        self._cleanup_tasks.append(task)
        self._stats.tasks_registered += 1
        _get_logger().debug(f"Registered cleanup task: {name} (priority: {priority})")

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown.

        Handles:
            - SIGTERM: Graceful termination (e.g., systemd stop)
            - SIGINT: Keyboard interrupt (Ctrl+C)
            - SIGQUIT: Quit signal with core dump

        Note:
            Previous handlers are saved and can be restored.

        """
        signals_to_handle = [
            (signal.SIGTERM, "SIGTERM"),
            (signal.SIGINT, "SIGINT"),
        ]

        # Add SIGQUIT on Unix systems
        if hasattr(signal, "SIGQUIT"):
            signals_to_handle.append((signal.SIGQUIT, "SIGQUIT"))

        for sig, name in signals_to_handle:
            try:
                # Save original handler
                original = signal.getsignal(sig)
                self._original_handlers[sig] = original

                # Set new handler
                signal.signal(sig, self._signal_handler)
                _get_logger().debug(f"Registered signal handler for {name}")
            except (OSError, ValueError) as e:
                _get_logger().warning(f"Could not register handler for {name}: {e}")

        # Register atexit handler as final fallback
        atexit.register(self._atexit_handler)
        _get_logger().debug("Registered atexit handler")

    def restore_signal_handlers(self) -> None:
        """Restore original signal handlers.

        Useful for cleanup or testing.
        """
        for sig, original in self._original_handlers.items():
            try:
                signal.signal(sig, original)
            except (OSError, ValueError) as e:
                _get_logger().warning(f"Could not restore signal {sig}: {e}")

        self._original_handlers.clear()
        _get_logger().debug("Restored original signal handlers")

    def _signal_handler(self, signum: int, frame: t.Any) -> None:
        """Internal signal handler that triggers shutdown.

        Args:
            signum: Signal number
            frame: Current stack frame (unused)

        """
        sig_name = signal.Signals(signum).name
        _get_logger().info(f"Received signal {sig_name}, initiating graceful shutdown")

        # Run shutdown in the event loop
        try:
            loop = asyncio.get_running_loop()
            # Schedule shutdown as a task
            loop.create_task(self.shutdown())
        except RuntimeError:
            # No running loop, run in new loop
            asyncio.run(self.shutdown())

    def _atexit_handler(self) -> None:
        """Final cleanup handler registered with atexit.

        Ensures cleanup runs even if signals aren't caught.
        """
        if not self._shutdown_initiated:
            _get_logger().info("atexit handler triggered, running final cleanup")
            with suppress(RuntimeError):
                asyncio.run(self.shutdown())

    async def _execute_cleanup_task(self, task: CleanupTask) -> None:
        """Execute a single cleanup task with timeout enforcement.

        Args:
            task: Cleanup task to execute

        Raises:
            TimeoutError: If task exceeds timeout
            Exception: If task execution fails

        """
        _get_logger().debug(
            f"Executing cleanup task: {task.name} "
            f"(priority: {task.priority}, timeout: {task.timeout_seconds}s)",
        )

        # Execute with timeout
        if asyncio.iscoroutinefunction(task.callback):
            await asyncio.wait_for(task.callback(), timeout=task.timeout_seconds)
        else:
            # Sync function - run in executor
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, task.callback),
                timeout=task.timeout_seconds,
            )

    def _handle_task_timeout(self, task: CleanupTask) -> bool:
        """Handle cleanup task timeout.

        Args:
            task: Task that timed out

        Returns:
            True if should stop cleanup (critical task), False otherwise

        """
        self._stats.tasks_timeout += 1
        _get_logger().error(
            f"Cleanup task timed out after {task.timeout_seconds}s: {task.name}",
        )
        if task.critical:
            _get_logger().critical(
                f"Critical task failed: {task.name}, stopping cleanup",
            )
            return True
        return False

    def _handle_task_failure(self, task: CleanupTask, error: Exception) -> bool:
        """Handle cleanup task failure.

        Args:
            task: Task that failed
            error: Exception that occurred

        Returns:
            True if should stop cleanup (critical task), False otherwise

        """
        self._stats.tasks_failed += 1
        _get_logger().error(
            f"Cleanup task failed: {task.name} - {error}",
            exc_info=True,
        )
        if task.critical:
            _get_logger().critical(
                f"Critical task failed: {task.name}, stopping cleanup",
            )
            return True
        return False

    def _finalize_shutdown(
        self,
        sorted_tasks: list[CleanupTask],
        start_time: float,
    ) -> None:
        """Finalize shutdown and log results.

        Args:
            sorted_tasks: List of tasks that were executed
            start_time: When shutdown started (from time.perf_counter())

        """
        import time

        # Calculate total duration
        self._stats.total_duration_ms = (time.perf_counter() - start_time) * 1000

        _get_logger().info(
            f"Shutdown complete: {self._stats.tasks_executed}/{len(sorted_tasks)} tasks succeeded "
            f"in {self._stats.total_duration_ms:.2f}ms",
        )

        if self._stats.tasks_failed > 0 or self._stats.tasks_timeout > 0:
            _get_logger().warning(
                f"Shutdown had issues: {self._stats.tasks_failed} failed, "
                f"{self._stats.tasks_timeout} timed out",
            )

    async def shutdown(self) -> ShutdownStats:
        """Execute all cleanup tasks in priority order.

        Returns:
            ShutdownStats with execution details

        Features:
            - Executes tasks by priority (highest first)
            - Enforces per-task timeouts
            - Handles both async and sync cleanup functions
            - Continues on non-critical failures
            - Tracks comprehensive statistics

        """
        import time

        start_time = time.perf_counter()

        # Prevent multiple simultaneous shutdowns
        async with self._shutdown_lock:
            if self._shutdown_initiated:
                _get_logger().debug("Shutdown already initiated, skipping")
                return self._stats

            self._shutdown_initiated = True
            _get_logger().info(
                f"Starting graceful shutdown with {len(self._cleanup_tasks)} tasks",
            )

            # Sort by priority (highest first)
            sorted_tasks = sorted(
                self._cleanup_tasks,
                key=lambda t: t.priority,
                reverse=True,
            )

            for task in sorted_tasks:
                try:
                    await self._execute_cleanup_task(task)
                    self._stats.tasks_executed += 1
                    _get_logger().debug(f"Cleanup task completed: {task.name}")

                except TimeoutError:
                    if self._handle_task_timeout(task):
                        break

                except Exception as e:  # noqa: BLE001 - shutdown loop must continue across all registered cleanup tasks; each task can raise arbitrary errors
                    if self._handle_task_failure(task, e):
                        break

            self._finalize_shutdown(sorted_tasks, start_time)
            return self._stats

    def get_stats(self) -> ShutdownStats:
        """Get current shutdown statistics.

        Returns:
            ShutdownStats with current state

        """
        return self._stats

    def is_shutdown_initiated(self) -> bool:
        """Check if shutdown has been initiated.

        Returns:
            True if shutdown is in progress or complete

        """
        return self._shutdown_initiated


# Global shutdown manager instance
_global_shutdown_manager: ShutdownManager | None = None


def get_shutdown_manager() -> ShutdownManager:
    """Get the global shutdown manager instance.

    Returns:
        Global ShutdownManager singleton

    Example:
        >>> from session_buddy.shutdown_manager import get_shutdown_manager
        >>>
        >>> shutdown_mgr = get_shutdown_manager()
        >>> shutdown_mgr.register_cleanup("my_cleanup", cleanup_func)

    """
    global _global_shutdown_manager

    if _global_shutdown_manager is None:
        _global_shutdown_manager = ShutdownManager()

    return _global_shutdown_manager


__all__ = [
    "CleanupTask",
    "ShutdownManager",
    "ShutdownStats",
    "get_shutdown_manager",
]
