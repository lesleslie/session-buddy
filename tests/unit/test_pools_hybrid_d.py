"""Unit tests for Hybrid D persistence plumbing on WorkerPool.

Phase D adds ``backend``, ``model``, and ``reflect_tasks`` params to
``WorkerPool.__init__`` plus a ``pool_metadata`` dict that is propagated
into channel-session events (D2) and gated per-task reflection storage
(D3). These tests cover the D1 surface only — no channel session or
reflection behaviour is exercised here.
"""

from __future__ import annotations

import session_buddy.pools as sp


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