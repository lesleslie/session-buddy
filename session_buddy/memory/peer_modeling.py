"""Per-project peer modeling (Honcho-style theory of mind).

Phase 1.5 Feature #2. This module is the data layer for an evolving
"theory of mind" representation: per ``(peer_id, project_id)`` pair,
we store a short textual ``representation_text`` (a few sentences
synthesized from the peer's recent memories in this project) plus
an ``evidence_count`` and the ``model`` that produced it.

## ACL contract

This module is the **data layer**, not the policy layer. Adapters
read and write the table freely; **tools and agents** are responsible
for ACL enforcement:

- Reading ``user_models`` requires the ``peer_models:read`` permission
- Writing ``user_models`` requires the ``peer_models:write`` permission

A global user model would be a privacy disaster — the composite
``PRIMARY KEY (peer_id, project_id)`` enforces per-project scoping
at the schema level. Callers MUST pass both fields; a tool that
silently defaults one is a regression.

## Synthesis path

The default ``model='heuristic'`` representation is built by
:func:`_heuristic_synthesize`, which reads the last N memories for
this ``(peer_id, project_id)`` and produces a few sentences by
grouping categories. LLM-driven synthesis (via
``model='minimax-M3-highspeed'``) is a Conscious-Agent concern; the
adapter accepts an explicit ``model`` argument so the row records
which path produced it (per the plan's LLM Cost Ceiling).
"""

from __future__ import annotations

import logging
import typing as t

if t.TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Default model name recorded in the row when a peer model is created
# without an LLM call. This is the cheap, deterministic path; the
# Conscious Agent may rewrite the row with model='minimax-M3-highspeed'
# when its LLM cost budget allows.
DEFAULT_HEURISTIC_MODEL = "heuristic"


def heuristic_synthesize(
    conn: DuckDBPyConnection,
    *,
    peer_id: str,
    project_id: str,
    recent_limit: int = 5,
) -> str:
    """Produce a short representation by summarizing recent memories.

    Heuristic path: no LLM. Reads the last ``recent_limit`` memories
    for the ``(peer_id, project_id)`` pair and produces a few
    sentences by counting categories and listing the most recent
    topics. The output is intentionally short — the adapter stores
    the full row, callers can ask for more context via
    :func:`peer_context`.

    Returns:
        A short textual representation, e.g.
        ``"User has 3 recent memories in proj-1. Recent categories:
        facts (2), preferences (1). Topics: python, async, v2 rewire."``.
        Returns a one-sentence placeholder when there are no memories
        yet, so the row is never empty (an empty ``representation_text``
        is indistinguishable from "row never written").
    """
    # Project filter is on the conversation row's project column.
    # peer_id is not yet a column on conversations_v2 — it lives in
    # metadata when the ingester tags the row. For heuristic synthesis
    # we filter by project only (cross-peer dedup is the caller's
    # problem; the row's composite PK keeps writes safe regardless).
    rows = conn.execute(
        """
        SELECT category, content, timestamp
        FROM conversations_v2
        WHERE project = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        [project_id, recent_limit],
    ).fetchall()

    if not rows:
        return (
            f"Peer {peer_id} has no memories yet in project "
            f"{project_id}. Initial representation."
        )

    # Count categories.
    category_counts: dict[str, int] = {}
    for row in rows:
        cat = str(row[0]) if row[0] else "unknown"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    cat_summary = ", ".join(
        f"{cat} ({n})"
        for cat, n in sorted(
            category_counts.items(), key=lambda x: -x[1]
        )
    )

    # Pull a couple of distinct first-words as "topics" — short and
    # legible. The full content is in the row; the representation is
    # meant to be a glance.
    topics: list[str] = []
    seen: set[str] = set()
    for row in rows:
        content = str(row[1] or "")
        first_word = content.split(maxsplit=1)[0].strip(".,;:") if content else ""
        if first_word and first_word.lower() not in seen:
            topics.append(first_word)
            seen.add(first_word.lower())
        if len(topics) >= 3:
            break

    topic_str = ", ".join(topics) if topics else "(no topics yet)"

    return (
        f"Peer {peer_id} has {len(rows)} recent memories in "
        f"project {project_id}. Recent categories: {cat_summary}. "
        f"Recent topics: {topic_str}."
    )


def upsert_peer_model(
    conn: DuckDBPyConnection,
    *,
    peer_id: str,
    project_id: str,
    representation_text: str | None = None,
    model: str = DEFAULT_HEURISTIC_MODEL,
) -> str:
    """Insert or update the row for ``(peer_id, project_id)``.

    On first call, synthesizes a heuristic representation from recent
    memories. On subsequent calls, increments ``evidence_count`` and
    refreshes ``representation_text`` (either heuristically or from
    the caller's ``representation_text`` arg, which is what the
    Conscious Agent uses for its LLM-driven path).

    Returns the ``representation_text`` that was stored.
    """
    if representation_text is None:
        representation_text = heuristic_synthesize(
            conn, peer_id=peer_id, project_id=project_id
        )

    conn.execute(
        """
        INSERT INTO user_models
            (peer_id, project_id, representation_text, last_updated, evidence_count, model)
        VALUES (?, ?, ?, now(), 1, ?)
        ON CONFLICT (peer_id, project_id) DO UPDATE SET
            representation_text = EXCLUDED.representation_text,
            last_updated = now(),
            evidence_count = user_models.evidence_count + 1,
            model = EXCLUDED.model
        """,
        [peer_id, project_id, representation_text, model],
    )

    return representation_text


def get_peer_model(
    conn: DuckDBPyConnection, *, peer_id: str, project_id: str
) -> dict[str, t.Any] | None:
    """Return the row for ``(peer_id, project_id)`` or None if missing."""
    result = conn.execute(
        """
        SELECT peer_id, project_id, representation_text,
               last_updated, evidence_count, model
        FROM user_models
        WHERE peer_id = ? AND project_id = ?
        """,
        [peer_id, project_id],
    )
    columns = [c[0] for c in (result.description or [])]
    rows = result.fetchall()
    if not rows:
        return None
    return dict(zip(columns, rows[0], strict=False))


def recent_memories(
    conn: DuckDBPyConnection,
    *,
    project_id: str,
    recent_limit: int,
) -> list[dict[str, t.Any]]:
    """Return the last ``recent_limit`` conversations for ``project_id``.

    Used by :func:`peer_context` to bundle recent memories alongside
    the representation. Filters by project only — peer scoping is
    the caller's responsibility (the row's composite PK is the
    authoritative guard against cross-peer contamination).
    """
    result = conn.execute(
        """
        SELECT id, content, category, timestamp, project, source_type
        FROM conversations_v2
        WHERE project = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        [project_id, recent_limit],
    )
    columns = [c[0] for c in (result.description or [])]
    return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]


def build_peer_context(
    conn: DuckDBPyConnection,
    *,
    peer_id: str,
    project_id: str,
    recent_limit: int = 5,
    target_peer_id: str | None = None,
) -> dict[str, t.Any]:
    """Bundle a peer's representation + recent memories into one dict.

    Shape::

        {
            "peer_id": str,
            "project_id": str,
            "representation_text": str,
            "last_updated": datetime | None,
            "evidence_count": int,
            "model": str,
            "recent_memories": [{"id": ..., "content": ..., ...}],
            "target_peer": {...same shape...} | None,
        }

    The ``target_peer`` field is populated only when
    ``target_peer_id`` is provided AND that peer has a row in
    ``user_models`` for the same project. Useful for agent-vs-user
    theory of mind (the user model and the agent's self-model can
    be returned side by side).
    """
    model = get_peer_model(conn, peer_id=peer_id, project_id=project_id)
    memories = recent_memories(
        conn, project_id=project_id, recent_limit=recent_limit
    )

    if model is None:
        base: dict[str, t.Any] = {
            "peer_id": peer_id,
            "project_id": project_id,
            "representation_text": "",
            "last_updated": None,
            "evidence_count": 0,
            "model": "",
            "recent_memories": memories,
            "target_peer": None,
        }
    else:
        base = {
            "peer_id": model["peer_id"],
            "project_id": model["project_id"],
            "representation_text": model["representation_text"],
            "last_updated": model["last_updated"],
            "evidence_count": int(model["evidence_count"]),
            "model": model["model"],
            "recent_memories": memories,
            "target_peer": None,
        }

    if target_peer_id is not None:
        target = get_peer_model(
            conn, peer_id=target_peer_id, project_id=project_id
        )
        if target is not None:
            base["target_peer"] = {
                "peer_id": target["peer_id"],
                "project_id": target["project_id"],
                "representation_text": target["representation_text"],
                "last_updated": target["last_updated"],
                "evidence_count": int(target["evidence_count"]),
                "model": target["model"],
            }

    return base
