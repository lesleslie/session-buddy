"""MCP tools for Session-Buddy worker pool management.

This module exposes pool management functionality through the MCP protocol
for remote control and monitoring of worker pools.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from session_buddy.pools import get_pool_manager

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


async def pool_create(pool_id: str | None = None) -> dict[str, Any]:
    """Create a new worker pool with exactly 3 workers.

    Args:
        pool_id: Optional pool identifier (auto-generated if not provided)

    Returns:
        Dictionary with pool status and information

    Example:
        >>> pool_create("my_pool")
        {
            "pool_id": "my_pool",
            "status": "running",
            "workers_count": 3,
            "queue_size": 0
        }
    """
    manager = await get_pool_manager()

    pool = await manager.create_pool(pool_id=pool_id)
    status = pool.get_status()

    logger.info(f"Created pool {pool.pool_id}")

    return {
        "success": True,
        "pool_id": pool.pool_id,
        "status": status["status"],
        "workers_count": status["workers_count"],
        "queue_size": status["queue_size"],
        "created_at": status["created_at"],
    }


async def pool_execute(
    pool_id: str,
    prompt: str,
    context: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Execute a task on a specific pool.

    Args:
        pool_id: Pool identifier
        prompt: Task prompt/instruction
        context: Optional execution context
        timeout: Maximum time to wait for result (seconds)

    Returns:
        Dictionary with execution result

    Example:
        >>> pool_execute("my_pool", "Write Python code", timeout=30.0)
        {
            "success": True,
            "pool_id": "my_pool",
            "worker_id": "my_pool-worker-1",
            "result": {...}
        }
    """
    manager = await get_pool_manager()

    try:
        result = await manager.execute_on_pool(
            pool_id=pool_id,
            prompt=prompt,
            context=context,
            timeout=timeout,
        )

        logger.info(f"Executed task on pool {pool_id}")

        return {
            "success": True,
            "pool_id": pool_id,
            "worker_id": result.get("worker_id"),
            "result": result,
        }
    except Exception as e:
        logger.error(f"Failed to execute task on pool {pool_id}: {e}")
        return {
            "success": False,
            "pool_id": pool_id,
            "error": str(e),
        }


async def pool_execute_batch(
    pool_id: str,
    prompts: list[str],
    context: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Execute multiple tasks in parallel on a pool.

    Args:
        pool_id: Pool identifier
        prompts: List of task prompts
        context: Optional shared execution context
        timeout: Maximum time to wait for each result (seconds)

    Returns:
        Dictionary with batch execution results

    Example:
        >>> pool_execute_batch("my_pool", ["Task 1", "Task 2", "Task 3"])
        {
            "success": True,
            "pool_id": "my_pool",
            "results_count": 3,
            "results": [...]
        }
    """
    manager = await get_pool_manager()

    try:
        pool = await manager.get_pool(pool_id)
        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        results = await pool.execute_batch(
            prompts=prompts,
            context=context,
            timeout=timeout,
        )

        logger.info(f"Executed batch of {len(prompts)} tasks on pool {pool_id}")

        return {
            "success": True,
            "pool_id": pool_id,
            "results_count": len(results),
            "results": [str(r) for r in results],
        }
    except Exception as e:
        logger.error(f"Failed to execute batch on pool {pool_id}: {e}")
        return {
            "success": False,
            "pool_id": pool_id,
            "error": str(e),
        }


async def pool_route_task(
    prompt: str,
    context: dict[str, Any] | None = None,
    selector: str = "least_loaded",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Route task to best available pool using specified strategy.

    Args:
        prompt: Task prompt/instruction
        context: Optional execution context
        selector: Pool selection strategy (least_loaded, round_robin, random)
        timeout: Maximum time to wait for result (seconds)

    Returns:
        Dictionary with routed execution result

    Example:
        >>> pool_route_task("Write tests", selector="least_loaded")
        {
            "success": True,
            "pool_id": "pool_abc123",
            "strategy": "least_loaded",
            "result": {...}
        }
    """
    manager = await get_pool_manager()

    try:
        pool_id, result = await manager.route_task(
            prompt=prompt,
            context=context,
            selector=selector,
            timeout=timeout,
        )

        logger.info(f"Routed task to pool {pool_id} using {selector} strategy")

        return {
            "success": True,
            "pool_id": pool_id,
            "strategy": selector,
            "result": result,
        }
    except Exception as e:
        logger.error(f"Failed to route task: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def pool_list() -> dict[str, Any]:
    """List all worker pools.

    Returns:
        Dictionary with list of pools and their status

    Example:
        >>> pool_list()
        {
            "success": True,
            "pools_count": 2,
            "pools": [
                {"pool_id": "pool_1", "running": true, "workers_count": 3},
                {"pool_id": "pool_2", "running": true, "workers_count": 3}
            ]
        }
    """
    manager = await get_pool_manager()

    pools = await manager.list_pools()

    return {
        "success": True,
        "pools_count": len(pools),
        "pools": pools,
    }


async def pool_status(pool_id: str) -> dict[str, Any]:
    """Get detailed status of a specific pool.

    Args:
        pool_id: Pool identifier

    Returns:
        Dictionary with pool status and worker details

    Example:
        >>> pool_status("my_pool")
        {
            "success": True,
            "pool_id": "my_pool",
            "running": true,
            "workers": [...],
            "tasks_submitted": 10,
            "tasks_completed": 8
        }
    """
    manager = await get_pool_manager()

    try:
        pool = await manager.get_pool(pool_id)
        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        status = pool.get_status()

        return {
            "success": True,
            "pool_id": pool_id,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Failed to get status for pool {pool_id}: {e}")
        return {
            "success": False,
            "pool_id": pool_id,
            "error": str(e),
        }


async def pool_health(pool_id: str | None = None) -> dict[str, Any]:
    """Get health status of pools.

    Args:
        pool_id: Optional pool identifier. If not provided, returns health for all pools.

    Returns:
        Dictionary with health status

    Example:
        >>> pool_health("my_pool")
        {
            "success": True,
            "pool_id": "my_pool",
            "status": "healthy",
            "workers_healthy": 3,
            "workers_total": 3
        }
    """
    manager = await get_pool_manager()

    try:
        if pool_id:
            # Get health for specific pool
            pool = await manager.get_pool(pool_id)
            if not pool:
                raise ValueError(f"Pool {pool_id} not found")

            health = await pool.health_check()

            return {
                "success": True,
                "pool_id": pool_id,
                "health": health,
            }
        else:
            # Get health for all pools
            health = await manager.get_health_status()

            return {
                "success": True,
                "health": health,
            }
    except Exception as e:
        logger.error(f"Failed to get health status: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def pool_delete(pool_id: str, timeout: float = 5.0) -> dict[str, Any]:
    """Delete a worker pool.

    Args:
        pool_id: Pool identifier
        timeout: Maximum time to wait for pool shutdown (seconds)

    Returns:
        Dictionary with deletion result

    Example:
        >>> pool_delete("my_pool")
        {
            "success": True,
            "pool_id": "my_pool",
            "deleted": true
        }
    """
    manager = await get_pool_manager()

    try:
        deleted = await manager.delete_pool(pool_id, timeout=timeout)

        logger.info(f"Deleted pool {pool_id}: {deleted}")

        return {
            "success": True,
            "pool_id": pool_id,
            "deleted": deleted,
        }
    except Exception as e:
        logger.error(f"Failed to delete pool {pool_id}: {e}")
        return {
            "success": False,
            "pool_id": pool_id,
            "error": str(e),
        }


async def pool_manager_status() -> dict[str, Any]:
    """Get status of the pool manager.

    Returns:
        Dictionary with pool manager status

    Example:
        >>> pool_manager_status()
        {
            "success": True,
            "running": true,
            "pools_total": 2,
            "pools_healthy": 2
        }
    """
    manager = await get_pool_manager()

    health = await manager.get_health_status()

    return {
        "success": True,
        "manager_running": manager.running,
        "health": health,
    }


def _register_pool_execution_tools(mcp: FastMCP) -> None:
    """Register pool task execution tools."""

    @mcp.tool()  # type: ignore[misc]
    async def create_pool(
        pool_id: str | None = None,
    ) -> str:
        """Create a new worker pool with exactly 3 workers.

        Args:
            pool_id: Optional pool identifier (auto-generated if not provided)

        Returns:
            Pool creation result message
        """
        result = await pool_create(pool_id=pool_id)
        if result["success"]:
            return f"✅ Created pool {result['pool_id']} with {result['workers_count']} workers"
        return f"❌ Failed to create pool: {result.get('error', 'Unknown error')}"

    @mcp.tool()  # type: ignore[misc]
    async def execute_on_pool(
        pool_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Execute a task on a specific pool.

        Args:
            pool_id: Pool identifier
            prompt: Task prompt/instruction
            context: Optional execution context
            timeout: Maximum time to wait for result (seconds)

        Returns:
            Task execution result message
        """
        result = await pool_execute(
            pool_id=pool_id,
            prompt=prompt,
            context=context,
            timeout=timeout,
        )
        if result["success"]:
            return f"✅ Task executed on pool {pool_id} by worker {result.get('worker_id', 'unknown')}"
        return f"❌ Failed to execute task: {result.get('error', 'Unknown error')}"

    @mcp.tool()  # type: ignore[misc]
    async def execute_batch_on_pool(
        pool_id: str,
        prompts: list[str],
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Execute multiple tasks in parallel on a pool.

        Args:
            pool_id: Pool identifier
            prompts: List of task prompts
            context: Optional shared execution context
            timeout: Maximum time to wait for each result (seconds)

        Returns:
            Batch execution result message
        """
        result = await pool_execute_batch(
            pool_id=pool_id,
            prompts=prompts,
            context=context,
            timeout=timeout,
        )
        if result["success"]:
            return f"✅ Executed {result['results_count']} tasks on pool {pool_id}"
        return f"❌ Failed to execute batch: {result.get('error', 'Unknown error')}"

    @mcp.tool()  # type: ignore[misc]
    async def route_to_pool(
        prompt: str,
        context: dict[str, Any] | None = None,
        selector: str = "least_loaded",
        timeout: float | None = None,
    ) -> str:
        """Route task to best available pool using specified strategy.

        Args:
            prompt: Task prompt/instruction
            context: Optional execution context
            selector: Pool selection strategy (least_loaded, round_robin, random)
            timeout: Maximum time to wait for result (seconds)

        Returns:
            Task routing result message
        """
        result = await pool_route_task(
            prompt=prompt,
            context=context,
            selector=selector,
            timeout=timeout,
        )
        if result["success"]:
            return f"✅ Routed task to pool {result['pool_id']} using {result['strategy']} strategy"
        return f"❌ Failed to route task: {result.get('error', 'Unknown error')}"


def _register_pool_monitoring_tools(mcp: FastMCP) -> None:
    """Register pool monitoring and status tools."""

    @mcp.tool()  # type: ignore[misc]
    async def list_pools() -> str:
        """List all worker pools.

        Returns:
            List of pools with status
        """
        result = await pool_list()
        pools_info = "\n".join(
            f"  - {p['pool_id']}: running={p['running']}, workers={p['workers_count']}"
            for p in result["pools"]
        )
        return f"📊 Pools ({result['pools_count']} total):\n{pools_info}"

    @mcp.tool()  # type: ignore[misc]
    async def get_pool_status(pool_id: str) -> str:
        """Get detailed status of a specific pool.

        Args:
            pool_id: Pool identifier

        Returns:
            Pool status details
        """
        result = await pool_status(pool_id)
        if result["success"]:
            status = result["status"]
            return (
                f"📊 Pool {pool_id}:\n"
                f"  Running: {status['running']}\n"
                f"  Workers: {status['workers_count']}\n"
                f"  Queue size: {status['queue_size']}\n"
                f"  Tasks submitted: {status['tasks_submitted']}\n"
                f"  Tasks completed: {status['tasks_completed']}\n"
                f"  Success rate: {status['success_rate']:.1%}"
            )
        return f"❌ Failed to get pool status: {result.get('error', 'Unknown error')}"

    @mcp.tool()  # type: ignore[misc]
    async def check_pool_health(pool_id: str | None = None) -> str:
        """Get health status of pools.

        Args:
            pool_id: Optional pool identifier. If not provided, returns health for all pools.

        Returns:
            Health status information
        """
        result = await pool_health(pool_id)
        if result["success"]:
            if pool_id:
                health = result["health"]
                return (
                    f"🏥 Pool {pool_id} health:\n"
                    f"  Status: {health['status']}\n"
                    f"  Healthy workers: {health['workers_healthy']}/{health['workers_total']}"
                )
            else:
                health = result["health"]
                return (
                    f"🏥 Pool Manager Health:\n"
                    f"  Running: {health['pool_manager_running']}\n"
                    f"  Total pools: {health['pools_total']}\n"
                    f"  Healthy pools: {health['pools_healthy']}"
                )
        return f"❌ Failed to get health status: {result.get('error', 'Unknown error')}"


def _register_pool_management_tools(mcp: FastMCP) -> None:
    """Register pool lifecycle management tools."""

    @mcp.tool()  # type: ignore[misc]
    async def delete_pool(pool_id: str, timeout: float = 5.0) -> str:
        """Delete a worker pool.

        Args:
            pool_id: Pool identifier
            timeout: Maximum time to wait for pool shutdown (seconds)

        Returns:
            Pool deletion result message
        """
        result = await pool_delete(pool_id, timeout)
        if result["success"]:
            if result["deleted"]:
                return f"✅ Deleted pool {pool_id}"
            return f"⚠️ Pool {pool_id} not found"
        return f"❌ Failed to delete pool: {result.get('error', 'Unknown error')}"

    @mcp.tool()  # type: ignore[misc]
    async def get_pool_manager_status() -> str:
        """Get status of the pool manager.

        Returns:
            Pool manager status information
        """
        result = await pool_manager_status()
        health = result["health"]
        return (
            f"🔧 Pool Manager Status:\n"
            f"  Running: {result['manager_running']}\n"
            f"  Total pools: {health['pools_total']}\n"
            f"  Healthy pools: {health['pools_healthy']}"
        )


def register_pool_tools(mcp: FastMCP) -> None:
    """Register all worker pool management tools.

    Note: This function has high complexity due to nested tool registration pattern.
    Each tool is simple and follows a consistent structure, so the complexity is acceptable.
    """
    _register_pool_execution_tools(mcp)
    _register_pool_monitoring_tools(mcp)
    _register_pool_management_tools(mcp)
