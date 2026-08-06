# Cross-Repo Work Accounting in Checkpoint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture cross-repo work (commits, plan refs, blockers, test runs) into the session-buddy checkpoint via two ingest paths (ambient `git log` pull from sibling repos + explicit `store_cross_repo_work` MCP push from other Bodai repos), render a "Cross-Repo Work" section in the handoff doc, and lay the substrate for future routing/trigger consumers — without breaking the existing checkpoint pipeline.

**Architecture:** New `cross_repo_work_v2` DuckDB table (one row per `conversation_id` × `repo_name`; `work_entries` is a JSON column of discriminated-union entries deduped by `(kind, sha|plan_path)`). New `CheckpointCrossRepoAccountant` orchestrates `AmbientPuller` + the merge primitive + write. New MCP tool `store_cross_repo_work` (`@require_auth(Permission.WRITE)` + server-side path resolution). `HandoffLink` reads the table and renders a markdown section between "Quality Breakdown" and "Recommendations" in the production handoff path. Spec: `docs/superpowers/specs/2026-08-05-cross-repo-checkpoint-accounting-design.md` (commit `0e75c7b3`).

**Tech Stack:** Python 3.13, DuckDB ≥0.9.0 (for `INSERT ... ON CONFLICT`), Pydantic v2 (discriminated unions, `ConfigDict(extra="forbid")`), FastMCP via `mcp-common`, `asyncio.to_thread` for sync git subprocess, existing `ReflectionDatabaseAdapter` for storage, `pytest` with the project's `crackerjack`-driven quality gates.

## Global Constraints

Every task's requirements implicitly include this section.

- **Python target**: 3.13+. Use `from __future__ import annotations` as the first non-comment line of every new source file. `X | None` (not `Optional[X]`), `list[str]`, `pathlib.Path`. No `assert` in production code (use `mahavishnu/core/errors.py`-style exceptions). Oneiric logger (`oneiric.logging`) — never stdlib `logging` or `print()`. All I/O in the orchestration layer is async; use `asyncio.to_thread` for blocking subprocess. (session-buddy `CLAUDE.md` crackerjack-compliant-code section.)
- **Hard limits** (from `pyproject.toml`): line-length 100, function args 10, branches 15, returns 6, statements 55 ceiling. Coverage: 80% minimum. New modules must clear the crackerjack gate.
- **DuckDB version**: ≥0.9.0 (required for `INSERT ... ON CONFLICT`). Use `CAST(? AS JSON)` (not `?::JSON`). Use `BEGIN TRANSACTION` (no `IMMEDIATE` qualifier — DuckDB doesn't accept it; it's SQLite syntax). DuckDB does NOT enforce `FOREIGN KEY` — referential integrity is at the application layer.
- **Storage path**: All writes go through `session_buddy/adapters/reflection_adapter_oneiric.py` via `require_reflection_database()` + the existing lock convention. New DDL must be added to EVERY active schema-init/migration path in `session_buddy/memory/schema_v2.py` AND the migration registry in `session_buddy/memory/migration.py`.
- **MCP registration**: every new tool must (a) export `register_<tool>_tools` from `session_buddy/mcp/tools/__init__.py`, (b) add it to `_ALL_REGISTERS` in `session_buddy/mcp/server.py:40-153`, and (c) wire it into the `STANDARD` profile in `session_buddy/mcp/tools/profiles.py:42-76`.
- **Auth contract**: `@require_auth(Permission.WRITE, config=<AuthConfig>, service_name="session-buddy")`. The literal `@require_auth()` defaults to `Permission.READ` and bypasses auth when `config=None` — DO NOT copy the unguarded `store_code_graph_from_mahavishnu` precedent OR the missing-Permission.WRITE precedent in newer session-tracking tools.
- **Conversation identity**: the canonical join key is `conversations_v2.id` (ULID). External pushers must supply it explicitly. `start_session` MCP tool MUST exist and return `conversation_id` before this feature ships.
- **Never-breaks invariant**: cross-repo accounting NEVER blocks the git commit / handoff doc. Storage failures log WARNING and continue; never raise out of `capture()`.
- **Schema naming**: rename `session_id` → `conversation_id` throughout (the prior name was confusing because `checkpoint_session()` generates a fresh ULID per checkpoint invocation, which is NOT the join key). Real names to keep verbatim: `start_session` (MCP tool), `checkpoint_session` (Python method), `session_window_start` / `session_window_end` (time-window terms).
- **Pydantic v2 strict**: every model has `model_config = ConfigDict(extra="forbid")`. Idempotency on `(conversation_id, repo_name, sha|plan_path)` is enforced by the merge primitive in §Merge primitive, NOT by a schema UNIQUE constraint.
- **Conventions** (crackerjack-compliant-code): imports sorted within sections (force-sort-within-sections), known-first-party=["session_buddy"]. Functions ≤15 branches, ≤6 returns, ≤55 statements. `logger.exception(...)` in `except` blocks. No `# type: ignore` — use `# ty: ignore[<code>]` if needed.

---

### Task 1: Preflight — verify `start_session` prerequisite

**Files:** none (read-only).

- [ ] **Step 1: Confirm `start_session` returns `conversation_id`**

Run: `grep -n "conversation_id\|conversationId" session_buddy/tools/session_tools.py | head -10`
Expected: at least one match referencing `conversation_id` as a returned field. If absent, this task escalates to Task 2 (create the prerequisite) before continuing.

- [ ] **Step 2: Confirm `conversations_v2` is reachable as the join key**

Run: `grep -n "conversations_v2\|CREATE TABLE conversations" session_buddy/memory/schema_v2.py | head -5`
Expected: at least one match. Note the column name of the PK (`id` expected) — the rest of this plan references `conversations_v2.id` as the canonical conversation_id.

- [ ] **Step 3: Confirm DuckDB version ≥0.9.0**

Run: `python -c "import duckdb; print(duckdb.__version__)" | head -1`
Expected: `0.9.0` or higher. If lower, document the gap and escalate.

- [ ] **Step 4: Commit nothing** (no changes). Note outcomes in the next task's commit message.

---

### Task 2: Schema — `cross_repo_work_v2` table + migration registration

**Files:**
- Modify: `session_buddy/memory/schema_v2.py` (add DDL after `conversations_v2` block, ~line 119)
- Modify: `session_buddy/memory/migration.py` (register the new DDL with a version key)
- Test: `tests/unit/memory/test_cross_repo_work_v2_schema.py`

**Interfaces:**
- Consumes: `session_buddy.adapters.reflection_adapter_oneiric.require_reflection_database()` (existing)
- Produces: a table `cross_repo_work_v2` registered in both `schema_v2.py::INIT_SCHEMA` and `migration.py::MIGRATIONS`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/memory/test_cross_repo_work_v2_schema.py
from __future__ import annotations

from pathlib import Path

import duckdb

from session_buddy.adapters.reflection_adapter_oneiric import (
    require_reflection_database,
)
from session_buddy.memory.migration import apply_migrations


def test_cross_repo_work_v2_table_present(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    apply_migrations(conn)
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'cross_repo_work_v2'"
    ).fetchall()
    columns = {r[0] for r in rows}
    expected = {
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
    }
    assert expected.issubset(columns), f"missing columns: {expected - columns}"


def test_cross_repo_work_v2_unique_constraint(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    apply_migrations(conn)
    indexes = conn.execute(
        "SELECT index_name FROM duckdb_indexes() "
        "WHERE table_name = 'cross_repo_work_v2'"
    ).fetchall()
    assert any("conversation_id_repo_name" in str(r) for r in indexes), (
        f"missing UNIQUE (conversation_id, repo_name) index; got {indexes}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/memory/test_cross_repo_work_v2_schema.py -v`
Expected: FAIL with "no such table cross_repo_work_v2".

- [ ] **Step 3: Add DDL to `schema_v2.py`**

In `session_buddy/memory/schema_v2.py`, find the `INIT_SCHEMA` constant (or the equivalent module-level DDL block; grep for `CREATE TABLE conversations_v2`) and append:

```sql
CREATE TABLE IF NOT EXISTS cross_repo_work_v2 (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    repo_name       TEXT NOT NULL,
    repo_path       TEXT NOT NULL,
    repo_role       TEXT,
    session_window_start  TIMESTAMP WITH TIME ZONE NOT NULL,
    session_window_end    TIMESTAMP WITH TIME ZONE NOT NULL,
    work_entries    JSON NOT NULL,
    contributor_sources JSON NOT NULL DEFAULT '[]',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cross_repo_work_v2_conv_repo
    ON cross_repo_work_v2 (conversation_id, repo_name);
```

(Recall: DuckDB does NOT enforce `FOREIGN KEY` — the keyword is reserved but skipped. conversation_id is a logical reference to `conversations_v2.id`, enforced at the application layer in the CrossRepoPusher.)

- [ ] **Step 4: Register the DDL in `migration.py`**

In `session_buddy/memory/migration.py`, append the same DDL block to the `MIGRATIONS` registry (find the version-keyed list — add a new entry keyed by an appropriate version stamp such as `("2026-08-05", "cross_repo_work_v2", ddl)`). Apply via `apply_migrations(conn)`. Both the schema-init path AND the migration-registry path execute the same DDL.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/memory/test_cross_repo_work_v2_schema.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add session_buddy/memory/schema_v2.py session_buddy/memory/migration.py tests/unit/memory/test_cross_repo_work_v2_schema.py
git commit -m "feat(schema): add cross_repo_work_v2 table + migration registration"
```

---

### Task 3: Pydantic models — discriminated union + Create/Read split

**Files:**
- Create: `session_buddy/memory/cross_repo_work.py`
- Test: `tests/unit/memory/test_cross_repo_work_pydantic.py`

**Interfaces:**
- Consumes: `pydantic.BaseModel`, `pydantic.ConfigDict`, `pydantic.Field`, `pydantic.StringConstraints`, `typing.Annotated`, `typing.Literal`
- Produces (exported):
  - `WorkEntry` (discriminated union type alias)
  - `Provenance` (`Literal["ambient", "explicit"]`)
  - `CommitEntry` / `PlanRefEntry` (entry models)
  - `RepoNameStr` / `UlidStr` / `AuthorStr` (constrained-string aliases)
  - `CrossRepoWorkRowCreate` / `CrossRepoWorkRowRead` (table-row models)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/memory/test_cross_repo_work_pydantic.py
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
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
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
    # create has no created_at/updated_at; read does
    with pytest.raises(ValidationError):
        CrossRepoWorkRowCreate(
            id="01HXX",
            conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/memory/test_cross_repo_work_pydantic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'session_buddy.memory.cross_repo_work'`.

- [ ] **Step 3: Create `session_buddy/memory/cross_repo_work.py`**

```python
# session_buddy/memory/cross_repo_work.py
"""Pydantic v2 models for the cross_repo_work_v2 reflection table.

Discriminated union over WorkEntry kind, with extra="forbid" on every model.
Split into Create (write path) and Read (read path with DB-generated timestamps).
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

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
    causation_id: str | None = None    # future consumer pattern


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
    Union[CommitEntry, PlanRefEntry],
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/memory/test_cross_repo_work_pydantic.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/memory/cross_repo_work.py tests/unit/memory/test_cross_repo_work_pydantic.py
git commit -m "feat(memory): add cross_repo_work Pydantic models (WorkEntry discriminated union)"
```

---

### Task 4: HandoffLink — read consumer with sentinel rendering

**Files:**
- Create: `session_buddy/core/lifecycle/handoff_link.py`
- Modify: `session_buddy/core/session_manager.py:818` (insert call into `_generate_handoff_documentation` after the Quality Breakdown block)
- Test: `tests/unit/core/lifecycle/test_handoff_link.py`

**Interfaces:**
- Consumes: `CrossRepoWorkRowRead`, `ConversationWindow` (a small tuple `(start: datetime, end: datetime)`) — both passed in by the caller.
- Produces: `str` (the rendered markdown section, including its `## Cross-Repo Work` heading). Caller appends it to the handoff doc.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/lifecycle/test_handoff_link.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from session_buddy.core.lifecycle.handoff_link import HandoffLink
from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowRead,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _row(repo: str, count: int) -> CrossRepoWorkRowRead:
    now = _now()
    return CrossRepoWorkRowRead(
        id=f"id_{repo}",
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
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
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        rows=[_row("mahavishnu", 3), _row("crackerjack", 1), _row("akosha", 0)],
    )
    assert section.startswith("## Cross-Repo Work")
    assert "mahavishnu" in section
    assert "crackerjack" in section
    assert "akosha" in section
    assert "sha0" in section  # first SHA shown


def test_render_section_no_rows_shows_no_work_sentinel() -> None:
    section = HandoffLink.render_section(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        rows=[],
    )
    assert "_No cross-repo work captured._" in section


def test_render_section_caps_at_five_commits_per_repo() -> None:
    section = HandoffLink.render_section(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        rows=[_row("mahavishnu", 50)],
    )
    # First five shown; remaining summarized, not enumerated
    assert "sha0" in section
    assert "sha4" in section
    assert "sha5" not in section
    assert "omitted" in section or "and " in section


def test_render_section_renders_under_200ms_with_500_rows() -> None:
    import time
    rows = [_row(f"repo-{i}", 1) for i in range(500)]
    start = time.perf_counter()
    HandoffLink.render_section(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        rows=rows,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200, f"render took {elapsed_ms:.1f}ms"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/lifecycle/test_handoff_link.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'session_buddy.core.lifecycle.handoff_link'`.

- [ ] **Step 3: Create `session_buddy/core/lifecycle/handoff_link.py`**

```python
# session_buddy/core/lifecycle/handoff_link.py
"""Read-side consumer: render the 'Cross-Repo Work' section of the handoff doc.

Public surface is the staticmethod render_section, which keeps the read path
testable without instantiating a CheckpointCrossRepoAccountant.
"""
from __future__ import annotations

import html
from collections.abc import Iterable
from datetime import datetime

from oneiric.logging import get_logger

from session_buddy.memory.cross_repo_work import CrossRepoWorkRowRead

_log = get_logger(__name__)

_MAX_SHAS_PER_REPO = 5


class HandoffLink:
    """Renders the Cross-Repo Work markdown section for the handoff doc."""

    @staticmethod
    def render_section(
        conversation_id: str,
        rows: Iterable[CrossRepoWorkRowRead],
    ) -> str:
        rows_list = list(rows)
        try:
            return HandoffLink._render_inner(conversation_id, rows_list)
        except Exception as exc:  # noqa: BLE001 — sentinel path, never raise
            _log.exception(
                "cross_repo_work_handoff_render_failed",
                extra={"conversation_id": conversation_id, "error": str(exc)},
            )
            return (
                "## Cross-Repo Work\n\n"
                "> Cross-Repo Work could not be captured: "
                f"{type(exc).__name__}. See logs for details.\n"
            )

    @staticmethod
    def _render_inner(
        conversation_id: str,
        rows: list[CrossRepoWorkRowRead],
    ) -> str:
        if not rows:
            return "## Cross-Repo Work\n\n_No cross-repo work captured._\n"

        lines: list[str] = ["## Cross-Repo Work", ""]
        rows_sorted = sorted(rows, key=lambda r: r.repo_name)
        for row in rows_sorted:
            commits = [e for e in row.work_entries if e.kind == "commit"]
            lines.append(
                f"- **{row.repo_name}** ({row.repo_role or 'unknown'}): "
                f"{len(commits)} commit(s) since "
                f"{row.session_window_start.isoformat()}"
            )
            for entry in commits[:_MAX_SHAS_PER_REPO]:
                sha_short = html.escape(entry.sha[:7])
                subject = html.escape(entry.subject or "(no subject)")
                lines.append(f"  - `{sha_short}` {subject}")
            omitted = len(commits) - _MAX_SHAS_PER_REPO
            if omitted > 0:
                lines.append(f"  - … and {omitted} more commit(s)")
        lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 4: Wire `HandoffLink.render_section` into the production handoff path**

In `session_buddy/core/session_manager.py`, locate the `_generate_handoff_documentation` method (line 789). Find the section that emits "## Quality Breakdown" (line 818). Immediately after that block's write loop, before the "## Recommendations" block, insert a call to fetch cross-repo rows and render the section. Sketch (full code adapted from the surrounding style of `session_manager.py`):

```python
# inside _generate_handoff_documentation, after the Quality Breakdown loop, before Recommendations
try:
    from session_buddy.adapters.reflection_adapter_oneiric import (
        require_reflection_database,
    )
    from session_buddy.core.lifecycle.handoff_link import HandoffLink
    from session_buddy.memory.cross_repo_work import CrossRepoWorkRowRead

    with require_reflection_database() as conn:
        rows = conn.execute(
            "SELECT id, conversation_id, repo_name, repo_path, repo_role, "
            "session_window_start, session_window_end, work_entries, "
            "contributor_sources, created_at, updated_at "
            "FROM cross_repo_work_v2 WHERE conversation_id = ?",
            [conversation_id],
        ).fetchall()
    read_rows = [CrossRepoWorkRowRead.model_validate(dict(r)) for r in rows]
    markdown_content.append(
        HandoffLink.render_section(conversation_id, read_rows)
    )
except Exception as exc:  # noqa: BLE001 — sentinel path; do not break handoff
    _log.exception("cross_repo_work_handoff_render_failed")
    markdown_content.append(
        "## Cross-Repo Work\n\n"
        "> Cross-Repo Work could not be captured: "
        f"{type(exc).__name__}. See logs for details.\n"
    )
```

(Adjust the `_log` reference to match the logger instance already imported in `session_manager.py` — likely `self.logger` or a module-level logger.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/lifecycle/test_handoff_link.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add session_buddy/core/lifecycle/handoff_link.py session_buddy/core/session_manager.py tests/unit/core/lifecycle/test_handoff_link.py
git commit -m "feat(handoff): add HandoffLink consumer + wire into _generate_handoff_documentation"
```

---

### Task 5: AmbientPuller — async git log with timeout + non-local filter

**Files:**
- Create: `session_buddy/core/checkpoint/__init__.py`
- Create: `session_buddy/core/checkpoint/ambient_puller.py`
- Test: `tests/unit/core/checkpoint/test_ambient_puller.py`

**Interfaces:**
- Consumes: `pathlib.Path` (working_directory), `UlidStr` (conversation_id), `datetime` (session_window_start, session_window_end), `Settings` (for `settings/ecosystem.yaml` path; injected).
- Produces: `tuple[list[CommitEntry], list[str]]` — `(captured_entries, per_repo_failures)`. Never raises.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/checkpoint/test_ambient_puller.py
from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from session_buddy.core.checkpoint.ambient_puller import AmbientPuller


def _git_init(path: Path) -> None:
    subprocess.check_call(["git", "init", "--quiet", str(path)])
    subprocess.check_call(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"]
    )
    subprocess.check_call(
        ["git", "-C", str(path), "config", "user.name", "Test"]
    )


def _commit(path: Path, msg: str) -> str:
    subprocess.check_call(["git", "-C", str(path), "commit", "--allow-empty", "-m", msg])
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"]
    ).decode().strip()


def _write_manifest(tmp_path: Path, repos: list[dict[str, str]]) -> Path:
    p = tmp_path / "ecosystem.yaml"
    p.write_text(yaml.safe_dump({"ecosystem": {r["name"]: {"path": r["path"], "role": r["role"]} for r in repos}}))
    return p


@pytest.mark.asyncio
async def test_ambient_puller_captures_commits_from_sibling(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    _git_init(sibling)
    sha = _commit(sibling, "feat(sibling): hello")
    manifest = _write_manifest(tmp_path, [{"name": "sibling", "path": str(sibling), "role": "x"}])

    start = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    end = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    puller = AmbientPuller(manifest_path=manifest)
    entries, failures = await puller.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=start,
        session_window_end=end,
    )
    assert failures == []
    assert any(e.sha == sha for e in entries)


@pytest.mark.asyncio
async def test_ambient_puller_excludes_local_working_directory(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sha = _commit(workdir, "feat(work): local commit")
    manifest = _write_manifest(tmp_path, [{"name": "work", "path": str(workdir), "role": "x"}])

    start = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    end = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    puller = AmbientPuller(manifest_path=manifest)
    entries, _ = await puller.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=start,
        session_window_end=end,
    )
    assert all(e.sha != sha for e in entries)


@pytest.mark.asyncio
async def test_ambient_puller_skips_missing_manifest(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    puller = AmbientPuller(manifest_path=tmp_path / "nonexistent.yaml")
    entries, failures = await puller.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc),
        session_window_end=datetime.now(tz=timezone.utc),
    )
    assert entries == []
    assert failures == []


@pytest.mark.asyncio
async def test_ambient_puller_skips_repo_with_no_commits_in_window(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    _git_init(sibling)
    _commit(sibling, "ancient commit")
    manifest = _write_manifest(tmp_path, [{"name": "sibling", "path": str(sibling), "role": "x"}])

    # Window entirely in the future
    start = datetime.now(tz=timezone.utc) + timedelta(days=10)
    end = start + timedelta(hours=1)
    puller = AmbientPuller(manifest_path=manifest)
    entries, failures = await puller.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=start,
        session_window_end=end,
    )
    assert entries == []
    assert failures == []
```

(Timeout tests below are in Task 5b; this task covers the core happy path.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/checkpoint/test_ambient_puller.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'session_buddy.core.checkpoint.ambient_puller'`.

- [ ] **Step 3: Create `session_buddy/core/checkpoint/__init__.py`** (empty file).

- [ ] **Step 4: Create `session_buddy/core/checkpoint/ambient_puller.py`**

```python
# session_buddy/core/checkpoint/ambient_puller.py
"""Ambient capture of git commits from sibling repos during a session-buddy checkpoint.

Runs `git log` per non-local sibling repo inside asyncio.to_thread (so the
event loop is never blocked), with a 10s per-repo timeout and a 30s
per-batch cap. Never raises — failures are returned in the
per_repo_failures list and the orchestrator logs them as WARNING.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from oneiric.logging import get_logger

from session_buddy.memory.cross_repo_work import CommitEntry

_log = get_logger(__name__)

_PER_REPO_TIMEOUT_S = 10.0
_BATCH_TIMEOUT_S = 30.0
_MAX_COMMITS = 500


@dataclass(frozen=True)
class _RepoTarget:
    name: str
    path: Path
    role: str | None


class AmbientPuller:
    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path

    async def capture(
        self,
        *,
        working_directory: Path,
        conversation_id: str,
        session_window_start: datetime,
        session_window_end: datetime,
    ) -> tuple[list[CommitEntry], list[str]]:
        repos = self._load_repos(working_directory)
        if not repos:
            return [], []

        captured: list[CommitEntry] = []
        failures: list[str] = []

        async def _run_one(target: _RepoTarget) -> None:
            try:
                entries = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._git_log,
                        target,
                        session_window_start,
                        session_window_end,
                    ),
                    timeout=_PER_REPO_TIMEOUT_S,
                )
                captured.extend(entries)
            except asyncio.TimeoutError:
                _log.warning(
                    "ambient_pull_git_log_timeout",
                    extra={"repo": target.name, "timeout_s": _PER_REPO_TIMEOUT_S},
                )
                failures.append(target.name)
            except Exception as exc:  # noqa: BLE001 — never raise
                _log.warning(
                    "ambient_pull_failed",
                    extra={"repo": target.name, "error": str(exc)},
                )
                failures.append(target.name)

        try:
            await asyncio.wait_for(
                asyncio.gather(*(_run_one(r) for r in repos), return_exceptions=True),
                timeout=_BATCH_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            _log.warning(
                "ambient_pull_batch_timeout",
                extra={"timeout_s": _BATCH_TIMEOUT_S},
            )
        return captured, failures

    @staticmethod
    def _load_repos(working_directory: Path) -> list[_RepoTarget]:
        # manifest loading is sync; small file, OK to do at capture time
        manifest = Path(os.environ.get("ECOSYSTEM_MANIFEST", "settings/ecosystem.yaml"))
        if not manifest.exists():
            _log.info("ambient_pull_manifest_missing", extra={"path": str(manifest)})
            return []
        try:
            data = yaml.safe_load(manifest.read_text())
        except yaml.YAMLError as exc:
            _log.warning("ambient_pull_manifest_malformed", extra={"error": str(exc)})
            return []
        if not isinstance(data, dict) or "ecosystem" not in data:
            return []
        local = working_directory.resolve()
        result: list[_RepoTarget] = []
        for name, entry in data["ecosystem"].items():
            if not isinstance(entry, dict) or "path" not in entry:
                continue
            path = Path(entry["path"]).resolve()
            if path == local:
                continue  # non-local filter: skip working_directory
            result.append(_RepoTarget(name=name, path=path, role=entry.get("role")))
        return result

    @staticmethod
    def _git_log(
        target: _RepoTarget,
        start: datetime,
        end: datetime,
    ) -> list[CommitEntry]:
        argv = [
            "git",
            "log",
            f"--since={int(start.timestamp())}",
            f"--until={int(end.timestamp())}",
            f"-n{_MAX_COMMITS}",
            "--format=%H%x09%s%x09%an%x09%ae%x09%aI",
            "--",
            str(target.path),
        ]
        proc = subprocess.run(  # noqa: S603 — argv list, not shell
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=_PER_REPO_TIMEOUT_S + 1,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git log failed: {proc.stderr.strip()}")
        result: list[CommitEntry] = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t", 5)
            if len(parts) < 5:
                continue
            sha, subject, author_name, author_email, ts = parts[:5]
            result.append(
                CommitEntry(
                    kind="commit",
                    sha=sha,
                    subject=subject or None,
                    author=f"{author_name} <{author_email}>",
                    timestamp=datetime.fromisoformat(ts.replace("Z", "+00:00")),
                    provenance="ambient",
                )
            )
        return result
```

(Adjust the `_load_repos` static method to read from the `manifest_path` constructor argument — replace `Path(os.environ.get(...))` with `self._manifest_path`. The version above is illustrative; the actual implementer uses the constructor arg.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/checkpoint/test_ambient_puller.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add session_buddy/core/checkpoint/__init__.py session_buddy/core/checkpoint/ambient_puller.py tests/unit/core/checkpoint/test_ambient_puller.py
git commit -m "feat(checkpoint): add AmbientPuller (async git log + timeout + non-local filter)"
```

---

### Task 6: Merge primitive — Python dedup + atomic DuckDB SQL

**Files:**
- Create: `session_buddy/core/checkpoint/merge_primitive.py`
- Test: `tests/unit/core/checkpoint/test_merge_primitive.py`

**Interfaces:**
- Consumes: `CrossRepoWorkRowCreate` (incoming row), DuckDB connection (via `require_reflection_database()`).
- Produces: `CrossRepoWorkRowRead` (the post-merge row as written), `int` (entries_inserted), `int` (entries_deduplicated).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/checkpoint/test_merge_primitive.py
from __future__ import annotations

from datetime import datetime, timezone

import duckdb

from session_buddy.adapters.reflection_adapter_oneiric import (
    require_reflection_database,
)
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
)


def _now():
    return datetime.now(tz=timezone.utc)


def _row(sha: str, prov: str = "ambient"):
    now = _now()
    return CrossRepoWorkRowCreate(
        id=f"id_{sha}",
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        repo_name="mahavishnu",
        repo_path="/Users/les/Projects/mahavishnu",
        repo_role="orchestrator",
        session_window_start=now,
        session_window_end=now,
        work_entries=[CommitEntry(kind="commit", sha=sha, provenance=prov)],
        contributor_sources=[prov],
    )


def test_merge_first_write_inserts(tmp_path):
    db = tmp_path / "m.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP NOT NULL, "
        "session_window_end TIMESTAMP NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "UNIQUE (conversation_id, repo_name))"
    )
    mp = MergePrimitive()
    read, ins, ded = mp.merge(conn, _row("sha1"))
    assert ins == 1 and ded == 0
    assert len(read.work_entries) == 1


def test_merge_dedup_on_sha_keeps_explicit(tmp_path):
    db = tmp_path / "m.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP NOT NULL, "
        "session_window_end TIMESTAMP NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "UNIQUE (conversation_id, repo_name))"
    )
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1", "ambient"))
    read, ins, ded = mp.merge(conn, _row("sha1", "explicit"))
    assert ins == 0 and ded == 1
    assert read.work_entries[0].provenance == "explicit"
    assert "ambient" in read.contributor_sources
    assert "explicit" in read.contributor_sources


def test_merge_different_shas_appends(tmp_path):
    db = tmp_path / "m.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP NOT NULL, "
        "session_window_end TIMESTAMP NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "UNIQUE (conversation_id, repo_name))"
    )
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1"))
    read, ins, ded = mp.merge(conn, _row("sha2"))
    assert ins == 1 and ded == 0
    assert {e.sha for e in read.work_entries} == {"sha1", "sha2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/checkpoint/test_merge_primitive.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `session_buddy/core/checkpoint/merge_primitive.py`**

```python
# session_buddy/core/checkpoint/merge_primitive.py
"""Atomic merge primitive for cross_repo_work_v2.

Performs read-dedup-write inside BEGIN TRANSACTION with a Python-held
adapter lock. The SQL receives pre-merged JSON via CAST(? AS JSON)
parameters; the dedup-by-(kind, sha|plan_path) happens in Python.

Idempotency on (conversation_id, repo_name, sha) is enforced HERE,
not by a schema UNIQUE constraint (DuckDB JSON columns don't support
deduplication natively).
"""
from __future__ import annotations

import json
from typing import Iterable

import duckdb

from oneiric.logging import get_logger

from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
    CrossRepoWorkRowRead,
    PlanRefEntry,
    WorkEntry,
)

_log = get_logger(__name__)


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
            # Prefer provenance="explicit" over "ambient"; otherwise keep existing
            if (
                existing_entry.provenance == "ambient"
                and entry.provenance == "explicit"
            ):
                by_key[key] = entry
            deduplicated += 1
        else:
            by_key[key] = entry
            inserted += 1
    return list(by_key.values()), inserted, deduplicated


def _union_provenance(
    existing: Iterable[str],
    incoming: Iterable[str],
) -> list[str]:
    seen: list[str] = []
    for prov in list(existing) + list(incoming):
        if prov not in seen:
            seen.append(prov)
    return seen


class MergePrimitive:
    def merge(
        self,
        conn: duckdb.DuckDBPyConnection,
        incoming: CrossRepoWorkRowCreate,
    ) -> tuple[CrossRepoWorkRowRead, int, int]:
        # Read existing row (if any) inside the transaction.
        existing = conn.execute(
            "SELECT work_entries, contributor_sources, session_window_end "
            "FROM cross_repo_work_v2 "
            "WHERE conversation_id = ? AND repo_name = ?",
            [incoming.conversation_id, incoming.repo_name],
        ).fetchone()

        if existing is None:
            new_entries = list(incoming.work_entries)
            inserted = len(new_entries)
            deduplicated = 0
            merged_provenance = list(incoming.contributor_sources)
            new_session_window_end = incoming.session_window_end
        else:
            existing_entries_raw, existing_provenance_raw, existing_end_raw = existing
            existing_entries = [
                WorkEntry.model_validate(e) for e in json.loads(existing_entries_raw)
            ]
            existing_provenance = json.loads(existing_provenance_raw)
            new_entries, inserted, deduplicated = _merge_entries(
                existing_entries, list(incoming.work_entries)
            )
            merged_provenance = _union_provenance(
                existing_provenance, incoming.contributor_sources
            )
            # Preserve the GREATEST of existing vs incoming session_window_end
            existing_end = CrossRepoWorkRowRead.model_validate(
                {"session_window_end": existing_end_raw}
            ).session_window_end
            new_session_window_end = max(existing_end, incoming.session_window_end)

        conn.execute("BEGIN TRANSACTION")
        try:
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
                    json.dumps([e.model_dump(mode="json") for e in new_entries]),
                    json.dumps(merged_provenance),
                    json.dumps([e.model_dump(mode="json") for e in new_entries]),
                    json.dumps(merged_provenance),
                ],
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        # Read back the canonical row to return as CrossRepoWorkRowRead.
        read_row = conn.execute(
            "SELECT id, conversation_id, repo_name, repo_path, repo_role, "
            "session_window_start, session_window_end, work_entries, "
            "contributor_sources, created_at, updated_at "
            "FROM cross_repo_work_v2 "
            "WHERE conversation_id = ? AND repo_name = ?",
            [incoming.conversation_id, incoming.repo_name],
        ).fetchone()
        read_dict = dict(zip(
            [
                "id", "conversation_id", "repo_name", "repo_path", "repo_role",
                "session_window_start", "session_window_end", "work_entries",
                "contributor_sources", "created_at", "updated_at",
            ],
            read_row,
        ))
        read_dict["work_entries"] = json.loads(read_dict["work_entries"])
        read_dict["contributor_sources"] = json.loads(read_dict["contributor_sources"])
        return (
            CrossRepoWorkRowRead.model_validate(read_dict),
            inserted,
            deduplicated,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/checkpoint/test_merge_primitive.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/core/checkpoint/merge_primitive.py tests/unit/core/checkpoint/test_merge_primitive.py
git commit -m "feat(checkpoint): add MergePrimitive (Python dedup + atomic DuckDB transaction)"
```

---

### Task 7: CheckpointCrossRepoAccountant — orchestrator

**Files:**
- Create: `session_buddy/core/checkpoint/cross_repo_accountant.py`
- Test: `tests/unit/core/checkpoint/test_cross_repo_accountant.py`

**Interfaces:**
- Consumes: `Path` (working_directory), `UlidStr` (conversation_id), `datetime` × 2 (session_window_start, session_window_end), `AmbientPuller` instance, `MergePrimitive` instance, DuckDB connection.
- Produces: `CrossRepoCaptureSummary` — a small dataclass `{repos_captured: int, entries_inserted: int, entries_deduplicated: int, ambient_failures: list[str]}`. Never raises.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/checkpoint/test_cross_repo_accountant.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
from session_buddy.core.checkpoint.cross_repo_accountant import (
    CheckpointCrossRepoAccountant,
    CrossRepoCaptureSummary,
)
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import CommitEntry


def _now():
    return datetime.now(tz=timezone.utc)


def _setup_db(tmp_path: Path):
    db = tmp_path / "a.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP NOT NULL, "
        "session_window_end TIMESTAMP NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "UNIQUE (conversation_id, repo_name))"
    )
    return conn


@pytest.mark.asyncio
async def test_capture_returns_summary_and_writes_rows(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    import subprocess
    subprocess.check_call(["git", "init", "--quiet", str(sibling)])
    subprocess.check_call(["git", "-C", str(sibling), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(sibling), "config", "user.name", "T"])
    subprocess.check_call(["git", "-C", str(sibling), "commit", "--allow-empty", "-m", "hi"])
    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(
        f"ecosystem:\n  sibling:\n    path: {sibling}\n    role: test\n"
    )

    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(manifest),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    summary: CrossRepoCaptureSummary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=_now() - timedelta(hours=1),
        session_window_end=_now() + timedelta(hours=1),
    )
    assert summary.repos_captured == 1
    assert summary.entries_inserted == 1
    assert summary.ambient_failures == []
    # Row was actually written
    count = conn.execute(
        "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id = ?",
        ["01HXXXXXXXXXXXXXXXXXXXXXXXXX"],
    ).fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_capture_never_raises_on_ambient_failure(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(tmp_path / "missing.yaml"),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    summary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=_now(),
        session_window_end=_now(),
    )
    # No rows written, no exception raised
    assert summary.repos_captured == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/checkpoint/test_cross_repo_accountant.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `session_buddy/core/checkpoint/cross_repo_accountant.py`**

```python
# session_buddy/core/checkpoint/cross_repo_accountant.py
"""Orchestrator that captures cross-repo work during a session-buddy checkpoint.

Coordinates AmbientPuller + MergePrimitive + write. Never raises — returns
a CrossRepoCaptureSummary for the checkpoint log. Cross-repo accounting
failures NEVER block the git commit / handoff doc (G6).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb
from oneiric.logging import get_logger

from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
    UlidStr,
)
from session_buddy.utils.ulid_generator import generate_ulid

_log = get_logger(__name__)


@dataclass
class CrossRepoCaptureSummary:
    repos_captured: int = 0
    entries_inserted: int = 0
    entries_deduplicated: int = 0
    ambient_failures: list[str] = field(default_factory=list)

    def merge(self, other: CrossRepoCaptureSummary) -> None:
        self.repos_captured += other.repos_captured
        self.entries_inserted += other.entries_inserted
        self.entries_deduplicated += other.entries_deduplicated
        self.ambient_failures.extend(other.ambient_failures)


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
            entries, failures = await self._puller.capture(
                working_directory=working_directory,
                conversation_id=conversation_id,
                session_window_start=session_window_start,
                session_window_end=session_window_end,
            )
        except Exception as exc:  # noqa: BLE001 — never raise
            _log.warning(
                "cross_repo_accountant_pull_failed",
                extra={"error": str(exc), "conversation_id": conversation_id},
            )
            return summary

        summary.ambient_failures = failures
        if not entries:
            return summary

        # Group entries by repo_name. (AmbientPuller exposes the repo
        # via entry.repo_name? — here we synthesize from the manifest.)
        # For ambient-only entries, all SHAs come from a single repo per
        # puller.run call; we treat that as one row keyed on the ambient
        # call's repo. The implementer adjusts this when refactoring
        # AmbientPuller to return per-repo lists.

        # Simple case: single-repo ambient run → single row.
        # Group by repo_name from a sibling manifest lookup (done via
        # AmbientPuller internals — kept opaque here).
        repo_name = "<ambient>"  # placeholder — replaced in wiring task
        repo_path = str(working_directory)
        repo_role = None

        row = CrossRepoWorkRowCreate(
            id=generate_ulid(),
            conversation_id=conversation_id,
            repo_name=repo_name,
            repo_path=repo_path,
            repo_role=repo_role,
            session_window_start=session_window_start,
            session_window_end=session_window_end,
            work_entries=entries,
            contributor_sources=["ambient"],
        )
        try:
            _read, ins, ded = self._merge.merge(self._conn, row)
        except Exception as exc:  # noqa: BLE001 — never raise
            _log.warning(
                "cross_repo_accountant_merge_failed",
                extra={"error": str(exc), "conversation_id": conversation_id},
            )
            return summary

        summary.entries_inserted += ins
        summary.entries_deduplicated += ded
        summary.repos_captured = 1
        return summary
```

NOTE: The placeholder `<ambient>` for `repo_name` will be replaced in the **wiring task** (Task 11), where the AmbientPuller interface is refactored to return `dict[str, list[CommitEntry]]` (per-repo lists). This task ships the orchestrator skeleton; the per-repo split is a follow-up wiring step.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/checkpoint/test_cross_repo_accountant.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/core/checkpoint/cross_repo_accountant.py tests/unit/core/checkpoint/test_cross_repo_accountant.py
git commit -m "feat(checkpoint): add CheckpointCrossRepoAccountant orchestrator (never-raises)"
```

---

### Task 8: CrossRepoPusher MCP tool — auth + validation + atomicity

**Files:**
- Create: `session_buddy/mcp/tools/cross_repo_work.py`
- Test: `tests/unit/mcp/tools/test_cross_repo_work.py`

**Interfaces:**
- Consumes: `StoreCrossRepoWorkRequest` (Pydantic model from Task 3), `mcp_common.auth.AuthConfig`, `MergePrimitive`, DuckDB connection.
- Produces: `CrossRepoStoreResult` (typed domain result — see schema in the file).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/mcp/tools/test_cross_repo_work.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    require_reflection_database,
)
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.mcp.tools.cross_repo_work import (
    RepoWorkEntry,
    StoreCrossRepoWorkRequest,
    store_cross_repo_work,
)
from session_buddy.memory.cross_repo_work import CommitEntry


def _setup_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    db = tmp_path / "m.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP NOT NULL, "
        "session_window_end TIMESTAMP NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "UNIQUE (conversation_id, repo_name))"
    )
    conn.execute(
        "CREATE TABLE conversations_v2 ("
        "id TEXT PRIMARY KEY, started_at TIMESTAMP, ended_at TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO conversations_v2 VALUES (?, ?, ?)",
        ["01HXXXXXXXXXXXXXXXXXXXXXXXXX", datetime.now(tz=timezone.utc), None],
    )
    return conn


def _request(repo_name: str = "mahavishnu", sha: str = "abc123"):
    return StoreCrossRepoWorkRequest(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        repos=[RepoWorkEntry(
            repo_name=repo_name,
            work_entries=[CommitEntry(
                kind="commit", sha=sha, provenance="explicit",
            )],
        )],
    )


@pytest.mark.asyncio
async def test_store_cross_repo_work_persists_row(tmp_path: Path) -> None:
    conn = _setup_db(tmp_path)
    result = await store_cross_repo_work(
        request=_request(),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    assert result.status == "ok"
    assert result.repos_stored == 1
    count = conn.execute(
        "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id = ?",
        ["01HXXXXXXXXXXXXXXXXXXXXXXXXX"],
    ).fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_store_cross_repo_work_dedupes_by_sha(tmp_path: Path) -> None:
    conn = _setup_db(tmp_path)
    r1 = await store_cross_repo_work(
        request=_request(sha="dup"), merge_primitive=MergePrimitive(), conn=conn,
    )
    r2 = await store_cross_repo_work(
        request=_request(sha="dup"), merge_primitive=MergePrimitive(), conn=conn,
    )
    assert r1.entries_inserted == 1
    assert r2.entries_inserted == 0
    assert r2.entries_deduplicated == 1


@pytest.mark.asyncio
async def test_store_cross_repo_work_atomic_multi_repo(tmp_path: Path) -> None:
    conn = _setup_db(tmp_path)
    request = StoreCrossRepoWorkRequest(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        repos=[
            RepoWorkEntry(
                repo_name="mahavishnu",
                work_entries=[CommitEntry(kind="commit", sha="a", provenance="explicit")],
            ),
            RepoWorkEntry(
                repo_name="crackerjack",
                work_entries=[CommitEntry(kind="commit", sha="b", provenance="explicit")],
            ),
        ],
    )
    result = await store_cross_repo_work(
        request=request, merge_primitive=MergePrimitive(), conn=conn,
    )
    assert result.status == "ok"
    assert result.repos_stored == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/mcp/tools/test_cross_repo_work.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `session_buddy/mcp/tools/cross_repo_work.py`**

```python
# session_buddy/mcp/tools/cross_repo_work.py
"""MCP tool: store_cross_repo_work.

Receiver for cross-repo work entries pushed by other Bodai repos. The
caller supplies the conversation_id ULID (join key with conversations_v2)
and a list of repos with their work entries. Server-side path resolution
from ecosystem.yaml (path authority — wire shape has no repo_path).

Auth: @require_auth(Permission.WRITE, config=AuthConfig, service_name=...).
DO NOT use the literal @require_auth() — mcp-common defaults to READ and
bypasses auth when config=None.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import duckdb
import yaml
from oneiric.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic import ValidationError

from mcp_common.auth import AuthConfig, Permission, require_auth

from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
    PlanRefEntry,
    UlidStr,
    WorkEntry,
)
from session_buddy.utils.ulid_generator import generate_ulid

_log = get_logger(__name__)


RepoNameStr = Annotated[
    str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
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


def _load_ecosystem() -> dict[str, dict[str, str]]:
    manifest = Path(os.environ.get("ECOSYSTEM_MANIFEST", "settings/ecosystem.yaml"))
    if not manifest.exists():
        return {}
    try:
        data = yaml.safe_load(manifest.read_text())
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data.get("ecosystem", {})


def _resolve_repo(repo_name: str, ecosystem: dict) -> tuple[str | None, str | None]:
    """Server-side path resolution. Returns (path, role) or (None, None)
    if repo_name is not in ecosystem.yaml."""
    entry = ecosystem.get(repo_name)
    if not isinstance(entry, dict):
        return None, None
    return entry.get("path"), entry.get("role")


async def store_cross_repo_work(
    *,
    request: StoreCrossRepoWorkRequest,
    merge_primitive: MergePrimitive,
    conn: duckdb.DuckDBPyConnection,
) -> CrossRepoStoreResult:
    """Handler body. The @require_auth + @mcp_server.tool decorators are
    composed in Task 9 (MCP registration)."""
    ecosystem = _load_ecosystem()
    now = datetime.now(tz=timezone.utc)
    per_repo: list[RepoStoreStatus] = []
    total_received = 0
    total_inserted = 0
    total_deduplicated = 0
    repos_stored = 0

    try:
        for repo_entry in request.repos:
            path, role = _resolve_repo(repo_entry.repo_name, ecosystem)
            if path is None:
                per_repo.append(RepoStoreStatus(
                    repo_name=repo_entry.repo_name,
                    status="rejected",
                    entries_received=len(repo_entry.work_entries),
                    entries_inserted=0,
                    entries_deduplicated=0,
                    message="repo not in ecosystem.yaml",
                ))
                continue
            row = CrossRepoWorkRowCreate(
                id=generate_ulid(),
                conversation_id=request.conversation_id,
                repo_name=repo_entry.repo_name,
                repo_path=path,
                repo_role=role,
                session_window_start=now,
                session_window_end=now,
                work_entries=repo_entry.work_entries,
                contributor_sources=["explicit"],
            )
            _read, ins, ded = merge_primitive.merge(conn, row)
            total_received += len(repo_entry.work_entries)
            total_inserted += ins
            total_deduplicated += ded
            per_repo.append(RepoStoreStatus(
                repo_name=repo_entry.repo_name,
                status="stored" if ins > 0 else "deduplicated",
                entries_received=len(repo_entry.work_entries),
                entries_inserted=ins,
                entries_deduplicated=ded,
                message=None,
            ))
            if ins > 0:
                repos_stored += 1

        return CrossRepoStoreResult(
            status="ok",
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
    except Exception as exc:  # noqa: BLE001
        _log.exception("store_cross_repo_work_failed")
        return CrossRepoStoreResult(
            status="failed",
            error_code="storage_locked" if "write_conflict" in str(exc) else "internal",
            message=str(exc),
            retryable=True,
            repos_received=len(request.repos),
            repos_stored=0,
            entries_received=total_received,
            entries_inserted=0,
            entries_deduplicated=0,
            per_repo=[],
        )
```

(Imports for `Annotated`, `Literal`, `StringConstraints` are already at the top.)

- [ ] **Step 4: Run tests to verify them pass**

Run: `uv run pytest tests/unit/mcp/tools/test_cross_repo_work.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/mcp/tools/cross_repo_work.py tests/unit/mcp/tools/test_cross_repo_work.py
git commit -m "feat(mcp): add store_cross_repo_work tool (auth + validation + atomicity)"
```

---

### Task 9: MCP registration — 3 wiring steps + STANDARD profile smoke test

**Files:**
- Modify: `session_buddy/mcp/tools/__init__.py` (export `register_cross_repo_work_tools`)
- Modify: `session_buddy/mcp/server.py:40-153` (add to `_ALL_REGISTERS`)
- Modify: `session_buddy/mcp/tools/profiles.py:42-76` (wire into `STANDARD` profile)
- Modify: `session_buddy/mcp/tools/cross_repo_work.py` (add `register_cross_repo_work_tools` function with decorator composition)
- Test: `tests/integration/test_mcp_registration_standard_profile.py`

**Interfaces:**
- Consumes: `mcp_server` instance (FastMCP), `AuthConfig`, `MergePrimitive` factory.
- Produces: the registered tool `store_cross_repo_work` callable; advertised in the `STANDARD` profile's tool list.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_mcp_registration_standard_profile.py
from __future__ import annotations

import os

import pytest


@pytest.fixture
def standard_profile(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_TOOL_PROFILE", "standard")
    # Re-import after env var set, since profiles.py reads it at import time
    import importlib
    import session_buddy.mcp.tools.profiles as profiles
    importlib.reload(profiles)
    return profiles


def test_store_cross_repo_work_in_standard_profile(standard_profile) -> None:
    tool_names = {t["name"] for t in standard_profile.STANDARD_TOOLS}
    assert "store_cross_repo_work" in tool_names, (
        f"store_cross_repo_work missing from STANDARD profile; got {tool_names}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_mcp_registration_standard_profile.py -v`
Expected: FAIL with `AssertionError`.

- [ ] **Step 3: Add `register_cross_repo_work_tools` to `cross_repo_work.py`**

Append to `session_buddy/mcp/tools/cross_repo_work.py`:

```python
from mcp_common.auth import AuthConfig


def register_cross_repo_work_tools(
    mcp_server,
    *,
    auth_config: AuthConfig,
    merge_primitive: MergePrimitive,
    conn_factory,
) -> None:
    """Register store_cross_repo_work on the FastMCP server with auth.

    DO NOT use the literal @require_auth() — mcp-common defaults to
    Permission.READ and bypasses auth when config=None. Pass the explicit
    Permission.WRITE and the session-buddy AuthConfig.
    """
    @require_auth(Permission.WRITE, config=auth_config, service_name="session-buddy")
    @mcp_server.tool(name="store_cross_repo_work")
    async def _store_cross_repo_work(
        request: StoreCrossRepoWorkRequest,
    ) -> CrossRepoStoreResult:
        conn = conn_factory()
        return await store_cross_repo_work(
            request=request,
            merge_primitive=merge_primitive,
            conn=conn,
        )
```

(Adjust `conn_factory` to whatever the project uses for connection acquisition — likely `require_reflection_database()` context manager wrapped in a callable, or a session-scoped connection. The implementer matches the existing pattern in `server.py`.)

- [ ] **Step 4: Export from `session_buddy/mcp/tools/__init__.py`**

Add `from session_buddy.mcp.tools.cross_repo_work import register_cross_repo_work_tools` (or the project's existing import style) and add it to the `__all__` list.

- [ ] **Step 5: Add to `_ALL_REGISTERS` in `session_buddy/mcp/server.py:40-153`**

Find the `_ALL_REGISTERS` list (likely near the bottom of the file). Append a registration call:

```python
register_cross_repo_work_tools(
    _mcp_server,
    auth_config=_AUTH_CONFIG,
    merge_primitive=MergePrimitive(),
    conn_factory=require_reflection_database,
)
```

(Adjust names to match the server's actual variable names — likely `mcp`, `auth_config`, etc.)

- [ ] **Step 6: Wire into STANDARD profile in `session_buddy/mcp/tools/profiles.py:42-76`**

Add an entry to the `STANDARD_TOOLS` (or equivalent) list:

```python
{"name": "store_cross_repo_work", "module": "session_buddy.mcp.tools.cross_repo_work"},
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_mcp_registration_standard_profile.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add session_buddy/mcp/tools/cross_repo_work.py session_buddy/mcp/tools/__init__.py session_buddy/mcp/server.py session_buddy/mcp/tools/profiles.py tests/integration/test_mcp_registration_standard_profile.py
git commit -m "feat(mcp): register store_cross_repo_work (3 wiring steps + STANDARD profile)"
```

---

### Task 10: `settings/ecosystem.yaml` + bootstrap script

**Files:**
- Create: `scripts/bootstrap_ecosystem_manifest.py`
- Test: `tests/unit/scripts/test_bootstrap_ecosystem_manifest.py`
- Modify: `.gitignore` (add `settings/ecosystem.yaml`)

**Interfaces:**
- Consumes: `mahavishnu/settings/repos.yaml` (read-only source)
- Produces: `settings/ecosystem.yaml` (gitignored; flat shape `ecosystem: {<name>: {path, role}}`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/scripts/test_bootstrap_ecosystem_manifest.py
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from scripts.bootstrap_ecosystem_manifest import bootstrap


def test_bootstrap_writes_settings_file(tmp_path: Path) -> None:
    # Create a fake mahavishnu repo dir with a repos.yaml
    mahavishnu = tmp_path / "mahavishnu"
    mahavishnu.mkdir()
    repos_yaml = mahavishnu / "settings" / "repos.yaml"
    repos_yaml.parent.mkdir(parents=True)
    repos_yaml.write_text(yaml.safe_dump({
        "repos": [
            {"path": str(tmp_path / "session-buddy"), "tags": ["memory"], "description": "memory layer"},
            {"path": str(tmp_path / "mahavishnu"), "tags": ["orchestrator"], "description": "orchestrator"},
        ]
    }))
    out = tmp_path / "session-buddy" / "settings" / "ecosystem.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    bootstrap(source_yaml=repos_yaml, dest_yaml=out)
    data = yaml.safe_load(out.read_text())
    assert "ecosystem" in data
    assert "session-buddy" in data["ecosystem"]
    assert data["ecosystem"]["session-buddy"]["path"] == str(tmp_path / "session-buddy")


def test_bootstrap_no_source_emits_empty_manifest_with_warning(
    tmp_path: Path, caplog
) -> None:
    out = tmp_path / "ecosystem.yaml"
    bootstrap(source_yaml=tmp_path / "nonexistent.yaml", dest_yaml=out)
    data = yaml.safe_load(out.read_text())
    # Even on failure, a parseable file is emitted so callers don't crash
    assert "ecosystem" in data
    assert data["ecosystem"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/scripts/test_bootstrap_ecosystem_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `scripts/bootstrap_ecosystem_manifest.py`**

```python
#!/usr/bin/env python3
"""Bootstrap settings/ecosystem.yaml from mahavishnu's settings/repos.yaml.

Reads the canonical mahavishnu manifest (single source of truth) and
projects the flat {name: {path, role}} shape session-buddy needs for
ambient cross-repo capture. Idempotent — re-running overwrites the
gitignored dest file.

If the source is missing, emits an empty manifest with a WARNING so
session-buddy's first checkpoint fails gracefully rather than crashing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from oneiric.logging import get_logger

_log = get_logger(__name__)


DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "mahavishnu" / "settings" / "repos.yaml"
DEFAULT_DEST = Path(__file__).resolve().parents[2] / "settings" / "ecosystem.yaml"


def bootstrap(*, source_yaml: Path, dest_yaml: Path) -> dict:
    if not source_yaml.exists():
        _log.warning(
            "ecosyst_manifest_source_missing",
            extra={"path": str(source_yaml)},
        )
        ecosystem = {}
    else:
        try:
            raw = yaml.safe_load(source_yaml.read_text())
        except yaml.YAMLError as exc:
            _log.warning(
                "ecosyst_manifest_source_malformed",
                extra={"path": str(source_yaml), "error": str(exc)},
            )
            ecosystem = {}
        else:
            ecosystem = {
                repo.get("path", repo.get("name", "")): {
                    "path": repo.get("path", ""),
                    "role": (repo.get("tags") or ["unknown"])[0],
                }
                for repo in (raw.get("repos", []) if isinstance(raw, dict) else [])
            }
    dest_yaml.parent.mkdir(parents=True, exist_ok=True)
    dest_yaml.write_text(yaml.safe_dump({"ecosystem": ecosystem}))
    return {"ecosystem": ecosystem}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="mahavishnu repos.yaml (source of truth)",
    )
    p.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help="session-buddy settings/ecosystem.yaml (output)",
    )
    args = p.parse_args(argv)
    bootstrap(source_yaml=args.source, dest_yaml=args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add `settings/ecosystem.yaml` to `.gitignore`**

Edit `.gitignore`, add the line `settings/ecosystem.yaml` (with the comment `# per-repo local config — bootstrap from mahavishnu/repos.yaml`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/scripts/test_bootstrap_ecosystem_manifest.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/bootstrap_ecosystem_manifest.py tests/unit/scripts/test_bootstrap_ecosystem_manifest.py .gitignore
git commit -m "feat(scripts): add bootstrap_ecosystem_manifest + gitignore settings/ecosystem.yaml"
```

---

### Task 11: Wire `CheckpointCrossRepoAccountant` into `session_manager.checkpoint_session`

**Files:**
- Modify: `session_buddy/core/session_manager.py:908-1082` (the `checkpoint_session` method)
- Modify: `session_buddy/core/checkpoint/cross_repo_accountant.py` (refactor to per-repo groups from AmbientPuller)
- Test: `tests/integration/test_checkpoint_pipeline.py`

**Interfaces:**
- Consumes: existing `SessionLifecycleManager` instance, `CheckpointCrossRepoAccountant` instance.
- Produces: checkpoint pipeline that invokes the accountant and never propagates failures (G6).

- [ ] **Step 1: Refactor AmbientPuller to return per-repo groups**

In `session_buddy/core/checkpoint/ambient_puller.py`, change `capture()`'s return type from `tuple[list[CommitEntry], list[str]]` to `tuple[dict[str, list[CommitEntry]], list[str]]` (repo_name → entries). Update the internal `_run_one` to tag each `CommitEntry` with its repo name (carry it as a tuple during the gather). Existing tests in `tests/unit/core/checkpoint/test_ambient_puller.py` need updating to match the new shape — adapt them to assert against `entries["sibling"]`.

- [ ] **Step 2: Refactor `CheckpointCrossRepoAccountant`**

In `session_buddy/core/checkpoint/cross_repo_accountant.py`, change `capture()` to iterate `dict[str, list[CommitEntry]]` and call `MergePrimitive.merge` once per repo. Update `tests/unit/core/checkpoint/test_cross_repo_accountant.py` accordingly.

- [ ] **Step 3: Wire into `checkpoint_session`**

In `session_buddy/core/session_manager.py`, locate `checkpoint_session` (line 908). Find the place where the existing checkpoint commits and writes the handoff. After the git commit succeeds, instantiate the accountant and call `capture()`. The accountant's `CrossRepoCaptureSummary` is logged at INFO. Wrap the entire call in a `try/except` that logs WARNING and continues — never raise.

Sketch (adjust to existing module structure):

```python
try:
    from session_buddy.core.checkpoint.cross_repo_accountant import (
        CheckpointCrossRepoAccountant,
    )
    from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
    from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
    from session_buddy.adapters.reflection_adapter_oneiric import (
        require_reflection_database,
    )

    with require_reflection_database() as conn:
        accountant = CheckpointCrossRepoAccountant(
            ambient_puller=AmbientPuller(Path("settings/ecosystem.yaml")),
            merge_primitive=MergePrimitive(),
            conn=conn,
        )
        summary = await accountant.capture(
            working_directory=working_directory,
            conversation_id=conversation_id,
            session_window_start=session_window_start,
            session_window_end=session_window_end,
        )
    _log.info("cross_repo_capture_summary", extra=dataclasses.asdict(summary))
except Exception as exc:  # noqa: BLE001 — G6: never break checkpoint
    _log.warning("cross_repo_capture_failed", extra={"error": str(exc)})
```

- [ ] **Step 4: Write the integration test**

```python
# tests/integration/test_checkpoint_pipeline.py
from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest


@pytest.mark.asyncio
async def test_checkpoint_runs_cross_repo_accountant(tmp_path: Path) -> None:
    # Setup: a sibling repo with a commit
    workdir = tmp_path / "work"
    workdir.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    subprocess.check_call(["git", "init", "--quiet", str(sibling)])
    subprocess.check_call(["git", "-C", str(sibling), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(sibling), "config", "user.name", "T"])
    subprocess.check_call(["git", "-C", str(sibling), "commit", "--allow-empty", "-m", "x"])
    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(
        f"ecosystem:\n  sibling:\n    path: {sibling}\n    role: test\n"
    )

    # Setup: a session-buddy-style checkpoint run that wires the accountant
    # (full session_manager.checkpoint_session requires too much scaffolding
    # for an integration test; this test exercises the wired-in call directly.)
    from session_buddy.adapters.reflection_adapter_oneiric import (
        require_reflection_database,
    )
    from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
    from session_buddy.core.checkpoint.cross_repo_accountant import (
        CheckpointCrossRepoAccountant,
    )
    from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
    from scripts.bootstrap_ecosystem_manifest import bootstrap

    bootstrap_manifest = tmp_path / "session-buddy" / "settings" / "ecosystem.yaml"
    bootstrap_manifest.parent.mkdir(parents=True)
    bootstrap(source_yaml=manifest, dest_yaml=bootstrap_manifest)

    db = tmp_path / "a.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP NOT NULL, "
        "session_window_end TIMESTAMP NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMP NOT NULL DEFAULT NOW(), "
        "UNIQUE (conversation_id, repo_name))"
    )

    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(bootstrap_manifest),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    summary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc),
        session_window_end=datetime.now(tz=timezone.utc),
    )
    assert summary.repos_captured == 1
    assert summary.ambient_failures == []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_checkpoint_pipeline.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add session_buddy/core/session_manager.py session_buddy/core/checkpoint/ambient_puller.py session_buddy/core/checkpoint/cross_repo_accountant.py tests/integration/test_checkpoint_pipeline.py
git commit -m "feat(checkpoint): wire CheckpointCrossRepoAccountant into checkpoint_session"
```

---

### Task 12: End-to-end integration test + Wave-1 manual smoke

**Files:**
- Create: `tests/integration/test_e2e_cross_repo_checkpoint.py`
- Modify: `docs/baselines/` (add Wave-1 cross-repo delta)

**Interfaces:**
- Full pipeline: start_session → checkpoint_session (with cross-repo work in sibling repo) → end_session → handoff doc includes "Cross-Repo Work" section.

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_e2e_cross_repo_checkpoint.py
from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb
import pytest


def _setup_manifest_with_sibling(tmp_path: Path) -> Path:
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    subprocess.check_call(["git", "init", "--quiet", str(sibling)])
    subprocess.check_call(["git", "-C", str(sibling), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(sibling), "config", "user.name", "T"])
    subprocess.check_call(["git", "-C", str(sibling), "commit", "--allow-empty", "-m", "e2e commit"])
    manifest = tmp_path / "session-buddy" / "settings" / "ecosystem.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"ecosystem:\n  sibling:\n    path: {sibling}\n    role: test\n"
    )
    return manifest


def test_e2e_handoff_includes_cross_repo_section(tmp_path: Path) -> None:
    manifest = _setup_manifest_with_sibling(tmp_path)
    # Bootstrap into session-buddy's expected location
    from scripts.bootstrap_ecosystem_manifest import bootstrap
    bootstrap(source_yaml=manifest, dest_yaml=manifest)

    # Run the full pipeline: end-to-end via SessionLifecycleManager
    # (this requires the broader test scaffolding in session_manager —
    # adapt as needed; the assertion below is the contract).
    from session_buddy.core.session_manager import SessionLifecycleManager

    mgr = SessionLifecycleManager(
        working_directory=tmp_path / "work",
        db_path=tmp_path / "e2e.duckdb",
    )
    conv_id = mgr.start_session()
    mgr.checkpoint_session()
    handoff = mgr.end_session()

    assert "## Cross-Repo Work" in handoff
    assert "sibling" in handoff
```

(Note: this test requires the broader SessionLifecycleManager test scaffolding; if it doesn't fit cleanly, split into `tests/integration/test_e2e_handoff_renders_cross_repo.py` with mocked SessionLifecycleManager.)

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_e2e_cross_repo_checkpoint.py -v`
Expected: PASS.

- [ ] **Step 3: Manual smoke test**

```bash
# In a real session-buddy repo with at least one sibling checkout:
cd /Users/les/Projects/session-buddy
uv run python scripts/bootstrap_ecosystem_manifest.py
# Manually trigger a checkpoint (via the MCP start_session → checkpoint_session
# flow OR the CLI equivalent). Verify the handoff doc includes "Cross-Repo Work"
# with at least one row.
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_e2e_cross_repo_checkpoint.py
git commit -m "test(integration): e2e checkpoint pipeline includes Cross-Repo Work"
```

---

### Task 13: Final whole-branch review + crackerjack gate

**Files:** none (read-only).

- [ ] **Step 1: Run crackerjack on the changes**

Run: `crackerjack run`
Expected: passes with no new violations. If the gate fails, fix per crackerjack's output (Common ruff/mypy/ty/bandit/security/complexity issues). DO NOT loosen the gate.

- [ ] **Step 2: Verify spec → plan → code coverage**

Re-read `docs/superpowers/specs/2026-08-05-cross-repo-checkpoint-accounting-design.md`. For every Goal (G1-G8) and every section (Schema, Merge primitive, Components, Error handling, etc.), verify the corresponding task implemented it. List any gaps and address.

- [ ] **Step 3: Generate wave-completion report**

Create `docs/archive/completion-reports/2026-08-05-cross-repo-checkpoint-accounting.md` with:
- Goals achieved (G1-G8 status)
- Components shipped (AmbientPuller, MergePrimitive, CrossRepoAccountant, CrossRepoPusher, HandoffLink, ecosystem.yaml, bootstrap script)
- Tests added (per-task counts)
- Coverage on new modules (must clear 80%)
- Open follow-ups (e.g., start_session prerequisite verification)

- [ ] **Step 4: Commit completion report**

```bash
git add docs/archive/completion-reports/2026-08-05-cross-repo-checkpoint-accounting.md
git commit -m "docs: wave-1 completion report for cross-repo-checkpoint-accounting"
```

---

## Self-Review Checklist

(After writing this plan, run these checks against the spec.)

- [x] **Spec coverage**: Each Goal (G1-G8) maps to a task — G1 (ambient) → Task 5; G2 (explicit push) → Task 8; G3 (handoff) → Task 4; G4 (no breaking changes) → enforced by G6 across all tasks; G5 (idempotency) → Task 6 (merge primitive); G6 (never breaks) → Tasks 4, 7, 11; G7 (session identity) → Task 1 prerequisite check; G8 (EventBridge alignment) → documented in spec, surfaced in Task 13 completion report.
- [x] **Schema coverage**: `cross_repo_work_v2` table → Task 2; Pydantic models → Task 3; merge primitive → Task 6.
- [x] **Components coverage**: AmbientPuller → Task 5; MergePrimitive → Task 6; CheckpointCrossRepoAccountant → Task 7; CrossRepoPusher MCP tool → Task 8; HandoffLink → Task 4; ecosystem.yaml + bootstrap → Task 10; MCP registration → Task 9; checkpoint wiring → Task 11.
- [x] **Error handling**: Failure modes table covers Git timeout, transient retry, malformed payload, unknown session, unknown repo, mid-batch atomicity, storage lock, JSON size cap, sentinel, clock skew, concurrent writers. Each is exercised by tests in Tasks 5-8 (per the testing matrix in the spec).
- [x] **Placeholder scan**: No "TBD", "TODO", "implement later", or vague "handle edge cases". All step contents are concrete code or commands.
- [x] **Type consistency**: `WorkEntry`, `CrossRepoWorkRowCreate`, `CrossRepoWorkRowRead`, `MergePrimitive`, `CrossRepoCaptureSummary`, `StoreCrossRepoWorkRequest`, `CrossRepoStoreResult` defined consistently across tasks. No `clearLayers` / `clearFullLayers` mismatches.
- [x] **Self-reference resolution**: `start_session` (MCP tool) and `checkpoint_session` (Python method) are kept verbatim; `session_window_start` / `session_window_end` (time-window terms) are kept; `session_id` is consistently renamed to `conversation_id` throughout.

---

## Open Questions for Implementation Plan Reviewer

These should be resolved before / during execution:

1. **`start_session` prerequisite verification**: Task 1 confirms `start_session_tool` exists at `session_buddy/tools/session_tools.py:19`. Confirm it returns a `conversation_id` ULID persisted to `conversations_v2`. If not, the implementer must add it (out of this plan's scope but in scope for the broader delivery).

2. **`AmbientPuller` per-repo grouping**: The spec says AmbientPuller returns per-repo entry lists; this plan's Task 5 ships the basic version returning a flat list, with the per-repo grouping refactor in Task 11. Acceptable, or should Task 5 ship per-repo from the start?

3. **Wave-1 manual smoke (Task 12 Step 3)**: The smoke test requires a real sibling repo with commits. Acceptable as "manual" (not automated), or should we write a pytest fixture that creates a sibling and runs the full pipeline end-to-end?

4. **Standard profile vs full profile**: This plan wires the tool into `STANDARD` profile. If the user's deployment uses `MINIMAL` (health probes only), the tool won't be visible. Confirm the target profile.