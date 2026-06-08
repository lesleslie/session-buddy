"""Integration tests for Honcho-style per-project peer modeling (Phase 1.5 #2).

The v2 rewire established the v2 tables; this feature adds a
``user_models`` table that captures an evolving, LLM-derivable
"theory of mind" per ``(peer_id, project_id)`` pair. The composite
primary key enforces per-project scoping at the schema level — a
global user model would be a privacy disaster, and the schema makes
it impossible to construct one by accident.

The Conscious Agent is the only legitimate writer of new peer
representations; the adapter exposes three read/write methods
(``get_peer_model``, ``update_peer_model``, ``peer_context``) plus
the underlying table. ACL is a CALLER concern: tools check the
``peer_models:read`` / ``peer_models:write`` permission, not the
adapter.

Each test uses ``fast_temp_db`` so the v2 schema (and the new
``user_models`` table) is freshly created in a temp file.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest


# ---------------------------------------------------------------------------
# Test 1: get_peer_model returns None for unknown peer
# ---------------------------------------------------------------------------


async def test_get_peer_model_returns_none_for_unknown(
    fast_temp_db: AsyncGenerator,
) -> None:
    """First read for a never-seen peer returns None (no row created)."""
    db = fast_temp_db

    result = await db.get_peer_model(peer_id="user-1", project_id="proj-1")

    assert result is None, (
        f"expected None for unknown peer, got {result!r}"
    )

    # No row should have been created on a read miss.
    count = db.conn.execute(
        "SELECT COUNT(*) FROM user_models WHERE peer_id = ?",
        ["user-1"],
    ).fetchone()
    assert count is not None
    assert count[0] == 0, (
        f"read miss should not create a row, got {count[0]} rows"
    )


# ---------------------------------------------------------------------------
# Test 2: update_peer_model creates initial row
# ---------------------------------------------------------------------------


async def test_update_peer_model_creates_initial_row(
    fast_temp_db: AsyncGenerator,
) -> None:
    """First call upserts a new row with model='heuristic'."""
    db = fast_temp_db

    representation = await db.update_peer_model(
        peer_id="user-1",
        project_id="proj-1",
    )

    assert isinstance(representation, str), (
        f"expected str representation, got {type(representation).__name__}"
    )
    assert len(representation) > 0, "representation should be non-empty"

    rows = db.conn.execute(
        """
        SELECT representation_text, evidence_count, model, peer_id, project_id
        FROM user_models
        WHERE peer_id = ? AND project_id = ?
        """,
        ["user-1", "proj-1"],
    ).fetchall()
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    row = rows[0]
    assert row[0] == representation
    assert row[1] == 1, f"first update should yield evidence_count=1, got {row[1]}"
    assert row[2] == "heuristic", f"expected model='heuristic', got {row[2]!r}"
    assert row[3] == "user-1"
    assert row[4] == "proj-1"


# ---------------------------------------------------------------------------
# Test 3: update_peer_model increments evidence_count and updates timestamp
# ---------------------------------------------------------------------------


async def test_update_peer_model_increments_evidence(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Repeat updates bump evidence_count and last_updated."""
    db = fast_temp_db

    first = await db.update_peer_model(peer_id="user-1", project_id="proj-1")
    first_row = db.conn.execute(
        "SELECT last_updated, evidence_count FROM user_models "
        "WHERE peer_id = ? AND project_id = ?",
        ["user-1", "proj-1"],
    ).fetchone()
    assert first_row is not None
    first_ts = first_row[0]
    assert first_row[1] == 1

    # Force a measurable clock delta so last_updated can advance.
    db.conn.execute(
        "UPDATE user_models SET last_updated = last_updated - INTERVAL (? || ' seconds') "
        "WHERE peer_id = ? AND project_id = ?",
        ["2", "user-1", "proj-1"],
    )

    second = await db.update_peer_model(peer_id="user-1", project_id="proj-1")
    second_row = db.conn.execute(
        "SELECT last_updated, evidence_count FROM user_models "
        "WHERE peer_id = ? AND project_id = ?",
        ["user-1", "proj-1"],
    ).fetchone()
    assert second_row is not None
    assert second_row[1] == 2, (
        f"expected evidence_count=2 after second update, got {second_row[1]}"
    )
    assert second_row[0] > first_ts, (
        "last_updated should advance on update"
    )
    # Both calls should return representations (even if identical).
    assert isinstance(first, str)
    assert isinstance(second, str)


# ---------------------------------------------------------------------------
# Test 4: peer_context includes the representation + recent memories
# ---------------------------------------------------------------------------


async def test_peer_context_returns_representation_and_recent(
    fast_temp_db: AsyncGenerator,
) -> None:
    """peer_context bundles representation + last N memories for that peer."""
    db = fast_temp_db

    # Seed: a representation + a few memories tagged with the project.
    await db.update_peer_model(peer_id="user-1", project_id="proj-1")
    for i in range(3):
        await db.store_conversation(
            content=f"memory-{i} for user-1",
            metadata={"project": "proj-1"},
            source_type="manual",
        )

    context = await db.peer_context(
        peer_id="user-1", project_id="proj-1", recent_limit=2
    )

    assert context["peer_id"] == "user-1"
    assert context["project_id"] == "proj-1"
    assert isinstance(context["representation_text"], str)
    assert len(context["representation_text"]) > 0
    assert context["evidence_count"] == 1
    assert context["model"] == "heuristic"
    # recent_limit=2 → 2 most recent memories.
    assert len(context["recent_memories"]) == 2, (
        f"expected 2 recent memories, got {len(context['recent_memories'])}"
    )


# ---------------------------------------------------------------------------
# Test 5: per-project scoping — same peer_id, different project_ids
# ---------------------------------------------------------------------------


async def test_peer_models_isolated_per_project(
    fast_temp_db: AsyncGenerator,
) -> None:
    """The same peer_id in two different projects is two distinct rows."""
    db = fast_temp_db

    rep_a = await db.update_peer_model(peer_id="user-1", project_id="proj-A")
    rep_b = await db.update_peer_model(peer_id="user-1", project_id="proj-B")

    model_a = await db.get_peer_model(peer_id="user-1", project_id="proj-A")
    model_b = await db.get_peer_model(peer_id="user-1", project_id="proj-B")
    assert model_a is not None
    assert model_b is not None
    assert model_a["project_id"] == "proj-A"
    assert model_b["project_id"] == "proj-B"
    # Both should have evidence_count=1 (independent first updates).
    assert model_a["evidence_count"] == 1
    assert model_b["evidence_count"] == 1

    # Total rows in user_models: exactly 2 (one per project).
    total = db.conn.execute("SELECT COUNT(*) FROM user_models").fetchone()
    assert total is not None
    assert total[0] == 2, f"expected 2 rows, got {total[0]}"


# ---------------------------------------------------------------------------
# Test 6: peer_context for unknown peer returns empty structure
# ---------------------------------------------------------------------------


async def test_peer_context_for_unknown_peer_returns_empty(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Unknown peer: representation_text is empty, recent_memories is []."""
    db = fast_temp_db

    context = await db.peer_context(
        peer_id="nobody", project_id="proj-1", recent_limit=5
    )

    assert context["peer_id"] == "nobody"
    assert context["project_id"] == "proj-1"
    assert context["representation_text"] == ""
    assert context["evidence_count"] == 0
    assert context["model"] == ""
    assert context["recent_memories"] == []


# ---------------------------------------------------------------------------
# Test 7: ACL note is preserved on the module docstring
# ---------------------------------------------------------------------------


def test_peer_modeling_acl_docstring_present() -> None:
    """The peer_modeling module documents the ACL contract.

    A regression in the docstring (e.g. someone removing the ACL note)
    is a security regression — peer_models is the only memory
    primitive that can leak a user's preferences if mis-served.
    The note is the cheap way to keep future contributors honest.
    """
    from session_buddy.memory import peer_modeling

    doc = peer_modeling.__doc__ or ""
    assert "peer_models:read" in doc, (
        "peer_modeling module docstring must document peer_models:read ACL"
    )
    assert "peer_models:write" in doc, (
        "peer_modeling module docstring must document peer_models:write ACL"
    )


# ---------------------------------------------------------------------------
# Test 8: peer_context only returns memories for the matching project
# ---------------------------------------------------------------------------


async def test_peer_context_filters_by_project(
    fast_temp_db: AsyncGenerator,
) -> None:
    """recent_memories only includes the matching project_id (no cross-leak)."""
    db = fast_temp_db

    await db.update_peer_model(peer_id="user-1", project_id="proj-A")
    await db.store_conversation(
        content="in-A",
        metadata={"project": "proj-A"},
        source_type="manual",
    )
    await db.store_conversation(
        content="in-B",
        metadata={"project": "proj-B"},
        source_type="manual",
    )

    context = await db.peer_context(
        peer_id="user-1", project_id="proj-A", recent_limit=10
    )

    # Only the proj-A memory should be in recent_memories.
    assert len(context["recent_memories"]) == 1
    assert "in-A" in context["recent_memories"][0]["content"]


# ---------------------------------------------------------------------------
# Test 9: model field reflects what the LLM/heuristic produced
# ---------------------------------------------------------------------------


async def test_update_peer_model_records_model_used(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``model`` is part of the row so consumers can tell heuristic vs LLM.

    The plan's LLM Cost Ceiling tracks per-call model attribution;
    the row's ``model`` column is the source of truth.
    """
    db = fast_temp_db

    await db.update_peer_model(
        peer_id="user-1",
        project_id="proj-1",
        model="heuristic",
    )

    model = await db.get_peer_model(peer_id="user-1", project_id="proj-1")
    assert model is not None
    assert model["model"] == "heuristic"

    # Second update with an LLM model name should overwrite the model.
    db.conn.execute(
        "UPDATE user_models SET last_updated = last_updated - INTERVAL (? || ' seconds') "
        "WHERE peer_id = ? AND project_id = ?",
        ["2", "user-1", "proj-1"],
    )
    await db.update_peer_model(
        peer_id="user-1",
        project_id="proj-1",
        model="minimax-M3-highspeed",
    )
    model2 = await db.get_peer_model(peer_id="user-1", project_id="proj-1")
    assert model2 is not None
    assert model2["model"] == "minimax-M3-highspeed", (
        "model should be updated when explicitly provided"
    )
    assert model2["evidence_count"] == 2


# ---------------------------------------------------------------------------
# Test 10: peer_context target_peer_id returns a second representation
# ---------------------------------------------------------------------------


async def test_peer_context_with_target_peer_id(
    fast_temp_db: AsyncGenerator,
) -> None:
    """When ``target_peer_id`` is set, the context also bundles
    that peer's representation (useful for agent-vs-user theory
    of mind).
    """
    db = fast_temp_db

    await db.update_peer_model(peer_id="user-1", project_id="proj-1")
    await db.update_peer_model(peer_id="agent-1", project_id="proj-1")

    context = await db.peer_context(
        peer_id="user-1",
        project_id="proj-1",
        target_peer_id="agent-1",
        recent_limit=5,
    )

    assert "target_peer" in context
    assert context["target_peer"] is not None
    assert context["target_peer"]["peer_id"] == "agent-1"
    assert context["target_peer"]["project_id"] == "proj-1"
    assert isinstance(
        context["target_peer"]["representation_text"], str
    )


# ---------------------------------------------------------------------------
# Test 11: peer_context target_peer_id with unknown target → None
# ---------------------------------------------------------------------------


async def test_peer_context_target_unknown_returns_none(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``target_peer`` is None when ``target_peer_id`` has no model."""
    db = fast_temp_db

    await db.update_peer_model(peer_id="user-1", project_id="proj-1")

    context = await db.peer_context(
        peer_id="user-1",
        project_id="proj-1",
        target_peer_id="unknown-agent",
        recent_limit=5,
    )

    assert context["target_peer"] is None


# ---------------------------------------------------------------------------
# Test 12: last_updated is close to "now" for a fresh upsert
# ---------------------------------------------------------------------------


async def test_fresh_update_sets_last_updated_recently(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``last_updated`` should be within a small window of ``datetime.now()``.

    DuckDB stores TIMESTAMP without timezone; we compare to naive
    ``datetime.now()`` to keep the delta small. A future change to
    TIMESTAMPTZ would switch this comparison to ``datetime.now(UTC)``.
    """
    from datetime import datetime

    db = fast_temp_db

    before = datetime.now()
    await db.update_peer_model(peer_id="user-1", project_id="proj-1")
    after = datetime.now()

    row = db.conn.execute(
        "SELECT last_updated FROM user_models "
        "WHERE peer_id = ? AND project_id = ?",
        ["user-1", "proj-1"],
    ).fetchone()
    assert row is not None
    ts = row[0]
    delta_before = (ts - before).total_seconds()
    delta_after = (after - ts).total_seconds()
    assert -1.0 <= delta_before <= 5.0, (
        f"last_updated too far before 'now': {delta_before}s"
    )
    assert -1.0 <= delta_after <= 5.0, (
        f"last_updated too far after 'now': {delta_after}s"
    )
