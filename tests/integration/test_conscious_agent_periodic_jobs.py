"""Integration tests for Conscious Agent periodic jobs (Phase 1.5 follow-up).

The Conscious Agent runs as a background loop with three new
periodic jobs added by Phase 1.5:

- ``prune_provenance_older_than(days=90)`` — drop provenance rows
  that haven't been touched in 90 days (per the plan's R1 retention
  policy).
- ``prune_causal_links_older_than(days=90)`` — drop causal links
  that haven't been touched in 90 days (per the plan's §Feature #3
  pruning policy).
- ``distill_skills_now()`` — extract learnable patterns from current
  session activity (per the plan's §Feature #6).

These jobs run alongside the existing promotion/demotion logic in
``_analyze_and_optimize``. They are best-effort: a failure in
one job must NOT stop the others (the plan's resilience
contract — see Decision I in the plan).

Each test exercises the Conscious Agent's run loop end-to-end against
the ``fast_temp_db`` fixture and pins the result keys.

## Test fixture note

The Conscious Agent's pre-existing methods (``_demote_stale_memories``,
``_analyze_access_patterns``) open their own DuckDB connection via
``get_database_path()`` rather than using ``self.reflection_db``. To
make those methods see the test's temp DB, we patch
``session_buddy.settings.get_database_path`` to return the temp path
for the duration of each test. The new periodic jobs honor
``self.reflection_db`` directly, so they pick up the fixture
without patching.
"""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_with_patched_path(fast_temp_db: AsyncGenerator):
    """Yield ``(agent, db)`` with ``get_database_path`` patched to the
    temp DB. The Conscious Agent's pre-existing methods open their
    own DuckDB connection via ``get_database_path()``; the new
    periodic jobs honor ``self.reflection_db`` directly. This
    fixture bridges the two.
    """
    from session_buddy.memory.conscious_agent import ConsciousAgent
    from session_buddy import settings as settings_mod

    db = fast_temp_db
    db_path = Path(str(db.settings.database_path))
    agent = ConsciousAgent(reflection_db=db, analysis_interval_hours=1)
    with patch.object(
        settings_mod, "get_database_path", lambda: db_path
    ):
        yield agent, db


# ---------------------------------------------------------------------------
# Test 1: _analyze_and_optimize returns new periodic-job keys
# ---------------------------------------------------------------------------


async def test_analyze_returns_periodic_job_keys(
    agent_with_patched_path: tuple,
) -> None:
    """The result dict gains ``provenance_pruned``,
    ``causal_links_pruned``, ``skills_distilled``, and
    ``periodic_jobs_errors`` keys (Phase 1.5 follow-up wiring).
    """
    agent, _db = agent_with_patched_path
    results = await agent._analyze_and_optimize()

    expected_keys = {
        # Pre-existing keys.
        "timestamp",
        "patterns_analyzed",
        "promotion_candidates",
        "promoted_count",
        "demoted_count",
        "promoted_ids",
        "demoted_ids",
        # Phase 1.5 follow-up keys.
        "provenance_pruned",
        "causal_links_pruned",
        "skills_distilled",
        "periodic_jobs_errors",
    }
    missing = expected_keys - results.keys()
    assert not missing, (
        f"_analyze_and_optimize missing keys: {missing}; got {results.keys()}"
    )
    # The new keys default to safe values on a clean DB.
    assert results["provenance_pruned"] == 0
    assert results["causal_links_pruned"] == 0
    assert results["skills_distilled"] == 0
    assert results["periodic_jobs_errors"] == []


# ---------------------------------------------------------------------------
# Test 2: provenance pruning runs as part of the periodic loop
# ---------------------------------------------------------------------------


async def test_provenance_pruning_runs_within_loop(
    agent_with_patched_path: tuple,
) -> None:
    """A backdated provenance row is pruned by the agent's loop.

    The plan's retention is 90 days. A row backdated 100 days is
    in scope; a fresh row is not. The Conscious Agent's loop
    delegates to ``prune_provenance_older_than`` (the same method
    the MCP tool exposes).
    """
    agent, db = agent_with_patched_path

    # Seed a memory + provenance row, then backdate.
    conv_id = await db.store_conversation(
        content="test",
        metadata={"source_session": "sess-1"},
        source_type="claude_code",
    )
    db.conn.execute(
        "UPDATE memory_provenance SET extracted_at = now() - INTERVAL '100 days' "
        "WHERE memory_id = ?",
        [conv_id],
    )
    pre_count = db.conn.execute(
        "SELECT COUNT(*) FROM memory_provenance WHERE memory_id = ?",
        [conv_id],
    ).fetchone()[0]
    assert pre_count == 1
    results = await agent._analyze_and_optimize()

    # The pruned count is at least 1 (the backdated row).
    assert results["provenance_pruned"] >= 1, (
        f"expected provenance_pruned >= 1, got {results['provenance_pruned']!r}"
    )

    post_count = db.conn.execute(
        "SELECT COUNT(*) FROM memory_provenance WHERE memory_id = ?",
        [conv_id],
    ).fetchone()[0]
    assert post_count == 0, f"backdated row should be pruned, got {post_count}"


# ---------------------------------------------------------------------------
# Test 3: causal-link pruning runs as part of the periodic loop
# ---------------------------------------------------------------------------


async def test_causal_link_pruning_runs_within_loop(
    agent_with_patched_path: tuple,
) -> None:
    """A backdated causal link is pruned by the agent's loop.

    Causal links use the same 90-day retention as provenance.
    """
    agent, db = agent_with_patched_path

    from_id = await db.store_conversation(
        content="a", metadata={"project": "p"}, source_type="manual"
    )
    to_id = await db.store_conversation(
        content="b", metadata={"project": "p"}, source_type="manual"
    )
    link_id = await db.record_observed_link(
        from_id=from_id, to_id=to_id, link_type="led_to", evidence=0.9
    )
    db.conn.execute(
        "UPDATE causal_links SET last_evidence_at = now() - INTERVAL '100 days' "
        "WHERE id = ?",
        [link_id],
    )

    results = await agent._analyze_and_optimize()

    assert results["causal_links_pruned"] >= 1, (
        f"expected causal_links_pruned >= 1, got {results['causal_links_pruned']!r}"
    )

    remaining = db.conn.execute(
        "SELECT COUNT(*) FROM causal_links WHERE id = ?", [link_id]
    ).fetchone()[0]
    assert remaining == 0, f"backdated link should be pruned, got {remaining}"


# ---------------------------------------------------------------------------
# Test 4: skill distillation runs as part of the periodic loop
# ---------------------------------------------------------------------------


async def test_skill_distillation_runs_within_loop(
    agent_with_patched_path: tuple,
) -> None:
    """The agent's loop delegates to ``distill_skills_now``.

    A clean DB returns 0 (no skills to distill); the wiring
    matters, not the result.
    """
    agent, _db = agent_with_patched_path

    results = await agent._analyze_and_optimize()

    # The key exists and is an int (could be 0 on a clean DB).
    assert isinstance(results["skills_distilled"], int)
    assert results["skills_distilled"] >= 0


# ---------------------------------------------------------------------------
# Test 5: best-effort — one job failure does NOT stop the others
# ---------------------------------------------------------------------------


async def test_periodic_job_failure_does_not_stop_loop(
    fast_temp_db: AsyncGenerator,
) -> None:
    """If one periodic job raises, the others still run.

    The plan's resilience contract: Conscious Agent is best-effort.
    A failure in prune_provenance must not stop causal-link
    pruning or skill distillation. The error is captured into
    ``periodic_jobs_errors`` instead of raising.
    """
    from session_buddy.memory.conscious_agent import ConsciousAgent

    db = fast_temp_db

    # Make prune_provenance_older_than raise; leave the other two
    # working. The agent should capture the error and continue.
    original_prune = db.prune_provenance_older_than

    async def failing_prune(*args: object, **kwargs: object) -> int:
        raise RuntimeError("simulated provenance prune failure")

    db.prune_provenance_older_than = failing_prune  # type: ignore[method-assign]
    try:
        agent = ConsciousAgent(reflection_db=db, analysis_interval_hours=1)
        results = await agent._analyze_and_optimize()

        # The error is recorded.
        assert any(
            "provenance" in err for err in results["periodic_jobs_errors"]
        ), (
            f"expected provenance error in {results['periodic_jobs_errors']!r}"
        )

        # The other two jobs still ran (their counts are valid ints).
        assert isinstance(results["causal_links_pruned"], int)
        assert isinstance(results["skills_distilled"], int)
    finally:
        db.prune_provenance_older_than = original_prune  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Test 6: cadence (analysis_interval_hours) is the run-loop knob
# ---------------------------------------------------------------------------


async def test_cadence_is_controlled_by_analysis_interval_hours(
    fast_temp_db: AsyncGenerator,
) -> None:
    """The agent's analysis_interval matches the constructor arg.

    This pins the contract: the Conscious Agent uses the same
    cadence for promotion/demotion AND the new periodic jobs.
    """
    from session_buddy.memory.conscious_agent import ConsciousAgent

    db = fast_temp_db
    agent = ConsciousAgent(reflection_db=db, analysis_interval_hours=12)

    assert agent.analysis_interval == timedelta(hours=12)


# ---------------------------------------------------------------------------
# Test 7: no reflection_db → periodic jobs are skipped, not crashed
# ---------------------------------------------------------------------------


async def test_no_reflection_db_skips_periodic_jobs(
    agent_with_patched_path: tuple,
) -> None:
    """If ``reflection_db`` is None, the new periodic jobs short-circuit
    cleanly while the legacy promotion/demotion still runs.

    The new jobs honor ``self.reflection_db`` — when it's None,
    they return their safe defaults without raising. The legacy
    methods (``_demote_stale_memories``) open their own
    connection regardless. This test pins the contract that the
    new jobs don't crash when ``reflection_db`` is None.
    """
    from session_buddy.memory.conscious_agent import ConsciousAgent

    # Make a fresh agent with reflection_db=None (deliberately
    # override the fixture's adapter).
    agent, _db = agent_with_patched_path
    agent.reflection_db = None  # type: ignore[assignment]

    results = await agent._analyze_and_optimize()

    # The new keys are at safe defaults — the new jobs short-circuited
    # because reflection_db is None.
    assert results["provenance_pruned"] == 0
    assert results["causal_links_pruned"] == 0
    assert results["skills_distilled"] == 0
    # No errors should be recorded for the skipped jobs (they
    # didn't run, they didn't fail).
    assert results["periodic_jobs_errors"] == []
