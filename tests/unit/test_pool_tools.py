from __future__ import annotations

import pytest


class DummyMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.mark.asyncio
async def test_register_pool_tools_registers_all_wrappers() -> None:
    from session_buddy.mcp.tools.infrastructure import pools as mod

    mcp = DummyMCP()
    mod.register_pool_tools(mcp)

    assert {
        "create_pool",
        "execute_on_pool",
        "execute_batch_on_pool",
        "route_to_pool",
        "list_pools",
        "get_pool_status",
        "check_pool_health",
        "delete_pool",
        "get_pool_manager_status",
    }.issubset(mcp.tools)


@pytest.mark.asyncio
async def test_pool_execution_wrappers_format_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.infrastructure import pools as mod

    monkeypatch.setattr(
        mod,
        "pool_create",
        lambda pool_id=None: _async_return(
            {
                "success": True,
                "pool_id": pool_id or "pool_1",
                "workers_count": 3,
                "queue_size": 0,
                "created_at": "now",
            }
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_execute",
        lambda pool_id, prompt, context=None, timeout=None: _async_return(
            {"success": True, "worker_id": "worker-1"}
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_execute_batch",
        lambda pool_id, prompts, context=None, timeout=None: _async_return(
            {"success": True, "results_count": len(prompts)}
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_route_task",
        lambda prompt, context=None, selector="least_loaded", timeout=None: _async_return(
            {"success": True, "pool_id": "pool-9", "strategy": selector}
        ),
    )

    mcp = DummyMCP()
    mod.register_pool_tools(mcp)

    assert await mcp.tools["create_pool"]("pool-x") == "✅ Created pool pool-x with 3 workers"
    assert (
        await mcp.tools["execute_on_pool"]("pool-x", "do work")
        == "✅ Task executed on pool pool-x by worker worker-1"
    )
    assert (
        await mcp.tools["execute_batch_on_pool"]("pool-x", ["a", "b"])
        == "✅ Executed 2 tasks on pool pool-x"
    )
    assert (
        await mcp.tools["route_to_pool"]("do work", selector="random")
        == "✅ Routed task to pool pool-9 using random strategy"
    )

    monkeypatch.setattr(
        mod,
        "pool_create",
        lambda pool_id=None: _async_return({"success": False, "error": "nope"}),
    )
    monkeypatch.setattr(
        mod,
        "pool_execute",
        lambda pool_id, prompt, context=None, timeout=None: _async_return(
            {"success": False, "error": "failed"}
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_execute_batch",
        lambda pool_id, prompts, context=None, timeout=None: _async_return(
            {"success": False, "error": "batch-failed"}
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_route_task",
        lambda prompt, context=None, selector="least_loaded", timeout=None: _async_return(
            {"success": False, "error": "route-failed"}
        ),
    )

    assert await mcp.tools["create_pool"]() == "❌ Failed to create pool: nope"
    assert await mcp.tools["execute_on_pool"]("pool-x", "do work") == "❌ Failed to execute task: failed"
    assert await mcp.tools["execute_batch_on_pool"]("pool-x", ["a"]) == "❌ Failed to execute batch: batch-failed"
    assert await mcp.tools["route_to_pool"]("do work") == "❌ Failed to route task: route-failed"


@pytest.mark.asyncio
async def test_pool_monitoring_and_management_wrappers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.infrastructure import pools as mod

    monkeypatch.setattr(
        mod,
        "pool_list",
        lambda: _async_return(
            {
                "success": True,
                "pools_count": 2,
                "pools": [
                    {"pool_id": "p1", "running": True, "workers_count": 3},
                    {"pool_id": "p2", "running": False, "workers_count": 1},
                ],
            }
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_status",
        lambda pool_id: _async_return(
            {
                "success": True,
                "status": {
                    "running": True,
                    "workers_count": 3,
                    "queue_size": 2,
                    "tasks_submitted": 7,
                    "tasks_completed": 6,
                    "success_rate": 0.8571,
                },
            }
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_health",
        lambda pool_id=None: _async_return(
            {
                "success": True,
                "health": (
                    {
                        "pool_manager_running": True,
                        "pools_total": 2,
                        "pools_healthy": 1,
                    }
                    if pool_id is None
                    else {"status": "healthy", "workers_healthy": 3, "workers_total": 3}
                ),
            }
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_delete",
        lambda pool_id, timeout=5.0: _async_return(
            {"success": True, "deleted": True}
        ),
    )
    monkeypatch.setattr(
        mod,
        "pool_manager_status",
        lambda: _async_return(
            {
                "success": True,
                "manager_running": True,
                "health": {"pools_total": 2, "pools_healthy": 2},
            }
        ),
    )

    mcp = DummyMCP()
    mod.register_pool_tools(mcp)

    assert "Pools (2 total)" in await mcp.tools["list_pools"]()
    assert "Pool p1" in await mcp.tools["get_pool_status"]("p1")
    assert "Pool p1 health" in await mcp.tools["check_pool_health"]("p1")
    assert "Pool Manager Health" in await mcp.tools["check_pool_health"]()
    assert await mcp.tools["delete_pool"]("p1") == "✅ Deleted pool p1"
    assert "Pool Manager Status" in await mcp.tools["get_pool_manager_status"]()


async def _async_return(value):
    return value
