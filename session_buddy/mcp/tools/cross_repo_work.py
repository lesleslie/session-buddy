"""MCP tool: store_cross_repo_work.

Receiver for cross-repo work entries pushed by other Bodai repos. The
caller supplies the conversation_id ULID (join key with session_windows)
and a list of repos with their work entries. Server-side path resolution
from ecosystem.yaml (path authority — wire shape has no repo_path).

Auth: @require_auth(optional=False) (session-buddy local — composed in
register_cross_repo_work_tools, Task 9).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, TypedDict

import duckdb
import yaml
from oneiric.core.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.core.ulid_generator import generate_ulid
from session_buddy.memory.cross_repo_work import (
    CrossRepoWorkRowCreate,
    UlidStr,
    WorkEntry,
)

_log = get_logger(__name__)


RepoNameStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
]


class RepoWorkEntry(BaseModel):
    """Wire shape for one repo's worth of work entries. NO repo_path here —
    the server resolves it from ecosystem.yaml."""

    model_config = ConfigDict(extra="forbid")
    repo_name: RepoNameStr
    work_entries: Annotated[list[WorkEntry], Field(min_length=1, max_length=200)]


class StoreCrossRepoWorkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: UlidStr
    repos: Annotated[list[RepoWorkEntry], Field(min_length=1, max_length=26)]


class RepoStoreStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repo_name: RepoNameStr
    status: Literal["stored", "deduplicated", "rejected"]
    entries_received: Annotated[int, Field(ge=0)]
    entries_inserted: Annotated[int, Field(ge=0)]
    entries_deduplicated: Annotated[int, Field(ge=0)]
    message: str | None = None


class CrossRepoStoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "partial", "failed"]
    error_code: str | None = None
    message: str | None = None
    retryable: bool = False
    repos_received: Annotated[int, Field(ge=0)]
    repos_stored: Annotated[int, Field(ge=0)]
    entries_received: Annotated[int, Field(ge=0)]
    entries_inserted: Annotated[int, Field(ge=0)]
    entries_deduplicated: Annotated[int, Field(ge=0)]
    per_repo: Annotated[list[RepoStoreStatus], Field(max_length=26)]


class _EcosystemEntry(TypedDict, total=True):
    path: str
    role: str | None


_EcosystemDict = dict[str, _EcosystemEntry]


class _ResolvedRepoEntry(BaseModel):
    """Internal type: server-resolved repo metadata."""

    model_config = ConfigDict(extra="forbid")
    repo_name: str
    path: str
    role: str | None = None


def _load_ecosystem(ecosystem_path) -> _EcosystemDict:
    if not ecosystem_path.exists():
        return {}
    try:
        data = yaml.safe_load(ecosystem_path.read_text())
    except (yaml.YAMLError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw = data.get("ecosystem", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): {"path": str(v.get("path", "")), "role": v.get("role")}
        for k, v in raw.items()
        if isinstance(v, dict)
    }


def _resolve_repo(
    repo_name: str, ecosystem: _EcosystemDict
) -> _ResolvedRepoEntry | None:
    """Lowercase normalization for case-insensitive lookup."""
    name_lower = repo_name.strip().lower()
    entry = ecosystem.get(name_lower) or ecosystem.get(repo_name)
    if entry is None:
        return None
    return _ResolvedRepoEntry(
        repo_name=name_lower,
        path=entry["path"],
        role=entry["role"],
    )


async def store_cross_repo_work(
    *,
    request: StoreCrossRepoWorkRequest,
    merge_primitive: MergePrimitive,
    conn: duckdb.DuckDBPyConnection,
    ecosystem_path,
) -> CrossRepoStoreResult:
    """Handler body. The @require_auth + @mcp_server.tool decorators are
    composed in `register_cross_repo_work_tools` (Task 9)."""
    # 1. conversation_id existence check (G7). Validates against session_windows
    # (canonical conversation identity, v2.1 amendment), NOT conversations_v2.
    conv_exists = conn.execute(
        "SELECT 1 FROM session_windows WHERE id = ?",
        [request.conversation_id],
    ).fetchone()
    if conv_exists is None:
        return CrossRepoStoreResult(
            status="failed",
            error_code="session_not_found",
            message=f"conversation_id {request.conversation_id} not found",
            retryable=False,
            repos_received=len(request.repos),
            repos_stored=0,
            entries_received=0,
            entries_inserted=0,
            entries_deduplicated=0,
            per_repo=[],
        )

    ecosystem = _load_ecosystem(ecosystem_path)
    now = datetime.now(tz=UTC)
    per_repo: list[RepoStoreStatus] = []
    rows_to_write: list[CrossRepoWorkRowCreate] = []
    rejection_map: dict[str, str] = {}  # repo_name -> reason

    for repo_entry in request.repos:
        resolved = _resolve_repo(repo_entry.repo_name, ecosystem)
        if resolved is None:
            rejection_map[repo_entry.repo_name] = "repo not in ecosystem.yaml"
            continue
        rows_to_write.append(
            CrossRepoWorkRowCreate(
                id=generate_ulid(),
                conversation_id=request.conversation_id,
                repo_name=resolved.repo_name,
                repo_path=resolved.path,
                repo_role=resolved.role,
                session_window_start=now,
                session_window_end=now,
                work_entries=repo_entry.work_entries,
                contributor_sources=["explicit"],
            )
        )

    # 2. Multi-repo atomicity — wrap the entire batch in ONE transaction.
    total_received = sum(len(r.work_entries) for r in request.repos)
    repos_stored = 0
    total_inserted = 0
    total_deduplicated = 0
    status = "ok"

    if rows_to_write:
        conn.execute("BEGIN TRANSACTION")
        try:
            _reads, ins, dead = merge_primitive.multi_merge(conn, rows_to_write)
            conn.execute("COMMIT")
            total_inserted = ins
            total_deduplicated = dead
            repos_stored = len(rows_to_write)
        except Exception as exc:  # noqa: BLE001
            # Wrap ROLLBACK itself in inner try/except so a failing rollback
            # doesn't violate the always-return-a-result contract.
            try:
                conn.execute("ROLLBACK")
            except Exception as rollback_exc:  # noqa: BLE001
                _log.warning(
                    "store_cross_repo_work_rollback_failed",
                    extra={"error": str(rollback_exc)},
                )
            _log.exception("store_cross_repo_work_failed")
            return CrossRepoStoreResult(
                status="failed",
                error_code="storage_locked"
                if "write_conflict" in str(exc)
                else "internal",
                message=str(exc),
                retryable=True,
                repos_received=len(request.repos),
                repos_stored=0,
                entries_received=total_received,
                entries_inserted=0,
                entries_deduplicated=0,
                per_repo=[],
            )

    # Build per_repo breakdown
    for repo_entry in request.repos:
        if repo_entry.repo_name in rejection_map:
            per_repo.append(
                RepoStoreStatus(
                    repo_name=repo_entry.repo_name,
                    status="rejected",
                    entries_received=len(repo_entry.work_entries),
                    entries_inserted=0,
                    entries_deduplicated=0,
                    message=rejection_map[repo_entry.repo_name],
                )
            )
        else:
            per_repo.append(
                RepoStoreStatus(
                    repo_name=repo_entry.repo_name,
                    status="stored",
                    entries_received=len(repo_entry.work_entries),
                    entries_inserted=len(repo_entry.work_entries),
                    entries_deduplicated=0,
                    message=None,
                )
            )

    if rejection_map:
        status = "partial" if repos_stored > 0 else "failed"

    return CrossRepoStoreResult(
        status=status,
        error_code=None,
        message=None,
        retryable=False,
        repos_received=len(request.repos),
        repos_stored=repos_stored,
        entries_received=total_received,
        entries_inserted=total_inserted,
        entries_deduplicated=total_deduplicated,
        per_repo=per_repo,
    )
