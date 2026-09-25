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

    create_result = await mcp.tools["create_pool"]("pool-x")
    assert create_result["success"] is True
    assert create_result["pool_id"] == "pool-x"
    assert create_result["workers_count"] == 3

    execute_result = await mcp.tools["execute_on_pool"]("pool-x", "do work")
    assert execute_result["success"] is True
    assert execute_result["worker_id"] == "worker-1"

    batch_result = await mcp.tools["execute_batch_on_pool"]("pool-x", ["a", "b"])
    assert batch_result["success"] is True
    assert batch_result["results_count"] == 2

    route_result = await mcp.tools["route_to_pool"]("do work", selector="random")
    assert route_result["success"] is True
    assert route_result["pool_id"] == "pool-9"
    assert route_result["strategy"] == "random"

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

    create_fail = await mcp.tools["create_pool"]()
    assert create_fail["success"] is False
    assert create_fail["error"] == "nope"

    execute_fail = await mcp.tools["execute_on_pool"]("pool-x", "do work")
    assert execute_fail["success"] is False
    assert execute_fail["error"] == "failed"

    batch_fail = await mcp.tools["execute_batch_on_pool"]("pool-x", ["a"])
    assert batch_fail["success"] is False
    assert batch_fail["error"] == "batch-failed"

    route_fail = await mcp.tools["route_to_pool"]("do work")
    assert route_fail["success"] is False
    assert route_fail["error"] == "route-failed"


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

    list_result = await mcp.tools["list_pools"]()
    assert list_result["success"] is True
    assert list_result["pools_count"] == 2
    assert list_result["pools"] == [
        {"pool_id": "p1", "running": True, "workers_count": 3},
        {"pool_id": "p2", "running": False, "workers_count": 1},
    ]

    status_result = await mcp.tools["get_pool_status"]("p1")
    assert status_result["success"] is True
    assert status_result["status"]["running"] is True
    assert status_result["status"]["workers_count"] == 3

    pool_health_result = await mcp.tools["check_pool_health"]("p1")
    assert pool_health_result["success"] is True
    assert pool_health_result["health"]["status"] == "healthy"
    assert pool_health_result["health"]["workers_healthy"] == 3

    manager_health_result = await mcp.tools["check_pool_health"]()
    assert manager_health_result["success"] is True
    assert manager_health_result["health"]["pool_manager_running"] is True
    assert manager_health_result["health"]["pools_total"] == 2

    delete_result = await mcp.tools["delete_pool"]("p1")
    assert delete_result["success"] is True
    assert delete_result["deleted"] is True

    manager_status_result = await mcp.tools["get_pool_manager_status"]()
    assert manager_status_result["success"] is True
    assert manager_status_result["manager_running"] is True
    assert manager_status_result["health"]["pools_total"] == 2


async def _async_return(value):
    return value
