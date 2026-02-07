"""Integration tests for Session-Buddy worker pools."""

import asyncio
import pytest

from session_buddy.pools import PoolManager, WorkerPool, get_pool_manager


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pool_lifecycle():
    """Test complete pool lifecycle: create, execute, shutdown."""
    pool = WorkerPool(pool_id="integration_test_pool")

    # Initialize pool
    await pool.initialize()
    assert pool.running is True
    assert len(pool.workers) == 3

    # Execute tasks
    result1 = await pool.execute(prompt="Task 1")
    result2 = await pool.execute(prompt="Task 2")

    assert result1 is not None
    assert result2 is not None
    assert pool.tasks_completed == 2

    # Shutdown pool
    await pool.shutdown()
    assert pool.running is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_pool_coordination():
    """Test coordinating multiple pools simultaneously."""
    manager = PoolManager()
    await manager.start()

    # Create multiple pools
    pool1 = await manager.create_pool(pool_id="coord_pool_1")
    pool2 = await manager.create_pool(pool_id="coord_pool_2")
    pool3 = await manager.create_pool(pool_id="coord_pool_3")

    # Execute tasks across pools
    results = await asyncio.gather(
        pool1.execute(prompt="Pool 1 task"),
        pool2.execute(prompt="Pool 2 task"),
        pool3.execute(prompt="Pool 3 task"),
    )

    assert len(results) == 3
    assert all(r is not None for r in results)

    await manager.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pool_scaling_behavior():
    """Test pool behavior under load."""
    pool = WorkerPool(pool_id="load_test_pool")
    await pool.initialize()

    # Submit 20 tasks (more than workers)
    tasks = [
        "Task " + str(i)
        for i in range(20)
    ]

    results = await pool.execute_batch(prompts=tasks, timeout=30.0)

    # All tasks should complete
    assert len(results) == 20
    assert pool.tasks_completed >= 18  # Allow for some failures

    await pool.shutdown()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_failure_handling():
    """Test that pool continues operating despite worker failures."""
    pool = WorkerPool(pool_id="failure_test_pool")
    await pool.initialize()

    # Submit a mix of valid and potentially failing tasks
    results = await asyncio.gather(
        *[pool.execute(prompt=f"Task {i}") for i in range(10)],
        return_exceptions=True,
    )

    # Pool should still be operational
    assert pool.running is True

    # At least some tasks should succeed
    successful = sum(1 for r in results if not isinstance(r, Exception))
    assert successful >= 8

    await pool.shutdown()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pool_health_monitoring():
    """Test health monitoring across multiple pools."""
    manager = PoolManager()
    await manager.start()

    # Create pools
    await manager.create_pool(pool_id="health_pool_1")
    await manager.create_pool(pool_id="health_pool_2")

    # Get health status
    health = await manager.get_health_status()

    assert health["pools_total"] == 2
    assert health["pools_healthy"] == 2

    # Execute tasks and check health again
    await manager.execute_on_pool("health_pool_1", "Health check task")

    health_after = await manager.get_health_status()
    assert health_after["pools_healthy"] == 2

    await manager.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_routing_strategies():
    """Test different task routing strategies."""
    manager = PoolManager()
    await manager.start()

    # Create 3 pools
    for i in range(1, 4):
        await manager.create_pool(pool_id=f"route_pool_{i}")

    # Test least_loaded
    pool_id1, _ = await manager.route_task("Test 1", selector="least_loaded")
    assert pool_id1.startswith("route_pool_")

    # Test round_robin
    for _ in range(5):
        pool_id2, _ = await manager.route_task("Test 2", selector="round_robin")
        assert pool_id2.startswith("route_pool_")

    # Test random
    pool_id3, _ = await manager.route_task("Test 3", selector="random")
    assert pool_id3.startswith("route_pool_")

    await manager.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_pool_operations():
    """Test concurrent operations on multiple pools."""
    manager = PoolManager()
    await manager.start()

    # Create pools
    pools = []
    for i in range(5):
        pool = await manager.create_pool(pool_id=f"concurrent_pool_{i}")
        pools.append(pool)

    # Execute tasks concurrently on all pools
    async def execute_on_pool(pool):
        results = []
        for j in range(5):
            result = await pool.execute(prompt=f"Pool task {j}")
            results.append(result)
        return results

    pool_results = await asyncio.gather(*[execute_on_pool(p) for p in pools])

    # Verify results
    assert len(pool_results) == 5
    for results in pool_results:
        assert len(results) == 5
        assert all(r is not None for r in results)

    await manager.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_global_pool_manager_persistence():
    """Test that global pool manager persists across calls."""
    # Get global manager
    manager1 = await get_pool_manager()
    await manager1.create_pool(pool_id="persistent_pool")

    # Get global manager again
    manager2 = await get_pool_manager()

    # Should have the pool created earlier
    pool = await manager2.get_pool("persistent_pool")
    assert pool is not None
    assert pool.pool_id == "persistent_pool"

    # Cleanup
    await manager2.delete_pool("persistent_pool")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
