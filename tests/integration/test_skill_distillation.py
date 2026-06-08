"""Integration tests for Skill Distillation (Phase 1.5 #6).

The v2 rewire established the v2 tables; this feature adds a
``distilled_skills`` table that captures learnable patterns extracted
from session activity. The plan's contract is:

- A skill is a four-field artifact: ``problem_pattern`` (X),
  ``suggested_approach`` (Y), ``because`` (Z), and an
  ``evidence_count`` of prior cases.
- The plan's quality floor is ``importance_score >= 0.7`` (CHECK
  constraint). Below that, the distiller filters out the row.
- Source memory ids are stored as a JSON array (VARCHAR) for
  provenance — "N prior cases" comes from this list's length.
- The Conscious Agent's LLM synthesis path is separate from the
  data layer; the ``model`` column records which path produced
  the row ('heuristic' for the cheap path, an LLM name for the
  Conscious Agent path).

The distiller is LLM-optional. The data layer works without an
LLM call; the LLM path is an enhancement that can rewrite
``suggested_approach`` into better prose. Tests use the heuristic
path so they don't need a configured LLM provider.

Each test uses ``fast_temp_db`` so the v2 schema (and the new
``distilled_skills`` table) is freshly created in a temp file.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest


# ---------------------------------------------------------------------------
# Test 1: distill_skills_now produces >= 1 skill from repeated-access patterns
# ---------------------------------------------------------------------------


async def test_distill_skills_now_produces_skill(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A category with 3+ accessed memories in the same project → skill.

    The plan's evidence threshold is "3 prior cases". The distiller
    clusters memories by (project, category) and produces a skill
    for each cluster with at least ``evidence_threshold`` memories.
    The synthesized ``importance_score`` must be >= 0.7 (CHECK
    constraint) to be persisted.
    """
    db = fast_temp_db

    # 3 memories in proj-p, all category="context", all accessed.
    ids: list[str] = []
    for i in range(3):
        cid = await db.store_conversation(
            content=f"memory {i} about python async",
            metadata={"project": "proj-p"},
            source_type="manual",
            category="context",
        )
        ids.append(cid)
        # Simulate access — a search would log to memory_access_log.
        db.conn.execute(
            "INSERT INTO memory_access_log (id, memory_id, access_type) "
            "VALUES (?, ?, 'retrieve')",
            [f"access-{i}", cid],
        )

    skills = await db.distill_skills_now(evidence_threshold=3)

    # At least one skill should have been distilled.
    assert len(skills) >= 1, (
        f"expected >= 1 skill from repeated-access pattern, got {skills!r}"
    )

    # The skill that captures the proj-p context cluster should exist.
    proj_skills = [s for s in skills if s["problem_pattern"]]
    assert len(proj_skills) >= 1

    # And the importance_score must be at or above the 0.7 floor.
    for s in proj_skills:
        assert s["importance_score"] >= 0.7, (
            f"importance_score below floor: {s!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: importance_score < 0.7 is rejected by the CHECK constraint
# ---------------------------------------------------------------------------


def test_check_constraint_rejects_low_importance() -> None:
    """Direct INSERT with importance_score < 0.7 must raise.

    The CHECK constraint is the database's last line of defense
    against a regression in the distiller that lets low-quality
    skills slip through. The application filter is the first
    line; the constraint is the second.
    """
    import tempfile
    from pathlib import Path

    from session_buddy.adapters.reflection_adapter_oneiric import (
        ReflectionDatabaseAdapterOneiric,
    )
    from session_buddy.adapters.settings import ReflectionAdapterSettings
    from ulid import ULID

    async def go() -> None:
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
            path = Path(f.name)
        settings = ReflectionAdapterSettings(
            database_path=path,
            collection_name="default",
            embedding_dim=384,
            enable_vss=False,
            enable_embeddings=False,
        )
        db = ReflectionDatabaseAdapterOneiric(settings=settings)
        await db.initialize()

        with pytest.raises(Exception) as exc_info:  # noqa: PT011
            db.conn.execute(
                """
                INSERT INTO distilled_skills
                    (id, problem_pattern, suggested_approach, because,
                     importance_score, model)
                VALUES (?, 'x', 'y', 'z', 0.5, 'heuristic')
                """,
                [str(ULID())],
            )
        # The CHECK constraint surfaces as a DuckDB ConstraintException;
        # the test accepts any exception family and just checks that
        # the row was NOT persisted.
        assert "CHECK" in str(exc_info.value) or "constraint" in str(
            exc_info.value
        ).lower(), f"expected CHECK violation, got {exc_info.value!r}"

        # And nothing was persisted.
        n = db.conn.execute(
            "SELECT COUNT(*) FROM distilled_skills"
        ).fetchone()[0]
        assert n == 0, f"low-quality row leaked through: {n} rows"

    import asyncio
    asyncio.run(go())


# ---------------------------------------------------------------------------
# Test 3: search_distilled_skills returns matching skills
# ---------------------------------------------------------------------------


async def test_search_distilled_skills_finds_match(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Search by problem-pattern substring returns matching skills.

    The data layer's search is a simple LIKE match on the three
    text fields. LLM-based semantic search is a future Conscious
    Agent enhancement; the data layer is intentionally a thin
    wrapper.
    """
    db = fast_temp_db

    # Seed 3 memories and distill. The first content word is what
    # the heuristic distiller uses for the topic string, so we
    # pick a distinctive first word ("duckdb-feature") that will
    # be extracted verbatim into the problem_pattern.
    for i in range(3):
        cid = await db.store_conversation(
            content=f"duckdb-feature-{i} covers indexing and HNSW",
            metadata={"project": "p"},
            source_type="manual",
            category="rules",
        )
        db.conn.execute(
            "INSERT INTO memory_access_log (id, memory_id, access_type) "
            "VALUES (?, ?, 'retrieve')",
            [f"access-{i}", cid],
        )

    skills = await db.distill_skills_now(evidence_threshold=3)
    assert len(skills) >= 1

    # Search for a substring of the problem_pattern.
    found = await db.search_distilled_skills(query="duckdb", limit=5)
    assert len(found) >= 1, f"expected match for 'duckdb', got {found!r}"
    for skill in found:
        assert "duckdb" in skill["problem_pattern"].lower() or any(
            "duckdb" in str(v).lower() for v in skill.values()
        )


# ---------------------------------------------------------------------------
# Test 4: reinforce_skill bumps evidence_count and last_reinforced_at
# ---------------------------------------------------------------------------


async def test_reinforce_skill_bumps_counts(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Re-observing a skill's pattern bumps evidence_count + timestamp."""
    db = fast_temp_db

    # Distill a skill.
    for i in range(3):
        cid = await db.store_conversation(
            content=f"memory {i} about TDD",
            metadata={"project": "p"},
            source_type="manual",
            category="rules",
        )
        db.conn.execute(
            "INSERT INTO memory_access_log (id, memory_id, access_type) "
            "VALUES (?, ?, 'retrieve')",
            [f"access-{i}", cid],
        )
    skills = await db.distill_skills_now(evidence_threshold=3)
    assert len(skills) >= 1
    skill_id = skills[0]["id"]

    first_row = db.conn.execute(
        "SELECT evidence_count, last_reinforced_at FROM distilled_skills "
        "WHERE id = ?",
        [skill_id],
    ).fetchone()
    assert first_row is not None
    first_count = first_row[0]
    first_ts = first_row[1]

    # Backdate and reinforce.
    db.conn.execute(
        "UPDATE distilled_skills SET last_reinforced_at = "
        "last_reinforced_at - INTERVAL (? || ' seconds') "
        "WHERE id = ?",
        ["5", skill_id],
    )

    reinforced = await db.reinforce_skill(skill_id=skill_id)
    assert reinforced is True

    second_row = db.conn.execute(
        "SELECT evidence_count, last_reinforced_at FROM distilled_skills "
        "WHERE id = ?",
        [skill_id],
    ).fetchone()
    assert second_row is not None
    assert second_row[0] == first_count + 1, (
        f"evidence_count should advance from {first_count} to "
        f"{first_count + 1}, got {second_row[0]}"
    )
    assert second_row[1] > first_ts, (
        "last_reinforced_at should advance on reinforce"
    )


# ---------------------------------------------------------------------------
# Test 5: top N skills by importance_score
# ---------------------------------------------------------------------------


async def test_top_skills_by_importance(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``search_distilled_skills`` with empty query returns top by score."""
    db = fast_temp_db

    # Two distinct clusters, each producing a skill.
    for cat in ("rules", "preferences"):
        for i in range(3):
            cid = await db.store_conversation(
                content=f"{cat} memory {i}",
                metadata={"project": f"proj-{cat}"},
                source_type="manual",
                category=cat,
            )
            db.conn.execute(
                "INSERT INTO memory_access_log (id, memory_id, access_type) "
                "VALUES (?, ?, 'retrieve')",
                [f"access-{cat}-{i}", cid],
            )

    skills = await db.distill_skills_now(evidence_threshold=3)
    assert len(skills) >= 2

    # Top-N should return them sorted by importance_score DESC.
    top = await db.search_distilled_skills(query="", limit=10)
    assert len(top) >= 2
    scores = [s["importance_score"] for s in top]
    assert scores == sorted(scores, reverse=True), (
        f"top skills should be sorted DESC by importance, got {scores!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: source_memory_ids JSON list round-trips
# ---------------------------------------------------------------------------


async def test_source_memory_ids_round_trip(
    fast_temp_db: AsyncGenerator,
) -> None:
    """The JSON list of contributing memory ids is preserved verbatim."""
    import json

    db = fast_temp_db

    ids: list[str] = []
    for i in range(3):
        cid = await db.store_conversation(
            content=f"round-trip {i}",
            metadata={"project": "p"},
            source_type="manual",
            category="rules",
        )
        ids.append(cid)
        db.conn.execute(
            "INSERT INTO memory_access_log (id, memory_id, access_type) "
            "VALUES (?, ?, 'retrieve')",
            [f"access-{i}", cid],
        )

    skills = await db.distill_skills_now(evidence_threshold=3)
    assert len(skills) >= 1

    skill = skills[0]
    assert skill["source_memory_ids"] is not None
    # The distiller stores the JSON as VARCHAR; the adapter
    # decodes it for the consumer.
    decoded = json.loads(skill["source_memory_ids"])
    assert isinstance(decoded, list)
    assert all(isinstance(m, str) for m in decoded)
    # The contributing memory ids should be a subset of the seeded
    # memories. We don't require exact equality because the
    # distiller may add more from the access-pattern join.
    for m in decoded:
        assert m in ids, f"unexpected source_memory_id {m!r}"


# ---------------------------------------------------------------------------
# Test 7: distiller module is LLM-optional (no LLM imports required)
# ---------------------------------------------------------------------------


def test_distiller_module_is_llm_optional() -> None:
    """The data layer (skills module) must not require an LLM.

    The plan's LLM Cost Ceiling caps skill distillation at 100
    calls/week. The data layer must work without an LLM call —
    the LLM path is a Conscious Agent enhancement, not a
    dependency. A regression that imports an LLM client at module
    scope would burn the budget.

    Allowed: heuristic defaults. Forbidden: provider SDK imports
    or hardcoded LLM calls.
    """
    import session_buddy.skills.distiller as distiller

    source = open(distiller.__file__).read()
    forbidden = [
        "import openai",
        "from openai",
        "import anthropic",
        "from anthropic",
        "import minimax",
        "from minimax",
        "ChatCompletion",
    ]
    for needle in forbidden:
        assert needle not in source, (
            f"distiller.py must not {needle!r} (LLM Cost Ceiling)"
        )


# ---------------------------------------------------------------------------
# Test 8: distill_skills_now with insufficient evidence returns empty
# ---------------------------------------------------------------------------


async def test_distill_returns_empty_for_low_evidence(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A single memory does not produce a skill (evidence threshold = 3)."""
    db = fast_temp_db

    # One memory, one access — below the 3-case threshold.
    cid = await db.store_conversation(
        content="lone memory",
        metadata={"project": "p"},
        source_type="manual",
        category="context",
    )
    db.conn.execute(
        "INSERT INTO memory_access_log (id, memory_id, access_type) "
        "VALUES (?, ?, 'retrieve')",
        ["access-lone", cid],
    )

    skills = await db.distill_skills_now(evidence_threshold=3)
    assert skills == [], (
        f"single memory should not produce a skill, got {skills!r}"
    )


# ---------------------------------------------------------------------------
# Test 9: reinforce_skill on unknown id returns False
# ---------------------------------------------------------------------------


async def test_reinforce_unknown_skill_returns_false(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Reinforcing a non-existent skill id is a no-op (returns False)."""
    db = fast_temp_db

    reinforced = await db.reinforce_skill(skill_id="NONEXISTENT_01")
    assert reinforced is False


# ---------------------------------------------------------------------------
# Test 10: empty db returns empty result for all queries
# ---------------------------------------------------------------------------


async def test_empty_db_returns_empty_results(
    fast_temp_db: AsyncGenerator,
) -> None:
    """On a freshly-initialized db, all skill queries return []."""
    db = fast_temp_db

    distilled = await db.distill_skills_now()
    assert distilled == []

    searched = await db.search_distilled_skills(query="anything")
    assert searched == []
