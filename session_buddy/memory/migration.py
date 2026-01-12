"""
Schema migration and versioning for conversations/reflections v1 → v2.

Implements:
- Version detection and history logging
- Idempotent creation of v2 schema
- Best-effort migration preserving ONNX vectors
- Backup/rollback helpers (filesystem copy)
"""

from __future__ import annotations

import json
import shutil
import typing as t
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

from session_buddy.memory.schema_v2 import MIGRATION_SQL, SCHEMA_V2_SQL
from session_buddy.settings import get_database_path

SCHEMA_META_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    from_version TEXT,
    to_version TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT, -- pending|success|failed
    stats TEXT,  -- JSON-encoded stats for portability
    error TEXT
);
"""


@dataclass(slots=True)
class MigrationResult:
    success: bool
    error: str | None = None
    stats: dict[str, t.Any] | None = None
    duration_seconds: float | None = None


def _connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})


def _ensure_meta(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(SCHEMA_META_SQL)


def _get_schema_version(conn: duckdb.DuckDBPyConnection) -> str:
    """Return 'v2' if v2 tables exist, 'v1' if only legacy tables exist, else 'unknown'."""
    _ensure_meta(conn)
    # Try meta table first
    from contextlib import suppress

    with suppress(Exception):
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        if row and isinstance(row[0], str):
            return row[0]

    # Fallback to table existence checks
    v2_tables = {
        "conversations_v2",
        "reflections_v2",
        "memory_entities",
        "memory_relationships",
        "memory_promotions",
        "memory_access_log",
    }
    v2_count = 0
    for name in v2_tables:
        try:
            conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
            v2_count += 1
        except Exception:
            continue
    if v2_count >= 2:
        return "v2"

    # Check for legacy v1 tables
    try:
        conn.execute("SELECT 1 FROM conversations LIMIT 1")
        return "v1"
    except Exception:
        return "unknown"


def get_schema_version(db_path: Path | None = None) -> str:
    path = Path(db_path) if db_path else get_database_path()
    with _connect(path) as conn:
        return _get_schema_version(conn)


def update_schema_version(conn: duckdb.DuckDBPyConnection, version: str) -> None:
    _ensure_meta(conn)
    conn.execute(
        """
        INSERT INTO schema_meta(key, value, updated_at)
        VALUES ('schema_version', ?, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=NOW()
        """,
        [version],
    )


def create_v2_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(SCHEMA_V2_SQL)


def count_v1_conversations(conn: duckdb.DuckDBPyConnection) -> int:
    try:
        row = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def count_v2_conversations(conn: duckdb.DuckDBPyConnection) -> int:
    try:
        row = conn.execute("SELECT COUNT(*) FROM conversations_v2").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def create_backup(backup_dir: Path | None = None) -> Path:
    """Create a timestamped DB backup and return path to the backup file."""
    db_path = get_database_path()
    backup_root = backup_dir or db_path.parent
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"backup_v1_{ts}.duckdb"
    shutil.copy2(db_path, backup_path)
    return backup_path


def restore_backup(backup_path: Path) -> None:
    db_path = get_database_path()
    shutil.copy2(backup_path, db_path)


def needs_migration(db_path: Path | None = None) -> bool:
    version = get_schema_version(db_path)
    return version == "v1"


def migrate_v1_to_v2(
    *, db_path: Path | None = None, dry_run: bool = False
) -> MigrationResult:
    """Migrate legacy v1 data to v2 schema.

    - Creates v2 schema if missing
    - Best-effort categorization via MIGRATION_SQL
    - Preserves existing embeddings
    - Updates schema_meta on success
    """
    start = datetime.now()
    path = Path(db_path) if db_path else get_database_path()

    with _connect(path) as conn:
        _ensure_meta(conn)
        current = _get_schema_version(conn)
        if current == "v2":
            return MigrationResult(
                success=True,
                stats={"skipped": True, "reason": "already_v2"},
                duration_seconds=0.0,
            )

        mig_id = f"mig_{start.strftime('%Y%m%d_%H%M%S_%f')}"

        if dry_run:
            return _handle_dry_run(conn, start)
        try:
            return _perform_migration(conn, current, mig_id, start)
        except Exception as e:
            return _handle_migration_exception(conn, mig_id, start, e)


def _handle_dry_run(
    conn: duckdb.DuckDBPyConnection, start: datetime
) -> MigrationResult:
    """Handle dry run of migration."""
    v1_count = count_v1_conversations(conn)
    stats = {"preview": True, "would_migrate": v1_count}
    return MigrationResult(
        success=True,
        stats=stats,
        duration_seconds=(datetime.now() - start).total_seconds(),
    )


def _perform_migration(
    conn: duckdb.DuckDBPyConnection, current: str, mig_id: str, start: datetime
) -> MigrationResult:
    """Perform the actual migration."""
    # Record migration row (pending) for real migration
    conn.execute(
        """
        INSERT INTO schema_migrations(id, from_version, to_version, started_at, status)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'pending')
        """,
        [mig_id, current, "v2"],
    )

    # Create v2 schema
    create_v2_schema(conn)

    # Execute data migration (best-effort); run statements separately
    for stmt in MIGRATION_SQL.split(";"):
        sql = stmt.strip()
        if not sql:
            continue
        conn.execute(sql)

    v1_count = count_v1_conversations(conn)
    v2_count = count_v2_conversations(conn)

    if v2_count >= v1_count:
        return _handle_migration_success(conn, mig_id, start, v1_count, v2_count)
    return _handle_migration_failure(conn, mig_id, start, v1_count, v2_count)


def _handle_migration_success(
    conn: duckdb.DuckDBPyConnection,
    mig_id: str,
    start: datetime,
    v1_count: int,
    v2_count: int,
) -> MigrationResult:
    """Handle successful migration completion."""
    update_schema_version(conn, "v2")
    stats = {"migrated": v2_count, "source": v1_count}
    conn.execute(
        "UPDATE schema_migrations SET status='success', completed_at=CURRENT_TIMESTAMP, stats=? WHERE id=?",
        [json.dumps(stats), mig_id],
    )
    return MigrationResult(
        success=True,
        stats=stats,
        duration_seconds=(datetime.now() - start).total_seconds(),
    )


def _handle_migration_failure(
    conn: duckdb.DuckDBPyConnection,
    mig_id: str,
    start: datetime,
    v1_count: int,
    v2_count: int,
) -> MigrationResult:
    """Handle migration failure."""
    err = f"Missing data after migration: v1={v1_count}, v2={v2_count}"
    conn.execute(
        "UPDATE schema_migrations SET status='failed', completed_at=CURRENT_TIMESTAMP, error=? WHERE id=?",
        [err, mig_id],
    )
    return MigrationResult(
        success=False,
        error=err,
        stats={"v1": v1_count, "v2": v2_count},
        duration_seconds=(datetime.now() - start).total_seconds(),
    )


def _handle_migration_exception(
    conn: duckdb.DuckDBPyConnection, mig_id: str, start: datetime, exception: Exception
) -> MigrationResult:
    """Handle migration exception."""
    with suppress(Exception):
        conn.execute(
            "UPDATE schema_migrations SET status='failed', completed_at=CURRENT_TIMESTAMP, error=? WHERE id=?",
            [str(exception), mig_id],
        )
    return MigrationResult(
        success=False,
        error=str(exception),
        duration_seconds=(datetime.now() - start).total_seconds(),
    )


def get_migration_status(db_path: Path | None = None) -> dict[str, t.Any]:
    path = Path(db_path) if db_path else get_database_path()
    with _connect(path) as conn:
        _ensure_meta(conn)
        # Basic stats
        try:
            mig_history = conn.execute(
                "SELECT id, from_version, to_version, started_at, completed_at, status FROM schema_migrations ORDER BY started_at DESC LIMIT 10"
            ).fetchall()
        except Exception:
            mig_history = []

        return {
            "current_version": _get_schema_version(conn),
            "migration_history": [
                {
                    "id": r[0],
                    "from": r[1],
                    "to": r[2],
                    "started_at": str(r[3]),
                    "completed_at": str(r[4]) if r[4] else None,
                    "status": r[5],
                }
                for r in mig_history
            ],
            "counts": {
                "v1_conversations": count_v1_conversations(conn),
                "v2_conversations": count_v2_conversations(conn),
            },
        }


__all__ = [
    "MigrationResult",
    "create_backup",
    "create_v2_schema",
    "get_migration_status",
    "get_schema_version",
    "migrate_v1_to_v2",
    "needs_migration",
    "restore_backup",
]
