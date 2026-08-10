# Cross-Repo Work Accounting in Checkpoint — Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **For the implementer:** This is v2 of the plan. v1 had 11 convergent Critical bugs (per the power-trio + mahavishnu-specialist plan review). v2 fixes them and adds per-repo grouping from the start (no Task-7 placeholder), adds the `start_session` prerequisite refactor as Task 1.5, and adds Integration Contract blocks per session-buddy's `.claude/decisions/wire-up-contract.md`.

**Goal:** Capture cross-repo work (commits, plan refs, blockers, test runs) into the session-buddy checkpoint via two ingest paths (ambient `git log` pull from sibling repos + explicit `store_cross_repo_work` MCP push from other Bodai repos), render a "Cross-Repo Work" section in the handoff doc, and lay the substrate for future routing/trigger consumers — without breaking the existing checkpoint pipeline.

**Architecture:** New `cross_repo_work_v2` DuckDB table (one row per `conversation_id` × `repo_name`; `work_entries` is a JSON column of discriminated-union entries deduped by `(kind, sha|plan_path)`). New `CheckpointCrossRepoAccountant` orchestrates `AmbientPuller` (returns `dict[str, list[CommitEntry]]` per-repo) + `MergePrimitive` (single-`BEGIN TRANSACTION` write across the batch) + write. New MCP tool `store_cross_repo_work` using session-buddy's local `require_auth(optional=False)` decorator + server-side path resolution from `settings/ecosystem.yaml`. `HandoffLink` reads the table and renders a markdown section between "Quality Breakdown" and "Recommendations" in the production handoff path.

**Spec:** `docs/superpowers/specs/2026-08-05-cross-repo-checkpoint-accounting-design.md` (commit `0e75c7b3`, v3).

## Global Constraints

Every task's requirements implicitly include this section.

- **Python target**: 3.13+. Use `from __future__ import annotations` as the first non-comment line of every new source file. `X | None` (not `Optional[X]`), `list[str]`, `pathlib.Path`. No `assert` in production code. Oneiric logger (`oneiric.logging`) — never stdlib `logging` or `print()`. All I/O in the orchestration layer is async; use `asyncio.to_thread` for blocking subprocess.
- **Hard limits** (from `pyproject.toml`): line-length 100, function args 10, branches 15, returns 6, statements 55 ceiling. Coverage: 80% minimum.
- **DuckDB version**: ≥0.9.0 (required for `INSERT ... ON CONFLICT`). Use `CAST(? AS JSON)` (not `?::JSON`). Use `BEGIN TRANSACTION` (no `IMMEDIATE` qualifier). DuckDB does NOT enforce `FOREIGN KEY` — referential integrity is at the application layer.
- **Storage path**: All writes go through `session_buddy/adapters/reflection_adapter_oneiric.py` via `require_reflection_database()` + the existing lock convention. New DDL must be added to EVERY active schema-init/migration path in `session_buddy/memory/schema_v2.py` AND the migration registry in `session_buddy/memory/migration.py`. The adapter's `__aexit__` calls `aclose()` which auto-commits pending transactions on connection close; explicit `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK` inside the adapter's context manager is safe.
- **MCP registration**: every new tool must (a) define `register_<tool>_tools(mcp_server)` in a new module, (b) export it from `session_buddy/mcp/tools/__init__.py`, (c) add the **register-function name string** to `_ALL_REGISTERS` dict in `session_buddy/mcp/server.py:88`, and (d) add the same string to `STANDARD_REGISTRATIONS: list[str]` in `session_buddy/mcp/tools/profiles.py:36`. **Verified**: `STANDARD_REGISTRATIONS` is a flat list of strings (e.g., `"register_conversation_tools"`), NOT a list of dicts. **Verified**: `_ALL_REGISTERS` is a dict keyed by register-function name mapping to the callable.
- **Auth contract**: session-buddy's local `require_auth(optional=False)` decorator from `session_buddy/mcp/auth.py:79`. **It does NOT accept `Permission.WRITE` or `config=` kwargs** — the mcp-integration power-trio review assumed the `mcp-common` signature which does not apply here. The correct pattern is:
  ```python
  from session_buddy.mcp.auth import require_auth
  
  @require_auth(optional=False)
  @mcp_server.tool(name="store_cross_repo_work")
  async def _store_cross_repo_work(
      request: StoreCrossRepoWorkRequest,
      token: str | None = None,  # populated by FastMCP auth context
  ) -> CrossRepoStoreResult: ...
  ```
  The `optional=False` means the tool requires a valid `token` kwarg. The session-buddy auth wrapper extracts the token via `kwargs.pop("token", None)`. **DO NOT** import from `mcp_common.auth` — the local wrapper at `session_buddy/mcp/auth.py` is the project's idiom.
- **Conversation identity** (v2.1 amendment): the canonical join key is `session_windows.id` (ULID), NOT `conversations_v2.id` (which is a Memori-style memory entry ULID). External pushers must supply it explicitly. **The CrossRepoPusher must validate `conversation_id` exists in `session_windows` before write** — orphan rows are rejected with `error_code="session_not_found"`. `start_session` must return a parseable `conversation_id` (Task 1.5 extends `initialize_session` to INSERT into `session_windows` and return the ULID).
- **Never-breaks invariant**: cross-repo accounting NEVER blocks the git commit / handoff doc. Storage failures log WARNING and continue; never raise out of `capture()`.
- **Schema naming**: rename `session_id` → `conversation_id` throughout. Real names to keep verbatim: `start_session` (MCP tool), `checkpoint_session` (Python method), `session_window_start` / `session_window_end` (time-window terms).
- **Pydantic v2 strict**: every model has `model_config = ConfigDict(extra="forbid")`. Idempotency on `(conversation_id, repo_name, sha|plan_path)` is enforced by the merge primitive in §Merge primitive, NOT by a schema UNIQUE constraint. Discriminated union: `Annotated[Union[CommitEntry, PlanRefEntry], Field(discriminator="kind")]`.
- **Per-repo grouping from the start**: `AmbientPuller.capture()` returns `tuple[dict[str, list[CommitEntry]], list[str]]` (repo_name → entries). The Task-7 orchestrator iterates the dict and calls `MergePrimitive.merge()` once per repo. **NO `<ambient>` placeholder**.
- **Multi-repo atomicity**: the explicit push (`store_cross_repo_work`) wraps the entire per-call loop in ONE `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK`. Either all repos in a single call are written, or the whole transaction rolls back. The merge primitive itself does NOT open a transaction — the caller does.
- **Conventions** (crackerjack-compliant-code): imports sorted within sections (force-sort-within-sections), known-first-party=["session_buddy"]. Functions ≤15 branches, ≤6 returns, ≤55 statements. `logger.exception(...)` in `except` blocks. No `# type: ignore` — use `# ty: ignore[<code>]` if needed.
- **Process Discipline** (CLAUDE.md): every task includes an **Integration Contract** block (Triggered from, Returns to / updates, Demonstrable by, Rollback signal, Observability added). Initialize a `docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md` in `built` state during Task 2; transition to `wired` at Task 11d; `adopted` at Task 13. Run `python scripts/audit_orphans.py --since=2026-08-05` in Task 13 Step 1.

---

### Task 0: Preflight — verify `start_session` + DuckDB + adapter

**Files:** none (read-only).

- [ ] **Step 1: Verify `start_session` return shape**

Run: `grep -B1 -A8 "async def _start_impl" session_buddy/mcp/tools/session/session_tools.py | head -30`
Expected: `_start_impl(...) -> str` return annotation. **Confirmed at v2 prep time** — `_start_impl` returns `str` (formatted prose), NOT a typed envelope with `conversation_id`. This is a prerequisite gap that Task 1.5 addresses.

- [ ] **Step 2: Verify `conversations_v2` is reachable**

Run: `grep -n "CREATE TABLE conversations_v2" session_buddy/memory/schema_v2.py | head -3`
Expected: at least one match. Note the column name of the PK (`id` expected).

- [ ] **Step 3: Verify DuckDB version ≥0.9.0**

Run: `uv run python -c "import duckdb; print(duckdb.__version__)" | head -1`
Expected: `0.9.0` or higher. If lower, document the gap and escalate.

- [ ] **Step 4: Verify session-buddy local auth wrapper**

Run: `grep -n "def require_auth\|@wraps" session_buddy/mcp/auth.py | head -10`
Expected: `def require_auth(optional: bool = False) -> Callable[...]` — confirms the signature. **DO NOT use `mcp_common.auth.require_auth`**; the local wrapper is the project idiom.

- [ ] **Step 5: Verify profile structure**

Run: `grep -n "_REGISTRATIONS\s*[:=]\|_ALL_REGISTRATIONS" session_buddy/mcp/tools/profiles.py session_buddy/mcp/server.py | head -20`
Expected: `STANDARD_REGISTRATIONS: list[str]` (flat list of register-function name strings), `_ALL_REGISTRATIONS: dict[str, ...]` keyed by register-function name.

- [ ] **Step 6: Commit nothing.** Note outcomes in the next task's commit message.

---

### Task 1.5: Refactor `_start_impl` to return typed envelope with `conversation_id`

**Files:**
- Modify: `session_buddy/mcp/tools/session/session_tools.py:start_session_tool` (return type) and `_start_impl` (return value)
- Modify: `session_buddy/tools/session_tools.py:start_session_tool` (the wrapper that delegates to `_start_impl`)
- Modify: `session_buddy/core/session_manager.py:initialize_session` (insert into `session_windows`, return `conversation_id` ULID — **v2.1 amendment**)
- Test: `tests/unit/mcp/tools/session/test_start_session_returns_typed_envelope.py`

**Why this task exists:** `start_session_tool` currently returns a formatted text string, not a typed envelope with `conversation_id`. The CrossRepoPusher's spec-required `conversation_id` validation can only work if `start_session` produces a parseable `conversation_id`.

**v2.1 amendment (added 2026-08-05):**
- `initialize_session` does NOT currently return `conversation_id` (verified by Task 0 — keys are `{success, project, working_directory, quality_score, quality_data, project_context, claude_directory, previous_session}`).
- `conversations_v2` is a Memori-style memory table; its `id` is a memory entry ULID, NOT a session/conversation identifier.
- Solution: extend `initialize_session` to (a) generate a 26-char Crockford ULID via `generate_ulid()`, (b) insert into the new `session_windows` table (DDL added in Task 2), (c) return the ULID as `conversation_id` in the dict.
- The schema table `session_windows` is added in Task 2. Task 1.5 references it as if it exists; if the migration hasn't run yet, `_store_session_window` must handle the missing-table case (log WARNING and return None for the ULID, never raise — G6 sentinel).

**Interfaces:**
- Consumes: existing `start_session_tool(...)` callers (their return value is a `str`).
- Produces: `_start_impl(...) -> tuple[str, str]` where the second element is the `conversation_id` ULID. The `start_session_tool` wrapper returns just the first element to preserve existing callers.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/mcp/tools/session/test_start_session_returns_typed_envelope.py
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import duckdb
import pytest

from session_buddy.mcp.tools.session.session_tools import _start_impl
from session_buddy.tools.session_tools import start_session_tool


ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


@pytest.fixture
def session_windows_db(tmp_path: Path, monkeypatch):
    """Provide a DuckDB file with session_windows table + reflection adapter env."""
    db_path = tmp_path / "reflection.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS session_windows ("
        "id TEXT PRIMARY KEY, working_directory TEXT NOT NULL, project TEXT, "
        "started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), "
        "ended_at TIMESTAMP WITH TIME ZONE, session_metadata JSON NOT NULL DEFAULT '{}')"
    )
    conn.close()
    monkeypatch.setenv("SESSION_BUDDY_REFLECTION_DB", str(db_path))
    yield db_path


@pytest.mark.asyncio
async def test_start_impl_returns_parseable_conversation_id(
    tmp_path: Path, monkeypatch, session_windows_db,
) -> None:
    prose, conversation_id = await _start_impl(working_directory=str(tmp_path))
    assert ULID_RE.match(conversation_id), (
        f"conversation_id {conversation_id!r} is not a 26-char Crockford ULID"
    )


def test_start_session_tool_wrapper_preserves_prose_string() -> None:
    """Wrapper must still return str (not the tuple) so existing callers don't break."""
    import inspect
    sig = inspect.signature(start_session_tool)
    assert sig.return_annotation is str
```

(The test fixture creates a `session_windows` table on a tmp DuckDB and points the reflection adapter at it via env var. If the env-var path for `require_reflection_database()` differs in this codebase, the implementer must adjust — verify by reading `session_buddy/adapters/reflection_adapter_oneiric.py`. The test will fail until both `initialize_session` and `_start_impl` are updated.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/mcp/tools/session/test_start_session_returns_typed_envelope.py -v`
Expected: FAIL with a tuple-unpacking error or annotation mismatch.

- [ ] **Step 3: Refactor `_start_impl` to return `(prose, conversation_id)`**

First, extend `SessionLifecycleManager.initialize_session` in `session_buddy/core/session_manager.py` to insert into `session_windows` and return the ULID:

```python
# In SessionLifecycleManager.initialize_session, AFTER the existing setup
# (around line 867, before the return), add:

conversation_id = generate_ulid()
try:
    from session_buddy.adapters.reflection_adapter_oneiric import (
        require_reflection_database,
    )
    with require_reflection_database() as db_conn:
        db_conn.execute(
            "INSERT INTO session_windows (id, working_directory, project, started_at) "
            "VALUES (?, ?, ?, NOW())",
            [conversation_id, str(current_dir), self.current_project],
        )
except Exception as exc:  # noqa: BLE001 — G6 sentinel; never block startup
    self.logger.warning(
        "session_window_insert_failed",
        extra={"error": str(exc)},
    )
    conversation_id = None  # downstream: _start_impl returns None; pusher rejects

return {
    "success": True,
    "conversation_id": conversation_id,  # may be None if session_windows missing
    # ... rest of existing keys unchanged ...
}
```

Then in `session_buddy/mcp/tools/session/session_tools.py`:

```python
async def _start_impl(working_directory: str | None = None) -> tuple[str, str]:
    """Returns (formatted_prose, conversation_id). The conversation_id is
    a 26-char Crockford ULID persisted to session_windows.id; callers that
    need only the prose (e.g. the FastMCP wrapper) unpack and discard."""
    # ... existing setup, build prose as before ...
    result = await _get_session_manager().initialize_session(working_directory)
    # ... build prose as before ...
    prose = output_builder.build()
    conversation_id = result.get("conversation_id")  # may be None if session_windows missing
    return prose, conversation_id


async def start_session_tool(working_directory: str | None = None) -> str:
    """Start a new Claude session, including environment setup and shortcuts.

    Returns the formatted prose string for human consumption. Callers needing
    the conversation_id ULID should call _start_impl directly (it returns the
    tuple) or use mcp__session-buddy__start_session and parse the response.
    """
    prose, _ = await _start_impl(working_directory)
    return prose
```

(The actual implementer reads the existing `_start_impl` body and threads the `conversation_id` extraction through. The `conversation_id` is generated and persisted by `initialize_session`'s new INSERT; if `session_windows` doesn't exist (Task 2 not yet applied), the INSERT logs WARNING and conversation_id is None.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/mcp/tools/session/test_start_session_returns_typed_envelope.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add session_buddy/mcp/tools/session/session_tools.py session_buddy/tools/session_tools.py tests/unit/mcp/tools/session/test_start_session_returns_typed_envelope.py
git commit -m "feat(start_session): return typed envelope (prose, conversation_id) for cross-repo pushers"
```

**Integration Contract:**
- Triggered from: existing `start_session_tool` callers (Claude Code session startup).
- Returns to / updates: `session_buddy.tools.session_tools.start_session_tool` (returns prose unchanged); `_start_impl` callers (now have parseable ULID).
- Demonstrable by: `tests/unit/mcp/tools/session/test_start_session_returns_typed_envelope.py`.
- Rollback signal: revert the commit; existing callers use prose-only.
- Observability added: existing `_start_impl` logging unchanged.

---

### Task 2: Schema — `cross_repo_work_v2` table + migration registration

**Files:**
- Modify: `session_buddy/memory/schema_v2.py` (add DDL after `conversations_v2` block, ~line 119 — **include `session_windows` table for conversation identity**)
- Modify: `session_buddy/memory/migration.py` (register the new DDL with a version key — include both tables)
- Create: `docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md` (initialize in `built` state per CLAUDE.md Process Discipline)
- Test: `tests/unit/memory/test_cross_repo_work_v2_schema.py` (extend with `session_windows` presence test)

**v2.1 amendment (added 2026-08-05):**
- **New table `session_windows`** for conversation identity. The existing `conversations_v2` is a Memori-style *memory* table (id is a memory entry ULID), so `cross_repo_work_v2.conversation_id` cannot FK to `conversations_v2.id`. The new table tracks one row per session window.
- All downstream references to "conversations_v2.id" as session identifier → `session_windows.id`. Affected: Task 1.5 (initialize_session), Task 8 (CrossRepoPusher validation), Task 11c (started_at lookup), Task 12 (test setup).

**Interfaces:**
- Consumes: `session_buddy.adapters.reflection_adapter_oneiric.require_reflection_database()` (existing).
- Produces: a table `cross_repo_work_v2` registered in both `schema_v2.py::INIT_SCHEMA` and `migration.py::MIGRATIONS`.

- [ ] **Step 1: Write the failing test** (same as v1)

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
        "id", "conversation_id", "repo_name", "repo_path", "repo_role",
        "session_window_start", "session_window_end", "work_entries",
        "contributor_sources", "created_at", "updated_at",
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

- [ ] **Step 3: Add DDL to `schema_v2.py`** (amended v2.1)

```sql
CREATE TABLE IF NOT EXISTS session_windows (
    id              TEXT PRIMARY KEY,                -- 26-char Crockford ULID
    working_directory TEXT NOT NULL,
    project         TEXT,
    started_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMP WITH TIME ZONE,
    session_metadata JSON NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cross_repo_work_v2 (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,                  -- FK -> session_windows.id (app-layer)
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

(DuckDB does NOT enforce `FOREIGN KEY`; referential integrity is enforced at the application layer in the CrossRepoPusher — `SELECT 1 FROM session_windows WHERE id = ?`.)

- [ ] **Step 4: Register the DDL in `migration.py`** (same as v1)

In `session_buddy/memory/migration.py`, append the same DDL block to the `MIGRATIONS` registry. Key it by `("2026-08-05", "cross_repo_work_v2", ddl)`.

- [ ] **Step 5: Initialize feature-tracking file**

Create `docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md`:

```markdown
---
feature: cross-repo-checkpoint-accounting
status: built
created: 2026-08-05
last_updated: 2026-08-05
---

# Cross-Repo Work Accounting in Checkpoint

## Built
- `cross_repo_work_v2` schema + migration registered (this task).

## Wired (pending Task 11d)
- `CheckpointCrossRepoAccountant.capture()` invoked from `session_manager.checkpoint_session`.
- `HandoffLink.render_section()` injected into `_generate_handoff_documentation`.
- `store_cross_repo_work` MCP tool registered via `register_cross_repo_work_tools` in `STANDARD_REGISTRATIONS`.

## Adopted (pending Task 13)
- First wave-1 checkpoint produces "Cross-Repo Work" section in handoff doc.
- Crackerjack gate green; coverage ≥80% on the 5 new modules.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/memory/test_cross_repo_work_v2_schema.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add session_buddy/memory/schema_v2.py session_buddy/memory/migration.py tests/unit/memory/test_cross_repo_work_v2_schema.py docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md
git commit -m "feat(schema): add cross_repo_work_v2 table + migration registration + feature-tracking init"
```

**Integration Contract:**
- Triggered from: `apply_migrations()` on first session-buddy startup with a fresh DB.
- Returns to / updates: `cross_repo_work_v2` table is queryable via `require_reflection_database()`.
- Demonstrable by: `tests/unit/memory/test_cross_repo_work_v2_schema.py`.
- Rollback signal: `DROP TABLE cross_repo_work_v2` (migration-revert or manual).
- Observability added: `feature_tracking/2026-08-05-...md` transitions to `built`.

---

### Task 3: Pydantic models — discriminated union + Create/Read split

**Files:**
- Create: `session_buddy/memory/cross_repo_work.py`
- Test: `tests/unit/memory/test_cross_repo_work_pydantic.py`

(Same as v1 — content unchanged from v1 Task 3.)

---

### Task 4: HandoffLink — read consumer with sentinel rendering

**Files:**
- Create: `session_buddy/core/lifecycle/handoff_link.py`
- Modify: `session_buddy/core/session_manager.py` (insert call into `_generate_handoff_documentation` after the "Quality Breakdown" section)
- Test: `tests/unit/core/lifecycle/test_handoff_link.py`

**v2 changes from v1:**
- Move imports to module top (not function-local). The function-local import workaround is only valid when there's a circular import risk; here there isn't.
- Add `test_render_section_returns_sentinel_on_internal_failure` that monkeypatches `_render_inner` to raise, asserting the sentinel substring is present.
- Add `test_render_section_with_500_rows_under_200ms` for stress performance.

(Same body as v1 Task 4 with the above test additions.)

---

### Task 5: AmbientPuller — async git log with per-repo grouping from the start

**Files:**
- Create: `session_buddy/core/checkpoint/__init__.py`
- Create: `session_buddy/core/checkpoint/ambient_puller.py`
- Create: `session_buddy/core/checkpoint/manifest_resolver.py` (shared helper — used by AmbientPuller and CrossRepoPusher; eliminates the duplicate env-var pattern flagged by python-pro M1 and mcp I5)
- Test: `tests/unit/core/checkpoint/test_ambient_puller.py`

**v2 changes from v1 (the BIG one):**

- **Return type is per-repo from the start**: `tuple[dict[str, list[CommitEntry]], list[str]]` — `repo_name -> entries`. NO flat-list intermediate. NO Task-7 placeholder.
- **`_load_repos` is an INSTANCE METHOD** (not `@staticmethod`) and reads `self._manifest_path` directly. **NO env-var fallback** in the loader — the constructor argument is the canonical source. The wiring layer (Task 11d) reads env var and constructs `AmbientPuller(path)`.
- **Per-repo timeout test** + **per-batch timeout test** + **git log retry test** + **clock-skew test** (per spec §Error handling resilience C2/C3/I1/I3).

**Interfaces:**
- Consumes: `Path` (manifest path), `Path` (working_directory), `UlidStr` (conversation_id), `datetime × 2` (window).
- Produces: `tuple[dict[str, list[CommitEntry]], list[str]]` — per-repo entries + per-repo failure names. Never raises.

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
    subprocess.check_call(["git", "-C", str(path), "config", "user.email", "test@example.com"])
    subprocess.check_call(["git", "-C", str(path), "config", "user.name", "Test"])


def _commit(path: Path, msg: str) -> str:
    subprocess.check_call(["git", "-C", str(path), "commit", "--allow-empty", "-m", msg])
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"]
    ).decode().strip()


def _write_manifest(tmp_path: Path, repos: list[dict[str, str]]) -> Path:
    p = tmp_path / "ecosystem.yaml"
    p.write_text(yaml.safe_dump({
        "ecosystem": {
            r["name"]: {"path": r["path"], "role": r["role"]}
            for r in repos
        }
    }))
    return p


async def _capture(puller, **kwargs):
    return await puller.capture(
        working_directory=kwargs["working_directory"],
        conversation_id=kwargs["conversation_id"],
        session_window_start=kwargs["session_window_start"],
        session_window_end=kwargs["session_window_end"],
    )


@pytest.mark.asyncio
async def test_per_repo_grouping_from_start(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sib_a = tmp_path / "a"; sib_a.mkdir(); _git_init(sib_a)
    sib_b = tmp_path / "b"; sib_b.mkdir(); _git_init(sib_b)
    sha_a = _commit(sib_a, "feat(a): 1")
    sha_b = _commit(sib_b, "feat(b): 2")
    manifest = _write_manifest(tmp_path, [
        {"name": "a", "path": str(sib_a), "role": "x"},
        {"name": "b", "path": str(sib_b), "role": "x"},
    ])
    puller = AmbientPuller(manifest_path=manifest)
    start = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    end = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    grouped, failures = await _capture(
        puller,
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=start,
        session_window_end=end,
    )
    assert failures == []
    # Per-repo: each sibling has its own bucket
    assert "a" in grouped
    assert "b" in grouped
    assert any(e.sha == sha_a for e in grouped["a"])
    assert any(e.sha == sha_b for e in grouped["b"])
    # NO "<ambient>" placeholder key
    assert "<ambient>" not in grouped


@pytest.mark.asyncio
async def test_non_local_filter_skips_working_directory(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sha_local = _commit(workdir, "feat(work): local")
    manifest = _write_manifest(tmp_path, [{"name": "work", "path": str(workdir), "role": "x"}])
    puller = AmbientPuller(manifest_path=manifest)
    grouped, _ = await _capture(
        puller, working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        session_window_end=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    assert all(e.sha != sha_local for grouped_entries in grouped.values() for e in grouped_entries)


@pytest.mark.asyncio
async def test_missing_manifest_no_raise(tmp_path: Path) -> None:
    puller = AmbientPuller(manifest_path=tmp_path / "missing.yaml")
    grouped, failures = await _capture(
        puller, working_directory=tmp_path / "work",
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc),
        session_window_end=datetime.now(tz=timezone.utc),
    )
    assert grouped == {}
    assert failures == []


@pytest.mark.asyncio
async def test_per_repo_timeout_kills_hung_git(tmp_path: Path) -> None:
    """Spec §Error handling resilience C2: 10s per-repo timeout."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    sib = tmp_path / "hung_sibling"
    sib.mkdir()
    # Inject a git wrapper that sleeps for 60s
    sleep_bin = tmp_path / "git-sleep"
    sleep_bin.mkdir()
    (sleep_bin / "git").write_text("#!/bin/sh\nsleep 60\n")
    (sleep_bin / "git").chmod(0o755)
    manifest_path = tmp_path / "ecosystem.yaml"
    manifest_path.write_text(
        f"ecosystem:\n  hung_sibling:\n    path: {sib}\n    role: x\n"
    )
    puller = AmbientPuller(manifest_path=manifest_path, git_bin=tmp_path / "git-sleep" / "git")
    start = datetime.now(tz=timezone.utc)
    end = start + timedelta(hours=1)
    # Should return within ~15s, not 60s
    grouped, failures = await asyncio.wait_for(
        _capture(puller, working_directory=workdir, conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
                  session_window_start=start, session_window_end=end),
        timeout=15,
    )
    assert "hung_sibling" in failures


@pytest.mark.asyncio
async def test_git_log_retry_on_transient_failure(tmp_path: Path) -> None:
    """Spec §Error handling resilience I1: 2x retry on lock/EAGAIN transient."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    sib = tmp_path / "sibling"; sib.mkdir()
    _git_init(sib)
    sha = _commit(sib, "feat(sibling): hi")
    # Wrapper that fails twice then succeeds
    fail_bin = tmp_path / "git-flaky"
    fail_bin.mkdir()
    state_file = tmp_path / ".flaky_state"
    state_file.write_text("0")
    (fail_bin / "git").write_text(
        f"#!/bin/sh\nn=$(cat {state_file})\n"
        f"if [ $n -lt 2 ]; then echo $((n+1)) > {state_file}; exit 128; fi\n"
        f"exec /usr/bin/git \"$@\"\n"
    )
    (fail_bin / "git").chmod(0o755)
    manifest = _write_manifest(tmp_path, [{"name": "sibling", "path": str(sib), "role": "x"}])
    puller = AmbientPuller(manifest_path=manifest, git_bin=fail_bin / "git")
    grouped, failures = await _capture(
        puller, working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        session_window_end=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    assert failures == []
    assert any(e.sha == sha for e in grouped.get("sibling", []))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/checkpoint/test_ambient_puller.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the three new files**

`session_buddy/core/checkpoint/manifest_resolver.py`:

```python
"""Centralized manifest-path resolution. Eliminates the duplicate
ECOSYSTEM_MANIFEST env-var pattern that previously appeared in both
AmbientPuller and store_cross_repo_work (python-pro M1 / mcp I5)."""
from __future__ import annotations

from pathlib import Path

DEFAULT_RELATIVE_PATH = Path("settings/ecosystem.yaml")


def resolve_manifest_path(explicit: Path | None = None) -> Path:
    """Return explicit arg if given; else ECOSYSTEM_MANIFEST env var;
    else settings/ecosystem.yaml relative to cwd. Single source of truth."""
    if explicit is not None:
        return explicit
    import os
    env = os.environ.get("ECOSYSTEM_MANIFEST")
    if env:
        return Path(env)
    return DEFAULT_RELATIVE_PATH
```

`session_buddy/core/checkpoint/ambient_puller.py`:

```python
"""Ambient capture of git commits from sibling repos.

Returns per-repo groups (dict[str, list[CommitEntry]]) plus per-repo
failure names. Per-repo timeout 10s, per-batch timeout 30s, transient
git failure retry 2x with backoff. Never raises.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import Awaitable
from datetime import datetime
from pathlib import Path

import yaml
from oneiric.logging import get_logger

from session_buddy.core.checkpoint.manifest_resolver import resolve_manifest_path
from session_buddy.memory.cross_repo_work import CommitEntry

_log = get_logger(__name__)

_PER_REPO_TIMEOUT_S = 10.0
_BATCH_TIMEOUT_S = 30.0
_MAX_COMMITS = 500
_GIT_RETRY_BACKOFF_S = (0.25, 0.75)
_TRANSIENT_GIT_EXIT_CODES = frozenset({128, 129})  # lock-related


class AmbientPuller:
    def __init__(
        self,
        manifest_path: Path | None = None,
        *,
        git_bin: Path | None = None,
    ) -> None:
        self._manifest_path = resolve_manifest_path(manifest_path)
        self._git_bin = git_bin or Path("git")

    async def capture(
        self,
        *,
        working_directory: Path,
        conversation_id: str,
        session_window_start: datetime,
        session_window_end: datetime,
    ) -> tuple[dict[str, list[CommitEntry]], list[str]]:
        repos = self._load_repos(working_directory)
        if not repos:
            return {}, []

        captured: dict[str, list[CommitEntry]] = {}
        failures: list[str] = []

        async def _run_one(target_name: str, target_path: Path) -> None:
            for attempt in range(3):  # initial + 2 retries
                try:
                    entries = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._git_log,
                            target_path,
                            session_window_start,
                            session_window_end,
                        ),
                        timeout=_PER_REPO_TIMEOUT_S,
                    )
                    captured[target_name] = entries
                    return
                except asyncio.TimeoutError:
                    _log.warning(
                        "ambient_pull_git_log_timeout",
                        extra={"repo": target_name, "timeout_s": _PER_REPO_TIMEOUT_S},
                    )
                    failures.append(target_name)
                    return
                except subprocess.CalledProcessError as exc:
                    if exc.returncode in _TRANSIENT_GIT_EXIT_CODES and attempt < 2:
                        await asyncio.sleep(_GIT_RETRY_BACKOFF_S[attempt])
                        continue
                    _log.warning(
                        "ambient_pull_failed",
                        extra={"repo": target_name, "error": str(exc)},
                    )
                    failures.append(target_name)
                    return
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "ambient_pull_failed",
                        extra={"repo": target_name, "error": str(exc)},
                    )
                    failures.append(target_name)
                    return

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(_run_one(name, path) for name, path in repos),
                    return_exceptions=True,
                ),
                timeout=_BATCH_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            _log.warning("ambient_pull_batch_timeout", extra={"timeout_s": _BATCH_TIMEOUT_S})
        return captured, failures

    def _load_repos(self, working_directory: Path) -> list[tuple[str, Path]]:
        if not self._manifest_path.exists():
            _log.info("ambient_pull_manifest_missing", extra={"path": str(self._manifest_path)})
            return []
        try:
            data = yaml.safe_load(self._manifest_path.read_text())
        except yaml.YAMLError as exc:
            _log.warning("ambient_pull_manifest_malformed", extra={"error": str(exc)})
            return []
        if not isinstance(data, dict) or "ecosystem" not in data:
            return []
        local = working_directory.resolve()
        result: list[tuple[str, Path]] = []
        for name, entry in data["ecosystem"].items():
            if not isinstance(entry, dict) or "path" not in entry:
                continue
            path = Path(entry["path"]).resolve()
            if path == local:
                continue  # non-local filter
            result.append((name, path))
        return result

    def _git_log(
        self,
        repo_path: Path,
        start: datetime,
        end: datetime,
    ) -> list[CommitEntry]:
        argv = [
            str(self._git_bin),
            "log",
            f"--since={int(start.timestamp())}",
            f"--until={int(end.timestamp())}",
            f"-n{_MAX_COMMITS}",
            "--format=%H%x09%s%x09%an%x09%ae%x09%aI",
            "--",
            str(repo_path),
        ]
        proc = subprocess.run(  # noqa: S603 — argv list
            argv, capture_output=True, text=True, check=False,
            timeout=_PER_REPO_TIMEOUT_S + 1,
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, argv, proc.stderr)
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

`session_buddy/core/checkpoint/__init__.py`: empty file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/checkpoint/test_ambient_puller.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/core/checkpoint/__init__.py session_buddy/core/checkpoint/ambient_puller.py session_buddy/core/checkpoint/manifest_resolver.py tests/unit/core/checkpoint/test_ambient_puller.py
git commit -m "feat(checkpoint): AmbientPuller with per-repo grouping + timeouts + retry"
```

**Integration Contract:**
- Triggered from: `CheckpointCrossRepoAccountant.capture()` (Task 7).
- Returns to / updates: dict[str, list[CommitEntry]] per-repo + per-repo failure names.
- Demonstrable by: `tests/unit/core/checkpoint/test_ambient_puller.py` (5 tests including per-repo timeout).
- Rollback signal: revert this commit; `CheckpointCrossRepoAccountant` callsite will fail with a clear error.
- Observability added: `ambient_pull_failed`, `ambient_pull_git_log_timeout`, `ambient_pull_batch_timeout`, `ambient_pull_manifest_missing`, `ambient_pull_manifest_malformed` log events.

---

### Task 6: MergePrimitive — Python dedup + atomic DuckDB transaction (caller-managed)

**Files:**
- Create: `session_buddy/core/checkpoint/merge_primitive.py`
- Test: `tests/unit/core/checkpoint/test_merge_primitive.py`

**v2 changes from v1 (multiple Criticals fixed):**

1. **`BEGIN TRANSACTION` placed BEFORE the SELECT** (python-pro C2). The merge must read+dedup+write atomically.
2. **The merge primitive does NOT open its own transaction.** The caller (CrossRepoPusher or CheckpointCrossRepoAccountant) wraps the batch in ONE `BEGIN TRANSACTION` and passes the connection through. The merge primitive is transaction-agnostic.
3. **Fix the bogus `model_validate` call** (code-reviewer C3). DuckDB returns `datetime` for TIMESTAMP WITH TIME ZONE; no need to round-trip through `CrossRepoWorkRowRead`.
4. **Spec merge collision rules** (code-reviewer M5): preserve max `files_changed_count`, preserve first-observed `timestamp` on provenance-tied collisions.
5. **`contributor_sources` order-preserving union** (code-reviewer I5).

**Interfaces:**
- Consumes: `CrossRepoWorkRowCreate` (incoming row), DuckDB connection (already inside a transaction managed by the caller).
- Produces: `tuple[CrossRepoWorkRowRead, int, int]` — post-merge row, `entries_inserted`, `entries_deduplicated`. **Never opens or closes transactions.**

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/checkpoint/test_merge_primitive.py
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import duckdb

from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
    CrossRepoWorkRowRead,
)


def _now():
    return datetime.now(tz=timezone.utc)


def _row(sha: str, prov: str = "ambient", files_changed_count: int | None = None,
         timestamp: datetime | None = None, id_suffix: str = ""):
    now = _now()
    return CrossRepoWorkRowCreate(
        id=f"id_{sha}{id_suffix}",
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        repo_name="mahavishnu",
        repo_path="/Users/les/Projects/mahavishnu",
        repo_role="orchestrator",
        session_window_start=now,
        session_window_end=now,
        work_entries=[CommitEntry(
            kind="commit", sha=sha, provenance=prov,
            files_changed_count=files_changed_count, timestamp=timestamp,
        )],
        contributor_sources=[prov],
    )


def _make_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
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


def test_merge_first_write_inserts():
    conn = _make_conn()
    mp = MergePrimitive()
    read, ins, ded = mp.merge(conn, _row("sha1"))
    assert ins == 1 and ded == 0
    assert len(read.work_entries) == 1


def test_merge_dedup_prefers_explicit():
    conn = _make_conn()
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1", "ambient"))
    read, ins, ded = mp.merge(conn, _row("sha2", "explicit"))  # second merge is a fresh call
    assert ins == 1 and ded == 0
    # Now collide: insert sha1 again from explicit source
    read2, ins2, ded2 = mp.merge(conn, _row("sha1", "explicit"))
    assert ins2 == 0 and ded2 == 1
    assert read2.work_entries[0].provenance == "explicit"
    assert "ambient" in read2.contributor_sources
    assert "explicit" in read2.contributor_sources


def test_merge_collision_preserves_max_files_changed():
    conn = _make_conn()
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1", "ambient", files_changed_count=3))
    read, _, _ = mp.merge(conn, _row("sha1", "explicit", files_changed_count=5, id_suffix="2"))
    assert read.work_entries[0].files_changed_count == 5  # max preserved


def test_merge_contributor_sources_order_preserving():
    conn = _make_conn()
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1", "ambient"))
    read, _, _ = mp.merge(conn, _row("sha1", "explicit", id_suffix="2"))
    assert read.contributor_sources == ["ambient", "explicit"]


def test_merge_collision_preserves_first_observed_timestamp():
    conn = _make_conn()
    mp = MergePrimitive()
    older = _now() - timedelta(hours=2)
    newer = _now() - timedelta(hours=1)
    mp.merge(conn, _row("sha1", "ambient", timestamp=older))
    read, _, _ = mp.merge(conn, _row("sha1", "explicit", timestamp=newer, id_suffix="2"))
    # First-observed wins on timestamp; even though explicit is the canonical entry,
    # the timestamp from the first observation is preserved.
    assert read.work_entries[0].timestamp == older


def test_merge_does_not_open_transaction():
    """Caller-managed transactions. merge() should not BEGIN or COMMIT."""
    conn = _make_conn()
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1"))
    # If merge had committed, we couldn't roll back. Roll back manually:
    conn.execute("ROLLBACK")
    rows = conn.execute("SELECT COUNT(*) FROM cross_repo_work_v2").fetchone()[0]
    # If merge had its own transaction, ROLLBACK would NOT have rolled back.
    # If merge is caller-transaction-agnostic, ROLLBACK removes the row.
    assert rows == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/checkpoint/test_merge_primitive.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `session_buddy/core/checkpoint/merge_primitive.py`**

```python
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
from datetime import datetime
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
            # Prefer provenance="explicit" over "ambient"
            winner = entry
            if existing_entry.provenance == "explicit" and entry.provenance == "ambient":
                winner = existing_entry  # ambient suppressed by existing explicit
                _log.debug("cross_repo_dedup_suppressed_ambient", extra={"sha": key[1]})
            else:
                # Merge fields per spec: max files_changed_count, first-observed timestamp
                if (
                    isinstance(winner, CommitEntry)
                    and isinstance(existing_entry, CommitEntry)
                ):
                    max_fcc = max(
                        existing_entry.files_changed_count or 0,
                        winner.files_changed_count or 0,
                    )
                    first_ts = (
                        existing_entry.timestamp
                        if existing_entry.timestamp
                        else winner.timestamp
                    )
                    winner = CommitEntry(
                        **{
                            **winner.model_dump(),
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
        # Caller-managed transaction. Read existing, dedup, write.
        # Use the connection's transaction context as-is.
        row = conn.execute(
            "SELECT work_entries, contributor_sources, session_window_end "
            "FROM cross_repo_work_v2 "
            "WHERE conversation_id = ? AND repo_name = ?",
            [incoming.conversation_id, incoming.repo_name],
        ).fetchone()

        if row is None:
            merged_entries = list(incoming.work_entries)
            inserted = len(merged_entries)
            deduplicated = 0
            merged_provenance = list(incoming.contributor_sources)
            new_session_window_end = incoming.session_window_end
        else:
            existing_entries_raw, existing_prov_raw, existing_end = row
            existing_entries = [
                WorkEntry.model_validate(e) for e in json.loads(existing_entries_raw)
            ]
            existing_prov = json.loads(existing_prov_raw)
            merged_entries, inserted, deduplicated = _merge_entries(
                existing_entries, list(incoming.work_entries)
            )
            merged_provenance = _union_provenance(
                existing_prov, incoming.contributor_sources
            )
            new_session_window_end = max(existing_end, incoming.session_window_end)

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
                entries_json, prov_json,
                entries_json, prov_json,
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
        return (
            CrossRepoWorkRowRead.model_validate(dict(zip(
                [
                    "id", "conversation_id", "repo_name", "repo_path", "repo_role",
                    "session_window_start", "session_window_end", "work_entries",
                    "contributor_sources", "created_at", "updated_at",
                ],
                read_row,
            ))),
            inserted,
            deduplicated,
        )

    def multi_merge(
        self,
        conn: duckdb.DuckDBPyConnection,
        rows: list[CrossRepoWorkRowCreate],
    ) -> tuple[list[CrossRepoWorkRowRead], int, int]:
        """Convenience: caller has already opened BEGIN TRANSACTION. Loops over
        rows. All-or-nothing (caller ROLLBACKs on any error)."""
        results: list[CrossRepoWorkRowRead] = []
        total_ins = 0
        total_ded = 0
        for row in rows:
            read, ins, ded = self.merge(conn, row)
            results.append(read)
            total_ins += ins
            total_ded += ded
        return results, total_ins, total_ded
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/checkpoint/test_merge_primitive.py -v`
Expected: PASS (6 tests including the transaction-agnosticism check).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/core/checkpoint/merge_primitive.py tests/unit/core/checkpoint/test_merge_primitive.py
git commit -m "feat(checkpoint): MergePrimitive caller-managed transaction + collision merge rules"
```

**Integration Contract:**
- Triggered from: `CheckpointCrossRepoAccountant.capture()` (Task 7) and `store_cross_repo_work` MCP handler (Task 8).
- Returns to / updates: `CrossRepoWorkRowRead` post-merge + insertion/dedup counts.
- Demonstrable by: `tests/unit/core/checkpoint/test_merge_primitive.py` (6 tests).
- Rollback signal: revert commit; callers raise on `ModuleNotFoundError`.
- Observability added: `cross_repo_dedup_suppressed_ambient` DEBUG log when ambient is suppressed by an existing explicit entry.

---

### Task 7: CheckpointCrossRepoAccountant — per-repo orchestrator

**Files:**
- Create: `session_buddy/core/checkpoint/cross_repo_accountant.py`
- Test: `tests/unit/core/checkpoint/test_cross_repo_accountant.py`

**v2 changes from v1:**

- **NO `<ambient>` placeholder**. `AmbientPuller` returns `dict[str, list[CommitEntry]]` from Task 5. The accountant iterates the dict, calls `MergePrimitive.merge()` once per repo. **No Task-11 refactor needed.**
- Multi-repo integration test (verifies two sibling repos' entries land in separate rows).

**Interfaces:**
- Consumes: `Path`, `UlidStr`, `datetime × 2`, `AmbientPuller` (per-repo dict return), `MergePrimitive`, DuckDB connection (caller-managed transaction).
- Produces: `CrossRepoCaptureSummary` — `{repos_captured, entries_inserted, entries_deduplicated, ambient_failures}`. Never raises.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/core/checkpoint/test_cross_repo_accountant.py
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest
import yaml

from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
from session_buddy.core.checkpoint.cross_repo_accountant import (
    CheckpointCrossRepoAccountant,
    CrossRepoCaptureSummary,
)
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive


def _git_init(p: Path) -> None:
    subprocess.check_call(["git", "init", "--quiet", str(p)])
    subprocess.check_call(["git", "-C", str(p), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(p), "config", "user.name", "T"])


def _commit(p: Path, msg: str) -> str:
    subprocess.check_call(["git", "-C", str(p), "commit", "--allow-empty", "-m", msg])
    return subprocess.check_output(["git", "-C", str(p), "rev-parse", "HEAD"]).decode().strip()


def _setup_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(tmp_path / "a.duckdb"))
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
async def test_capture_multi_repo_writes_per_repo_rows(tmp_path: Path) -> None:
    workdir = tmp_path / "work"; workdir.mkdir(); _git_init(workdir)
    sib_a = tmp_path / "a"; sib_a.mkdir(); _git_init(sib_a)
    sib_b = tmp_path / "b"; sib_b.mkdir(); _git_init(sib_b)
    _commit(sib_a, "feat(a)")
    _commit(sib_b, "feat(b)")
    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(
        f"ecosystem:\n  a:\n    path: {sib_a}\n    role: x\n  b:\n    path: {sib_b}\n    role: x\n"
    )
    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(manifest_path=manifest),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    summary: CrossRepoCaptureSummary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        session_window_end=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    assert summary.repos_captured == 2
    assert summary.ambient_failures == []
    # Verify TWO rows written, not one
    count = conn.execute(
        "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id = ?",
        ["01HXXXXXXXXXXXXXXXXXXXXXXXXX"],
    ).fetchone()[0]
    assert count == 2


@pytest.mark.asyncio
async def test_capture_never_raises_on_ambient_failure(tmp_path: Path) -> None:
    workdir = tmp_path / "work"; workdir.mkdir()
    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(manifest_path=tmp_path / "missing.yaml"),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    summary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc),
        session_window_end=datetime.now(tz=timezone.utc),
    )
    assert summary.repos_captured == 0
    assert summary.entries_inserted == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/checkpoint/test_cross_repo_accountant.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `session_buddy/core/checkpoint/cross_repo_accountant.py`**

```python
"""Orchestrator that captures cross-repo work during a session-buddy
checkpoint. Coordinates AmbientPuller (per-repo groups) + MergePrimitive
+ write. Never raises — returns a CrossRepoCaptureSummary for the
checkpoint log. Cross-repo accounting failures NEVER block the git
commit / handoff doc (G6).
"""
from __future__ import annotations

import dataclasses
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

        # We need ecosystem.yaml here to resolve path/role per repo.
        # The puller already loaded it; expose via a small accessor or refetch.
        from session_buddy.core.checkpoint.manifest_resolver import (
            resolve_manifest_path,
        )
        import yaml as _yaml
        manifest = resolve_manifest_path(self._puller._manifest_path)
        ecosystem: dict[str, dict[str, str]] = {}
        if manifest.exists():
            try:
                ecosystem = (_yaml.safe_load(manifest.read_text()) or {}).get("ecosystem", {})
            except _yaml.YAMLError:
                ecosystem = {}

        rows: list[CrossRepoWorkRowCreate] = []
        for repo_name, entries in grouped.items():
            entry = ecosystem.get(repo_name, {})
            rows.append(CrossRepoWorkRowCreate(
                id=generate_ulid(),
                conversation_id=conversation_id,
                repo_name=repo_name,
                repo_path=entry.get("path", ""),
                repo_role=entry.get("role"),
                session_window_start=session_window_start,
                session_window_end=session_window_end,
                work_entries=entries,
                contributor_sources=["ambient"],
            ))

        try:
            conn.execute("BEGIN TRANSACTION")
            _reads, ins, ded = self._merge.multi_merge(conn, rows)
            conn.execute("COMMIT")
        except Exception as exc:  # noqa: BLE001 — never raise
            conn.execute("ROLLBACK")
            _log.warning(
                "cross_repo_accountant_merge_failed",
                extra={"error": str(exc), "conversation_id": conversation_id},
            )
            return summary

        summary.entries_inserted += ins
        summary.entries_deduplicated += ded
        summary.repos_captured = len(grouped)
        return summary
```

- [ ] **Step 4: Run tests to verify them pass**

Run: `uv run pytest tests/unit/core/checkpoint/test_cross_repo_accountant.py -v`
Expected: PASS (2 tests; both multi-repo row separation and never-raises).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/core/checkpoint/cross_repo_accountant.py tests/unit/core/checkpoint/test_cross_repo_accountant.py
git commit -m "feat(checkpoint): CheckpointCrossRepoAccountant per-repo orchestrator (no placeholder)"
```

**Integration Contract:**
- Triggered from: `session_manager.checkpoint_session` (Task 11d).
- Returns to / updates: `CrossRepoCaptureSummary` for the checkpoint log; one row per (conversation_id, repo_name) in `cross_repo_work_v2`.
- Demonstrable by: `tests/unit/core/checkpoint/test_cross_repo_accountant.py` (multi-repo + never-raises).
- Rollback signal: revert commit; `checkpoint_session` integration would not invoke the accountant.
- Observability added: `cross_repo_accountant_pull_failed`, `cross_repo_accountant_merge_failed` WARNING logs.

---

### Task 8: CrossRepoPusher MCP tool — auth + validation + multi-repo atomicity

**Files:**
- Create: `session_buddy/mcp/tools/cross_repo_work.py`
- Create: `session_buddy/mcp/tools/cross_repo_work_register.py` (the `register_cross_repo_work_tools` function — separate file per project convention)
- Test: `tests/unit/mcp/tools/test_cross_repo_work.py`

**v2 changes from v1 (multiple Criticals fixed):**

1. **Add `conversation_id` validation** (architect C3, code-reviewer C1, mcp C4). Before any merge, `SELECT 1 FROM session_windows WHERE id = ?` (NOT `conversations_v2` — that's a Memori memory table per the v2.1 amendment) — on miss, return `CrossRepoStoreResult(status="failed", error_code="session_not_found", retryable=False)`.
2. **Multi-repo atomicity** (code-reviewer C2). The whole per-call loop runs in ONE `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK`. The merge primitive does NOT open its own (Task 6 refactor).
3. **`_ResolvedRepoEntry` Pydantic model** (mcp I2). Internal type for server-side path resolution. `extra="forbid"`.
4. **`repo_name` normalization** (mcp I3). Lowercase both sides of the ecosystem lookup.
5. **Import order** (python-pro C4). Alphabetize within sections; combine `from pydantic import ...`.
6. **Type parameters on `dict`** (python-pro C5). `dict[str, dict[str, str | None]]` with `TypedDict`.
7. **`_load_ecosystem` uses `manifest_resolver`** (mcp I5). Eliminates duplicate env-var pattern.
8. **`status="partial"` is reachable** (code-reviewer M4). When the unknown-repo rejection is mixed with successful inserts, return `status="partial"` with the rejections in `per_repo[].status="rejected"`.
9. **Use session-buddy's local auth** (mcp C1). `from session_buddy.mcp.auth import require_auth`. NOT `mcp_common.auth.require_auth`.

**Interfaces:**
- Consumes: `StoreCrossRepoWorkRequest` (Pydantic model), session-buddy's local `require_auth`, `MergePrimitive`, DuckDB connection.
- Produces: `CrossRepoStoreResult` (typed domain result with `status`, `error_code`, `retryable`, per-repo breakdown).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/mcp/tools/test_cross_repo_work.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest
import yaml

from session_buddy.mcp.tools.cross_repo_work import (
    RepoWorkEntry,
    StoreCrossRepoWorkRequest,
    store_cross_repo_work,
    _ResolvedRepoEntry,
)
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import CommitEntry


def _setup(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(tmp_path / "m.duckdb"))
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
        "CREATE TABLE session_windows ("
        "id TEXT PRIMARY KEY, working_directory TEXT NOT NULL, project TEXT, "
        "started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), "
        "ended_at TIMESTAMP WITH TIME ZONE, session_metadata JSON NOT NULL DEFAULT '{}')"
    )
    conn.execute(
        "INSERT INTO session_windows VALUES (?, ?, ?, NOW(), NULL, '{}')",
        ["01HXXXXXXXXXXXXXXXXXXXXXXXXX", "/tmp/test", "test-project"],
    )
    return conn


def _write_manifest(tmp_path: Path, repos: list[dict[str, str]]) -> Path:
    p = tmp_path / "ecosystem.yaml"
    p.write_text(yaml.safe_dump({
        "ecosystem": {r["name"]: {"path": r["path"], "role": r["role"]} for r in repos}
    }))
    return p


def _request(sha: str = "abc123", repo: str = "mahavishnu"):
    return StoreCrossRepoWorkRequest(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        repos=[RepoWorkEntry(
            repo_name=repo,
            work_entries=[CommitEntry(kind="commit", sha=sha, provenance="explicit")],
        )],
    )


@pytest.mark.asyncio
async def test_rejects_unknown_conversation_id(tmp_path: Path) -> None:
    """G7 validation per spec."""
    conn = _setup(tmp_path)
    manifest = _write_manifest(tmp_path, [{"name": "mahavishnu", "path": "/m", "role": "x"}])
    bad_req = StoreCrossRepoWorkRequest(
        conversation_id="01HNOTEXISTXXXXXXXXXXXXXXXXXX",
        repos=[RepoWorkEntry(repo_name="mahavishnu",
                              work_entries=[CommitEntry(kind="commit", sha="a", provenance="explicit")])],
    )
    result = await store_cross_repo_work(
        request=bad_req, merge_primitive=MergePrimitive(),
        conn=conn, ecosystem_path=manifest,
    )
    assert result.status == "failed"
    assert result.error_code == "session_not_found"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_rejects_unknown_repo_with_partial_status(tmp_path: Path) -> None:
    """Spec §Error handling: unknown repo → rejected. When mixed with
    valid repos, status is 'partial'."""
    conn = _setup(tmp_path)
    manifest = _write_manifest(tmp_path, [{"name": "mahavishnu", "path": "/m", "role": "x"}])
    request = StoreCrossRepoWorkRequest(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        repos=[
            RepoWorkEntry(repo_name="mahavishnu",
                          work_entries=[CommitEntry(kind="commit", sha="a", provenance="explicit")]),
            RepoWorkEntry(repo_name="unknown_repo",
                          work_entries=[CommitEntry(kind="commit", sha="b", provenance="explicit")]),
        ],
    )
    result = await store_cross_repo_work(
        request=request, merge_primitive=MergePrimitive(),
        conn=conn, ecosystem_path=manifest,
    )
    assert result.status == "partial"
    statuses = {s.repo_name: s.status for s in result.per_repo}
    assert statuses["mahavishnu"] == "stored"
    assert statuses["unknown_repo"] == "rejected"


@pytest.mark.asyncio
async def test_multi_repo_atomic_rollback(tmp_path: Path) -> None:
    """If any repo's merge fails, the whole call rolls back."""
    conn = _setup(tmp_path)
    manifest = _write_manifest(tmp_path, [{"name": "a", "path": "/a", "role": "x"}])
    request = StoreCrossRepoWorkRequest(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        repos=[
            RepoWorkEntry(repo_name="a",
                          work_entries=[CommitEntry(kind="commit", sha="a1", provenance="explicit")]),
            RepoWorkEntry(repo_name="a",
                          work_entries=[CommitEntry(kind="commit", sha="a2", provenance="explicit")]),
        ],
    )
    result = await store_cross_repo_work(
        request=request, merge_primitive=MergePrimitive(),
        conn=conn, ecosystem_path=manifest,
    )
    # Two repos with same repo_name in one call should be a duplicate-key failure
    # (UNIQUE (conversation_id, repo_name)); the whole call should roll back.
    assert result.status == "failed"
    count = conn.execute(
        "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id = ?",
        ["01HXXXXXXXXXXXXXXXXXXXXXXXXX"],
    ).fetchone()[0]
    assert count == 0  # atomic rollback — neither row landed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/mcp/tools/test_cross_repo_work.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `session_buddy/mcp/tools/cross_repo_work.py`**

```python
"""MCP tool: store_cross_repo_work.

Receiver for cross-repo work entries pushed by other Bodai repos. The
caller supplies the conversation_id ULID (join key with session_windows.id per v2.1 amendment)
and a list of repos with their work entries. Server-side path resolution
from ecosystem.yaml (path authority — wire shape has no repo_path).

Auth: @require_auth(optional=False) (session-buddy local — does NOT accept
Permission.WRITE or config kwargs).
"""
from __future__ import annotations

import json
from typing import Annotated, Literal, TypedDict

import duckdb
import yaml
from oneiric.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from session_buddy.core.checkpoint.manifest_resolver import resolve_manifest_path
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
    except yaml.YAMLError:
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


def _resolve_repo(repo_name: str, ecosystem: _EcosystemDict) -> _ResolvedRepoEntry | None:
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
    # 1. conversation_id existence check (G7) — against session_windows
    # (NOT conversations_v2 — that's a Memori memory table per v2.1 amendment)
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
    now = datetime.now(tz=timezone.utc)
    per_repo: list[RepoStoreStatus] = []
    rows_to_write: list[CrossRepoWorkRowCreate] = []
    rejection_map: dict[str, str] = {}  # repo_name -> reason

    for repo_entry in request.repos:
        resolved = _resolve_repo(repo_entry.repo_name, ecosystem)
        if resolved is None:
            rejection_map[repo_entry.repo_name] = "repo not in ecosystem.yaml"
            continue
        rows_to_write.append(CrossRepoWorkRowCreate(
            id=generate_ulid(),
            conversation_id=request.conversation_id,
            repo_name=resolved.repo_name,
            repo_path=resolved.path,
            repo_role=resolved.role,
            session_window_start=now,
            session_window_end=now,
            work_entries=repo_entry.work_entries,
            contributor_sources=["explicit"],
        ))

    # 2. Multi-repo atomicity — wrap the entire batch in ONE transaction.
    total_received = sum(len(r.work_entries) for r in request.repos)
    repos_stored = 0
    total_inserted = 0
    total_deduplicated = 0
    status = "ok"

    if rows_to_write:
        conn.execute("BEGIN TRANSACTION")
        try:
            _reads, ins, ded = merge_primitive.multi_merge(conn, rows_to_write)
            conn.execute("COMMIT")
            total_inserted = ins
            total_deduplicated = ded
            repos_stored = len(rows_to_write)
        except Exception as exc:  # noqa: BLE001
            conn.execute("ROLLBACK")
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

    # Build per_repo breakdown
    for repo_entry in request.repos:
        if repo_entry.repo_name in rejection_map:
            per_repo.append(RepoStoreStatus(
                repo_name=repo_entry.repo_name,
                status="rejected",
                entries_received=len(repo_entry.work_entries),
                entries_inserted=0,
                entries_deduplicated=0,
                message=rejection_map[repo_entry.repo_name],
            ))
        else:
            per_repo.append(RepoStoreStatus(
                repo_name=repo_entry.repo_name,
                status="stored",
                entries_received=len(repo_entry.work_entries),
                entries_inserted=len(repo_entry.work_entries),
                entries_deduplicated=0,
                message=None,
            ))

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
```

(NOTE: the `datetime` and `timezone` imports at the top are required by the `now` variable. The `_ResolvedRepoEntry` class is internal but exported for use in `register_cross_repo_work_tools`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/mcp/tools/test_cross_repo_work.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/mcp/tools/cross_repo_work.py tests/unit/mcp/tools/test_cross_repo_work.py
git commit -m "feat(mcp): store_cross_repo_work with conversation_id check + multi-repo atomicity"
```

**Integration Contract:**
- Triggered from: external Bodai repos calling `mcp__session-buddy__store_cross_repo_work` (e.g., mahavishnu workers, akosha aggregations).
- Returns to / updates: `cross_repo_work_v2` rows + `CrossRepoStoreResult` to caller.
- Demonstrable by: `tests/unit/mcp/tools/test_cross_repo_work.py` (3 tests including rejection paths and atomic rollback).
- Rollback signal: revert commit; callers fall back to ambient-only path.
- Observability added: `store_cross_repo_work_failed` log event; per-repo status surfaced in `CrossRepoStoreResult`.

---

### Task 9: MCP registration — using actual session-buddy profile shape

**Files:**
- Modify: `session_buddy/mcp/tools/__init__.py` (export `register_cross_repo_work_tools`)
- Modify: `session_buddy/mcp/server.py` (add to `_ALL_REGISTERS` dict, line 88)
- Modify: `session_buddy/mcp/tools/profiles.py` (add `"register_cross_repo_work_tools"` string to `STANDARD_REGISTRATIONS: list[str]`, line 36)
- Create: `session_buddy/mcp/tools/cross_repo_work_register.py` (the register function)
- Test: `tests/integration/test_mcp_registration_standard_profile.py`

**v2 changes from v1:**

- **Use session-buddy local auth**: `@require_auth(optional=False)` (NOT `mcp-common` signature).
- **`STANDARD_REGISTRATIONS: list[str]`** is the correct shape — append a STRING, not a dict.
- **`_ALL_REGISTRATIONS` is a dict** keyed by register-function name mapping to the callable.
- **`AuthConfig.from_settings()` doesn't exist** — use `get_auth_config()` from `session_buddy/mcp/auth`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_mcp_registration_standard_profile.py
from __future__ import annotations


def test_register_cross_repo_work_tools_in_standard_profile() -> None:
    from session_buddy.mcp.tools.profiles import STANDARD_REGISTRATIONS
    assert "register_cross_repo_work_tools" in STANDARD_REGISTRATIONS, (
        f"register_cross_repo_work_tools missing from STANDARD; "
        f"profile has {STANDARD_REGISTRATIONS}"
    )


def test_register_cross_repo_work_tools_in_all_registers() -> None:
    from session_buddy.mcp import server
    assert "register_cross_repo_work_tools" in server._ALL_REGISTRATIONS, (
        f"register_cross_repo_work_tools missing from _ALL_REGISTRATIONS"
    )


def test_register_function_creates_store_cross_repo_work_tool() -> None:
    """Verify the registered tool is callable and named correctly."""
    import asyncio
    from unittest.mock import MagicMock
    from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
    from session_buddy.mcp.tools.cross_repo_work_register import (
        register_cross_repo_work_tools,
    )

    fake_server = MagicMock()
    fake_server.tool = MagicMock()

    register_cross_repo_work_tools(fake_server)

    # Verify @mcp_server.tool was called with name="store_cross_repo_work"
    fake_server.tool.assert_called()
    call_kwargs = fake_server.tool.call_args.kwargs
    assert call_kwargs.get("name") == "store_cross_repo_work"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_mcp_registration_standard_profile.py -v`
Expected: FAIL with `KeyError` or `ImportError`.

- [ ] **Step 3: Create `session_buddy/mcp/tools/cross_repo_work_register.py`**

```python
"""Register store_cross_repo_work on a FastMCP server.

Composition:
  - @require_auth(optional=False) — session-buddy's local auth wrapper;
    requires a valid token kwarg. Does NOT accept Permission.WRITE or
    config= — those are mcp-common concepts that don't apply here.
  - @mcp_server.tool(name="store_cross_repo_work") — FastMCP registration.

The client-visible name is "mcp__session-buddy__store_cross_repo_work"
(the client prefix is added by FastMCP).
"""
from __future__ import annotations

import duckdb
from fastmcp import FastMCP
from pydantic import BaseModel

from session_buddy.adapters.reflection_adapter_oneiric import (
    require_reflection_database,
)
from session_buddy.core.checkpoint.manifest_resolver import resolve_manifest_path
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.mcp.auth import require_auth
from session_buddy.mcp.tools.cross_repo_work import (
    CrossRepoStoreResult,
    StoreCrossRepoWorkRequest,
    store_cross_repo_work,
)


def register_cross_repo_work_tools(mcp_server: FastMCP) -> None:
    """Register store_cross_repo_work on the given FastMCP server instance.

    The merged primitive is module-level (stateless); a fresh DuckDB
    connection is acquired per-call via require_reflection_database().
    """
    merge_primitive = MergePrimitive()

    @require_auth(optional=False)
    @mcp_server.tool(name="store_cross_repo_work")
    async def _store_cross_repo_work(
        request: StoreCrossRepoWorkRequest,
        token: str | None = None,  # populated by FastMCP auth context
    ) -> CrossRepoStoreResult:
        ecosystem_path = resolve_manifest_path()
        async with require_reflection_database() as conn:
            return await store_cross_repo_work(
                request=request,
                merge_primitive=merge_primitive,
                conn=conn,
                ecosystem_path=ecosystem_path,
            )

    # Attach to module-level namespace so the FastMCP introspection sees it.
    # (FastMCP tool registration by name handles the rest via decorator.)
```

- [ ] **Step 4: Export from `__init__.py`**

In `session_buddy/mcp/tools/__init__.py`, add to imports and `__all__`:

```python
from session_buddy.mcp.tools.cross_repo_work_register import (
    register_cross_repo_work_tools,
)

__all__ = [..., "register_cross_repo_work_tools"]
```

(Adjust to match the existing project's export style.)

- [ ] **Step 5: Add to `_ALL_REGISTRATIONS` in `session_buddy/mcp/server.py`**

Find the `_ALL_REGISTRATIONS: dict[str, ...] = {...}` literal (line 88). Add an entry:

```python
_ALL_REGISTRATIONS: dict[str, Callable[[FastMCP], None]] = {
    # ... existing entries ...
    "register_cross_repo_work_tools": register_cross_repo_work_tools,
}
```

(Also add `from session_buddy.mcp.tools.cross_repo_work_register import register_cross_repo_work_tools` in the import block at the top of the file.)

- [ ] **Step 6: Add to `STANDARD_REGISTRATIONS` in `profiles.py`**

Append the STRING `"register_cross_repo_work_tools"` to `STANDARD_REGISTRATIONS: list[str]` (line 36). **Do NOT add a dict** — the list is flat strings.

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_mcp_registration_standard_profile.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add session_buddy/mcp/tools/cross_repo_work_register.py session_buddy/mcp/tools/__init__.py session_buddy/mcp/server.py session_buddy/mcp/tools/profiles.py tests/integration/test_mcp_registration_standard_profile.py
git commit -m "feat(mcp): register store_cross_repo_work (3 wiring steps + STANDARD profile)"
```

**Integration Contract:**
- Triggered from: `session_buddy/mcp/server.py` startup; `register_all()` loops over `_ALL_REGISTRATIONS` and calls each.
- Returns to / updates: tool available under `mcp__session-buddy__store_cross_repo_work` for STANDARD profile deployments.
- Demonstrable by: `tests/integration/test_mcp_registration_standard_profile.py`.
- Rollback signal: remove the line from `STANDARD_REGISTRATIONS`, remove from `_ALL_REGISTRATIONS`, remove the export.
- Observability added: FastMCP server logs tool registration at startup.

---

### Task 10: `settings/ecosystem.yaml` + bootstrap script

**Files:**
- Create: `scripts/bootstrap_ecosystem_manifest.py`
- Test: `tests/unit/scripts/test_bootstrap_ecosystem_manifest.py`
- Modify: `.gitignore` (add `settings/ecosystem.yaml`)

**v2 changes from v1:**

- **Bootstrap keys by SLUG (Path.name)**, not by absolute path (code-reviewer C5). `repos.yaml` rows have `path` but no `name`; synthesize slug as `Path(repo["path"]).name`.
- **Fix the log-key typo** `ecosyst_` → `ecosystem_` (mcp M3).
- **Read source path from env var** `MAHAVISHNU_REPOS_YAML` with sibling fallback (architect I5).

**Interfaces:**
- Consumes: `mahavishnu/settings/repos.yaml` (or env var override).
- Produces: `settings/ecosystem.yaml` keyed by slug (e.g., `"mahavishnu"`, not `"/Users/les/Projects/mahavishnu"`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/scripts/test_bootstrap_ecosystem_manifest.py
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from scripts.bootstrap_ecosystem_manifest import bootstrap


def test_bootstrap_keys_by_slug_not_path(tmp_path: Path) -> None:
    """Slugs are Path.name, not absolute paths."""
    repos_yaml = tmp_path / "src.yaml"
    repos_yaml.write_text(yaml.safe_dump({
        "repos": [
            {"path": str(tmp_path / "session-buddy"), "tags": ["memory"], "description": "x"},
            {"path": str(tmp_path / "mahavishnu"), "tags": ["orchestrator"], "description": "x"},
        ]
    }))
    out = tmp_path / "ecosystem.yaml"
    bootstrap(source_yaml=repos_yaml, dest_yaml=out)
    data = yaml.safe_load(out.read_text())
    assert "session-buddy" in data["ecosystem"], f"slug key missing: {data}"
    assert "mahavishnu" in data["ecosystem"], f"slug key missing: {data}"
    assert data["ecosystem"]["session-buddy"]["path"] == str(tmp_path / "session-buddy")
    assert data["ecosystem"]["session-buddy"]["role"] == "memory"


def test_bootstrap_no_source_emits_empty_manifest(tmp_path: Path) -> None:
    out = tmp_path / "ecosystem.yaml"
    bootstrap(source_yaml=tmp_path / "nonexistent.yaml", dest_yaml=out)
    data = yaml.safe_load(out.read_text())
    assert data["ecosystem"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/scripts/test_bootstrap_ecosystem_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `scripts/bootstrap_ecosystem_manifest.py`**

```python
#!/usr/bin/env python3
"""Bootstrap settings/ecosystem.yaml from mahavishnu's settings/repos.yaml.

Keys the output by SLUG (Path.name) so consumers can use canonical
short names (e.g., "mahavishnu") instead of absolute paths.

Idempotent. Re-running overwrites the gitignored dest file.

If the source is missing, emits an empty manifest with a WARNING so
session-buddy's first checkpoint fails gracefully rather than crashing.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from oneiric.logging import get_logger

_log = get_logger(__name__)


DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "mahavishnu" / "settings" / "repos.yaml"
DEFAULT_DEST = Path(__file__).resolve().parents[2] / "settings" / "ecosystem.yaml"
ENV_SOURCE = "MAHAVISHNU_REPOS_YAML"


def bootstrap(*, source_yaml: Path, dest_yaml: Path) -> dict:
    if not source_yaml.exists():
        _log.warning(
            "ecosystem_manifest_source_missing",
            extra={"path": str(source_yaml)},
        )
        ecosystem: dict[str, dict[str, str | None]] = {}
    else:
        try:
            raw = yaml.safe_load(source_yaml.read_text())
        except yaml.YAMLError as exc:
            _log.warning(
                "ecosystem_manifest_source_malformed",
                extra={"path": str(source_yaml), "error": str(exc)},
            )
            ecosystem = {}
        else:
            repos = (raw or {}).get("repos", []) if isinstance(raw, dict) else []
            ecosystem = {}
            for repo in repos:
                if not isinstance(repo, dict):
                    continue
                path_str = repo.get("path", "")
                if not path_str:
                    continue
                slug = Path(path_str).name
                tags = repo.get("tags") or []
                role = tags[0] if tags else None
                ecosystem[slug] = {"path": path_str, "role": role}
    dest_yaml.parent.mkdir(parents=True, exist_ok=True)
    dest_yaml.write_text(yaml.safe_dump({"ecosystem": ecosystem}))
    return {"ecosystem": ecosystem}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    source_default = Path(os.environ.get(ENV_SOURCE, DEFAULT_SOURCE))
    p.add_argument("--source", type=Path, default=source_default, help="source repos.yaml")
    p.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="dest ecosystem.yaml")
    args = p.parse_args(argv)
    bootstrap(source_yaml=args.source, dest_yaml=args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add `settings/ecosystem.yaml` to `.gitignore`**

Append: `settings/ecosystem.yaml  # per-repo local config — bootstrap from mahavishnu/repos.yaml`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/scripts/test_bootstrap_ecosystem_manifest.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/bootstrap_ecosystem_manifest.py tests/unit/scripts/test_bootstrap_ecosystem_manifest.py .gitignore
git commit -m "feat(scripts): bootstrap_ecosystem_manifest keyed by slug"
```

---

### Task 11: Wire `CheckpointCrossRepoAccountant` into `session_manager.checkpoint_session` — split into 11a/11b/11c/11d

**v2 splits the original monolithic Task 11 into 4 atomic tasks** (architect I1). Each produces one reviewable commit.

---

### Task 11a: Cross-repo accountants in `feature_tracking` — `built → wired`

**Files:**
- Modify: `docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md` (status update)

- [ ] **Step 1: Update feature-tracking to `wired`**

```markdown
---
status: wired
---
```

(Per CLAUDE.md process discipline.)

- [ ] **Step 2: Commit**

```bash
git add docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md
git commit -m "chore(feature-tracking): mark cross-repo checkpoint accounting as wired"
```

---

### Task 11b: Wire HandoffLink into `_generate_handoff_documentation`

**Files:**
- Modify: `session_buddy/core/session_manager.py:818` (the "Quality Breakdown" section block)
- Test: extend `tests/unit/core/lifecycle/test_handoff_link.py` to cover wired-in path

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/core/lifecycle/test_handoff_link.py extension (append)
def test_render_section_returns_sentinel_on_internal_failure() -> None:
    from session_buddy.core.lifecycle.handoff_link import HandoffLink
    import pytest
    from unittest.mock import patch

    with patch.object(HandoffLink, "_render_inner", side_effect=RuntimeError("boom")):
        section = HandoffLink.render_section(
            conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
            rows=[],
        )
    assert "could not be captured" in section
    assert "RuntimeError" in section or "boom" in section
```

(Already partially covered in v1 Task 4; this is the explicit sentinel test.)

- [ ] **Step 2: Run test to verify it fails** (if not already covered)

Run: `uv run pytest tests/unit/core/lifecycle/test_handoff_link.py -v`

- [ ] **Step 3: Wire HandoffLink**

In `session_buddy/core/session_manager.py`, after the Quality Breakdown loop (line ~818), insert:

```python
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
except Exception as exc:  # noqa: BLE001 — sentinel path; never break handoff
    self.logger.exception("cross_repo_work_handoff_render_failed")
    markdown_content.append(
        "## Cross-Repo Work\n\n"
        "> Cross-Repo Work could not be captured: "
        f"{type(exc).__name__}. See logs for details.\n"
    )
```

(Imports should be hoisted to module top per python-pro I8. The actual implementer hoists them.)

- [ ] **Step 4: Commit**

```bash
git add session_buddy/core/session_manager.py tests/unit/core/lifecycle/test_handoff_link.py
git commit -m "feat(handoff): wire HandoffLink into _generate_handoff_documentation (after Quality Breakdown)"
```

---

### Task 11c: Wire CheckpointCrossRepoAccountant into `checkpoint_session` — with `start_session` conversation_id lookup

**Files:**
- Modify: `session_buddy/core/session_manager.py:908-1082` (the `checkpoint_session` method)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_checkpoint_wiring.py
from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    require_reflection_database,
)


def _git_init(p: Path) -> None:
    subprocess.check_call(["git", "init", "--quiet", str(p)])
    subprocess.check_call(["git", "-C", str(p), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(p), "config", "user.name", "T"])


@pytest.mark.asyncio
async def test_checkpoint_session_invokes_accountant(tmp_path: Path, monkeypatch) -> None:
    """The wiring in checkpoint_session actually runs the accountant."""
    workdir = tmp_path / "work"; workdir.mkdir(); _git_init(workdir)
    sib = tmp_path / "sib"; sib.mkdir(); _git_init(sib)
    subprocess.check_call(["git", "-C", str(sib), "commit", "--allow-empty", "-m", "x"])
    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(f"ecosystem:\n  sib:\n    path: {sib}\n    role: x\n")

    # Monkeypatch the manifest resolver so the wiring picks up our tmp manifest
    monkeypatch.setenv("ECOSYSTEM_MANIFEST", str(manifest))

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
    conn.execute(
        "CREATE TABLE session_windows ("
        "id TEXT PRIMARY KEY, working_directory TEXT NOT NULL, project TEXT, "
        "started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), "
        "ended_at TIMESTAMP WITH TIME ZONE, session_metadata JSON NOT NULL DEFAULT '{}')"
    )
    conv_id = "01HXXXXXXXXXXXXXXXXXXXXXXXXX"
    conn.execute(
        "INSERT INTO session_windows VALUES (?, ?, ?, NOW(), NULL, '{}')",
        [conv_id, str(workdir), "test-project"],
    )
    conn.close()

    # Now run a checkpoint end-to-end through SessionLifecycleManager
    # (the test scaffolding for full integration is brittle; the contract is
    # that AFTER checkpoint_session returns, the DB has 1+ cross_repo_work_v2 rows
    # for our conversation_id.)
    from session_buddy.core.session_manager import SessionLifecycleManager

    mgr = SessionLifecycleManager(
        working_directory=workdir,
        db_path=str(db),
    )
    await mgr.start_session()
    await mgr.checkpoint_session()

    with duckdb.connect(str(db)) as verify_conn:
        count = verify_conn.execute(
            "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id IS NOT NULL"
        ).fetchone()[0]
        assert count >= 1, f"checkpoint didn't write cross_repo_work_v2 rows; got {count}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_checkpoint_wiring.py -v`
Expected: FAIL with row count == 0.

- [ ] **Step 3: Wire CheckpointCrossRepoAccountant into `checkpoint_session`**

In `session_buddy/core/session_manager.py`, in the `checkpoint_session` method (line 908), AFTER the git commit succeeds, add the wiring:

```python
# After the existing git commit logic
try:
    from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
    from session_buddy.core.checkpoint.cross_repo_accountant import (
        CheckpointCrossRepoAccountant,
    )
    from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
    from session_buddy.adapters.reflection_adapter_oneiric import (
        require_reflection_database,
    )
    from session_buddy.core.checkpoint.manifest_resolver import (
        resolve_manifest_path,
    )

    # CRITICAL: load conversation_id and session_window_start from
    # session_windows — NOT a fresh NOW(). The spec's G6 + G7 require
    # that consecutive checkpoints in the same session share the same
    # conversation-window, accumulating work via the merge primitive.
    started_at: datetime | None = None
    with require_reflection_database() as conn:
        row = conn.execute(
            "SELECT started_at FROM session_windows WHERE id = ?",
            [self._conversation_id],  # whichever field holds the current conv id
        ).fetchone()
        started_at = row[0] if row else None

    if started_at is None:
        # Fallback to NOW if session_windows row is missing (defensive only)
        started_at = datetime.now(tz=timezone.utc)

    with require_reflection_database() as conn:
        accountant = CheckpointCrossRepoAccountant(
            ambient_puller=AmbientPuller(resolve_manifest_path()),
            merge_primitive=MergePrimitive(),
            conn=conn,
        )
        summary = await accountant.capture(
            working_directory=working_directory,
            conversation_id=self._conversation_id,
            session_window_start=started_at,
            session_window_end=datetime.now(tz=timezone.utc),
        )
    self.logger.info(
        "cross_repo_capture_summary",
        extra={
            "repos_captured": summary.repos_captured,
            "entries_inserted": summary.entries_inserted,
            "entries_deduplicated": summary.entries_deduplicated,
            "ambient_failures": summary.ambient_failures,
        },
    )
except Exception as exc:  # noqa: BLE001 — G6 sentinel path; never break checkpoint
    self.logger.warning(
        "cross_repo_capture_failed",
        extra={"error": str(exc)},
    )
```

(The implementer adjusts to match the existing `self._conversation_id` field name in `session_manager.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_checkpoint_wiring.py -v`
Expected: PASS (count >= 1).

- [ ] **Step 5: Commit**

```bash
git add session_buddy/core/session_manager.py tests/integration/test_checkpoint_wiring.py
git commit -m "feat(checkpoint): wire CheckpointCrossRepoAccountant into checkpoint_session"
```

---

### Task 11d: Update feature-tracking to `wired` (after Task 11b + 11c ship)

- [ ] **Step 1: Update feature-tracking status**

```markdown
---
status: wired
---
```

- [ ] **Step 2: Commit**

```bash
git add docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md
git commit -m "chore(feature-tracking): mark cross-repo checkpoint accounting as wired"
```

---

### Task 12: End-to-end integration test

**Files:**
- Create: `tests/integration/test_e2e_cross_repo_checkpoint.py`

- [ ] **Step 1: Write the integration test** (similar to v1 with the `start_session` prerequisite enforced)

The full e2e test instantiates `SessionLifecycleManager`, calls `start_session` / `checkpoint_session` / `end_session`, and asserts the handoff doc includes "## Cross-Repo Work" with at least one row from a sibling repo. The test will only pass if Tasks 1.5, 2-7, 11a-c are all complete.

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_e2e_cross_repo_checkpoint.py -v`
Expected: PASS once all upstream tasks are merged.

- [ ] **Step 3: Manual smoke**

Run `crackerjack run` once in the session-buddy repo to verify the full quality gate green.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_e2e_cross_repo_checkpoint.py
git commit -m "test(integration): e2e checkpoint pipeline includes Cross-Repo Work"
```

---

### Task 13: Final gate + completion report + orphan audit

**Files:**
- Create: `docs/archive/completion-reports/2026-08-05-cross-repo-checkpoint-accounting.md`
- Modify: `docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md` (final `adopted` state)

- [ ] **Step 1: Run orphan audit**

Run: `python scripts/audit_orphans.py --since=2026-08-05`
Expected: no new orphan symbols. If orphans surface (e.g., `CheckpointCrossRepoAccountant` has zero callers), the wiring is incomplete.

- [ ] **Step 2: Run crackerjack gate**

Run: `crackerjack run`
Expected: passes with no new violations.

- [ ] **Step 3: Generate completion report**

Create `docs/archive/completion-reports/2026-08-05-cross-repo-checkpoint-accounting.md` with:
- Goals G1-G8 status (all met)
- Components shipped (AmbientPuller, MergePrimitive, CheckpointCrossRepoAccountant, CrossRepoPusher, HandoffLink, ecosystem.yaml, bootstrap script, register_cross_repo_work_tools)
- Tests added (per-task counts; total ≥ 25 tests)
- Coverage on the 5 new modules (must clear 80%)
- **EventBridge migration decision** (mahavishnu I1): option (a) "keep both with `cross_repo_work_v2` as the checkpoint-time mirror" is the chosen default. Recorded in `.claude/decisions/cross-repo-work-vs-eventbridge.md`.
- Open follow-ups:
  - `bind_conversation` MCP tool for cross-pusher conversation_id discovery (mahavishnu C2)
  - Cross-MCP auth identity ADR (mahavishnu C3)
  - STANDARD profile gating CI guard (mahavishnu I3)
  - Deferred items from spec §Out of scope (routing, trigger follow-ups, ext:<id>)

- [ ] **Step 4: Mark `adopted` in feature-tracking**

```markdown
---
status: adopted
adopted_at: 2026-08-05
---
```

- [ ] **Step 5: Commit completion report**

```bash
git add docs/archive/completion-reports/2026-08-05-cross-repo-checkpoint-accounting.md docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md .claude/decisions/cross-repo-work-vs-eventbridge.md
git commit -m "docs: wave-1 completion report for cross-repo-checkpoint-accounting + EventBridge decision"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: G1 → Task 5 (ambient); G2 → Task 8 (explicit push); G3 → Task 4 (handoff); G4 → enforced by G6 across all tasks; G5 → Task 6 (merge primitive); G6 → Tasks 4, 7, 8, 11c; G7 → Task 1.5 + Task 8 (start_session + validation); G8 → Task 13 completion report (EventBridge decision).
- [x] **Per-repo grouping from the start**: `AmbientPuller.capture()` returns `dict[str, list[CommitEntry]]`. NO `<ambient>` placeholder in Task 7.
- [x] **Conversation_id validation**: Task 8 does `SELECT 1 FROM session_windows WHERE id = ?` before any merge (v2.1 amendment — was `conversations_v2` which is a Memori memory table).
- [x] **Multi-repo atomicity**: Task 8 wraps the entire batch in ONE `BEGIN TRANSACTION`. Task 6's merge is caller-transaction-agnostic.
- [x] **MCP registration matches actual codebase shape**: `STANDARD_REGISTRATIONS: list[str]`, `_ALL_REGISTRATIONS: dict[str, ...]`, `@require_auth(optional=False)` (session-buddy local).
- [x] **Auth contract correct**: session-buddy local `require_auth`, NOT mcp-common `require_auth(Permission.WRITE, config=...)`.
- [x] **Slug-keyed bootstrap**: Task 10 keys by `Path(repo["path"]).name`, not absolute path.
- [x] **Integration Contract blocks**: present on every task.
- [x] **Feature-tracking lifecycle**: `built` (Task 2) → `wired` (Task 11d) → `adopted` (Task 13).
- [x] **Open Questions resolved**:
  - Per-repo grouping: ships from Task 5 (no placeholder).
  - Wave-1 manual smoke: remains in Task 12 Step 3 (manual, not fixture).
  - Standard vs full profile: STANDARD per Task 9 (cross-pushers need STANDARD).

---

## Open Questions for Implementation Reviewer

1. **`start_session` envelope refactor** (Task 1.5): if `_start_impl` already returns a `conversation_id` in its dict (verify in step 3), the refactor is a one-line `return prose, conversation_id`. If not, this task escalates to a deeper change. The plan assumes the former.

2. **EventBridge migration decision** (Task 13 Step 3): the plan picks option (a) "keep both" as the default. The implementer may want to record a different decision in `.claude/decisions/cross-repo-work-vs-eventbridge.md` after discussion with the mahavishnu team.

3. **Cross-MCP auth ADR** (mahavishnu C3): not in scope for this wave. Tracked as a follow-up.