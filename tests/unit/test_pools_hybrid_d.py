"""Unit tests for Hybrid D persistence plumbing on WorkerPool.

Phase D adds ``backend``, ``model``, and ``reflect_tasks`` params to
``WorkerPool.__init__`` plus a ``pool_metadata`` dict that is propagated
into channel-session events (D2) and gated per-task reflection storage
(D3).
"""

from __future__ import annotations

import asyncio
from typing import Any

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


async def test_pool_with_reflect_tasks_stores_reflection(monkeypatch):
    """``reflect_tasks=True`` writes one reflection per completed task."""
    import json

    from session_buddy.mcp.tools.memory import memory_tools

    stored: list[dict[str, Any]] = []

    async def fake_store_reflection_impl(content, tags=None, project=None):
        stored.append({"content": content, "tags": tags, "project": project})
        return f"ok-{len(stored)}"

    monkeypatch.setattr(
        memory_tools, "_store_reflection_impl", fake_store_reflection_impl
    )

    pool = sp.WorkerPool(pool_id="t-reflect", reflect_tasks=True)
    await pool.initialize()
    try:
        await pool.execute("hello reflection")
        # Allow reflection helper to run
        assert len(stored) >= 1
        # Content should be JSON of the envelope
        envelope = json.loads(stored[-1]["content"])
        assert "response" in envelope
        assert envelope["worker_id"].startswith("t-reflect-worker-")
    finally:
        await pool.shutdown()


async def test_pool_default_no_reflection(monkeypatch):
    """Default ``reflect_tasks=False`` must NOT write any reflections."""
    from session_buddy.mcp.tools.memory import memory_tools

    stored: list[int] = []

    async def fake_store_reflection_impl(*a, **kw):
        stored.append(1)
        return "ok"

    monkeypatch.setattr(
        memory_tools, "_store_reflection_impl", fake_store_reflection_impl
    )

    pool = sp.WorkerPool(pool_id="t-noreflect")  # default reflect_tasks=False
    await pool.initialize()
    try:
        await pool.execute("no reflection please")
        # Allow reflection helper time to (not) run
        await asyncio.sleep(0.2)
        assert len(stored) == 0
    finally:
        await pool.shutdown()


async def test_create_pool_wrapper_accepts_backend_and_reflect():
    """MCP ``pool_create`` must thread ``backend``, ``model``,
    ``reflect_tasks`` through to WorkerPool."""
    # Reset global pool manager so test isolation is guaranteed.
    from session_buddy import pools as sp_mod

    sp_mod._global_pool_manager = None

    from session_buddy.mcp.tools.infrastructure.pools import pool_create, pool_delete

    pool_id = "t-mcp-create"
    try:
        result = await pool_create(
            pool_id=pool_id,
            backend="placeholder",
            reflect_tasks=True,
        )
        assert result["success"] is True
        assert result["pool_id"] == pool_id
        assert result["metadata"]["backend"] == "placeholder"
        assert result["metadata"]["reflect_tasks"] is True
        assert result["metadata"]["model"] is None
    finally:
        await pool_delete(pool_id)
        sp_mod._global_pool_manager = None