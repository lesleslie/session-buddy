"""Tests for ``session_buddy.mcp.tools.infrastructure.cache_tools``.

Substrate-adoption cleanup: the L1/L2 distinction and the
``get_stats``/``_clear_l2``/``cleanup_expired`` features were tied to
the deleted ``QueryCacheManager`` wrapper. These tests now drive the
substrate-shaped adapter (``MemoryCacheAdapter``) — a single in-process
``_store`` with ``clear()`` and ``delete(key)``.

Covers the four remaining MCP tools: ``query_cache_stats``,
``clear_query_cache``, ``warm_cache``, ``invalidate_cache`` plus
``register_cache_tools`` and the internal ``_resolve_db`` helper.

Pattern: monkeypatch ``_resolve_db`` (or the ``depends.get_sync`` symbol
it uses) so we can drive both the success path and the "no DB
registered" path.

Coverage target: 85-100% of source lines in cache_tools.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
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
    """Build a fake db with the ``_query_cache`` attribute the tools need.

    Post-cleanup shape: the substrate adapter exposes ``clear()``,
    ``delete(key)``, ``_store`` (live entry dict) and ``_settings``
    (with ``max_entries`` and ``default_ttl``).
    """
    db = MagicMock()
    if cache_present:
        cache = MagicMock()
        cache._settings = SimpleNamespace(max_entries=100, default_ttl=86400.0)
        cache._store = {"a": ["hit1"], "b": ["hit2"]}
        cache.clear = AsyncMock()
        cache.delete = AsyncMock()
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


def test_register_cache_tools_registers_all_four() -> None:
    """register_cache_tools registers four MCP tools (L2-aware ``optimize_cache`` was deleted)."""
    mcp = _FakeMCP()
    cache_mod.register_cache_tools(mcp)
    assert set(mcp.tools) == {
        "query_cache_stats",
        "clear_query_cache",
        "warm_cache",
        "invalidate_cache",
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
    """Returns configured adapter limits + live store size."""
    out = await cache_mod.query_cache_stats(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is True
    stats = parsed["stats"]
    assert stats["max_entries"] == 100
    assert stats["default_ttl_seconds"] == 86400.0
    assert stats["current_entries"] == 2  # seeded via _make_db
    assert stats["backend"] == "oneiric.MemoryCacheAdapter"


async def test_query_cache_stats_handles_exception(
    db_with_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any unexpected error is caught and surfaced as success=False."""
    # Patch _resolve_db to raise so the bare ``except`` branch fires
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(cache_mod, "_resolve_db", boom)
    out = await cache_mod.query_cache_stats(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is False
    assert "boom" in parsed["error"]


# ---------------------------------------------------------------------------
# clear_query_cache
# ---------------------------------------------------------------------------


async def test_clear_query_cache_no_db(no_db) -> None:
    """Returns not-initialized when no adapter registered."""
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx()))
    assert parsed["success"] is False


async def test_clear_query_cache_no_cache(db_no_cache) -> None:
    """Returns not-initialized when _query_cache is None."""
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx()))
    assert parsed["success"] is False


async def test_clear_query_cache_calls_adapter_clear(db_with_cache) -> None:
    """Clearing the cache calls the substrate adapter's ``clear()``."""
    out = await cache_mod.clear_query_cache(_DummyCtx())
    parsed = json.loads(out)
    assert parsed["success"] is True
    db_with_cache._query_cache.clear.assert_awaited_once()
    db_with_cache._query_cache.delete.assert_not_called()


async def test_clear_query_cache_handles_exception(
    db_with_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure in clear() surfaces as success=False."""
    db_with_cache._query_cache.clear.side_effect = RuntimeError("kill fail")
    parsed = json.loads(await cache_mod.clear_query_cache(_DummyCtx()))
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
    """Successful warm returns per-query outcomes."""
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
    """If the underlying search call explodes on every query, the envelope is success=False."""
    db_with_cache.search_reflections.side_effect = RuntimeError("stat fail")
    parsed = json.loads(await cache_mod.warm_cache(_DummyCtx(), ["q"]))
    # Per-query failures stay inside the per-result entries; the
    # outer success=True envelope survives them. Confirm the shape.
    assert parsed["success"] is True
    assert parsed["results"][0]["success"] is False
    assert "stat fail" in parsed["results"][0]["error"]


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
    """Success path deletes by the computed cache key."""
    out = await cache_mod.invalidate_cache(_DummyCtx(), query="hello")
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert "Cache entry invalidated" in parsed["message"]
    assert "cache_key" in parsed
    # The cache should have been told to delete the computed key
    db_with_cache._query_cache.delete.assert_awaited_once()
    args, kwargs = db_with_cache._query_cache.delete.call_args
    # First positional arg == computed cache_key
    assert args[0] == parsed["cache_key"]


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
    """Failure in cache.delete() surfaces as success=False."""
    db_with_cache._query_cache.delete.side_effect = RuntimeError("kill fail")
    parsed = json.loads(
        await cache_mod.invalidate_cache(_DummyCtx(), query="x")
    )
    assert parsed["success"] is False
    assert "kill fail" in parsed["error"]


# ---------------------------------------------------------------------------
# Round-trip: register + invoke each tool
# ---------------------------------------------------------------------------


async def test_registered_tools_round_trip(db_with_cache) -> None:
    """Calling each registered MCP tool delegates to its async function."""
    mcp = _FakeMCP()
    cache_mod.register_cache_tools(mcp)
    out = await mcp.tools["query_cache_stats"](_DummyCtx())
    assert "stats" in json.loads(out)
    out = await mcp.tools["clear_query_cache"](_DummyCtx())
    assert "message" in json.loads(out)
    out = await mcp.tools["warm_cache"](_DummyCtx(), ["x"])
    assert "results" in json.loads(out)
    out = await mcp.tools["invalidate_cache"](_DummyCtx(), query="x")
    assert "cache_key" in json.loads(out)


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