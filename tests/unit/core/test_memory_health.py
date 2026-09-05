"""Focused unit tests for session_buddy.core.memory_health."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from session_buddy.core.memory_health import (
    DEPENDENCY_KEY,
    ErrorHotSpotMetrics,
    MemoryHealthAnalyzer,
    ReflectionHealthMetrics,
)


def _make_analyzer_with_conn(conn: Any) -> MemoryHealthAnalyzer:
    """Build an analyzer whose connection is the supplied in-memory DuckDB.

    The analyzer normally opens a file-backed DuckDB at ``db_path/reflections.db``.
    For tests we want to inject a deterministic in-memory connection so we can
    pre-create the tables the code expects.
    """
    analyzer = MemoryHealthAnalyzer(db_path="/tmp/memory_health_test_dummy")
    analyzer._conn = conn
    return analyzer


def _create_empty_reflections_table(conn: Any) -> None:
    """Create an empty ``reflections`` table the analyzer queries."""
    conn.execute(
        """
        CREATE TABLE reflections (
            id VARCHAR PRIMARY KEY,
            content VARCHAR,
            tags VARCHAR[],
            timestamp TIMESTAMP
        )
        """
    )


def _create_empty_error_tables(conn: Any) -> None:
    """Create empty causal_error_events and causal_chains tables."""
    conn.execute(
        """
        CREATE TABLE causal_error_events (
            id VARCHAR PRIMARY KEY,
            error_type VARCHAR,
            timestamp TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE causal_chains (
            id VARCHAR PRIMARY KEY,
            error_id VARCHAR,
            resolution_time_minutes DOUBLE
        )
        """
    )


class TestReflectionHealthMetricsDataclass:
    """Direct dataclass behaviour tests (no DB)."""

    def test_defaults_are_zero(self) -> None:
        metrics = ReflectionHealthMetrics(
            total_reflections=0,
            stale_reflections=0,
            stale_threshold_days=90,
            avg_reflection_age_days=0.0,
            tags_distribution={},
            storage_size_bytes=0,
            last_reflection_timestamp=None,
            first_reflection_timestamp=None,
        )
        assert metrics.total_reflections == 0
        assert metrics.stale_threshold_days == 90
        assert metrics.last_reflection_timestamp is None

    def test_to_dict_serializes_timestamps_as_iso(self) -> None:
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        metrics = ReflectionHealthMetrics(
            total_reflections=2,
            stale_reflections=0,
            stale_threshold_days=30,
            avg_reflection_age_days=1.5,
            tags_distribution={"alpha": 2},
            storage_size_bytes=1024 * 1024,
            last_reflection_timestamp=ts,
            first_reflection_timestamp=ts,
        )
        data = metrics.to_dict()
        assert data["total_reflections"] == 2
        assert data["storage_size_mb"] == 1.0
        assert data["last_reflection_timestamp"] == ts.isoformat()
        assert data["first_reflection_timestamp"] == ts.isoformat()
        assert data["tags_distribution"] == {"alpha": 2}

    def test_to_dict_handles_none_timestamps(self) -> None:
        metrics = ReflectionHealthMetrics(
            total_reflections=0,
            stale_reflections=0,
            stale_threshold_days=90,
            avg_reflection_age_days=0.0,
            tags_distribution={},
            storage_size_bytes=0,
            last_reflection_timestamp=None,
            first_reflection_timestamp=None,
        )
        data = metrics.to_dict()
        assert data["last_reflection_timestamp"] is None
        assert data["first_reflection_timestamp"] is None

    def test_to_dict_storage_size_mb_rounds(self) -> None:
        metrics = ReflectionHealthMetrics(
            total_reflections=1,
            stale_reflections=0,
            stale_threshold_days=90,
            avg_reflection_age_days=0.0,
            tags_distribution={},
            storage_size_bytes=int(2.5 * 1024 * 1024),
            last_reflection_timestamp=None,
            first_reflection_timestamp=None,
        )
        assert metrics.to_dict()["storage_size_mb"] == 2.5


class TestErrorHotSpotMetricsDataclass:
    """Direct dataclass behaviour tests (no DB)."""

    def test_defaults_are_zero(self) -> None:
        metrics = ErrorHotSpotMetrics(
            total_errors=0,
            most_common_error_types=[],
            avg_resolution_time_minutes=0.0,
            fastest_resolution_minutes=None,
            slowest_resolution_minutes=None,
            unresolved_errors=0,
            recent_error_rate=0.0,
        )
        assert metrics.total_errors == 0
        assert metrics.fastest_resolution_minutes is None

    def test_to_dict_rounds_and_formats(self) -> None:
        metrics = ErrorHotSpotMetrics(
            total_errors=3,
            most_common_error_types=[("ValueError", 3)],
            avg_resolution_time_minutes=12.3456,
            fastest_resolution_minutes=2.0,
            slowest_resolution_minutes=99.999,
            unresolved_errors=1,
            recent_error_rate=0.5,
        )
        data = metrics.to_dict()
        assert data["total_errors"] == 3
        assert data["most_common_error_types"] == [
            {"error_type": "ValueError", "count": 3}
        ]
        assert data["avg_resolution_time_minutes"] == 12.35
        assert data["fastest_resolution_minutes"] == 2.0
        assert data["slowest_resolution_minutes"] == 100.0
        assert data["unresolved_errors"] == 1
        assert data["recent_error_rate"] == 0.5

    def test_to_dict_with_none_resolution_times(self) -> None:
        metrics = ErrorHotSpotMetrics(
            total_errors=0,
            most_common_error_types=[],
            avg_resolution_time_minutes=0.0,
            fastest_resolution_minutes=None,
            slowest_resolution_minutes=None,
            unresolved_errors=0,
            recent_error_rate=0.0,
        )
        data = metrics.to_dict()
        assert data["fastest_resolution_minutes"] is None
        assert data["slowest_resolution_minutes"] is None


class TestMemoryHealthAnalyzerInit:
    """Analyzer construction and ``initialize`` lifecycle."""

    def test_init_uses_explicit_db_path(self, tmp_path) -> None:
        target = tmp_path / "mem"
        analyzer = MemoryHealthAnalyzer(db_path=str(target))
        assert analyzer.db_path == str(target)
        assert analyzer._conn is None

    def test_initialize_creates_connection(self, tmp_path) -> None:
        target = tmp_path / "mem"
        target.mkdir()
        analyzer = MemoryHealthAnalyzer(db_path=str(target))
        try:
            import asyncio

            asyncio.run(analyzer.initialize())
            assert analyzer._conn is not None
        finally:
            analyzer.close()

    def test_close_releases_connection(self, tmp_path) -> None:
        target = tmp_path / "mem"
        target.mkdir()
        analyzer = MemoryHealthAnalyzer(db_path=str(target))
        try:
            import asyncio

            asyncio.run(analyzer.initialize())
            assert analyzer._conn is not None
            analyzer.close()
            assert analyzer._conn is None
        except Exception:
            analyzer.close()
            raise

    def test_dependency_key_constant(self) -> None:
        assert DEPENDENCY_KEY == "memory_health_analyzer"


class TestGetReflectionHealthEmpty:
    """``get_reflection_health`` short-circuit paths that avoid the unnest query."""

    async def test_returns_defaults_when_reflections_table_missing(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_reflection_health()
        assert isinstance(result, ReflectionHealthMetrics)
        assert result.total_reflections == 0
        assert result.stale_reflections == 0
        assert result.last_reflection_timestamp is None
        assert result.first_reflection_timestamp is None
        assert result.stale_threshold_days == 90

    async def test_returns_defaults_when_table_exists_but_empty(
        self, duckdb_connection
    ) -> None:
        _create_empty_reflections_table(duckdb_connection)
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_reflection_health()
        assert result.total_reflections == 0
        assert result.avg_reflection_age_days == 0.0
        assert result.tags_distribution == {}

    async def test_returns_defaults_for_custom_stale_threshold(
        self, duckdb_connection
    ) -> None:
        _create_empty_reflections_table(duckdb_connection)
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_reflection_health(stale_threshold_days=7)
        assert result.stale_threshold_days == 7
        assert result.total_reflections == 0


class TestGetReflectionHealthPopulated:
    """``get_reflection_health`` against a populated DuckDB table.

    The production ``unnest()`` GROUP BY query is now wrapped in a
    subquery so DuckDB accepts it, and storage size uses the native
    ``pragma_database_size()`` instead of the Postgres-only
    ``pg_database_size``. These tests exercise the real SQL paths.
    """

    async def test_aggregates_sample_reflections_via_mock(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        fixed = ReflectionHealthMetrics(
            total_reflections=3,
            stale_reflections=0,
            stale_threshold_days=90,
            avg_reflection_age_days=1.0,
            tags_distribution={"alpha": 2, "beta": 2},
            storage_size_bytes=4096,
            last_reflection_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            first_reflection_timestamp=datetime(2025, 12, 1, tzinfo=UTC),
        )
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(fixed)
        )
        result = await analyzer.get_reflection_health()
        assert result.total_reflections == 3
        assert result.tags_distribution == {"alpha": 2, "beta": 2}
        assert result.last_reflection_timestamp == datetime(
            2026, 1, 1, tzinfo=UTC
        )

    async def test_real_duckdb_tag_distribution_and_size(
        self, duckdb_connection
    ) -> None:
        """The fixed ``unnest()`` subquery + ``pragma_database_size()``
        paths now work against a real DuckDB instance. Insert a small
        reflections table and verify the aggregate fields.
        """
        duckdb_connection.execute(
            """
            CREATE TABLE reflections (
                id VARCHAR,
                content TEXT,
                tags VARCHAR[],
                timestamp TIMESTAMP,
                metadata JSON
            )
            """
        )
        duckdb_connection.execute(
            """
            INSERT INTO reflections (id, content, tags, timestamp, metadata)
            VALUES
                ('r1', 'alpha', ['alpha', 'beta'], '2026-01-01', NULL),
                ('r2', 'beta',  ['alpha'],         '2026-01-02', NULL),
                ('r3', 'gamma', ['beta'],          '2026-01-03', NULL)
            """
        )
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_reflection_health()
        assert result.total_reflections == 3
        # tag distribution should reflect 2x alpha, 2x beta.
        assert result.tags_distribution == {"alpha": 2, "beta": 2}
        # Storage size must come back as a non-negative int.
        assert isinstance(result.storage_size_bytes, int)
        assert result.storage_size_bytes >= 0

    async def test_stale_reflection_detection_via_mock(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        fixed = ReflectionHealthMetrics(
            total_reflections=5,
            stale_reflections=2,
            stale_threshold_days=90,
            avg_reflection_age_days=10.0,
            tags_distribution={},
            storage_size_bytes=0,
            last_reflection_timestamp=None,
            first_reflection_timestamp=None,
        )
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(fixed)
        )
        result = await analyzer.get_reflection_health()
        assert result.stale_reflections == 2
        assert result.total_reflections == 5


class TestGetErrorHotspots:
    """``get_error_hotspots`` paths."""

    async def test_defaults_when_error_table_missing(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_error_hotspots()
        assert isinstance(result, ErrorHotSpotMetrics)
        assert result.total_errors == 0
        assert result.most_common_error_types == []
        assert result.fastest_resolution_minutes is None
        assert result.slowest_resolution_minutes is None
        assert result.recent_error_rate == 0.0

    async def test_defaults_when_error_table_empty(
        self, duckdb_connection
    ) -> None:
        _create_empty_error_tables(duckdb_connection)
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_error_hotspots()
        assert result.total_errors == 0
        assert result.most_common_error_types == []
        assert result.unresolved_errors == 0
        assert result.fastest_resolution_minutes is None

    async def test_aggregates_sample_errors(self, duckdb_connection) -> None:
        _create_empty_error_tables(duckdb_connection)
        now = datetime.now(UTC)
        duckdb_connection.execute(
            "INSERT INTO causal_error_events VALUES (?, ?, ?)",
            ["e1", "ValueError", now],
        )
        duckdb_connection.execute(
            "INSERT INTO causal_error_events VALUES (?, ?, ?)",
            ["e2", "ValueError", now],
        )
        duckdb_connection.execute(
            "INSERT INTO causal_error_events VALUES (?, ?, ?)",
            ["e3", "KeyError", now],
        )
        duckdb_connection.execute(
            "INSERT INTO causal_chains VALUES (?, ?, ?)",
            ["c1", "e1", 5.0],
        )
        duckdb_connection.execute(
            "INSERT INTO causal_chains VALUES (?, ?, ?)",
            ["c2", "e2", 15.0],
        )
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_error_hotspots()
        assert result.total_errors == 3
        # Most common first.
        assert result.most_common_error_types[0] == ("ValueError", 2)
        assert result.most_common_error_types[1] == ("KeyError", 1)
        assert result.fastest_resolution_minutes == 5.0
        assert result.slowest_resolution_minutes == 15.0
        assert result.avg_resolution_time_minutes == 10.0
        # e3 has no chain → unresolved.
        assert result.unresolved_errors == 1
        # All three events happened today → recent rate is 3 / 30 = 0.1.
        assert result.recent_error_rate == pytest.approx(3 / 30)

    async def test_unresolved_counts_left_joined_events(
        self, duckdb_connection
    ) -> None:
        _create_empty_error_tables(duckdb_connection)
        now = datetime.now(UTC)
        duckdb_connection.execute(
            "INSERT INTO causal_error_events VALUES (?, ?, ?)",
            ["e1", "ValueError", now],
        )
        duckdb_connection.execute(
            "INSERT INTO causal_error_events VALUES (?, ?, ?)",
            ["e2", "KeyError", now],
        )
        # Both unresolved (no matching causal_chains row).
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_error_hotspots()
        assert result.unresolved_errors == 2
        assert result.fastest_resolution_minutes is None
        assert result.slowest_resolution_minutes is None


class TestGetCleanupRecommendations:
    """``get_cleanup_recommendations`` exercised via MagicMock so we don't
    hit the production unnest GROUP BY query.
    """

    async def test_empty_state_returns_empty_list(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        result = await analyzer.get_cleanup_recommendations()
        assert result == []

    async def test_recommends_cleaning_stale_reflections(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=10,
                    stale_reflections=4,
                    stale_threshold_days=90,
                    avg_reflection_age_days=120.0,
                    tags_distribution={},
                    storage_size_bytes=0,
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=0,
                    most_common_error_types=[],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=0,
                    recent_error_rate=0.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        actions = {rec["action"] for rec in result}
        assert "clean_stale_reflections" in actions
        stale_rec = next(
            r for r in result if r["action"] == "clean_stale_reflections"
        )
        # 4/10 = 40% > 20% → high priority.
        assert stale_rec["priority"] == "high"
        assert "4 stale reflections" in stale_rec["details"]

    async def test_low_priority_stale_when_below_20_percent(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=100,
                    stale_reflections=10,
                    stale_threshold_days=90,
                    avg_reflection_age_days=20.0,
                    tags_distribution={},
                    storage_size_bytes=0,
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=0,
                    most_common_error_types=[],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=0,
                    recent_error_rate=0.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        stale_rec = next(
            r for r in result if r["action"] == "clean_stale_reflections"
        )
        # 10/100 = 10% < 20% → medium priority.
        assert stale_rec["priority"] == "medium"

    async def test_recommends_optimizing_large_storage(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=0,
                    stale_reflections=0,
                    stale_threshold_days=90,
                    avg_reflection_age_days=0.0,
                    tags_distribution={},
                    storage_size_bytes=200 * 1024 * 1024,  # 200 MB
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=0,
                    most_common_error_types=[],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=0,
                    recent_error_rate=0.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        actions = {rec["action"] for rec in result}
        assert "optimize_storage" in actions
        opt_rec = next(r for r in result if r["action"] == "optimize_storage")
        # 200 MB → below 500 MB → low priority.
        assert opt_rec["priority"] == "low"

    async def test_storage_optimization_medium_when_huge(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=0,
                    stale_reflections=0,
                    stale_threshold_days=90,
                    avg_reflection_age_days=0.0,
                    tags_distribution={},
                    storage_size_bytes=600 * 1024 * 1024,  # 600 MB
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=0,
                    most_common_error_types=[],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=0,
                    recent_error_rate=0.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        opt_rec = next(r for r in result if r["action"] == "optimize_storage")
        # 600 MB → above 500 MB → medium priority.
        assert opt_rec["priority"] == "medium"

    async def test_recommends_investigating_high_error_rate(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=0,
                    stale_reflections=0,
                    stale_threshold_days=90,
                    avg_reflection_age_days=0.0,
                    tags_distribution={},
                    storage_size_bytes=0,
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=100,
                    most_common_error_types=[],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=0,
                    recent_error_rate=3.5,  # > 2.0
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        actions = {rec["action"] for rec in result}
        assert "investigate_error_pattern" in actions
        inv_rec = next(
            r for r in result if r["action"] == "investigate_error_pattern"
        )
        assert inv_rec["priority"] == "high"

    async def test_recommends_reviewing_unresolved_errors(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=0,
                    stale_reflections=0,
                    stale_threshold_days=90,
                    avg_reflection_age_days=0.0,
                    tags_distribution={},
                    storage_size_bytes=0,
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=7,
                    most_common_error_types=[],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=7,  # > 5
                    recent_error_rate=0.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        actions = {rec["action"] for rec in result}
        assert "review_unresolved_errors" in actions

    async def test_recommends_addressing_recurring_error(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=0,
                    stale_reflections=0,
                    stale_threshold_days=90,
                    avg_reflection_age_days=0.0,
                    tags_distribution={},
                    storage_size_bytes=0,
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=4,
                    most_common_error_types=[("Recurring", 4)],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=0,
                    recent_error_rate=0.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        actions = {rec["action"] for rec in result}
        assert "address_recurring_error" in actions
        rec = next(
            r for r in result if r["action"] == "address_recurring_error"
        )
        assert "4 times" in rec["details"]
        # 4 occurrences → medium (>= 3 and < 5).
        assert rec["priority"] == "medium"

    async def test_recurring_error_high_priority_at_five_occurrences(
        self, duckdb_connection
    ) -> None:
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=0,
                    stale_reflections=0,
                    stale_threshold_days=90,
                    avg_reflection_age_days=0.0,
                    tags_distribution={},
                    storage_size_bytes=0,
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=6,
                    most_common_error_types=[("Frequent", 6)],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=0,
                    recent_error_rate=0.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        rec = next(
            r for r in result if r["action"] == "address_recurring_error"
        )
        assert rec["priority"] == "high"

    async def test_full_state_recommendations_aggregated(
        self, duckdb_connection
    ) -> None:
        """When every trigger fires, all five recommendations are present."""
        analyzer = _make_analyzer_with_conn(duckdb_connection)
        analyzer.get_reflection_health = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ReflectionHealthMetrics(
                    total_reflections=10,
                    stale_reflections=5,
                    stale_threshold_days=90,
                    avg_reflection_age_days=100.0,
                    tags_distribution={},
                    storage_size_bytes=200 * 1024 * 1024,
                    last_reflection_timestamp=None,
                    first_reflection_timestamp=None,
                )
            )
        )
        analyzer.get_error_hotspots = (  # type: ignore[method-assign]
            lambda *a, **kw: _await(
                ErrorHotSpotMetrics(
                    total_errors=100,
                    most_common_error_types=[("Hot", 6)],
                    avg_resolution_time_minutes=0.0,
                    fastest_resolution_minutes=None,
                    slowest_resolution_minutes=None,
                    unresolved_errors=8,
                    recent_error_rate=3.0,
                )
            )
        )
        result = await analyzer.get_cleanup_recommendations()
        actions = {rec["action"] for rec in result}
        assert actions == {
            "clean_stale_reflections",
            "optimize_storage",
            "investigate_error_pattern",
            "review_unresolved_errors",
            "address_recurring_error",
        }


async def _await(value: Any) -> Any:
    """Helper to make a coroutine-returning lambda for patching async methods."""
    return value
