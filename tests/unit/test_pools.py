"""Comprehensive unit tests for session_buddy/pools.py.

Tests cover WorkerPool and PoolManager classes with all public methods,
edge cases, and error handling paths.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the modules under test
from session_buddy.pools import (
    WORKERS_PER_POOL,
    PoolManager,
    WorkerPool,
    get_pool_manager,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_worker():
    """Create a mock Worker instance."""
    worker = MagicMock()
    worker.worker_id = "mock-worker-id"
    worker.pool_id = "mock-pool-id"
    worker.running = True
    worker.healthy = True
    worker.tasks_processed = 0
    worker.tasks_succeeded = 0
    worker.tasks_failed = 0
    worker.total_processing_time = 0.0
    worker.last_activity = None
    worker.health_check_failures = 0
    worker.health_check = AsyncMock(return_value=True)
    worker.get_status = MagicMock(
        return_value={
            "worker_id": "mock-worker-id",
            "pool_id": "mock-pool-id",
            "running": True,
            "healthy": True,
            "tasks_processed": 0,
        }
    )
    worker.start = AsyncMock()
    worker.stop = AsyncMock()
    return worker


@pytest.fixture
def mock_task():
    """Create a mock Task instance."""
    task = MagicMock()
    task.task_id = "mock-task-id"
    task.prompt = "mock prompt"
    task.context = {}
    task.status = "pending"
    task.result = None
    task.error = None
    task.wait_for_result = AsyncMock(return_value={"status": "completed"})
    task.set_result = AsyncMock()
    task.set_error = AsyncMock()
    return task


@pytest.fixture
def mock_queue():
    """Create a mock asyncio.Queue."""
    queue = MagicMock(spec=asyncio.Queue)
    queue.qsize = MagicMock(return_value=0)
    queue.put = AsyncMock()
    queue.get = AsyncMock()
    return queue


# =============================================================================
# Test Classes - WorkerPool
# =============================================================================


class TestWorkerPoolInit:
    """Tests for WorkerPool.__init__ method."""

    def test_init_with_no_pool_id(self):
        """Test initialization without providing pool_id auto-generates one."""
        pool = WorkerPool()
        assert pool.pool_id is not None
        assert pool.pool_id.startswith("pool_")
        assert len(pool.pool_id) == 13  # "pool_" + 8 hex chars

    def test_init_with_custom_pool_id(self):
        """Test initialization with custom pool_id."""
        pool = WorkerPool(pool_id="custom-pool-123")
        assert pool.pool_id == "custom-pool-123"

    def test_init_creates_empty_workers_list(self):
        """Test that initialization creates empty workers list."""
        pool = WorkerPool()
        assert pool.workers == []

    def test_init_creates_task_queue(self):
        """Test that initialization creates task queue."""
        pool = WorkerPool()
        assert isinstance(pool.task_queue, asyncio.Queue)

    def test_init_sets_running_false(self):
        """Test that initialization sets running state to False."""
        pool = WorkerPool()
        assert pool.running is False

    def test_init_sets_created_at(self):
        """Test that initialization sets created_at timestamp."""
        pool = WorkerPool()
        assert pool.created_at is not None
        assert isinstance(pool.created_at, datetime)

    def test_init_sets_started_at_none(self):
        """Test that initialization sets started_at to None."""
        pool = WorkerPool()
        assert pool.started_at is None

    def test_init_zeroes_statistics(self):
        """Test that initialization zeroes all statistics counters."""
        pool = WorkerPool()
        assert pool.tasks_submitted == 0
        assert pool.tasks_completed == 0
        assert pool.tasks_failed == 0


class TestWorkerPoolInitialize:
    """Tests for WorkerPool.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_creates_three_workers(self, mock_queue):
        """Test that initialize creates exactly 3 workers."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue

        with patch("session_buddy.pools.Worker") as MockWorker:
            mock_worker_instance = MagicMock()
            mock_worker_instance.start = AsyncMock()
            MockWorker.return_value = mock_worker_instance

            await pool.initialize()

            assert MockWorker.call_count == WORKERS_PER_POOL
            assert len(pool.workers) == WORKERS_PER_POOL

    @pytest.mark.asyncio
    async def test_initialize_starts_all_workers(self, mock_queue):
        """Test that initialize starts all created workers."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.start = AsyncMock()

        with patch("session_buddy.pools.Worker") as MockWorker:
            MockWorker.side_effect = mock_workers
            await pool.initialize()

            for w in mock_workers:
                w.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_sets_running_true(self, mock_queue):
        """Test that initialize sets running state to True."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue

        with patch("session_buddy.pools.Worker") as MockWorker:
            mock_worker_instance = MagicMock()
            mock_worker_instance.start = AsyncMock()
            MockWorker.return_value = mock_worker_instance

            await pool.initialize()

            assert pool.running is True

    @pytest.mark.asyncio
    async def test_initialize_sets_started_at_timestamp(self, mock_queue):
        """Test that initialize sets started_at timestamp."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue

        with patch("session_buddy.pools.Worker") as MockWorker:
            mock_worker_instance = MagicMock()
            mock_worker_instance.start = AsyncMock()
            MockWorker.return_value = mock_worker_instance

            await pool.initialize()

            assert pool.started_at is not None
            assert isinstance(pool.started_at, datetime)

    @pytest.mark.asyncio
    async def test_initialize_idempotent_when_already_running(self, mock_queue):
        """Test that calling initialize when already running is idempotent."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        await pool.initialize()

        # Should not create new workers
        assert len(pool.workers) == 0

    @pytest.mark.asyncio
    async def test_initialize_creates_unique_worker_ids(self, mock_queue):
        """Test that initialize creates workers with unique IDs."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue

        created_worker_ids = []

        def create_mock_worker(worker_id, queue, pool_id):
            mock = MagicMock()
            mock.worker_id = worker_id
            mock.start = AsyncMock()
            created_worker_ids.append(worker_id)
            return mock

        with patch("session_buddy.pools.Worker", side_effect=create_mock_worker):
            await pool.initialize()

        assert len(set(created_worker_ids)) == WORKERS_PER_POOL
        for worker_id in created_worker_ids:
            assert pool.pool_id in worker_id


class TestWorkerPoolShutdown:
    """Tests for WorkerPool.shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_returns_immediately_when_not_running(self):
        """Test that shutdown returns immediately if pool is not running."""
        pool = WorkerPool(pool_id="test-pool")
        pool.running = False

        await pool.shutdown()

        # No workers to stop, so nothing should happen
        assert pool.workers == []

    @pytest.mark.asyncio
    async def test_shutdown_stops_all_workers(self, mock_queue):
        """Test that shutdown stops all running workers."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.stop = AsyncMock()
        pool.workers = mock_workers

        await pool.shutdown()

        for w in mock_workers:
            w.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_clears_workers_list(self, mock_queue):
        """Test that shutdown clears the workers list."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True
        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.stop = AsyncMock()
        pool.workers = mock_workers

        # Mock asyncio.gather to return an awaitable that resolves
        async def mock_gather(*coroutines, return_exceptions=False):
            # Each arg is a coroutine to await
            results = []
            for coro in coroutines:
                try:
                    await coro
                except Exception:
                    pass
            return results

        with patch("asyncio.gather", side_effect=mock_gather):
            await pool.shutdown()

        assert pool.workers == []

    @pytest.mark.asyncio
    async def test_shutdown_sets_running_false(self, mock_queue):
        """Test that shutdown sets running state to False."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True
        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.stop = AsyncMock()
        pool.workers = mock_workers

        async def mock_gather(*coroutines, return_exceptions=False):
            for coro in coroutines:
                try:
                    await coro
                except Exception:
                    pass
            return []

        with patch("asyncio.gather", side_effect=mock_gather):
            await pool.shutdown()

        assert pool.running is False

    @pytest.mark.asyncio
    async def test_shutdown_awaits_all_worker_stops(self, mock_queue):
        """Test that shutdown awaits all worker stop tasks."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.stop = AsyncMock()
        pool.workers = mock_workers

        gather_called = False

        async def mock_gather(*coroutines, return_exceptions=False):
            nonlocal gather_called
            gather_called = True
            for coro in coroutines:
                try:
                    await coro
                except Exception:
                    pass
            return []

        with patch("asyncio.gather", side_effect=mock_gather):
            await pool.shutdown()
            assert gather_called

    @pytest.mark.asyncio
    async def test_shutdown_respects_timeout_parameter(self, mock_queue):
        """Test that shutdown passes timeout to workers."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.stop = AsyncMock()
        pool.workers = mock_workers

        await pool.shutdown(timeout=10.0)

        for w in mock_workers:
            w.stop.assert_called_with(timeout=10.0)


class TestWorkerPoolExecute:
    """Tests for WorkerPool.execute method."""

    @pytest.mark.asyncio
    async def test_execute_raises_when_not_running(self, mock_queue):
        """Test that execute raises RuntimeError when pool is not running."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = False

        with pytest.raises(RuntimeError, match="not running"):
            await pool.execute("test prompt")

    @pytest.mark.asyncio
    async def test_execute_increments_tasks_submitted(self, mock_queue):
        """Test that execute increments tasks_submitted counter."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(return_value="result")
        mock_task.task_id = "test-task"

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task
            await pool.execute("test prompt")

        assert pool.tasks_submitted == 1

    @pytest.mark.asyncio
    async def test_execute_creates_task_with_correct_prompt(self, mock_queue):
        """Test that execute creates task with correct prompt."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(return_value="result")

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task
            await pool.execute("my test prompt")

            MockTask.assert_called_once()
            call_kwargs = MockTask.call_args[1]
            assert call_kwargs["prompt"] == "my test prompt"

    @pytest.mark.asyncio
    async def test_execute_creates_task_with_context(self, mock_queue):
        """Test that execute creates task with execution context."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(return_value="result")

        context = {"user_id": "123", "session": "abc"}

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task
            await pool.execute("prompt", context=context)

            call_kwargs = MockTask.call_args[1]
            assert call_kwargs["context"] == context

    @pytest.mark.asyncio
    async def test_execute_puts_task_in_queue(self, mock_queue):
        """Test that execute puts task in the task queue."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(return_value="result")

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task
            await pool.execute("prompt")

            mock_queue.put.assert_called_once_with(mock_task)

    @pytest.mark.asyncio
    async def test_execute_increments_completed_on_success(self, mock_queue):
        """Test that execute increments tasks_completed on success."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(return_value="result")

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task
            await pool.execute("prompt")

        assert pool.tasks_completed == 1
        assert pool.tasks_failed == 0

    @pytest.mark.asyncio
    async def test_execute_increments_failed_on_exception(self, mock_queue):
        """Test that execute increments tasks_failed on exception."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(side_effect=ValueError("test error"))

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task

            with pytest.raises(ValueError):
                await pool.execute("prompt")

        assert pool.tasks_failed == 1
        assert pool.tasks_completed == 0

    @pytest.mark.asyncio
    async def test_execute_passes_timeout_to_task(self, mock_queue):
        """Test that execute passes timeout to task's wait_for_result."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(return_value="result")

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task
            await pool.execute("prompt", timeout=30.0)

            mock_task.wait_for_result.assert_called_once_with(timeout=30.0)

    @pytest.mark.asyncio
    async def test_execute_returns_task_result(self, mock_queue):
        """Test that execute returns the task result."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        expected_result = {"output": "test result", "status": "ok"}

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(return_value=expected_result)

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task
            result = await pool.execute("prompt")

        assert result == expected_result

    @pytest.mark.asyncio
    async def test_execute_reraises_task_exception(self, mock_queue):
        """Test that execute re-raises exceptions from task execution."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_task = MagicMock()
        mock_task.wait_for_result = AsyncMock(side_effect=RuntimeError("execution failed"))

        with patch("session_buddy.pools.Task") as MockTask:
            MockTask.return_value = mock_task

            with pytest.raises(RuntimeError, match="execution failed"):
                await pool.execute("prompt")


class TestWorkerPoolExecuteBatch:
    """Tests for WorkerPool.execute_batch method."""

    @pytest.mark.asyncio
    async def test_execute_batch_raises_when_not_running(self, mock_queue):
        """Test that execute_batch raises RuntimeError when pool is not running."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = False

        with pytest.raises(RuntimeError, match="not running"):
            await pool.execute_batch(["prompt1", "prompt2"])

    @pytest.mark.asyncio
    async def test_execute_batch_with_empty_list(self, mock_queue):
        """Test that execute_batch handles empty prompts list."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        async def mock_gather(*args, return_exceptions=False):
            return []

        with patch("asyncio.gather", side_effect=mock_gather):
            result = await pool.execute_batch([])

        assert result == []

    @pytest.mark.asyncio
    async def test_execute_batch_increments_submitted_for_each_prompt(
        self, mock_queue
    ):
        """Test that execute_batch increments tasks_submitted for each prompt."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        async def mock_gather(*args, return_exceptions=False):
            return ["r1", "r2", "r3"]

        with patch("session_buddy.pools.Task") as MockTask:
            mock_task = MagicMock()
            mock_task.wait_for_result = AsyncMock(return_value="result")
            MockTask.return_value = mock_task

            await pool.execute_batch(["p1", "p2", "p3"])

        assert pool.tasks_submitted == 3

    @pytest.mark.asyncio
    async def test_execute_batch_creates_task_per_prompt(self, mock_queue):
        """Test that execute_batch creates one task per prompt."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        prompts = ["prompt1", "prompt2", "prompt3", "prompt4"]

        async def mock_gather(*args, return_exceptions=False):
            return ["r1", "r2", "r3", "r4"]

        with patch("session_buddy.pools.Task") as MockTask:
            mock_task = MagicMock()
            mock_task.wait_for_result = AsyncMock(return_value="result")
            MockTask.return_value = mock_task

            await pool.execute_batch(prompts)

            assert MockTask.call_count == len(prompts)

    @pytest.mark.asyncio
    async def test_execute_batch_submits_all_to_queue(self, mock_queue):
        """Test that execute_batch submits all tasks to queue."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        prompts = ["p1", "p2", "p3"]

        async def mock_gather(*args, return_exceptions=False):
            return []

        with patch("session_buddy.pools.Task") as MockTask:
            mock_task = MagicMock()
            mock_task.wait_for_result = AsyncMock(return_value="result")
            MockTask.return_value = mock_task

            await pool.execute_batch(prompts)

            assert mock_queue.put.call_count == len(prompts)

    @pytest.mark.asyncio
    async def test_execute_batch_returns_results_in_order(self, mock_queue):
        """Test that execute_batch returns results in same order as prompts."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        prompts = ["p1", "p2", "p3"]
        expected_results = ["result1", "result2", "result3"]

        async def mock_gather(*args, return_exceptions=False):
            return expected_results

        with patch("session_buddy.pools.Task") as MockTask:
            mock_task = MagicMock()
            mock_task.wait_for_result = AsyncMock(side_effect=expected_results)
            MockTask.return_value = mock_task

            results = await pool.execute_batch(prompts)

        assert results == expected_results

    @pytest.mark.asyncio
    async def test_execute_batch_counts_exceptions_as_failures(self, mock_queue):
        """Test that execute_batch counts exceptions as task failures."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        results_with_error = ["result1", ValueError("error"), "result3"]

        async def mock_gather(*args, return_exceptions=False):
            return results_with_error

        with patch("session_buddy.pools.Task") as MockTask:
            mock_task = MagicMock()
            mock_task.wait_for_result = AsyncMock(side_effect=results_with_error)
            MockTask.return_value = mock_task

            await pool.execute_batch(["p1", "p2", "p3"])

        assert pool.tasks_failed == 1
        assert pool.tasks_completed == 2

    @pytest.mark.asyncio
    async def test_execute_batch_passes_timeout_to_all_tasks(self, mock_queue):
        """Test that execute_batch passes timeout to all task wait calls."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        async def mock_gather(*args, return_exceptions=False):
            return ["r1", "r2"]

        with patch("session_buddy.pools.Task") as MockTask:
            mock_task = MagicMock()
            mock_task.wait_for_result = AsyncMock(return_value="result")
            MockTask.return_value = mock_task

            await pool.execute_batch(["p1", "p2"], timeout=15.0)

            # Check that wait_for_result was called with timeout
            calls = mock_task.wait_for_result.call_args_list
            for call in calls:
                assert call[1]["timeout"] == 15.0

    @pytest.mark.asyncio
    async def test_execute_batch_uses_shared_context(self, mock_queue):
        """Test that execute_batch uses shared context for all tasks."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        context = {"shared": "context", "user": "test"}

        async def mock_gather(*args, return_exceptions=False):
            return []

        with patch("session_buddy.pools.Task") as MockTask:
            mock_task = MagicMock()
            mock_task.wait_for_result = AsyncMock(return_value="result")
            MockTask.return_value = mock_task

            await pool.execute_batch(["p1", "p2"], context=context)

            # Verify each task was created with the shared context
            for call in MockTask.call_args_list:
                assert call[1]["context"] == context


class TestWorkerPoolHealthCheck:
    """Tests for WorkerPool.health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_not_running_status(self, mock_queue):
        """Test that health_check returns not_running status when pool is down."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = False

        result = await pool.health_check()

        assert result["pool_id"] == "test-pool"
        assert result["status"] == "not_running"
        assert result["workers"] == []

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_when_all_workers_healthy(
        self, mock_queue
    ):
        """Test that health_check returns healthy when all workers are healthy."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.health_check = AsyncMock(return_value=True)
            w.get_status = MagicMock(return_value={"status": "ok"})
        pool.workers = mock_workers

        result = await pool.health_check()

        assert result["status"] == "healthy"
        assert result["workers_healthy"] == WORKERS_PER_POOL
        assert result["workers_total"] == WORKERS_PER_POOL

    @pytest.mark.asyncio
    async def test_health_check_returns_degraded_when_some_unhealthy(
        self, mock_queue
    ):
        """Test that health_check returns degraded when some workers unhealthy."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        # Two healthy, one unhealthy
        mock_workers[0].health_check = AsyncMock(return_value=True)
        mock_workers[1].health_check = AsyncMock(return_value=True)
        mock_workers[2].health_check = AsyncMock(return_value=False)

        for i, w in enumerate(mock_workers):
            w.get_status = MagicMock(return_value={"status": f"worker-{i}"})

        pool.workers = mock_workers

        result = await pool.health_check()

        assert result["status"] == "degraded"
        assert result["workers_healthy"] == 2

    @pytest.mark.asyncio
    async def test_health_check_includes_worker_health_details(self, mock_queue):
        """Test that health_check includes per-worker health details."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue = mock_queue
        pool.running = True

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for w in mock_workers:
            w.health_check = AsyncMock(return_value=True)
            w.get_status = MagicMock(return_value={"worker_id": "test"})

        pool.workers = mock_workers

        result = await pool.health_check()

        assert "worker_health" in result
        assert len(result["worker_health"]) == WORKERS_PER_POOL


class TestWorkerPoolGetStatus:
    """Tests for WorkerPool.get_status method."""

    def test_get_status_returns_pool_id(self):
        """Test that get_status returns pool_id."""
        pool = WorkerPool(pool_id="test-pool-123")
        status = pool.get_status()

        assert status["pool_id"] == "test-pool-123"

    def test_get_status_returns_running_state(self):
        """Test that get_status returns running state."""
        pool = WorkerPool(pool_id="test-pool")
        pool.running = True
        status = pool.get_status()

        assert status["running"] is True

    def test_get_status_returns_workers_count(self):
        """Test that get_status returns workers count."""
        pool = WorkerPool(pool_id="test-pool")
        pool.workers = [MagicMock(), MagicMock(), MagicMock()]
        status = pool.get_status()

        assert status["workers_count"] == 3

    def test_get_status_returns_queue_size(self):
        """Test that get_status returns queue size."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue.qsize = MagicMock(return_value=5)
        status = pool.get_status()

        assert status["queue_size"] == 5

    def test_get_status_returns_statistics(self):
        """Test that get_status returns task statistics."""
        pool = WorkerPool(pool_id="test-pool")
        pool.tasks_submitted = 10
        pool.tasks_completed = 8
        pool.tasks_failed = 2

        status = pool.get_status()

        assert status["tasks_submitted"] == 10
        assert status["tasks_completed"] == 8
        assert status["tasks_failed"] == 2

    def test_get_status_calculates_success_rate_with_no_tasks(self):
        """Test that get_status calculates success rate as 1.0 with no tasks."""
        pool = WorkerPool(pool_id="test-pool")
        pool.tasks_submitted = 0

        status = pool.get_status()

        assert status["success_rate"] == 1.0

    def test_get_status_calculates_success_rate_with_tasks(self):
        """Test that get_status calculates correct success rate."""
        pool = WorkerPool(pool_id="test-pool")
        pool.tasks_submitted = 10
        pool.tasks_completed = 8
        pool.tasks_failed = 2

        status = pool.get_status()

        assert status["success_rate"] == 0.8

    def test_get_status_returns_created_at_isoformat(self):
        """Test that get_status returns created_at in ISO format."""
        pool = WorkerPool(pool_id="test-pool")
        status = pool.get_status()

        assert "created_at" in status
        assert isinstance(status["created_at"], str)

    def test_get_status_returns_started_at_when_set(self):
        """Test that get_status returns started_at when pool has started."""
        pool = WorkerPool(pool_id="test-pool")
        pool.started_at = datetime.now(UTC)

        status = pool.get_status()

        assert status["started_at"] is not None

    def test_get_status_returns_none_for_started_at_when_not_started(self):
        """Test that get_status returns None for started_at when not started."""
        pool = WorkerPool(pool_id="test-pool")

        status = pool.get_status()

        assert status["started_at"] is None

    def test_get_status_includes_worker_statuses(self):
        """Test that get_status includes status of all workers."""
        pool = WorkerPool(pool_id="test-pool")

        mock_workers = [MagicMock() for _ in range(WORKERS_PER_POOL)]
        for i, w in enumerate(mock_workers):
            w.get_status = MagicMock(return_value={"worker_id": f"w{i}"})
        pool.workers = mock_workers

        status = pool.get_status()

        assert "workers" in status
        assert len(status["workers"]) == WORKERS_PER_POOL


class TestWorkerPoolRepr:
    """Tests for WorkerPool.__repr__ method."""

    def test_repr_includes_pool_id(self):
        """Test that __repr__ includes pool_id."""
        pool = WorkerPool(pool_id="my-test-pool")
        repr_str = repr(pool)

        assert "my-test-pool" in repr_str

    def test_repr_includes_running_state(self):
        """Test that __repr__ includes running state."""
        pool = WorkerPool(pool_id="test-pool")
        pool.running = True
        repr_str = repr(pool)

        assert "running=True" in repr_str

    def test_repr_includes_workers_count(self):
        """Test that __repr__ includes workers count."""
        pool = WorkerPool(pool_id="test-pool")
        pool.workers = [MagicMock(), MagicMock()]
        repr_str = repr(pool)

        assert "workers=2" in repr_str

    def test_repr_includes_queue_size(self):
        """Test that __repr__ includes queue size."""
        pool = WorkerPool(pool_id="test-pool")
        pool.task_queue.qsize = MagicMock(return_value=7)
        repr_str = repr(pool)

        assert "queue_size=7" in repr_str


# =============================================================================
# Test Classes - PoolManager
# =============================================================================


class TestPoolManagerInit:
    """Tests for PoolManager.__init__ method."""

    def test_init_creates_empty_pools_dict(self):
        """Test that __init__ creates empty pools dictionary."""
        manager = PoolManager()
        assert manager.pools == {}

    def test_init_creates_lock(self):
        """Test that __init__ creates asyncio Lock."""
        manager = PoolManager()
        assert isinstance(manager._lock, asyncio.Lock)

    def test_init_sets_running_false(self):
        """Test that __init__ sets running state to False."""
        manager = PoolManager()
        assert manager.running is False


class TestPoolManagerStart:
    """Tests for PoolManager.start method."""

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self):
        """Test that start sets running state to True."""
        manager = PoolManager()
        await manager.start()
        assert manager.running is True

    @pytest.mark.asyncio
    async def test_start_idempotent_when_already_running(self):
        """Test that start is idempotent when already running."""
        manager = PoolManager()
        manager.running = True

        await manager.start()

        # Should not change anything
        assert manager.running is True


class TestPoolManagerStop:
    """Tests for PoolManager.stop method."""

    @pytest.mark.asyncio
    async def test_stop_returns_when_not_running(self):
        """Test that stop returns immediately if not running."""
        manager = PoolManager()
        manager.running = False

        await manager.stop()

        assert manager.running is False

    @pytest.mark.asyncio
    async def test_stop_shuts_down_all_pools(self):
        """Test that stop shuts down all pools."""
        manager = PoolManager()
        manager.running = True

        mock_pool1 = MagicMock()
        mock_pool1.shutdown = AsyncMock()
        mock_pool2 = MagicMock()
        mock_pool2.shutdown = AsyncMock()

        manager.pools = {"pool1": mock_pool1, "pool2": mock_pool2}

        async def mock_gather(*coroutines, return_exceptions=False):
            for coro in coroutines:
                try:
                    await coro
                except Exception:
                    pass
            return []

        with patch("asyncio.gather", side_effect=mock_gather):
            await manager.stop()

            mock_pool1.shutdown.assert_called_once()
            mock_pool2.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_clears_pools_dict(self):
        """Test that stop clears the pools dictionary."""
        manager = PoolManager()
        manager.running = True

        mock_pool = MagicMock()
        mock_pool.shutdown = AsyncMock()
        manager.pools = {"pool1": mock_pool}

        async def mock_gather(*coroutines, return_exceptions=False):
            for coro in coroutines:
                try:
                    await coro
                except Exception:
                    pass
            return []

        with patch("asyncio.gather", side_effect=mock_gather):
            await manager.stop()

        assert manager.pools == {}

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        """Test that stop sets running state to False."""
        manager = PoolManager()
        manager.running = True

        mock_pool = MagicMock()
        mock_pool.shutdown = AsyncMock()
        manager.pools = {"pool1": mock_pool}

        async def mock_gather(*coroutines, return_exceptions=False):
            for coro in coroutines:
                try:
                    await coro
                except Exception:
                    pass
            return []

        with patch("asyncio.gather", side_effect=mock_gather):
            await manager.stop()

        assert manager.running is False


class TestPoolManagerCreatePool:
    """Tests for PoolManager.create_pool method."""

    @pytest.mark.asyncio
    async def test_create_pool_with_auto_id(self):
        """Test that create_pool generates pool_id if not provided."""
        manager = PoolManager()

        with patch("session_buddy.pools.WorkerPool") as MockPool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.pool_id = "pool_abc12345"
            mock_pool_instance.initialize = AsyncMock()
            MockPool.return_value = mock_pool_instance

            pool = await manager.create_pool()

            MockPool.assert_called_once_with(pool_id=None)
            assert pool.pool_id == "pool_abc12345"

    @pytest.mark.asyncio
    async def test_create_pool_with_custom_id(self):
        """Test that create_pool uses provided pool_id."""
        manager = PoolManager()

        with patch("session_buddy.pools.WorkerPool") as MockPool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.pool_id = "custom-pool-id"
            mock_pool_instance.initialize = AsyncMock()
            MockPool.return_value = mock_pool_instance

            pool = await manager.create_pool(pool_id="custom-pool-id")

            MockPool.assert_called_once_with(pool_id="custom-pool-id")

    @pytest.mark.asyncio
    async def test_create_pool_raises_on_duplicate_id(self):
        """Test that create_pool raises ValueError for duplicate pool_id."""
        manager = PoolManager()

        mock_existing_pool = MagicMock()
        manager.pools = {"existing-pool": mock_existing_pool}

        with pytest.raises(ValueError, match="already exists"):
            await manager.create_pool(pool_id="existing-pool")

    @pytest.mark.asyncio
    async def test_create_pool_initializes_new_pool(self):
        """Test that create_pool initializes the new pool."""
        manager = PoolManager()

        with patch("session_buddy.pools.WorkerPool") as MockPool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.pool_id = "new-pool"
            mock_pool_instance.initialize = AsyncMock()
            MockPool.return_value = mock_pool_instance

            await manager.create_pool()

            mock_pool_instance.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_pool_adds_to_pools_dict(self):
        """Test that create_pool adds new pool to pools dictionary."""
        manager = PoolManager()

        with patch("session_buddy.pools.WorkerPool") as MockPool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.pool_id = "added-pool"
            mock_pool_instance.initialize = AsyncMock()
            MockPool.return_value = mock_pool_instance

            await manager.create_pool()

            assert "added-pool" in manager.pools
            assert manager.pools["added-pool"] == mock_pool_instance

    @pytest.mark.asyncio
    async def test_create_pool_returns_created_pool(self):
        """Test that create_pool returns the created pool."""
        manager = PoolManager()

        with patch("session_buddy.pools.WorkerPool") as MockPool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.pool_id = "return-pool"
            mock_pool_instance.initialize = AsyncMock()
            MockPool.return_value = mock_pool_instance

            result = await manager.create_pool()

            assert result == mock_pool_instance


class TestPoolManagerGetPool:
    """Tests for PoolManager.get_pool method."""

    @pytest.mark.asyncio
    async def test_get_pool_returns_pool_when_found(self):
        """Test that get_pool returns pool when it exists."""
        manager = PoolManager()

        mock_pool = MagicMock()
        manager.pools = {"found-pool": mock_pool}

        result = await manager.get_pool("found-pool")

        assert result == mock_pool

    @pytest.mark.asyncio
    async def test_get_pool_returns_none_when_not_found(self):
        """Test that get_pool returns None when pool doesn't exist."""
        manager = PoolManager()
        manager.pools = {}

        result = await manager.get_pool("nonexistent-pool")

        assert result is None


class TestPoolManagerDeletePool:
    """Tests for PoolManager.delete_pool method."""

    @pytest.mark.asyncio
    async def test_delete_pool_returns_true_when_found(self):
        """Test that delete_pool returns True when pool exists."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.shutdown = AsyncMock()
        manager.pools = {"to-delete": mock_pool}

        result = await manager.delete_pool("to-delete")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_pool_removes_from_dict(self):
        """Test that delete_pool removes pool from dictionary."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.shutdown = AsyncMock()
        manager.pools = {"to-delete": mock_pool}

        await manager.delete_pool("to-delete")

        assert "to-delete" not in manager.pools

    @pytest.mark.asyncio
    async def test_delete_pool_shuts_down_pool(self):
        """Test that delete_pool calls shutdown on the pool."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.shutdown = AsyncMock()
        manager.pools = {"to-shutdown": mock_pool}

        await manager.delete_pool("to-shutdown")

        mock_pool.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_pool_returns_false_when_not_found(self):
        """Test that delete_pool returns False when pool doesn't exist."""
        manager = PoolManager()
        manager.pools = {}

        result = await manager.delete_pool("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_pool_passes_timeout_to_shutdown(self):
        """Test that delete_pool passes timeout to shutdown."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.shutdown = AsyncMock()
        manager.pools = {"pool": mock_pool}

        await manager.delete_pool("pool", timeout=15.0)

        mock_pool.shutdown.assert_called_once_with(timeout=15.0)


class TestPoolManagerListPools:
    """Tests for PoolManager.list_pools method."""

    @pytest.mark.asyncio
    async def test_list_pools_returns_empty_list_when_no_pools(self):
        """Test that list_pools returns empty list when no pools exist."""
        manager = PoolManager()
        manager.pools = {}

        result = await manager.list_pools()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_pools_returns_status_for_each_pool(self):
        """Test that list_pools returns status dictionary for each pool."""
        manager = PoolManager()

        mock_pool1 = MagicMock()
        mock_pool1.get_status = MagicMock(return_value={"pool_id": "pool1"})
        mock_pool2 = MagicMock()
        mock_pool2.get_status = MagicMock(return_value={"pool_id": "pool2"})

        manager.pools = {"pool1": mock_pool1, "pool2": mock_pool2}

        result = await manager.list_pools()

        assert len(result) == 2
        assert result[0]["pool_id"] == "pool1"
        assert result[1]["pool_id"] == "pool2"


class TestPoolManagerExecuteOnPool:
    """Tests for PoolManager.execute_on_pool method."""

    @pytest.mark.asyncio
    async def test_execute_on_pool_raises_when_pool_not_found(self):
        """Test that execute_on_pool raises ValueError when pool not found."""
        manager = PoolManager()
        manager.pools = {}

        with pytest.raises(ValueError, match="not found"):
            await manager.execute_on_pool("nonexistent-pool", "prompt")

    @pytest.mark.asyncio
    async def test_execute_on_pool_calls_pool_execute(self):
        """Test that execute_on_pool delegates to pool.execute."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.execute = AsyncMock(return_value="result")
        manager.pools = {"test-pool": mock_pool}

        result = await manager.execute_on_pool(
            "test-pool", "test prompt", context={"key": "value"}, timeout=30.0
        )

        mock_pool.execute.assert_called_once_with(
            prompt="test prompt", context={"key": "value"}, timeout=30.0
        )
        assert result == "result"

    @pytest.mark.asyncio
    async def test_execute_on_pool_passes_context(self):
        """Test that execute_on_pool passes context to pool.execute."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.execute = AsyncMock()
        manager.pools = {"pool": mock_pool}

        context = {"user": "testuser", "session": "abc123"}

        await manager.execute_on_pool("pool", "prompt", context=context)

        call_kwargs = mock_pool.execute.call_args[1]
        assert call_kwargs["context"] == context


class TestPoolManagerRouteTask:
    """Tests for PoolManager.route_task method."""

    @pytest.mark.asyncio
    async def test_route_task_raises_when_no_pools(self):
        """Test that route_task raises ValueError when no pools available."""
        manager = PoolManager()
        manager.pools = {}

        with pytest.raises(ValueError, match="No pools available"):
            await manager.route_task("test prompt")

    @pytest.mark.asyncio
    async def test_route_task_raises_on_unknown_selector(self):
        """Test that route_task raises ValueError for unknown selector."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.task_queue.qsize = MagicMock(return_value=0)
        mock_pool.execute = AsyncMock(return_value="result")
        mock_pool.pool_id = "test-pool"
        manager.pools = {"pool": mock_pool}

        with pytest.raises(ValueError, match="Unknown selector strategy"):
            await manager.route_task("prompt", selector="invalid_strategy")

    @pytest.mark.asyncio
    async def test_route_task_uses_least_loaded_selector(self):
        """Test that route_task selects pool with smallest queue for least_loaded."""
        manager = PoolManager()

        mock_pool1 = MagicMock()
        mock_pool1.task_queue.qsize = MagicMock(return_value=5)
        mock_pool1.pool_id = "pool1"

        mock_pool2 = MagicMock()
        mock_pool2.task_queue.qsize = MagicMock(return_value=2)  # Smallest
        mock_pool2.pool_id = "pool2"

        mock_pool3 = MagicMock()
        mock_pool3.task_queue.qsize = MagicMock(return_value=8)
        mock_pool3.pool_id = "pool3"

        manager.pools = {"pool1": mock_pool1, "pool2": mock_pool2, "pool3": mock_pool3}

        # Mock execute to return (pool_id, result)
        async def mock_execute(prompt, context=None, timeout=None):
            return "result"

        mock_pool1.execute = mock_execute
        mock_pool2.execute = mock_execute
        mock_pool3.execute = mock_execute

        pool_id, result = await manager.route_task("prompt", selector="least_loaded")

        assert pool_id == "pool2"

    @pytest.mark.asyncio
    async def test_route_task_uses_round_robin_selector(self):
        """Test that route_task selects first pool for round_robin."""
        manager = PoolManager()

        mock_pool1 = MagicMock()
        mock_pool1.task_queue.qsize = MagicMock(return_value=10)
        mock_pool1.pool_id = "pool1"

        mock_pool2 = MagicMock()
        mock_pool2.task_queue.qsize = MagicMock(return_value=2)
        mock_pool2.pool_id = "pool2"

        manager.pools = {"pool1": mock_pool1, "pool2": mock_pool2}

        async def mock_execute(prompt, context=None, timeout=None):
            return "result"

        mock_pool1.execute = mock_execute
        mock_pool2.execute = mock_execute

        pool_id, result = await manager.route_task("prompt", selector="round_robin")

        assert pool_id == "pool1"

    @pytest.mark.asyncio
    async def test_route_task_uses_random_selector(self):
        """Test that route_task uses random selection for random selector."""
        manager = PoolManager()

        mock_pool1 = MagicMock()
        mock_pool1.task_queue.qsize = MagicMock(return_value=5)
        mock_pool1.pool_id = "pool1"

        mock_pool2 = MagicMock()
        mock_pool2.task_queue.qsize = MagicMock(return_value=5)
        mock_pool2.pool_id = "pool2"

        manager.pools = {"pool1": mock_pool1, "pool2": mock_pool2}

        async def mock_execute(prompt, context=None, timeout=None):
            return "result"

        mock_pool1.execute = mock_execute
        mock_pool2.execute = mock_execute

        # Just verify it doesn't raise and returns a valid pool_id
        pool_id, result = await manager.route_task("prompt", selector="random")

        assert pool_id in ["pool1", "pool2"]

    @pytest.mark.asyncio
    async def test_route_task_returns_tuple_of_pool_id_and_result(self):
        """Test that route_task returns (pool_id, result) tuple."""
        manager = PoolManager()

        mock_pool = MagicMock()
        mock_pool.task_queue.qsize = MagicMock(return_value=0)
        mock_pool.pool_id = "my-pool"
        mock_pool.execute = AsyncMock(return_value="my-result")
        manager.pools = {"my-pool": mock_pool}

        pool_id, result = await manager.route_task("prompt")

        assert pool_id == "my-pool"
        assert result == "my-result"


class TestPoolManagerGetHealthStatus:
    """Tests for PoolManager.get_health_status method."""

    @pytest.mark.asyncio
    async def test_get_health_status_returns_manager_running_status(self):
        """Test that get_health_status includes manager running state."""
        manager = PoolManager()
        manager.running = True
        manager.pools = {}

        result = await manager.get_health_status()

        assert result["pool_manager_running"] is True

    @pytest.mark.asyncio
    async def test_get_health_status_returns_zero_pools_count(self):
        """Test that get_health_status returns 0 pools when empty."""
        manager = PoolManager()
        manager.pools = {}

        result = await manager.get_health_status()

        assert result["pools_total"] == 0
        assert result["pools_healthy"] == 0

    @pytest.mark.asyncio
    async def test_get_health_status_counts_healthy_pools(self):
        """Test that get_health_status counts pools with healthy status."""
        manager = PoolManager()

        mock_pool1 = MagicMock()
        mock_pool1.health_check = AsyncMock(return_value={"status": "healthy"})

        mock_pool2 = MagicMock()
        mock_pool2.health_check = AsyncMock(return_value={"status": "degraded"})

        mock_pool3 = MagicMock()
        mock_pool3.health_check = AsyncMock(return_value={"status": "healthy"})

        manager.pools = {
            "pool1": mock_pool1,
            "pool2": mock_pool2,
            "pool3": mock_pool3,
        }

        result = await manager.get_health_status()

        assert result["pools_total"] == 3
        assert result["pools_healthy"] == 2

    @pytest.mark.asyncio
    async def test_get_health_status_includes_pool_details(self):
        """Test that get_health_status includes details for each pool."""
        manager = PoolManager()

        mock_pool1 = MagicMock()
        mock_pool1.health_check = AsyncMock(return_value={"pool_id": "pool1"})

        mock_pool2 = MagicMock()
        mock_pool2.health_check = AsyncMock(return_value={"pool_id": "pool2"})

        manager.pools = {"pool1": mock_pool1, "pool2": mock_pool2}

        result = await manager.get_health_status()

        assert len(result["pool_details"]) == 2

    @pytest.mark.asyncio
    async def test_get_health_status_handles_exceptions_from_pools(self):
        """Test that get_health_status handles exceptions from pool health checks."""
        manager = PoolManager()

        mock_pool1 = MagicMock()
        mock_pool1.health_check = AsyncMock(side_effect=RuntimeError("health failed"))

        mock_pool2 = MagicMock()
        mock_pool2.health_check = AsyncMock(return_value={"status": "healthy"})

        manager.pools = {"pool1": mock_pool1, "pool2": mock_pool2}

        result = await manager.get_health_status()

        # Should still return results, just not count unhealthy ones
        assert result["pools_total"] == 2


class TestPoolManagerRepr:
    """Tests for PoolManager.__repr__ method."""

    def test_repr_includes_running_state(self):
        """Test that __repr__ includes running state."""
        manager = PoolManager()
        manager.running = True

        repr_str = repr(manager)

        assert "running=True" in repr_str

    def test_repr_includes_pools_count(self):
        """Test that __repr__ includes pools count."""
        manager = PoolManager()
        manager.pools = {"p1": MagicMock(), "p2": MagicMock(), "p3": MagicMock()}

        repr_str = repr(manager)

        assert "pools=3" in repr_str


# =============================================================================
# Test Classes - get_pool_manager (Global Instance)
# =============================================================================


class TestGetPoolManager:
    """Tests for get_pool_manager function."""

    @pytest.mark.asyncio
    async def test_get_pool_manager_returns_manager(self):
        """Test that get_pool_manager returns a PoolManager instance."""
        result = await get_pool_manager()
        assert isinstance(result, PoolManager)

    @pytest.mark.asyncio
    async def test_get_pool_manager_returns_same_instance(self):
        """Test that get_pool_manager returns singleton instance."""
        # Reset global state first
        import session_buddy.pools as pools_module

        pools_module._global_pool_manager = None

        manager1 = await get_pool_manager()
        manager2 = await get_pool_manager()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_get_pool_manager_starts_manager(self):
        """Test that get_pool_manager starts the manager."""
        import session_buddy.pools as pools_module

        pools_module._global_pool_manager = None

        manager = await get_pool_manager()

        assert manager.running is True


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_workers_per_pool_is_three(self):
        """Test that WORKERS_PER_POOL is fixed at 3."""
        assert WORKERS_PER_POOL == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])