"""Tests for session_buddy.mcp.tools.infrastructure.history_cache.

Lifts line coverage to >=95% and branch coverage to >=90% for the
small ``HistoryAnalysisCache`` module. The module exposes:

- ``HistoryAnalysisCache`` (TTLCache implementation)
- ``get_cache`` / ``reset_cache`` (process-global cache helpers)
- ``ACBHistoryCache`` (backwards-compatible class alias)

The ``utc_now`` import from ``session_buddy.utils.time`` is monkeypatched
in each time-driven test so that the cache's age math is fully
deterministic — the module never calls ``datetime.now()`` directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Module-level smoke
# ---------------------------------------------------------------------------


def test_module_public_symbols_are_importable() -> None:
    """Every public symbol listed in the module's public surface is importable.

    This is the MCP smoke check required by the per-module brief.
    """
    from session_buddy.mcp.tools.infrastructure import history_cache

    assert history_cache.HistoryAnalysisCache is not None
    assert history_cache.get_cache is not None
    assert history_cache.reset_cache is not None
    assert history_cache.ACBHistoryCache is not None


def test_acb_history_cache_is_alias_for_history_analysis_cache() -> None:
    """The backwards-compatible alias points at the canonical class."""
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        ACBHistoryCache,
        HistoryAnalysisCache,
    )

    assert ACBHistoryCache is HistoryAnalysisCache


# ---------------------------------------------------------------------------
# Clock fixture used by every test that depends on age / TTL math
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[datetime]]:
    """Freeze the cache module's ``utc_now`` and let the caller advance it.

    Yields a single-element list whose element is the current ``fake_now``.
    Tests mutate ``frozen_clock[0]`` (or ``frozen_clock[0] = ...``) to advance
    the clock; ``utc_now`` reads it on every call so the cache sees a fresh
    timestamp and ``age > ttl`` paths actually fire.
    """
    from session_buddy.mcp.tools.infrastructure import history_cache

    state: list[datetime] = [datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)]
    monkeypatch.setattr(history_cache, "utc_now", lambda: state[0])
    yield state


# ---------------------------------------------------------------------------
# HistoryAnalysisCache
# ---------------------------------------------------------------------------


def test_ttl_hash_returns_iso_format_utc_now(
    frozen_clock: list[datetime],
) -> None:
    """``_ttl_hash`` is a private helper that snapshots ``utc_now`` as ISO."""
    from session_buddy.mcp.tools.infrastructure import history_cache

    assert history_cache._ttl_hash() == "2026-07-27T12:00:00+00:00"

    # Move the clock forward and confirm the helper picks up the new value.
    frozen_clock[0] = datetime(2026, 7, 28, 1, 2, 3, tzinfo=UTC)
    assert history_cache._ttl_hash() == "2026-07-28T01:02:03+00:00"


def test_init_uses_default_ttl_when_unspecified() -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache()

    assert cache._ttl == 300.0
    assert cache._cache == {}


def test_init_records_creation_timestamp(frozen_clock: list[datetime]) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)

    assert cache._created_at == frozen_clock[0]


def test_get_returns_default_when_key_missing() -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)

    assert cache.get("missing") is None
    assert cache.get("missing", default="fallback") == "fallback"


def test_get_returns_stored_value_when_fresh(
    frozen_clock: list[datetime],
) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("key", {"value": 1})

    # Advance by 1s, well within the 10s TTL.
    frozen_clock[0] = frozen_clock[0] + timedelta(seconds=1)

    assert cache.get("key") == {"value": 1}
    # Default is not consulted when value is present.
    assert cache.get("key", default="ignored") == {"value": 1}


def test_get_returns_default_and_evicts_when_expired(
    frozen_clock: list[datetime],
) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("key", "stale")

    # Advance past the TTL.
    frozen_clock[0] = frozen_clock[0] + timedelta(seconds=11)

    assert cache.get("key", default="expired") == "expired"
    # Expired entry is evicted, not retained.
    assert "key" not in cache._cache


def test_get_evicts_at_exact_ttl_boundary(
    frozen_clock: list[datetime],
) -> None:
    """``age > ttl`` is strict, so ttl == age still serves the value."""
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("key", "boundary")

    frozen_clock[0] = frozen_clock[0] + timedelta(seconds=10)

    assert cache.get("key") == "boundary"


def test_set_stores_value_with_timestamp(frozen_clock: list[datetime]) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("key", {"answer": 42})

    assert cache._cache["key"] == ({"answer": 42}, frozen_clock[0])


def test_set_overwrites_existing_value(frozen_clock: list[datetime]) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("key", "first")
    frozen_clock[0] = frozen_clock[0] + timedelta(seconds=1)
    cache.set("key", "second")

    assert cache.get("key") == "second"
    # Only one entry remains under that key.
    assert list(cache._cache.keys()) == ["key"]


def test_clear_empties_the_cache(frozen_clock: list[datetime]) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("a", 1)
    cache.set("b", 2)

    cache.clear()

    assert cache._cache == {}
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_is_expired_returns_true_for_missing_key() -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)

    assert cache.is_expired("not-there") is True


def test_is_expired_returns_false_when_fresh(
    frozen_clock: list[datetime],
) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("key", "v")

    frozen_clock[0] = frozen_clock[0] + timedelta(seconds=5)

    assert cache.is_expired("key") is False


def test_is_expired_returns_true_after_ttl(
    frozen_clock: list[datetime],
) -> None:
    from session_buddy.mcp.tools.infrastructure.history_cache import (
        HistoryAnalysisCache,
    )

    cache = HistoryAnalysisCache(ttl=10.0)
    cache.set("key", "v")

    frozen_clock[0] = frozen_clock[0] + timedelta(seconds=11)

    assert cache.is_expired("key") is True


# ---------------------------------------------------------------------------
# get_cache / reset_cache (module-level state)
# ---------------------------------------------------------------------------


def test_get_cache_creates_singleton_on_first_call() -> None:
    from session_buddy.mcp.tools.infrastructure import history_cache

    history_cache.reset_cache()

    first = history_cache.get_cache(ttl=12.5)

    assert isinstance(first, history_cache.HistoryAnalysisCache)
    # ttl from the *first* call is preserved on subsequent calls.
    assert first._ttl == 12.5


def test_get_cache_returns_same_instance_across_calls() -> None:
    from session_buddy.mcp.tools.infrastructure import history_cache

    history_cache.reset_cache()

    first = history_cache.get_cache(ttl=1.0)
    second = history_cache.get_cache(ttl=99.0)

    assert first is second
    # ttl is sticky from the first construction; subsequent ttl is ignored.
    assert first._ttl == 1.0


def test_get_cache_uses_default_ttl_when_unspecified() -> None:
    from session_buddy.mcp.tools.infrastructure import history_cache

    history_cache.reset_cache()

    cache = history_cache.get_cache()

    assert cache._ttl == 300.0


def test_reset_cache_clears_entries_and_drops_singleton() -> None:
    from session_buddy.mcp.tools.infrastructure import history_cache

    history_cache.reset_cache()
    cache = history_cache.get_cache(ttl=5.0)
    cache.set("key", "value")

    history_cache.reset_cache()

    assert cache.get("key") is None
    fresh = history_cache.get_cache(ttl=5.0)
    assert fresh is not cache


def test_reset_cache_is_safe_when_no_instance_exists() -> None:
    """Calling reset_cache with no prior get_cache is a no-op."""
    from session_buddy.mcp.tools.infrastructure import history_cache

    history_cache.reset_cache()  # warm-up; creates and clears.

    # Second call with cleared global state must not raise.
    history_cache.reset_cache()

    assert history_cache._global_cache is None
