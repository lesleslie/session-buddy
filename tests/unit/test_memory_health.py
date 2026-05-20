from __future__ import annotations

import sys
import types
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

_DUCKDB_STUB = types.ModuleType("duckdb")
_DUCKDB_STUB.connect = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
sys.modules.setdefault("duckdb", _DUCKDB_STUB)

_MEMORY_HEALTH_PATH = (
    Path(__file__).resolve().parents[2] / "session_buddy" / "core" / "memory_health.py"
)
_MEMORY_HEALTH_SPEC = spec_from_file_location(
    "session_buddy.core.memory_health",
    _MEMORY_HEALTH_PATH,
)
assert _MEMORY_HEALTH_SPEC is not None and _MEMORY_HEALTH_SPEC.loader is not None
_memory_health = module_from_spec(_MEMORY_HEALTH_SPEC)
sys.modules[_MEMORY_HEALTH_SPEC.name] = _memory_health
_MEMORY_HEALTH_SPEC.loader.exec_module(_memory_health)

ErrorHotSpotMetrics = _memory_health.ErrorHotSpotMetrics
MemoryHealthAnalyzer = _memory_health.MemoryHealthAnalyzer
ReflectionHealthMetrics = _memory_health.ReflectionHealthMetrics


class _FakeCursor:
    def __init__(self, one=None, many=None) -> None:
        self._one = one
        self._many = many or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _FakeConn:
    def __init__(self, cursors: list[_FakeCursor]) -> None:
        self._cursors = cursors
        self.executed: list[tuple[str, object | None]] = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self._cursors.pop(0)

    def close(self):
        self.closed = True


def test_reflection_and_error_metrics_to_dict() -> None:
    last = datetime(2024, 1, 2, 12, 30, tzinfo=UTC)
    first = datetime(2024, 1, 1, 8, 15, tzinfo=UTC)
    reflection = ReflectionHealthMetrics(
        total_reflections=3,
        stale_reflections=1,
        stale_threshold_days=30,
        avg_reflection_age_days=12.345,
        tags_distribution={"alpha": 2},
        storage_size_bytes=5 * 1024 * 1024,
        last_reflection_timestamp=last,
        first_reflection_timestamp=first,
    )
    error = ErrorHotSpotMetrics(
        total_errors=2,
        most_common_error_types=[("ValueError", 2)],
        avg_resolution_time_minutes=42.123,
        fastest_resolution_minutes=12.5,
        slowest_resolution_minutes=88.0,
        unresolved_errors=1,
        recent_error_rate=0.75,
    )

    assert reflection.to_dict() == {
        "total_reflections": 3,
        "stale_reflections": 1,
        "stale_threshold_days": 30,
        "avg_reflection_age_days": 12.345,
        "tags_distribution": {"alpha": 2},
        "storage_size_mb": 5.0,
        "last_reflection_timestamp": last.isoformat(),
        "first_reflection_timestamp": first.isoformat(),
    }
    assert error.to_dict() == {
        "total_errors": 2,
        "most_common_error_types": [{"error_type": "ValueError", "count": 2}],
        "avg_resolution_time_minutes": 42.12,
        "fastest_resolution_minutes": 12.5,
        "slowest_resolution_minutes": 88.0,
        "unresolved_errors": 1,
        "recent_error_rate": 0.75,
    }

    empty_reflection = ReflectionHealthMetrics(
        total_reflections=0,
        stale_reflections=0,
        stale_threshold_days=90,
        avg_reflection_age_days=0.0,
        tags_distribution={},
        storage_size_bytes=0,
        last_reflection_timestamp=None,
        first_reflection_timestamp=None,
    )
    empty_error = ErrorHotSpotMetrics(
        total_errors=0,
        most_common_error_types=[],
        avg_resolution_time_minutes=0.0,
        fastest_resolution_minutes=None,
        slowest_resolution_minutes=None,
        unresolved_errors=0,
        recent_error_rate=0.0,
    )

    assert empty_reflection.to_dict()["last_reflection_timestamp"] is None
    assert empty_reflection.to_dict()["first_reflection_timestamp"] is None
    assert empty_error.to_dict()["fastest_resolution_minutes"] is None
    assert empty_error.to_dict()["slowest_resolution_minutes"] is None


@pytest.mark.asyncio
async def test_get_reflection_health_no_tables() -> None:
    conn = _FakeConn([_FakeCursor(one=None)])
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    analyzer._conn = conn

    metrics = await analyzer.get_reflection_health()

    assert metrics.total_reflections == 0
    assert metrics.tags_distribution == {}
    assert metrics.last_reflection_timestamp is None


@pytest.mark.asyncio
async def test_get_reflection_health_empty_table() -> None:
    conn = _FakeConn([_FakeCursor(one=("reflections",)), _FakeCursor(one=(0,))])
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    analyzer._conn = conn

    metrics = await analyzer.get_reflection_health()

    assert metrics.total_reflections == 0
    assert metrics.stale_reflections == 0
    assert metrics.tags_distribution == {}


@pytest.mark.asyncio
async def test_get_reflection_health_with_rows() -> None:
    first = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    last = datetime(2024, 1, 3, 9, 30, tzinfo=UTC)
    conn = _FakeConn(
        [
            _FakeCursor(one=("reflections",)),
            _FakeCursor(one=(4,)),
            _FakeCursor(one=(first, last)),
            _FakeCursor(one=(2,)),
            _FakeCursor(one=(2.5,)),
            _FakeCursor(many=[("alpha", 3), ("beta", 1)]),
            _FakeCursor(one=(8 * 1024 * 1024,)),
        ]
    )
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    analyzer._conn = conn

    with patch("session_buddy.core.memory_health.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 1, 10, tzinfo=UTC)
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        mock_datetime.UTC = UTC
        mock_datetime.timedelta = timedelta

        metrics = await analyzer.get_reflection_health(stale_threshold_days=7)

    assert metrics.total_reflections == 4
    assert metrics.stale_reflections == 2
    assert metrics.avg_reflection_age_days == 2.5
    assert metrics.tags_distribution == {"alpha": 3, "beta": 1}
    assert metrics.storage_size_bytes == 8 * 1024 * 1024
    assert metrics.first_reflection_timestamp == first
    assert metrics.last_reflection_timestamp == last


@pytest.mark.asyncio
async def test_get_error_hotspots_branches() -> None:
    conn = _FakeConn([_FakeCursor(one=None)])
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    analyzer._conn = conn

    metrics = await analyzer.get_error_hotspots()
    assert metrics.total_errors == 0
    assert metrics.most_common_error_types == []


@pytest.mark.asyncio
async def test_get_error_hotspots_empty_table() -> None:
    conn = _FakeConn([_FakeCursor(one=("causal_error_events",)), _FakeCursor(one=(0,))])
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    analyzer._conn = conn

    metrics = await analyzer.get_error_hotspots()

    assert metrics.total_errors == 0
    assert metrics.most_common_error_types == []

    conn = _FakeConn(
        [
            _FakeCursor(one=("causal_error_events",)),
            _FakeCursor(one=(5,)),
            _FakeCursor(many=[("TypeError", 3), ("ValueError", 1)]),
            _FakeCursor(one=(1.0, 8.0, 4.5)),
            _FakeCursor(one=(2,)),
            _FakeCursor(one=(4,)),
        ]
    )
    analyzer._conn = conn

    with patch("session_buddy.core.memory_health.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 1, 31, tzinfo=UTC)
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        mock_datetime.UTC = UTC
        mock_datetime.timedelta = timedelta

        metrics = await analyzer.get_error_hotspots()

    assert metrics.total_errors == 5
    assert metrics.most_common_error_types == [("TypeError", 3), ("ValueError", 1)]
    assert metrics.avg_resolution_time_minutes == 4.5
    assert metrics.fastest_resolution_minutes == 1.0
    assert metrics.slowest_resolution_minutes == 8.0
    assert metrics.unresolved_errors == 2
    assert metrics.recent_error_rate == pytest.approx(4 / 30.0)


@pytest.mark.asyncio
async def test_get_cleanup_recommendations_and_close() -> None:
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    reflection = ReflectionHealthMetrics(
        total_reflections=10,
        stale_reflections=4,
        stale_threshold_days=30,
        avg_reflection_age_days=9.0,
        tags_distribution={},
        storage_size_bytes=600 * 1024 * 1024,
        last_reflection_timestamp=None,
        first_reflection_timestamp=None,
    )
    hotspots = ErrorHotSpotMetrics(
        total_errors=12,
        most_common_error_types=[("RuntimeError", 5)],
        avg_resolution_time_minutes=2.0,
        fastest_resolution_minutes=1.0,
        slowest_resolution_minutes=10.0,
        unresolved_errors=7,
        recent_error_rate=3.2,
    )
    analyzer.get_reflection_health = AsyncMock(return_value=reflection)  # type: ignore[method-assign]
    analyzer.get_error_hotspots = AsyncMock(return_value=hotspots)  # type: ignore[method-assign]

    recommendations = await analyzer.get_cleanup_recommendations()

    assert [item["action"] for item in recommendations] == [
        "clean_stale_reflections",
        "optimize_storage",
        "investigate_error_pattern",
        "review_unresolved_errors",
        "address_recurring_error",
    ]
    assert recommendations[0]["priority"] == "high"
    assert recommendations[1]["priority"] == "medium"
    assert recommendations[2]["priority"] == "high"
    assert recommendations[3]["priority"] == "medium"
    assert recommendations[4]["priority"] == "high"

    conn = _FakeConn([])
    analyzer._conn = conn
    analyzer.close()
    assert conn.closed is True
    assert analyzer._conn is None


@pytest.mark.asyncio
async def test_initialize_and_lazy_connection_and_close_without_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConn([])
    connect_mock = Mock(return_value=fake_conn)
    monkeypatch.setattr(_memory_health.duckdb, "connect", connect_mock)

    analyzer = MemoryHealthAnalyzer(db_path="/tmp/memory-health", logger=Mock())

    assert analyzer._conn is None
    assert analyzer._get_conn() is fake_conn
    await analyzer.initialize()
    analyzer.logger.info.assert_called_once()
    connect_mock.assert_called_once_with("/tmp/memory-health/reflections.db")

    analyzer.close()
    assert fake_conn.closed is True
    assert analyzer._conn is None

    analyzer.close()
    assert analyzer._conn is None


def test_get_memory_health_analyzer_uses_dependency_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_di = types.ModuleType("session_buddy.di")
    injected = MemoryHealthAnalyzer(logger=Mock())
    fake_di.depends = SimpleNamespace(get_sync=Mock(return_value=None))
    monkeypatch.setitem(sys.modules, "session_buddy.di", fake_di)

    assert _memory_health.get_memory_health_analyzer() is not None
    assert isinstance(_memory_health.get_memory_health_analyzer(), MemoryHealthAnalyzer)

    fake_di.depends.get_sync.return_value = injected
    assert _memory_health.get_memory_health_analyzer() is injected


@pytest.mark.asyncio
async def test_get_cleanup_recommendations_with_no_actions() -> None:
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    analyzer.get_reflection_health = AsyncMock(
        return_value=ReflectionHealthMetrics(
            total_reflections=0,
            stale_reflections=0,
            stale_threshold_days=30,
            avg_reflection_age_days=0.0,
            tags_distribution={},
            storage_size_bytes=0,
            last_reflection_timestamp=None,
            first_reflection_timestamp=None,
        )
    )  # type: ignore[method-assign]
    analyzer.get_error_hotspots = AsyncMock(
        return_value=ErrorHotSpotMetrics(
            total_errors=0,
            most_common_error_types=[],
            avg_resolution_time_minutes=0.0,
            fastest_resolution_minutes=None,
            slowest_resolution_minutes=None,
            unresolved_errors=0,
            recent_error_rate=0.0,
        )
    )  # type: ignore[method-assign]

    assert await analyzer.get_cleanup_recommendations() == []


@pytest.mark.asyncio
async def test_get_cleanup_recommendations_skips_non_recurring_error_type() -> None:
    analyzer = MemoryHealthAnalyzer(logger=Mock())
    analyzer.get_reflection_health = AsyncMock(
        return_value=ReflectionHealthMetrics(
            total_reflections=2,
            stale_reflections=0,
            stale_threshold_days=30,
            avg_reflection_age_days=0.0,
            tags_distribution={},
            storage_size_bytes=0,
            last_reflection_timestamp=None,
            first_reflection_timestamp=None,
        )
    )  # type: ignore[method-assign]
    analyzer.get_error_hotspots = AsyncMock(
        return_value=ErrorHotSpotMetrics(
            total_errors=2,
            most_common_error_types=[("RuntimeError", 2)],
            avg_resolution_time_minutes=0.0,
            fastest_resolution_minutes=None,
            slowest_resolution_minutes=None,
            unresolved_errors=0,
            recent_error_rate=0.0,
        )
    )  # type: ignore[method-assign]

    assert await analyzer.get_cleanup_recommendations() == []
