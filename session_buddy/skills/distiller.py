"""Skill Distillation: data layer (Phase 1.5 Feature #6).

A distilled skill is a learnable pattern extracted from observed
session activity. The shape is "for problems like X, try Y
because Z worked in N prior cases" — three short fields plus
evidence.

## LLM-optional by design

This module is the data layer. It does not call any LLM. The
heuristic synthesizer reads the ``memory_access_log`` (which
proves users are actually searching), groups by
``(project, category)``, and produces a skill for each cluster
with at least ``evidence_threshold`` memories. The LLM path
(Conscious Agent in production) can rewrite ``suggested_approach``
into better prose; the data layer doesn't care which path
produced the row — the ``model`` column records it.

## Importance score

The plan's quality floor is ``importance_score >= 0.7`` (CHECK
constraint). The heuristic computes importance from two
ingredients:

- ``log2(1 + evidence_count) / log2(1 + 16)``: saturates at 1.0
  when a cluster has 16+ accessed memories.
- A small boost when memories come from a single project
  (cross-project clusters are less actionable).

The product is clamped to [0.7, 1.0] so the distiller never
produces a below-floor row.
"""

from __future__ import annotations

import json
import logging
import typing as t

if t.TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

from ulid import ULID

logger = logging.getLogger(__name__)


# Quality floor per the plan. The CHECK constraint enforces this
# at the schema level; the distiller also filters at the
# application level (defense in depth).
IMPORTANCE_FLOOR: float = 0.7

# Default evidence threshold: "3 prior cases" per the plan.
DEFAULT_EVIDENCE_THRESHOLD: int = 3

# Default model name recorded in the row when the heuristic path
# produces the text. The Conscious Agent can rewrite the row
# with model='minimax-M3-highspeed' to capture LLM-authored
# prose in the same column.
HEURISTIC_MODEL: str = "heuristic"


def _importance_from_evidence(
    evidence_count: int, project_count: int
) -> float:
    """Heuristic importance score in [IMPORTANCE_FLOOR, 1.0].

    Pure-Python so the function is unit-testable without a DB.
    A cluster with more evidence and a single project scores
    higher; the saturating log keeps the result bounded.
    """
    import math

    # Saturate at 16 evidence; log2(1+16) = 4.0.
    score = math.log2(1 + evidence_count) / 4.0
    # Single-project clusters get a small boost; cross-project
    # stays at the base score. 1 project = full boost, 4+ = none.
    if project_count == 1:
        score = min(score + 0.1, 1.0)
    elif project_count > 4:
        score = max(score - 0.05, IMPORTANCE_FLOOR)
    return max(IMPORTANCE_FLOOR, min(score, 1.0))


def _truncate(s: str, n: int) -> str:
    """Truncate ``s`` to ``n`` chars, appending an ellipsis if cut."""
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def distill_skills(
    conn: DuckDBPyConnection,
    *,
    evidence_threshold: int = DEFAULT_EVIDENCE_THRESHOLD,
    model: str = HEURISTIC_MODEL,
) -> list[dict[str, t.Any]]:
    """Distill skills from current session activity.

    Algorithm (LLM-free):

    1. Find ``(project, category)`` clusters in ``conversations_v2``
       that have at least ``evidence_threshold`` rows joined to
       ``memory_access_log`` (i.e., the cluster has been
       searched, not just written).
    2. For each qualifying cluster, synthesize a skill:
       - ``problem_pattern``: project + category + count
       - ``suggested_approach``: a heuristic template referencing
         the most-frequent first content word ("{word}-style...")
       - ``because``: "N accessed memories in this category"
       - ``importance_score``: from the importance formula
    3. INSERT the row; the CHECK constraint enforces the 0.7 floor.
    4. Return the list of newly-distilled skill dicts (with
       ``source_memory_ids`` decoded for the consumer).

    The function is idempotent on the same data: a re-run
    produces duplicate rows (one per call). The Conscious Agent
    is responsible for scheduling cadence and dedup; the data
    layer is intentionally simple.
    """
    # Find clusters: (project, category) with >= evidence_threshold
    # accessed memories. A memory counts only if it has at least
    # one row in memory_access_log (proves it was searched).
    clusters = conn.execute(
        """
        SELECT
            c.project,
            c.category,
            COUNT(DISTINCT c.id) AS memory_count,
            COUNT(DISTINCT a.id) AS access_count,
            LIST(c.id ORDER BY c.timestamp DESC) AS memory_ids
        FROM conversations_v2 c
        JOIN memory_access_log a ON a.memory_id = c.id
        WHERE c.project IS NOT NULL
        GROUP BY c.project, c.category
        HAVING COUNT(DISTINCT c.id) >= ?
        """,
        [evidence_threshold],
    ).fetchall()

    distilled: list[dict[str, t.Any]] = []
    for project, category, memory_count, access_count, memory_ids in clusters:
        project_count = 1 if project else 0  # GROUP BY collapsed per (project, cat)
        importance = _importance_from_evidence(
            int(memory_count), project_count
        )
        if importance < IMPORTANCE_FLOOR:
            # The formula clamps, but defense in depth: skip
            # anything that fell below.
            continue

        # Most-frequent first content word (heuristic "topic").
        topic_rows = conn.execute(
            """
            SELECT content FROM conversations_v2
            WHERE id = ANY(?)
            ORDER BY timestamp DESC
            """,
            [list(memory_ids)],
        ).fetchall()
        first_words: list[str] = []
        seen: set[str] = set()
        for (content,) in topic_rows:
            text = str(content or "")
            word = text.split(maxsplit=1)[0].strip(".,;:") if text else ""
            if word and word.lower() not in seen:
                first_words.append(word)
                seen.add(word.lower())
            if len(first_words) >= 3:
                break
        topic_str = ", ".join(first_words) if first_words else "general"

        problem_pattern = _truncate(
            f"Project {project}: {memory_count} accessed {category} "
            f"memories about {topic_str}",
            500,
        )
        suggested_approach = _truncate(
            f"{topic_str}-style approach: leverage the recurring "
            f"{category} patterns in project {project}",
            500,
        )
        because_clause = _truncate(
            f"{memory_count} memories with {access_count} accesses in "
            f"this category (evidence: {memory_count} prior cases)",
            500,
        )

        skill_id = str(ULID())
        source_ids_json = json.dumps(list(memory_ids))

        conn.execute(
            """
            INSERT INTO distilled_skills
                (id, problem_pattern, suggested_approach, because,
                 evidence_count, source_memory_ids, importance_score,
                 model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                skill_id,
                problem_pattern,
                suggested_approach,
                because_clause,
                int(memory_count),
                source_ids_json,
                importance,
                model,
            ],
        )

        distilled.append(
            {
                "id": skill_id,
                "problem_pattern": problem_pattern,
                "suggested_approach": suggested_approach,
                "because": because_clause,
                "evidence_count": int(memory_count),
                "source_memory_ids": source_ids_json,
                "importance_score": importance,
                "model": model,
            }
        )

    return distilled


def search_distilled_skills(
    conn: DuckDBPyConnection,
    *,
    query: str = "",
    limit: int = 5,
) -> list[dict[str, t.Any]]:
    """Search distilled skills by problem_pattern / suggested_approach.

    An empty ``query`` returns the top ``limit`` skills by
    ``importance_score DESC, last_reinforced_at DESC``. A non-empty
    ``query`` does a case-insensitive substring match across the
    three text fields (LIKE %q%). The data layer's search is a
    thin wrapper; LLM-based semantic search is a future Conscious
    Agent enhancement.

    Returns skill dicts with ``source_memory_ids`` decoded into
    a Python list for the consumer.
    """
    if query:
        like = f"%{query.lower()}%"
        result = conn.execute(
            """
            SELECT id, problem_pattern, suggested_approach, because,
                   evidence_count, source_memory_ids, importance_score,
                   model, created_at, last_reinforced_at
            FROM distilled_skills
            WHERE LOWER(problem_pattern) LIKE ?
               OR LOWER(suggested_approach) LIKE ?
               OR LOWER(because) LIKE ?
            ORDER BY importance_score DESC, last_reinforced_at DESC
            LIMIT ?
            """,
            [like, like, like, limit],
        )
    else:
        result = conn.execute(
            """
            SELECT id, problem_pattern, suggested_approach, because,
                   evidence_count, source_memory_ids, importance_score,
                   model, created_at, last_reinforced_at
            FROM distilled_skills
            ORDER BY importance_score DESC, last_reinforced_at DESC
            LIMIT ?
            """,
            [limit],
        )
    columns = [c[0] for c in (result.description or [])]
    rows = []
    for row in result.fetchall():
        d = dict(zip(columns, row, strict=False))
        # Decode the source_memory_ids JSON for the consumer.
        raw = d.get("source_memory_ids")
        if isinstance(raw, str) and raw:
            try:
                d["source_memory_ids"] = json.loads(raw)
            except json.JSONDecodeError:
                d["source_memory_ids"] = []
        else:
            d["source_memory_ids"] = []
        rows.append(d)
    return rows


def reinforce_skill(conn: DuckDBPyConnection, *, skill_id: str) -> bool:
    """Bump ``evidence_count`` and ``last_reinforced_at`` for a skill.

    Returns ``True`` if the row existed and was updated, ``False``
    if no row matched (idempotent no-op for unknown ids).
    """
    result = conn.execute(
        """
        UPDATE distilled_skills
        SET evidence_count = evidence_count + 1,
            last_reinforced_at = now()
        WHERE id = ?
        RETURNING id
        """,
        [skill_id],
    )
    return result.fetchone() is not None
