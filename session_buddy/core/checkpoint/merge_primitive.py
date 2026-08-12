"""Atomic merge primitive for cross_repo_work_v2.

Performs read-dedup-write inside a CALLER-MANAGED transaction. The merge
primitive does NOT BEGIN or COMMIT — the caller (CrossRepoPusher or
CheckpointCrossRepoAccountant) wraps the entire batch in one
BEGIN TRANSACTION / COMMIT / ROLLBACK to deliver multi-repo atomicity.

Idempotency on (conversation_id, repo_name, sha) is enforced HERE,
not by a schema UNIQUE constraint (DuckDB JSON columns can't deduplicate
elements natively).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime

import duckdb
from oneiric.core.logging import get_logger
from pydantic import TypeAdapter

from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
    CrossRepoWorkRowRead,
    PlanRefEntry,
    WorkEntry,
)

_log = get_logger(__name__)

# TypeAdapter for tagged-union WorkEntry — Annotated[Union, Field(discriminator=...)]
# is not a class and has no .model_validate, so we use TypeAdapter explicitly.
_work_entry_adapter: TypeAdapter[WorkEntry] = TypeAdapter(WorkEntry)


def _coerce_aware(value: datetime) -> datetime:
    """Defensive: DuckDB returns tz-aware datetimes for TIMESTAMP WITH TIME ZONE
    (production schema), but a caller might construct a CrossRepoWorkRowCreate
    with a naive datetime. Normalize to a comparable form by treating naive as
    UTC. This lets max(naive, aware) succeed without raising TypeError."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _dedup_key(entry: WorkEntry) -> tuple[str, str]:
    if isinstance(entry, CommitEntry):
        return ("commit", entry.sha)
    if isinstance(entry, PlanRefEntry):
        return ("plan_ref", entry.plan_path)
    raise TypeError(f"unsupported entry kind: {type(entry).__name__}")


def _merge_entries(
    existing: list[WorkEntry],
    incoming: list[WorkEntry],
) -> tuple[list[WorkEntry], int, int]:
    by_key: dict[tuple[str, str], WorkEntry] = {_dedup_key(e): e for e in existing}
    inserted = 0
    deduplicated = 0
    for entry in incoming:
        key = _dedup_key(entry)
        if key in by_key:
            existing_entry = by_key[key]
            winner = entry
            if (
                existing_entry.provenance == "explicit"
                and entry.provenance == "ambient"
            ):
                winner = existing_entry  # ambient suppressed by existing explicit
                _log.debug("cross_repo_dedup_suppressed_ambient", extra={"sha": key[1]})
            else:
                # Merge fields per spec: max files_changed_count, first-observed timestamp.
                if isinstance(winner, CommitEntry) and isinstance(
                    existing_entry, CommitEntry
                ):
                    max_fcc = max(
                        existing_entry.files_changed_count or 0,
                        winner.files_changed_count or 0,
                    )
                    first_ts = existing_entry.timestamp or winner.timestamp
                    # model_copy(update=...) avoids the dict-spread kwarg
                    # union that breaks ty's field-type narrowing — Pydantic
                    # validates each override against the model's field schema
                    # directly rather than via dict-literal inference.
                    winner = winner.model_copy(
                        update={
                            "files_changed_count": max_fcc,
                            "timestamp": first_ts,
                        }
                    )
            by_key[key] = winner
            deduplicated += 1
        else:
            by_key[key] = entry
            inserted += 1
    return list(by_key.values()), inserted, deduplicated


def _union_provenance(existing: Iterable[str], incoming: Iterable[str]) -> list[str]:
    # dict.fromkeys preserves insertion order while collapsing duplicates
    # in a single C-level pass — both faster and clearer than the
    # list-membership accumulator.
    return list(dict.fromkeys([*existing, *incoming]))


class MergePrimitive:
    """Atomic read-dedup-write primitive for cross_repo_work_v2.

    Single public method: ``multi_merge``. Caller opens BEGIN TRANSACTION,
    passes rows; all-or-nothing on any error (caller ROLLBACKs).
    """

    def multi_merge(
        self,
        conn: duckdb.DuckDBPyConnection,
        rows: list[CrossRepoWorkRowCreate],
    ) -> tuple[list[CrossRepoWorkRowRead], int, int]:
        """Caller-managed transaction. Loops over rows, performing read-dedup-write
        for each. All-or-nothing (caller ROLLBACKs on any error)."""
        results: list[CrossRepoWorkRowRead] = []
        total_ins = 0
        total_ded = 0
        for incoming in rows:
            read_row = self._read_dedup_write(conn, incoming)
            results.append(read_row[0])
            total_ins += read_row[1]
            total_ded += read_row[2]
        return results, total_ins, total_ded

    def _read_dedup_write(
        self,
        conn: duckdb.DuckDBPyConnection,
        incoming: CrossRepoWorkRowCreate,
    ) -> tuple[CrossRepoWorkRowRead, int, int]:
        row = conn.execute(
            "SELECT work_entries, contributor_sources, session_window_end "
            "FROM cross_repo_work_v2 "
            "WHERE conversation_id = ? AND repo_name = ?",
            [incoming.conversation_id, incoming.repo_name],
        ).fetchone()

        if row is None:
            merged_entries = incoming.work_entries.copy()
            inserted = len(merged_entries)
            deduplicated = 0
            merged_provenance = incoming.contributor_sources.copy()
            new_session_window_end = incoming.session_window_end
        else:
            existing_entries_raw, existing_prov_raw, existing_end = row
            existing_entries = [
                _work_entry_adapter.validate_python(e)
                for e in json.loads(existing_entries_raw)
            ]
            existing_prov = json.loads(existing_prov_raw)
            merged_entries, inserted, deduplicated = _merge_entries(
                existing_entries, incoming.work_entries.copy()
            )
            merged_provenance = _union_provenance(
                existing_prov, incoming.contributor_sources
            )
            new_session_window_end = max(
                _coerce_aware(existing_end), _coerce_aware(incoming.session_window_end)
            )

        entries_json = json.dumps([e.model_dump(mode="json") for e in merged_entries])
        prov_json = json.dumps(merged_provenance)
        conn.execute(
            "INSERT INTO cross_repo_work_v2 ("
            "id, conversation_id, repo_name, repo_path, repo_role, "
            "session_window_start, session_window_end, "
            "work_entries, contributor_sources, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, "
            "CAST(? AS JSON), CAST(? AS JSON), NOW(), NOW()) "
            "ON CONFLICT (conversation_id, repo_name) DO UPDATE SET "
            "work_entries = CAST(? AS JSON), "
            "contributor_sources = CAST(? AS JSON), "
            "session_window_end = GREATEST("
            "cross_repo_work_v2.session_window_end, excluded.session_window_end"
            "), updated_at = NOW()",
            [
                incoming.id,
                incoming.conversation_id,
                incoming.repo_name,
                incoming.repo_path,
                incoming.repo_role,
                incoming.session_window_start,
                new_session_window_end,
                entries_json,
                prov_json,
                entries_json,
                prov_json,
            ],
        )

        read_row = conn.execute(
            "SELECT id, conversation_id, repo_name, repo_path, repo_role, "
            "session_window_start, session_window_end, work_entries, "
            "contributor_sources, created_at, updated_at "
            "FROM cross_repo_work_v2 "
            "WHERE conversation_id = ? AND repo_name = ?",
            [incoming.conversation_id, incoming.repo_name],
        ).fetchone()
        if read_row is None:
            # We just inserted the row above, so it must be readable.
            # A None here indicates a transactional visibility problem
            # (writer race, broken COMMIT) — surface it loudly rather
            # than silently emitting an invalid model_validate call.
            raise RuntimeError(
                "cross_repo_work_v2 row vanished after insert; "
                "check transaction isolation and PRAGMA settings"
            )
        # DuckDB returns JSON columns as raw strings; parse before Pydantic validate
        # (CrossRepoWorkRowRead expects work_entries: list[WorkEntry] and
        # contributor_sources: list[Provenance], not JSON strings).
        read_dict = dict(
            zip(
                [
                    "id",
                    "conversation_id",
                    "repo_name",
                    "repo_path",
                    "repo_role",
                    "session_window_start",
                    "session_window_end",
                    "work_entries",
                    "contributor_sources",
                    "created_at",
                    "updated_at",
                ],
                read_row,
            )
        )
        read_dict["work_entries"] = json.loads(read_dict["work_entries"])
        read_dict["contributor_sources"] = json.loads(read_dict["contributor_sources"])
        return (
            CrossRepoWorkRowRead.model_validate(read_dict),
            inserted,
            deduplicated,
        )
