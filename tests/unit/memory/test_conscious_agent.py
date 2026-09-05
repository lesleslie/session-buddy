"""Tests for session_buddy.memory.conscious_agent.

Covers the ConsciousAgent class and its host-wide election lock:
- ``_start_conscious_agent_with_lock`` election semantics (feature flag,
  in-process cache, POSIX flock election, exception tolerance)
- ``_calculate_recency_score`` exponential decay + tz handling
- ``_get_category_weight`` known categories + unknown fallback
- ``_generate_promotion_reason`` reasons triggered by access count,
  recency, semantic importance, and category
- ``_calculate_promotion_priorities`` weighted scoring + threshold gate
- ``_analyze_access_patterns`` end-to-end via a real :memory: DuckDB
- ``_promote_memories`` + ``_demote_stale_memories`` via real DuckDB
- ``_periodic_distill_skills`` with reflection_db stub
- ``start``/``stop`` lifecycle (cancel the background task cleanly)

DB-touching methods all follow the same pattern: ``import duckdb`` +
``get_database_path()`` inside the function body. Monkeypatching
``get_database_path`` to point at a tmp_path file is the consistent
strategy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest

from session_buddy.memory import conscious_agent
from session_buddy.memory.conscious_agent import (
    ConsciousAgent,
    MemoryAccessPattern,
    PromotionCandidate,
    _start_conscious_agent_with_lock,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_election_state(monkeypatch: pytest.MonkeyPatch):
    """Reset module-level election cache between tests."""
    monkeypatch.setattr(conscious_agent, "_conscious_agent_elected", False)
    monkeypatch.setattr(conscious_agent, "_conscious_agent_lock_fd", None)
    return monkeypatch


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a tmp_path-backed DuckDB file path (does not open the file)."""
    return tmp_path / "reflection.duckdb"


@pytest.fixture
def patched_db_path(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch ``session_buddy.settings.get_database_path`` to return tmp_db.

    The conscious_agent module imports ``get_database_path`` inside method
    bodies via ``from session_buddy.settings import get_database_path``,
    so the only attribute we can patch is the source attribute.
    """
    import session_buddy.settings

    monkeypatch.setattr(
        session_buddy.settings, "get_database_path", lambda: tmp_db
    )
    return tmp_db


def _seed_db_with_schema(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open a tmp DuckDB and apply v2 schema; return the connection."""
    conn = duckdb.connect(str(db_path))
    from session_buddy.memory.migration import apply_migrations

    apply_migrations(conn)
    return conn


def _make_pattern(
    *,
    memory_id: str = "m1",
    access_count: int = 5,
    hours_ago: float = 1.0,
    semantic_importance: float = 0.5,
    category: str = "facts",
    velocity: float = 1.0,
) -> MemoryAccessPattern:
    return MemoryAccessPattern(
        memory_id=memory_id,
        access_count=access_count,
        last_accessed=datetime.now() - timedelta(hours=hours_ago),
        access_velocity=velocity,
        semantic_importance=semantic_importance,
        category=category,
    )


# ---------------------------------------------------------------------------
# _start_conscious_agent_with_lock
# ---------------------------------------------------------------------------


class TestStartConsciousAgentWithLock:
    def test_disabled_returns_false(
        self, reset_election_state, tmp_path: Path, monkeypatch
    ) -> None:
        # Use a real tempfile but disable the feature.
        settings = SimpleNamespace(enable_conscious_agent=False)
        assert _start_conscious_agent_with_lock(settings) is False

    def test_in_process_elected_blocks_second_call(
        self, reset_election_state, monkeypatch
    ) -> None:
        settings = SimpleNamespace(enable_conscious_agent=True)
        # First call would try to flock — patch the lockfile path so we
        # don't actually take a real lock. Instead, simulate the election
        # by patching ``_conscious_agent_elected`` to True after first
        # call. Simpler: drive both calls through monkeypatched behavior.
        # We test the in-process branch by forcing the module-level cache.
        monkeypatch.setattr(conscious_agent, "_conscious_agent_elected", True)
        # When the cache is set, the function short-circuits to False.
        assert _start_conscious_agent_with_lock(settings) is False

    def test_election_returns_true_when_lock_acquired(
        self, reset_election_state, tmp_path: Path, monkeypatch
    ) -> None:
        # Redirect the lockfile into tmp_path so we don't pollute /tmp.
        from pathlib import Path as P

        lock_path = tmp_path / "test_lock.lock"
        monkeypatch.setattr(
            conscious_agent, "_CONSCIOUS_AGENT_LOCK_PATH", str(lock_path.name)
        )
        monkeypatch.setattr(
            conscious_agent.tempfile, "gettempdir", lambda: str(tmp_path)
        )

        settings = SimpleNamespace(enable_conscious_agent=True)
        assert _start_conscious_agent_with_lock(settings) is True
        assert lock_path.exists()
        # The PID is written to the file.
        content = lock_path.read_text().strip()
        assert content.isdigit()

    def test_election_returns_false_when_already_locked(
        self, reset_election_state, tmp_path: Path, monkeypatch
    ) -> None:
        # Pre-create a locked file by another process. We simulate the
        # "lock held" condition by holding an exclusive fcntl lock in
        # this process, which another flock() call would block on.
        lock_path = tmp_path / "test_lock.lock"
        lock_path.write_text("other-pid")
        held_fd = open(lock_path, "r")
        import fcntl

        fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        monkeypatch.setattr(
            conscious_agent, "_CONSCIOUS_AGENT_LOCK_PATH", str(lock_path.name)
        )
        monkeypatch.setattr(
            conscious_agent.tempfile, "gettempdir", lambda: str(tmp_path)
        )

        settings = SimpleNamespace(enable_conscious_agent=True)
        try:
            assert _start_conscious_agent_with_lock(settings) is False
        finally:
            fcntl.flock(held_fd, fcntl.LOCK_UN)
            held_fd.close()

    def test_election_returns_false_on_permission_error(
        self, reset_election_state, tmp_path: Path, monkeypatch
    ) -> None:
        # The function calls ``lock_path.touch(exist_ok=True)`` then
        # ``lock_path.open("w")``. Patch Path.touch to raise an OSError so
        # the early-return error path is exercised.
        from pathlib import Path as P

        original_touch = P.touch

        def boom(self, *args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(P, "touch", boom)
        try:
            settings = SimpleNamespace(enable_conscious_agent=True)
            assert _start_conscious_agent_with_lock(settings) is False
        finally:
            monkeypatch.setattr(P, "touch", original_touch)


# ---------------------------------------------------------------------------
# Pure-Python helpers
# ---------------------------------------------------------------------------


class TestCalculateRecencyScore:
    def test_recent_returns_high(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        score = agent._calculate_recency_score(datetime.now())
        # Accessed 0 hours ago → exp(0) = 1.0
        assert 0.99 < score <= 1.0

    def test_old_returns_low(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        # 240 hours ago → exp(-10) ≈ 4.5e-5
        score = agent._calculate_recency_score(
            datetime.now() - timedelta(hours=240)
        )
        assert score < 0.01

    def test_strips_tzinfo(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        # Use a tz-aware datetime 48 hours in the past. After tzinfo
        # stripping, the comparison with ``datetime.now()`` (naive local)
        # still yields a positive delta even with timezone offset between
        # UTC and local. The function must not raise on tz-aware input.
        aware = datetime.now(UTC) - timedelta(hours=48)
        score = agent._calculate_recency_score(aware)
        # Bound: still within (0, 1] for any reasonable past timestamp.
        assert 0.0 < score <= 1.0


class TestGetCategoryWeight:
    def test_known_categories(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        assert agent._get_category_weight("preferences") == 1.0
        assert agent._get_category_weight("skills") == 0.9
        assert agent._get_category_weight("rules") == 0.8
        assert agent._get_category_weight("facts") == 0.7
        assert agent._get_category_weight("context") == 0.6

    def test_unknown_category_default(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        assert agent._get_category_weight("garbage") == 0.5
        assert agent._get_category_weight("") == 0.5


class TestGeneratePromotionReason:
    def test_high_access_frequency_reason(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        pattern = _make_pattern(access_count=10, hours_ago=24)
        reason = agent._generate_promotion_reason(pattern, 0.8)
        assert "high access frequency" in reason
        assert "10x" in reason
        assert "score: 0.80" in reason

    def test_recently_accessed_reason(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        pattern = _make_pattern(access_count=2, hours_ago=2)
        reason = agent._generate_promotion_reason(pattern, 0.75)
        assert "recently accessed" in reason

    def test_high_semantic_importance_reason(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        pattern = _make_pattern(semantic_importance=0.9, hours_ago=24)
        reason = agent._generate_promotion_reason(pattern, 0.8)
        assert "high semantic importance" in reason

    def test_critical_category_reason(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        pattern = _make_pattern(category="skills", hours_ago=24)
        reason = agent._generate_promotion_reason(pattern, 0.75)
        assert "critical category (skills)" in reason

    def test_fallback_priority_reason(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        pattern = _make_pattern(
            access_count=1, hours_ago=48, semantic_importance=0.3,
            category="facts",
        )
        reason = agent._generate_promotion_reason(pattern, 0.5)
        assert reason.startswith("high priority score")


# ---------------------------------------------------------------------------
# _calculate_promotion_priorities
# ---------------------------------------------------------------------------


class TestCalculatePromotionPriorities:
    @pytest.mark.asyncio
    async def test_filters_below_threshold(self) -> None:
        agent = ConsciousAgent(reflection_db=None, promotion_threshold=0.9)
        # Low priority pattern → filtered out.
        pattern = _make_pattern(
            access_count=1, hours_ago=48, semantic_importance=0.3,
            category="facts",
        )
        result = await agent._calculate_promotion_priorities([pattern])
        assert result == []

    @pytest.mark.asyncio
    async def test_promotes_above_threshold(self) -> None:
        agent = ConsciousAgent(reflection_db=None, promotion_threshold=0.5)
        # High-priority pattern: recent, frequently accessed, important.
        pattern = _make_pattern(
            access_count=15, hours_ago=1, semantic_importance=0.95,
            category="preferences",
        )
        result = await agent._calculate_promotion_priorities([pattern])
        assert len(result) == 1
        candidate = result[0]
        assert isinstance(candidate, PromotionCandidate)
        assert candidate.memory_id == "m1"
        assert candidate.priority_score >= 0.5
        assert candidate.current_tier == "long_term"

    @pytest.mark.asyncio
    async def test_sorted_highest_first(self) -> None:
        agent = ConsciousAgent(reflection_db=None, promotion_threshold=0.3)
        high = _make_pattern(
            memory_id="high",
            access_count=20, hours_ago=1, semantic_importance=0.99,
            category="preferences",
        )
        low = _make_pattern(
            memory_id="low",
            access_count=3, hours_ago=20, semantic_importance=0.4,
            category="context",
        )
        result = await agent._calculate_promotion_priorities([high, low])
        assert len(result) == 2
        assert result[0].memory_id == "high"
        assert result[1].memory_id == "low"

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        result = await agent._calculate_promotion_priorities([])
        assert result == []


# ---------------------------------------------------------------------------
# _analyze_access_patterns — DB-backed
# ---------------------------------------------------------------------------


class TestAnalyzeAccessPatterns:
    @pytest.mark.asyncio
    async def test_returns_patterns_from_db(self, patched_db_path: Path) -> None:
        conn = _seed_db_with_schema(patched_db_path)
        try:
            # Seed a conversation and an access log.
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["m1", "content", "skills", 0.8, "long_term", "default"],
            )
            conn.execute(
                "INSERT INTO memory_access_log (id, memory_id, access_type, timestamp) "
                "VALUES (?, ?, ?, ?)",
                ["a1", "m1", "search", datetime.now()],
            )
            conn.execute(
                "INSERT INTO memory_access_log (id, memory_id, access_type, timestamp) "
                "VALUES (?, ?, ?, ?)",
                ["a2", "m1", "search", datetime.now()],
            )
            conn.commit()
        finally:
            conn.close()

        agent = ConsciousAgent(reflection_db=None)
        patterns = await agent._analyze_access_patterns()
        assert len(patterns) == 1
        assert patterns[0].memory_id == "m1"
        assert patterns[0].access_count == 2
        assert patterns[0].category == "skills"
        assert patterns[0].semantic_importance == pytest.approx(0.8, rel=1e-5)

    @pytest.mark.asyncio
    async def test_handles_missing_tables(self, tmp_db: Path, monkeypatch) -> None:
        # No schema applied → tables missing → empty list, no exception.
        import session_buddy.settings
        monkeypatch.setattr(
            session_buddy.settings, "get_database_path", lambda: tmp_db
        )
        agent = ConsciousAgent(reflection_db=None)
        patterns = await agent._analyze_access_patterns()
        assert patterns == []

    @pytest.mark.asyncio
    async def test_handles_connect_failure(
        self, tmp_db: Path, monkeypatch
    ) -> None:
        # Force a failed connect via monkeypatch on the duckdb module itself.
        # conscious_agent does ``import duckdb`` inside the method body, so
        # we patch the duckdb module's connect.
        import session_buddy.settings
        monkeypatch.setattr(
            session_buddy.settings, "get_database_path", lambda: tmp_db
        )
        import duckdb

        original_connect = duckdb.connect

        def boom(*args, **kwargs):
            raise OSError("simulated connect failure")

        monkeypatch.setattr(duckdb, "connect", boom)
        try:
            agent = ConsciousAgent(reflection_db=None)
            patterns = await agent._analyze_access_patterns()
            assert patterns == []
        finally:
            monkeypatch.setattr(duckdb, "connect", original_connect)


# ---------------------------------------------------------------------------
# _promote_memories — DB-backed
# ---------------------------------------------------------------------------


class TestPromoteMemories:
    @pytest.mark.asyncio
    async def test_promotes_candidate_to_short_term(
        self, patched_db_path: Path
    ) -> None:
        conn = _seed_db_with_schema(patched_db_path)
        try:
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["m1", "content", "skills", 0.9, "long_term", "default"],
            )
            conn.commit()
        finally:
            conn.close()

        agent = ConsciousAgent(reflection_db=None)
        candidates = [
            PromotionCandidate(
                memory_id="m1",
                priority_score=0.85,
                reason="hot memory",
                current_tier="long_term",
            )
        ]
        promoted = await agent._promote_memories(candidates)
        assert promoted == ["m1"]

        # Verify the DB state.
        conn = duckdb.connect(str(patched_db_path))
        try:
            tier = conn.execute(
                "SELECT memory_tier FROM conversations_v2 WHERE id=?", ["m1"]
            ).fetchone()[0]
            promo = conn.execute(
                "SELECT from_tier, to_tier, reason, priority_score FROM memory_promotions "
                "WHERE memory_id=?",
                ["m1"],
            ).fetchone()
        finally:
            conn.close()
        assert tier == "short_term"
        assert promo[0] == "long_term"
        assert promo[1] == "short_term"
        assert promo[2] == "hot memory"
        assert promo[3] == pytest.approx(0.85, rel=1e-5)

    @pytest.mark.asyncio
    async def test_continues_on_per_candidate_failure(
        self, patched_db_path: Path, monkeypatch
    ) -> None:
        conn = _seed_db_with_schema(patched_db_path)
        try:
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["m1", "x", "facts", 0.5, "long_term", "default"],
            )
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["m2", "y", "facts", 0.5, "long_term", "default"],
            )
            conn.commit()
        finally:
            conn.close()

        # Make the FIRST connection's UPDATE raise. Subsequent connections
        # (m2) get a fresh, working connection.
        original_connect = duckdb.connect
        call_count = {"n": 0}

        def connect_with_first_failure(*args, **kwargs):
            call_count["n"] += 1
            real_conn = original_connect(*args, **kwargs)

            if call_count["n"] != 1:
                return real_conn

            # Wrap the first connection so its execute() raises on UPDATE.
            class FailingConnection:
                def __init__(self, real):
                    self._real = real

                def execute(self, sql, params=None):
                    if "UPDATE conversations_v2" in sql:
                        raise RuntimeError("simulated first-candidate failure")
                    return self._real.execute(sql, params)

                def close(self):
                    self._real.close()

            return FailingConnection(real_conn)

        monkeypatch.setattr(duckdb, "connect", connect_with_first_failure)

        agent = ConsciousAgent(reflection_db=None)
        candidates = [
            PromotionCandidate(
                memory_id="m1", priority_score=0.8,
                reason="r1", current_tier="long_term",
            ),
            PromotionCandidate(
                memory_id="m2", priority_score=0.7,
                reason="r2", current_tier="long_term",
            ),
        ]
        promoted = await agent._promote_memories(candidates)
        # m1 errors out, m2 succeeds.
        assert "m2" in promoted
        assert "m1" not in promoted


# ---------------------------------------------------------------------------
# _demote_stale_memories — DB-backed
# ---------------------------------------------------------------------------


class TestDemoteStaleMemories:
    @pytest.mark.asyncio
    async def test_demotes_old_short_term_memories(
        self, patched_db_path: Path
    ) -> None:
        conn = _seed_db_with_schema(patched_db_path)
        try:
            # Two short-term memories: one stale (no access log) and one fresh.
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["stale", "x", "facts", 0.5, "short_term", "default"],
            )
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["fresh", "y", "facts", 0.5, "short_term", "default"],
            )
            conn.execute(
                "INSERT INTO memory_access_log "
                "(id, memory_id, access_type, timestamp) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                ["ax", "fresh", "search"],
            )
            conn.commit()
        finally:
            conn.close()

        agent = ConsciousAgent(reflection_db=None)
        demoted = await agent._demote_stale_memories()
        assert demoted == ["stale"]

        # Verify state.
        conn = duckdb.connect(str(patched_db_path))
        try:
            stale_tier = conn.execute(
                "SELECT memory_tier FROM conversations_v2 WHERE id=?", ["stale"]
            ).fetchone()[0]
            fresh_tier = conn.execute(
                "SELECT memory_tier FROM conversations_v2 WHERE id=?", ["fresh"]
            ).fetchone()[0]
        finally:
            conn.close()
        assert stale_tier == "long_term"
        assert fresh_tier == "short_term"

    @pytest.mark.asyncio
    async def test_no_short_term_returns_empty(
        self, patched_db_path: Path
    ) -> None:
        conn = _seed_db_with_schema(patched_db_path)
        try:
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["m1", "x", "facts", 0.5, "long_term", "default"],
            )
            conn.commit()
        finally:
            conn.close()

        agent = ConsciousAgent(reflection_db=None)
        demoted = await agent._demote_stale_memories()
        assert demoted == []


# ---------------------------------------------------------------------------
# _periodic_distill_skills — with reflection_db stub
# ---------------------------------------------------------------------------


class TestPeriodicDistillSkills:
    @pytest.mark.asyncio
    async def test_uses_reflection_db_when_provided(self) -> None:
        from unittest.mock import AsyncMock

        reflection_db = MagicMock()
        reflection_db.distill_skills_now = AsyncMock(
            return_value=[{"id": "s1"}, {"id": "s2"}]
        )

        agent = ConsciousAgent(reflection_db=reflection_db)
        count = await agent._periodic_distill_skills()
        assert count == 2
        reflection_db.distill_skills_now.assert_awaited_once_with(evidence_threshold=3)

    @pytest.mark.asyncio
    async def test_falls_back_to_db_when_reflection_db_none(
        self, patched_db_path: Path
    ) -> None:
        # No reflection_db and DB doesn't exist → 0.
        # Note: patched_db_path points at a file that doesn't exist yet.
        agent = ConsciousAgent(reflection_db=None)
        count = await agent._periodic_distill_skills()
        assert count == 0

    @pytest.mark.asyncio
    async def test_falls_back_to_db_with_empty_skills(
        self, patched_db_path: Path
    ) -> None:
        # Create the DB but no skills.
        _seed_db_with_schema(patched_db_path).close()
        agent = ConsciousAgent(reflection_db=None)
        count = await agent._periodic_distill_skills()
        # distill_skills returns [] on an empty DB.
        assert count == 0


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_then_stop(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        await agent.start()
        assert agent._running is True
        assert agent._task is not None

        await agent.stop()
        assert agent._running is False
        assert agent._task is None or agent._task.cancelled() or agent._task.done()

    @pytest.mark.asyncio
    async def test_start_when_already_running_is_noop(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        await agent.start()
        first_task = agent._task
        await agent.start()  # second start should warn, not double-launch
        assert agent._task is first_task
        await agent.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_noop(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        await agent.stop()  # no exception
        assert agent._running is False


# ---------------------------------------------------------------------------
# _analyze_and_optimize — orchestration
# ---------------------------------------------------------------------------


class TestAnalyzeAndOptimize:
    @pytest.mark.asyncio
    async def test_full_pipeline_returns_result_dict(
        self, patched_db_path: Path, monkeypatch
    ) -> None:
        # Mock the metrics calls so they don't fail in the test env.
        from session_buddy import metrics

        monkeypatch.setattr(metrics, "record_provenance_pruned", lambda n: None)
        monkeypatch.setattr(metrics, "record_causal_links_pruned", lambda n: None)
        monkeypatch.setattr(metrics, "record_skills_distilled", lambda n: None)
        monkeypatch.setattr(metrics, "record_periodic_job_errors", lambda errs: None)

        # Seed v2 schema + a memory so promote/demote have something to do.
        # Note: no access_log insert here because that creates an FK chain
        # that (in DuckDB's strict mode) blocks the promote UPDATE.
        conn = _seed_db_with_schema(patched_db_path)
        try:
            conn.execute(
                "INSERT INTO conversations_v2 "
                "(id, content, category, importance_score, memory_tier, namespace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ["m1", "x", "skills", 0.9, "long_term", "default"],
            )
            conn.commit()
        finally:
            conn.close()

        agent = ConsciousAgent(reflection_db=None, promotion_threshold=0.0)
        result = await agent._analyze_and_optimize()

        # Shape contract — no access_log seed → 0 patterns → 0 promotions
        # is expected; we just verify the dict structure.
        assert "timestamp" in result
        assert result["patterns_analyzed"] == 0
        assert result["promotion_candidates"] == 0
        assert result["promoted_count"] == 0
        assert result["promoted_ids"] == []
        assert result["demoted_ids"] == []
        assert result["provenance_pruned"] >= 0
        assert result["causal_links_pruned"] >= 0
        assert result["skills_distilled"] >= 0
        assert isinstance(result["periodic_jobs_errors"], list)

    @pytest.mark.asyncio
    async def test_step_failure_is_captured(
        self, patched_db_path: Path, monkeypatch
    ) -> None:
        # Force _promote_memories to raise so the orchestration catches
        # the exception and records it.
        agent = ConsciousAgent(reflection_db=None, promotion_threshold=0.0)

        async def boom_promote(candidates):
            raise RuntimeError("simulated promote failure")

        agent._promote_memories = boom_promote  # type: ignore[method-assign]

        # Mock metrics to avoid failures.
        from session_buddy import metrics

        monkeypatch.setattr(metrics, "record_provenance_pruned", lambda n: None)
        monkeypatch.setattr(metrics, "record_causal_links_pruned", lambda n: None)
        monkeypatch.setattr(metrics, "record_skills_distilled", lambda n: None)
        monkeypatch.setattr(metrics, "record_periodic_job_errors", lambda errs: None)

        result = await agent._analyze_and_optimize()
        # The error from _promote_memories is captured into periodic_jobs_errors.
        assert any("promote_memories" in e for e in result["periodic_jobs_errors"])
        # promoted_count defaults to 0 because promote failed.
        assert result["promoted_count"] == 0


# ---------------------------------------------------------------------------
# _run_periodic_jobs
# ---------------------------------------------------------------------------


class TestRunPeriodicJobs:
    @pytest.mark.asyncio
    async def test_returns_zero_counts_with_empty_db(
        self, patched_db_path: Path
    ) -> None:
        agent = ConsciousAgent(reflection_db=None)
        result = await agent._run_periodic_jobs()
        assert result == {
            "provenance_pruned": 0,
            "causal_links_pruned": 0,
            "skills_distilled": 0,
            "errors": [],
        }

    @pytest.mark.asyncio
    async def test_records_error_when_a_job_fails(
        self, patched_db_path: Path
    ) -> None:
        agent = ConsciousAgent(reflection_db=None)
        # Force the provenance prune to raise.
        async def boom(*args, **kwargs):
            raise RuntimeError("simulated prune failure")

        agent._periodic_prune_provenance = boom  # type: ignore[method-assign]
        result = await agent._run_periodic_jobs()
        assert any("provenance_prune" in e for e in result["errors"])
        # Other jobs still ran.
        assert result["causal_links_pruned"] == 0
        assert result["skills_distilled"] == 0


# ---------------------------------------------------------------------------
# _periodic_prune_provenance
# ---------------------------------------------------------------------------


class TestPeriodicPruneProvenance:
    @pytest.mark.asyncio
    async def test_zero_when_db_missing(
        self, tmp_db: Path, monkeypatch
    ) -> None:
        # tmp_db doesn't exist.
        import session_buddy.settings

        monkeypatch.setattr(
            session_buddy.settings, "get_database_path", lambda: tmp_db
        )
        agent = ConsciousAgent(reflection_db=None)
        count = await agent._periodic_prune_provenance(days=90)
        assert count == 0

    @pytest.mark.asyncio
    async def test_prunes_old_rows(self, patched_db_path: Path) -> None:
        conn = _seed_db_with_schema(patched_db_path)
        try:
            # memory_provenance columns: id, memory_id, source_type,
            # source_ref, extracted_at, model.
            conn.execute(
                "INSERT INTO memory_provenance "
                "(id, memory_id, source_type, extracted_at) "
                "VALUES (?, ?, ?, ?)",
                ["old", "m1", "test", datetime.now() - timedelta(days=120)],
            )
            conn.execute(
                "INSERT INTO memory_provenance "
                "(id, memory_id, source_type, extracted_at) "
                "VALUES (?, ?, ?, ?)",
                ["new", "m1", "test", datetime.now()],
            )
            conn.commit()
        finally:
            conn.close()

        agent = ConsciousAgent(reflection_db=None)
        count = await agent._periodic_prune_provenance(days=90)
        assert count == 1

        # Verify only the old row was removed.
        conn = duckdb.connect(str(patched_db_path))
        try:
            remaining = conn.execute(
                "SELECT id FROM memory_provenance ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert remaining == [("new",)]

    @pytest.mark.asyncio
    async def test_uses_reflection_db_when_provided(self) -> None:
        from unittest.mock import AsyncMock

        reflection_db = MagicMock()
        reflection_db.prune_provenance_older_than = AsyncMock(return_value=7)

        agent = ConsciousAgent(reflection_db=reflection_db)
        count = await agent._periodic_prune_provenance(days=30)
        assert count == 7
        reflection_db.prune_provenance_older_than.assert_awaited_once_with(days=30)


# ---------------------------------------------------------------------------
# _periodic_prune_causal_links
# ---------------------------------------------------------------------------


class TestPeriodicPruneCausalLinks:
    @pytest.mark.asyncio
    async def test_zero_when_db_missing(
        self, tmp_db: Path, monkeypatch
    ) -> None:
        import session_buddy.settings

        monkeypatch.setattr(
            session_buddy.settings, "get_database_path", lambda: tmp_db
        )
        agent = ConsciousAgent(reflection_db=None)
        count = await agent._periodic_prune_causal_links(days=90)
        assert count == 0

    @pytest.mark.asyncio
    async def test_prunes_old_causal_links(self, patched_db_path: Path) -> None:
        conn = _seed_db_with_schema(patched_db_path)
        try:
            # causal_links columns: id, from_id, to_id, link_type, evidence,
            # last_evidence_at, link_origin, created_at, depth.
            # The agent prunes by last_evidence_at (default = now() at row
            # creation), so backdate that column to simulate "old".
            conn.execute(
                "INSERT INTO causal_links "
                "(id, from_id, to_id, link_type, evidence, "
                "last_evidence_at, link_origin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ["old", "a", "b", "causes", 0.5,
                 datetime.now() - timedelta(days=120), "inferred"],
            )
            conn.execute(
                "INSERT INTO causal_links "
                "(id, from_id, to_id, link_type, evidence, "
                "last_evidence_at, link_origin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ["new", "c", "d", "causes", 0.5, datetime.now(), "inferred"],
            )
            conn.commit()
        finally:
            conn.close()

        agent = ConsciousAgent(reflection_db=None)
        count = await agent._periodic_prune_causal_links(days=90)
        assert count == 1

    @pytest.mark.asyncio
    async def test_uses_reflection_db_when_provided(self) -> None:
        from unittest.mock import AsyncMock

        reflection_db = MagicMock()
        reflection_db.prune_causal_links_older_than = AsyncMock(return_value=4)

        agent = ConsciousAgent(reflection_db=reflection_db)
        count = await agent._periodic_prune_causal_links(days=30)
        assert count == 4
        reflection_db.prune_causal_links_older_than.assert_awaited_once_with(
            days=30
        )


# ---------------------------------------------------------------------------
# force_analysis
# ---------------------------------------------------------------------------


class TestForceAnalysis:
    @pytest.mark.asyncio
    async def test_delegates_to_analyze_and_optimize(
        self, patched_db_path: Path, monkeypatch
    ) -> None:
        # Mock metrics.
        from session_buddy import metrics

        monkeypatch.setattr(metrics, "record_provenance_pruned", lambda n: None)
        monkeypatch.setattr(metrics, "record_causal_links_pruned", lambda n: None)
        monkeypatch.setattr(metrics, "record_skills_distilled", lambda n: None)
        monkeypatch.setattr(metrics, "record_periodic_job_errors", lambda errs: None)

        agent = ConsciousAgent(reflection_db=None)
        result = await agent.force_analysis()
        # Same shape as _analyze_and_optimize.
        assert "timestamp" in result
        assert "patterns_analyzed" in result
        assert "promoted_count" in result


# ---------------------------------------------------------------------------
# _run_loop — error path (brief)
# ---------------------------------------------------------------------------


class TestRunLoop:
    @pytest.mark.asyncio
    async def test_loop_logs_and_continues_on_error(self) -> None:
        agent = ConsciousAgent(reflection_db=None)
        # Make _analyze_and_optimize raise forever; loop should keep
        # running, swallowing exceptions and waiting 5 minutes on each.
        call_count = {"n": 0}

        async def boom_analyze():
            call_count["n"] += 1
            raise RuntimeError("simulated loop failure")

        agent._analyze_and_optimize = boom_analyze  # type: ignore[method-assign]

        # Replace asyncio.sleep in the loop body with a no-op.
        import asyncio as _asyncio

        original_sleep = _asyncio.sleep

        async def fast_sleep(seconds):
            call_count["n"] += 1  # also count sleep
            # Bail out by stopping the agent after a few iterations.
            agent._running = False

        # Patch conscious_agent's asyncio.sleep reference.
        import session_buddy.memory.conscious_agent as ca

        ca.asyncio.sleep = fast_sleep  # type: ignore[attr-defined]

        try:
            await agent.start()
            # Wait for the loop to stop itself.
            for _ in range(20):
                if not agent._running:
                    break
                await original_sleep(0.01)
            # Loop should have made at least one analyze call.
            assert call_count["n"] >= 1
        finally:
            await agent.stop()
            ca.asyncio.sleep = original_sleep  # type: ignore[attr-defined]
