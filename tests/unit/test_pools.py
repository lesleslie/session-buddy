"""Tests for Session-Buddy worker pool implementation."""

import asyncio
import pytest

from session_buddy.pools import PoolManager, WorkerPool, WORKERS_PER_POOL, get_pool_manager
from session_buddy.worker import Task, Worker


@pytest.mark.asyncio
async def test_worker_task_creation():
    """Test that Task objects are created correctly."""
    task = Task(
        task_id="test_task_1",
        prompt="Write Python code",
        context={"repo": "/test/repo"},
    )

    assert task.task_id == "test_task_1"
    assert task.prompt == "Write Python code"
    assert task.context == {"repo": "/test/repo"}
    assert task.status == "pending"
    assert task.result is None
    assert task.error is None


@pytest.mark.asyncio
async def test_worker_task_result():
    """Test that task results can be set and retrieved."""
    task = Task(task_id="test_task_2", prompt="Test task")

    # Set result
    await task.set_result({"output": "Task completed"})

    # Verify result is set
    assert task.status == "completed"
    assert task.result == {"output": "Task completed"}
    assert task.error is None
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_worker_task_error():
    """Test that task errors can be set and retrieved."""
    task = Task(task_id="test_task_3", prompt="Test task")

    # Set error
    test_error = Exception("Task failed")
    await task.set_error(test_error)

    # Verify error is set
    assert task.status == "failed"
    assert task.error == test_error
    assert task.result is None


@pytest.mark.asyncio
async def test_worker_task_wait_for_result():
    """Test that wait_for_result blocks until result is set."""
    task = Task(task_id="test_task_4", prompt="Test task")

    # Create a task to set result after delay
    async def set_delayed_result():
        await asyncio.sleep(0.1)
        await task.set_result("delayed result")

    asyncio.create_task(set_delayed_result())

    # Wait for result (should block until set)
    result = await task.wait_for_result(timeout=1.0)

    assert result == "delayed result"
    assert task.status == "completed"


@pytest.mark.asyncio
async def test_worker_task_timeout():
    """Test that wait_for_result raises TimeoutError when timeout exceeded."""
    task = Task(task_id="test_task_5", prompt="Test task")

    # Don't set result, should timeout
    with pytest.raises(asyncio.TimeoutError):
        await task.wait_for_result(timeout=0.1)


@pytest.mark.asyncio
async def test_worker_initialization():
    """Test that Worker initializes correctly."""
    queue = asyncio.Queue()
    worker = Worker(worker_id="test_worker_1", queue=queue, pool_id="test_pool")

    assert worker.worker_id == "test_worker_1"
    assert worker.queue == queue
    assert worker.pool_id == "test_pool"
    assert worker.running is False
    assert worker.tasks_processed == 0
    assert worker.tasks_succeeded == 0
    assert worker.tasks_failed == 0


@pytest.mark.asyncio
async def test_worker_start_stop():
    """Test that worker can be started and stopped."""
    queue = asyncio.Queue()
    worker = Worker(worker_id="test_worker_2", queue=queue, pool_id="test_pool")

    # Start worker
    await worker.start()
    assert worker.running is True
    assert worker._task is not None

    # Stop worker
    await worker.stop(timeout=1.0)
    assert worker.running is False


@pytest.mark.asyncio
async def test_worker_processes_task():
    """Test that worker processes tasks from queue."""
    queue = asyncio.Queue()
    worker = Worker(worker_id="test_worker_3", queue=queue, pool_id="test_pool")

    await worker.start()

    # Create and submit task
    task = Task(task_id="worker_test_1", prompt="Test prompt")
    await queue.put(task)

    # Wait for task to complete
    result = await task.wait_for_result(timeout=2.0)

    assert result is not None
    assert task.status == "completed"
    assert worker.tasks_processed == 1
    assert worker.tasks_succeeded == 1

    await worker.stop()


@pytest.mark.asyncio
async def test_worker_health_check():
    """Test worker health check functionality."""
    queue = asyncio.Queue()
    worker = Worker(worker_id="test_worker_4", queue=queue, pool_id="test_pool")

    # Not running yet - should be unhealthy
    health = await worker.health_check()
    assert health is False

    # Start worker - should be healthy
    await worker.start()
    health = await worker.health_check()
    assert health is True

    await worker.stop()


@pytest.mark.asyncio
async def test_worker_pool_initialization():
    """Test that WorkerPool initializes exactly 3 workers."""
    pool = WorkerPool(pool_id="test_pool_1")
    await pool.initialize()

    assert pool.running is True
    assert len(pool.workers) == WORKERS_PER_POOL
    assert pool.started_at is not None

    # Verify all workers are running
    for worker in pool.workers:
        assert worker.running is True

    await pool.shutdown()


@pytest.mark.asyncio
async def test_worker_pool_execute_task():
    """Test that pool can execute a single task."""
    pool = WorkerPool(pool_id="test_pool_2")
    await pool.initialize()

    result = await pool.execute(prompt="Write tests", timeout=2.0)

    assert result is not None
    assert "worker_id" in result
    assert "pool_id" in result
    assert result["pool_id"] == "test_pool_2"
    assert pool.tasks_submitted == 1
    assert pool.tasks_completed == 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_worker_pool_execute_batch():
    """Test that pool can execute multiple tasks in parallel."""
    pool = WorkerPool(pool_id="test_pool_3")
    await pool.initialize()

    prompts = ["Task 1", "Task 2", "Task 3", "Task 4", "Task 5"]

    results = await pool.execute_batch(prompts=prompts, timeout=5.0)

    assert len(results) == 5
    assert pool.tasks_submitted == 5
    assert pool.tasks_completed >= 3  # At least some should succeed

    await pool.shutdown()


@pytest.mark.asyncio
async def test_worker_pool_not_running_error():
    """Test that pool raises error when executing while not running."""
    pool = WorkerPool(pool_id="test_pool_4")

    with pytest.raises(RuntimeError, match="not running"):
        await pool.execute(prompt="Test")


@pytest.mark.asyncio
async def test_worker_pool_health_check():
    """Test pool health check functionality."""
    pool = WorkerPool(pool_id="test_pool_5")
    await pool.initialize()

    health = await pool.health_check()

    assert health["status"] == "healthy"
    assert health["pool_id"] == "test_pool_5"
    assert health["workers_total"] == WORKERS_PER_POOL
    assert health["workers_healthy"] == WORKERS_PER_POOL

    await pool.shutdown()


@pytest.mark.asyncio
async def test_worker_pool_get_status():
    """Test that pool returns status correctly."""
    pool = WorkerPool(pool_id="test_pool_6")
    await pool.initialize()

    status = pool.get_status()

    assert status["pool_id"] == "test_pool_6"
    assert status["running"] is True
    assert status["workers_count"] == WORKERS_PER_POOL
    assert status["created_at"] is not None
    assert status["started_at"] is not None

    await pool.shutdown()


@pytest.mark.asyncio
async def test_pool_manager_initialization():
    """Test that PoolManager initializes correctly."""
    manager = PoolManager()
    await manager.start()

    assert manager.running is True
    assert len(manager.pools) == 0

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_create_pool():
    """Test that PoolManager can create pools."""
    manager = PoolManager()
    await manager.start()

    pool = await manager.create_pool(pool_id="manager_test_pool")

    assert pool is not None
    assert pool.pool_id == "manager_test_pool"
    assert pool.running is True
    assert len(manager.pools) == 1

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_duplicate_pool_error():
    """Test that creating duplicate pool raises error."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="duplicate_pool")

    with pytest.raises(ValueError, match="already exists"):
        await manager.create_pool(pool_id="duplicate_pool")

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_get_pool():
    """Test that PoolManager can retrieve pools."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="get_test_pool")
    pool = await manager.get_pool("get_test_pool")

    assert pool is not None
    assert pool.pool_id == "get_test_pool"

    # Non-existent pool
    pool = await manager.get_pool("non_existent")
    assert pool is None

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_delete_pool():
    """Test that PoolManager can delete pools."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="delete_test_pool")
    assert len(manager.pools) == 1

    deleted = await manager.delete_pool("delete_test_pool")

    assert deleted is True
    assert len(manager.pools) == 0

    # Try deleting non-existent pool
    deleted = await manager.delete_pool("non_existent")
    assert deleted is False

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_execute_on_pool():
    """Test that PoolManager can execute tasks on specific pools."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="execute_test_pool")

    result = await manager.execute_on_pool(
        pool_id="execute_test_pool",
        prompt="Execute via manager",
        timeout=2.0,
    )

    assert result is not None
    assert result["pool_id"] == "execute_test_pool"

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_route_task_least_loaded():
    """Test that PoolManager routes tasks using least_loaded strategy."""
    manager = PoolManager()
    await manager.start()

    # Create multiple pools
    await manager.create_pool(pool_id="route_pool_1")
    await manager.create_pool(pool_id="route_pool_2")

    pool_id, result = await manager.route_task(
        prompt="Routed task",
        selector="least_loaded",
        timeout=2.0,
    )

    assert pool_id in ("route_pool_1", "route_pool_2")
    assert result is not None

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_route_task_round_robin():
    """Test that PoolManager routes tasks using round_robin strategy."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="rr_pool_1")
    await manager.create_pool(pool_id="rr_pool_2")

    # Execute multiple tasks - should distribute
    for _ in range(4):
        pool_id, result = await manager.route_task(
            prompt="Round robin task",
            selector="round_robin",
            timeout=2.0,
        )
        assert pool_id in ("rr_pool_1", "rr_pool_2")
        assert result is not None

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_route_task_random():
    """Test that PoolManager routes tasks using random strategy."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="random_pool_1")
    await manager.create_pool(pool_id="random_pool_2")

    pool_id, result = await manager.route_task(
        prompt="Random task",
        selector="random",
        timeout=2.0,
    )

    assert pool_id in ("random_pool_1", "random_pool_2")
    assert result is not None

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_route_task_no_pools():
    """Test that routing fails when no pools available."""
    manager = PoolManager()
    await manager.start()

    with pytest.raises(ValueError, match="No pools available"):
        await manager.route_task(prompt="Test", selector="least_loaded")

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_list_pools():
    """Test that PoolManager can list all pools."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="list_pool_1")
    await manager.create_pool(pool_id="list_pool_2")

    pools = await manager.list_pools()

    assert len(pools) == 2
    pool_ids = {p["pool_id"] for p in pools}
    assert pool_ids == {"list_pool_1", "list_pool_2"}

    await manager.stop()


@pytest.mark.asyncio
async def test_pool_manager_get_health_status():
    """Test that PoolManager returns health status for all pools."""
    manager = PoolManager()
    await manager.start()

    await manager.create_pool(pool_id="health_pool_1")
    await manager.create_pool(pool_id="health_pool_2")

    health = await manager.get_health_status()

    assert health["pool_manager_running"] is True
    assert health["pools_total"] == 2
    assert health["pools_healthy"] == 2
    assert len(health["pool_details"]) == 2

    await manager.stop()


@pytest.mark.asyncio
async def test_global_pool_manager_singleton():
    """Test that global pool manager is a singleton."""
    manager1 = await get_pool_manager()
    manager2 = await get_pool_manager()

    # Should be the same instance
    assert manager1 is manager2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
