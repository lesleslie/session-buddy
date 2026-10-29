---
status: active
role: implementation
date: 2026-10-29
last_reviewed: 2026-10-29
superseded_by: null
blocks_on: []
topic: memory-architecture
---

# Per-Reflection Delete Tool

**Date:** 2026-10-29
**Status:** active, implementation — implemented and verified; awaiting merge to `main`
**Scope:** session-buddy
**Branch:** `feature/reflection-delete-tool`
**Worktree:** `~/.local/state/mahavishnu/worktrees/session-buddy/feature-reflection-delete`

## Problem

Session-Buddy can create and mutate a reflection, but it cannot remove one.
The MCP surface exposes `store_reflection`, `update_reflection` (via
`tasks_update`) and `search_reflections`, but no delete. The only ways to
remove a reflection today are:

- `reset_reflection_database` — drops the entire collection.
- `reset_reflection_database` on the adapter — same.
- Editing the DuckDB file by hand.

That asymmetry is the reason a superseded note cannot be removed. Three
versions of the same configuration note were stored under the same tags;
`deduplicate_content` reports **0 duplicates** because the versions differ
substantially in content, and `find_duplicates` cannot pair them either, so
the stale versions cannot be pruned. They will surface in `quick_search`
alongside the current one.

## Design

The capability already exists at the store layer. The gap is two layers up.

### Layer 1 — store: already implemented

`ReflectionDatabase.delete_reflection(reflection_id)` exists at
`session_buddy/reflection/database.py:643`. It checks for existence, deletes
from `reflections`, cleans `reflection_tags`, raises `TypeError` on `None`,
and returns `False` for a missing id. It already has unit, error-handling,
property-based and performance-benchmark coverage.

### Layer 2 — adapter: added

`ReflectionDatabaseAdapter.delete_reflection(reflection_id) -> bool`, placed
next to `update_reflection` and modelled on it (`cur.rowcount > 0`).

The v2 schema keeps `content`, `embedding`, `fingerprint` and `tags` on a
single `reflections_v2` row, so removing that row removes every derived
artifact with it:

| Derived artifact | Where it lives | Removed by |
|---|---|---|
| Semantic-search embedding | `reflections_v2.embedding` | the row delete |
| MinHash duplicate-detection fingerprint | `reflections_v2.fingerprint` | the row delete |
| Tags | `reflections_v2.tags` (JSON column) | the row delete |
| Search-result cache | `_query_cache`, keyed by query — stores result **IDs** and re-reads rows on a hit | no purge needed; the re-read simply returns nothing for the deleted id |

There is no child table keyed on `reflections_v2.id` to cascade into — every
`memory_*` table that carries a FOREIGN KEY references `conversations_v2(id)`.
`memory_provenance.memory_id` is unconstrained, so it is cleaned defensively
rather than relying on a constraint that does not exist.

### Layer 3 — MCP tool: added

`delete_reflection` follows the established `_operation` / `_impl` pair
pattern in `session_buddy/mcp/tools/memory/memory_tools.py`, registered with
`@mcp.tool()` alongside the other memory tools.

### The sidecar

`session_buddy/mcp/tools/tasks_storage.py` keeps task metadata in a
**separate SQLite database** (`tasks_metadata.sqlite`), keyed by
`reflection_id`. The module docstring states the cross-DB contract:

> *"a sidecar row whose reflection was deleted from DuckDB is orphaned and
> ignored by `find_tasks_by_metadata` consumers"*

DuckDB's delete cannot reach across that boundary, so
`tasks_storage.delete_task_metadata(engine, reflection_id)` was added and
the MCP tool calls it. A sidecar-cleanup failure is logged but does not fail
the delete — the reflection is gone either way.

## Integration Contract

| Field | Value |
|---|---|
| **Triggered from** | `mcp__session-buddy__delete_reflection(reflection_id)` (new MCP tool); `session_buddy.tools.memory_tools.delete_reflection(reflection_id)` (public API shim) |
| **Returns to / updates** | Removes one row from `reflections_v2` (DuckDB) and the matching row from the `reflections` sidecar table in `tasks_metadata.sqlite` |
| **Demonstrable by** | `tests/unit/test_reflection_delete_tool.py` — 13 tests covering row removal, idempotency, absence from plain and cached searches, fingerprint release, sidecar cleanup, and the MCP tool surface |
| **Rollback signal** | Any test in `tests/unit/test_reflection_delete_tool.py` fails; or `delete_reflection` returns `True` for a reflection that still appears in `quick_search` |
| **Observability added** | The tool returns a structured envelope: `ToolMessages.success` with `reflection_id` (plus `task_metadata_removed: true` when a sidecar row was also removed), or `ToolMessages.empty_results` for an unknown id — not an exception |

## Files changed

| File | Change |
|---|---|
| `session_buddy/adapters/reflection_adapter_oneiric.py` | Added `delete_reflection()` |
| `session_buddy/mcp/tools/memory/memory_tools.py` | Added `_delete_reflection_operation`, `_delete_reflection_impl`, and the `@mcp.tool()` registration |
| `session_buddy/mcp/tools/tasks_storage.py` | Added `delete_task_metadata()` |
| `session_buddy/tools/memory_tools.py` | Added the `delete_reflection` public shim and `__all__` entry |
| `tests/unit/test_reflection_delete_tool.py` | New — 13 tests |

## Decisions

- **Idempotent, not raising.** Deleting an unknown id reports "not found"
  rather than raising, matching `delete_conversation`'s contract (returns 0
  for a missing id).
- **No `reflection_tags` cleanup in the adapter.** The v2 schema has no such
  table — tags are a JSON column on `reflections_v2`. The legacy
  `reflection_tags` cleanup in `reflection/database.py` belongs to the legacy
  schema path.
- **No cache purge.** The query cache stores ids and re-reads rows, so a
  deleted reflection drops out of cached searches on the next query.
- **Sidecar failure is non-fatal.** Logged via `logger.exception`, but the
  reflection delete still succeeds.

## Open questions for review

1. **Profile gating.** `register_memory_tools(mcp)` is called unconditionally
   from `server_optimized.py:764`, so memory tools bypass the profile
   system entirely — a new destructive tool would be exposed at every tier,
   including `minimal`. The existing `store_reflection` is equally
   ungated, so this is consistent, but a destructive tool may deserve more
   care than a write.
2. **Should the tool be able to remove a task's backing reflection?** The
   sidecar cleanup handles the metadata row, but the task itself lives in a
   different subsystem. Deleting a reflection that backs an open task may
   need to refuse or cascade further.
3. **`update_reflection` has the same staleness class of bug.** It performs a
   bare `UPDATE` and never re-embeds or invalidates the cache, so an updated
   reflection can keep serving a stale cached embedding. The delete path does
   not inherit that problem (the row is gone), but `update_reflection` is
   worth a separate look.

## Verification

```
13 passed  — tests/unit/test_reflection_delete_tool.py
ruff       — clean on all five changed files
```

Regression note: `tests/unit/test_reflection_database_edge_cases.py` has 22
failures, but the **same 22 failures reproduce on unmodified `main`** — they
are pre-existing and unrelated to this change (that suite exercises the
legacy `ReflectionDatabase`, which this change does not touch).
