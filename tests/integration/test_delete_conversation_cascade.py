"""Integration tests for application-level cascade delete (R1).

DuckDB does NOT support ``ON DELETE CASCADE`` on FOREIGN KEY constraints,
so the v2 schema relies on application-level cascade for any operation
that removes a row from ``conversations_v2``.

There are five child tables that hold a reference to a conversation
(either directly, or transitively via ``memory_entities``):

* ``memory_provenance``  → direct FK to ``conversations_v2.id``
* ``memory_entities``    → direct FK to ``conversations_v2.id``
* ``memory_promotions``  → direct FK to ``conversations_v2.id``
* ``memory_access_log``  → direct FK to ``conversations_v2.id``
* ``memory_relationships`` → 2nd-level: FK to ``memory_entities.id``

This file pins the cascade contract end-to-end through the public
``delete_conversation`` API:

* Direct children are removed when the parent is deleted.
* 2nd-level children (``memory_relationships``) are removed via the
  entity chain BEFORE the entities themselves are removed.
* The operation is idempotent — calling it twice or on a missing id
  returns 0 and does not raise.
* The return value is the number of ``conversations_v2`` rows actually
  removed (0 or 1).

Each test uses the ``fast_temp_db`` fixture so the v2 schema is created
freshly in a temp file.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from ulid import ULID


# ---------------------------------------------------------------------------
# Test 1: delete cascades to memory_provenance
# ---------------------------------------------------------------------------


async def test_delete_cascades_to_provenance(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``memory_provenance`` row is removed when its parent is deleted."""
    db = fast_temp_db
    memory_id = await db.store_conversation(
        content="test",
        metadata={"source_session": "sess-1"},
        source_type="claude_code",
    )

    # Sanity: store_conversation should have created the provenance row.
    pre = db.conn.execute(
        "SELECT COUNT(*) FROM memory_provenance WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert pre == 1, f"expected 1 provenance row pre-delete, got {pre}"

    deleted = await db.delete_conversation(memory_id)
    assert deleted == 1, f"expected delete_conversation to return 1, got {deleted}"

    post_prov = db.conn.execute(
        "SELECT COUNT(*) FROM memory_provenance WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert post_prov == 0, (
        f"expected 0 provenance rows post-delete, got {post_prov}"
    )

    post_conv = db.conn.execute(
        "SELECT COUNT(*) FROM conversations_v2 WHERE id = ?",
        [memory_id],
    ).fetchone()[0]
    assert post_conv == 0, (
        f"expected 0 conversations_v2 rows post-delete, got {post_conv}"
    )


# ---------------------------------------------------------------------------
# Test 2: delete cascades to memory_entities
# ---------------------------------------------------------------------------


async def test_delete_cascades_to_memory_entities(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``memory_entities`` row referencing the memory is removed."""
    db = fast_temp_db
    memory_id = await db.store_conversation(
        content="entity test",
        source_type="manual",
    )

    # Manually insert an entity referencing this memory.
    entity_id = str(ULID())
    db.conn.execute(
        """
        INSERT INTO memory_entities
            (id, memory_id, entity_type, entity_value, confidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        [entity_id, memory_id, "technology", "python", 0.9],
    )

    pre = db.conn.execute(
        "SELECT COUNT(*) FROM memory_entities WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert pre == 1, f"expected 1 entity row pre-delete, got {pre}"

    await db.delete_conversation(memory_id)

    post = db.conn.execute(
        "SELECT COUNT(*) FROM memory_entities WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert post == 0, f"expected 0 entity rows post-delete, got {post}"


# ---------------------------------------------------------------------------
# Test 3: delete cascades to memory_promotions
# ---------------------------------------------------------------------------


async def test_delete_cascades_to_memory_promotions(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``memory_promotions`` row referencing the memory is removed."""
    db = fast_temp_db
    memory_id = await db.store_conversation(
        content="promotion test",
        source_type="manual",
    )

    promotion_id = str(ULID())
    db.conn.execute(
        """
        INSERT INTO memory_promotions
            (id, memory_id, from_tier, to_tier, reason, priority_score)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            promotion_id,
            memory_id,
            "short_term",
            "long_term",
            "test promotion",
            0.7,
        ],
    )

    pre = db.conn.execute(
        "SELECT COUNT(*) FROM memory_promotions WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert pre == 1, f"expected 1 promotion row pre-delete, got {pre}"

    await db.delete_conversation(memory_id)

    post = db.conn.execute(
        "SELECT COUNT(*) FROM memory_promotions WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert post == 0, f"expected 0 promotion rows post-delete, got {post}"


# ---------------------------------------------------------------------------
# Test 4: delete cascades to memory_access_log
# ---------------------------------------------------------------------------


async def test_delete_cascades_to_memory_access_log(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``memory_access_log`` rows referencing the memory are removed.

    The cascade is conservative: it removes instrumentation rows too.
    An ``access_log`` row with no parent memory is meaningless once
    the memory itself is gone — keeping it would leak dead-pointer
    data into the Conscious Agent analysis loop.
    """
    db = fast_temp_db
    memory_id = await db.store_conversation(
        content="access log test",
        source_type="manual",
    )

    # Manually insert a few access log rows referencing the memory.
    for access_type in ("search", "retrieve", "promote"):
        db.conn.execute(
            """
            INSERT INTO memory_access_log
                (id, memory_id, access_type, query_text)
            VALUES (?, ?, ?, ?)
            """,
            [str(ULID()), memory_id, access_type, "test query"],
        )

    pre = db.conn.execute(
        "SELECT COUNT(*) FROM memory_access_log WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert pre == 3, f"expected 3 access log rows pre-delete, got {pre}"

    await db.delete_conversation(memory_id)

    post = db.conn.execute(
        "SELECT COUNT(*) FROM memory_access_log WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert post == 0, f"expected 0 access log rows post-delete, got {post}"


# ---------------------------------------------------------------------------
# Test 5: delete cascades to memory_relationships via entities
# ---------------------------------------------------------------------------


async def test_delete_cascades_to_relationships_via_entities(
    fast_temp_db: AsyncGenerator,
) -> None:
    """``memory_relationships`` are removed BEFORE their entity rows.

    A self-referencing relationship is the simplest way to exercise
    the 2nd-level cascade: an entity A belonging to the memory, and
    a relationship A→A. Both must be gone after the cascade.
    """
    db = fast_temp_db
    memory_id = await db.store_conversation(
        content="relationship test",
        source_type="manual",
    )

    entity_id = str(ULID())
    db.conn.execute(
        """
        INSERT INTO memory_entities
            (id, memory_id, entity_type, entity_value, confidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        [entity_id, memory_id, "concept", "self_ref", 1.0],
    )

    relationship_id = str(ULID())
    db.conn.execute(
        """
        INSERT INTO memory_relationships
            (id, from_entity_id, to_entity_id, relationship_type, strength)
        VALUES (?, ?, ?, ?, ?)
        """,
        [relationship_id, entity_id, entity_id, "related_to", 1.0],
    )

    pre_rels = db.conn.execute(
        """
        SELECT COUNT(*) FROM memory_relationships
        WHERE from_entity_id = ? OR to_entity_id = ?
        """,
        [entity_id, entity_id],
    ).fetchone()[0]
    assert pre_rels == 1, f"expected 1 relationship pre-delete, got {pre_rels}"

    pre_ent = db.conn.execute(
        "SELECT COUNT(*) FROM memory_entities WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert pre_ent == 1, f"expected 1 entity pre-delete, got {pre_ent}"

    await db.delete_conversation(memory_id)

    post_rels = db.conn.execute(
        """
        SELECT COUNT(*) FROM memory_relationships
        WHERE from_entity_id = ? OR to_entity_id = ?
        """,
        [entity_id, entity_id],
    ).fetchone()[0]
    assert post_rels == 0, (
        f"expected 0 relationships post-delete, got {post_rels}"
    )

    post_ent = db.conn.execute(
        "SELECT COUNT(*) FROM memory_entities WHERE memory_id = ?",
        [memory_id],
    ).fetchone()[0]
    assert post_ent == 0, f"expected 0 entities post-delete, got {post_ent}"


# ---------------------------------------------------------------------------
# Test 6: delete is idempotent for missing memory
# ---------------------------------------------------------------------------


async def test_delete_is_idempotent_for_missing_memory(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Deleting a non-existent memory returns 0 and does not raise."""
    db = fast_temp_db

    # Should not raise.
    result = await db.delete_conversation("NONEXISTENT_ULID_01")

    assert result == 0, (
        f"expected delete_conversation on missing id to return 0, got {result}"
    )


# ---------------------------------------------------------------------------
# Test 7: delete returns count
# ---------------------------------------------------------------------------


async def test_delete_returns_count(
    fast_temp_db: AsyncGenerator,
) -> None:
    """First call returns 1, repeat call returns 0 (idempotent)."""
    db = fast_temp_db
    memory_id = await db.store_conversation(
        content="count test",
        source_type="manual",
    )

    first = await db.delete_conversation(memory_id)
    assert first == 1, f"first delete should return 1, got {first}"

    second = await db.delete_conversation(memory_id)
    assert second == 0, f"second delete should return 0 (idempotent), got {second}"
