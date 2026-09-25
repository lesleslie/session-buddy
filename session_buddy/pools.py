"""Worker pool management for Session-Buddy delegated execution.

This module provides pool management for coordinating exactly 3 workers
per pool, with task queues, health monitoring, and statistics tracking.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from .worker import Task, Worker

# Hybrid D: re-use the existing track_channel_session validator rather
# than introducing a parallel event pipeline. The validator accepts
# event_type ∈ {channel_session_start, channel_heartbeat, channel_session_end}.
# The import is deferred to method bodies to avoid a circular import
# (``session_buddy.mcp.tools`` eagerly imports ``session_buddy.pools``).

logger = logging.getLogger(__name__)


def _emit_channel_session_event(
    pool_id: str,
    event_type: str,
    metadata: dict[str, Any],
    message_count: int = 0,
) -> None:
    """Lazy helper: import the channel store + emit one lifecycle event.

    Defers the import to dodge the pools ↔ mcp.tools circular import.
    Best-effort: any import or store failure is logged and swallowed so
    a malformed observer stack never blocks pool lifecycle.
    """
    try:
        from .mcp.tools.session.channel_tracking_tools import (
            ChannelSessionEvent,
            _store as _channel_store,
        )
    except Exception:  # noqa: BLE001 — observability is best-effort
        logger.exception("channel_tracking_tools import failed; skipping event")
        return

    event = ChannelSessionEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        channel_type="pool",
        channel_id=f"pool:{pool_id}",
        sender_id=pool_id,
        timestamp=datetime.now(UTC).isoformat(),
        component_name="session-buddy",
        session_scope="conversation",
        message_count=message_count,
        metadata=metadata,
    )
    if event_type == "channel_session_start":
        _channel_store.start(event)
    elif event_type == "channel_session_end":
        _channel_store.end(event)


# Number of workers per pool (fixed at 3 per architecture)
WORKERS_PER_POOL = 3


class WorkerPool:
    """Manages exactly 3 workers for delegated execution.

    Each pool maintains a task queue and coordinates 3 workers
    to process tasks asynchronously with health monitoring.
    """

    def __init__(
        self,
        pool_id: str | None = None,
        *,
        backend: str = "placeholder",
        model: str | None = None,
        reflect_tasks: bool = False,
    ) -> None:
        """Initialize a new worker pool.

        Args:
            pool_id: Optional pool identifier (auto-generated if not provided)
            backend: Backend strategy name (``"placeholder"`` or ``"llm"``).
            model: Optional default model name forwarded to LLM backend.
            reflect_tasks: When True, every completed task writes a
                session-buddy reflection tagged ``pool-task`` for
                observability. Default ``False`` preserves byte-identical
                behaviour for existing pools.
        """
        self.pool_id = pool_id or f"pool_{uuid.uuid4().hex[:8]}"
        self.task_queue: asyncio.Queue[Task] = asyncio.Queue()
        self.workers: list[Worker] = []

        # Pool state
        self.running = False
        self.created_at = datetime.now(UTC)
        self.started_at: datetime | None = None

        # Statistics
        self.tasks_submitted = 0
        self.tasks_completed = 0
        self.tasks_failed = 0

        # Hybrid D: backend selection + observability opt-ins.
        # Defaults preserve byte-identical envelopes for existing callers.
        self.backend_name = backend
        self.model = model
        self.reflect_tasks = reflect_tasks
        self.pool_metadata: dict[str, Any] = {
            "backend": backend,
            "model": model,
            "reflect_tasks": reflect_tasks,
        }
        # Backend instance is set by ``initialize()`` so test code that
        # bypasses ``initialize()`` can still inject a fake.
        self._backend_instance: Any = None

        logger.info(f"Worker pool {self.pool_id} created")

    async def initialize(self) -> None:
        """Initialize exactly 3 workers for the pool."""
        if self.running:
            logger.warning(f"Pool {self.pool_id} is already initialized")
            return

        logger.info(f"Initializing {WORKERS_PER_POOL} workers for pool {self.pool_id}")

        # Create exactly 3 workers
        for i in range(WORKERS_PER_POOL):
            worker_id = f"{self.pool_id}-worker-{i}"
            worker = Worker(
                worker_id=worker_id, queue=self.task_queue, pool_id=self.pool_id
            )
            self.workers.append(worker)

        # Start all workers
        for worker in self.workers:
            await worker.start()

        self.running = True
        self.started_at = datetime.now(UTC)

        # Hybrid D: emit channel_session_start so external observers
        # (Akosha, Grafana, get_channel_sessions) can discover the pool.
        _emit_channel_session_event(
            pool_id=self.pool_id,
            event_type="channel_session_start",
            metadata=dict(self.pool_metadata),
        )

        logger.info(f"Pool {self.pool_id} initialized with {len(self.workers)} workers")

    async def shutdown(self, timeout: float = 5.0) -> None:
        """Shutdown the pool and all workers.

        Args:
            timeout: Maximum time to wait for each worker to stop
        """
        if not self.running:
            return

        logger.info(f"Shutting down pool {self.pool_id}")

        # Stop all workers
        stop_tasks = [worker.stop(timeout=timeout) for worker in self.workers]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        self.workers.clear()
        self.running = False

        # Hybrid D: emit channel_session_end so observers can release
        # the pool session and any subscribers close out cleanly.
        _emit_channel_session_event(
            pool_id=self.pool_id,
            event_type="channel_session_end",
            metadata={
                **self.pool_metadata,
                "tasks_submitted": self.tasks_submitted,
                "tasks_completed": self.tasks_completed,
                "tasks_failed": self.tasks_failed,
            },
            message_count=self.tasks_completed,
        )

        logger.info(f"Pool {self.pool_id} shut down")

    async def execute(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute a task on the pool.

        Args:
            prompt: Task prompt/instruction
            context: Optional execution context
            timeout: Maximum time to wait for result

        Returns:
            Task execution result

        Raises:
            RuntimeError: If pool is not running
            asyncio.TimeoutError: If task execution times out
            Exception: If task execution fails
        """
        if not self.running:
            raise RuntimeError(f"Pool {self.pool_id} is not running")

        # Create task
        task_id = f"{self.pool_id}-task-{self.tasks_submitted}"
        task = Task(task_id=task_id, prompt=prompt, context=context)

        self.tasks_submitted += 1

        logger.info(f"Submitting task {task_id} to pool {self.pool_id}")

        # Add task to queue (workers will pick it up)
        await self.task_queue.put(task)

        # Wait for result
        try:
            result = await task.wait_for_result(timeout=timeout)

            self.tasks_completed += 1

            logger.info(f"Task {task_id} completed successfully")
            return result

        except Exception as e:
            self.tasks_failed += 1
            logger.error(f"Task {task_id} failed: {e}")
            raise

    async def execute_batch(
        self,
        prompts: list[str],
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> list[Any]:
        """Execute multiple tasks in parallel.

        Args:
            prompts: List of task prompts
            context: Optional shared execution context
            timeout: Maximum time to wait for each result

        Returns:
            List of task results in same order as prompts
        """
        if not self.running:
            raise RuntimeError(f"Pool {self.pool_id} is not running")

        # Create tasks
        tasks = []
        for i, prompt in enumerate(prompts):
            task_id = f"{self.pool_id}-batch-{self.tasks_submitted + i}"
            task = Task(task_id=task_id, prompt=prompt, context=context)
            tasks.append(task)

        self.tasks_submitted += len(tasks)

        # Submit all tasks to queue
        for task in tasks:
            await self.task_queue.put(task)

        # Wait for all results
        results = await asyncio.gather(
            *[task.wait_for_result(timeout=timeout) for task in tasks],
            return_exceptions=True,
        )

        # Update statistics
        for result in results:
            if isinstance(result, Exception):
                self.tasks_failed += 1
            else:
                self.tasks_completed += 1

        return results

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on all workers.

        Returns:
            Dictionary with health status for pool and workers
        """
        if not self.running:
            return {
                "pool_id": self.pool_id,
                "status": "not_running",
                "workers": [],
            }

        # Check health of all workers in parallel
        health_results = await asyncio.gather(
            *[worker.health_check() for worker in self.workers]
        )

        all_healthy = all(health_results)

        return {
            "pool_id": self.pool_id,
            "status": "healthy" if all_healthy else "degraded",
            "workers_healthy": sum(health_results),
            "workers_total": len(self.workers),
            "worker_health": [worker.get_status() for worker in self.workers],
        }

    def get_status(self) -> dict[str, Any]:
        """Get pool status.

        Returns:
            Dictionary with pool status information
        """
        return {
            "pool_id": self.pool_id,
            "running": self.running,
            "workers_count": len(self.workers),
            "queue_size": self.task_queue.qsize(),
            "tasks_submitted": self.tasks_submitted,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "success_rate": (
                self.tasks_completed / self.tasks_submitted
                if self.tasks_submitted > 0
                else 1.0
            ),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "workers": [worker.get_status() for worker in self.workers],
        }

    def __repr__(self) -> str:
        """String representation of pool."""
        return (
            f"WorkerPool(id={self.pool_id}, running={self.running}, "
            f"workers={len(self.workers)}, queue_size={self.task_queue.qsize()})"
        )


class PoolManager:
    """Manages multiple worker pools for delegated execution.

    Provides centralized pool lifecycle management, task routing,
    and cross-pool monitoring.
    """

    def __init__(self) -> None:
        """Initialize pool manager."""
        self.pools: dict[str, WorkerPool] = {}
        self._lock = asyncio.Lock()
        self.running = False

        logger.info("Pool manager initialized")

    async def start(self) -> None:
        """Start pool manager."""
        if self.running:
            logger.warning("Pool manager is already running")
            return

        self.running = True
        logger.info("Pool manager started")

    async def stop(self) -> None:
        """Stop pool manager and shutdown all pools."""
        if not self.running:
            return

        logger.info("Stopping pool manager")

        # Shutdown all pools
        async with self._lock:
            shutdown_tasks = [pool.shutdown() for pool in self.pools.values()]
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            self.pools.clear()

        self.running = False
        logger.info("Pool manager stopped")

    async def create_pool(self, pool_id: str | None = None) -> WorkerPool:
        """Create a new worker pool.

        Args:
            pool_id: Optional pool identifier (auto-generated if not provided)

        Returns:
            Created pool
        """
        async with self._lock:
            if pool_id and pool_id in self.pools:
                raise ValueError(f"Pool {pool_id} already exists")

            pool = WorkerPool(pool_id=pool_id)
            await pool.initialize()

            self.pools[pool.pool_id] = pool

            logger.info(f"Created pool {pool.pool_id}")
            return pool

    async def get_pool(self, pool_id: str) -> WorkerPool | None:
        """Get a pool by ID.

        Args:
            pool_id: Pool identifier

        Returns:
            Pool if found, None otherwise
        """
        async with self._lock:
            return self.pools.get(pool_id)

    async def delete_pool(self, pool_id: str, timeout: float = 5.0) -> bool:
        """Delete a pool.

        Args:
            pool_id: Pool identifier
            timeout: Maximum time to wait for pool shutdown

        Returns:
            True if pool was deleted, False if not found
        """
        async with self._lock:
            pool = self.pools.pop(pool_id, None)
            if pool:
                await pool.shutdown(timeout=timeout)
                logger.info(f"Deleted pool {pool_id}")
                return True
            return False

    async def list_pools(self) -> list[dict[str, Any]]:
        """List all pools.

        Returns:
            List of pool status dictionaries
        """
        async with self._lock:
            return [pool.get_status() for pool in self.pools.values()]

    async def execute_on_pool(
        self,
        pool_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute a task on a specific pool.

        Args:
            pool_id: Pool identifier
            prompt: Task prompt
            context: Optional execution context
            timeout: Maximum time to wait for result

        Returns:
            Task result

        Raises:
            ValueError: If pool not found
        """
        pool = await self.get_pool(pool_id)
        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        return await pool.execute(prompt=prompt, context=context, timeout=timeout)

    async def route_task(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        selector: str = "least_loaded",
        timeout: float | None = None,
    ) -> tuple[str, Any]:
        """Route task to best available pool.

        Args:
            prompt: Task prompt
            context: Optional execution context
            selector: Pool selection strategy (round_robin, least_loaded, random)
            timeout: Maximum time to wait for result

        Returns:
            Tuple of (pool_id, task_result)

        Raises:
            ValueError: If no pools available
        """
        async with self._lock:
            if not self.pools:
                raise ValueError("No pools available for routing")

            # Select pool based on strategy
            if selector == "least_loaded":
                # Select pool with smallest queue
                pool = min(self.pools.values(), key=lambda p: p.task_queue.qsize())
            elif selector == "round_robin":
                # Select first pool (could be enhanced with counter)
                pool = next(iter(self.pools.values()))
            elif selector == "random":
                import random

                pool = random.choice(list(self.pools.values()))
            else:
                raise ValueError(f"Unknown selector strategy: {selector}")

            pool_id = pool.pool_id

        # Execute on selected pool (outside lock)
        result = await pool.execute(prompt=prompt, context=context, timeout=timeout)

        return pool_id, result

    async def get_health_status(self) -> dict[str, Any]:
        """Get health status of all pools.

        Returns:
            Dictionary with health status for all pools
        """
        async with self._lock:
            health_checks = [pool.health_check() for pool in self.pools.values()]
            health_results = await asyncio.gather(
                *health_checks, return_exceptions=True
            )

            return {
                "pool_manager_running": self.running,
                "pools_total": len(self.pools),
                "pools_healthy": sum(
                    1
                    for h in health_results
                    if isinstance(h, dict) and h.get("status") == "healthy"
                ),
                "pool_details": [h for h in health_results if isinstance(h, dict)],
            }

    def __repr__(self) -> str:
        """String representation of pool manager."""
        return f"PoolManager(running={self.running}, pools={len(self.pools)})"


# Global pool manager instance
_global_pool_manager: PoolManager | None = None
_manager_lock = asyncio.Lock()


async def get_pool_manager() -> PoolManager:
    """Get or create global pool manager instance.

    Returns:
        Global pool manager
    """
    global _global_pool_manager

    async with _manager_lock:
        if _global_pool_manager is None:
            _global_pool_manager = PoolManager()
            await _global_pool_manager.start()

        return _global_pool_manager
