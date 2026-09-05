"""Tests for session_buddy.mcp.tools.infrastructure.history_cache.

Covers the native TTL cache used for history analysis:
- ``HistoryAnalysisCache``: get/set/clear/is_expired + TTL expiry
- ``get_cache``: lazy global initialization, ttl argument
- ``reset_cache``: clears and resets global
- ``ACBHistoryCache``: backwards-compatible alias
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

from session_buddy.mcp.tools.infrastructure import history_cache as mod
from session_buddy.mcp.tools.infrastructure.history_cache import (
    ACBHistoryCache,
    HistoryAnalysisCache,
    get_cache,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Reset module-level global cache between tests."""
    reset_cache()
    yield
    reset_cache()


class TestHistoryAnalysisCacheInit:
    """Cache constructor + initial state."""

    def test_default_ttl_is_300(self) -> None:
        cache = HistoryAnalysisCache()
        assert cache._ttl == 300.0
        assert isinstance(cache._created_at, datetime)

    def test_custom_ttl(self) -> None:
        cache = HistoryAnalysisCache(ttl=12.5)
        assert cache._ttl == 12.5

    def test_starts_empty(self) -> None:
        cache = HistoryAnalysisCache()
        assert cache._cache == {}
        assert cache.get("missing") is None


class TestHistoryAnalysisCacheGetSet:
    """Cache get/set primitives."""

    def test_set_then_get_roundtrip(self) -> None:
        cache = HistoryAnalysisCache(ttl=300.0)
        cache.set("k", {"value": 42})
        assert cache.get("k") == {"value": 42}

    def test_get_missing_key_returns_default_none(self) -> None:
        cache = HistoryAnalysisCache()
        assert cache.get("absent") is None

    def test_get_missing_key_returns_custom_default(self) -> None:
        cache = HistoryAnalysisCache()
        sentinel: Any = object()
        assert cache.get("absent", default=sentinel) is sentinel

    def test_set_overwrites_value(self) -> None:
        cache = HistoryAnalysisCache(ttl=300.0)
        cache.set("k", "v1")
        cache.set("k", "v2")
        assert cache.get("k") == "v2"


class TestHistoryAnalysisCacheClear:
    """Cache.clear removes all entries."""

    def test_clear_empties_cache(self) -> None:
        cache = HistoryAnalysisCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        assert cache._cache == {}
        assert cache.get("k1") is None
        assert cache.get("k2") is None

    def test_clear_when_empty_does_not_raise(self) -> None:
        cache = HistoryAnalysisCache()
        cache.clear()  # no-op
        assert cache._cache == {}


class TestHistoryAnalysisCacheIsExpired:
    """Cache.is_expired behavior."""

    def test_missing_key_is_expired(self) -> None:
        cache = HistoryAnalysisCache()
        assert cache.is_expired("nope") is True

    def test_fresh_key_is_not_expired(self) -> None:
        cache = HistoryAnalysisCache(ttl=300.0)
        cache.set("k", "v")
        assert cache.is_expired("k") is False

    def test_old_key_is_expired(self) -> None:
        cache = HistoryAnalysisCache(ttl=0.001)
        cache.set("k", "v")
        # Force expiry by patching utc_now to a future instant.
        original_now = mod.utc_now
        future = original_now() + timedelta(seconds=10)
        with patch.object(mod, "utc_now", return_value=future):
            assert cache.is_expired("k") is True


class TestHistoryAnalysisCacheTtlExpiryOnGet:
    """Expired entries are removed on access."""

    def test_expired_entry_returns_default(self) -> None:
        cache = HistoryAnalysisCache(ttl=0.001)
        cache.set("k", "v")
        future = mod.utc_now() + timedelta(seconds=10)
        with patch.object(mod, "utc_now", return_value=future):
            assert cache.get("k") is None

    def test_expired_entry_removed_from_cache(self) -> None:
        cache = HistoryAnalysisCache(ttl=0.001)
        cache.set("k", "v")
        future = mod.utc_now() + timedelta(seconds=10)
        with patch.object(mod, "utc_now", return_value=future):
            cache.get("k")
        assert "k" not in cache._cache

    def test_get_within_ttl_keeps_entry(self) -> None:
        cache = HistoryAnalysisCache(ttl=300.0)
        cache.set("k", "v")
        cache.get("k")
        assert "k" in cache._cache

    def test_expired_get_returns_custom_default(self) -> None:
        cache = HistoryAnalysisCache(ttl=0.001)
        cache.set("k", "v")
        future = mod.utc_now() + timedelta(seconds=10)
        sentinel: Any = object()
        with patch.object(mod, "utc_now", return_value=future):
            assert cache.get("k", default=sentinel) is sentinel


class TestGlobalCacheSingleton:
    """Module-level singleton helpers."""

    def test_get_cache_returns_singleton(self) -> None:
        a = get_cache()
        b = get_cache()
        assert a is b

    def test_get_cache_default_ttl(self) -> None:
        c = get_cache()
        assert c._ttl == 300.0
        assert isinstance(c, HistoryAnalysisCache)

    def test_get_cache_passes_ttl_only_on_first_init(self) -> None:
        c1 = get_cache(ttl=42.0)
        # Subsequent calls ignore new ttl (singleton pattern).
        c2 = get_cache(ttl=999.0)
        assert c1 is c2
        assert c1._ttl == 42.0

    def test_reset_cache_clears_data(self) -> None:
        c = get_cache()
        c.set("k", "v")
        reset_cache()
        # After reset, get_cache creates a new instance.
        c2 = get_cache()
        assert c2 is not c
        assert c2.get("k") is None

    def test_reset_cache_when_none_safe(self) -> None:
        # First ensure it's None.
        reset_cache()
        # Calling again should still be safe.
        reset_cache()
        # And get_cache() still works.
        c = get_cache()
        assert c is not None


class TestACBHistoryCacheAlias:
    """Backwards-compat alias resolves to HistoryAnalysisCache."""

    def test_alias_is_same_class(self) -> None:
        assert ACBHistoryCache is HistoryAnalysisCache

    def test_alias_can_be_instantiated(self) -> None:
        cache = ACBHistoryCache(ttl=10.0)
        cache.set("k", "v")
        assert cache.get("k") == "v"


class TestTtlHash:
    """Internal TTL hash helper."""

    def test_ttl_hash_returns_iso_string(self) -> None:
        # _ttl_hash uses utc_now().isoformat() — verify it's a string.
        result = mod._ttl_hash()
        assert isinstance(result, str)
        # And it parses back.
        parsed = datetime.fromisoformat(result)
        assert isinstance(parsed, datetime)


class TestModuleExports:
    """Module surface is stable."""

    def test_module_has_expected_symbols(self) -> None:
        assert isinstance(mod, ModuleType)
        for name in (
            "HistoryAnalysisCache",
            "ACBHistoryCache",
            "get_cache",
            "reset_cache",
            "_ttl_hash",
        ):
            assert hasattr(mod, name)
