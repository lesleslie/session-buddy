"""Causal Memory Chains (Phase 1.5 Feature #3).

A directed graph over ``conversations_v2`` rows where ``from_id`` is
the (probable) cause of ``to_id``. Two flavors of link:

- ``observed``: a ground-truth link from a transcript ``parentUuid``
  chain, a manual note, or a tool that asserts "A caused B".
- ``inferred``: a heuristic guess from co-occurrence in the same
  project with category overlap and time decay.

## LLM-free by design

The plan's LLM Cost Ceiling pins causal inference at 0 — the
heuristic is cheap enough to run on every write, so we don't
trade inference quality for cost. A regression test
(``test_causal_module_has_no_llm_imports``) pins this; if a future
contributor adds an LLM call here, the test fails.

## Heuristic evidence weight

``evidence = category_overlap * time_decay``

- ``category_overlap`` ∈ {0.0, 1.0}: 1.0 if same category, else
  a partial score from a category-compatibility table.
- ``time_decay`` = ``exp(-Δseconds / 3600)`` (half-life of ~1 hour).

The 0.5 floor is the plan's quality gate. Same category, 1 second
apart → evidence ≈ 1.0. Different categories 1 hour apart → ≈ 0.0.

## Cycle-safe walk

``walk_causal_chain`` is BFS with a visited set. The depth cap of
3 (per the plan) is enforced; A→B→A terminates immediately.
"""

from __future__ import annotations

import logging
import math
import typing as t

if t.TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

from ulid import ULID

logger = logging.getLogger(__name__)


# Quality floor per the plan: ``evidence > 0.5``. We do not persist
# inferred links at or below this threshold.
EVIDENCE_FLOOR: float = 0.5

# Depth cap per the plan: walkers must not recurse past depth 3.
DEFAULT_MAX_DEPTH: int = 3

# Categories that imply related (but not identical) content.
# Used to give a partial ``category_overlap`` score (0.5) instead
# of 0.0 when categories differ but are conceptually adjacent.
RELATED_CATEGORY_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"facts", "context"}),
        frozenset({"preferences", "context"}),
        frozenset({"skills", "context"}),
        frozenset({"rules", "context"}),
    }
)


def category_overlap(cat_a: str | None, cat_b: str | None) -> float:
    """Return 0.0-1.0 score for category similarity.

    - Same category: 1.0
    - Adjacent category (RELATED_CATEGORY_PAIRS): 0.5
    - Otherwise: 0.0
    - Either None: 0.0
    """
    if cat_a is None or cat_b is None:
        return 0.0
    if cat_a == cat_b:
        return 1.0
    if frozenset({cat_a, cat_b}) in RELATED_CATEGORY_PAIRS:
        return 0.5
    return 0.0


def time_decay(delta_seconds: float) -> float:
    """Exponential decay with ~1 hour half-life.

    Returns 1.0 at delta=0, 0.5 at delta=3600s, ~0 at delta > 4h.
    Always in (0.0, 1.0].
    """
    if delta_seconds <= 0:
        return 1.0
    return math.exp(-delta_seconds / 3600.0)


def evidence_weight(
    cat_a: str | None, cat_b: str | None, delta_seconds: float
) -> float:
    """Combine category and time into a single evidence weight ∈ (0.0, 1.0]."""
    return category_overlap(cat_a, cat_b) * time_decay(delta_seconds)


def record_observed_link(
    conn: DuckDBPyConnection,
    *,
    from_id: str,
    to_id: str,
    link_type: str,
    evidence: float,
) -> str:
    """Insert or update an observed causal link.

    Self-links (``from_id == to_id``) are rejected with ``ValueError`` —
    they are a malformed causal graph and silently allowing them
    would corrupt the chain walker. Evidence must be in (0.0, 1.0]
    (the CHECK constraint enforces this at the schema level too).

    Returns the link's id. If a row with the same ``(from_id, to_id,
    link_type)`` already exists, this is an UPSERT: the existing id
    is preserved and ``last_evidence_at`` + ``evidence`` are updated.
    Otherwise a fresh ULID is generated.

    The natural identity of an observed link is the triple
    ``(from_id, to_id, link_type)`` — "A led_to B" is one logical
    link, regardless of how many times it was observed. The upsert
    keeps the same id on re-observation so callers can correlate
    repeated observations without changing the link's id.
    """
    if from_id == to_id:
        raise ValueError(f"self-link rejected: from_id == to_id ({from_id!r})")
    if not (0.0 < evidence <= 1.0):
        raise ValueError(f"evidence must be in (0.0, 1.0], got {evidence}")

    # Look for an existing row with the same (from, to, type). If
    # one exists, UPDATE it. Otherwise INSERT a fresh row.
    existing = conn.execute(
        """
        SELECT id FROM causal_links
        WHERE from_id = ? AND to_id = ? AND link_type = ?
        LIMIT 1
        """,
        [from_id, to_id, link_type],
    ).fetchone()
    if existing is not None:
        link_id = str(existing[0])
        conn.execute(
            """
            UPDATE causal_links
            SET evidence = ?, last_evidence_at = now()
            WHERE id = ?
            """,
            [evidence, link_id],
        )
        return link_id

    link_id = str(ULID())
    conn.execute(
        """
        INSERT INTO causal_links
            (id, from_id, to_id, link_type, evidence, link_origin, depth)
        VALUES (?, ?, ?, ?, ?, 'observed', 1)
        """,
        [link_id, from_id, to_id, link_type, evidence],
    )
    return link_id


def infer_causal_links_for(
    conn: DuckDBPyConnection,
    *,
    memory_id: str,
    lookback_limit: int = 20,
) -> list[dict[str, t.Any]]:
    """Infer causal links FROM prior memories TO ``memory_id``.

    Algorithm (LLM-free, plan §Feature #3):

    1. Look at the last ``lookback_limit`` memories in the same
       project as ``memory_id``, with ``timestamp < memory_id.timestamp``.
    2. For each prior memory, compute evidence =
       ``category_overlap * time_decay``.
    3. Persist any with ``evidence > EVIDENCE_FLOOR`` as
       ``link_origin='inferred'``.
    4. Return the list of newly inferred links.

    Cross-project candidates are filtered out by the SQL ``WHERE``
    clause. Self-link is impossible because the prior memories
    are timestamped before ``memory_id``.

    Returns:
        List of link dicts with keys: ``id``, ``from_id``, ``to_id``,
        ``link_type``, ``evidence``, ``link_origin``.
    """
    # Fetch the target memory's project + category + timestamp.
    target_row = conn.execute(
        """
        SELECT project, category, timestamp
        FROM conversations_v2
        WHERE id = ?
        """,
        [memory_id],
    ).fetchone()
    if target_row is None:
        return []
    target_project, target_category, target_ts = target_row

    # Look at recent same-project memories before the target.
    candidates = conn.execute(
        """
        SELECT id, category, timestamp
        FROM conversations_v2
        WHERE project = ?
          AND timestamp < ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        [target_project, target_ts, lookback_limit],
    ).fetchall()

    inferred: list[dict[str, t.Any]] = []
    for cand_id, cand_category, cand_ts in candidates:
        # Coerce DuckDB's naive datetime — both should be naive.
        delta = (target_ts - cand_ts).total_seconds()
        weight = evidence_weight(cand_category, target_category, delta)
        if weight <= EVIDENCE_FLOOR:
            continue

        link_id = str(ULID())
        conn.execute(
            """
            INSERT INTO causal_links
                (id, from_id, to_id, link_type, evidence, link_origin, depth)
            VALUES (?, ?, ?, 'related_to', ?, 'inferred', 1)
            """,
            [link_id, cand_id, memory_id, weight],
        )
        inferred.append(
            {
                "id": link_id,
                "from_id": cand_id,
                "to_id": memory_id,
                "link_type": "related_to",
                "evidence": weight,
                "link_origin": "inferred",
            }
        )

    return inferred


def walk_causal_chain(
    conn: DuckDBPyConnection,
    *,
    start_id: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[dict[str, t.Any]]:
    """BFS-walk the causal graph from ``start_id`` up to ``max_depth``.

    Returns a list of walked edges in BFS order. Each edge dict has
    keys ``from_id``, ``to_id``, ``link_type``, ``evidence``,
    ``link_origin``, ``depth``. ``depth`` is the hop count from
    ``start_id``: 1 for direct neighbors, 2 for neighbors of
    neighbors, etc. (capped at ``max_depth``).

    Cycle-safe via a visited set keyed on the destination ``to_id``
    (so each memory is visited at most once). The set starts with
    ``{start_id}`` so the start itself is never re-entered.

    An isolated start (no outgoing or incoming links) returns ``[]``.
    """
    if max_depth < 1:
        return []

    visited: set[str] = {start_id}
    frontier: list[tuple[str, int]] = [(start_id, 0)]
    walked: list[dict[str, t.Any]] = []

    while frontier:
        next_frontier: list[tuple[str, int]] = []
        for current_id, current_depth in frontier:
            if current_depth >= max_depth:
                continue
            # Outgoing edges from current_id.
            edges = conn.execute(
                """
                SELECT from_id, to_id, link_type, evidence, link_origin
                FROM causal_links
                WHERE from_id = ?
                """,
                [current_id],
            ).fetchall()
            for edge in edges:
                frm, to, ltype, evidence, origin = edge
                if to in visited:
                    continue
                visited.add(to)
                walked.append(
                    {
                        "from_id": str(frm),
                        "to_id": str(to),
                        "link_type": str(ltype),
                        "evidence": float(evidence),
                        "link_origin": str(origin),
                        "depth": current_depth + 1,
                    }
                )
                next_frontier.append((str(to), current_depth + 1))
        frontier = next_frontier

    return walked


def prune_causal_links_older_than(conn: DuckDBPyConnection, *, days: int = 90) -> int:
    """Delete causal links with ``last_evidence_at`` older than ``days``.

    Returns the number of rows deleted. This is what the Conscious
    Agent runs as a periodic cleanup (plan §Feature #3: "links with
    ``last_evidence_at < now() - 90 days`` are pruned by Conscious
    Agent"). A link bumped by ``record_observed_link`` is safe for
    another 90 days.
    """
    before = conn.execute("SELECT COUNT(*) FROM causal_links").fetchone()
    before_count = int(before[0]) if before else 0

    conn.execute(
        """
        DELETE FROM causal_links
        WHERE last_evidence_at < now() - INTERVAL (? || ' days')
        """,
        [str(days)],
    )

    after = conn.execute("SELECT COUNT(*) FROM causal_links").fetchone()
    after_count = int(after[0]) if after else 0
    return before_count - after_count


def get_incoming_links(
    conn: DuckDBPyConnection, *, memory_id: str
) -> list[dict[str, t.Any]]:
    """Return all causal links that point TO ``memory_id``.

    Useful for "what caused this memory?" queries — the inverse
    of the chain walker. Same row shape as ``walk_causal_chain``.
    """
    result = conn.execute(
        """
        SELECT from_id, to_id, link_type, evidence, link_origin, depth
        FROM causal_links
        WHERE to_id = ?
        ORDER BY last_evidence_at DESC
        """,
        [memory_id],
    )
    columns = [c[0] for c in (result.description or [])]
    return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]
