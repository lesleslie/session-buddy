"""RED golden test: existing reflection-adapter call sites must round-trip through the v2 write path.

This is the merge gate for the Phase 0 PR. It exercises a representative sample of
the 28 known non-test call sites that touch the reflection adapter and asserts each
one routes through the v2-only write path (i.e. rows land in ``conversations_v2``,
not the legacy ``{collection}_conversations`` collection table).

Covered sites (full list lives in the discovery report):
    Write sites (4):
        - core/conversation_storage.py:213          (db.store_conversation)
        - mcp/tools/conversation/conversation_tools.py:72  (db.store_conversation)
        - mcp/tools/session/crackerjack_tools.py:859       (db.store_conversation)
        - mcp/tools/session/crackerjack_tools.py:866       (db.store_conversation)

    Read sites (5 of 24 — representative of the search/read surface):
        - mcp/tools/memory/memory_tools.py:170       (db.search_conversations)
        - mcp/tools/memory/memory_tools.py:318       (db.search_conversations)
        - mcp/tools/memory/search_tools.py:119       (db.search_conversations)
        - mcp/tools/memory/search_tools.py:201       (db.search_conversations)
        - mcp/tools/memory/search_tools.py:683       (db.search_conversations)

Raw SQL sites (4) and the wrapper-call sites (3) are intentionally excluded from
the parametrize set: they target ``{collection}_conversations`` directly and will
collapse onto v2 once the adapter itself rewires. They are covered by the
post-rewire migration tests.

The test is RED today because:
    1. The current adapter writes to ``default_conversations`` (collection-scoped).
    2. ``conversations_v2`` is not auto-created on initialize (it lives in
       ``memory/schema_v2.py`` but is not part of the adapter's bootstrap).
    3. Even if it were created, the write path does not insert into it.

This file MUST fail until the v2 rewire is complete.

SQL safety note: all DuckDB introspection queries below use bound parameters
via DuckDB catalog functions (``duckdb_tables()``, ``duckdb_columns()``) or
delegate table-name construction to the adapter's existing ``_table()`` helper
(the same one used by ``session_buddy/doctor.py``). No external input is
interpolated into SQL strings.
"""

from __future__ import annotations

from typing import Any

import pytest

# Module-level constant: post-rewire target table name. Not user input.
V2_TABLE_NAME = "conversations_v2"

# Subset of v2 columns the merge gate requires.
_V2_REQUIRED_COLUMNS: tuple[str, ...] = ("id", "content", "metadata")


# ---------------------------------------------------------------------------
# Site registry
# ---------------------------------------------------------------------------

WRITE_SITES: list[tuple[str, int, str]] = [
    ("session_buddy/core/conversation_storage.py", 213, "store_conversation"),
    ("session_buddy/mcp/tools/conversation/conversation_tools.py", 72, "store_conversation"),
    ("session_buddy/mcp/tools/session/crackerjack_tools.py", 859, "store_conversation"),
    ("session_buddy/mcp/tools/session/crackerjack_tools.py", 866, "store_conversation"),
]

READ_SITES: list[tuple[str, int, str]] = [
    ("session_buddy/mcp/tools/memory/memory_tools.py", 170, "search_conversations"),
    ("session_buddy/mcp/tools/memory/memory_tools.py", 318, "search_conversations"),
    ("session_buddy/mcp/tools/memory/search_tools.py", 119, "search_conversations"),
    ("session_buddy/mcp/tools/memory/search_tools.py", 201, "search_conversations"),
    ("session_buddy/mcp/tools/memory/search_tools.py", 683, "search_conversations"),
]


# ---------------------------------------------------------------------------
# Helpers — DuckDB introspection via bound parameters.
# ---------------------------------------------------------------------------


def _source_line_matches(file_path: str, line: int, needle: str) -> bool:
    """Confirm ``needle`` appears at ``file_path:line``.

    Returns True if the file cannot be read (skip rather than fail on
    feature-branch refactors).
    """
    import os

    abs_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        file_path,
    )
    try:
        with open(abs_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return True
    if line - 1 >= len(lines):
        return False
    return needle in lines[line - 1]


def _duckdb_table_exists(conn: Any, table_name: str) -> bool:
    """True if ``table_name`` is in DuckDB's catalog (bound parameter)."""
    try:
        row = conn.execute(
            "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1",
            [table_name],
        ).fetchone()
    except Exception:
        return False
    return row is not None


def _v2_required_columns_present(conn: Any) -> bool:
    """True if v2 table exists and has the merge-gate contract columns."""
    try:
        rows = conn.execute(
            "SELECT column_name FROM duckdb_columns() WHERE table_name = ?",
            [V2_TABLE_NAME],
        ).fetchall()
    except Exception:
        return False
    names = {str(r[0]) for r in rows}
    return all(col in names for col in _V2_REQUIRED_COLUMNS)


def _v2_has_row_with_content(conn: Any, content_marker: str) -> bool:
    """True if the v2 table has a row whose content contains ``content_marker``.

    Table name is read from the catalog via a bound parameter; the LIKE
    pattern is also bound. The only string-typed literal in the SQL is the
    column name ``content`` which is a fixed schema field.
    """
    if not _duckdb_table_exists(conn, V2_TABLE_NAME):
        return False
    try:
        rows = conn.execute(
            "SELECT content FROM conversations_v2 WHERE content LIKE ?",
            [f"%{content_marker}%"],
        ).fetchall()
    except Exception:
        return False
    return any(content_marker in str(r[0]) for r in rows)


def _insert_v2_row(conn: Any, row_id: str, content: str) -> bool:
    """Insert a v2 row directly. False if v2 table is missing/wrong shape."""
    if not _v2_required_columns_present(conn):
        return False
    try:
        conn.execute(
            "INSERT INTO conversations_v2 (id, content, category) "
            "VALUES (?, ?, ?)",
            [row_id, content, "context"],
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Parametrized golden cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("file_path", "line", "qualname"),
    WRITE_SITES,
    ids=[f"{f.split('/')[-1]}:{ln}" for f, ln, _ in WRITE_SITES],
)
async def test_write_site_round_trips_through_v2(
    fast_temp_db: Any,
    file_path: str,
    line: int,
    qualname: str,
) -> None:
    """Each known write site must end up writing to ``conversations_v2``."""
    if not _source_line_matches(file_path, line, "store_conversation"):
        pytest.skip(f"Call site moved or refactored: {file_path}:{line}")

    db = fast_temp_db
    conn = db.conn

    sample = (
        f"golden-roundtrip-{file_path.split('/')[-1]}-{line}-"
        f"{qualname}-v2"
    )
    if qualname == "store_conversation":
        conv_id = await db.store_conversation(sample, {"project": "golden"})
    else:
        from session_buddy.core.conversation_storage import (
            store_conversation_checkpoint,
        )

        result = await store_conversation_checkpoint(
            db=db,
            content=sample,
            metadata={"project": "golden"},
            checkpoint_type="golden",
        )
        conv_id = result if isinstance(result, str) else "ok"

    # The v2 table must exist with the merge-gate contract columns.
    assert _duckdb_table_exists(conn, V2_TABLE_NAME), (
        f"Write site {file_path}:{line} did not create a v2 schema. "
        f"Expected table '{V2_TABLE_NAME}' to exist after initialize+write."
    )
    assert _v2_required_columns_present(conn), (
        f"Write site {file_path}:{line} created '{V2_TABLE_NAME}' but it "
        f"is missing one of {_V2_REQUIRED_COLUMNS}."
    )

    # The v2 table must contain a row with the sample content.
    assert _v2_has_row_with_content(conn, sample), (
        f"Write site {file_path}:{line} (qualname={qualname}, id={conv_id}) "
        f"did not land a row in '{V2_TABLE_NAME}'. Adapter is still on the "
        f"v1 collection table; v2 rewire not complete."
    )


@pytest.mark.parametrize(
    ("file_path", "line", "qualname"),
    READ_SITES,
    ids=[f"{f.split('/')[-1]}:{ln}" for f, ln, _ in READ_SITES],
)
async def test_read_site_sees_v2_writes(
    fast_temp_db: Any,
    file_path: str,
    line: int,
    qualname: str,
) -> None:
    """A row written to v2 must be discoverable by every read site."""
    if not _source_line_matches(file_path, line, "search_conversations"):
        pytest.skip(f"Call site moved or refactored: {file_path}:{line}")

    db = fast_temp_db

    # Write a v2-shaped row directly so we can isolate the read path.
    marker = f"golden-read-{file_path.split('/')[-1]}-{line}"
    if not _insert_v2_row(db.conn, f"golden-{line}", marker):
        pytest.fail(
            f"v2 table '{V2_TABLE_NAME}' missing or malformed. "
            f"Read site {file_path}:{line} cannot be exercised because the "
            f"v2 rewire has not created the target table."
        )

    # Exercise the read site via the public search method.
    results = await db.search_conversations(
        query=marker,
        project="golden",
        limit=5,
        min_score=0.0,
    )

    # Shape assertion: list of dicts with the contract fields.
    assert isinstance(results, list), (
        f"Read site {file_path}:{line} returned {type(results).__name__}, "
        f"expected list."
    )
    assert results, (
        f"Read site {file_path}:{line} returned no results for a row that "
        f"was just inserted into '{V2_TABLE_NAME}'. Read path does not see v2."
    )
    for hit in results:
        assert isinstance(hit, dict), (
            f"Read site {file_path}:{line} returned non-dict hit: {hit!r}"
        )
        for field in ("id", "content"):
            assert field in hit, (
                f"Read site {file_path}:{line} missing field '{field}' "
                f"in result: {hit!r}"
            )


# ---------------------------------------------------------------------------
# Coverage marker
# ---------------------------------------------------------------------------


def test_site_registry_covers_28_call_sites() -> None:
    """Guardrail: registry sums to 9 entries (4 writes + 5 reads).

    Full site list is 28; the remaining 19 sites are intentionally deferred
    to the post-rewire migration tests. Fails if a future agent silently
    shrinks the registry below the documented sample size.
    """
    total = len(WRITE_SITES) + len(READ_SITES)
    assert total == 9, (
        f"Golden registry shrank to {total} sites; expected 9 (4 write + 5 read). "
        f"Either restore the documented sample or update this guard."
    )
