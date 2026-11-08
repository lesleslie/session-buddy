---
status: active
role: implementation
date: 2026-11-07
last_reviewed: 2026-11-07
superseded_by: null
blocks_on: []
topic: memory-architecture
---

# Task Metadata Single-Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse Session-Buddy's task metadata into the reflection store
(`reflections_v2.metadata`) so a task's identity and its payload can never
diverge, and make any residual divergence loud instead of silent.

**Architecture:** Tasks are reflections. The reflection store already has a
nullable `metadata JSON` column that the adapter never writes; task metadata
instead lives in a SQLModel SQLite sidecar (`tasks_metadata.sqlite`) keyed by
`reflection_id`. The plan first makes the split observable (a task whose
sidecar row resolves but whose reflection row is invisible must answer
`reflection_unreadable`, never `not_found`), then makes the reflection store
authoritative (dual-write, read-from-reflection, backfill), and only then
retires the sidecar.

**Tech Stack:** Python 3.14, DuckDB (`reflections_v2`), SQLModel/SQLAlchemy
(SQLite sidecar — to be retired), Pydantic v2, FastMCP, pytest.

**Spec:** `~/Projects/mahavishnu/docs/specs/.archive/2026-09-29-task-system-design.md`
§Data Model / §Data Flow path 1. That spec specifies ONE write:
`store_reflection(content, metadata={kind=task, owner=..., ...}, tags=[...])`.
The current v1.1 spec (`~/Projects/mahavishnu/docs/specs/2026-10-02-bodai-task-system-v1.1.md`)
treats the sidecar as pre-existing fact and does not revisit the topology.

## Why this exists

The split was scaffolding, not a decision. Commit `0f90abd4` ("T4 fix round 2
— SQLModel migration for task metadata persistence", 2026-09-29) introduced
the sidecar because the adapter's `store_reflection` did not accept
`metadata=` and SQLAlchemy has no in-tree DuckDB dialect. The module
docstring states the deferral — *"broader SQLModel adoption is a separate
decision"* — and `memory_tools.py:146` states it again — *"the existing
reflection adapter's `store_reflection` signature is intentionally out of
scope for this fix"*. No ADR, no `docs/decisions/` entry, no tracking issue
recorded that deferral.

It cost real data on 2026-11-07. Two tasks created at 10:18 and updated at
11:06 became invisible to `tasks_get` / `tasks_list` / `tasks_search`
between 11:06 and 11:15 while their rows stayed on disk in BOTH stores:

```
tasks_get → _find_reflection_id_by_task_id (SQLite sidecar)  → SUCCEEDS
          → _read_reflection(id)   (live DuckDB)             → returns None
          → "not_found"
```

`tasks_list` hit the same `None` and took its *"orphan sidecar row — skip
silently"* branch. The trigger was this environment's recurring DuckDB WAL
poison (*"Operation requires a flat or constant vector but a non-flat/non-
constant vector was encountered"*): the checkpointed main file was written
at 10:16, before the 10:18 creates, so those rows lived only in the WAL and
the live connection lost sight of them. A fresh `duckdb` connection to the
same file+WAL sees all 7 task rows; the live server saw 5.

## Global Constraints

- **Never break the happy path.** `tasks_create` → `tasks_get` →
  `tasks_update` → `tasks_complete` must keep working identically for every
  caller. Phase 1 changes only the *failure* envelope.
- **`not_found` means "no such task".** It must never be returned for a task
  whose sidecar row resolves. A task that exists but is unreadable answers
  `reflection_unreadable`.
- **Server-set fields stay server-set.** `owner`, `created_by`, `completed_by`
  and `workflow_id` are never sourced from caller-supplied `metadata`.
  Caller-supplied metadata continues to live under the nested `metadata` key.
- **The `task` tag stays the durable discriminator.** `is_task_reflection`
  already documents it as surviving a sidecar wipe. Do not remove it.
- **DuckDB is the durable store.** The sidecar is a transitional artefact
  until Task 7.
- **`reflections_v2.metadata` is nullable `JSON`** (`schema_v2.py:117` and
  the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS metadata JSON` at
  `schema_v2.py:193`). Writing `NULL` for reflections with no metadata must
  stay valid — most reflections in the fleet have no metadata at all.
- **No new MCP server, no new dependency.** `duckdb-engine` is NOT added;
  the reflection store is already DuckDB and already has the column.
- **Line length 88** (`ruff`); `from __future__ import annotations` first
  non-comment line; `X | None` over `Optional[X]`; no `print()` in library
  code — use `logger`.
- **Type checker is `ty`,** not mypy. `ty: ignore[...]` is line-scoped and
  must sit on the diagnostic's line.

## Review Focus

Five input classes or failure modes the plan implies that no happy-path test
exercises. Each gets a test in the task that owns the code.

1. **A sidecar row whose reflection is invisible** — the task exists but
   cannot be read. Expected: `reflection_unreadable`, never `not_found`,
   and never a silent skip.
2. **A reflection with no metadata at all** (every non-task reflection in the
   fleet). Expected: the read path falls back to the sidecar / returns
   `None` cleanly; writing `NULL` metadata must not corrupt the row.
3. **A sidecar row whose reflection was deleted** (the orphan direction).
   Expected: the row is reported as unreadable/missing, and the reconciliation
   helper lists it — never resurrected as a phantom task.
4. **A caller-supplied `metadata` blob containing a non-JSON-serialisable
   value.** Expected: `store_reflection` rejects it with a clear error
   rather than writing a malformed JSON document.
5. **Two stores disagreeing about the same task** (sidecar has newer
   `status` than the reflection row, or vice versa). Expected: the
   documented precedence applies — reflection store wins, sidecar is the
   fallback — and the reconciliation helper can report the drift.

## File Structure

| File | Responsibility |
|---|---|
| `session_buddy/mcp/tools/tasks_tools.py` | Task tool bodies. Phase 1 error envelopes; metadata read precedence; dual-write on update. |
| `session_buddy/mcp/tools/tasks_reconcile.py` | **NEW.** Read-only enumeration of sidecar rows whose reflection is invisible, and of drift between the two stores. |
| `session_buddy/mcp/tools/tasks_migrate.py` | **NEW.** Backfill: copy sidecar metadata into `reflections_v2.metadata`. Runnable as `python -m session_buddy.mcp.tools.tasks_migrate`. |
| `session_buddy/mcp/tools/tasks_storage.py` | The sidecar. Retired in Task 7. |
| `session_buddy/adapters/reflection_adapter_oneiric.py` | `store_reflection` / `update_reflection` / `get_reflection_by_id` gain `metadata` support. |
| `session_buddy/mcp/tools/memory/memory_tools.py` | `_store_reflection_impl` passes `metadata` down to the adapter (dual-write). |
| `session_buddy/mcp/tools/tasks_models.py` | `TaskListResult.unreadable_count`. |
| `session_buddy/server_optimized.py` | Sidecar engine wiring. Removed in Task 7. |

---

### Task 1: `tasks_get` answers `reflection_unreadable`, not `not_found`

**Files:**
- Modify: `session_buddy/mcp/tools/tasks_tools.py` (`tasks_get`, ~line 1056)
- Test: `tests/unit/test_tasks_tools.py`

**Interfaces:**
- Consumes: existing `_find_reflection_id_by_task_id(engine, task_id) -> str | None`
  and `_read_reflection(reflection_id) -> dict | None`.
- Produces: error envelope `{"status": "error", "error_code":
  "reflection_unreadable", "message": str, "details": {"task_id": str,
  "reflection_id": str}}`.

- [x] **Step 1: Write the failing test**

Add to `tests/unit/test_tasks_tools.py`:

```python
async def test_tasks_get_reports_unreadable_reflection_not_not_found():
    """Sidecar resolves the task but the reflection row is invisible."""
    # Patch _find_reflection_id_by_task_id to return a reflection id and
    # _read_reflection to return None.
    result = await tasks_get(ctx, "t-" + "0" * 32)
    assert result["error_code"] == "reflection_unreadable"
    assert result["status"] == "error"
    assert result["details"]["reflection_id"] == "abc123"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tasks_tools.py -k unreadable -v`
Expected: FAIL — current code returns `error_code == "not_found"`.

- [x] **Step 3: Implement in `tasks_tools.py`**

In `tasks_get`, split the current single `not_found` return into two cases.
Keep `not_found` only for the case where the sidecar itself has no row
(`target is None`). When `target` is found but `_read_reflection(target)` is
`None`, return the `reflection_unreadable` envelope with `details` carrying
`task_id` and `reflection_id`. The `_build_task(...) is None` case keeps
`not_found` — that means the row exists but lacks required fields, which is
a different defect (and is covered by the `reflection_unreadable` detail
message rather than a bare not-found).

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tasks_tools.py -v`
Expected: PASS, including the pre-existing `not_found` tests for a genuinely
absent task.

- [x] **Step 5: Commit**

```bash
git add session_buddy/mcp/tools/tasks_tools.py tests/unit/test_tasks_tools.py
git commit -m "fix(tasks): report reflection_unreadable instead of not_found"
```

---

### Task 2: `tasks_list` surfaces unreadable rows

**Files:**
- Modify: `session_buddy/mcp/tools/tasks_models.py` (`TaskListResult`)
- Modify: `session_buddy/mcp/tools/tasks_tools.py` (`tasks_list`)
- Test: `tests/unit/test_tasks_tools.py`

**Interfaces:**
- Consumes: `TaskListResult` model, `tasks_list` candidate loop.
- Produces: `TaskListResult.unreadable_count: int = 0` (new field, default
  keeps every existing construction site valid — the model is
  `extra="forbid"`, so the field must be added to the model, not passed in).

- [x] **Step 1: Write the failing test**

```python
async def test_tasks_list_reports_unreadable_reflections():
    """One candidate's reflection is invisible: count it, do not drop it silently."""
    # Arrange two sidecar task rows; _read_reflection returns None for one.
    result = await tasks_list(ctx, k=20)
    assert result.unreadable_count == 1
    assert result.total == 1  # only the readable one is a task item
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tasks_tools.py -k unreadable -v`
Expected: FAIL — `TaskListResult` has no `unreadable_count` attribute.

- [x] **Step 3: Implement**

Add `unreadable_count: int = 0` to `TaskListResult` with a docstring line
saying it counts sidecar task rows whose backing reflection could not be
read (a durability fault, not a filter). In `tasks_list`, replace the
`continue  # orphan sidecar row — skip silently` branch with: increment a
local counter, append the reflection id to a list, `continue`. After the
loop, `logger.warning("tasks_list: %d task reflections unreadable: %s",
counter, ids[:10])` and set `unreadable_count=counter` on the result.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tasks_tools.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add session_buddy/mcp/tools/tasks_models.py session_buddy/mcp/tools/tasks_tools.py tests/unit/test_tasks_tools.py
git commit -m "feat(tasks): surface unreadable_count in tasks_list"
```

---

### Task 3: Reconciliation helper

**Files:**
- Create: `session_buddy/mcp/tools/tasks_reconcile.py`
- Test: `tests/unit/test_tasks_reconcile.py`

**Interfaces:**
- Consumes: `tasks_storage.get_engine()`,
  `tasks_storage.find_tasks_by_metadata(engine, {"kind": "task"})`,
  `tasks_tools._read_reflection`.
- Produces:
  - `async def find_unreadable_task_reflections(engine: Engine) -> list[str]`
    — reflection ids whose sidecar row exists but whose reflection row is
    not readable, sorted.

  (`find_task_metadata_drift` was moved to Task 5 — see the ledger ruling:
  it compares against the reflection row's `metadata` column, which the
  adapter does not expose until Task 4 lands.)

- [x] **Step 1: Write the failing test**

`tests/unit/test_tasks_reconcile.py`:

```python
async def test_find_unreadable_task_reflections_lists_sidecar_only_rows():
    # Two sidecar task rows; one reflection is readable, one is not.
    result = await find_unreadable_task_reflections(engine)
    assert result == ["unreadable_reflection_id"]


async def test_find_unreadable_task_reflections_does_not_resurrect_deleted_reflections():
    # The sidecar row's reflection was DELETED. It must be reported as
    # unreadable, never re-materialised as a phantom task.
    result = await find_unreadable_task_reflections(engine)
    assert result == ["deleted_reflection_id"]
    # tasks_get for its task_id must not answer with a Task.
    got = await tasks_get(ctx, task_id_of_deleted)
    assert got["error_code"] != "not_found"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tasks_reconcile.py -v`
Expected: FAIL — module does not exist.

- [x] **Step 3: Implement**

New module. `find_unreadable_task_reflections` iterates the sidecar task
rows, calls `_read_reflection` for each, and collects the ids whose read
returned `None`. It takes the engine as a parameter so tests can inject an
in-memory one — do not call `tasks_storage.get_engine()` inside it.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tasks_reconcile.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add session_buddy/mcp/tools/tasks_reconcile.py tests/unit/test_tasks_reconcile.py
git commit -m "feat(tasks): add store-divergence reconciliation helpers"
```

---

### Task 4: The reflection store can carry metadata

**Files:**
- Modify: `session_buddy/adapters/reflection_adapter_oneiric.py`
  (`store_reflection` ~line 2230, both INSERT statements at ~2333 and
  ~2364, `update_reflection` ~line 2836, `get_reflection_by_id` ~line 2801)
- Test: `tests/unit/test_reflection_metadata_column.py` (new)

**Interfaces:**
- Consumes: the existing `reflections_v2.metadata JSON` column.
- Produces:
  - `async def store_reflection(self, content: str, tags: list[str] | None = None,
    deduplicate: bool = False, dedup_threshold: float = 0.85,
    project: str | None = None, *, metadata: dict[str, t.Any] | None = None,
    source_session_id: str | None = None,
    source_artifact_uri: str | None = None) -> str`
    — new keyword-only `metadata`; when `None`, the column is written as
    `NULL` (no behaviour change for existing callers).
  - `async def update_reflection(self, reflection_id: str, *, content: str | None = None,
    tags: list[str] | None = None, metadata: dict[str, t.Any] | None = None) -> bool`
    — new keyword-only `metadata`; when provided, replaces the column.
  - `async def get_reflection_by_id(self, reflection_id: str) -> dict[str, t.Any] | None`
    — now also returns a `"metadata"` key holding the parsed dict, or `{}`
    when the column is NULL.

- [x] **Step 1: Write the failing test**

`tests/unit/test_reflection_metadata_column.py`:

```python
async def test_store_reflection_round_trips_metadata(reflection_db):
    rid = await reflection_db.store_reflection(
        content="hello", tags=["task"], metadata={"kind": "task", "owner": "user:les"}
    )
    row = await reflection_db.get_reflection_by_id(rid)
    assert row["metadata"] == {"kind": "task", "owner": "user:les"}


async def test_store_reflection_without_metadata_writes_null(reflection_db):
    rid = await reflection_db.store_reflection(content="plain", tags=["note"])
    row = await reflection_db.get_reflection_by_id(rid)
    assert row["metadata"] == {}


async def test_update_reflection_replaces_metadata(reflection_db):
    rid = await reflection_db.store_reflection(content="x", metadata={"a": 1})
    assert await reflection_db.update_reflection(rid, metadata={"b": 2}) is True
    row = await reflection_db.get_reflection_by_id(rid)
    assert row["metadata"] == {"b": 2}


async def test_store_reflection_rejects_unserialisable_metadata(reflection_db):
    with pytest.raises((TypeError, ValueError)):
        await reflection_db.store_reflection(content="x", metadata={"bad": object()})
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_reflection_metadata_column.py -v`
Expected: FAIL — `store_reflection` raises `TypeError` for the unexpected
`metadata` keyword.

- [x] **Step 3: Implement**

In `store_reflection`, add the keyword-only `metadata` parameter. Add
`metadata` to the column list of **both** INSERT statements (the one at
~2333 and the one at ~2364 — the second is a different code path and
missing it is the classic half-done change). Serialise with
`json.dumps(metadata)` and let a `TypeError` propagate for unserialisable
values (that is what the fourth test pins). Insert as `CAST(? AS JSON)` so
DuckDB stores a JSON document rather than a VARCHAR. When `metadata is
None`, bind `None` so the column stays NULL.

In `update_reflection`, add the keyword-only `metadata` parameter and, when
it is not `None`, append `metadata = CAST(? AS JSON)` to the SET clause.
When it is `None`, leave the column untouched (the current behaviour of not
touching it must be preserved — `update_reflection` is called by paths that
do not know about metadata).

In `get_reflection_by_id`, add `metadata` to the SELECT and return
`json.loads(row)` when the column is non-null and non-empty, else `{}`.
Note the existing code returns `created_at`/`updated_at` as ISO strings;
keep that shape and add `"metadata"` as a parsed dict.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_reflection_metadata_column.py -v`
Expected: PASS.

- [x] **Step 5: Run the adapter's existing tests to prove no regression**

Run: `pytest tests/unit -k "reflection and not metadata" -x -q`
Expected: PASS — `store_reflection`'s new default-None behaviour must not
change any existing caller.

- [x] **Step 6: Commit**

```bash
git add session_buddy/adapters/reflection_adapter_oneiric.py tests/unit/test_reflection_metadata_column.py
git commit -m "feat(reflections): store and read the metadata column"
```

---

### Task 5: Task metadata flows through the reflection store

**Files:**
- Modify: `session_buddy/mcp/tools/memory/memory_tools.py`
  (`_store_reflection_impl`, ~line 157)
- Modify: `session_buddy/mcp/tools/tasks_tools.py`
  (`tasks_get`, `tasks_list`, `_persist_task_update`, `tasks_complete`,
  `tasks_link_workflow`)
- Test: `tests/unit/test_tasks_tools.py`, `tests/unit/test_memory_tools.py`

**Interfaces:**
- Consumes: `store_reflection(..., metadata=...)` and
  `update_reflection(..., metadata=...)` from Task 4; the `"metadata"` key on
  the dict returned by `_read_reflection`.
- Produces: `def _read_task_metadata(reflection: dict[str, Any] | None,
  sidecar_meta: dict[str, Any] | None) -> dict[str, Any]` in `tasks_tools.py`
  — **merges** the two documents key by key, the reflection's `metadata`
  winning per key, with ONE exception: the write-once workflow-link keys
  (`workflow_id`, `workflow_linked_at`, `workflow_linked_by`), where the
  sidecar wins whenever it holds a link. The merge (rather than a wholesale
  preference) is what keeps a partial reflection document from dropping
  fields the sidecar still has; the link exception is what stops a stale
  `workflow_id: None` in the reflection document from shadowing a live
  binding. *(Amended 2026-11-07 after the whole-branch review: the plan
  first specified "the reflection's `metadata` dict when it is a non-empty
  dict, otherwise the sidecar blob", and the implementation merged.)*
  Plus `async def find_task_metadata_drift(engine: Engine) -> list[dict[str, Any]]`
  in `session_buddy/mcp/tools/tasks_reconcile.py` — one entry per task whose
  sidecar metadata and the reflection row's `metadata` disagree, each
  `{"reflection_id", "task_id", "fields": [...]}`. `fields` lists the
  differing top-level keys. (Moved here from Task 3: it needs the
  reflection's `metadata` column, which Task 4 exposes.)

- [x] **Step 1: Write the failing test**

In `tests/unit/test_tasks_tools.py`:

```python
async def test_task_metadata_is_read_from_the_reflection_row():
    # The sidecar has no row; the reflection row carries metadata.
    result = await tasks_get(ctx, task_id)
    assert result.owner == "user:les"
    assert result.metadata == {"branch": "feature/x"}
```

In `tests/unit/test_memory_tools.py`:

```python
async def test_store_reflection_impl_passes_metadata_to_the_adapter():
    # The adapter's store_reflection receives metadata=...
    assert captured["metadata"] == {"kind": "task"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tasks_tools.py -k "read_from_the_reflection" -v`
Expected: FAIL — the sidecar is still the only metadata source.

- [x] **Step 3: Implement**

In `memory_tools._store_reflection_impl`, pass `metadata=metadata` to
`db.store_reflection(...)`. **Keep** the existing
`tasks_storage.persist_task_metadata(...)` call — this phase is dual-write,
so every existing reader keeps working while the reflection store becomes
authoritative. Add a comment stating the sidecar write is transitional and
is removed by Task 7.

In `tasks_tools.py`, add `_read_task_metadata` and use it at every place
that currently calls `tasks_storage.read_task_metadata` for the purpose of
building a `Task`: `tasks_get`, `tasks_list`, and the `current` read inside
`_persist_task_update`.

In `_persist_task_update`, after computing `new_meta`, write it to BOTH
stores: `await _update_reflection(reflection_id=..., content=..., tags=...,
metadata=new_meta)` (extend `_update_reflection` to accept and forward
`metadata`) and keep `tasks_storage.persist_task_metadata(...)`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tasks_tools.py tests/unit/test_memory_tools.py -v`
Expected: PASS.

- [x] **Step 5: Run the whole task test suite**

Run: `pytest tests/unit/test_tasks_storage.py tests/unit/test_tasks_persistence.py tests/unit/test_tasks_link_workflow.py tests/unit/test_tasks_legacy.py tests/unit/mcp/test_lifespan_task_sidecar.py -v`
Expected: PASS — these pin the sidecar behaviour and must survive
dual-write unchanged.

- [x] **Step 6: Commit**

```bash
git add session_buddy/mcp/tools/memory/memory_tools.py session_buddy/mcp/tools/tasks_tools.py tests/unit/test_tasks_tools.py tests/unit/test_memory_tools.py
git commit -m "feat(tasks): read and write task metadata through the reflection store"
```

---

### Task 6: Backfill the reflection store

**Files:**
- Create: `session_buddy/mcp/tools/tasks_migrate.py`
- Test: `tests/unit/test_tasks_migrate.py`

**Interfaces:**
- Consumes: the sidecar blob for each task row; the adapter's
  `update_reflection(..., metadata=...)`.
- Produces:
  - `async def backfill_task_metadata(engine: Engine, db: Any) -> dict[str, int]`
    returning `{"migrated": int, "skipped": int, "missing_reflection": int}`
    — `migrated` = rows whose reflection metadata was written,
    `skipped` = rows whose reflection already had metadata,
    `missing_reflection` = sidecar rows whose reflection does not exist.
  - `async def main() -> None` for `python -m` invocation, printing a
    JSON summary to stdout (this is a CLI entry point, so `print()` is
    allowed here).

- [x] **Step 1: Write the failing test**

```python
async def test_backfill_copies_sidecar_metadata_into_the_reflection_row():
    # One sidecar row; its reflection has no metadata yet.
    result = await backfill_task_metadata(engine, db)
    assert result["migrated"] == 1
    row = await db.get_reflection_by_id(reflection_id)
    assert row["metadata"]["kind"] == "task"


async def test_backfill_does_not_overwrite_existing_metadata(engine, db):
    # Reflection already has metadata -> skipped, original preserved.
    result = await backfill_task_metadata(engine, db)
    assert result["skipped"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tasks_migrate.py -v`
Expected: FAIL — module does not exist.

- [x] **Step 3: Implement**

New module. For each sidecar task row, read the reflection; if it is `None`,
count `missing_reflection` and continue. If the reflection's `metadata` is
already a non-empty dict, count `skipped` and continue. Otherwise write the
sidecar blob via `db.update_reflection(reflection_id, metadata=blob)` and
count `migrated`. Never delete a sidecar row from this function — the
sidecar stays until Task 7.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tasks_migrate.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add session_buddy/mcp/tools/tasks_migrate.py tests/unit/test_tasks_migrate.py
git commit -m "feat(tasks): backfill task metadata into the reflection store"
```

---

### Task 7: Retire the sidecar — DEFERRED (operator step, 2026-11-07)

> **Why this task is deferred, not done.** Retiring the sidecar requires
> the live backfill to have run first — until then the reflection store
> has no metadata for the fleet's existing rows, and a
> reflection-store-only reader would see zero tasks. The running
> session-buddy server holds an exclusive DuckDB lock, so the backfill
> cannot run against the live database without stopping the service.
> Stopping a live service and writing to its database is an operator
> action, not a code action.
>
> **What WAS done instead.** The backfill was verified end-to-end against
> a COPY of the live stores through the real adapter:
> `{"migrated": 9, "skipped": 0, "missing_reflection": 0}` — all nine
> task rows, including the two that went invisible on 2026-11-07.
>
> **The operator sequence** (also in
> `docs/feature-tracking/2026-11-07-task-metadata-single-store.md`):
> stop the service → `python -m session_buddy.mcp.tools.tasks_migrate` →
> back up `tasks_metadata.sqlite` → delete the sidecar module and
> rewrite the nine test files → restart and confirm `tasks_list` returns
> the same tasks.
>
> The steps below are unchanged and ready to run.

**Files:**
- Delete: `session_buddy/mcp/tools/tasks_storage.py`
- Modify: `session_buddy/server_optimized.py` (remove the `set_engine` wiring)
- Modify: `session_buddy/settings.py` (remove the `task_metadata` settings block)
- Modify: `session_buddy/mcp/tools/tasks_tools.py`,
  `session_buddy/mcp/tools/memory/memory_tools.py`,
  `session_buddy/mcp/tools/advanced/fingerprint_tools.py` (drop sidecar calls)
- Modify: the nine test files that reference `tasks_storage`:
  `tests/unit/test_tasks_storage.py` (delete),
  `tests/unit/test_tasks_tools.py`,
  `tests/unit/test_tasks_link_workflow.py`,
  `tests/unit/test_tasks_persistence.py`,
  `tests/unit/test_memory_tools.py`,
  `tests/unit/test_reflection_delete_tool.py`,
  `tests/unit/mcp/test_lifespan_task_sidecar.py` (delete),
  `tests/integration/test_tasks_end_to_end.py`,
  `tests/integration/test_tasks_authz.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: `tasks_storage.py` deleted; no `tasks_metadata.sqlite` on disk;
  task metadata lives only in `reflections_v2.metadata`.

- [ ] **Step 1: Confirm the gate before starting**

Run: `pytest tests/unit tests/integration -k "task" -q`
Expected: PASS on the Task-6 tree. **If any task test fails, stop and fix
Phase 2 before touching Task 7.** Task 7 is the only step that removes a
working fallback; skipping the gate converts a safe change into a lossy one.

- [ ] **Step 2: Replace the sidecar reads with the reflection-store reads**

In `tasks_tools.py`, replace the existing
`_find_reflection_id_by_task_id(engine: Engine, task_id: str) -> str | None`
with a new
`async def _find_reflection_id_by_task_id(db: Any, task_id: str) -> str | None`
that resolves `task_id -> reflection_id` by querying the reflection store
instead of the sidecar. The `reflections_v2.metadata` JSON blob carries
`task_id`, so the lookup is a SQL scan over
`json_extract_string(metadata, '$.task_id') = ?`. The visibility filter and
the caller-identity rules are unchanged.

Callers of the old helper (`tasks_get`, and anything else that resolves a
task id) must be updated to the new signature in the same commit — a
half-migrated helper is the failure mode this task is fixing.

- [ ] **Step 3: Delete the sidecar module and its wiring**

Delete `session_buddy/mcp/tools/tasks_storage.py`. Remove the
`tasks_storage.set_engine(...)` block from `server_optimized.py` and the
`task_metadata` settings block from `settings.py`. Remove the
`persist_task_metadata` call from `memory_tools._store_reflection_impl` and
the `delete_task_metadata` call from
`memory_tools._delete_reflection_operation`.

- [ ] **Step 4: Update the affected tests**

Replace sidecar fixtures with reflection-row fixtures. Delete
`tests/unit/test_tasks_storage.py` and `tests/unit/mcp/test_lifespan_task_sidecar.py`.
`tests/unit/test_reflection_delete_tool.py` keeps its sidecar-cleanup test
only in the form "deleting a reflection removes the task metadata that was
stored on it" — assert via the reflection row, not the sidecar.

- [ ] **Step 5: Run the full task + reflection test suite**

Run: `pytest tests/unit tests/integration -k "task or reflection" -q`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `pytest -x -q`
Expected: PASS, or only the pre-existing failures documented on `main`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(tasks): retire the task metadata sidecar"
```

---

## Integration Contract

| Field | Value |
|---|---|
| **Triggered from** | `mcp__session-buddy__tasks_get` / `tasks_list` / `tasks_update` / `tasks_complete` / `tasks_link_workflow` / `tasks_search` / `tasks_history` / `store_reflection` / `delete_reflection`; `python -m session_buddy.mcp.tools.tasks_migrate` |
| **Returns to / updates** | `reflections_v2.metadata` becomes the single source of truth for task metadata; `TaskListResult` gains `unreadable_count`; `tasks_get` gains the `reflection_unreadable` error code |
| **Demonstrable by** | `pytest tests/unit/test_tasks_tools.py tests/unit/test_tasks_reconcile.py tests/unit/test_reflection_metadata_column.py tests/unit/test_tasks_migrate.py -v` — all PASS; plus `python -m session_buddy.mcp.tools.tasks_migrate` on a copy of the live DB reporting `scanned == N, migrated == N, skipped == 0, missing_reflection == 0` (`scanned` was added 2026-11-07 so a truncated run cannot look like a complete one) |
| **Rollback signal** | Any task test fails after Task 5 (dual-write) → revert to Task 4 and keep the sidecar. After Task 7 the sidecar is gone, so rollback is `git revert` of the Task 7 commit **plus** re-running the backfill from a pre-Task-7 backup of `tasks_metadata.sqlite` — therefore **back up `tasks_metadata.sqlite` before Task 7** |
| **Observability added** | `logger.warning("tasks_list: %d task reflections unreadable: %s", ...)`; `logger.warning("tasks_search: task reflection %r is unreadable ...")`; `reflection_unreadable` error envelope; `unreadable_count` on `TaskListResult`; `tasks_reconcile` helpers returning the divergence set; `tasks_migrate` JSON summary (`scanned` / `migrated` / `skipped` / `missing_reflection`) |

## Rollback

- Tasks 1–4 are additive and independently revertible.
- Task 5 is dual-write, and the READ side is a merge (reflection wins per
  key, sidecar wins for the write-once workflow-link keys) — not the
  wholesale reflection preference this plan originally specified. Reverting
  Task 5 therefore does NOT return to sidecar-authoritative reads: it
  returns to sidecar-only reads with the reflection column ignored, which
  is the pre-Task-5 behaviour. The merge and the link exception are
  recorded in the SDD ledger; reverting them alone re-opens the two
  defects the whole-branch review found (a link invisible to every reader,
  and a link destroyed by the next update).
- Task 6 is a pure backfill: reverting it leaves the reflection store with
  extra metadata that nothing reads.
- Task 7 is the only destructive step. **Before it**, copy
  `~/.local/share/session-buddy/tasks_metadata.sqlite` to a dated backup.

## Out of Scope

- The `bodai_events` enqueue failure (*"enqueue task.updated failed: union[str,
  bytes, int, float] object expected; got dict"*) — `TaskUpdatedPayload.diff`
  is `dict[str, tuple[Any, Any]]` and the Redis `XADD` adapter only accepts
  scalar field values. Real bug, separate defect, separate task.
- The DuckDB WAL poison itself (the underlying trigger for the 2026-11-07
  incident) — that is the "flat or constant vector" checkpoint failure.
  Task 1 and Task 2 make its *consequences* loud; they do not fix the
  poison.
- The `pool_route_execute` task-shape mismatch, which blocks stage-2
  ensemble review in mahavishnu.
