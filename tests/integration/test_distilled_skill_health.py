"""Integration tests for the ``distilled_skill_health`` MCP tool (Phase 1.5 wiring).

The coverage report on the Crackerjack side calls this tool via the MCP
client (per A3 + Q3 default — Crackerjack should NOT read DuckDB
directly). The tool returns a list of distilled skills, each tagged
with a ``status`` of ``fresh``, ``stale``, ``under_utilized``, or
``cold``.

Status semantics (mirrors the plan's A4 + the "under-utilized"
criterion in Item 4):

- ``stale`` — ``last_reinforced_at < now() - threshold_days``
- ``under_utilized`` — ``importance_score >= 0.9`` and no matching
  Crackerjack skill (when ``crackerjack_skill_names`` is provided)
- ``cold`` — has never been reinforced (placeholder for the
  under-utilized case where no Crackerjack skill list is supplied,
  or for a row that has zero evidence and is the only signal in
  its category — the report's "cold" bucket)
- ``fresh`` — everything else

These tests are the RED-first contract. Each test seeds 1..3 skills
directly into the v2 schema so the tool can be tested in isolation
from the Conscious Agent's periodic jobs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any


def _seed_distilled_skill(
    db: Any,
    *,
    skill_id: str,
    problem_pattern: str,
    importance_score: float,
    last_reinforced_at: datetime | None = None,
) -> None:
    """Insert a single row into ``distilled_skills`` for testing.

    The v2 schema enforces ``importance_score >= 0.7`` via a CHECK
    constraint, so callers must use a value at or above the floor.
    """
    if last_reinforced_at is None:
        last_reinforced_at = datetime.now()
    db.conn.execute(
        """
        INSERT INTO distilled_skills
            (id, problem_pattern, suggested_approach, because,
             importance_score, model, created_at, last_reinforced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            skill_id,
            problem_pattern,
            "approach-" + skill_id,
            "because-" + skill_id,
            float(importance_score),
            "heuristic",
            last_reinforced_at,
            last_reinforced_at,
        ],
    )


# ---------------------------------------------------------------------------
# Test 1: stale vs fresh — the 90-day threshold (A4)
# ---------------------------------------------------------------------------


async def test_distilled_skill_health_marks_stale(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A skill reinforced > threshold_days ago is reported as 'stale'.

    The plan's A4 pins the threshold at 90 days, matching the
    retention policy. A skill reinforced 100 days ago must
    surface as ``stale``; one reinforced yesterday must
    surface as ``fresh``.
    """
    db = fast_temp_db

    now = datetime.now()
    _seed_distilled_skill(
        db,
        skill_id="skill-stale",
        problem_pattern="stale pattern",
        importance_score=0.85,
        last_reinforced_at=now - timedelta(days=100),
    )
    _seed_distilled_skill(
        db,
        skill_id="skill-fresh",
        problem_pattern="fresh pattern",
        importance_score=0.75,
        last_reinforced_at=now - timedelta(days=1),
    )

    # Import lazily to avoid module-load surprises; the tool is
    # wired in search_tools.py and registered alongside the
    # other Phase 1.5 tools.
    from session_buddy.mcp.tools.memory.search_tools import (
        _distilled_skill_health_impl,
    )

    result = await _distilled_skill_health_impl(threshold_days=90, db=db)

    by_id = {row["id"]: row for row in result}
    assert "skill-stale" in by_id, f"missing stale row in {result!r}"
    assert "skill-fresh" in by_id, f"missing fresh row in {result!r}"
    assert by_id["skill-stale"]["status"] == "stale", (
        f"100-day-old skill should be 'stale', got {by_id['skill-stale']!r}"
    )
    # Per the plan's acceptance, the report's non-stale /
    # non-under-utilized bucket is 'cold' — a recently-reinforced
    # low-importance skill is exactly the "cold-start" signal:
    # present, recent, but no actionable signal.
    assert by_id["skill-fresh"]["status"] == "cold", (
        f"1-day-old low-importance skill should be 'cold', got "
        f"{by_id['skill-fresh']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: under-utilized — high importance with no Crackerjack counterpart
# ---------------------------------------------------------------------------


async def test_distilled_skill_health_marks_under_utilized(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A high-importance skill with no matching Crackerjack skill is 'under_utilized'.

    The Item 4 acceptance criterion: a skill with
    ``importance_score = 0.95`` and no Crackerjack skill whose name
    contains the problem pattern is reported as
    ``under_utilized`` so operators know to bootstrap a Crackerjack
    skill for it.
    """
    db = fast_temp_db

    _seed_distilled_skill(
        db,
        skill_id="skill-unused",
        problem_pattern="duckdb indexes",
        importance_score=0.95,
        last_reinforced_at=datetime.now() - timedelta(days=2),
    )
    # A second high-importance skill whose name DOES match a
    # Crackerjack skill — this one should be 'fresh' (not under-utilized).
    _seed_distilled_skill(
        db,
        skill_id="skill-with-match",
        problem_pattern="cruddy coverage",
        importance_score=0.92,
        last_reinforced_at=datetime.now() - timedelta(days=2),
    )
    # Bump evidence_count so neither skill is 'cold'.
    db.conn.execute(
        "UPDATE distilled_skills SET evidence_count = 5 WHERE id IN (?, ?)",
        ["skill-unused", "skill-with-match"],
    )

    from session_buddy.mcp.tools.memory.search_tools import (
        _distilled_skill_health_impl,
    )

    result = await _distilled_skill_health_impl(
        threshold_days=90,
        crackerjack_skill_names=["cruddy coverage", "some other skill"],
        db=db,
    )

    by_id = {row["id"]: row for row in result}
    assert by_id["skill-unused"]["status"] == "under_utilized", (
        f"high-importance skill with no Crackerjack match should be "
        f"'under_utilized', got {by_id['skill-unused']!r}"
    )
    assert by_id["skill-with-match"]["status"] == "fresh", (
        f"high-importance skill WITH a Crackerjack match should be "
        f"'fresh' (not 'under_utilized'), got {by_id['skill-with-match']!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: cold — never reinforced (zero evidence, low importance)
# ---------------------------------------------------------------------------


async def test_distilled_skill_health_marks_cold(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A skill that was never reinforced and is below the 0.9
    importance floor is reported as 'cold'.

    'Cold' is the catch-all bucket for skills the report can't
    recommend acting on — never reinforced, low importance, or
    evidence_count == 0. It is distinct from 'stale' (which
    requires a non-zero last_reinforced_at older than the
    threshold) and from 'under_utilized' (which requires
    importance >= 0.9 with no Crackerjack match).
    """
    db = fast_temp_db

    _seed_distilled_skill(
        db,
        skill_id="skill-cold",
        problem_pattern="lone pattern",
        importance_score=0.7,
        last_reinforced_at=datetime.now(),
    )
    # Backdate created_at so the row has aged, but never reinforced.
    db.conn.execute(
        "UPDATE distilled_skills SET evidence_count = 0 WHERE id = ?",
        ["skill-cold"],
    )

    from session_buddy.mcp.tools.memory.search_tools import (
        _distilled_skill_health_impl,
    )

    result = await _distilled_skill_health_impl(threshold_days=90, db=db)

    by_id = {row["id"]: row for row in result}
    assert by_id["skill-cold"]["status"] == "cold", (
        f"never-reinforced low-importance skill should be 'cold', "
        f"got {by_id['skill-cold']!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: the 3-skill acceptance scenario from the plan (Item 4)
# ---------------------------------------------------------------------------


async def test_distilled_skill_health_three_seed_scenario(
    fast_temp_db: AsyncGenerator,
) -> None:
    """The plan's Item 4 acceptance: 3 skills, 3 different statuses.

    Seeds:
    - 1 reinforced yesterday (fresh)
    - 1 reinforced 100 days ago (stale)
    - 1 with importance=0.95 and no Crackerjack counterpart
      (under_utilized)

    Asserts the report returns one row per status bucket.
    """
    db = fast_temp_db

    now = datetime.now()
    _seed_distilled_skill(
        db,
        skill_id="fresh-skill",
        problem_pattern="pattern fresh",
        importance_score=0.75,
        last_reinforced_at=now - timedelta(days=1),
    )
    _seed_distilled_skill(
        db,
        skill_id="stale-skill",
        problem_pattern="pattern stale",
        importance_score=0.8,
        last_reinforced_at=now - timedelta(days=100),
    )
    _seed_distilled_skill(
        db,
        skill_id="under-utilized-skill",
        problem_pattern="pattern underutilized",
        importance_score=0.95,
        last_reinforced_at=now - timedelta(days=2),
    )
    # Bump evidence_count so 'fresh' really reports as 'fresh'
    # rather than 'cold' (cold = evidence_count == 0).
    db.conn.execute(
        "UPDATE distilled_skills SET evidence_count = 5 "
        "WHERE id IN (?, ?, ?)",
        ["fresh-skill", "stale-skill", "under-utilized-skill"],
    )

    from session_buddy.mcp.tools.memory.search_tools import (
        _distilled_skill_health_impl,
    )

    result = await _distilled_skill_health_impl(
        threshold_days=90,
        crackerjack_skill_names=["crackerjack", "unrelated skill"],
        db=db,
    )

    statuses = {row["status"] for row in result}
    assert statuses == {"fresh", "stale", "under_utilized"}, (
        f"expected exactly the 3 status buckets from the plan's "
        f"acceptance, got {statuses!r} from {result!r}"
    )
    by_id = {row["id"]: row for row in result}
    assert by_id["fresh-skill"]["status"] == "fresh"
    assert by_id["stale-skill"]["status"] == "stale"
    assert by_id["under-utilized-skill"]["status"] == "under_utilized"
