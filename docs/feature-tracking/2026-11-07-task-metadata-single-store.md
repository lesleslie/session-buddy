---
feature: task-metadata-single-store
status: built
created: 2026-11-07
last_updated: 2026-11-07
adopted_at: null
state_history:
  - "2026-11-07: built (plan written and activated; implementation starting — Phase 1 harden, Phase 2 consolidate, Phase 3 retire)"
  - "2026-11-07: built (whole-branch review returned 'not safe to merge as-is'; 2 Critical + 5 Important findings fixed on the branch; the reconciler and the backfill are built but have NO production caller — M7)"
---

# TASK-METADATA-SINGLE-STORE: One Store for Task Metadata

## Problem

Task metadata lives in a SQLModel SQLite sidecar
(`~/.local/share/session-buddy/tasks_metadata.sqlite`) while task content
lives in DuckDB `reflections_v2`. Identity resolution and payload read
therefore cross a database boundary with no transaction, no referential
integrity, and no reconciliation.

The split was never an architectural decision. The design spec
(`mahavishnu/docs/specs/.archive/2026-09-29-task-system-design.md` §Data
Flow path 1) specifies a single write —
`store_reflection(content, metadata={kind=task, owner=..., ...}, tags=[...])`.
Commit `0f90abd4` ("T4 fix round 2 — SQLModel migration for task metadata
persistence", 2026-09-29) introduced the sidecar because the adapter's
`store_reflection` did not accept `metadata=` and SQLAlchemy has no in-tree
DuckDB dialect. `memory_tools.py:146` states the deferral explicitly: *"the
existing reflection adapter's `store_reflection` signature is intentionally
out of scope for this fix"*. No ADR, no `docs/decisions/` entry, and no
tracking issue recorded it — it exists only as a docstring sentence, which
is why it survived six weeks.

## Cost (proven 2026-11-07)

Two tasks created at 10:18 and updated at 11:06 became invisible to
`tasks_get` / `tasks_list` / `tasks_search` between 11:06 and 11:15 while
their rows stayed on disk in **both** stores.

```
tasks_get → _find_reflection_id_by_task_id (SQLite sidecar)  → SUCCEEDS
          → _read_reflection(id)   (live DuckDB)             → returns None
          → "not_found"
```

`tasks_list` hit the same `None` and took its *"orphan sidecar row — skip
silently"* branch. Trigger: this environment's recurring DuckDB WAL poison
(*"Operation requires a flat or constant vector but a non-flat/non-constant
vector was encountered"*). The checkpointed main file was written at 10:16,
before the 10:18 creates, so those rows lived only in the WAL and the live
connection lost sight of them. A fresh `duckdb` connection to the same
file+WAL sees all 7 task rows; the live server saw 5.

## Built

Plan: `docs/plans/2026-11-07-task-metadata-single-store.md` (status
`active`).

| Phase | Deliverable | State |
|---|---|---|
| 1 — Harden | `tasks_get` answers `reflection_unreadable` instead of `not_found`; `tasks_list` surfaces `unreadable_count`; `tasks_reconcile` enumerates divergence | **built** |
| 2 — Consolidate | adapter `store_reflection` / `update_reflection` / `get_reflection_by_id` support the existing `reflections_v2.metadata` column; dual-write; read-from-reflection with sidecar fallback; backfill tool | **built** |
| 3 — Retire | `tasks_storage.py` deleted; no `tasks_metadata.sqlite` on disk | **deferred** — needs the live backfill run, which needs the service stopped |

Phase 1 files: `session_buddy/mcp/tools/tasks_tools.py`,
`session_buddy/mcp/tools/tasks_models.py`,
`session_buddy/mcp/tools/tasks_reconcile.py`.

Phase 2 files: `session_buddy/adapters/reflection_adapter_oneiric.py`
(`store_reflection` / `update_reflection` / `get_reflection_by_id`),
`session_buddy/mcp/tools/memory/memory_tools.py` (forwards `metadata` to
the adapter), `session_buddy/mcp/tools/tasks_migrate.py` (backfill tool).

## Wired

**Phase 1 — wired.** `tasks_get` returns the `reflection_unreadable`
envelope when the sidecar resolves a task but the reflection row is
unreadable; `tasks_list` reports `unreadable_count` and logs a WARNING with
the affected ids; `tasks_reconcile.find_unreadable_task_reflections` and
`find_task_metadata_drift` enumerate the divergence.

The new error code is gated on a sidecar-derived ownership check
(`_sidecar_visible_to`) before it is returned — otherwise it would be an
existence oracle for a non-owner, which the spec §Authz Model forbids
(404 over 403).

**Phase 2 — wired.** Task metadata now flows through the reflection store:
`store_reflection(metadata=...)` writes `reflections_v2.metadata`,
`update_reflection(metadata=...)` replaces it, `get_reflection_by_id`
returns it, and the task tools read the reflection row's document first
with the sidecar as the transition fallback. Writes are dual (both stores)
until the sidecar is retired.

Verified against a **copy** of the live stores: the backfill migrated all
10 task rows (0 skipped, 0 missing), including the two rows that went
invisible on 2026-11-07.

**Not wired — the reconciler and the backfill have no production caller.**
`tasks_reconcile` and `tasks_migrate` are libraries, not MCP tools, not
scheduled, not startup checks; a grep over `session_buddy/` finds no
importer outside their own modules. The repo's Process Discipline
(`CLAUDE.md`: *"If the audit reports recently-added symbols with zero
callers, the feature is not done — either wire it or remove it"*) applies:
these two modules are **built, not wired**. Wiring them is a separate
decision (an MCP tool, a startup check, or a scheduled job) and is not
made here. The consequence is concrete and worth stating plainly: the
reconciler is the only instrument that would have detected the link loss
the whole-branch review found (see below) in production, and it never runs.

## Adopted

**Phase 2 — adopted for new writes; the fleet's existing rows are still
sidecar-only.** The live database has not been backfilled: the running
session-buddy server holds an exclusive DuckDB lock, so the backfill
cannot run against it without stopping the service. That is an
operator step, not a code step.

## Whole-branch review (2026-11-07)

A fresh-context review of the branch returned **"Not safe to merge
as-is"** and found two Critical and five Important defects, all in the
transition code. All seven are fixed on this branch:

| # | Finding | Fix |
|---|---|---|
| C1 | `tasks_link_workflow` wrote only to the sidecar, so the link was invisible to every reader and the next `tasks_update` destroyed it | the link now mirrors into the reflection document; the sidecar write stays the authority for link-once |
| C2 | `python -m session_buddy.mcp.tools.tasks_migrate` opened the in-memory sidecar, so the runbook's migration step migrated nothing | `main()` opens the configured sidecar path |
| I1 | the backfill and the reconcilers silently truncated at 1000 rows | `find_tasks_by_metadata(limit=None)`; the summary reports `scanned` |
| I2 | `tasks_search` dropped an unreadable task in silence | it logs a WARNING naming the reflection |
| I3 | `tasks_history` read the raw sidecar, so Phase 3 would empty every history | it reads the merged document |
| I4 | the link's history entries were dropped by the next `tasks_update` | the link appends to the merged history; the dual-write carries it forward |
| I5 | a stale explicit `None` in the reflection document could shadow a fresh sidecar value | the write-once workflow-link keys are the sidecar's; every other writer is dual-write |

The review also found two Review Focus input classes with no test (a
reflection row whose metadata column is NULL, and a metadata bag that
cannot be serialised). Both are now pinned.

## Why Phase 3 is deferred

Retiring the sidecar requires the live backfill to have run first — until
then, the reflection store has no metadata for the fleet's existing rows
and a reflection-store-only reader would see zero tasks. The sequence is:

1. Stop the session-buddy service (it holds an exclusive DuckDB lock).
2. `python -m session_buddy.mcp.tools.tasks_migrate` against the live
   stores; expect
   `{"scanned": N, "migrated": N, "skipped": 0, "missing_reflection": 0}`
   where N is the number of task rows in the sidecar (10 as of
   2026-11-07, verified against a copy of the live stores).
   **Treat `migrated == 0` against a non-empty sidecar as a failure, not
   as "nothing to do"** — that is exactly what the broken `main()` (C2)
   used to print, and it is the signature of a migration that ran against
   the wrong database.
3. Back up `~/.local/share/session-buddy/tasks_metadata.sqlite`.
4. Delete `session_buddy/mcp/tools/tasks_storage.py`, its wiring in
   `server_optimized.py` and `settings.py`, and rewrite the nine test
   files that reference it.
   **Task identity moves with it.** The task-id → reflection-id
   resolution lives entirely in the sidecar
   (`_find_reflection_id_by_task_id(engine, task_id)`); deleting the
   sidecar without re-pointing it breaks EVERY task lookup, not just the
   metadata read. Plan Task 7 Step 2 specifies the replacement — a
   reflection-store scan over `json_extract_string(metadata, '$.task_id')`.
   Do not follow this runbook literally without that step.
5. Restart the service and confirm `tasks_list` returns the same tasks.

Step 2 is a write to the live database while the service is down — an
operator action, so it is left to the operator rather than taken here.

## Related

- Session-Buddy task `t-01a1b8726b0d704ea2bcf0e117869695` (this work)
- Session-Buddy task `t-01a1b77b1747700ebbecae01de6bf625` (the durability
  bug Phase 1 makes loud)
- Memory `feedback-duckdb-poisoned-wal-recovery`,
  `duckdb-fixed-size-array-dim-mismatch`
