from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


class DummyMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class DummyCache:
    """Post-substrate-cleanup shape: MemoryCacheAdapter-like with the
    ``TrackedCacheAdapter`` shim surface.

    The historical L1/L2 split is gone; the substrate adapter exposes
    a single store, ``clear()``, ``delete(key)``, and ``_settings``.
    The shim adds ``get_stats()`` (returns the substrate-shaped stats
    plus hit-rate fields) and ``cleanup_expired()`` (returns 0; no-op
    for the substrate's TTL-on-write model).
    """

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {}
        self._settings = SimpleNamespace(max_entries=100, default_ttl=86400.0)
        self.cleared = False
        self.deleted: list[str] = []
        self.cleanup_called = False

    async def clear(self) -> None:
        self._store.clear()
        self.cleared = True

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self.deleted.append(key)

    def get_stats(self) -> dict:
        return {
            "max_entries": self._settings.max_entries,
            "default_ttl_seconds": self._settings.default_ttl,
            "current_entries": len(self._store),
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "backend": "oneiric.MemoryCacheAdapter",
        }

    def cleanup_expired(self) -> int:
        self.cleanup_called = True
        return 0


class DummyDb:
    def __init__(self, cache: DummyCache | None) -> None:
        self._query_cache = cache
        self.search_calls: list[tuple[str, int, bool]] = []

    async def search_reflections(self, query: str, limit: int, use_cache: bool) -> list[str]:
        self.search_calls.append((query, limit, use_cache))
        return [f"result:{query}"]


@pytest.fixture
def cache_tools_module():
    from session_buddy.mcp.tools.infrastructure import cache_tools

    return cache_tools


def test_register_cache_tools_registers_expected_tools(cache_tools_module) -> None:
    mcp = DummyMCP()

    cache_tools_module.register_cache_tools(mcp)

    assert {
        "query_cache_stats",
        "clear_query_cache",
        "warm_cache",
        "invalidate_cache",
        "optimize_cache",
    }.issubset(mcp.tools)


@pytest.mark.asyncio
async def test_query_cache_stats_and_clear_cache_paths(
    monkeypatch: pytest.MonkeyPatch,
    cache_tools_module,
) -> None:
    cache = DummyCache()
    db = DummyDb(cache)
    monkeypatch.setattr(
        "session_buddy.di.depends.get_sync",
        lambda key: db,
    )

    stats = json.loads(await cache_tools_module.query_cache_stats(None))
    assert stats["success"] is True
    assert stats["stats"]["max_entries"] == 100
    assert stats["stats"]["backend"] == "oneiric.MemoryCacheAdapter"

    cleared = json.loads(await cache_tools_module.clear_query_cache(None))
    assert cleared["success"] is True
    assert cache.cleared is True


@pytest.mark.asyncio
async def test_query_cache_stats_and_clear_cache_without_cache(
    monkeypatch: pytest.MonkeyPatch,
    cache_tools_module,
) -> None:
    monkeypatch.setattr(
        "session_buddy.di.depends.get_sync",
        lambda key: DummyDb(None),
    )

    stats = json.loads(await cache_tools_module.query_cache_stats(None))
    cleared = json.loads(await cache_tools_module.clear_query_cache(None))

    assert stats["success"] is False
    assert "not initialized" in stats["error"]
    assert cleared["success"] is False
    assert "not initialized" in cleared["error"]


@pytest.mark.asyncio
async def test_warm_and_invalidate_cache_paths(
    monkeypatch: pytest.MonkeyPatch,
    cache_tools_module,
) -> None:
    cache = DummyCache()
    db = DummyDb(cache)
    monkeypatch.setattr(
        "session_buddy.di.depends.get_sync",
        lambda key: db,
    )

    empty = json.loads(await cache_tools_module.warm_cache(None, []))
    assert empty["success"] is False

    warmed = json.loads(
        await cache_tools_module.warm_cache(None, ["alpha", "beta"])
    )
    assert warmed["success"] is True
    assert len(db.search_calls) == 2
    assert warmed["results"][0]["success"] is True

    invalidated = json.loads(
        await cache_tools_module.invalidate_cache(None, "alpha", project="p1")
    )
    assert invalidated["success"] is True
    assert cache.deleted[-1] == invalidated["cache_key"]

    optimized = json.loads(await cache_tools_module.optimize_cache(None))
    assert optimized["success"] is True
    assert optimized["entries_cleaned"] == 0
    assert cache.cleanup_called is True
    assert "hit_rate" in optimized["stats"]
