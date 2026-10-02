---
name: bodai-session-buddy-task-system
description: Use when the user asks to track, list, or complete work items that should survive the session — "what's on my plate", "create a todo", "show my open tasks", "what's overdue for me", "what's blocking me", "find tasks like X", "complete task t-...", or "track this for later". Routes to one of 5 backends (in-session checklist, subagent TodoWrite delegation, session-buddy tasks_*, mahavishnu workflows, akosha read) using the decision tree in the body.
allowed-tools: mcp__session-buddy__tasks_*, mcp__mahavishnu__tasks_handoff_to_workflow, mcp__akosha__tasks_*, Read, Write
---

# task-system (Bodai)

## When to use this skill

Use this skill when the user wants **persistent task tracking** that survives the session boundary. Triggers include:

- "what's on my plate"
- "create a task for X"
- "show my open tasks"
- "what's overdue for me"
- "what's blocking me"
- "find tasks like X" (semantic search)
- "complete task t-..."
- "track this for later"
- "list my tasks"
- "what did I do today" (history)

Do NOT use this skill for: pure exploratory questions, ephemeral session-local notes (use `/tmp/todos-<sid>.md`), git-branch-only operations (use `auto-coordinate`).

## Decision tree

| Condition | Backend |
|---|---|
| Ephemeral, single-session, <5 items | In-session markdown checklist or `/tmp/todos-<sid>.md` |
| Subagent dispatched, subagent HAS TodoWrite (`feature-dev:*`, `Explore`, `claude-security:*`) | Pass nothing; let subagent own its TodoWrite list |
| Subagent dispatched, subagent LACKS TodoWrite (`mahavishnu-orchestrator`, generic worker) | Call `mcp__session-buddy__tasks_create` BEFORE `Agent` dispatch with content = the subagent's task; pass `task_id` in the dispatch prompt so the worker can update via `tasks_complete` |
| Cross-session persistence needed | `mcp__session-buddy__tasks_create` |
| Triggers async follow-on work | `mcp__session-buddy__tasks_create` + `mcp__mahavishnu__tasks_handoff_to_workflow` (two separate calls; never implicit) |
| Read-only analytics ("what's blocking me?", "tasks like X") | `mcp__akosha__tasks_blocking` / `tasks_overdue_for` / `tasks_similar_to` (eventual consistency ~30s) |
| Fast read ("what's on my plate?") | `mcp__session-buddy__tasks_list(status="open")` — immediate, write-side |

## Tool surface (session-buddy)

All `tasks_*` tools live under the `mcp__session-buddy__*` namespace. Server-derived identity: `owner` and `created_by` are ALWAYS set from the MCP caller identity — caller-supplied values are silently overwritten (or rejected for `tasks_update`).

### `tasks_create(content, tags, owner=None, due=None, priority='normal', effort=None, parent_task_id=None, metadata=None) -> Task`

Create a new task. Rate limit: 60/min per caller. Tags MUST include `"task"` (Pydantic validator rejects otherwise). Content ≤ 4096 bytes; metadata ≤ 1024 bytes; ≤ 32 tags each ≤ 64 chars.

Returns a `Task` with `id` matching `^t-[0-9a-f]{32}$` (full UUID7 + `t-` prefix; compact form in `metadata.uuid_alias` for display).

```python
created = await tasks_create(
    content="Refactor the authz middleware",
    tags=["task", "authz", "refactor"],
    priority="high",
    effort="m",
)
print(created.id)  # t-0190a3b4c5d6c5d6c5d6c5d6c5d6c5d6
```

### `tasks_list(status=None, owner=None, tag=None, parent_task_id=None, include_legacy=False, k=20, cursor=None) -> TaskListResult`

List tasks with filtering and pagination. **Server-side: `owner` is forced to `caller_identity` regardless of caller input** (security-critical). Visibility filter applied to every row. `include_legacy=False` by default; legacy `tags=["todo"]` rows are excluded unless the caller opts in.

### `tasks_get(task_id: str) -> Task | error_envelope`

Fetch a single task by id. Validates `task_id` matches `^t-[0-9a-f]{32}$`. Returns 404 (not 403) on missing or invisible — no info leak.

### `tasks_update(task_id, request: UpdateTaskRequest) -> Task | error_envelope`

Update mutable fields. **Caller-supplied `owner` / `created_by` / `completed_by` are REJECTED** with `owner_mutation_forbidden` envelope (defense-in-depth via `getattr` since `UpdateTaskRequest` already excludes them via Pydantic `extra="forbid"`). `workflow_id` is server-set ONLY by `tasks_handoff_to_workflow`. Rate limit: 120/min per caller (shared with `tasks_complete`).

### `tasks_complete(task_id, result_notes=None) -> Task | error_envelope`

Mark a task as done. **Only the `owner` can complete**; non-owners get 404 (info-leak parity with `tasks_get`). Sets `status="done"`, `completed_at=now`, `completed_by=caller` (server-derived). **No implicit dispatch** — even if `result_notes` starts with `"HANDOFF: "`, no workflow is triggered. Use `tasks_handoff_to_workflow` for that.

### `tasks_search(query, project=None, min_score=None, k=10) -> list[Task]`

Semantic search with `quick_search` parity. Returns ONLY `kind=task` rows (filters out non-task reflections via sidecar metadata or tags). Visibility filter applied (private tasks excluded for non-owners). Filter ordering: kind=task gate → visibility → min_score (security first, relevance last).

### `tasks_history(task_id, k=50, cursor=None) -> TaskHistoryResult`

Fetch the change history for a task with cursor-based pagination. Reads `metadata["history"]` from the sidecar. Each entry is a `TaskEvent` with `event_type="updated"` for v1 (other event types reserved for future use by handoff/completion events). Returns `{items: list[TaskEvent], next_cursor: str | None}` (no `total` field).

## Subagent handoff

```
If subagent has TodoWrite (feature-dev:*, Explore, claude-security:*):
    Pass nothing extra; let the subagent maintain its own list.
If subagent lacks TodoWrite (mahavishnu-orchestrator, generic Mahavishnu worker):
    Call mcp__session-buddy__tasks_create BEFORE Agent dispatch with content = the subagent's task.
    Pass task_id in the dispatch prompt so the worker can update via tasks_complete.
    Worker should call mcp__session-buddy__tasks_complete when done.
```

## Handoff to workflow (the ONLY dispatch edge)

```python
# Step 1: Create the task
task = await tasks_create(content="...", tags=["task", "workflow"])

# Step 2: Hand off to a mahavishnu workflow (separate call; never implicit)
workflow_id = await mcp__mahavishnu__tasks_handoff_to_workflow(
    task_id=task.id,
    adapter="prefect",  # or "llamaindex" | "agno"
    task_type="code_review",
    params={"prompt": "..."},
    timeout=300,
)
# Step 3: The handoff tool updates task.workflow_id server-side.
# Do NOT try to set workflow_id via tasks_update; it's rejected.
```

**Critical:** `tasks_complete` does NOT dispatch. The only path from a task to a running workflow is the explicit two-call sequence above.

## Backend selection rules

1. **Ephemeral, single-session, <5 items** → in-session checklist. Skip the tools entirely.
2. **Subagent has TodoWrite** → pass nothing; subagent owns its list.
3. **Cross-session persistence** → `tasks_create` (session-buddy).
4. **Async follow-on work** → `tasks_create` then `tasks_handoff_to_workflow` (two calls; never implicit).
5. **Read-only analytics** → akosha `tasks_*` tools (eventual consistency ~30s).
6. **Fast read of "what's on my plate"** → `tasks_list(status="open")` from session-buddy (immediate).

## Negative trigger phrases

DO NOT use this skill for:

- Pure exploratory questions with no task to track ("how does X work?")
- Ephemeral session-local notes (use `/tmp/todos-<sid>.md`)
- Git-branch-only operations (use `auto-coordinate`)
- Claude Code's built-in `TaskCreate`/`TodoWrite` (these tools are blocked by Anthropic's `tengu_vellum_ash` server-side gate against MiniMax-M3 / Opus / Sonnet / Fable in this session — use this skill instead)

## Schema reference

```
Task.id            = "t-{32 hex}"   # full UUID7 with t- prefix; compact form in metadata.uuid_alias
Task.owner         = "user:<email>" | "agent:<id>"  # server-derived from caller
Task.tags          = ["task", "<domain>", ...optional]  # "task" discriminator required
Task.status        = open | in_progress | blocked | done | cancelled
Task.priority      = critical | high | normal | low
Task.effort        = xs | s | m | l | xl
Task.visibility    = private (default) | team (treated as private in v1.1; v2+ expands) | public (supported in v1.1)
```

## Events

`tasks_*` mutations emit events to `bodai:events` Redis Stream via oneiric `RedisStreamsQueueAdapter`; consumers read via `XREADGROUP` with consumer group `bodai-task-orphan-sweeper`.

Event types under the `task.*` namespace:

- `task.created` — new task minted
- `task.updated` — one event per diff field (content, priority, status, etc., plus `updated_at`)
- `task.completed` — task marked done
- `task.cancelled` — task cancelled (reuses `task.completed` payload for v1)
- `task.handoff_started` / `task.handoff_completed` / `task.handoff_orphan` — emitted by `tasks_handoff_to_workflow` (mahavishnu, T17)

v1.1 adds the `TaskOrphanSweeper` in mahavishnu that re-links tasks on `task.handoff_orphan` events.

Akosha indexes these; reindex lag is ~30s. Read-side analytics via `mcp__akosha__tasks_*` tools will reflect writes within that window.

## Failure modes

- **Rate limit (60/min create, 120/min update/complete, 10/min handoff)** — caller exceeds quota → `rate_limited` error envelope. Retry after the window.
- **404 on tasks_get / tasks_update / tasks_history / tasks_complete** — task not found OR caller lacks visibility. Both look identical to the caller (no info leak).
- **`invalid_id_format`** — `task_id` doesn't match `^t-[0-9a-f]{32}$`. Check for truncation, UUID7 prefix lost, or extra dashes.
- **`owner_mutation_forbidden`** — caller tried to set `owner`/`created_by`/`completed_by` via `tasks_update`. These fields are server-derived; users cannot change ownership.
- **`akosha reindex lag`** — `mcp__akosha__tasks_*` reads may show stale data for ~30s after a write. Use `mcp__session-buddy__tasks_*` for immediate consistency.

## Cross-references

- `bodai-radar` — cross-ecosystem search (includes tasks via akosha reindex)
- `auto-coordinate` — git-branch coordination (different concern; use for branches not tasks)
- `ecosystem-skill-loader` — installs skills published by the loader (this skill is auto-discoverable through `mcp__akosha__list_ecosystem_skills`)
- `crackerjack-compliant-code` — code style for any code emitted while reasoning about this skill

## Versioning

- v1.0: Initial release with `tasks_create`, `tasks_list`, `tasks_get`, `tasks_update`, `tasks_complete`, `tasks_search`, `tasks_history`.
- v1.1 ships: T12 fixed in v1.1; `visibility="public"` is supported. `BodaiEventsPublisher` ships events to `bodai:events` via oneiric `RedisStreamsQueueAdapter`; `TaskOrphanSweeper` re-links tasks on `task.handoff_orphan` events. v1.1 preserves current `team` semantics — see v2+ scope below.

## v2+ scope

- **team-mode ACL**: when `visibility="team"`, callers should see other members' team-visible tasks; v1.1 preserves current `team` semantics (treated as private) and defers this to v2+.
