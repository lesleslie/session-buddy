"""Integration tests for Phase 1.5 Feature #7: Memory Differential at Session End.

The differential is a 'session learning report' generated at session end.
It is a pure read over v2 tables (conversations_v2, memory_access_log) and
summarizes:

- new_memories:           memories written during the session window
- reinforced_memories:    memories accessed more than once during the window
- contradictions:         memories whose content disagrees (placeholder)
- new_causal_links:       new causal links formed (placeholder)
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest


def _new_memory_id(prefix: str) -> str:
    """Stable-ish ID generator for test data (avoids importing the real one)."""
    return f"{prefix}_{hashlib.md5(f'{prefix}_{time.time()}'.encode(), usedforsecurity=False).hexdigest()[:12]}"


@pytest.fixture
async def v2_db(tmp_path) -> AsyncGenerator[Any]:
    """Adapter instance with the v2 schema (conversations_v2, memory_access_log)."""
    from session_buddy.adapters.settings import ReflectionAdapterSettings
    from tests.conftest import _get_reflection_database_class

    db_path = tmp_path / "differential.duckdb"
    settings = ReflectionAdapterSettings(
        database_path=db_path,
        collection_name="default",
        embedding_dim=384,
        distance_metric="cosine",
        enable_vss=False,
        threads=1,
        memory_limit="512MB",
        enable_embeddings=False,
    )
    adapter_cls = _get_reflection_database_class()
    db = adapter_cls(settings=settings)
    await db.initialize()
    try:
        yield db
    finally:
        with __import__("contextlib").suppress(Exception):
            await db.close()


def _insert_memory(
    db: Any,
    *,
    memory_id: str,
    content: str,
    session_id: str,
    timestamp: datetime,
    category: str = "facts",
    project: str = "test-project",
) -> None:
    """Insert a row into conversations_v2 with explicit timestamp and session_id."""
    db.conn.execute(
        """
        INSERT INTO conversations_v2 (
            id, content, category, project, namespace, timestamp, session_id,
            user_id, memory_tier, importance_score, access_count
        ) VALUES (?, ?, ?, ?, 'default', ?, ?, 'default', 'long_term', 0.5, 0)
        """,
        [memory_id, content, category, project, timestamp, session_id],
    )


def _insert_access(
    db: Any, *, memory_id: str, timestamp: datetime, access_type: str = "search"
) -> None:
    """Insert a row into memory_access_log."""
    db.conn.execute(
        """
        INSERT INTO memory_access_log (id, memory_id, access_type, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        [_new_memory_id("acc"), memory_id, access_type, timestamp],
    )


@pytest.mark.asyncio
async def test_differential_reports_new_memories_in_window(v2_db: Any) -> None:
    """Memories written within the window are included; older ones are filtered out."""
    now = datetime.now(UTC)
    in_window = now - timedelta(hours=1)
    out_of_window = now - timedelta(days=8)

    for i in range(3):
        _insert_memory(
            v2_db,
            memory_id=_new_memory_id("mem"),
            content=f"in-window-{i}",
            session_id="sess-current",
            timestamp=in_window,
        )
    for i in range(2):
        _insert_memory(
            v2_db,
            memory_id=_new_memory_id("mem"),
            content=f"out-of-window-{i}",
            session_id="sess-current",
            timestamp=out_of_window,
        )

    report = await v2_db.generate_session_differential(
        session_id="sess-current", window_hours=24
    )

    assert report["new_memory_count"] == 3
    assert len(report["new_memories"]) == 3
    contents = {row["content"] for row in report["new_memories"]}
    assert contents == {"in-window-0", "in-window-1", "in-window-2"}


@pytest.mark.asyncio
async def test_differential_identifies_reinforced_memories(v2_db: Any) -> None:
    """Memories with >1 access in the window appear in reinforced_memories."""
    now = datetime.now(UTC)
    ts_mem = now - timedelta(hours=1)
    ts_acc = now - timedelta(minutes=30)

    memory_ids = [_new_memory_id("mem") for _ in range(5)]
    for mid in memory_ids:
        _insert_memory(
            v2_db,
            memory_id=mid,
            content=f"content-{mid}",
            session_id="sess-A",
            timestamp=ts_mem,
        )

    # 3 accesses for memory_ids[0], 1 access each for the others
    for _ in range(3):
        _insert_access(v2_db, memory_id=memory_ids[0], timestamp=ts_acc)
    for mid in memory_ids[1:]:
        _insert_access(v2_db, memory_id=mid, timestamp=ts_acc)

    report = await v2_db.generate_session_differential(
        session_id="sess-A", window_hours=24
    )

    reinforced_ids = {r["memory_id"] for r in report["reinforced_memories"]}
    assert memory_ids[0] in reinforced_ids
    for mid in memory_ids[1:]:
        assert mid not in reinforced_ids
    # And the access count for the reinforced memory is 3
    target = next(
        r for r in report["reinforced_memories"] if r["memory_id"] == memory_ids[0]
    )
    assert target["access_count"] == 3


@pytest.mark.asyncio
async def test_differential_handles_empty_session(v2_db: Any) -> None:
    """An unknown session_id returns zero counts and empty lists."""
    report = await v2_db.generate_session_differential(
        session_id="sess-empty", window_hours=24
    )

    assert report["new_memory_count"] == 0
    assert report["new_memories"] == []
    assert report["reinforced_memories"] == []
    assert report["contradictions"] == []
    assert report["new_causal_links"] == []


@pytest.mark.asyncio
async def test_differential_contradictions_field_present(v2_db: Any) -> None:
    """The contradictions field is returned.

    Full NLP-based contradiction detection is out of scope for v1. The
    report must always expose the field; if no detection logic runs, it
    is an empty list.
    """
    now = datetime.now(UTC)
    ts = now - timedelta(hours=1)
    _insert_memory(
        v2_db,
        memory_id=_new_memory_id("mem"),
        content="The capital of France is Paris",
        session_id="sess",
        timestamp=ts,
    )
    _insert_memory(
        v2_db,
        memory_id=_new_memory_id("mem"),
        content="The capital of France is NOT Paris",
        session_id="sess",
        timestamp=ts,
    )

    report = await v2_db.generate_session_differential(
        session_id="sess", window_hours=24
    )

    assert "contradictions" in report
    assert isinstance(report["contradictions"], list)


@pytest.mark.asyncio
async def test_differential_window_filters_correctly(v2_db: Any) -> None:
    """Memories just outside the window are excluded; just inside are included."""
    now = datetime.now(UTC)

    _insert_memory(
        v2_db,
        memory_id=_new_memory_id("mem"),
        content="just-outside",
        session_id="sess",
        timestamp=now - timedelta(hours=25),
    )
    _insert_memory(
        v2_db,
        memory_id=_new_memory_id("mem"),
        content="just-inside",
        session_id="sess",
        timestamp=now - timedelta(hours=23),
    )

    report = await v2_db.generate_session_differential(
        session_id="sess", window_hours=24
    )

    contents = {row["content"] for row in report["new_memories"]}
    assert contents == {"just-inside"}
    assert report["new_memory_count"] == 1
