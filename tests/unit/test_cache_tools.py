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
    def __init__(self) -> None:
        self.l1_max_size = 100
        self.l2_ttl_seconds = 86400
        self._initialized = True
        self.invalidated: list[str | None] = []
        self.l2_cleared = False
        self.cleaned = False

    def get_stats(self) -> dict[str, float]:
        return {
            "l1_hit_rate": 0.6,
            "l2_hit_rate": 0.4,
            "l1_size": 3,
        }

    def invalidate(self, cache_key: str | None = None) -> None:
        self.invalidated.append(cache_key)

    def _clear_l2(self) -> None:
        self.l2_cleared = True

    async def cleanup_expired(self) -> int:
        self.cleaned = True
        return 2


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
    assert stats["stats"]["l1_max_size"] == 100
    assert stats["interpretation"]["l1_hit_rate_category"] == "Excellent"

    cleared = json.loads(await cache_tools_module.clear_query_cache(None, "all"))
    assert cleared["success"] is True
    assert cache.l2_cleared is True
    assert cache.invalidated == [None]


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
async def test_warm_invalidate_and_optimize_cache_paths(
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
    assert cache.invalidated[-1] == invalidated["cache_key"]

    optimized = json.loads(
        await cache_tools_module.optimize_cache(None, compact_l2=True, cleanup_expired=True)
    )
    assert optimized["success"] is True
    assert optimized["results"]["expired_entries_removed"] == 2
    assert optimized["results"]["l2_compacted"] is True
    assert cache.cleaned is True
