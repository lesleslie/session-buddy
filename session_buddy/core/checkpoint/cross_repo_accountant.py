"""Orchestrator that captures cross-repo work during a session-buddy
checkpoint. Coordinates AmbientPuller (per-repo groups) + MergePrimitive
+ write. Never raises — returns a CrossRepoCaptureSummary for the
checkpoint log. Cross-repo accounting failures NEVER block the git
commit / handoff doc (G6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast

import duckdb
import yaml
from oneiric.core.logging import get_logger

from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
from session_buddy.core.checkpoint.manifest_resolver import resolve_manifest_path
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.core.ulid_generator import generate_ulid
from session_buddy.memory.cross_repo_work import (
    CrossRepoWorkRowCreate,
    UlidStr,
    WorkEntry,
)

_log = get_logger(__name__)


@dataclass
class CrossRepoCaptureSummary:
    repos_captured: int = 0
    entries_inserted: int = 0
    entries_deduplicated: int = 0
    ambient_failures: list[str] = field(default_factory=list)


class CheckpointCrossRepoAccountant:
    def __init__(
        self,
        *,
        ambient_puller: AmbientPuller,
        merge_primitive: MergePrimitive,
        conn: duckdb.DuckDBPyConnection,
    ) -> None:
        self._puller = ambient_puller
        self._merge = merge_primitive
        self._conn = conn

    async def capture(
        self,
        *,
        working_directory: Path,
        conversation_id: UlidStr,
        session_window_start: datetime,
        session_window_end: datetime,
    ) -> CrossRepoCaptureSummary:
        summary = CrossRepoCaptureSummary()
        try:
            grouped, failures = await self._puller.capture(
                working_directory=working_directory,
                conversation_id=conversation_id,
                session_window_start=session_window_start,
                session_window_end=session_window_end,
            )
        except Exception as exc:  # noqa: BLE001 — never raise (G6)
            _log.warning(
                "cross_repo_accountant_pull_failed",
                extra={"error": str(exc), "conversation_id": conversation_id},
            )
            return summary

        summary.ambient_failures = failures
        if not grouped:
            return summary

        # Resolve ecosystem.yaml once to get path/role per repo.
        # AmbientPuller already loaded it; we re-resolve to avoid
        # exposing the private _manifest_path accessor.
        ecosystem: dict[str, dict[str, str]] = {}
        manifest = resolve_manifest_path(self._puller._manifest_path)
        if manifest.exists():
            try:
                loaded = yaml.safe_load(manifest.read_text()) or {}
                ecosystem = (
                    loaded.get("ecosystem", {}) if isinstance(loaded, dict) else {}
                )
            except yaml.YAMLError, OSError:
                # YAMLError: parse failure. OSError: TOCTOU race,
                # PermissionError, IsADirectoryError, etc. G6 — never raise.
                ecosystem = {}

        rows: list[CrossRepoWorkRowCreate] = []
        for repo_name, entries in grouped.items():
            entry = ecosystem.get(repo_name, {})
            # AmbientPuller returns list[CommitEntry]; widen to the union
            # for CrossRepoWorkRowCreate (every CommitEntry is a WorkEntry).
            # Cast is safe — the list is treated as read-only here.
            work_entries: list[WorkEntry] = cast("list[WorkEntry]", entries)
            rows.append(
                CrossRepoWorkRowCreate(
                    id=generate_ulid(),
                    conversation_id=conversation_id,
                    repo_name=repo_name,
                    repo_path=entry.get("path", ""),
                    repo_role=entry.get("role"),
                    session_window_start=session_window_start,
                    session_window_end=session_window_end,
                    work_entries=work_entries,
                    contributor_sources=["ambient"],
                )
            )

        try:
            self._conn.execute("BEGIN TRANSACTION")
            _reads, ins, dead = self._merge.multi_merge(self._conn, rows)
            self._conn.execute("COMMIT")
        except Exception as exc:  # noqa: BLE001 — never raise (G6)
            try:
                self._conn.execute("ROLLBACK")
            except Exception as rb_exc:  # noqa: BLE001 — never raise (G6)
                # ROLLBACK itself raised (broken connection, autocommit, etc.).
                # Never let rollback failure propagate and break the
                # checkpoint log / handoff doc.
                _log.warning(
                    "cross_repo_accountant_rollback_failed",
                    extra={"error": str(rb_exc), "conversation_id": conversation_id},
                )
            _log.warning(
                "cross_repo_accountant_merge_failed",
                extra={"error": str(exc), "conversation_id": conversation_id},
            )
            return summary

        summary.entries_inserted += ins
        summary.entries_deduplicated += dead
        summary.repos_captured = len(grouped)
        return summary
