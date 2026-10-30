#!/usr/bin/env python3
"""Migrate a DuckDB reflection database to a new embedding width.

The DuckDB embedding columns are fixed-size ARRAY columns (``FLOAT[N]``),
and DuckDB cannot change an ARRAY's width in place:

    ALTER TABLE t ALTER COLUMN embedding TYPE FLOAT[768]
      -> Conversion Error: Cannot cast array of size 4096 to array of size 768

It cannot be widened by dropping and re-adding the column either, because
a column cannot be dropped while an index covers a later column, and a
table cannot be altered while a foreign key points at it. So the
migration rebuilds the database.

The rebuild uses DuckDB's own ``EXPORT DATABASE`` / ``IMPORT DATABASE``
machinery, which is the only route that reproduces the schema faithfully:
every constraint, check, foreign key and index -- including the HNSW
indexes with their ``WITH (M = ..., ef_construction = ...)`` options --
comes back exactly as it was.

What changes:

* Every ``FLOAT[old]`` column becomes ``FLOAT[new]``.
* The vectors in those columns are **dropped**. They were produced by the
  old provider in the old vector space and carry no meaning in the new
  one; they are re-embedded from the row's text by ``--re-embed``.

Usage::

    # Stop the server first -- DuckDB is single-writer and the file must
    # not be held open.
    python scripts/migrate_embedding_dim.py --dry-run
    python scripts/migrate_embedding_dim.py --re-embed

The original file is copied to ``<path>.pre-migration.bak`` before the
new one is put in place.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from session_buddy.memory.embedding_dim import DEFAULT_EMBEDDING_DIM
from session_buddy.paths import data_dir

#: A fixed-size ARRAY column in the exported schema.
_VECTOR_TYPE = re.compile(r"FLOAT\[(?P<width>\d+)\]")


def _quote_identifier(value: str) -> str:
    """Quote a SQL identifier, escaping any embedded double quote.

    The identifiers here come out of the database's own catalog, so they
    are not a trusted source for a statement to run. Surrounding a name
    with quotes is not escaping it -- a name containing a quote would
    close the identifier and start a new one -- so the embedded quotes
    are doubled, which is what SQL defines the escape to be.

    Args:
        value: The identifier to quote.

    Returns:
        The quoted identifier.
    """
    return '"' + value.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    """Quote a string literal, escaping any embedded single quote.

    DuckDB exposes no parameter binding for ``EXPORT DATABASE``, so the
    path has to be spelled out in the statement. A single quote is
    escaped by doubling it.

    Args:
        value: The literal to quote.

    Returns:
        The quoted literal.
    """
    return "'" + value.replace("'", "''") + "'"


def _vector_columns(
    conn: duckdb.DuckDBPyConnection,
) -> dict[str, list[tuple[str, int]]]:
    """Map each table to its fixed-size ARRAY columns and their widths.

    Args:
        conn: A connection to the database.

    Returns:
        ``{table_name: [(column_name, width), ...]}``.
    """
    rows = conn.execute(
        "SELECT table_name, column_name, data_type FROM duckdb_columns() "
        "WHERE database_name = current_database() AND schema_name = 'main' "
        "AND data_type LIKE 'FLOAT%' ORDER BY table_name, column_index"
    ).fetchall()
    columns: dict[str, list[tuple[str, int]]] = {}
    for table_name, column_name, data_type in rows:
        match = re.fullmatch(r"FLOAT\[(\d+)\]", str(data_type))
        if match is None:
            continue
        columns.setdefault(str(table_name), []).append(
            (str(column_name), int(match.group(1)))
        )
    return columns


def _rewrite_width(schema_sql: str, old_width: int, new_width: int) -> str:
    """Rewrite every ``FLOAT[old_width]`` to ``FLOAT[new_width]``.

    The rewrite is validated to be *width-only*: mapping the new width
    back to the old one must reproduce the original text exactly. That is
    what makes it safe to execute the result -- it is DuckDB's own
    serialisation of the schema being migrated, and the only thing that
    differs is the vector width.

    Args:
        schema_sql: The exported schema.
        old_width: The width being replaced.
        new_width: The width to write.

    Returns:
        The rewritten schema.

    Raises:
        ValueError: If the rewrite changed anything but the width.
    """
    rewritten = _VECTOR_TYPE.sub(
        lambda m: (
            f"FLOAT[{new_width}]" if int(m.group("width")) == old_width else m.group(0)
        ),
        schema_sql,
    )
    if rewritten == schema_sql:
        return rewritten
    restored = _VECTOR_TYPE.sub(
        lambda m: (
            f"FLOAT[{old_width}]" if int(m.group("width")) == new_width else m.group(0)
        ),
        rewritten,
    )
    if restored != schema_sql:
        raise ValueError(
            "the schema rewrite changed more than the vector width; refusing to migrate"
        )
    return rewritten


def _partition_statements(
    conn: duckdb.DuckDBPyConnection, schema_sql: str
) -> tuple[list[str], list[str]]:
    """Split the exported schema into table DDL and index DDL.

    The tables are created first and the indexes afterwards, so the data
    load happens on unindexed tables. That is deliberate: rebuilding an
    HNSW index over rows that came from a WAL replay is the operation
    that poisons the instance (see ``session_buddy/memory/duckdb_open.py``).

    Args:
        conn: A connection used only for its statement parser.
        schema_sql: The exported schema.

    Returns:
        ``(table_statements, index_statements)``.
    """
    tables: list[str] = []
    indexes: list[str] = []
    for statement in conn.extract_statements(schema_sql):
        sql = statement.query
        if not sql.strip():
            continue
        if "CREATE INDEX" in sql.upper():
            indexes.append(sql)
        else:
            tables.append(sql)
    return tables, indexes


def _copy_data(
    target: duckdb.DuckDBPyConnection,
    vector_columns: dict[str, list[tuple[str, int]]],
    source_alias: str = "src",
) -> dict[str, int]:
    """Copy every row from the attached source into the target, minus the vectors.

    The vector columns are omitted so they default to NULL -- the old
    vectors belong to the old provider's space.

    Args:
        target: The database being built, with the source attached.
        vector_columns: The vector columns to omit, per table.
        source_alias: The name the source database is attached under.

    Returns:
        ``{table_name: rows_copied}``.
    """
    copied: dict[str, int] = {}
    # An attached database has its own schema, and DuckDB names that
    # schema 'main' too -- so the database name is the discriminator that
    # keeps the source's tables out of the target's column list.
    table_names = [
        str(row[0])
        for row in target.execute(
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = current_database() "
            "AND schema_name = 'main' ORDER BY table_name"
        ).fetchall()
    ]
    for table in table_names:
        all_columns = [
            str(row[0])
            for row in target.execute(
                "SELECT column_name FROM duckdb_columns() "
                "WHERE database_name = current_database() "
                "AND schema_name = 'main' AND table_name = ? "
                "ORDER BY column_index",
                [table],
            ).fetchall()
        ]
        omitted = {name for name, _ in vector_columns.get(table, [])}
        kept = [name for name in all_columns if name not in omitted]
        if not kept:
            copied[table] = 0
            continue
        quoted_table = _quote_identifier(table)
        quoted_source = _quote_identifier(source_alias)
        quoted = ", ".join(_quote_identifier(name) for name in kept)
        # The INSERT reports how many rows it inserted, so the count
        # does not need a query of its own.
        #
        # SQL has no binding for identifiers, so the table and column
        # names have to be spelled out. They come out of the catalog and
        # are escaped by _quote_identifier; the values are parameters.
        #
        # The suppression has to sit on the line the match *starts* on --
        # semgrep attributes a trailing comment to its own line, and the
        # match starts at the ``execute(`` call, not at the argument.
        inserted = target.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.lang.security.audit.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query
            f"INSERT INTO {quoted_table} ({quoted}) "
            f"SELECT {quoted} FROM {quoted_source}.{quoted_table}"
        ).fetchone()[0]
        copied[table] = int(inserted)
    return copied


async def _reembed(target_path: Path, tables: dict[str, list[str]]) -> int:
    """Re-embed the rows of the given tables with the current provider.

    Args:
        target_path: The migrated database.
        tables: ``{table_name: [text_column, ...]}`` -- the first text
            column present in the table is used as the text to embed.

    Returns:
        The number of rows that received an embedding.
    """
    from session_buddy.reflection.embeddings import generate_embedding

    conn = duckdb.connect(str(target_path))
    try:
        # The re-embed updates an HNSW-indexed table, and the extension
        # that owns the index type has to be loaded on the modifying
        # connection -- an extension binds to a database *instance*, not
        # to a file.
        conn.execute("LOAD 'vss'")
        conn.execute("SET hnsw_enable_experimental_persistence=true")
    except Exception:  # noqa: BLE001 - the vss extension may not be installed
        print(
            "WARNING: the vss extension is not available; the rows will be "
            "re-embedded later, from the server."
        )
    updated = 0
    try:
        for table, text_columns in tables.items():
            columns = [
                str(row[0])
                for row in conn.execute(
                    "SELECT column_name FROM duckdb_columns() "
                    "WHERE table_name = ? ORDER BY column_index",
                    [table],
                ).fetchall()
            ]
            if "embedding" not in columns:
                continue
            text_column = next((c for c in text_columns if c in columns), None)
            if text_column is None:
                continue
            rows = conn.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.lang.security.audit.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query
                f"SELECT id, {_quote_identifier(text_column)} "
                f"FROM {_quote_identifier(table)} "
                "WHERE embedding IS NULL AND "
                f"{_quote_identifier(text_column)} IS NOT NULL"
            ).fetchall()
            for row_id, text in rows:
                vector = await generate_embedding(str(text))
                if vector is None:
                    continue
                conn.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.lang.security.audit.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query
                    f"UPDATE {_quote_identifier(table)} SET embedding = ? WHERE id = ?",
                    [vector, row_id],
                )
                updated += 1
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    return updated


def _export_schema(source_file: Path, export_dir: Path) -> str:
    """Export the database and return its schema.

    Args:
        source_file: The database to export.
        export_dir: Where to write the export.

    Returns:
        The exported schema.
    """
    source = duckdb.connect(str(source_file))
    try:
        source.execute("LOAD 'vss'")
        source.execute("SET hnsw_enable_experimental_persistence=true")
        export_dir.mkdir(parents=True, exist_ok=True)
        # DuckDB exposes no parameter binding for EXPORT DATABASE -- the
        # statement is a parser error with a placeholder -- so the path
        # has to be spelled out. It is escaped as a string literal (a
        # single quote is escaped by doubling it), and the path comes
        # from tempfile.mkdtemp(), never from user input.
        #
        # The suppression has to sit on the line the match *starts* on --
        # semgrep attributes a trailing comment to its own line, and the
        # match starts at the ``execute(`` call, not at the argument.
        source.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.lang.security.audit.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query
            f"EXPORT DATABASE {_quote_literal(str(export_dir))} (FORMAT PARQUET)"
        )
        return (export_dir / "schema.sql").read_text(encoding="utf-8")
    finally:
        # The file has to be closed before it can be attached to another
        # connection: DuckDB refuses to attach a file it already has a
        # handle on.
        source.close()


def _rebuild_database(
    source_file: Path,
    new_file: Path,
    export_dir: Path,
    vector_columns: dict[str, list[tuple[str, int]]],
    old_width: int,
    new_width: int,
) -> dict[str, int]:
    """Rebuild the database at the new width.

    The tables are created first and the indexes afterwards, so the data
    load happens on unindexed tables. That is deliberate: rebuilding an
    HNSW index over rows that came from a WAL replay is the operation
    that poisons the instance (see ``session_buddy/memory/duckdb_open.py``).

    Args:
        source_file: The database to read from.
        new_file: The database to write.
        export_dir: Where to write the export.
        vector_columns: The vector columns, per table.
        old_width: The width being replaced.
        new_width: The width to write.

    Returns:
        ``{table_name: rows_copied}``.
    """
    rewritten = _rewrite_width(
        _export_schema(source_file, export_dir), old_width, new_width
    )
    target = duckdb.connect(str(new_file))
    try:
        target.execute("LOAD 'vss'")
        target.execute("SET hnsw_enable_experimental_persistence=true")
        table_ddl, index_ddl = _partition_statements(target, rewritten)
        for statement in table_ddl:
            target.execute(statement)
        print(f"Created {len(table_ddl)} tables.")

        target.execute("ATTACH ? AS src (READ_ONLY)", [str(source_file)])
        try:
            copied = _copy_data(target, vector_columns)
        finally:
            target.execute("DETACH src")
        print(f"Copied {sum(copied.values())} rows.")

        for statement in index_ddl:
            target.execute(statement)
        print(f"Created {len(index_ddl)} indexes.")

        target.execute("CHECKPOINT")
        return copied
    finally:
        target.close()


def _verify_migration(
    new_file: Path, copied: dict[str, int], new_width: int
) -> int | None:
    """Check the rebuilt database before it is put in place.

    Args:
        new_file: The rebuilt database.
        copied: The row counts that were copied.
        new_width: The width every vector column must have.

    Returns:
        The number of indexes, or ``None`` when the verification failed.
    """
    verifier = duckdb.connect(str(new_file), read_only=True)
    try:
        verifier.execute("LOAD 'vss'")
        after = _vector_columns(verifier)
        bad = [
            (table, name, width)
            for table, cols in after.items()
            for name, width in cols
            if width != new_width
        ]
        if bad:
            print(f"ERROR: verification failed -- wrong widths: {bad}")
            return None
        for table, count in copied.items():
            # query_table() takes the table name as a parameter, so the
            # name never has to be interpolated into the statement.
            actual = verifier.execute(
                "SELECT count(*) FROM query_table(?)", [table]
            ).fetchone()[0]
            if int(actual) != count:
                print(
                    f"ERROR: verification failed -- {table} has {actual} rows, "
                    f"expected {count}"
                )
                return None
        return int(
            verifier.execute("SELECT count(*) FROM duckdb_indexes()").fetchone()[0]
        )
    finally:
        verifier.close()


def migrate(
    db_path: Path,
    new_width: int,
    *,
    out_path: Path | None = None,
    reembed: bool = False,
    replace: bool = False,
    dry_run: bool = False,
) -> int:
    """Migrate ``db_path`` to ``new_width``.

    The migration is **non-destructive by default**: the rebuilt database
    is written to ``out_path`` and the input is never modified. Passing
    ``replace`` additionally copies the original to a ``.bak`` and puts
    the rebuilt file in its place.

    Args:
        db_path: The DuckDB file to migrate.
        new_width: The target vector width.
        out_path: Where to write the rebuilt database. Defaults to
            ``<db_path>.migrated-<width>.duckdb``.
        reembed: Whether to re-embed the rows after the migration.
        replace: Whether to replace the input file with the rebuild.
        dry_run: Report what would happen without changing anything.

    Returns:
        A process exit code.
    """
    if not db_path.exists():
        print(f"ERROR: {db_path} does not exist")
        return 1

    try:
        conn = duckdb.connect(str(db_path))
    except Exception as exc:  # noqa: BLE001 - the lock message is the actionable part
        print(f"ERROR: could not open {db_path}: {exc}")
        print("DuckDB is single-writer -- stop the session-buddy server first.")
        return 1

    try:
        conn.execute("LOAD 'vss'")
        conn.execute("SET hnsw_enable_experimental_persistence=true")
        vector_columns = _vector_columns(conn)
    finally:
        conn.close()

    widths = {w for cols in vector_columns.values() for _, w in cols}
    if not widths:
        print("No fixed-size ARRAY columns found; nothing to migrate.")
        return 0
    if widths == {new_width}:
        print(f"Already at width {new_width}; nothing to migrate.")
        return 0
    old_width = min(widths)
    if len(widths) > 1:
        print(f"ERROR: the database has mixed vector widths {sorted(widths)}")
        return 1

    print(f"Database : {db_path}")
    print(f"Width    : {old_width} -> {new_width}")
    print("Columns  :")
    for table, cols in sorted(vector_columns.items()):
        for name, width in cols:
            print(f"  {table}.{name}: FLOAT[{width}] -> FLOAT[{new_width}]")
    if dry_run:
        print("\nDry run -- nothing changed.")
        return 0

    work = Path(tempfile.mkdtemp(prefix="sb-embed-migrate-"))
    source_file = work / "source.duckdb"
    new_file = work / "migrated.duckdb"
    export_dir = work / "export"

    # Work from a copy so the live file is never the thing being read
    # while the new one is written.
    shutil.copy2(db_path, source_file)
    wal = Path(f"{db_path}.wal")
    if wal.exists():
        shutil.copy2(wal, Path(f"{source_file}.wal"))

    copied = _rebuild_database(
        source_file, new_file, export_dir, vector_columns, old_width, new_width
    )

    # Verify before the swap: the row counts and the widths must match.
    index_count = _verify_migration(new_file, copied, new_width)
    if index_count is None:
        return 1
    print(f"Verified: {sum(copied.values())} rows, {index_count} indexes.")

    backup = db_path.with_suffix(db_path.suffix + ".pre-migration.bak")
    destination = out_path or db_path.with_suffix(
        db_path.suffix + f".migrated-{new_width}.duckdb"
    )
    if replace:
        shutil.copy2(db_path, backup)
        print(f"Backed up the original to {backup}")
        new_file.replace(destination)
        if destination == db_path:
            print(f"Migrated {db_path} to FLOAT[{new_width}].")
        else:
            print(f"Migrated copy written to {destination}.")
    else:
        shutil.copy2(new_file, destination)
        print(f"Migrated copy written to {destination}.")
        print(
            "The original was not modified. Re-run with --replace to put it in place."
        )

    # The re-embed runs on the file that was just put in place, so a
    # failure here cannot cost the migration itself.
    if reembed:
        print("Re-embedding rows with the current provider...")
        updated = asyncio.run(
            _reembed(
                destination,
                {"reflections_v2": ["content"], "conversations_v2": ["content"]},
            )
        )
        print(f"Re-embedded {updated} rows.")

    print(f"Working files left in {work} for inspection.")
    return 0


def main() -> int:
    """Parse the arguments and run the migration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=data_dir() / "reflection.duckdb",
        help="The DuckDB file to migrate.",
    )
    parser.add_argument(
        "--to-dim",
        type=int,
        default=DEFAULT_EMBEDDING_DIM,
        help="The target vector width.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write the rebuilt database. Defaults to "
        "<db>.migrated-<width>.duckdb. The input is never modified.",
    )
    parser.add_argument(
        "--re-embed",
        action="store_true",
        help="Re-embed the rows with the current provider after migrating.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the input file with the rebuild (backs it up first).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without changing anything.",
    )
    args = parser.parse_args()
    return migrate(
        args.db,
        args.to_dim,
        out_path=args.out,
        reembed=args.re_embed,
        replace=args.replace,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
