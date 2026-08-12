"""Pydantic v2 models for the cross_repo_work_v2 reflection table.

Discriminated union over WorkEntry kind, with extra="forbid" on every model.
Split into Create (write path) and Read (read path with DB-generated timestamps).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Provenance = Literal["ambient", "explicit"]


RepoNameStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
]

UlidStr = Annotated[
    str,
    StringConstraints(min_length=26, max_length=26, strip_whitespace=True),
]

AuthorStr = Annotated[
    str,
    StringConstraints(max_length=200, strip_whitespace=True),
]


class _BaseEntry(BaseModel):
    """Shared shape for cross-repo work entries. extra='forbid' prevents
    silent field-drop on typos and surfaces them as ValidationError instead.
    """

    model_config = ConfigDict(extra="forbid")
    provenance: Provenance
    correlation_id: str | None = None  # future consumer pattern
    causation_id: str | None = None  # future consumer pattern


class CommitEntry(_BaseEntry):
    kind: Literal["commit"]
    sha: str  # required: kind=commit without sha is meaningless for the dedup key
    subject: str | None = None
    files_changed_count: int | None = None
    author: AuthorStr | None = None
    timestamp: datetime | None = None


class PlanRefEntry(_BaseEntry):
    kind: Literal["plan_ref"]
    plan_path: str  # required
    phase: str | None = None


# Future kinds (PR, test_run, blocker) deferred — they need their own models
# with required-field contracts. Adding them is a Pydantic-only change.

WorkEntry = Annotated[
    CommitEntry | PlanRefEntry,
    Field(discriminator="kind"),
]


class CrossRepoWorkRowCreate(BaseModel):
    """Write-path model: orchestrator builds this from AmbientPuller or
    CrossRepoPusher before INSERT. No DB-generated timestamps."""

    model_config = ConfigDict(extra="forbid")
    id: str  # ULID; orchestrator generates
    conversation_id: UlidStr
    repo_name: RepoNameStr
    repo_path: str
    repo_role: str | None = None
    session_window_start: datetime
    session_window_end: datetime
    work_entries: list[WorkEntry]
    contributor_sources: list[Provenance] = Field(default_factory=list)


class CrossRepoWorkRowRead(BaseModel):
    """Read-path model: includes DB-generated created_at / updated_at."""

    model_config = ConfigDict(extra="forbid")
    id: str
    conversation_id: UlidStr
    repo_name: RepoNameStr
    repo_path: str
    repo_role: str | None = None
    session_window_start: datetime
    session_window_end: datetime
    work_entries: list[WorkEntry]
    contributor_sources: list[Provenance]
    created_at: datetime
    updated_at: datetime
