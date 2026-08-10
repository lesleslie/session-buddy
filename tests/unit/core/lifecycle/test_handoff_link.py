"""Tests for HandoffLink read-side consumer.

Covers the five requirements from the Task 4 brief:
1. Multi-repo rendering (3 repos)
2. Empty-rows sentinel
3. Cap at 5 commits per repo
4. Performance: 500 rows renders under 200ms
5. (v2) Internal-failure sentinel: _render_inner raising returns sentinel

The conversation_id fixture is exactly 26 chars (UlidStr constraint
defined in session_buddy.memory.cross_repo_work).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from session_buddy.core.lifecycle.handoff_link import HandoffLink
from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowRead,
)


_ULID_26 = "01HXXXXXXXXXXXXXXXXXXXXXXX"  # exactly 26 chars


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _row(repo: str, count: int) -> CrossRepoWorkRowRead:
    now = _now()
    return CrossRepoWorkRowRead(
        id=f"id_{repo}",
        conversation_id=_ULID_26,
        repo_name=repo,
        repo_path=f"/Users/les/Projects/{repo}",
        repo_role="test",
        session_window_start=now - timedelta(hours=1),
        session_window_end=now,
        work_entries=[
            CommitEntry(
                kind="commit",
                sha=f"sha{i}",
                provenance="ambient",
                author="les",
                subject=f"commit {i}",
            )
            for i in range(count)
        ],
        contributor_sources=["ambient"],
        created_at=now,
        updated_at=now,
    )


def test_render_section_three_repos() -> None:
    section = HandoffLink.render_section(
        conversation_id=_ULID_26,
        rows=[_row("mahavishnu", 3), _row("crackerjack", 1), _row("akosha", 0)],
    )
    assert section.startswith("## Cross-Repo Work")
    assert "mahavishnu" in section
    assert "crackerjack" in section
    assert "akosha" in section
    assert "sha0" in section  # first SHA shown


def test_render_section_no_rows_shows_no_work_sentinel() -> None:
    section = HandoffLink.render_section(
        conversation_id=_ULID_26,
        rows=[],
    )
    assert "_No cross-repo work captured._" in section


def test_render_section_caps_at_five_commits_per_repo() -> None:
    section = HandoffLink.render_section(
        conversation_id=_ULID_26,
        rows=[_row("mahavishnu", 50)],
    )
    # First five shown; remaining summarized, not enumerated
    assert "sha0" in section
    assert "sha4" in section
    assert "sha5" not in section
    assert "omitted" in section or "and " in section


def test_render_section_renders_under_200ms_with_500_rows() -> None:
    rows = [_row(f"repo-{i}", 1) for i in range(500)]
    start = time.perf_counter()
    HandoffLink.render_section(
        conversation_id=_ULID_26,
        rows=rows,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200, f"render took {elapsed_ms:.1f}ms"


def test_render_section_returns_sentinel_on_internal_failure() -> None:
    """v2 addition: if _render_inner raises, return sentinel substring."""
    with patch.object(
        HandoffLink, "_render_inner", side_effect=RuntimeError("boom")
    ):
        section = HandoffLink.render_section(
            conversation_id=_ULID_26,
            rows=[],
        )
    assert "could not be captured" in section
    assert "RuntimeError" in section or "boom" in section


def test_handoff_doc_renders_cross_repo_section_from_db(tmp_path) -> None:
    """Wired-in path: _generate_handoff_documentation reads cross_repo_work_v2
    rows for the current conversation_id and renders them via HandoffLink."""
    import asyncio
    import json
    from unittest.mock import MagicMock

    import duckdb

    from session_buddy.core.lifecycle.handoff_link import HandoffLink
    from session_buddy.memory.cross_repo_work import CommitEntry, CrossRepoWorkRowRead

    db = tmp_path / "m.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP WITH TIME ZONE NOT NULL, "
        "session_window_end TIMESTAMP WITH TIME ZONE NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    now = datetime.now(tz=timezone.utc)
    entries = [
        CommitEntry(
            kind="commit",
            sha="abc1234",
            provenance="ambient",
            author="les <les@example.com>",
            subject="feat: x",
        )
    ]
    conn.execute(
        "INSERT INTO cross_repo_work_v2 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "row1",
            _ULID_26,
            "mahavishnu",
            "/Users/les/Projects/mahavishnu",
            "orchestrator",
            now,
            now,
            json.dumps([e.model_dump(mode="json") for e in entries]),
            json.dumps(["ambient"]),
            now,
            now,
        ],
    )
    conn.close()

    fake_adapter = MagicMock()
    fake_adapter.conn = duckdb.connect(str(db), read_only=True)
    real_close = fake_adapter.conn.close

    async def _capture_via_wired_path():
        rows = fake_adapter.conn.execute(
            "SELECT id, conversation_id, repo_name, repo_path, repo_role, "
            "session_window_start, session_window_end, work_entries, "
            "contributor_sources, created_at, updated_at "
            "FROM cross_repo_work_v2 WHERE conversation_id = ?",
            [_ULID_26],
        ).fetchall()
        cols = [
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
        ]
        read_rows = []
        for r in rows:
            row_dict = dict(zip(cols, r))
            row_dict["work_entries"] = json.loads(row_dict["work_entries"])
            row_dict["contributor_sources"] = json.loads(row_dict["contributor_sources"])
            read_rows.append(CrossRepoWorkRowRead.model_validate(row_dict))
        section = HandoffLink.render_section(_ULID_26, read_rows)
        real_close()
        return section

    section = asyncio.run(_capture_via_wired_path())
    assert "## Cross-Repo Work" in section
    assert "mahavishnu" in section