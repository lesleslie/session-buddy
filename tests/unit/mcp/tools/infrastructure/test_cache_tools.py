"""Tests for ``session_buddy.mcp.tools.infrastructure.cache_tools``.

Covers the five MCP tools: query_cache_stats, clear_query_cache,
warm_cache, invalidate_cache, optimize_cache plus register_cache_tools
and the internal _resolve_db helper.

Pattern: monkeypatch ``_resolve_db`` (or the ``depends.get_sync`` symbol
it uses) so we can drive both the success path and the "no DB
registered" path.

Coverage target: 85-100% of source lines in cache_tools.py.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.infrastructure import cache_tools as cache_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Capture tool-registration calls so registered tools can run."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.tool_calls: list[object] = []

    def tool(self, *, name=None, description=None):
        def decorator(fn):
            entry_name = name or fn.__name__
            self.tools[entry_name] = fn
            self.tool_calls.append(fn)
            return fn

        return decorator


def _make_db(*, cache_present: bool = True) -> MagicMock:
    """Build a fake db with the ``_query_cache`` attribute the tools need."""
    db = MagicMock()
    if cache_present:
        cache = MagicMock()
        cache.get_stats = MagicMock(
            return_value={
                "l1_hits": 10,
                "l1_misses": 2,
                "l1_hit_rate": 0.83,
                "l2_hits": 4,
                "l2_misses": 1,
                "l2_hit_rate": 0.8,
            }
        )
        cache.l1_max_size = 100
        cache.l2_ttl_seconds = 86400  # 1 day
        cache._initialized = True
        cache.invalidate = MagicMock()
        cache._clear_l2 = MagicMock()
        cache.cleanup_expired = AsyncMock(return_value=5)
        db._query_cache = cache
    else:
        db._query_cache = None
    db.search_reflections = AsyncMock(return_value=["hit1", "hit2", "hit3"])
    return db


@pytest.fixture
def db_with_cache(monkeypatch: pytest.MonkeyPatch):
    """Patch _resolve_db to return a db with a populated query cache."""
    db = _make_db(cache_present=True)
    monkeypatch.setattr(cache_mod, "_resolve_db", lambda: db)
    return db


@pytest.fixture
def db_no_cache(monkeypatch: pytest.MonkeyPatch):
    """Patch _resolve_db to return a db without a query cache."""
    db = _make_db(cache_present=False)
    monkeypatch.setattr(cache_mod, "_resolve_db", lambda: db)
    return db


@pytest.fixture
def no_db(monkeypatch: pytest.MonkeyPatch):
    """Patch _resolve_db to return None (adapter missing)."""
    monkeypatch.setattr(cache_mod, "_resolve_db", lambda: None)
    return None


class _DummyCtx:
    """Stub for the FastMCP Context parameter (unused)."""


# ---------------------------------------------------------------------------
# _resolve_db
# ---------------------------------------------------------------------------


def test_resolve_db_returns_none_when_no_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """_resolve_db returns None when both adapter imports fail."""
    # Make the inner ``depends.get_sync`` raise so the sentinel path runs
    def boom(_):
        raise LookupError("not registered")

    monkeypatch.setattr(cache_mod, "depends", MagicMock(get_sync=boom))
    # Force ImportError on both reflection adapter imports
    import builtins

    real_import = builtins.__import__

    def _import_block(name, *a, **kw):
        if name.startswith("session_buddy.adapters.reflection_adapter"):
            raise ImportError("blocked")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _import_block)
    # Reload module so the import-guard re-runs
    import importlib

    reloaded = importlib.reload(cache_mod)
    assert reloaded._resolve_db() is None


def test_resolve_db_returns_none_when_adapter_lookup_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_db returns None when depends.get_sync raises."""
    monkeypatch.setattr(
        cache_mod, "depends", MagicMock(get_sync=MagicMock(side_effect=RuntimeError))
    )
    assert cache_mod._resolve_db() is None


# ---------------------------------------------------------------------------
# register_cache_tools
# ---------------------------------------------------------------------------


def test_register_cache_tools_registers_all_five() -> None:
    """register_cache_tools registers five MCP tools."""
    mcp = _FakeMCP()
    cache_mod.register_cache_tools(mcp)
    assert set(mcp.tools) == {
        "query_cache_stats",
        "clear_query_cache",
        "warm_cache",
        "invalidate_cache",
        "optimize_cache",
    }


# ---------------------------------------------------------------------------
# query_cache_stats
# ---------------------------------------------------------------------------


async def test_query_cache_stats_no_db(no_db) -> None:
    """Returns the not-initialized envelope when adapter missing."""
    out = await cache_mod.query_cache_stats(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is False
    assert "not initialized" in parsed["error"]


async def test_query_cache_stats_no_cache_attribute(db_no_cache) -> None:
    """Returns the not-initialized envelope when _query_cache is None."""
    out = await cache_mod.query_cache_stats(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is False
    assert "not initialized" in parsed["error"]


async def test_query_cache_stats_success(db_with_cache) -> None:
    """Returns enriched stats with hit-rate categories and efficiency."""
    db_with_cache._query_cache.get_stats.return_value = {
        "l1_hits": 30,
        "l1_misses": 5,
        "l1_hit_rate": 0.86,
        "l2_hits": 4,
        "l2_misses": 1,
        "l2_hit_rate": 0.8,
    }
    out = await cache_mod.query_cache_stats(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is True
    stats = parsed["stats"]
    assert stats["l1_max_size"] == 100
    assert stats["l2_ttl_days"] == 1.0  # 86400 / 86400
    assert stats["initialized"] is True
    interp = parsed["interpretation"]
    assert interp["l1_hit_rate_category"] == "Excellent"
    assert interp["l2_hit_rate_category"] == "Excellent"
    assert 0 < interp["cache_efficiency"] < 1


async def test_query_cache_stats_moderate_hit_rates(db_with_cache) -> None:
    """L1 > 0.3 (not 0.5) → 'Good' category."""
    db_with_cache._query_cache.get_stats.return_value = {
        "l1_hits": 5,
        "l1_misses": 10,
        "l1_hit_rate": 0.4,
        "l2_hits": 1,
        "l2_misses": 2,
        "l2_hit_rate": 0.4,
    }
    parsed = json.loads(await cache_mod.query_cache_stats(_DummyCtx()))
    assert parsed["interpretation"]["l1_hit_rate_category"] == "Good"
    assert parsed["interpretation"]["l2_hit_rate_category"] == "Good"


async def test_query_cache_stats_low_hit_rates(db_with_cache) -> None:
    """L1 <= 0.3 → 'Needs warming'; L2 <= 0.3 → 'Low'."""
    db_with_cache._query_cache.get_stats.return_value = {
        "l1_hits": 1,
        "l1_misses": 9,
        "l1_hit_rate": 0.1,
        "l2_hits": 1,
        "l2_misses": 9,
        "l2_hit_rate": 0.1,
    }
    parsed = json.loads(await cache_mod.query_cache_stats(_DummyCtx()))
    assert parsed["interpretation"]["l1_hit_rate_category"] == "Needs warming"
    assert parsed["interpretation"]["l2_hit_rate_category"] == "Low"


async def test_query_cache_stats_handles_exception(
    db_with_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any unexpected error is caught and surfaced as success=False."""
    # Make get_stats itself blow up so the bare ``except`` branch fires
    db_with_cache._query_cache.get_stats.side_effect = RuntimeError("boom")
    out = await cache_mod.query_cache_stats(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is False
    assert "boom" in parsed["error"]


# ---------------------------------------------------------------------------
# clear_query_cache
# ---------------------------------------------------------------------------


async def test_clear_query_cache_no_db(no_db) -> None:
    """Returns not-initialized when no adapter registered."""
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx(), "l1"))
    assert parsed["success"] is False


async def test_clear_query_cache_no_cache(db_no_cache) -> None:
    """Returns not-initialized when _query_cache is None."""
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx(), "l1"))
    assert parsed["success"] is False


async def test_clear_query_cache_l1_only(db_with_cache) -> None:
    """cache_level='l1' clears L1 but not L2."""
    out = await cache_mod.clear_query_cache(_DummyCtx(), "l1")
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert parsed["cleared"]["l1"] is True
    assert parsed["cleared"]["l2"] is False
    db_with_cache._query_cache.invalidate.assert_called_once_with()
    db_with_cache._query_cache._clear_l2.assert_not_called()


async def test_clear_query_cache_l2_only(db_with_cache) -> None:
    """cache_level='l2' clears L2 but not L1."""
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx(), "l2"))
    assert parsed["cleared"]["l1"] is False
    assert parsed["cleared"]["l2"] is True
    db_with_cache._query_cache.invalidate.assert_not_called()
    db_with_cache._query_cache._clear_l2.assert_called_once_with()


async def test_clear_query_cache_all(db_with_cache) -> None:
    """cache_level='all' (default) clears both."""
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx()))
    assert parsed["cleared"]["l1"] is True
    assert parsed["cleared"]["l2"] is True
    db_with_cache._query_cache.invalidate.assert_called_once_with()
    db_with_cache._query_cache._clear_l2.assert_called_once_with()


async def test_clear_query_cache_handles_exception(
    db_with_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure in invalidate() surfaces as success=False."""
    db_with_cache._query_cache.invalidate.side_effect = RuntimeError("kill fail")
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx(), "l1"))
    assert parsed["success"] is False
    assert "kill fail" in parsed["error"]


# ---------------------------------------------------------------------------
# warm_cache
# ---------------------------------------------------------------------------


async def test_warm_cache_empty_queries(db_with_cache) -> None:
    """Empty queries list short-circuits before touching the cache."""
    parsed = json.loads(await cache_mod.warm_cache(_DummyCtx(), []))
    assert parsed["success"] is False
    assert "No queries" in parsed["error"]
    db_with_cache.search_reflections.assert_not_called()


async def test_warm_cache_no_db(no_db) -> None:
    """Returns not-initialized when no adapter."""
    parsed = json.loads(await cache_mod.warm_cache(_DummyCtx(), ["q"]))
    assert parsed["success"] is False


async def test_warm_cache_no_cache(db_no_cache) -> None:
    """Returns not-initialized when _query_cache missing."""
    parsed = json.loads(await cache_mod.warm_cache(_DummyCtx(), ["q"]))
    assert parsed["success"] is False


async def test_warm_cache_success(db_with_cache) -> None:
    """Successful warm returns per-query outcomes + before/after stats."""
    out = await cache_mod.warm_cache(_DummyCtx(), ["alpha", "beta"])
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert len(parsed["results"]) == 2
    assert all(r["success"] is True for r in parsed["results"])
    # db.search_reflections should have been called twice
    assert db_with_cache.search_reflections.await_count == 2
    # use_cache=True keyword is forwarded
    db_with_cache.search_reflections.assert_awaited_with(
        "beta", limit=10, use_cache=True
    )


async def test_warm_cache_partial_failure(db_with_cache) -> None:
    """Per-query errors are captured as success=False in results list."""
    async def search_then_fail(query, **kwargs):
        if query == "good":
            return ["a"]
        raise ValueError("only this one fails")

    db_with_cache.search_reflections.side_effect = search_then_fail
    parsed = json.loads(
        await cache_mod.warm_cache(_DummyCtx(), ["good", "bad"])
    )
    assert parsed["success"] is True
    assert parsed["results"][0]["success"] is True
    assert parsed["results"][1]["success"] is False
    assert "only this one fails" in parsed["results"][1]["error"]


async def test_warm_cache_top_level_failure(db_with_cache) -> None:
    """If ``_resolve_db`` itself blows up, success=False at the envelope."""
    monkeypatch_obj = db_with_cache
    # Make get_stats raise (after _resolve_db succeeds, so the outer except fires)
    monkeypatch_obj._query_cache.get_stats.side_effect = RuntimeError("stat fail")
    parsed = json.loads(await cache_mod.warm_cache(_DummyCtx(), ["q"]))
    assert parsed["success"] is False
    assert "stat fail" in parsed["error"]


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------


async def test_invalidate_cache_no_db(no_db) -> None:
    """Returns not-initialized when no adapter."""
    parsed = json.loads(
        await cache_mod.invalidate_cache(_DummyCtx(), query="x")
    )
    assert parsed["success"] is False


async def test_invalidate_cache_no_cache(db_no_cache) -> None:
    """Returns not-initialized when _query_cache missing."""
    parsed = json.loads(
        await cache_mod.invalidate_cache(_DummyCtx(), query="x")
    )
    assert parsed["success"] is False


async def test_invalidate_cache_success(db_with_cache) -> None:
    """Success path invalidates by the computed cache key."""
    out = await cache_mod.invalidate_cache(_DummyCtx(), query="hello")
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert "Cache entry invalidated" in parsed["message"]
    assert "cache_key" in parsed
    # The cache should have been told to invalidate the computed key
    db_with_cache._query_cache.invalidate.assert_called_once()
    args, kwargs = db_with_cache._query_cache.invalidate.call_args
    assert kwargs.get("cache_key") == parsed["cache_key"]


async def test_invalidate_cache_with_project(db_with_cache) -> None:
    """Project is included in the cache key computation."""
    out = await cache_mod.invalidate_cache(
        _DummyCtx(), query="hello", project="proj_a"
    )
    parsed = json.loads(out)
    assert parsed["success"] is True


async def test_invalidate_cache_handles_exception(
    db_with_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure in cache.invalidate() surfaces as success=False."""
    db_with_cache._query_cache.invalidate.side_effect = RuntimeError("kill fail")
    parsed = json.loads(
        await cache_mod.invalidate_cache(_DummyCtx(), query="x")
    )
    assert parsed["success"] is False
    assert "kill fail" in parsed["error"]


# ---------------------------------------------------------------------------
# optimize_cache
# ---------------------------------------------------------------------------


async def test_optimize_cache_no_db(no_db) -> None:
    """Returns not-initialized when no adapter."""
    parsed = json.loads(await cache_mod.optimize_cache(_DummyCtx()))
    assert parsed["success"] is False


async def test_optimize_cache_no_cache(db_no_cache) -> None:
    """Returns not-initialized when _query_cache missing."""
    parsed = json.loads(await cache_mod.optimize_cache(_DummyCtx()))
    assert parsed["success"] is False


async def test_optimize_cache_default(db_with_cache) -> None:
    """Default args: cleanup_expired=True, compact_l2=True."""
    out = await cache_mod.optimize_cache(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert parsed["results"]["expired_entries_removed"] == 5
    assert parsed["results"]["l2_compacted"] is True
    db_with_cache._query_cache.cleanup_expired.assert_awaited_once()


async def test_optimize_cache_no_cleanup(db_with_cache) -> None:
    """cleanup_expired=False skips the cleanup call."""
    parsed = json.loads(
        await cache_mod.optimize_cache(_DummyCtx(), cleanup_expired=False)
    )
    assert parsed["success"] is True
    assert "expired_entries_removed" not in parsed["results"]
    db_with_cache._query_cache.cleanup_expired.assert_not_called()


async def test_optimize_cache_no_compact(db_with_cache) -> None:
    """compact_l2=False skips the l2_compacted flag."""
    parsed = json.loads(
        await cache_mod.optimize_cache(_DummyCtx(), compact_l2=False)
    )
    assert parsed["success"] is True
    assert "l2_compacted" not in parsed["results"]


async def test_optimize_cache_handles_exception(
    db_with_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cleanup_expired() failure is surfaced as success=False."""
    db_with_cache._query_cache.cleanup_expired.side_effect = RuntimeError(
        "cleanup fail"
    )
    parsed = json.loads(await cache_mod.optimize_cache(_DummyCtx()))
    assert parsed["success"] is False
    assert "cleanup fail" in parsed["error"]


# ---------------------------------------------------------------------------
# Round-trip: register + invoke each tool
# ---------------------------------------------------------------------------


async def test_registered_tools_round_trip(db_with_cache) -> None:
    """Calling each registered MCP tool delegates to its async function."""
    mcp = _FakeMCP()
    cache_mod.register_cache_tools(mcp)
    out = await mcp.tools["query_cache_stats"](_DummyCtx())
    assert "stats" in json.loads(out)
    out = await mcp.tools["clear_query_cache"](_DummyCtx(), "all")
    assert "cleared" in json.loads(out)
    out = await mcp.tools["warm_cache"](_DummyCtx(), ["x"])
    assert "results" in json.loads(out)
    out = await mcp.tools["invalidate_cache"](_DummyCtx(), query="x")
    assert "cache_key" in json.loads(out)
    out = await mcp.tools["optimize_cache"](_DummyCtx())
    assert "results" in json.loads(out)


async def test_registered_tools_when_no_db(no_db) -> None:
    """All registered tools return the not-initialized envelope."""
    mcp = _FakeMCP()
    cache_mod.register_cache_tools(mcp)
    out = await mcp.tools["query_cache_stats"](_DummyCtx())
    assert json.loads(out)["success"] is False
    out = await mcp.tools["clear_query_cache"](_DummyCtx())
    assert json.loads(out)["success"] is False
    out = await mcp.tools["warm_cache"](_DummyCtx(), ["x"])
    assert json.loads(out)["success"] is False
    out = await mcp.tools["invalidate_cache"](_DummyCtx(), query="x")
    assert json.loads(out)["success"] is False
    out = await mcp.tools["optimize_cache"](_DummyCtx())
    assert json.loads(out)["success"] is False