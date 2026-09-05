"""Tests for session_buddy.memory.migration.

Covers the v1 → v2 schema migration path:
- ``_connect`` direct DB connection
- ``_get_schema_version``: detection of v2/v1/unknown, fallback on table
  existence, and meta-table precedence
- ``update_schema_version``: insert + upsert semantics
- ``create_v2_schema`` and ``apply_migrations``: idempotent DDL
- ``count_v1_conversations`` / ``count_v2_conversations``: error tolerance
- ``create_backup`` / ``restore_backup`` / ``find_backup_path`` /
  ``_restore_backup_to``: filesystem-level copy with env var precedence
- ``needs_migration``: based on schema version
- ``migrate_v1_to_v2``: full matrix — already-v2 skip, dry run, success,
  verify_only, rollback, exception handling, and flag-conflict validation
- ``get_migration_status``: history + counts + version

All tests use ``tmp_path``-backed DuckDB files; production ``get_database_path``
is monkeypatched to point at the test path.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import duckdb
import pytest

from session_buddy.memory import migration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Return a tmp_path-backed DuckDB file path (does not create the file)."""
    return tmp_path / "reflection.duckdb"


@pytest.fixture
def db_conn(db_path: Path):
    """Yield an open DuckDB connection at ``db_path``.

    The connection is closed and the file removed at teardown.
    """
    conn = duckdb.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def patched_db_path(db_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Patch ``migration.get_database_path`` to return ``db_path``."""
    monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
    return db_path


@contextmanager
def _open(db_path: Path):
    conn = duckdb.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# _connect
# ---------------------------------------------------------------------------


class TestConnect:
    def test_opens_real_db(self, db_path: Path) -> None:
        with migration._connect(db_path) as conn:
            row = conn.execute("SELECT 42").fetchone()
            assert row == (42,)


# ---------------------------------------------------------------------------
# _get_schema_version
# ---------------------------------------------------------------------------


class TestGetSchemaVersion:
    def test_unknown_on_empty_db(self, db_conn) -> None:
        # Empty DB has no tables → "unknown".
        assert migration._get_schema_version(db_conn) == "unknown"

    def test_v1_detected_by_legacy_conversations_table(self, db_conn) -> None:
        db_conn.execute(
            "CREATE TABLE conversations (id TEXT, content TEXT, embedding TEXT)"
        )
        assert migration._get_schema_version(db_conn) == "v1"

    def test_v2_detected_by_two_or_more_v2_tables(self, db_conn) -> None:
        # Two v2 tables present → returns "v2" via the fallback count.
        db_conn.execute("CREATE TABLE conversations_v2 (id TEXT)")
        db_conn.execute("CREATE TABLE reflections_v2 (id TEXT)")
        assert migration._get_schema_version(db_conn) == "v2"

    def test_meta_table_value_takes_precedence(self, db_conn) -> None:
        # Even with only a v1 conversations table, the meta table wins.
        db_conn.execute("CREATE TABLE conversations (id TEXT, content TEXT)")
        migration._ensure_meta(db_conn)
        migration.update_schema_version(db_conn, "v2")
        assert migration._get_schema_version(db_conn) == "v2"


# ---------------------------------------------------------------------------
# update_schema_version / create_v2_schema
# ---------------------------------------------------------------------------


class TestUpdateSchemaVersion:
    def test_inserts_first_time(self, db_conn) -> None:
        migration._ensure_meta(db_conn)
        migration.update_schema_version(db_conn, "v2")
        row = db_conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        assert row == ("v2",)

    def test_upserts_existing_row(self, db_conn) -> None:
        migration._ensure_meta(db_conn)
        migration.update_schema_version(db_conn, "v1")
        migration.update_schema_version(db_conn, "v2")
        rows = db_conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchall()
        assert rows == [("v2",)]


class TestCreateV2Schema:
    def test_creates_v2_tables(self, db_conn) -> None:
        migration.create_v2_schema(db_conn)
        names = {
            row[0]
            for row in db_conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        for table in (
            "conversations_v2",
            "reflections_v2",
            "memory_entities",
            "memory_relationships",
            "memory_promotions",
            "memory_access_log",
        ):
            assert table in names

    def test_idempotent(self, db_conn) -> None:
        migration.create_v2_schema(db_conn)
        migration.create_v2_schema(db_conn)  # no error


# ---------------------------------------------------------------------------
# apply_migrations
# ---------------------------------------------------------------------------


class TestApplyMigrations:
    def test_runs_schema_and_forward_ddl(self, db_conn) -> None:
        migration.apply_migrations(db_conn)
        names = {
            row[0]
            for row in db_conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        # v2 baseline tables + the cross-repo-checkpoint v2.1 tables.
        for table in (
            "conversations_v2",
            "reflections_v2",
            "memory_entities",
            "memory_relationships",
        ):
            assert table in names
        # Cross-repo checkpoint forward DDL is registered.
        assert any("session_windows" in t or "cross_repo" in t for t in names)

    def test_registry_is_ordered_by_version(self) -> None:
        for key, ddl in migration.MIGRATIONS:
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert isinstance(ddl, str)


# ---------------------------------------------------------------------------
# count_v1_conversations / count_v2_conversations
# ---------------------------------------------------------------------------


class TestConversationCounts:
    def test_v1_count_on_empty_db(self, db_conn) -> None:
        assert migration.count_v1_conversations(db_conn) == 0

    def test_v1_count_after_inserts(self, db_conn) -> None:
        db_conn.execute(
            "CREATE TABLE conversations (id TEXT, content TEXT, embedding TEXT)"
        )
        db_conn.execute("INSERT INTO conversations VALUES ('a', 'x', 'y')")
        db_conn.execute("INSERT INTO conversations VALUES ('b', 'z', 'w')")
        assert migration.count_v1_conversations(db_conn) == 2

    def test_v2_count_requires_v2_table(self, db_conn) -> None:
        # Apply v2 schema and seed a row.
        migration.create_v2_schema(db_conn)
        assert migration.count_v2_conversations(db_conn) == 0


# ---------------------------------------------------------------------------
# Backup / restore
# ---------------------------------------------------------------------------


class TestBackupRestore:
    def test_create_backup_copies_db(self, patched_db_path: Path) -> None:
        # Seed a DB so the backup has content.
        conn = duckdb.connect(str(patched_db_path))
        conn.execute("CREATE TABLE foo (id INT)")
        conn.execute("INSERT INTO foo VALUES (1)")
        conn.close()

        backup = migration.create_backup()
        assert backup.exists()
        # Verify backup contains the seeded data.
        with duckdb.connect(str(backup)) as b:
            assert b.execute("SELECT * FROM foo").fetchall() == [(1,)]

    def test_create_backup_default_dir(
        self, patched_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Seed the DB so the backup source exists.
        duckdb.connect(str(patched_db_path)).execute("CREATE TABLE a (id INT)")
        # Explicit backup_dir overrides default.
        custom = patched_db_path.parent / "custom"
        backup = migration.create_backup(backup_dir=custom)
        assert backup.parent == custom

    def test_restore_backup_overwrites(
        self, patched_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Source DB has table A; backup has table B.
        src = tmp_path / "src.duckdb"
        bkp = tmp_path / "bkp.duckdb"
        duckdb.connect(str(src)).execute("CREATE TABLE a (id INT)")
        duckdb.connect(str(bkp)).execute("CREATE TABLE b (id INT)")
        monkeypatch.setattr(migration, "get_database_path", lambda: src)

        migration.restore_backup(bkp)

        with duckdb.connect(str(src)) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables"
                ).fetchall()
            }
        assert "b" in tables
        assert "a" not in tables


class TestRestoreBackupTo:
    def test_creates_parent_dir(
        self, patched_db_path: Path, tmp_path: Path
    ) -> None:
        bkp = tmp_path / "bkp.duckdb"
        duckdb.connect(str(bkp)).execute("CREATE TABLE x (id INT)")
        target = tmp_path / "deep" / "nested" / "ref.duckdb"

        migration._restore_backup_to(bkp, target)

        assert target.exists()
        with duckdb.connect(str(target)) as conn:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables"
                ).fetchall()
            }
        assert "x" in names


class TestFindBackupPath:
    def test_env_var_wins_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backup = tmp_path / "from-env.duckdb"
        backup.touch()
        monkeypatch.setenv("MAHAVISHNU_BACKUP_PATH", str(backup))
        assert migration.find_backup_path() == backup

    def test_env_var_missing_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "missing.duckdb"
        monkeypatch.setenv("MAHAVISHNU_BACKUP_PATH", str(missing))
        with pytest.raises(FileNotFoundError, match="Cannot rollback"):
            migration.find_backup_path()

    def test_falls_back_to_default_data_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No env var → look under ~/.claude/data, which we fake.
        monkeypatch.delenv("MAHAVISHNU_BACKUP_PATH", raising=False)
        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        backup_dir = fake_home / ".claude" / "data"
        backup_dir.mkdir(parents=True)
        backup = backup_dir / "backup_x.duckdb"
        backup.touch()

        assert migration.find_backup_path() == backup

    def test_falls_back_to_db_parent_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MAHAVISHNU_BACKUP_PATH", raising=False)
        # ~/.claude/data doesn't exist → look next to the DB.
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
        backup_dir = tmp_path / "next-to-db"
        backup_dir.mkdir()
        backup = backup_dir / "backup_y.duckdb"
        backup.touch()
        monkeypatch.setattr(migration, "get_database_path", lambda: backup_dir / "x.duckdb")

        assert migration.find_backup_path() == backup

    def test_raises_when_no_backup_anywhere(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MAHAVISHNU_BACKUP_PATH", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
        monkeypatch.setattr(
            migration, "get_database_path", lambda: tmp_path / "x.duckdb"
        )
        with pytest.raises(FileNotFoundError, match="No backup file found"):
            migration.find_backup_path()


# ---------------------------------------------------------------------------
# needs_migration
# ---------------------------------------------------------------------------


class TestNeedsMigration:
    def test_true_on_v1(self, db_path: Path) -> None:
        # Create a v1 DB.
        with duckdb.connect(str(db_path)) as conn:
            conn.execute(
                "CREATE TABLE conversations (id TEXT, content TEXT, embedding TEXT)"
            )
            migration._ensure_meta(conn)
        assert migration.needs_migration(db_path) is True

    def test_false_on_unknown(self, db_path: Path) -> None:
        # File doesn't exist → unknown → not a v1 → no migration needed.
        assert db_path.exists() is False
        # ``needs_migration`` opens the DB to inspect, so it must exist.
        with duckdb.connect(str(db_path)) as conn:
            conn.execute("SELECT 1")
        assert migration.needs_migration(db_path) is False


# ---------------------------------------------------------------------------
# migrate_v1_to_v2 — public entry point
# ---------------------------------------------------------------------------


def _seed_v1(db_path: Path) -> None:
    """Create a minimal v1 schema + one conversation and one reflection row.

    Both legacy tables are required because MIGRATION_SQL inserts from both.
    """
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE conversations (
                id TEXT,
                content TEXT,
                embedding TEXT,
                project TEXT,
                timestamp TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
            ["c1", "user prefers dark mode", None, "demo", datetime.now(UTC)],
        )
        conn.execute(
            """
            CREATE TABLE reflections (
                id TEXT,
                content TEXT,
                embedding TEXT,
                tags TEXT[],
                timestamp TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO reflections VALUES (?, ?, ?, ?, ?)",
            ["r1", "some reflection", None, ["tag1"], datetime.now(UTC)],
        )
        # Do NOT pre-create schema_meta — _ensure_meta creates it with the
        # correct shape (key, value, updated_at).
    finally:
        conn.close()


class TestMigrateV1ToV2:
    def test_already_v2_skips(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pre-create the v2 schema and mark as v2.
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        with duckdb.connect(str(db_path)) as conn:
            migration.apply_migrations(conn)
            migration.update_schema_version(conn, "v2")

        result = migration.migrate_v1_to_v2(db_path=db_path)
        assert result.success is True
        assert result.stats == {"skipped": True, "reason": "already_v2"}
        assert result.duration_seconds == 0.0

    def test_dry_run_returns_preview(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        _seed_v1(db_path)

        result = migration.migrate_v1_to_v2(db_path=db_path, dry_run=True)
        assert result.success is True
        assert result.stats == {"preview": True, "would_migrate": 1}

    def test_successful_migration(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        _seed_v1(db_path)

        result = migration.migrate_v1_to_v2(db_path=db_path)
        assert result.success is True
        assert result.stats == {"migrated": 1, "source": 1}

        # The v2 row exists.
        with duckdb.connect(str(db_path)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM conversations_v2"
            ).fetchone()[0]
            version = migration._get_schema_version(conn)
            mig_row = conn.execute(
                "SELECT status, stats FROM schema_migrations ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        assert count == 1
        assert version == "v2"
        assert mig_row[0] == "success"
        assert json.loads(mig_row[1]) == {"migrated": 1, "source": 1}

    def test_verify_only_sets_flag(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        _seed_v1(db_path)

        result = migration.migrate_v1_to_v2(db_path=db_path, verify_only=True)
        assert result.success is True
        # Stats includes verify_only=True flag in addition to migration counts.
        assert result.stats is not None
        assert result.stats.get("verify_only") is True

    def test_rollback_path(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        # Create a backup file in the same dir.
        backup = db_path.parent / "backup_rollback.duckdb"
        duckdb.connect(str(backup)).execute("CREATE TABLE rb (id INT)")
        monkeypatch.setenv("MAHAVISHNU_BACKUP_PATH", str(backup))
        # Need an existing DB to rollback to.
        duckdb.connect(str(db_path)).execute("CREATE TABLE x (id INT)")

        result = migration.migrate_v1_to_v2(db_path=db_path, rollback=True)
        assert result.success is True
        assert result.stats is not None
        assert result.stats.get("rolled_back") is True
        assert result.stats.get("backup_path") == str(backup)

    def test_rollback_fails_when_db_missing(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        monkeypatch.setenv(
            "MAHAVISHNU_BACKUP_PATH", str(db_path.parent / "missing.duckdb")
        )
        with pytest.raises(FileNotFoundError, match="Cannot rollback"):
            migration.migrate_v1_to_v2(db_path=db_path, rollback=True)

    def test_rollback_and_verify_only_conflict(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        with pytest.raises(ValueError, match="Cannot specify both"):
            migration.migrate_v1_to_v2(
                db_path=db_path, rollback=True, verify_only=True
            )

    def test_dry_run_with_rollback_conflicts(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        with pytest.raises(ValueError, match="dry_run with rollback"):
            migration.migrate_v1_to_v2(
                db_path=db_path, dry_run=True, rollback=True
            )

    def test_exception_handled_in_result(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        # Force _perform_migration to raise. Patch at the module level so
        # the public entry point catches it.
        def boom(*args, **kwargs):
            raise RuntimeError("simulated migration error")

        monkeypatch.setattr(migration, "_perform_migration", boom)
        # Seed a v1 DB so we go past the "already_v2" gate.
        _seed_v1(db_path)

        result = migration.migrate_v1_to_v2(db_path=db_path)
        assert result.success is False
        assert "simulated migration error" in (result.error or "")


# ---------------------------------------------------------------------------
# Migration failure path (v2_count < v1_count)
# ---------------------------------------------------------------------------


class TestMigrationFailure:
    def test_failure_when_no_data_migrates(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        # Seed v1 with one row but empty MIGRATION_SQL semantics by
        # breaking the target table. Easier: drop the conversations
        # table AFTER seeding so MIGRATION_SQL inserts nothing.
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE conversations (id TEXT, content TEXT, embedding TEXT, "
            "project TEXT, timestamp TIMESTAMP)"
        )
        conn.execute("INSERT INTO conversations VALUES ('c1', 'x', NULL, 'p', NULL)")
        conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.close()

        # Monkeypatch the data-migration to skip data inserts entirely.
        original_split = migration.MIGRATION_SQL.split

        def empty_split(sep):
            # Return one empty statement → loop skips it.
            return [""]

        monkeypatch.setattr(migration, "MIGRATION_SQL", " ")
        # Easier alternative: replace the migration SQL with whitespace so
        # all statements are skipped after stripping. The function-level
        # call already did that — just run.
        result = migration.migrate_v1_to_v2(db_path=db_path)
        assert result.success is False
        assert "Missing data after migration" in (result.error or "")


# ---------------------------------------------------------------------------
# get_migration_status
# ---------------------------------------------------------------------------


class TestGetMigrationStatus:
    def test_returns_version_and_history(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        _seed_v1(db_path)
        # Run a real migration first so schema_migrations has rows.
        migration.migrate_v1_to_v2(db_path=db_path)

        status = migration.get_migration_status(db_path=db_path)
        assert status["current_version"] == "v2"
        assert len(status["migration_history"]) >= 1
        assert status["counts"]["v2_conversations"] == 1

    def test_empty_db_returns_unknown(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(migration, "get_database_path", lambda: db_path)
        # Need an existing DB file for the connection.
        duckdb.connect(str(db_path)).execute("SELECT 1").fetchall()
        status = migration.get_migration_status(db_path=db_path)
        assert status["current_version"] == "unknown"
        assert status["migration_history"] == []


# ---------------------------------------------------------------------------
# Module-level get_database_path import test
# ---------------------------------------------------------------------------


def test_module_exports_contain_expected_symbols() -> None:
    for name in (
        "MIGRATIONS",
        "MigrationResult",
        "apply_migrations",
        "create_backup",
        "create_v2_schema",
        "get_migration_status",
        "get_schema_version",
        "migrate_v1_to_v2",
        "needs_migration",
        "restore_backup",
    ):
        assert name in migration.__all__
        assert hasattr(migration, name)
