"""Unit tests for Hybrid D persistence plumbing on WorkerPool.

Phase D adds ``backend``, ``model``, and ``reflect_tasks`` params to
``WorkerPool.__init__`` plus a ``pool_metadata`` dict that is propagated
into channel-session events (D2) and gated per-task reflection storage
(D3).
"""

from __future__ import annotations

import session_buddy.pools as sp
from session_buddy.mcp.tools.session.channel_tracking_tools import (
    _store as _channel_store,
)


async def test_pool_default_reflect_tasks_false():
    pool = sp.WorkerPool(pool_id="t1")
    assert pool.reflect_tasks is False
    assert pool.pool_metadata["reflect_tasks"] is False
    assert pool.pool_metadata["backend"] == "placeholder"
    assert pool.pool_metadata["model"] is None


async def test_pool_explicit_reflect_tasks_true():
    pool = sp.WorkerPool(pool_id="t2", reflect_tasks=True)
    assert pool.reflect_tasks is True
    assert pool.pool_metadata["reflect_tasks"] is True


async def test_pool_backend_and_model_metadata():
    pool = sp.WorkerPool(
        pool_id="t3",
        backend="llm",
        model="minimax/MiniMax-M3",
        reflect_tasks=True,
    )
    assert pool.backend_name == "llm"
    assert pool.model == "minimax/MiniMax-M3"
    assert pool.pool_metadata["backend"] == "llm"
    assert pool.pool_metadata["model"] == "minimax/MiniMax-M3"


async def test_pool_init_emits_channel_session_start():
    """``initialize()`` must register a channel_session_start event."""
    # Snapshot the store so we can isolate this test from other events.
    initial = list(_channel_store._active.values())
    pool = sp.WorkerPool(pool_id="t-chan-start", reflect_tasks=False)
    await pool.initialize()
        # _active holds active sessions; the start event may have already
        # been "ended" by a sibling test, so check the channel_id.
    active = _channel_store.query(
        channel_type="pool", channel_id=f"pool:t-chan-start"
    )
    assert len(active) == 1
    record = active[0]
    assert record["channel_type"] == "pool"
    assert record["channel_id"] == "pool:t-chan-start"
    assert record["sender_id"] == "t-chan-start"
    await pool.shutdown()


async def test_pool_shutdown_emits_channel_session_end():
    """``shutdown()`` must remove the active channel session."""
    pool = sp.WorkerPool(pool_id="t-chan-end", reflect_tasks=True)
    await pool.initialize()
    active = _channel_store.query(
        channel_type="pool", channel_id=f"pool:t-chan-end"
    )
    assert len(active) == 1
    await pool.shutdown()
    # After shutdown, the active record should be gone.
    active = _channel_store.query(
        channel_type="pool", channel_id=f"pool:t-chan-end"
    )
    assert len(active) == 0