"""Tests for ``session_buddy.mcp.tools.infrastructure.pools``.

Covers pool management MCP tools: pool_create, pool_execute,
pool_execute_batch, pool_route_task, pool_list, pool_status,
pool_health, pool_delete, pool_manager_status plus their MCP
registration wrappers (create_pool, execute_on_pool, etc.).

Pattern: patch ``session_buddy.pools.get_pool_manager`` (the import
alias used inside the module) so a fake PoolManager is returned
without touching the real global singleton.

Coverage target: 85-100% of source lines in pools.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.infrastructure import pools as pools_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Capture ``mcp.tool()`` decorators so registered tools can run."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *, name=None, description=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


def _make_pool(pool_id: str = "p1") -> MagicMock:
    """Return a fake WorkerPool with the methods the MCP tools call."""
    pool = MagicMock()
    pool.pool_id = pool_id
    pool.get_status = MagicMock(
        return_value={
            "pool_id": pool_id,
            "running": True,
            "workers_count": 3,
            "queue_size": 0,
            "tasks_submitted": 10,
            "tasks_completed": 8,
            "success_rate": 0.8,
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": "2026-01-01T00:00:01+00:00",
            "status": "running",
            "workers": [],
        }
    )
    pool.execute_batch = AsyncMock(return_value=["r1", "r2"])
    pool.health_check = AsyncMock(
        return_value={
            "pool_id": pool_id,
            "status": "healthy",
            "workers_healthy": 3,
            "workers_total": 3,
            "workers": [],
        }
    )
    return pool


def _make_manager(*, pool_id: str | None = "p1") -> tuple[MagicMock, MagicMock]:
    """Return a (manager, pool) where pool is registered with manager."""
    manager = MagicMock()
    pool = _make_pool(pool_id or "p1")
    manager.create_pool = AsyncMock(return_value=pool)
    manager.get_pool = AsyncMock(return_value=pool if pool_id else None)
    manager.delete_pool = AsyncMock(return_value=True)
    manager.list_pools = AsyncMock(return_value=[pool.get_status.return_value])
    manager.execute_on_pool = AsyncMock(return_value={"worker_id": "w1", "ok": True})
    manager.route_task = AsyncMock(return_value=(pool.pool_id, "routed-result"))
    manager.get_health_status = AsyncMock(
        return_value={
            "pool_manager_running": True,
            "pools_total": 1,
            "pools_healthy": 1,
            "pool_details": [],
        }
    )
    manager.running = True
    return manager, pool


@pytest.fixture
def patched_get_pool_manager(monkeypatch: pytest.MonkeyPatch):
    """Patch the module-level ``get_pool_manager`` factory."""
    manager, pool = _make_manager()
    get_pm = AsyncMock(return_value=manager)
    monkeypatch.setattr(pools_mod, "get_pool_manager", get_pm)
    return get_pm, manager, pool


# ---------------------------------------------------------------------------
# pool_create
# ---------------------------------------------------------------------------


async def test_pool_create_uses_pool_id(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_create passes the supplied pool_id through."""
    _, manager, _pool = patched_get_pool_manager
    result = await pools_mod.pool_create("my_pool")
    manager.create_pool.assert_awaited_once_with(pool_id="my_pool")
    assert result["success"] is True
    assert result["pool_id"] == "p1"
    assert result["status"] == "running"
    assert result["workers_count"] == 3
    assert result["queue_size"] == 0
    assert result["created_at"] == "2026-01-01T00:00:00+00:00"


async def test_pool_create_with_none_pool_id(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_create tolerates a None pool_id (server auto-generates)."""
    _get_pm, manager, _ = patched_get_pool_manager
    result = await pools_mod.pool_create(None)
    manager.create_pool.assert_awaited_once_with(pool_id=None)
    assert result["success"] is True


# ---------------------------------------------------------------------------
# pool_execute
# ---------------------------------------------------------------------------


async def test_pool_execute_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Successful execution returns success=True with worker_id and result."""
    _get_pm, manager, _pool = patched_get_pool_manager
    result = await pools_mod.pool_execute("p1", "write code", timeout=5.0)
    manager.execute_on_pool.assert_awaited_once_with(
        pool_id="p1",
        prompt="write code",
        context=None,
        timeout=5.0,
    )
    assert result["success"] is True
    assert result["pool_id"] == "p1"
    assert result["worker_id"] == "w1"
    assert result["result"] == {"worker_id": "w1", "ok": True}


async def test_pool_execute_handles_exception(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Failed execution returns success=False with the error message."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.execute_on_pool.side_effect = RuntimeError("pool crashed")
    result = await pools_mod.pool_execute("p1", "x")
    assert result["success"] is False
    assert result["pool_id"] == "p1"
    assert "pool crashed" in result["error"]


async def test_pool_execute_passes_context_and_timeout(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Optional context/timeout kwargs reach the manager unchanged."""
    _get_pm, manager, _ = patched_get_pool_manager
    ctx = {"user": "alice"}
    await pools_mod.pool_execute("p1", "x", context=ctx, timeout=2.5)
    manager.execute_on_pool.assert_awaited_once_with(
        pool_id="p1", prompt="x", context=ctx, timeout=2.5
    )


# ---------------------------------------------------------------------------
# pool_execute_batch
# ---------------------------------------------------------------------------


async def test_pool_execute_batch_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Successful batch returns results_count and stringified results."""
    _get_pm, _manager, pool = patched_get_pool_manager
    pool.execute_batch.return_value = ["alpha", "beta"]
    result = await pools_mod.pool_execute_batch(
        "p1", ["a", "b"], context={"k": "v"}, timeout=10.0
    )
    pool.execute_batch.assert_awaited_once_with(
        prompts=["a", "b"], context={"k": "v"}, timeout=10.0
    )
    assert result["success"] is True
    assert result["pool_id"] == "p1"
    assert result["results_count"] == 2
    assert result["results"] == ["alpha", "beta"]


async def test_pool_execute_batch_pool_not_found(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """get_pool returning None is surfaced as success=False."""
    _get_pm, manager, _pool = patched_get_pool_manager
    manager.get_pool.return_value = None
    result = await pools_mod.pool_execute_batch("missing", ["x"])
    assert result["success"] is False
    assert "not found" in result["error"]


async def test_pool_execute_batch_handles_exception(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Pool.execute_batch failure → success=False with error."""
    _get_pm, _manager, pool = patched_get_pool_manager
    pool.execute_batch.side_effect = ValueError("queue full")
    result = await pools_mod.pool_execute_batch("p1", ["x"])
    assert result["success"] is False
    assert "queue full" in result["error"]


# ---------------------------------------------------------------------------
# pool_route_task
# ---------------------------------------------------------------------------


async def test_pool_route_task_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Successful routing reports the chosen pool and strategy."""
    _get_pm, manager, _ = patched_get_pool_manager
    result = await pools_mod.pool_route_task(
        "do work", context={"x": 1}, selector="round_robin", timeout=3.0
    )
    manager.route_task.assert_awaited_once_with(
        prompt="do work", context={"x": 1}, selector="round_robin", timeout=3.0
    )
    assert result["success"] is True
    assert result["pool_id"] == "p1"
    assert result["strategy"] == "round_robin"
    assert result["result"] == "routed-result"


async def test_pool_route_task_handles_exception(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Routing failure returns success=False without pool_id."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.route_task.side_effect = ValueError("no pools")
    result = await pools_mod.pool_route_task("x")
    assert result["success"] is False
    assert "no pools" in result["error"]
    # Failure path does not include pool_id key
    assert "pool_id" not in result


# ---------------------------------------------------------------------------
# pool_list
# ---------------------------------------------------------------------------


async def test_pool_list_returns_pool_dicts(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_list returns the manager's list of pool dicts verbatim."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.list_pools.return_value = [{"pool_id": "a"}, {"pool_id": "b"}]
    result = await pools_mod.pool_list()
    assert result["success"] is True
    assert result["pools_count"] == 2
    assert result["pools"] == [{"pool_id": "a"}, {"pool_id": "b"}]


async def test_pool_list_empty(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_list handles empty pool list."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.list_pools.return_value = []
    result = await pools_mod.pool_list()
    assert result["pools_count"] == 0
    assert result["pools"] == []


# ---------------------------------------------------------------------------
# pool_status
# ---------------------------------------------------------------------------


async def test_pool_status_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_status returns manager.get_pool(...).get_status() result."""
    _get_pm, _manager, pool = patched_get_pool_manager
    result = await pools_mod.pool_status("p1")
    assert result["success"] is True
    assert result["pool_id"] == "p1"
    assert result["status"] == pool.get_status.return_value


async def test_pool_status_pool_not_found(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_status surfaces success=False for missing pools."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.get_pool.return_value = None
    result = await pools_mod.pool_status("missing")
    assert result["success"] is False
    assert "not found" in result["error"]


async def test_pool_status_get_status_raises(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_status handles errors from pool.get_status()."""
    _get_pm, _manager, pool = patched_get_pool_manager
    pool.get_status.side_effect = RuntimeError("boom")
    result = await pools_mod.pool_status("p1")
    assert result["success"] is False
    assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# pool_health
# ---------------------------------------------------------------------------


async def test_pool_health_for_specific_pool(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_health with pool_id returns that pool's health dict."""
    _get_pm, manager, pool = patched_get_pool_manager
    pool.health_check.return_value = {
        "pool_id": "p1",
        "status": "healthy",
        "workers_healthy": 3,
        "workers_total": 3,
    }
    result = await pools_mod.pool_health("p1")
    assert result["success"] is True
    assert result["pool_id"] == "p1"
    assert result["health"]["status"] == "healthy"


async def test_pool_health_pool_not_found(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_health with unknown pool_id returns success=False."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.get_pool.return_value = None
    result = await pools_mod.pool_health("missing")
    assert result["success"] is False
    assert "not found" in result["error"]


async def test_pool_health_all_pools(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_health with no pool_id returns manager-level health."""
    _get_pm, manager, _ = patched_get_pool_manager
    result = await pools_mod.pool_health()
    manager.get_health_status.assert_awaited_once()
    assert result["success"] is True
    assert result["health"]["pools_total"] == 1
    assert result["health"]["pools_healthy"] == 1
    # Specific pool path not taken when no pool_id supplied
    assert "pool_id" not in result


async def test_pool_health_health_check_raises(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_health surfaces pool.health_check() errors."""
    _get_pm, _manager, pool = patched_get_pool_manager
    pool.health_check.side_effect = RuntimeError("health fail")
    result = await pools_mod.pool_health("p1")
    assert result["success"] is False
    assert "health fail" in result["error"]


# ---------------------------------------------------------------------------
# pool_delete
# ---------------------------------------------------------------------------


async def test_pool_delete_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_delete passes through the deleted boolean."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.delete_pool.return_value = True
    result = await pools_mod.pool_delete("p1")
    manager.delete_pool.assert_awaited_once_with("p1", timeout=5.0)
    assert result["success"] is True
    assert result["deleted"] is True


async def test_pool_delete_default_timeout(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Default timeout is 5.0 seconds when not provided."""
    _get_pm, manager, _ = patched_get_pool_manager
    await pools_mod.pool_delete("p1")
    manager.delete_pool.assert_awaited_once_with("p1", timeout=5.0)


async def test_pool_delete_custom_timeout(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Custom timeout is forwarded to the manager."""
    _get_pm, manager, _ = patched_get_pool_manager
    await pools_mod.pool_delete("p1", timeout=15.5)
    manager.delete_pool.assert_awaited_once_with("p1", timeout=15.5)


async def test_pool_delete_handles_exception(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_delete surfaces success=False when delete_pool raises."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.delete_pool.side_effect = RuntimeError("shutdown fail")
    result = await pools_mod.pool_delete("p1")
    assert result["success"] is False
    assert "shutdown fail" in result["error"]


# ---------------------------------------------------------------------------
# pool_manager_status
# ---------------------------------------------------------------------------


async def test_pool_manager_status_returns_running_flag_and_health(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """pool_manager_status returns manager.running and health dict."""
    _get_pm, manager, _ = patched_get_pool_manager
    result = await pools_mod.pool_manager_status()
    assert result["success"] is True
    assert result["manager_running"] is True
    assert result["health"]["pools_total"] == 1


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def test_register_pool_execution_tools_registers_create_execute_batch_route(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Execution tools block registers create/execute/execute_batch/route_to_pool."""
    mcp = _FakeMCP()
    pools_mod._register_pool_execution_tools(mcp)
    assert set(mcp.tools) == {
        "create_pool",
        "execute_on_pool",
        "execute_batch_on_pool",
        "route_to_pool",
    }


def test_register_pool_monitoring_tools_registers_list_status_health(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Monitoring tools block registers list_pools/get_pool_status/check_pool_health."""
    mcp = _FakeMCP()
    pools_mod._register_pool_monitoring_tools(mcp)
    assert set(mcp.tools) == {"list_pools", "get_pool_status", "check_pool_health"}


def test_register_pool_management_tools_registers_delete_and_manager_status(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """Management block registers delete_pool and get_pool_manager_status."""
    mcp = _FakeMCP()
    pools_mod._register_pool_management_tools(mcp)
    assert set(mcp.tools) == {"delete_pool", "get_pool_manager_status"}


def test_register_pool_tools_registers_all_nine() -> None:
    """register_pool_tools combines all three blocks (9 tools total)."""
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    expected = {
        # Execution
        "create_pool",
        "execute_on_pool",
        "execute_batch_on_pool",
        "route_to_pool",
        # Monitoring
        "list_pools",
        "get_pool_status",
        "check_pool_health",
        # Management
        "delete_pool",
        "get_pool_manager_status",
    }
    assert set(mcp.tools) == expected


# ---------------------------------------------------------------------------
# MCP wrapper tool success/failure paths
# ---------------------------------------------------------------------------


async def test_create_pool_tool_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """create_pool wrapper returns ✅ when pool_create succeeds."""
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["create_pool"](pool_id=None)
    assert out.startswith("✅ Created pool")
    assert "3 workers" in out


async def test_create_pool_tool_failure(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """create_pool wrapper lets pool_create exceptions bubble through."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.create_pool.side_effect = ValueError("dup pool")
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    with pytest.raises(ValueError, match="dup pool"):
        await mcp.tools["create_pool"](pool_id="dup")


async def test_execute_on_pool_tool_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """execute_on_pool wrapper returns ✅ with worker_id."""
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["execute_on_pool"](
        pool_id="p1", prompt="x", context=None, timeout=None
    )
    assert out.startswith("✅ Task executed on pool p1 by worker w1")


async def test_execute_on_pool_tool_success_no_worker_id(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """execute_on_pool doesn't crash when the result has no worker_id key.

    Documents the current behavior: ``result.get('worker_id', 'unknown')``
    returns the literal stored value (None) rather than falling back to
    'unknown' because the key is present with a None value.
    """
    _get_pm, manager, _ = patched_get_pool_manager
    manager.execute_on_pool.return_value = {"no_worker": True}
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["execute_on_pool"](pool_id="p1", prompt="x")
    # Key is present with None — .get('worker_id', 'unknown') still returns None
    assert "by worker None" in out


async def test_execute_on_pool_tool_failure(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """execute_on_pool wrapper returns ❌ on failure."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.execute_on_pool.side_effect = RuntimeError("kaboom")
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["execute_on_pool"](pool_id="p1", prompt="x")
    assert out.startswith("❌ Failed to execute task:")
    assert "kaboom" in out


async def test_execute_batch_on_pool_tool_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """execute_batch_on_pool wrapper reports the result count."""
    _get_pm, _manager, pool = patched_get_pool_manager
    pool.execute_batch.return_value = ["r1", "r2", "r3"]
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["execute_batch_on_pool"](
        pool_id="p1", prompts=["a", "b", "c"]
    )
    assert out == "✅ Executed 3 tasks on pool p1"


async def test_execute_batch_on_pool_tool_failure(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """execute_batch_on_pool wrapper returns ❌ on failure."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.get_pool.return_value = None
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["execute_batch_on_pool"](pool_id="p1", prompts=["a"])
    assert out.startswith("❌ Failed to execute batch:")


async def test_route_to_pool_tool_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """route_to_pool wrapper reports the chosen pool and strategy."""
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["route_to_pool"](
        prompt="x", context=None, selector="least_loaded", timeout=None
    )
    assert out == "✅ Routed task to pool p1 using least_loaded strategy"


async def test_route_to_pool_tool_failure(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """route_to_pool wrapper returns ❌ on failure."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.route_task.side_effect = ValueError("no pools")
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["route_to_pool"](prompt="x")
    assert out.startswith("❌ Failed to route task:")


async def test_list_pools_tool_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """list_pools wrapper renders pool header + each pool summary line."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.list_pools.return_value = [
        {"pool_id": "alpha", "running": True, "workers_count": 3},
        {"pool_id": "beta", "running": False, "workers_count": 0},
    ]
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["list_pools"]()
    assert "📊 Pools (2 total):" in out
    assert "- alpha: running=True, workers=3" in out
    assert "- beta: running=False, workers=0" in out


async def test_get_pool_status_tool_success(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """get_pool_status renders Running/Workers/Queue/Tasks/rate lines."""
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["get_pool_status"](pool_id="p1")
    assert "📊 Pool p1:" in out
    assert "Running: True" in out
    assert "Workers: 3" in out
    assert "Queue size: 0" in out
    assert "Tasks submitted: 10" in out
    assert "Tasks completed: 8" in out
    assert "Success rate: 80.0%" in out


async def test_get_pool_status_tool_failure(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """get_pool_status wrapper returns ❌ when pool_status fails."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.get_pool.return_value = None
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["get_pool_status"](pool_id="missing")
    assert out.startswith("❌ Failed to get pool status:")


async def test_check_pool_health_specific_pool(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """check_pool_health(pool_id) renders Pool X health section."""
    _get_pm, _manager, pool = patched_get_pool_manager
    pool.health_check.return_value = {
        "pool_id": "p1",
        "status": "healthy",
        "workers_healthy": 3,
        "workers_total": 3,
    }
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["check_pool_health"](pool_id="p1")
    assert "🏥 Pool p1 health:" in out
    assert "Status: healthy" in out
    assert "Healthy workers: 3/3" in out


async def test_check_pool_health_all_pools(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """check_pool_health() with no arg renders manager-level summary."""
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["check_pool_health"](pool_id=None)
    assert "🏥 Pool Manager Health:" in out
    assert "Running: True" in out
    assert "Total pools: 1" in out
    assert "Healthy pools: 1" in out


async def test_check_pool_health_failure(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """check_pool_health wrapper returns ❌ on failure."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.get_pool.return_value = None
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["check_pool_health"](pool_id="missing")
    assert out.startswith("❌ Failed to get health status:")


async def test_delete_pool_tool_deleted(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """delete_pool wrapper returns ✅ when delete returned True."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.delete_pool.return_value = True
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["delete_pool"](pool_id="p1")
    assert out == "✅ Deleted pool p1"


async def test_delete_pool_tool_not_found(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """delete_pool wrapper returns ⚠️ when delete returned False."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.delete_pool.return_value = False
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["delete_pool"](pool_id="missing")
    assert out == "⚠️ Pool missing not found"


async def test_delete_pool_tool_failure(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """delete_pool wrapper returns ❌ on exception."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.delete_pool.side_effect = RuntimeError("err")
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["delete_pool"](pool_id="p1")
    assert out.startswith("❌ Failed to delete pool:")


async def test_delete_pool_tool_default_timeout(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """delete_pool wrapper forwards the timeout argument."""
    _get_pm, manager, _ = patched_get_pool_manager
    manager.delete_pool.return_value = True
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    await mcp.tools["delete_pool"](pool_id="p1", timeout=12.0)
    manager.delete_pool.assert_awaited_once_with("p1", timeout=12.0)


async def test_get_pool_manager_status_tool(
    patched_get_pool_manager: tuple[AsyncMock, MagicMock, MagicMock],
) -> None:
    """get_pool_manager_status wrapper renders Running/Total/Healthy lines."""
    mcp = _FakeMCP()
    pools_mod.register_pool_tools(mcp)
    out = await mcp.tools["get_pool_manager_status"]()
    assert "🔧 Pool Manager Status:" in out
    assert "Running: True" in out
    assert "Total pools: 1" in out
    assert "Healthy pools: 1" in out