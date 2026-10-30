"""Migrating a DuckDB database to a new embedding width.

The DuckDB embedding columns are fixed-size ARRAY columns, and DuckDB
cannot change an ARRAY's width in place. The migration therefore
rebuilds the database, and the rebuild has to bring back everything the
original had: the rows, the constraints, the foreign keys, and the HNSW
indexes with their tuning intact.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from migrate_embedding_dim import (
    _quote_identifier,
    _rewrite_width,
    _vector_columns,
    migrate,
)

OLD_WIDTH = 4096
NEW_WIDTH = 768


def _make_database(db_path: Path) -> None:
    """Build a database with the shape the real one has.

    An HNSW-indexed table with a row, a table that another table's
    foreign key points at, and an ordinary index -- so the rebuild has to
    reproduce a foreign key and an HNSW index, not just a table.
    """
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("LOAD 'vss'")
        conn.execute("SET hnsw_enable_experimental_persistence=true")
        conn.execute(
            f"CREATE TABLE conversations_v2 ("
            f"  id VARCHAR PRIMARY KEY,"
            f"  content VARCHAR NOT NULL,"
            f"  embedding FLOAT[{OLD_WIDTH}],"
            f"  category VARCHAR NOT NULL"
            f")"
        )
        conn.execute(
            f"CREATE TABLE reflections_v2 ("
            f"  id VARCHAR PRIMARY KEY,"
            f"  conversation_id VARCHAR,"
            f"  content VARCHAR NOT NULL,"
            f"  embedding FLOAT[{OLD_WIDTH}],"
            f"  FOREIGN KEY (conversation_id) REFERENCES conversations_v2(id)"
            f")"
        )
        conn.execute(
            "CREATE INDEX idx_default_refl_embeddings_hnsw ON reflections_v2 "
            "USING HNSW (embedding) WITH (M = 16, ef_construction = 200)"
        )
        conn.execute("CREATE INDEX idx_reflections_category ON reflections_v2(content)")
        vector = "[" + ",".join(["0.25"] * OLD_WIDTH) + "]"
        conn.execute("INSERT INTO conversations_v2 VALUES ('c1', 'a chat', ?, 'facts')", [vector])
        conn.execute(
            "INSERT INTO reflections_v2 VALUES ('r1', 'c1', 'a reflection', ?)",
            [vector],
        )
        conn.execute("CHECKPOINT")
    finally:
        conn.close()


def test_the_migration_rewrites_the_width(tmp_path: Path) -> None:
    """The rebuilt database has the new width."""
    db = tmp_path / "reflection.duckdb"
    _make_database(db)
    out = tmp_path / "migrated.duckdb"

    assert migrate(db, NEW_WIDTH, out_path=out) == 0

    conn = duckdb.connect(str(out), read_only=True)
    try:
        widths = {
            table: width
            for table, cols in _vector_columns(conn).items()
            for _, width in cols
        }
        assert set(widths.values()) == {NEW_WIDTH}
    finally:
        conn.close()


def test_the_migration_keeps_the_rows(tmp_path: Path) -> None:
    """The data survives; only the vectors are dropped."""
    db = tmp_path / "reflection.duckdb"
    _make_database(db)
    out = tmp_path / "migrated.duckdb"

    assert migrate(db, NEW_WIDTH, out_path=out) == 0

    conn = duckdb.connect(str(out), read_only=True)
    try:
        assert conn.execute("SELECT count(*) FROM reflections_v2").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM conversations_v2").fetchone()[0] == 1
        assert conn.execute("SELECT content FROM reflections_v2").fetchone()[0] == "a reflection"
        # The old vectors belong to the old provider's space.
        assert (
            conn.execute(
                "SELECT count(*) FROM reflections_v2 WHERE embedding IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


def test_the_migration_rebuilds_the_hnsw_index_with_its_options(
    tmp_path: Path,
) -> None:
    """An HNSW index rebuilt with the default tuning is a different index."""
    db = tmp_path / "reflection.duckdb"
    _make_database(db)
    out = tmp_path / "migrated.duckdb"

    assert migrate(db, NEW_WIDTH, out_path=out) == 0

    conn = duckdb.connect(str(out), read_only=True)
    try:
        conn.execute("LOAD 'vss'")
        indexes = conn.execute(
            "SELECT index_name, sql FROM duckdb_indexes() "
            "WHERE sql ILIKE '%USING HNSW%'"
        ).fetchall()
        assert indexes, "the HNSW index must be rebuilt"
        assert "M = 16" in indexes[0][1]
        assert "ef_construction = 200" in indexes[0][1]
    finally:
        conn.close()


def test_the_migration_keeps_the_foreign_key(tmp_path: Path) -> None:
    """A rebuild that drops the foreign key has changed the schema."""
    db = tmp_path / "reflection.duckdb"
    _make_database(db)
    out = tmp_path / "migrated.duckdb"

    assert migrate(db, NEW_WIDTH, out_path=out) == 0

    conn = duckdb.connect(str(out), read_only=True)
    try:
        constraints = conn.execute(
            "SELECT constraint_type FROM duckdb_constraints() "
            "WHERE table_name = 'reflections_v2'"
        ).fetchall()
        assert ("FOREIGN KEY",) in constraints
    finally:
        conn.close()


def test_the_migration_leaves_the_original_alone(tmp_path: Path) -> None:
    """Without ``replace`` the input file is not modified."""
    db = tmp_path / "reflection.duckdb"
    _make_database(db)
    out = tmp_path / "migrated.duckdb"
    before = db.read_bytes()

    assert migrate(db, NEW_WIDTH, out_path=out) == 0

    assert db.read_bytes() == before
    assert out.exists()


def test_a_database_at_the_target_width_is_left_alone(tmp_path: Path) -> None:
    """The migration is idempotent."""
    db = tmp_path / "reflection.duckdb"
    _make_database(db)
    out = tmp_path / "migrated.duckdb"

    assert migrate(db, NEW_WIDTH, out_path=out) == 0
    assert migrate(out, NEW_WIDTH, out_path=out) == 0


def test_the_width_rewrite_is_validated() -> None:
    """A rewrite that changed more than the width is refused."""
    schema = "CREATE TABLE t (e FLOAT[4096]); CREATE INDEX i ON t(e);"

    rewritten = _rewrite_width(schema, OLD_WIDTH, NEW_WIDTH)

    assert "FLOAT[768]" in rewritten
    assert "FLOAT[4096]" not in rewritten


def test_identifiers_are_escaped_not_just_quoted() -> None:
    """A name carrying a double quote must not break out of its identifier.

    The table and column names come out of the database's own catalog,
    so they are not a trusted source for a statement to run. Surrounding
    a name with quotes is not escaping it -- a name containing a quote
    would close the identifier and start a new one -- so the embedded
    quotes have to be doubled.
    """
    assert _quote_identifier('a"b') == '"a""b"'
    assert _quote_identifier("plain") == '"plain"'


def test_the_migration_survives_a_hostile_column_name(tmp_path: Path) -> None:
    """A column whose name carries a quote is copied, not injected."""
    db = tmp_path / "reflection.duckdb"
    conn = duckdb.connect(str(db))
    try:
        conn.execute("LOAD 'vss'")
        conn.execute(
            f'CREATE TABLE reflections_v2 (id VARCHAR PRIMARY KEY, '
            f'"od""d" VARCHAR, embedding FLOAT[{OLD_WIDTH}])'
        )
        conn.execute("INSERT INTO reflections_v2 VALUES ('r1', 'kept', NULL)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    out = tmp_path / "migrated.duckdb"

    assert migrate(db, NEW_WIDTH, out_path=out) == 0

    verifier = duckdb.connect(str(out), read_only=True)
    try:
        assert verifier.execute(
            'SELECT "od""d" FROM reflections_v2'
        ).fetchone()[0] == "kept"
    finally:
        verifier.close()
