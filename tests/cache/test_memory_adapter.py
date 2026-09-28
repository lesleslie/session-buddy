#!/usr/bin/env python3
"""Tests for the QueryCacheManager -> MemoryCacheAdapter substitution (Phase A, Task 1).

Per spec §6.1 "pure substitution": QueryCacheManager delegates to
oneiric.adapters.cache.memory.MemoryCacheAdapter. The L2 DuckDB
``query_cache_l2`` infrastructure is dead (spec §10 risk #1) and deleted.

REQ traceability: REQ-OSUB-A-001 (substitution), REQ-OSUB-A-002 (L2 removal).
"""

from __future__ import annotations

import asyncio

import pytest

from oneiric.adapters.cache.memory import MemoryCacheAdapter

from session_buddy.cache.query_cache import QueryCacheManager


@pytest.mark.req(["REQ-OSUB-A-001"])
def test_query_cache_delegates_to_memory_adapter() -> None:
    qc = QueryCacheManager(l1_max_size=10)  # NOTE: l1_max_size (NOT max_size — pure substitution)
    qc.put("k", ["v"], normalized_query="q", project=None)
    assert qc.get("k") == ["v"]
    assert isinstance(qc._cache, MemoryCacheAdapter)


@pytest.mark.req(["REQ-OSUB-A-001"])
def test_query_cache_constructor_signature_preserved() -> None:
    """Per spec §6.1 pure substitution — constructor arg names unchanged."""
    qc = QueryCacheManager(l1_max_size=42, l2_ttl_days=3)
    assert qc.l1_max_size == 42
    assert qc.l2_ttl_seconds == 3 * 86400


@pytest.mark.req(["REQ-OSUB-A-001"])
def test_sync_api_raises_in_running_loop() -> None:
    """Sync API is non-blocking-call-safe. In async contexts, callers should hit the adapter directly."""
    qc = QueryCacheManager(l1_max_size=10)

    async def inside() -> None:
        qc.put("k", ["v"], normalized_query="q", project=None)

    with pytest.raises(RuntimeError, match="running event loop"):
        asyncio.run(inside())


@pytest.mark.req(["REQ-OSUB-A-001", "REQ-OSUB-A-002"])
def test_query_cache_l2_table_block_deleted() -> None:
    """The runtime CREATE TABLE query_cache_l2 block in query_cache.py is gone."""
    import subprocess
    result = subprocess.run(
        ["grep", "-n", "query_cache_l2", "session_buddy/cache/query_cache.py"],
        capture_output=True, text=True,
    )
    assert result.stdout == "", f"query_cache_l2 still in query_cache.py:\n{result.stdout}"
