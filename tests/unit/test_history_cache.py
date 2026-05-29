from __future__ import annotations

from datetime import datetime, timedelta

import pytest


def test_ttl_hash_returns_iso_string(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_buddy.mcp.tools.infrastructure import history_cache

    class FakeDateTime(datetime):
        @classmethod
        def now(cls) -> datetime:
            return datetime(2026, 1, 2, 3, 4, 5)

    monkeypatch.setattr(history_cache, "datetime", FakeDateTime)

    assert history_cache._ttl_hash() == "2026-01-02T03:04:05"


def test_cache_hit_miss_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_buddy.mcp.tools.infrastructure import history_cache

    class FakeDateTime(datetime):
        current = datetime(2026, 1, 2, 3, 4, 5)

        @classmethod
        def now(cls) -> datetime:
            return cls.current

    monkeypatch.setattr(history_cache, "datetime", FakeDateTime)

    cache = history_cache.HistoryAnalysisCache(ttl=10.0)
    assert cache.get("missing", default="fallback") == "fallback"
    assert cache.is_expired("missing") is True

    cache.set("key", {"value": 1})
    assert cache.get("key") == {"value": 1}
    assert cache.is_expired("key") is False

    FakeDateTime.current = FakeDateTime.current + timedelta(seconds=11)

    assert cache.get("key", default="expired") == "expired"
    assert cache.is_expired("key") is True


def test_clear_and_global_cache_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_buddy.mcp.tools.infrastructure import history_cache

    history_cache.reset_cache()

    first = history_cache.get_cache(ttl=1.0)
    second = history_cache.get_cache(ttl=5.0)

    assert first is second
    assert first._ttl == 1.0

    first.set("key", "value")
    assert first.get("key") == "value"

    history_cache.reset_cache()

    assert first.get("key", default=None) is None
    fresh = history_cache.get_cache(ttl=2.0)
    assert fresh is not first
    assert fresh._ttl == 2.0

    fresh.set("another", 123)
    fresh.clear()
    assert fresh.get("another", default=None) is None
