#!/usr/bin/env python3
"""Integration test for migration rollback and verify-only modes.

This test verifies that:
1. `migrate_v1_to_v2(rollback=True)` restores v1 tables from a backup
2. `migrate_v1_to_v2(rollback=True)` fails fast if the backup is missing
3. `migrate_v1_to_v2(verify_only=True)` copies data to v2 but does not drop v1

TDD: These tests are intentionally RED. The current `migrate_v1_to_v2`
signature only accepts `db_path` and `dry_run` keyword arguments. The
plan calls for adding `rollback` and `verify_only` flags wired to the
existing `create_backup`/`restore_backup` helpers at
`session_buddy/memory/migration.py:143-156`.

Failure mode: `TypeError: unexpected keyword argument 'rollback'`
(or `'verify_only'`).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterator

import pytest

# Add project root to path so `session_buddy.*` imports resolve
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def v1_db_path(tmp_path: Path) -> Path:
    """Synthesize a v1-format DuckDB on disk for migration tests.

    The shape mirrors what MIGRATION_SQL selects against (id, content,
    embedding, project, timestamp) so the forward migration can populate
    v2 successfully and the test can then assert rollback behaviour.
    The embedding column uses FLOAT[384] to match schema_v2.
    """
    pytest.importorskip("duckdb")
    import duckdb  # type: ignore[import-untyped]

    db_path = tmp_path / "source.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                content TEXT,
                embedding FLOAT[384],
                project TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Build a 384-dim zero vector
        zero_vec = "[" + ",".join(["0.0"] * 384) + "]"
        con.execute(
            "INSERT INTO conversations VALUES ('1', 'test content', ?, "
            "'test-project', CURRENT_TIMESTAMP)",
            [zero_vec],
        )
        con.execute(
            "CREATE TABLE reflections ("
            "id TEXT PRIMARY KEY, content TEXT, embedding FLOAT[384], "
            "tags TEXT[], timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute(
            "INSERT INTO reflections VALUES ('r1', 'test reflection', ?, "
            "['tag1'], CURRENT_TIMESTAMP)",
            [zero_vec],
        )
        con.commit()
    finally:
        con.close()
    return db_path


@pytest.fixture
def isolated_backup_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Point MAHAVISHNU_BACKUP_PATH at a tmp file so the migration
    can both write and discover a backup deterministically.

    Defaults to a non-existent path so tests that *want* a missing
    backup can override it later.
    """
    backup_path = tmp_path / "missing_backup.duckdb"
    monkeypatch.setenv("MAHAVISHNU_BACKUP_PATH", str(backup_path))
    yield backup_path


def _seed_backup_at(
    source_db: Path, backup_path: Path
) -> Path:
    """Copy a synthesised v1 DuckDB to the given backup path."""
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, backup_path)
    return backup_path


class TestMigrationRollback:
    """Test suite for `migrate_v1_to_v2` rollback behaviour."""

    def test_rollback_restores_v1_tables_from_backup(
        self,
        tmp_path: Path,
        v1_db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A successful migrate-then-rollback should restore v1 row count."""
        from session_buddy.memory import migration

        # Stage 1: copy v1 source into a target the migration will operate on
        target_db = tmp_path / "target.duckdb"
        shutil.copy2(v1_db_path, target_db)

        # Point the backup helpers at a deterministic tmp path and seed it
        # with the original v1 source so the rollback has something to restore
        backup_path = tmp_path / "backups" / "backup_v1.duckdb"
        _seed_backup_at(v1_db_path, backup_path)
        monkeypatch.setenv("MAHAVISHNU_BACKUP_PATH", str(backup_path))

        # Stage 2: forward-migrate target
        forward_result = migration.migrate_v1_to_v2(db_path=target_db)
        assert forward_result.success, (
            f"forward migration should succeed; got error={forward_result.error!r}"
        )

        # Sanity check: v2 now has the migrated row
        v2_count = migration.count_v2_conversations(migration._connect(target_db))
        assert v2_count == 1, f"v2 should hold the migrated row; got {v2_count}"

        # Stage 3: rollback. This signature is what makes the test RED today.
        rollback_result = migration.migrate_v1_to_v2(
            db_path=target_db, rollback=True
        )
        assert rollback_result.success, (
            f"rollback should succeed; got error={rollback_result.error!r}"
        )

        # Stage 4: assert v1 is back, v1 row count matches the source
        conn = migration._connect(target_db)
        try:
            v1_count = migration.count_v1_conversations(conn)
            assert v1_count == 1, (
                f"v1 should be restored to 1 row after rollback; got {v1_count}"
            )
        finally:
            conn.close()

    def test_rollback_fails_fast_when_backup_missing(
        self,
        tmp_path: Path,
        isolated_backup_path: Path,
    ) -> None:
        """Calling rollback with no backup present must raise, not silently
        succeed and not produce a half-migrated database."""
        from session_buddy.memory import migration

        # `isolated_backup_path` already points at a non-existent file.
        # The migration's `restore_backup` must raise a clear error.
        nonexistent_db = tmp_path / "nonexistent.duckdb"

        with pytest.raises((FileNotFoundError, Exception)) as exc_info:
            migration.migrate_v1_to_v2(
                db_path=nonexistent_db, rollback=True
            )

        # Prefer a custom error class if the implementation introduces one;
        # otherwise FileNotFoundError is acceptable per the plan.
        error_message = str(exc_info.value)
        assert "backup" in error_message.lower(), (
            f"error message must mention 'backup'; got: {error_message!r}"
        )

    def test_verify_only_copies_without_dropping(
        self,
        tmp_path: Path,
        v1_db_path: Path,
        isolated_backup_path: Path,
    ) -> None:
        """`verify_only=True` should populate v2 but leave v1 intact."""
        from session_buddy.memory import migration

        target_db = tmp_path / "verify_target.duckdb"
        shutil.copy2(v1_db_path, target_db)

        result = migration.migrate_v1_to_v2(
            db_path=target_db, verify_only=True
        )
        assert result.success, (
            f"verify-only migration should succeed; got error={result.error!r}"
        )

        conn = migration._connect(target_db)
        try:
            v1_count = migration.count_v1_conversations(conn)
            v2_count = migration.count_v2_conversations(conn)
            assert v1_count == 1, (
                f"v1 should still hold its row in verify-only mode; got {v1_count}"
            )
            assert v2_count == 1, (
                f"v2 should hold the copied row in verify-only mode; got {v2_count}"
            )
        finally:
            conn.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
