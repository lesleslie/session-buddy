"""Worker implementation for Session-Buddy pool execution.

This module provides the Worker class that processes tasks from a queue
as part of a 3-worker pool for delegated execution.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class Task:
    """Represents a task to be executed by a worker."""

    def __init__(
        self, task_id: str, prompt: str, context: dict[str, Any] | None = None
    ) -> None:
        """Initialize a new task.

        Args:
            task_id: Unique task identifier
            prompt: Task prompt/instruction
            context: Optional context for task execution
        """
        self.task_id = task_id
        self.prompt = prompt
        self.context = context or {}
        self.created_at = datetime.now(UTC)
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.result: Any = None
        self.error: Exception | None = None
        self.status: str = "pending"  # pending, running, completed, failed
        self._result_event = asyncio.Event()

    async def wait_for_result(self, timeout: float | None = None) -> Any:
        """Wait for task result with optional timeout.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Task result

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
            Exception: If task failed
        """
        try:
            await asyncio.wait_for(self._result_event.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning(f"Task {self.task_id} timed out after {timeout}s")
            raise

        if self.error:
            raise self.error

        return self.result

    async def set_result(self, result: Any) -> None:
        """Set task result and mark as completed.

        Args:
            result: Task execution result
        """
        self.result = result
        self.status = "completed"
        self.completed_at = datetime.now(UTC)
        self._result_event.set()

    async def set_error(self, error: Exception) -> None:
        """Set task error and mark as failed.

        Args:
            error: Exception that occurred during execution
        """
        self.error = error
        self.status = "failed"
        self.completed_at = datetime.now(UTC)
        self._result_event.set()

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary representation.

        Returns:
            Dictionary with task data
        """
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "context": self.context,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": str(self.result) if self.result is not None else None,
            "error": str(self.error) if self.error else None,
        }


class Worker:
    """Single worker in a 3-worker pool.

    Each worker processes tasks from a shared queue asynchronously,
    maintaining its own state and health status.
    """

    def __init__(
        self, worker_id: str, queue: asyncio.Queue[Task], pool_id: str
    ) -> None:
        """Initialize a new worker.

        Args:
            worker_id: Unique worker identifier
            queue: Task queue to pull from
            pool_id: ID of the parent pool
        """
        self.worker_id = worker_id
        self.queue = queue
        self.pool_id = pool_id
        self.running = False
        self._task: asyncio.Task[None] | None = None

        # Worker statistics
        self.tasks_processed = 0
        self.tasks_succeeded = 0
        self.tasks_failed = 0
        self.total_processing_time = 0.0
        self.last_activity: datetime | None = None

        # Health monitoring
        self.healthy = True
        self.health_check_failures = 0
        self._health_lock = asyncio.Lock()

        logger.info(f"Worker {self.worker_id} initialized for pool {self.pool_id}")

    async def start(self) -> None:
        """Start worker processing loop."""
        if self.running:
            logger.warning(f"Worker {self.worker_id} is already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._process_tasks())
        logger.info(f"Worker {self.worker_id} started")

    async def stop(self, timeout: float = 5.0) -> None:
        """Stop worker processing loop.

        Args:
            timeout: Maximum time to wait for worker to stop
        """
        if not self.running:
            return

        logger.info(f"Stopping worker {self.worker_id}")
        self.running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except TimeoutError:
                logger.warning(
                    f"Worker {self.worker_id} did not stop within {timeout}s"
                )
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info(f"Worker {self.worker_id} stopped")

    async def _process_tasks(self) -> None:
        """Process tasks from queue continuously."""
        logger.info(f"Worker {self.worker_id} task processing loop started")

        while self.running:
            try:
                # Get task from queue with timeout to allow checking running flag
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # Process the task
                await self._execute_task(task)

            except TimeoutError:
                # No task available, continue loop
                continue
            except asyncio.CancelledError:
                logger.info(f"Worker {self.worker_id} task processing cancelled")
                break
            except Exception as e:
                logger.exception(
                    f"Worker {self.worker_id} error in task processing loop: {e}"
                )
                # Mark unhealthy but continue processing
                async with self._health_lock:
                    self.health_check_failures += 1
                    if self.health_check_failures >= 3:
                        self.healthy = False

        logger.info(f"Worker {self.worker_id} task processing loop ended")

    async def _execute_task(self, task: Task) -> None:
        """Execute a single task.

        Args:
            task: Task to execute
        """
        task.status = "running"
        task.started_at = datetime.now(UTC)
        self.last_activity = task.started_at

        logger.info(f"Worker {self.worker_id} executing task {task.task_id}")

        try:
            start_time = asyncio.get_event_loop().time()

            # Execute the task (delegate to actual execution logic)
            result = await self._execute_task_logic(task)

            end_time = asyncio.get_event_loop().time()
            processing_time = end_time - start_time
            self.total_processing_time += processing_time

            # Mark task as completed
            await task.set_result(result)

            self.tasks_processed += 1
            self.tasks_succeeded += 1

            # Reset health check failures on success
            async with self._health_lock:
                self.health_check_failures = 0
                self.healthy = True

            logger.info(
                f"Worker {self.worker_id} completed task {task.task_id} "
                f"in {processing_time:.2f}s"
            )

        except Exception as e:
            logger.exception(f"Worker {self.worker_id} failed task {task.task_id}: {e}")

            # Mark task as failed
            await task.set_error(e)

            self.tasks_processed += 1
            self.tasks_failed += 1

    async def _execute_task_logic(self, task: Task) -> Any:
        """Execute the actual task logic.

        This is a placeholder implementation. In a real system, this would
        delegate to LLM execution, tool use, or other task processing.

        Args:
            task: Task to execute

        Returns:
            Task result
        """
        # Simulate processing
        await asyncio.sleep(0.1)

        # Placeholder result - in real system, this would execute actual task
        result = {
            "worker_id": self.worker_id,
            "pool_id": self.pool_id,
            "task_id": task.task_id,
            "prompt": task.prompt,
            "response": f"Processed task: {task.prompt}",
            "context": task.context,
        }

        return result

    async def health_check(self) -> bool:
        """Check if worker is healthy.

        Returns:
            True if worker is healthy, False otherwise
        """
        async with self._health_lock:
            # Worker is unhealthy if too many consecutive failures
            if self.health_check_failures >= 3:
                return False

            # Worker is unhealthy if not running
            if not self.running:
                return False

            # Worker is unhealthy if no recent activity (stuck?)
            if self.last_activity:
                idle_time = (datetime.now(UTC) - self.last_activity).total_seconds()
                if idle_time > 300:  # 5 minutes with no activity
                    return False

            return True

    def get_status(self) -> dict[str, Any]:
        """Get worker status.

        Returns:
            Dictionary with worker status information
        """
        avg_processing_time = (
            self.total_processing_time / self.tasks_processed
            if self.tasks_processed > 0
            else 0
        )

        return {
            "worker_id": self.worker_id,
            "pool_id": self.pool_id,
            "running": self.running,
            "healthy": self.healthy,
            "tasks_processed": self.tasks_processed,
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "success_rate": (
                self.tasks_succeeded / self.tasks_processed
                if self.tasks_processed > 0
                else 1.0
            ),
            "avg_processing_time": avg_processing_time,
            "total_processing_time": self.total_processing_time,
            "last_activity": self.last_activity.isoformat()
            if self.last_activity
            else None,
        }

    def __repr__(self) -> str:
        """String representation of worker."""
        return (
            f"Worker(id={self.worker_id}, pool={self.pool_id}, "
            f"running={self.running}, healthy={self.healthy}, "
            f"tasks={self.tasks_processed})"
        )
