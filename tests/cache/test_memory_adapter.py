#!/usr/bin/env python3
"""Tests for the query_cache substrate-adoption cleanup (Phase B, Task 1).

After the substrate-adoption cleanup the file ships two module-level
helpers (``normalize_query``, ``compute_cache_key``) and a re-export of
the substrate ``MemoryCacheAdapter`` — the legacy ``QueryCacheManager``
wrapper was deleted. The shim restoration adds a thin
``TrackedCacheAdapter`` wrapper for hit-rate observability
(REQ-OSUB-B-003).

REQ traceability: REQ-OSUB-B-001 (delete wrapper), REQ-OSUB-B-002
(re-export adapter), REQ-OSUB-B-003 (TrackedCacheAdapter shim).
"""

from __future__ import annotations

import pytest

from oneiric.adapters.cache.memory import MemoryCacheAdapter

from session_buddy.cache.query_cache import (
    MemoryCacheSettings,
    TrackedCacheAdapter,
    compute_cache_key,
    normalize_query,
)


@pytest.mark.req(["REQ-OSUB-B-001"])
def test_normalize_query_lowercases_and_strips_punctuation() -> None:
    """Module-level helper preserves the historical normalize_query contract."""
    assert normalize_query("What did I  learn about  async?") == (
        "what did i learn about async"
    )
    assert normalize_query("  Find insights on authentication  ") == (
        "find insights on authentication"
    )


@pytest.mark.req(["REQ-OSUB-B-001"])
def test_compute_cache_key_is_deterministic() -> None:
    """Same inputs -> same SHA256 hex digest."""
    k1 = compute_cache_key("async patterns", project="myapp", limit=10)
    k2 = compute_cache_key("async patterns", project="myapp", limit=10)
    assert k1 == k2
    assert len(k1) == 64  # SHA256 hex digest length


@pytest.mark.req(["REQ-OSUB-B-001"])
def test_compute_cache_key_differs_with_kwargs() -> None:
    """Different kwargs -> different keys (kwargs are part of the hash)."""
    base = compute_cache_key("auth", limit=10)
    with_min_score = compute_cache_key("auth", limit=10, min_score=0.8)
    assert base != with_min_score


@pytest.mark.req(["REQ-OSUB-B-001"])
def test_compute_cache_key_includes_project() -> None:
    """Project filter changes the cache key."""
    no_project = compute_cache_key("auth", limit=10)
    with_project = compute_cache_key("auth", limit=10, project="myapp")
    assert no_project != with_project


@pytest.mark.req(["REQ-OSUB-B-002"])
def test_memory_cache_adapter_re_export() -> None:
    """The substrate adapter is reachable from session_buddy.cache.query_cache."""
    settings = MemoryCacheSettings(max_entries=10, default_ttl=60.0)
    adapter = MemoryCacheAdapter(settings)
    assert adapter._settings.max_entries == 10
    assert adapter._settings.default_ttl == 60.0


@pytest.mark.req(["REQ-OSUB-B-002"])
async def test_memory_cache_adapter_set_get_round_trip() -> None:
    """The re-exported adapter behaves like the substrate one — round-trips."""
    adapter = MemoryCacheAdapter(MemoryCacheSettings(max_entries=10))
    await adapter.set("k", ["v1", "v2"])
    assert await adapter.get("k") == ["v1", "v2"]


@pytest.mark.req(["REQ-OSUB-B-002"])
async def test_memory_cache_adapter_clear_empties_store() -> None:
    """``clear()`` is the L1/L2-consolidated eviction path."""
    adapter = MemoryCacheAdapter(MemoryCacheSettings(max_entries=10))
    await adapter.set("a", [1])
    await adapter.set("b", [2])
    await adapter.clear()
    assert await adapter.get("a") is None
    assert await adapter.get("b") is None


@pytest.mark.req(["REQ-OSUB-B-001"])
def test_query_cache_manager_class_deleted() -> None:
    """The legacy ``QueryCacheManager`` wrapper was deleted (pre-1.0
    replace-not-extend)."""
    with pytest.raises(ImportError):
        # runtime guard: importing the symbol must fail now.
        from session_buddy.cache.query_cache import QueryCacheManager  # noqa: F401


# ---------------------------------------------------------------------------
# TrackedCacheAdapter shim (REQ-OSUB-B-003)
# ---------------------------------------------------------------------------


@pytest.mark.req(["REQ-OSUB-B-003"])
async def test_tracked_cache_adapter_hits_and_misses() -> None:
    """Hits and misses are tracked per call; get_stats() surfaces them."""
    shim = TrackedCacheAdapter(MemoryCacheSettings(max_entries=10))
    await shim.set("k1", ["v1"])
    await shim.set("k2", ["v2"])

    # Two hits, one miss.
    assert await shim.get("k1") == ["v1"]
    assert await shim.get("k2") == ["v2"]
    assert await shim.get("missing") is None

    stats = shim.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate"] == pytest.approx(2 / 3)
    assert stats["current_entries"] == 2


@pytest.mark.req(["REQ-OSUB-B-003"])
async def test_tracked_cache_adapter_hit_rate_zero_when_no_lookups() -> None:
    """hit_rate is 0.0 (not a division-by-zero error) when no get() has been called."""
    shim = TrackedCacheAdapter(MemoryCacheSettings(max_entries=10))
    stats = shim.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["hit_rate"] == 0.0


@pytest.mark.req(["REQ-OSUB-B-003"])
def test_tracked_cache_adapter_cleanup_expired_is_noop() -> None:
    """cleanup_expired() returns 0 — the substrate uses TTL-on-write, no lazy eviction."""
    shim = TrackedCacheAdapter(MemoryCacheSettings(max_entries=10))
    assert shim.cleanup_expired() == 0


@pytest.mark.req(["REQ-OSUB-B-003"])
async def test_tracked_cache_adapter_invalidate_clears_store() -> None:
    """invalidate() is the preserved alias for clear() — used by the shutdown path."""
    shim = TrackedCacheAdapter(MemoryCacheSettings(max_entries=10))
    await shim.set("k1", ["v1"])
    await shim.invalidate()
    assert shim.get_stats()["current_entries"] == 0
    assert await shim.get("k1") is None


@pytest.mark.req(["REQ-OSUB-B-003"])
def test_tracked_cache_adapter_store_property_exposes_underlying() -> None:
    """The _store property is the shim's read-only view into the underlying adapter."""
    shim = TrackedCacheAdapter(MemoryCacheSettings(max_entries=10))
    assert shim._store == {}
    # Setting through the substrate and reading through the shim property
    # gives the same dict.
    await_set = shim._adapter
    assert shim._store is await_set._store
