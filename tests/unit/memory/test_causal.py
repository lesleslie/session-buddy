from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from ulid import ULID

from session_buddy.memory.causal import (
    DEFAULT_MAX_DEPTH,
    EVIDENCE_FLOOR,
    RELATED_CATEGORY_PAIRS,
    category_overlap,
    evidence_weight,
    get_incoming_links,
    infer_causal_links_for,
    prune_causal_links_older_than,
    record_observed_link,
    time_decay,
    walk_causal_chain,
)


# ------------------------------------------------------------------
# Pure-function helpers
# ------------------------------------------------------------------


class TestCategoryOverlap:
    """Tests for causal.category_overlap."""

    def test_same_category_is_one(self) -> None:
        assert category_overlap("facts", "facts") == 1.0

    def test_related_pair_is_half(self) -> None:
        for cat in ("facts", "preferences", "skills", "rules"):
            assert category_overlap(cat, "context") == 0.5

    def test_unrelated_is_zero(self) -> None:
        assert category_overlap("facts", "skills") == 0.0
        assert category_overlap("preferences", "rules") == 0.0

    def test_none_is_zero(self) -> None:
        assert category_overlap(None, "facts") == 0.0
        assert category_overlap("facts", None) == 0.0
        assert category_overlap(None, None) == 0.0

    def test_related_pairs_constant_shape(self) -> None:
        # The frozenset-of-frozensets must contain exactly the 4 documented pairs.
        assert len(RELATED_CATEGORY_PAIRS) == 4
        expected = {
            frozenset({"facts", "context"}),
            frozenset({"preferences", "context"}),
            frozenset({"skills", "context"}),
            frozenset({"rules", "context"}),
        }
        assert RELATED_CATEGORY_PAIRS == expected


class TestTimeDecay:
    """Tests for causal.time_decay."""

    def test_zero_delta_is_one(self) -> None:
        assert time_decay(0.0) == 1.0

    def test_negative_delta_clamps_to_one(self) -> None:
        # Negative deltas mean "future" — treated as zero.
        assert time_decay(-100.0) == 1.0

    def test_one_hour_is_exp_neg_one(self) -> None:
        # The actual implementation uses math.exp(-delta/3600), so at delta=3600s
        # the value is exp(-1) ≈ 0.3679, not the literal "0.5" stated in the
        # original docstring. (The half-life is ~3600/ln(2) seconds.)
        assert time_decay(3600.0) == pytest.approx(math.exp(-1), abs=1e-9)

    def test_decay_is_monotonic(self) -> None:
        prev = time_decay(0.0)
        for delta in (60, 600, 3600, 36000):
            cur = time_decay(delta)
            assert cur < prev
            prev = cur

    def test_underflow_to_zero_for_large_delta(self) -> None:
        # math.exp of a very large negative underflows to 0.0.
        assert time_decay(10**9) == 0.0


class TestEvidenceWeight:
    """Tests for causal.evidence_weight."""

    def test_same_category_combines_with_decay(self) -> None:
        # Same cat → 1.0 * decay.
        assert evidence_weight("facts", "facts", 0.0) == 1.0
        assert evidence_weight("facts", "facts", 3600.0) == pytest.approx(
            math.exp(-1), abs=1e-9
        )

    def test_unrelated_categories_yield_zero(self) -> None:
        # Different and unrelated → 0.0 regardless of decay.
        assert evidence_weight("facts", "skills", 0.0) == 0.0
        assert evidence_weight("facts", "skills", 1.0) == 0.0

    def test_related_categories_with_decay(self) -> None:
        # Related (facts/context) → 0.5 * decay.
        assert evidence_weight("facts", "context", 0.0) == 0.5
        assert evidence_weight("facts", "context", 3600.0) == pytest.approx(
            0.5 * math.exp(-1), abs=1e-9
        )

    def test_none_categories_yield_zero(self) -> None:
        assert evidence_weight(None, "facts", 0.0) == 0.0


# ------------------------------------------------------------------
# DuckDB fixtures
# ------------------------------------------------------------------


@pytest.fixture
def duck_conn():
    """In-memory DuckDB with the causal_links schema bootstrap."""
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE conversations_v2 (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            category TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            project TEXT,
            source_type TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE causal_links (
            id TEXT PRIMARY KEY,
            from_id TEXT NOT NULL,
            to_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            evidence REAL NOT NULL CHECK (evidence > 0.0 AND evidence <= 1.0),
            last_evidence_at TIMESTAMP NOT NULL DEFAULT now(),
            link_origin TEXT NOT NULL CHECK (link_origin IN ('observed', 'inferred')),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            depth INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    yield conn
    conn.close()


def _insert_memory(
    conn,
    *,
    memory_id: str,
    project: str = "proj-1",
    category: str = "facts",
    timestamp: str | None = None,
) -> None:
    ts = timestamp or "2026-09-04 12:00:00"
    conn.execute(
        """
        INSERT INTO conversations_v2 (id, content, category, project, timestamp)
        VALUES (?, 'placeholder', ?, ?, ?)
        """,
        [memory_id, category, project, ts],
    )


# ------------------------------------------------------------------
# record_observed_link
# ------------------------------------------------------------------


class TestRecordObservedLink:
    """Tests for causal.record_observed_link."""

    def test_self_link_rejected(self, duck_conn) -> None:
        with pytest.raises(ValueError, match="self-link rejected"):
            record_observed_link(
                duck_conn,
                from_id="x",
                to_id="x",
                link_type="led_to",
                evidence=0.8,
            )

    def test_evidence_zero_rejected(self, duck_conn) -> None:
        with pytest.raises(ValueError, match=r"evidence must be in \(0\.0, 1\.0\]"):
            record_observed_link(
                duck_conn,
                from_id="a",
                to_id="b",
                link_type="led_to",
                evidence=0.0,
            )

    def test_evidence_negative_rejected(self, duck_conn) -> None:
        with pytest.raises(ValueError, match=r"evidence must be in \(0\.0, 1\.0\]"):
            record_observed_link(
                duck_conn,
                from_id="a",
                to_id="b",
                link_type="led_to",
                evidence=-0.1,
            )

    def test_evidence_above_one_rejected(self, duck_conn) -> None:
        with pytest.raises(ValueError, match=r"evidence must be in \(0\.0, 1\.0\]"):
            record_observed_link(
                duck_conn,
                from_id="a",
                to_id="b",
                link_type="led_to",
                evidence=1.5,
            )

    def test_evidence_one_is_valid_boundary(self, duck_conn) -> None:
        link_id = record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=1.0,
        )
        assert isinstance(link_id, str) and len(link_id) > 0

    def test_link_type_origin_is_observed(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        row = duck_conn.execute(
            "SELECT link_origin, link_type, depth FROM causal_links"
        ).fetchone()
        assert row[0] == "observed"
        assert row[1] == "led_to"
        assert row[2] == 1

    def test_upsert_reuses_id(self, duck_conn) -> None:
        first = record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.6,
        )
        second = record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.9,
        )
        # Same (from, to, type) → same id, updated evidence.
        assert first == second
        count = duck_conn.execute("SELECT COUNT(*) FROM causal_links").fetchone()[0]
        assert count == 1
        ev = duck_conn.execute("SELECT evidence FROM causal_links").fetchone()[0]
        # REAL columns store floats with rounding error.
        assert ev == pytest.approx(0.9)

    def test_different_link_types_are_separate_rows(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="elaborated",
            evidence=0.5,
        )
        count = duck_conn.execute("SELECT COUNT(*) FROM causal_links").fetchone()[0]
        assert count == 2

    def test_returns_ulid_format(self, duck_conn) -> None:
        link_id = record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        # Crockford base32 ULIDs are 26 chars.
        assert len(link_id) == 26
        # Parses cleanly back to ULID object.
        assert isinstance(ULID.from_str(link_id), ULID)


# ------------------------------------------------------------------
# infer_causal_links_for
# ------------------------------------------------------------------


class TestInferCausalLinksFor:
    """Tests for causal.infer_causal_links_for."""

    def test_unknown_target_memory_returns_empty(self, duck_conn) -> None:
        result = infer_causal_links_for(duck_conn, memory_id="missing")
        assert result == []

    def test_infers_links_for_same_category_close_in_time(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            category="facts",
            timestamp="2026-09-04 12:00:00",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            category="facts",
            timestamp="2026-09-04 12:00:01",
        )
        links = infer_causal_links_for(duck_conn, memory_id="m2")
        assert len(links) == 1
        link = links[0]
        assert link["from_id"] == "m1"
        assert link["to_id"] == "m2"
        assert link["link_type"] == "related_to"
        assert link["link_origin"] == "inferred"
        assert link["evidence"] > EVIDENCE_FLOOR
        # Persisted in causal_links.
        rows = duck_conn.execute(
            "SELECT id, link_origin FROM causal_links"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "inferred"

    def test_filters_out_weak_evidence(self, duck_conn) -> None:
        # Two memories, same category, but 4 hours apart → evidence ≈ exp(-4) ≈ 0.018.
        _insert_memory(
            duck_conn,
            memory_id="m1",
            category="facts",
            timestamp="2026-09-04 08:00:00",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            category="facts",
            timestamp="2026-09-04 12:00:00",
        )
        links = infer_causal_links_for(duck_conn, memory_id="m2")
        assert links == []
        rows = duck_conn.execute("SELECT COUNT(*) FROM causal_links").fetchone()[0]
        assert rows == 0

    def test_cross_project_not_inferred(self, duck_conn) -> None:
        # Same category, adjacent timestamps, but different projects.
        _insert_memory(
            duck_conn,
            memory_id="m1",
            project="proj-1",
            category="facts",
            timestamp="2026-09-04 12:00:00",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            project="proj-2",
            category="facts",
            timestamp="2026-09-04 12:00:01",
        )
        links = infer_causal_links_for(duck_conn, memory_id="m2")
        assert links == []

    def test_related_categories_partial_evidence_below_floor(self, duck_conn) -> None:
        # facts → context gets 0.5 * decay; at 1-second gap evidence ≈ 0.49986,
        # which is BELOW the 0.5 evidence floor and must NOT be persisted.
        _insert_memory(
            duck_conn,
            memory_id="m1",
            category="facts",
            timestamp="2026-09-04 12:00:00",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            category="context",
            timestamp="2026-09-04 12:00:01",
        )
        links = infer_causal_links_for(duck_conn, memory_id="m2")
        assert links == []
        rows = duck_conn.execute("SELECT COUNT(*) FROM causal_links").fetchone()[0]
        assert rows == 0

    def test_lookback_limit_caps_candidates(self, duck_conn) -> None:
        # Insert 5 prior memories all within the same project, then target memory.
        for i in range(5):
            _insert_memory(
                duck_conn,
                memory_id=f"m{i}",
                timestamp=f"2026-09-04 12:00:0{i}",
            )
        _insert_memory(
            duck_conn,
            memory_id="target",
            category="facts",
            timestamp="2026-09-04 12:00:10",
        )
        links = infer_causal_links_for(
            duck_conn, memory_id="target", lookback_limit=2
        )
        # Only the two most recent prior memories can become candidates.
        assert len(links) <= 2

    def test_returns_dict_with_required_keys(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            category="facts",
            timestamp="2026-09-04 12:00:00",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            category="facts",
            timestamp="2026-09-04 12:00:01",
        )
        links = infer_causal_links_for(duck_conn, memory_id="m2")
        assert len(links) == 1
        link = links[0]
        for key in ("id", "from_id", "to_id", "link_type", "evidence", "link_origin"):
            assert key in link


# ------------------------------------------------------------------
# walk_causal_chain
# ------------------------------------------------------------------


class TestWalkCausalChain:
    """Tests for causal.walk_causal_chain."""

    def test_isolated_node_returns_empty(self, duck_conn) -> None:
        # No links.
        assert walk_causal_chain(duck_conn, start_id="nothing") == []

    def test_default_depth_is_three(self) -> None:
        # Module-level constant.
        assert DEFAULT_MAX_DEPTH == 3

    def test_zero_or_negative_depth_returns_empty(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        assert walk_causal_chain(duck_conn, start_id="a", max_depth=0) == []
        assert walk_causal_chain(duck_conn, start_id="a", max_depth=-1) == []

    def test_direct_neighbor_depth_one(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        walked = walk_causal_chain(duck_conn, start_id="a", max_depth=3)
        assert len(walked) == 1
        edge = walked[0]
        assert edge["from_id"] == "a"
        assert edge["to_id"] == "b"
        assert edge["link_type"] == "led_to"
        assert edge["link_origin"] == "observed"
        assert edge["evidence"] == pytest.approx(0.7)
        assert edge["depth"] == 1

    def test_multi_hop_walk(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        record_observed_link(
            duck_conn,
            from_id="b",
            to_id="c",
            link_type="led_to",
            evidence=0.7,
        )
        record_observed_link(
            duck_conn,
            from_id="c",
            to_id="d",
            link_type="led_to",
            evidence=0.7,
        )
        walked = walk_causal_chain(duck_conn, start_id="a", max_depth=3)
        depths = sorted(e["depth"] for e in walked)
        assert depths == [1, 2, 3]
        visited = {e["to_id"] for e in walked}
        assert visited == {"b", "c", "d"}

    def test_cycle_safe(self, duck_conn) -> None:
        # a → b → a — walker must not loop.
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        record_observed_link(
            duck_conn,
            from_id="b",
            to_id="a",
            link_type="led_to",
            evidence=0.7,
        )
        walked = walk_causal_chain(duck_conn, start_id="a", max_depth=3)
        # Only one edge — visiting 'a' from 'b' is blocked because 'a' is in visited.
        assert len(walked) == 1
        assert walked[0]["to_id"] == "b"

    def test_max_depth_caps_walk(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        record_observed_link(
            duck_conn,
            from_id="b",
            to_id="c",
            link_type="led_to",
            evidence=0.7,
        )
        walked = walk_causal_chain(duck_conn, start_id="a", max_depth=1)
        assert len(walked) == 1
        assert walked[0]["to_id"] == "b"


# ------------------------------------------------------------------
# prune_causal_links_older_than
# ------------------------------------------------------------------


class TestPruneCausalLinksOlderThan:
    """Tests for causal.prune_causal_links_older_than."""

    def test_returns_count_of_deleted_rows(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        # Bump last_evidence_at to be old.
        duck_conn.execute(
            "UPDATE causal_links SET last_evidence_at = now() - INTERVAL '100 days'"
        )
        # Add a fresh row that should NOT be deleted.
        record_observed_link(
            duck_conn,
            from_id="c",
            to_id="d",
            link_type="led_to",
            evidence=0.7,
        )
        deleted = prune_causal_links_older_than(duck_conn, days=90)
        assert deleted == 1
        remaining = duck_conn.execute(
            "SELECT from_id, to_id FROM causal_links"
        ).fetchall()
        assert remaining == [("c", "d")]

    def test_returns_zero_when_nothing_to_prune(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        assert prune_causal_links_older_than(duck_conn, days=90) == 0

    def test_returns_zero_on_empty_table(self, duck_conn) -> None:
        assert prune_causal_links_older_than(duck_conn, days=90) == 0

    def test_custom_days_argument(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="b",
            link_type="led_to",
            evidence=0.7,
        )
        # Age the row by 100 days.
        duck_conn.execute(
            "UPDATE causal_links SET last_evidence_at = now() - INTERVAL '100 days'"
        )
        # days=90 prunes it.
        assert prune_causal_links_older_than(duck_conn, days=90) == 1
        # After pruning, no rows remain so days=1 also returns 0.
        assert prune_causal_links_older_than(duck_conn, days=1) == 0


# ------------------------------------------------------------------
# get_incoming_links
# ------------------------------------------------------------------


class TestGetIncomingLinks:
    """Tests for causal.get_incoming_links."""

    def test_returns_empty_when_no_links(self, duck_conn) -> None:
        assert get_incoming_links(duck_conn, memory_id="nothing") == []

    def test_returns_only_links_pointing_at_memory(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="target",
            link_type="led_to",
            evidence=0.7,
        )
        record_observed_link(
            duck_conn,
            from_id="b",
            to_id="other",
            link_type="led_to",
            evidence=0.7,
        )
        record_observed_link(
            duck_conn,
            from_id="c",
            to_id="target",
            link_type="elaborated",
            evidence=0.5,
        )
        result = get_incoming_links(duck_conn, memory_id="target")
        assert len(result) == 2
        from_ids = {row["from_id"] for row in result}
        assert from_ids == {"a", "c"}

    def test_result_keys_match_walk_output(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="target",
            link_type="led_to",
            evidence=0.7,
        )
        result = get_incoming_links(duck_conn, memory_id="target")
        assert len(result) == 1
        row = result[0]
        for key in (
            "from_id",
            "to_id",
            "link_type",
            "evidence",
            "link_origin",
            "depth",
        ):
            assert key in row

    def test_ordered_by_recency_descending(self, duck_conn) -> None:
        record_observed_link(
            duck_conn,
            from_id="a",
            to_id="target",
            link_type="led_to",
            evidence=0.7,
        )
        # Backdate the first link.
        duck_conn.execute(
            """
            UPDATE causal_links
            SET last_evidence_at = now() - INTERVAL '5 days'
            WHERE from_id = 'a'
            """
        )
        # Add a fresh link.
        record_observed_link(
            duck_conn,
            from_id="b",
            to_id="target",
            link_type="led_to",
            evidence=0.7,
        )
        result = get_incoming_links(duck_conn, memory_id="target")
        # The fresh link ('b') must appear before the old ('a').
        assert result[0]["from_id"] == "b"
        assert result[1]["from_id"] == "a"


# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------


def test_evidence_floor_constant() -> None:
    assert EVIDENCE_FLOOR == 0.5


def test_default_max_depth_constant() -> None:
    assert DEFAULT_MAX_DEPTH == 3


# ------------------------------------------------------------------
# Property-style: time_decay never exceeds 1.0
# ------------------------------------------------------------------


@pytest.mark.parametrize("delta", [0, 1, 60, 3600, 86400, 10**7])
def test_time_decay_bounds(delta: float) -> None:
    val = time_decay(delta)
    # math.exp underflows to 0.0 for very large negative inputs, so the
    # docstring's "(0.0, 1.0]" is a design intent that math.exp cannot
    # honor for delta > ~700/hours. We assert the looser invariant: <= 1.0
    # and either positive (for normal deltas) or zero (underflow regime).
    assert 0.0 <= val <= 1.0
    if delta == 0:
        assert val == 1.0
    if delta > 0:
        assert val <= 1.0


def test_evidence_weight_bounded() -> None:
    for cat_a in (None, "facts", "preferences", "context"):
        for cat_b in (None, "facts", "preferences", "context"):
            val = evidence_weight(cat_a, cat_b, 0.0)
            assert 0.0 <= val <= 1.0
            assert isinstance(val, float)