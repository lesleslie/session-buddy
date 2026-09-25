"""End-to-end integration test for Hybrid D pool lifecycle observability.

Verifies the full ``create_pool → execute → channel session start →
execute_batch → delete_pool → channel session end`` flow against the
real MCP tool wrappers (not internals) plus the channel session store.

This is the runtime smoke for Phase D — proves that the wrappers,
the WorkerPool, and the channel session tracker stay in sync across
the whole lifecycle, including batch execution.
"""

from __future__ import annotations

from session_buddy import pools as sp_mod
from session_buddy.mcp.tools.infrastructure.pools import (
    pool_create,
    pool_delete,
    pool_execute,
    pool_execute_batch,
)
from session_buddy.mcp.tools.session.channel_tracking_tools import (
    _store as _channel_store,
)


async def test_full_lifecycle_observable():
    # Reset global pool manager to isolate this test.
    sp_mod._global_pool_manager = None

    pool_id = "integ-lifecycle"
    try:
        # Create with reflect_tasks=True to exercise D3 path too.
        create = await pool_create(pool_id=pool_id, reflect_tasks=True)
        assert create["success"], create
        assert create["pool_id"] == pool_id
        assert create["metadata"]["reflect_tasks"] is True

        # Channel session start event must be visible.
        active = _channel_store.query(
            channel_type="pool", channel_id=f"pool:{pool_id}"
        )
        assert len(active) == 1, "expected one active pool session"
        assert active[0]["channel_type"] == "pool"
        assert active[0]["sender_id"] == pool_id

        # Single-task execution must succeed.
        result = await pool_execute(pool_id=pool_id, prompt="integration smoke test")
        assert result["success"], result
        assert result["pool_id"] == pool_id

        # Batch execution must succeed.
        batch = await pool_execute_batch(
            pool_id=pool_id,
            prompts=["batch a", "batch b", "batch c"],
        )
        assert batch["success"], batch
        assert batch["results_count"] == 3
        for r in batch["results"]:
            assert r["status"] == "completed"
            assert "response" in r["output"]

        # Pool session still active before delete.
        active = _channel_store.query(
            channel_type="pool", channel_id=f"pool:{pool_id}"
        )
        assert len(active) == 1
    finally:
        # Cleanup — delete_pool should emit the end event.
        delete = await pool_delete(pool_id)
        assert delete["success"], delete
        sp_mod._global_pool_manager = None

    # After shutdown, the active record should be gone.
    active = _channel_store.query(
        channel_type="pool", channel_id=f"pool:{pool_id}"
    )
    assert len(active) == 0, "channel session was not ended on pool_delete"


async def test_pool_create_default_reflect_tasks_false():
    """Default ``pool_create`` must report ``reflect_tasks=False`` in metadata."""
    sp_mod._global_pool_manager = None
    pool_id = "integ-default"
    try:
        create = await pool_create(pool_id=pool_id)
        assert create["success"], create
        assert create["metadata"]["backend"] == "placeholder"
        assert create["metadata"]["reflect_tasks"] is False
    finally:
        await pool_delete(pool_id)
        sp_mod._global_pool_manager = None