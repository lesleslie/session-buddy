"""Integration tests for Causal Memory Chains (Phase 1.5 #3).

The v2 rewire (Phase 0) split ``parent_id`` semantics into
``turn_parent_id`` (transcript pairing) and ``causal_parent_id``
(inferred chains). This feature adds a dedicated ``causal_links``
table that captures the inferred graph: a directed, weighted,
``link_origin``-tagged network of "A caused B" relationships
between memory rows.

The chain walker enforces a depth cap of 3 and is cycle-safe (a
visited set prevents infinite loops on A→B→A). Inference is
LLM-free per the plan's LLM Cost Ceiling (heuristic: same-project
co-occurrence + category overlap + time delta → evidence weight).

Each test uses ``fast_temp_db`` so the v2 schema (and the new
``causal_links`` table) is freshly created in a temp file.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from ulid import ULID


# ---------------------------------------------------------------------------
# Test 1: record_observed_link stores a direct link
# ---------------------------------------------------------------------------


async def test_record_observed_link_creates_row(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A direct transcript-pair link (origin=observed) is stored verbatim."""
    db = fast_temp_db

    from_id = await db.store_conversation(
        content="root memory",
        metadata={"project": "proj-1"},
        source_type="manual",
    )
    to_id = await db.store_conversation(
        content="child memory",
        metadata={"project": "proj-1"},
        source_type="manual",
    )

    link_id = await db.record_observed_link(
        from_id=from_id,
        to_id=to_id,
        link_type="led_to",
        evidence=0.95,
    )

    assert isinstance(link_id, str)
    assert len(link_id) > 0

    rows = db.conn.execute(
        """
        SELECT from_id, to_id, link_type, evidence, link_origin, depth
        FROM causal_links WHERE id = ?
        """,
        [link_id],
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == from_id
    assert row[1] == to_id
    assert row[2] == "led_to"
    assert abs(row[3] - 0.95) < 1e-6
    assert row[4] == "observed"
    assert row[5] == 1


# ---------------------------------------------------------------------------
# Test 2: observed link bumps last_evidence_at
# ---------------------------------------------------------------------------


async def test_record_observed_link_upserts_and_bumps_evidence(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Recording the same (from, to) twice updates evidence + timestamp.

    The Conscious Agent uses ``last_evidence_at`` to decide which links
    to prune. Bumping it on reuse keeps active links alive.
    """
    db = fast_temp_db

    from_id = await db.store_conversation(
        content="a", metadata={"project": "p"}, source_type="manual"
    )
    to_id = await db.store_conversation(
        content="b", metadata={"project": "p"}, source_type="manual"
    )

    first_id = await db.record_observed_link(
        from_id=from_id, to_id=to_id, link_type="led_to", evidence=0.8
    )
    first_ts = db.conn.execute(
        "SELECT last_evidence_at FROM causal_links WHERE id = ?", [first_id]
    ).fetchone()[0]

    # Backdate so we can verify the timestamp moves forward.
    db.conn.execute(
        "UPDATE causal_links SET last_evidence_at = last_evidence_at "
        "- INTERVAL (? || ' seconds') WHERE id = ?",
        ["5", first_id],
    )

    second_id = await db.record_observed_link(
        from_id=from_id, to_id=to_id, link_type="led_to", evidence=0.9
    )

    # Same row id (upsert) — the second call did NOT create a new row.
    assert second_id == first_id, (
        f"expected upsert, got distinct id {second_id!r} vs {first_id!r}"
    )

    row = db.conn.execute(
        "SELECT evidence, last_evidence_at FROM causal_links WHERE id = ?",
        [first_id],
    ).fetchone()
    assert abs(row[0] - 0.9) < 1e-6, f"evidence should be 0.9, got {row[0]}"
    assert row[1] > first_ts, "last_evidence_at should advance on re-record"


# ---------------------------------------------------------------------------
# Test 3: infer_causal_links finds recent same-project memos
# ---------------------------------------------------------------------------


async def test_infer_causal_links_finds_recent_same_project(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Heuristic: A (older) + B (newer, same project, same category) → link.

    Plan: LLM-free, heuristic inference based on co-occurrence +
    category overlap. Two memories in the same project written
    close in time with the same category should produce a link
    from the older to the newer with evidence > 0.5.
    """
    db = fast_temp_db

    a = await db.store_conversation(
        content="first thought about python",
        metadata={"project": "p1"},
        source_type="manual",
        category="context",
    )
    b = await db.store_conversation(
        content="second thought about python",
        metadata={"project": "p1"},
        source_type="manual",
        category="context",
    )

    inferred = await db.infer_causal_links_for(memory_id=b)

    # At least one inferred link should land on ``a`` (the only
    # prior memory in the same project).
    assert any(link["from_id"] == a for link in inferred), (
        f"expected a→b inferred link, got {inferred!r}"
    )
    # And the link should be marked as inferred (not observed).
    matched = next(l for l in inferred if l["from_id"] == a)
    assert matched["link_origin"] == "inferred"
    assert matched["evidence"] > 0.5
    assert matched["to_id"] == b


# ---------------------------------------------------------------------------
# Test 4: cross-project memories do NOT link
# ---------------------------------------------------------------------------


async def test_inference_does_not_cross_projects(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Inference is per-project: a memory in proj-A cannot be caused
    by a memory in proj-B. This is the same scoping guarantee as
    the peer model — project is the implicit namespace.
    """
    db = fast_temp_db

    a = await db.store_conversation(
        content="in proj-A",
        metadata={"project": "proj-A"},
        source_type="manual",
        category="context",
    )
    b = await db.store_conversation(
        content="in proj-B",
        metadata={"project": "proj-B"},
        source_type="manual",
        category="context",
    )

    inferred = await db.infer_causal_links_for(memory_id=b)

    assert not any(link["from_id"] == a for link in inferred), (
        f"cross-project inference should not happen, got {inferred!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: causal_chain walks a 3-link chain with origin tags
# ---------------------------------------------------------------------------


async def test_causal_chain_walks_with_depth_cap(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A 3-link chain (A→B→C→D) walked from A returns B, C (cap=2)."""
    db = fast_temp_db

    a = await db.store_conversation(
        content="A", metadata={"project": "p"}, source_type="manual"
    )
    b = await db.store_conversation(
        content="B", metadata={"project": "p"}, source_type="manual"
    )
    c = await db.store_conversation(
        content="C", metadata={"project": "p"}, source_type="manual"
    )
    d = await db.store_conversation(
        content="D", metadata={"project": "p"}, source_type="manual"
    )

    await db.record_observed_link(a, b, "led_to", 0.9)
    await db.record_observed_link(b, c, "led_to", 0.9)
    await db.record_observed_link(c, d, "led_to", 0.9)

    chain = await db.causal_chain(start_id=a, max_depth=2)

    # BFS with depth=2:  A→B (depth 1), A→B→C (depth 2). NOT C→D.
    walked_ids = {edge["to_id"] for edge in chain}
    assert b in walked_ids, f"depth=1: B should be in chain, got {chain!r}"
    assert c in walked_ids, f"depth=2: C should be in chain, got {chain!r}"
    assert d not in walked_ids, (
        f"depth=2: D should NOT be in chain (3 hops away), got {chain!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: causal_chain is cycle-safe
# ---------------------------------------------------------------------------


async def test_causal_chain_cycle_safe(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A→B→A must terminate (visited set, not infinite loop).

    Cycles in real causal graphs are rare but possible (e.g. two
    memories reinforcing each other). The walker must terminate.
    """
    db = fast_temp_db

    a = await db.store_conversation(
        content="A", metadata={"project": "p"}, source_type="manual"
    )
    b = await db.store_conversation(
        content="B", metadata={"project": "p"}, source_type="manual"
    )

    await db.record_observed_link(a, b, "led_to", 0.9)
    await db.record_observed_link(b, a, "led_to", 0.9)

    # If the walker were cycle-naive, this would hang or recurse forever.
    chain = await db.causal_chain(start_id=a, max_depth=5)

    # Visited-set guarantees we only touch A and B once each.
    walked_ids = {edge["to_id"] for edge in chain}
    assert walked_ids <= {a, b}, f"cycle-safe walk, got {chain!r}"


# ---------------------------------------------------------------------------
# Test 7: prune removes old links, returns count
# ---------------------------------------------------------------------------


async def test_prune_causal_links_older_than(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Pruning links with stale ``last_evidence_at`` returns the count."""
    db = fast_temp_db

    from_id = await db.store_conversation(
        content="x", metadata={"project": "p"}, source_type="manual"
    )
    to_id = await db.store_conversation(
        content="y", metadata={"project": "p"}, source_type="manual"
    )

    link_id = await db.record_observed_link(from_id, to_id, "led_to", 0.9)

    # Backdate the link to 100 days ago.
    db.conn.execute(
        "UPDATE causal_links SET last_evidence_at = now() - INTERVAL '100 days' "
        "WHERE id = ?",
        [link_id],
    )

    pruned = await db.prune_causal_links_older_than(days=90)
    assert pruned == 1, f"expected 1 pruned link, got {pruned}"

    # Row should be gone.
    remaining = db.conn.execute(
        "SELECT COUNT(*) FROM causal_links WHERE id = ?", [link_id]
    ).fetchone()[0]
    assert remaining == 0


# ---------------------------------------------------------------------------
# Test 8: chain walk returns origin tag per edge
# ---------------------------------------------------------------------------


async def test_chain_walk_returns_link_origin(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Each walked edge exposes its ``link_origin`` so consumers can
    distinguish observed ground-truth from inferred guesses.
    """
    db = fast_temp_db

    a = await db.store_conversation(
        content="A", metadata={"project": "p"}, source_type="manual"
    )
    b = await db.store_conversation(
        content="B", metadata={"project": "p"}, source_type="manual"
    )

    await db.record_observed_link(a, b, "led_to", 0.9)

    chain = await db.causal_chain(start_id=a, max_depth=1)

    assert len(chain) == 1
    assert chain[0]["link_origin"] == "observed"
    assert chain[0]["from_id"] == a
    assert chain[0]["to_id"] == b


# ---------------------------------------------------------------------------
# Test 9: causal.py is LLM-free
# ---------------------------------------------------------------------------


def test_causal_module_has_no_llm_imports() -> None:
    """The plan's LLM Cost Ceiling says causal inference is LLM-free
    (heuristic). A future regression that imports an LLM client
    here would burn the budget. Pin it with a regression test.
    """
    import session_buddy.memory.causal as causal

    source = open(causal.__file__).read()
    forbidden = [
        "openai",
        "anthropic",
        "minimax",
        "ChatCompletion",
        "claude",
        "gpt-",
    ]
    for needle in forbidden:
        assert needle not in source, (
            f"causal.py must not import or reference '{needle}' "
            f"(LLM Cost Ceiling says causal inference is heuristic)"
        )


# ---------------------------------------------------------------------------
# Test 10: chain walk on isolated start_id returns empty list
# ---------------------------------------------------------------------------


async def test_chain_walk_on_isolated_start(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A memory with no incoming or outgoing links produces an empty chain."""
    db = fast_temp_db

    a = await db.store_conversation(
        content="alone", metadata={"project": "p"}, source_type="manual"
    )

    chain = await db.causal_chain(start_id=a, max_depth=3)

    assert chain == [], f"expected empty chain for isolated start, got {chain!r}"


# ---------------------------------------------------------------------------
# Test 11: high-evidence inference persists; low-evidence does not
# ---------------------------------------------------------------------------


async def test_inference_filters_low_evidence(
    fast_temp_db: AsyncGenerator,
) -> None:
    """The plan's quality floor is ``evidence > 0.5``. Inference that
    produces an evidence score <= 0.5 is NOT persisted.

    We test the heuristic function directly (rather than through the
    full DB-backed inference) to avoid a DuckDB 1.5.3 bug triggered
    by ``UPDATE conversations_v2`` (the WriteAheadLog replay crash
    also affects the cascade tests — see ``test_delete_conversation_cascade``
    for the upstream bug report).
    """
    from session_buddy.memory.causal import (
        EVIDENCE_FLOOR,
        evidence_weight,
    )

    # Same category, 1 second apart → high evidence.
    high = evidence_weight("context", "context", 1.0)
    assert high > EVIDENCE_FLOOR, (
        f"same-category close-in-time should be above floor, got {high}"
    )

    # Different categories, far apart in time → low evidence.
    low = evidence_weight("preferences", "skills", 3600.0)
    assert low <= EVIDENCE_FLOOR, (
        f"different-category far-apart should be at or below floor, got {low}"
    )

    # One category, far apart in time → low evidence (time decay).
    low_time = evidence_weight("context", "context", 7200.0)
    assert low_time <= EVIDENCE_FLOOR, (
        f"same-category but 2h apart should be at or below floor, got {low_time}"
    )

    # Either category None → 0.0 (filtered).
    none_cat = evidence_weight(None, "context", 1.0)
    assert none_cat == 0.0
    assert none_cat <= EVIDENCE_FLOOR


# ---------------------------------------------------------------------------
# Test 12: self-link attempt is rejected
# ---------------------------------------------------------------------------


async def test_self_link_rejected(
    fast_temp_db: AsyncGenerator,
) -> None:
    """A→A is a malformed causal link. Recording it must raise."""
    db = fast_temp_db

    a = await db.store_conversation(
        content="x", metadata={"project": "p"}, source_type="manual"
    )

    with pytest.raises(ValueError, match="self"):
        await db.record_observed_link(
            from_id=a, to_id=a, link_type="led_to", evidence=0.9
        )
