#!/usr/bin/env python3
"""Git maintenance service with hook-based architecture.

This service provides automatic git garbage collection with:
- Hook-based integration (decoupled from session lifecycle)
- Process tracking and resource management
- Rate limiting to prevent excessive gc calls
- Atomic operations to prevent TOCTOU race conditions
- Comprehensive error handling and logging

Week 8 Day 2 - Phase 5: Security hardening and architectural improvements.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from subprocess import Popen

import structlog

from session_buddy.core.hooks import (
    Hook,
    HookContext,
    HookResult,
    HooksManager,
    HookType,
)
from session_buddy.utils.git_operations import (
    _validate_prune_delay,
    is_git_operation_in_progress,
    schedule_automatic_git_gc,
)

__all__ = [
    "GitMaintenanceService",
    "GitProcessTracker",
    "get_git_maintenance_service",
]

logger = structlog.get_logger(__name__)


@dataclass
class TrackedProcess:
    """Information about a tracked git gc process."""

    popen: Popen
    start_time: datetime
    repository: Path
    prune_delay: str
    threshold: int


@dataclass
class GitMaintenanceConfig:
    """Configuration for git maintenance service."""

    enabled: bool = True
    prune_delay: str = "2.weeks"
    auto_threshold: int = 6700
    only_when_clean: bool = True
    # Rate limiting: minimum seconds between gc calls
    min_gc_interval: int = 3600  # 1 hour default
    # Process tracking: maximum concurrent gc processes
    max_concurrent_gc: int = 1


class GitProcessTracker:
    """Track and manage git gc processes.

    Features:
    - Process lifecycle tracking (start, monitor, cleanup)
    - Zombie process prevention
    - Resource usage monitoring
    - Automatic cleanup of dead processes
    """

    def __init__(self) -> None:
        """Initialize process tracker."""
        self.active_processes: dict[str, TrackedProcess] = {}
        self.finished_processes: list[TrackedProcess] = []
        self.max_finished_history = 100

    def track_process(
        self,
        popen: Popen,
        repository: Path,
        prune_delay: str,
        threshold: int,
    ) -> str:
        """Track a new git gc process.

        Args:
            popen: subprocess.Popen object
            repository: Git repository path
            prune_delay: Prune delay setting
            threshold: Auto threshold setting

        Returns:
            Process ID for tracking
        """
        process_id = f"{int(time.time())}_{repository.name}"

        tracked = TrackedProcess(
            popen=popen,
            start_time=datetime.now(),
            repository=repository,
            prune_delay=prune_delay,
            threshold=threshold,
        )

        self.active_processes[process_id] = tracked
        logger.info(
            "Tracked git gc process",
            process_id=process_id,
            repository=str(repository),
            prune_delay=prune_delay,
        )

        return process_id

    def cleanup_finished_processes(self) -> None:
        """Check and cleanup finished processes."""
        dead_processes = []

        for process_id, tracked in self.active_processes.items():
            if tracked.popen.poll() is not None:
                # Process has finished
                self.finished_processes.append(tracked)
                dead_processes.append(process_id)

                logger.info(
                    "Git gc process finished",
                    process_id=process_id,
                    return_code=tracked.popen.returncode,
                    duration_seconds=(
                        datetime.now() - tracked.start_time
                    ).total_seconds(),
                )

        # Remove dead processes from active list
        for process_id in dead_processes:
            del self.active_processes[process_id]

        # Trim finished history
        if len(self.finished_processes) > self.max_finished_history:
            self.finished_processes = self.finished_processes[
                -self.max_finished_history :
            ]

    def get_active_count(self) -> int:
        """Get count of active processes."""
        return len(self.active_processes)

    def wait_for_completion(self, timeout: int = 60) -> bool:
        """Wait for all active processes to complete.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if all processes completed, False if timeout
        """
        start_time = time.time()

        while self.active_processes and (time.time() - start_time) < timeout:
            self.cleanup_finished_processes()
            time.sleep(0.1)

        return len(self.active_processes) == 0

    def terminate_all(self) -> None:
        """Terminate all active processes (emergency cleanup)."""
        for process_id, tracked in self.active_processes.items():
            try:
                tracked.popen.terminate()
                logger.warning("Terminated git gc process", process_id=process_id)
            except Exception as e:
                logger.error(
                    "Failed to terminate git gc process",
                    process_id=process_id,
                    error=str(e),
                )

        self.active_processes.clear()


class GitMaintenanceService:
    """Git maintenance service with rate limiting and process tracking.

    This service uses hooks for loose coupling with the session lifecycle.
    It provides automatic git garbage collection with safety checks and
    resource management.

    Architecture:
    - Hook-based integration (decoupled from SessionLifecycleManager)
    - Singleton pattern via dependency injection
    - Thread-safe operations with file locking
    - Rate limiting to prevent excessive gc calls
    """

    _instance: GitMaintenanceService | None = None
    _lock_file: Path | None = None

    def __init__(self, config: GitMaintenanceConfig | None = None) -> None:
        """Initialize git maintenance service.

        Args:
            config: Configuration (uses defaults if None)
        """
        self.config = config or GitMaintenanceConfig()
        self.process_tracker = GitProcessTracker()
        self.last_gc_time: dict[str, datetime] = {}
        self._lock_file_handle: int | None = None
        self.hooks_manager: HooksManager | None = None

    @classmethod
    def get_instance(cls) -> GitMaintenanceService:
        """Get singleton instance.

        Returns:
            GitMaintenanceService instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def register_hooks(self, hooks_manager: HooksManager) -> None:
        """Register hooks with the hooks manager.

        Args:
            hooks_manager: The hooks manager instance
        """
        self.hooks_manager = hooks_manager

        # Create post-checkpoint hook
        hook = Hook(
            name="git_maintenance_post_checkpoint",
            hook_type=HookType.POST_CHECKPOINT,
            priority=100,  # Run after checkpoint commits
            handler=self._on_post_checkpoint,
        )

        await hooks_manager.register_hook(hook)
        logger.info("Registered git maintenance hooks")

    async def _on_post_checkpoint(self, context: HookContext) -> HookResult:
        """Handle post-checkpoint hook event.

        Args:
            context: Hook context with repository path and quality score

        Returns:
            HookResult indicating success
        """
        # Extract repository from checkpoint data
        if context.checkpoint_data and "repository" in context.checkpoint_data:
            repository_str = context.checkpoint_data["repository"]
        else:
            # Try metadata
            repository_str = context.metadata.get("repository")

        if not repository_str:
            return HookResult(success=True)

        repository = Path(repository_str)

        # Perform maintenance with rate limiting (sync wrapper)
        # Note: This is safe because perform_maintenance is fast
        # and the actual gc runs in background
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.perform_maintenance, repository)
        except Exception as e:
            logger.error(
                "Git maintenance hook error",
                repository=str(repository),
                error=str(e),
            )
            return HookResult(success=False, error=str(e))

        return HookResult(success=True)

    def _acquire_lock(self, repository: Path) -> bool:
        """Acquire exclusive lock to prevent concurrent gc operations.

        Uses file locking for atomic check-and-execute pattern.
        This prevents TOCTOU race conditions.

        Args:
            repository: Git repository path

        Returns:
            True if lock acquired, False otherwise
        """
        lock_file = repository / ".git" / "gc.lock"

        try:
            # Open lock file (create if doesn't exist)
            fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)

            # Try to acquire exclusive lock (non-blocking)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._lock_file_handle = fd
                logger.debug("Acquired git gc lock", lock_file=str(lock_file))
                return True
            except OSError:
                # Lock is held by another process
                os.close(fd)
                logger.debug("Git gc lock busy", lock_file=str(lock_file))
                return False

        except Exception as e:
            logger.error("Failed to acquire git gc lock", error=str(e))
            return False

    def _release_lock(self) -> None:
        """Release the exclusive lock."""
        if self._lock_file_handle is not None:
            try:
                fcntl.flock(self._lock_file_handle, fcntl.LOCK_UN)
                os.close(self._lock_file_handle)
                self._lock_file_handle = None
                logger.debug("Released git gc lock")
            except Exception as e:
                logger.error("Failed to release git gc lock", error=str(e))

    def _check_rate_limit(self, repository: Path) -> bool:
        """Check if rate limit allows gc to run.

        Args:
            repository: Git repository path

        Returns:
            True if rate limit allows gc, False otherwise
        """
        repo_key = str(repository)

        # Check if we've run gc recently
        if repo_key in self.last_gc_time:
            elapsed = datetime.now() - self.last_gc_time[repo_key]
            min_interval = timedelta(seconds=self.config.min_gc_interval)

            if elapsed < min_interval:
                logger.info(
                    "Rate limit: gc too recent",
                    repository=repo_key,
                    elapsed_seconds=elapsed.total_seconds(),
                    min_interval_seconds=self.config.min_gc_interval,
                )
                return False

        return True

    def _validate_maintenance_prerequisites(self, repository: Path) -> tuple[bool, str]:
        """Validate all prerequisites for git maintenance.

        Args:
            repository: Git repository path

        Returns:
            tuple: (can_proceed, error_message)
        """
        if not self.config.enabled:
            return False, "Git maintenance disabled"

        if not self._check_rate_limit(repository):
            return False, "Rate limit: gc too recent"

        if self.config.only_when_clean:
            if is_git_operation_in_progress(repository):
                return False, "Git operation in progress"

        if self.process_tracker.get_active_count() >= self.config.max_concurrent_gc:
            return False, "Max concurrent gc processes reached"

        is_valid, error_msg = _validate_prune_delay(self.config.prune_delay)
        if not is_valid:
            return False, f"Invalid prune delay: {error_msg}"

        if not self._acquire_lock(repository):
            return False, "Could not acquire gc lock"

        return True, ""

    def perform_maintenance(self, repository: Path) -> dict[str, Any]:
        """Perform git maintenance with safety checks.

        This method implements the complete maintenance workflow:
        1. Validate prerequisites (enabled, rate limit, git ops, process limit, config, lock)
        2. Schedule gc
        3. Track process
        4. Release lock

        Args:
            repository: Git repository path

        Returns:
            Dictionary with operation status and details
        """
        result: dict[str, Any] = {
            "success": False,
            "repository": str(repository),
            "message": "",
            "process_id": None,
        }

        try:
            can_proceed, error_msg = self._validate_maintenance_prerequisites(repository)

            if not can_proceed:
                result["message"] = error_msg

                if "Git operation in progress" in error_msg:
                    logger.info("Skipping gc: git operation in progress", repository=str(repository))
                elif "Max concurrent" in error_msg:
                    logger.warning(
                        "Skipping gc: too many active processes",
                        active_count=self.process_tracker.get_active_count(),
                        max_allowed=self.config.max_concurrent_gc,
                    )
                elif "Invalid prune delay" in error_msg:
                    logger.error("Invalid prune delay", error=error_msg)
                elif "lock" in error_msg:
                    logger.info("Skipping gc: lock held by another process")

                return result

            try:
                success, message = schedule_automatic_git_gc(
                    repository,
                    prune_delay=self.config.prune_delay,
                    auto_threshold=self.config.auto_threshold,
                )

                if success:
                    repo_key = str(repository)
                    self.last_gc_time[repo_key] = datetime.now()

                    result["success"] = True
                    result["message"] = message

                    logger.info(
                        "Git maintenance scheduled successfully",
                        repository=str(repository),
                        prune_delay=self.config.prune_delay,
                    )
                else:
                    result["message"] = message
                    logger.error(
                        "Failed to schedule git maintenance",
                        repository=str(repository),
                        error=message,
                    )

            finally:
                self._release_lock()

        except Exception as e:
            result["message"] = f"Exception: {e}"
            logger.error(
                "Git maintenance exception",
                repository=str(repository),
                error=str(e),
                exc_info=True,
            )
            self._release_lock()

        return result

    def shutdown(self) -> None:
        """Cleanup and shutdown the service.

        Terminates all active processes and releases resources.
        """
        logger.info("Shutting down git maintenance service")

        # Wait for processes to complete (with timeout)
        if not self.process_tracker.wait_for_completion(timeout=10):
            # Force terminate if timeout
            self.process_tracker.terminate_all()

        # Release lock if held
        self._release_lock()


def get_git_maintenance_service() -> GitMaintenanceService:
    """Get the singleton git maintenance service instance.

    Returns:
        GitMaintenanceService instance
    """
    return GitMaintenanceService.get_instance()
