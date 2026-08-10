from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
    CrossRepoWorkRowRead,
    PlanRefEntry,
    WorkEntry,
)


def test_commit_entry_requires_sha() -> None:
    with pytest.raises(ValidationError):
        CommitEntry(kind="commit", provenance="ambient")  # missing sha


def test_plan_ref_entry_requires_plan_path() -> None:
    with pytest.raises(ValidationError):
        PlanRefEntry(kind="plan_ref", provenance="explicit")  # missing plan_path


def test_work_entry_discriminator_routes_by_kind() -> None:
    commit: WorkEntry = CommitEntry(
        kind="commit",
        sha="abc123",
        provenance="ambient",
        author="les <les@example.com>",
    )
    plan_ref: WorkEntry = PlanRefEntry(
        kind="plan_ref",
        plan_path="docs/foo.md",
        provenance="explicit",
    )
    assert commit.kind == "commit"
    assert plan_ref.kind == "plan_ref"


def test_extra_forbid_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        CommitEntry(
            kind="commit",
            sha="abc123",
            provenance="ambient",
            extra_typo_field="nope",
        )


def test_create_and_read_row_models_have_distinct_fields() -> None:
    now = datetime.now(tz=timezone.utc)
    create = CrossRepoWorkRowCreate(
        id="01HXX",
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",  # 26 chars: UlidStr constraint
        repo_name="mahavishnu",
        repo_path="/Users/les/Projects/mahavishnu",
        repo_role="orchestrator",
        session_window_start=now,
        session_window_end=now,
        work_entries=[],
        contributor_sources=["ambient"],
    )
    read = CrossRepoWorkRowRead(
        id=create.id,
        conversation_id=create.conversation_id,
        repo_name=create.repo_name,
        repo_path=create.repo_path,
        repo_role=create.repo_role,
        session_window_start=create.session_window_start,
        session_window_end=create.session_window_end,
        work_entries=create.work_entries,
        contributor_sources=create.contributor_sources,
        created_at=now,
        updated_at=now,
    )
    # create has no created_at/updated_at; reject if added
    with pytest.raises(ValidationError):
        CrossRepoWorkRowCreate(
            id="01HXX",
            conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",  # 26 chars: UlidStr constraint
            repo_name="mahavishnu",
            repo_path="/Users/les/Projects/mahavishnu",
            repo_role="orchestrator",
            session_window_start=now,
            session_window_end=now,
            work_entries=[],
            contributor_sources=["ambient"],
            created_at=now,
        )
    # smoke that read carries DB-generated timestamps
    assert read.created_at == now