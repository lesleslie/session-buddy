#!/usr/bin/env python3
"""The adapter takes its vector width from the live schema.

DuckDB's embedding columns are fixed-size ``FLOAT[N]`` ARRAY columns and
cannot be widened in place, so a database written by an older build keeps
its old width. The adapter therefore reads the width back from the catalog
rather than trusting the canonical constant, so a database mid-migration
keeps working instead of failing every vector write.

Two things are pinned here:

* the *scenario* -- a database created at one width is still usable by a
  build whose canonical width differs; and
* the *scope* -- the width comes from the adapter's own database, not from
  another database attached to the same connection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.adapters import reflection_adapter_oneiric as reflection_module
from session_buddy.adapters.settings import ReflectionAdapterSettings
from session_buddy.memory.embedding_dim import DEFAULT_EMBEDDING_DIM

duckdb = pytest.importorskip("duckdb")

#: The width a build used before the canonical width moved to 768.
LEGACY_WIDTH = 4096


def _settings(path: Path, width: int) -> ReflectionAdapterSettings:
    """Build adapter settings for ``path`` at ``width``."""
    return ReflectionAdapterSettings(
        database_path=path,
        embedding_dim=width,
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )


def _embedding_width(adapter: reflection_module.ReflectionDatabaseAdapterOneiric) -> int | None:
    """Read the live width of the reflections_v2 embedding column."""
    row = adapter.conn.execute(
        "SELECT data_type FROM duckdb_columns() "
        "WHERE database_name = current_database() "
        "AND table_name = 'reflections_v2' "
        "AND column_name = 'embedding'"
    ).fetchone()
    if row is None:
        return None
    return int(str(row[0]).removeprefix("FLOAT[").removesuffix("]"))


@pytest.mark.asyncio
async def test_a_new_database_uses_the_canonical_width(tmp_path: Path) -> None:
    """A database with no history is created at the canonical width."""
    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(
        settings=_settings(tmp_path / "fresh.duckdb", DEFAULT_EMBEDDING_DIM)
    )
    await adapter.initialize()
    try:
        assert adapter.embedding_dim == DEFAULT_EMBEDDING_DIM
        assert _embedding_width(adapter) == DEFAULT_EMBEDDING_DIM
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_a_database_written_at_the_old_width_keeps_that_width(tmp_path: Path) -> None:
    """A database created by an older build keeps its own width.

    This is the migration case: the schema says 4096, the code says 768,
    and the adapter has to reconcile them in favour of the schema --
    otherwise every vector write fails the fixed-size ARRAY cast.
    """
    path = tmp_path / "legacy.duckdb"

    # An older build writes the database at the old width.
    writer = reflection_module.ReflectionDatabaseAdapterOneiric(
        settings=_settings(path, LEGACY_WIDTH)
    )
    await writer.initialize()
    try:
        assert _embedding_width(writer) == LEGACY_WIDTH
    finally:
        await writer.aclose()

    # A build whose canonical width differs adopts the live one.
    reader = reflection_module.ReflectionDatabaseAdapterOneiric(
        settings=_settings(path, DEFAULT_EMBEDDING_DIM)
    )
    await reader.initialize()
    try:
        assert reader.embedding_dim == LEGACY_WIDTH
        assert _embedding_width(reader) == LEGACY_WIDTH
    finally:
        await reader.aclose()


@pytest.mark.asyncio
async def test_the_width_comes_from_this_database_not_an_attached_one(tmp_path: Path) -> None:
    """An attached database must not supply the width.

    ``duckdb_columns()`` spans every attached database, and an attached
    database's rows come *first* in catalog order -- so an unscoped
    ``fetchone()`` would read the attached database's width and adopt it.
    """
    path = tmp_path / "own.duckdb"
    other_path = tmp_path / "other.duckdb"

    other = duckdb.connect(str(other_path))
    try:
        other.execute(f"CREATE TABLE reflections_v2 (embedding FLOAT[{DEFAULT_EMBEDDING_DIM}])")
    finally:
        other.close()

    adapter = reflection_module.ReflectionDatabaseAdapterOneiric(
        settings=_settings(path, LEGACY_WIDTH)
    )
    await adapter.initialize()
    try:
        assert adapter.embedding_dim == LEGACY_WIDTH

        conn = adapter.conn
        conn.execute("ATTACH ? AS other (READ_ONLY)", [str(other_path)])
        try:
            # Reset to the canonical width so the assertion below
            # proves the *adoption* happened, not that it never
            # needed to.
            adapter.embedding_dim = DEFAULT_EMBEDDING_DIM
            adapter._adopt_live_embedding_width()
            assert adapter.embedding_dim == LEGACY_WIDTH
        finally:
            conn.execute("DETACH other")
    finally:
        await adapter.aclose()
