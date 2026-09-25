#!/usr/bin/env python3
"""One-shot backfill: populate ``source_session_id`` + ``source_artifact_uri`` from existing tags.

Background: Track A-ext2 (commit ``4235b634``) encoded provenance as a
``provenance:<json>`` entry inside the ``tags`` array — not as a separate
column. Now that Track C has added the first-class ``source_session_id`` /
``source_artifact_uri`` columns, legacy reflections with those tag entries
need their columns populated.

The scan walks every row whose columns are still NULL, decodes any
``provenance:<json>`` tag it finds, and updates the columns. The script is
idempotent — re-running produces the same final state because the
``WHERE source_session_id IS NULL OR source_artifact_uri IS NULL``
predicate filters out rows the previous run already populated.

Usage:
    python scripts/backfill_reflection_provenance.py [--db PATH] [--dry-run]

If ``--db`` is omitted, the script scans every ``*.duckdb`` file under the
canonical Session-Buddy data directory (resolved via
``session_buddy.di.config.SessionPaths.from_home``). The ``--dry-run`` flag
prints the planned update count without mutating the database.

Exit code: always 0. Errors are logged but do not abort the run, because
a partial backfill is more useful than a failed one for a one-shot tool.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger("session_buddy.backfill_provenance")

REFLECTIONS_TABLE = "reflections_v2"
PROVENANCE_PREFIX = "provenance:"


def _iter_tags(raw: object) -> list[object]:
    """Normalize a ``tags`` cell into a list-like object.

    DuckDB returns TEXT[] as a Python list, but defensive callers may
    pre-JSON-encode or pass a string. We accept either form so the
    script does not crash on legacy data.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return decoded
    return []


def _extract_from_tags(
    tags: list[object],
) -> tuple[str | None, str | None]:
    """Return the (session_id, artifact_uri) encoded in any provenance: tag."""
    session_id: str | None = None
    artifact_uri: str | None = None
    for tag in tags:
        if not isinstance(tag, str) or not tag.startswith(PROVENANCE_PREFIX):
            continue
        try:
            payload = json.loads(tag[len(PROVENANCE_PREFIX) :])
        except json.JSONDecodeError:
            logger.debug("Skipping malformed provenance tag: %r", tag)
            continue
        if not isinstance(payload, dict):
            continue
        if session_id is None and payload.get("source_session_id"):
            session_id = str(payload["source_session_id"])
        if artifact_uri is None and payload.get("source_artifact_uri"):
            artifact_uri = str(payload["source_artifact_uri"])
        if session_id is not None and artifact_uri is not None:
            break
    return session_id, artifact_uri


def backfill(db_path: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Backfill one DB file.

    Returns:
        (updated_count, skipped_count).
    """
    conn = duckdb.connect(str(db_path), read_only=False)
    try:
        rows = conn.execute(
            f"""
            SELECT id, tags FROM {REFLECTIONS_TABLE}
            WHERE source_session_id IS NULL OR source_artifact_uri IS NULL
            """
        ).fetchall()
    except duckdb.Error as exc:
        logger.warning(
            "Could not read %s from %s: %s",
            REFLECTIONS_TABLE,
            db_path,
            exc,
        )
        return 0, 0

    updated = 0
    skipped = 0
    for rid, tags_raw in rows:
        tags = _iter_tags(tags_raw)
        sid, uri = _extract_from_tags(tags)
        if sid is None and uri is None:
            skipped += 1
            continue
        if dry_run:
            updated += 1
            continue
        conn.execute(
            f"""
            UPDATE {REFLECTIONS_TABLE}
            SET source_session_id = ?, source_artifact_uri = ?
            WHERE id = ?
            """,
            [sid, uri, rid],
        )
        updated += 1
    return updated, skipped


def discover_db_paths(data_dir: Path) -> list[Path]:
    """Find every ``*.duckdb`` file under ``data_dir``."""
    if not data_dir.exists():
        return []
    return sorted(data_dir.rglob("*.duckdb"))


def main(
    db: Path | None,
    *,
    dry_run: bool,
    data_dir: Path | None = None,
) -> int:
    """Run the backfill. Returns total rows updated (across all DBs)."""
    if db is not None:
        db_paths = [db]
    else:
        from session_buddy.di.config import SessionPaths

        paths = SessionPaths.from_home()
        target_dir = data_dir or paths.data_dir
        db_paths = discover_db_paths(target_dir)
        if not db_paths:
            print(f"No DuckDB files found under {target_dir}")
            return 0
        print(f"Found {len(db_paths)} DuckDB file(s) under {target_dir}")

    total_updated = 0
    total_skipped = 0
    for db_path in db_paths:
        if dry_run:
            print(f"  [dry-run] scanning {db_path}")
        try:
            updated, skipped = backfill(db_path, dry_run=dry_run)
        except Exception:
            logger.exception("Backfill failed for %s", db_path)
            continue
        if updated or skipped:
            mode = "[dry-run] " if dry_run else ""
            print(
                f"  {mode}{db_path}: updated={updated} skipped={skipped}"
            )
        total_updated += updated
        total_skipped += skipped

    print(
        "Done. "
        f"Total rows updated: {total_updated}; total rows skipped: {total_skipped}"
    )
    return total_updated


def cli() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "Backfill provenance",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help=(
            "Path to a single DuckDB file. Omit to scan every *.duckdb "
            "under the canonical Session-Buddy data directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned update count without mutating any database.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging for malformed-tag diagnostics.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    cli()
