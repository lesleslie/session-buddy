# Cross-Repo Work Accounting in Checkpoint — Design

> **For agentic workers:** This spec captures the design for cross-repo work accounting in session-buddy checkpoints. The implementation plan will follow in a separate document under `docs/superpowers/plans/`.

**Date:** 2026-08-05
**Status:** Draft v2 (post-multi-agent-review)
**Author:** Claude (per user brainstorming)
**Brainstorm:** `superpowers:brainstorming`
**Review:** 7-agent multi-lens review (code, architecture, schema, MCP, Python, resilience, strategic) — 9 convergent Criticals + EventBridge alignment addendum applied

## Context

Session-buddy's checkpoint pipeline is currently strictly single-project: when a session runs `mcp__session-buddy__checkpoint`, the work captured is scoped to `working_directory.name` only. Other Bodai ecosystem repos (mahavishnu, akosha, dhara, crackerjack, oneiric) are invisible to the checkpoint.

This breaks down when a single session spans multiple repos — e.g., the session that built mahavishnu's pool routing AND ran crackerjack quality work AND fixed session-buddy itself. The handoff doc captures session-buddy work but not the cross-repo work. Future consumers (routing, trigger follow-ups) have no audit trail.

**Goal:** Record cross-repo work in the checkpoint with enough structure to (a) enrich the handoff doc and (b) provide a substrate for future routing/trigger surfaces — without adding new dependencies or breaking the existing checkpoint pipeline.

**Approach:** Structured per-checkpoint, per-repo JSON storage with two ingest paths: ambient pull (session-buddy's own checkpoint pulls git log from sibling repos) and explicit push (other Bodai repos push via MCP). Handoff consumes the stored rows.

**Non-goals (out of scope for this spec):**

- Routing decisions in mahavishnu that consume cross-repo state.
- Trigger follow-ups via `broadcast_repository_message`.
- Per-task attribution finer than git commits (no per-CLAIM-line, no per-test-run unless explicitly pushed).
- Cross-repo identifier registry (`ext:<id>` chain IDs); we use git SHAs as canonical work IDs.

## Goals

- **G1**: When a session-buddy checkpoint runs, sibling-repo work (commits since session start) is captured automatically.
- **G2**: Other Bodai repos can explicitly push cross-repo work entries (commits, plan refs, blockers, test runs) into the checkpoint via an MCP write. Pushes target the **`conversation_id`** established by session-buddy's `start_session` tool (see §Session identity). A push with an unknown `conversation_id` is rejected (the spec's G7, derived from C5/I3 of the multi-agent review).
- **G3**: The handoff doc includes a "Cross-Repo Work" section listing per-repo activity.
- **G4**: Existing checkpoint behavior is preserved (no breaking changes to existing callers).
- **G5**: Storage is idempotent on `(conversation_id, repo_name, sha)` — duplicate pushes are deduped.
- **G6**: Cross-repo accounting failures NEVER break the checkpoint. They're observational metadata; the actual git commit / handoff doc must proceed even if ambient-pull or explicit-push fails.
- **G7 (derived from review C5/I3)**: Session identity is unambiguous. The join key across `cross_repo_work_v2`, `conversations_v2`, and any external pusher (mahavishnu, akosha, etc.) is the **`conversation_id`** established by session-buddy's `start_session` MCP tool and persisted on `conversations_v2`. See §Session identity.
- **G8 (derived from review trend-analyst C1/C2)**: This table is a **pre-EventBridge materialization** for repos that haven't shipped their publishers yet. Routing/trigger consumers will eventually read from EventBridge; `cross_repo_work_v2` is the fallback. See §Convergence-plan alignment.

## Architecture

```
session-buddy
├─ commands/checkpoint.py (existing)          ──┐
├─ core/session_manager.py                     │
│   SessionLifecycleManager.checkpoint_session│
│           │                                  │   ┌─ NEW ──────────────────────────────┐
│           ▼                                  ├──▶│ CheckpointCrossRepoAccountant      │
│   CheckpointCrossRepoAccountant             │   │ (orchestrator)                    │
│       │                                      │   │                                     │
│       ├──▶ AmbientPuller                    │   │ - reads ecosystem.yaml            │
│       │       (NEW)                          │   │ - invokes git log per repo        │
│       │       - settings/ecosystem.yaml       │   │ - merges with explicit-pushed      │
│       │       - git log --since session_window_start │   │ - writes cross_repo_work v2 row   │
│       │                                      │   │                                     │
│       ├──▶ CrossRepoPusher consumer          │   └─────────────────────────────────────┘
│       │       (NEW)                          │
│       │       - reads already-pushed entries  │   ┌─ NEW ──────────────────────────────┐
│       │       from cross_repo_work_v2         │   │ HandoffLink                         │
│       │       (no read API needed if merged  │   │ (consumer in core/lifecycle/       │
│       │       into the same table)           │   │  handoff.py)                       │
│       │                                      ├──▶│ - reads cross_repo_work rows       │
│       └──▶ Write to cross_repo_work_v2        │   │ - renders "Cross-Repo Work"        │
│                                                │   │   markdown section                │
│                                                │   └─────────────────────────────────────┘
│                                                                 ▲
│                                                                 │
│                                  mcp__session-buddy__store_cross_repo_work
│                                                                 │
│                            ┌──────────────────────────────┐    │
│                            │ mahavishnu (and other Bodai)   │────┘
│                            │ explicit push at their        │
│                            │ checkpoint workflow           │
│                            └──────────────────────────────┘
```

## Components

### NEW: `CheckpointCrossRepoAccountant` (orchestrator)

- Location: `session_buddy/core/checkpoint/cross_repo_accountant.py`
- Single public method: `capture(working_directory: Path, conversation_id: str) -> CrossRepoCaptureSummary`
- Coordinates AmbientPuller + existing pushed rows + merge + write to `cross_repo_work_v2`.
- Never raises. Returns a summary `{repos_captured: int, ambient_failures: list[str], explicit_count: int}` for the checkpoint log.

### NEW: `AmbientPuller`

- Location: `session_buddy/core/checkpoint/ambient_puller.py`
- Reads `settings/ecosystem.yaml` (a new session-buddy-side manifest cache modeled on mahavishnu's `repos.yaml`).
- **Non-local filter (review resilience C4)**: exclude the repo whose resolved path equals `working_directory.resolve()`. Comparison is by canonicalized path, not name, to handle aliased checkouts.
- For each non-local sibling repo, runs `git log` in a worker thread via `asyncio.to_thread` (matches existing `perform_git_checkpoint` pattern; review python-pro #6, resilience C3, architect C3):
  ```
  git log --since=<unix-timestamp> --until=<unix-timestamp> -n 500 \
          --format=%H%x09%s%x09%an%x09%ae%x09%aI -- <repo_path>
  ```
  - `--since` / `--until` use integer epoch seconds so timezone interpretation is unambiguous (review resilience I4).
  - `-n 500` bounds the result size so a stale `session_window_start` doesn't flood the row (review resilience I5).
  - `--format` produces 5 fields per commit: SHA, subject, author name, author email, ISO timestamp. Parsed in Python into `CommitEntry` rows.
  - **Per-repo timeout: 10s** via `subprocess.run(..., timeout=10)`; on timeout, kill child, log WARNING, skip. **Per-batch timeout: 30s** total across all siblings.
- Returns `list[CommitEntry]` keyed by `repo_name`, all with `provenance="ambient"`.
- Never raises; per-repo failures are logged + the repo is skipped. Bound is 30s total; if reached, abandons AmbientPuller with WARNING.

### NEW: `CrossRepoPusher` (MCP tool — receiver-side; rename candidate: `register_cross_repo_work_tools`)

- Location: `session_buddy/mcp/tools/cross_repo_work.py`
- FastMCP registers the tool as `store_cross_repo_work`; Claude clients display it as `mcp__session-buddy__store_cross_repo_work` (the `mcp__session-buddy__` prefix is the client namespace, not the registered name — review mcp-integration-expert Minor #1).
- Signature (Pydantic-typed, per review mcp-integration-expert Critical #1):

  ```python
  from mcp_common.auth import require_auth, Permission
  from pydantic import BaseModel, ConfigDict, Field

  class RepoWorkEntry(BaseModel):
      model_config = ConfigDict(extra="forbid")
      repo_name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
      repo_path: str                                       # resolved server-side via ecosystem.yaml
      work_entries: Annotated[list[WorkEntry], Field(min_length=1, max_length=200)]

  class StoreCrossRepoWorkRequest(BaseModel):
      model_config = ConfigDict(extra="forbid")
      conversation_id: Annotated[str, StringConstraints(min_length=26, max_length=26)]  # ULID
      repos: Annotated[list[RepoWorkEntry], Field(min_length=1, max_length=26)]

  class RepoStoreStatus(BaseModel):
      repo_name: str
      status: Literal["stored", "deduplicated", "rejected"]
      entries_received: int
      entries_inserted: int
      entries_deduplicated: int
      message: str | None = None

  class CrossRepoStoreResult(BaseModel):
      model_config = ConfigDict(extra="forbid")
      repos_received: int
      repos_stored: int
      entries_received: int
      entries_inserted: int
      entries_deduplicated: int
      per_repo: list[RepoStoreStatus]
      retryable: bool
  ```

- **Auth contract** (review mcp-integration-expert Critical #7): wrapped with `@require_auth()` and verifies the caller has `Permission.WRITE`. The previous `store_code_graph_from_mahavishnu` precedent is unguarded; newer session-tracking tools (`admin_shell_tracking_tools.py`, `channel_tracking_tools.py`) use `@require_auth()` without checking `Permission.WRITE`. The new tool MUST check `Permission.WRITE` — the spec is explicit so the implementer doesn't copy the unguarded precedent. The authentication token / context parameter is provided by the existing FastMCP auth context (no new auth surface added here).
- **Idempotency**: server-side, via §Merge primitive. Re-pushing the same `(conversation_id, repo_name, sha)` is a no-op recorded as `status="deduplicated"`. Callers don't preflight or maintain local dedupe caches — review mcp-integration-expert Critical #4.
- **Multi-repo batch atomicity** (review mcp-integration-expert Important #2 + resilience C8): all repos in a single call are written in one `BEGIN IMMEDIATE` transaction. Either the whole call succeeds (all repos stored) or it fails with a retryable error. The result's `per_repo` list reports per-repo `entries_received/inserted/deduplicated` counts even on success.
- **Registration contract** (review mcp-integration-expert Critical #6): the tool's registration must be exported from `session_buddy/mcp/tools/__init__.py`, listed in `_ALL_REGISTERS`, and wired into the `STANDARD` tool profile (the profile gate that determines which tools are available). Without these three wiring steps, the tool registers successfully but Mahavishnu sees "method not found" under every profile.
- **Path authority** (review mcp-integration-expert Important #5): the wire identity is a normalized repository slug (`repo_name`); the server resolves `repo_path` from `ecosystem.yaml` and **never** runs filesystem operations against a caller-supplied path.

### NEW: `HandoffLink` (consumer in `core/lifecycle/handoff.py`)

- Reads `cross_repo_work_v2` rows for the current session.
- Renders a "## Cross-Repo Work" section in the **production handoff path**: `session_buddy/core/session_manager._generate_handoff_documentation` (per review code-reviewer C3; the alternative path `core/lifecycle/handoff.py::generate_handoff_documentation` is a legacy duplication and the spec does not target it).
- Section anchor: **after "Quality Breakdown"** in the production handoff (line 789-823 of `session_manager.py`). No "Recovery" section exists in either path; the spec's earlier "Quality → Recovery" anchor was wrong and is replaced by this concrete anchor.
- Per-repo bullets: `repo_name (role): N commits since <start>` + first 5 commit SHAs (7-char) + subjects + author (sanitized via `html.escape`).
- **Sentinel on render failure** (per review resilience C7): always render the `## Cross-Repo Work` header. If `cross_repo_work_v2` query fails, body is `> Cross-Repo Work could not be captured: <reason>. See <log_ref>.` Downstream consumers can distinguish "no work captured" from "capture failed" — the former renders `_No cross-repo work captured._`, the latter renders the failure sentinel.

### NEW: `settings/ecosystem.yaml`

- New file. Format mirrors mahavishnu's `settings/repos.yaml`.
- Example:
  ```yaml
  ecosystem:
    session-buddy:
      path: /Users/les/Projects/session-buddy
      role: memory
    mahavishnu:
      path: /Users/les/Projects/mahavishnu
      role: orchestrator
    crackerjack:
      path: /Users/les/Projects/crackerjack
      role: quality
    # ... 26 Bodai repos
  ```
- `.gitignore` includes this file by default (per-repo local config, not shared).
- A bootstrap script `scripts/bootstrap_ecosystem_manifest.py` reads mahavishnu's `repos.yaml` and generates this file on first run.

## Data flow

```
[Mahavishnu's checkpoint workflow]
   │
   ▼
mcp__session-buddy__store_cross_repo_work(conversation_id, repos=[...])
   │
   ▼
[CrossRepoPusher validates + writes to cross_repo_work_v2]

[Session-buddy's own checkpoint workflow]
   │
   ▼
SessionLifecycleManager.checkpoint_session(working_directory)
   │
   ▼
CheckpointCrossRepoAccountant.capture(working_directory, conversation_id)
   │
   ├─▶ AmbientPuller.run(working_directory, conversation_id, session_window)
   │     │
   │     ├─ Read settings/ecosystem.yaml (sibling repos)
   │     ├─ For each non-local repo:
   │     │     ├─ Skip if not a git repo (graceful)
   │     │     ├─ git log --since session_window_start --until session_window_end
   │     │     └─ Capture: {sha, subject, author_name, author_email, timestamp} → CommitEntry
   │     └─ Returns list of repos with work entries
   │
   ├─▶ Merge with explicit-pushed entries (idempotent on (conversation_id, repo_name, sha))
   │
   └─▶ Write merged result to cross_repo_work_v2

[Read path: handoff]
   │
   ▼
HandoffLink.render_section(conversation_id, handoff_context)
   │
   ├─ Read cross_repo_work rows for conversation_id
   ├─ Group by repo_name
   ├─ Render markdown section
   └─ Return for inclusion in handoff
```

**Lifecycle properties:**

- **Idempotent on `(conversation_id, repo_name, sha)`**: re-running checkpoint won't duplicate commits (enforced by §Merge primitive).
- **Per-conversation window**: `session_window_start = start_session invocation timestamp` (persisted on `conversations_v2`); `session_window_end = NOW()` at each `capture()` call. Multiple checkpoints in the same conversation share the start; consecutive checkpoints' ambient captures accumulate via the merge primitive.
- **No hot path**: ambient pull adds ~50-200ms per sibling repo (git log is fast); explicit push is just an MCP write.
- **Failures**: AmbientPuller failures are logged + the repo is skipped, NOT fatal. Explicit push failures return error to caller.

## Schema

```sql
-- New v2 reflection table. Modeled on session_buddy/reflection/database.py:v2 schema style.
-- TEXT PKs match existing v2 convention (see schema_v2.py:39-119); ULID generated by Python.
-- Idempotency on (conversation_id, repo_name, sha) is enforced by the MERGE primitive in
-- §Merge primitive (atomic read-dedup-write in BEGIN IMMEDIATE), NOT by a schema
-- UNIQUE constraint — see Multi-agent Review C1.
CREATE TABLE cross_repo_work_v2 (
    id              TEXT PRIMARY KEY,                 -- ULID, generated by Python (matches generate_ulid())
    conversation_id      TEXT NOT NULL,                    -- ULID, FK-equivalent to conversations_v2.id (informational only — DuckDB FKs are advisory)
    repo_name       TEXT NOT NULL,                    -- e.g. "mahavishnu"
    repo_path       TEXT NOT NULL,                    -- absolute path on disk (denormalized from ecosystem.yaml at write time)
    repo_role       TEXT,                            -- e.g. "orchestrator", "quality" — from ecosystem.yaml
    session_window_start  TIMESTAMP WITH TIME ZONE NOT NULL,
    session_window_end    TIMESTAMP WITH TIME ZONE NOT NULL,
    work_entries    JSON NOT NULL,                   -- see shape below; per-entry dedup via §Merge primitive
    contributor_sources JSON NOT NULL DEFAULT '[]',  -- per-path provenance: ["ambient", "explicit"] — set semantics
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, repo_name)                   -- one row per (conversation, repo); sha-level dedup is §Merge primitive's job
);
```

**Why TEXT PKs and no UUID DEFAULT:** DuckDB's UUID generator is `uuid()`, not `gen_random_uuid()` (which is PostgreSQL). All existing session-buddy v2 tables use TEXT PKs with Python-side ULID generation (`session_manager.py:947` calls `generate_ulid()`); matching that convention lets `cross_repo_work_v2` join to `conversations_v2.id` without type coercion. The `id` column is filled by the orchestrator before INSERT.

## Merge primitive

Per-review Critical #1, #9 (convergent): SQL `UNIQUE(conversation_id, repo_name)` does **not** enforce the documented idempotency on `(conversation_id, repo_name, sha)`. Idempotency is enforced at the **application-level merge primitive**, not by a schema constraint. This matches DuckDB's lack of native JSON-set semantics and sidesteps the read-modify-write race the JSON-column design would otherwise create.

**The merge is atomic per row.** It runs inside `BEGIN IMMEDIATE` (DuckDB's serializable-per-connection transaction) so concurrent ambient + explicit writers cannot lose updates:

```sql
-- Performed inside BEGIN IMMEDIATE; one writer at a time per session-buddy connection.
INSERT INTO cross_repo_work_v2 (
    id, conversation_id, repo_name, repo_path, repo_role,
    session_window_start, session_window_end,
    work_entries, contributor_sources,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?::JSON, ?::JSON, NOW(), NOW())
ON CONFLICT (conversation_id, repo_name) DO UPDATE SET
    work_entries = dedupe_work_entries(
        cross_repo_work_v2.work_entries,
        excluded.work_entries
    ),
    contributor_sources = union_provenance(
        cross_repo_work_v2.contributor_sources,
        excluded.contributor_sources
    ),
    session_window_end = GREATEST(
        cross_repo_work_v2.session_window_end,
        excluded.session_window_end
    ),
    updated_at = NOW();
```

`dedupe_work_entries` is a Python pre-processing step (Pydantic-side) before this SQL runs:

1. Parse `cross_repo_work_v2.work_entries` (existing JSON) and `excluded.work_entries` (incoming JSON) into `list[WorkEntry]`.
2. Build a dedup key for each entry: `(kind, sha)` for `CommitEntry`, `(kind, plan_path)` for `PlanRefEntry`.
3. For collisions: prefer `provenance="explicit"` over `"ambient"` (review resilience C6); take the max `files_changed_count`; preserve the first-observed `timestamp`.
4. Return the merged `list[WorkEntry]` for the SQL `?::JSON` placeholder.

**Why not a normalized child table with `UNIQUE(conversation_id, repo_name, sha)`:** Reviewer mcp-integration-expert #4 suggested it as an alternative. We choose the JSON-merge approach because (a) the read path (HandoffLink) renders a single section per repo, so one row per (session, repo) is the natural read shape; (b) the JSON is small (~10 entries typical, 200 cap) so JSON-vs-normalized performance is irrelevant; (c) consolidating per-row provenance via `contributor_sources` keeps the "what paths contributed" answer cheap. The trade-off is documented in the testing matrix (the merge primitive gets its own unit test).

## Storage abstraction

All writes go through session-buddy's `ReflectionDatabaseAdapter` (`session_buddy/adapters/reflection_adapter_oneiric.py`) via `require_reflection_database()` + the existing locking convention. Reviewer mcp-integration-expert Important #3: the new DDL must be added to **every** active schema-initialization and migration path in `session_buddy/memory/schema_v2.py` and the migration registry (`session_buddy/memory/migration.py`); a tool that registers successfully but lands on a path missing the new DDL would return "table not found."

```sql
-- work_entries JSON shape (per-entry; dedup key is (kind, sha) for commit/pr/test_run or (kind, plan_path) for plan_ref):
[
  {
    "kind": "commit",
    "sha": "abc123def456...",                   -- required for commit; canonical ID
    "subject": "feat(mahavishnu): wire pool routing",
    "files_changed_count": 3,
    "author": "les <les@...",                   -- max 200 chars, sanitized on render (resilience I9)
    "timestamp": "2026-08-05T01:23:45Z",
    "provenance": "ambient",                    -- 'ambient' | 'explicit'; required for per-entry dedup
    "correlation_id": "wf_abc123",              -- optional; future consumer pattern (trend-analyst C4)
    "causation_id": null                        -- optional; future consumer pattern
  },
  {
    "kind": "plan_ref",
    "plan_path": "docs/superpowers/plans/2026-08-05-foo.md",  -- required for plan_ref
    "phase": "phase-1",
    "provenance": "explicit"
  }
]
```

**Pydantic mirror in `session_buddy/memory/cross_repo_work.py` (discriminated union per review C6):**

```python
from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Provenance = Literal["ambient", "explicit"]
AuthorStr = Annotated[str, StringConstraints(max_length=200, strip_whitespace=True)]

class _BaseEntry(BaseModel):
    """Shared shape. extra='forbid' prevents silent field-drop on typo."""
    model_config = ConfigDict(extra="forbid")
    provenance: Provenance
    correlation_id: str | None = None      # future consumer pattern
    causation_id: str | None = None        # future consumer pattern

class CommitEntry(_BaseEntry):
    kind: Literal["commit"]
    sha: str                                # required (review C6: kind=commit without sha is meaningless)
    subject: str | None = None
    files_changed_count: int | None = None
    author: AuthorStr | None = None
    timestamp: datetime | None = None

class PlanRefEntry(_BaseEntry):
    kind: Literal["plan_ref"]
    plan_path: str                          # required
    phase: str | None = None

# Future kinds (PR, test_run, blocker) deferred — they need their own models with
# required-field contracts. Adding them later is a Pydantic-only change.

WorkEntry = Annotated[
    Union[CommitEntry, PlanRefEntry],
    Field(discriminator="kind"),
]

class CrossRepoWorkRowCreate(BaseModel):
    """Used by AmbientPuller / CrossRepoPusher to build the row to insert."""
    model_config = ConfigDict(extra="forbid")
    id: str                                  # ULID; orchestrator generates
    conversation_id: str                          # ULID; matches conversations_v2.id
    repo_name: str
    repo_path: str
    repo_role: str | None = None
    session_window_start: datetime
    session_window_end: datetime
    work_entries: list[WorkEntry]
    contributor_sources: list[Provenance] = Field(default_factory=list)

class CrossRepoWorkRowRead(BaseModel):
    """Used by HandoffLink / read paths. Includes DB-generated timestamps."""
    model_config = ConfigDict(extra="forbid")
    id: str
    conversation_id: str
    repo_name: str
    repo_path: str
    repo_role: str | None = None
    session_window_start: datetime
    session_window_end: datetime
    work_entries: list[WorkEntry]
    contributor_sources: list[Provenance]
    created_at: datetime
    updated_at: datetime
```

**Why discriminated union (not flat-optional):** Review C6 caught that `WorkEntry(kind="commit")` with no `sha` passed validation, leaving the idempotency key empty. The tagged-union form enforces that `CommitEntry` has a `sha` and `PlanRefEntry` has a `plan_path` at the type layer, so callers can't construct entries that violate the dedup invariant. `extra="forbid"` (per review python-pro #4) prevents silent field-drop on typos.

## Error handling

| Failure mode | Behavior |
|---|---|
| `settings/ecosystem.yaml` missing | AmbientPuller skips pull entirely; logs INFO; checkpoint continues normally. (No ambient, but explicit push still works.) |
| `settings/ecosystem.yaml` present but malformed | Skip ambient + emit WARNING to checkpoint log; do NOT raise (don't break checkpoint on bad config). |
| `settings/ecosystem.yaml` filesystem pathologies (symlink loop, permission denied) | Skip ambient + emit WARNING; never raise. Validate via `os.path.realpath` for symlink loops and bound file size to 1 MiB. |
| Sibling repo path not a git repo | Skip that repo; emit DEBUG; continue with others. |
| `git log` on sibling times out | Per-repo timeout: 10s (`subprocess.run(..., timeout=10)`). On timeout: kill child, log WARNING `repo=<name> kind=git_log_timeout duration_ms=<n>`, skip repo, continue. Per-batch cap: 30s total across all siblings; if reached, abandon AmbientPuller with WARNING. (Review resilience C2.) |
| `git log` on sibling returns non-zero exit (transient: lock, EAGAIN) | Retry 2x with backoff (250ms, 750ms); on persistent failure, skip with WARNING. (Review resilience I1.) |
| Explicit push with malformed payload | Return 4xx-shaped error to caller (existing pattern). Log WARNING; do not store. |
| Explicit push with `conversation_id` that doesn't exist | Return 4xx-shaped error "session not found"; no store. (Review code-reviewer C1.) |
| Explicit push with unknown `repo_name` / `repo_path` | Return 4xx-shaped error "repo not in ecosystem.yaml"; no store. (Review code-reviewer I5.) |
| Explicit push mid-batch partial failure (A/B/C stored, D fails, E stored) | Wrap in single `BEGIN IMMEDIATE` transaction; write-all-or-roll-back. Caller sees either full success or full failure. (Review resilience C8.) |
| Storage write fails (DuckDB lock) | Retry 3x with backoff (100ms, 500ms, 2s); on exhaustion, **skip the write and log WARNING** — do NOT surface as checkpoint failure. Cross-repo accounting is observational metadata; a missed write is acceptable and never blocks the git commit / handoff doc. (Review C3 — directly fixes the contradiction with G6.) |
| `work_entries` JSON exceeds size cap (256 KiB or 200 entries) | Truncate with `<!-- truncated, N omitted -->` marker inside the JSON, log WARNING, continue. (Review resilience C5.) |
| HandoffLink.render_section fails | Log ERROR; handoff doc still written with sentinel `> Cross-Repo Work could not be captured: <reason>. See <log_ref>.` so downstream consumers can distinguish "no work" from "capture failed". (Review resilience C7.) |
| Clock skew detected (`session_window_start > session_window_end`) | Swap values, log WARNING `clock_skew_detected`, continue. (Review resilience I3.) |
| Concurrent AmbientPuller invocations | Use `BEGIN IMMEDIATE` transaction (DuckDB serializable per connection). Merge primitive in §Merge primitive is commutative so last-writer-wins is correct. (Review resilience I6.) |

## Session identity

Per-review code-reviewer I2, architect I1, python-pro C2, mcp-integration-expert Critical #2: a single canonical identifier must exist for the join key. The existing `checkpoint_session()` flow generates a fresh ULID per checkpoint invocation, which makes "session_start..now" semantics ambiguous across consecutive checkpoints. Resolution:

- **Canonical join key: `conversation_id`** (the session-buddy `conversations_v2.id` ULID), established by `start_session` MCP tool (or equivalent — to be added if not present) and **persisted** on `conversations_v2` at session start.
- `cross_repo_work_v2.conversation_id` (renamed from `conversation_id` in earlier revisions for clarity) joins 1:1 with `conversations_v2.id`.
- `CheckpointCrossRepoAccountant.capture(working_directory, conversation_id, session_window_start, session_window_end)` takes the conversation_id (not a per-checkpoint ID). The `session_window_start` is the conversation-start timestamp; `session_window_end` is "now" at the capture call.
- External pushers (Mahavishnu, Akosha, Crackerjack) learn the conversation_id either by:
  - Calling `start_session` themselves at the same logical session start, OR
  - Reading the conversation_id from a shared context propagation mechanism (the spec does NOT specify the mechanism — that's an open question for the implementation plan).

The earlier name `conversation_id` is replaced by `conversation_id` throughout this spec to match `conversations_v2.id` naming and avoid confusion with ephemeral per-checkpoint IDs.

## Convergence-plan alignment

Per-review trend-analyst C1, C2, I5 (and Important #1, #2): the Bodai Observability Pattern decision (`.claude/decisions/bodai-observability-pattern.md`) establishes that "the Claude Code observability surface for Bodai reads from Oneiric EventBridge exclusively," and Phase 6B of the convergence plan assigns Akosha and Crackerjack as **publishers to EventBridge** (publisher work is "cross-repo work 6.2a/6.2b, not started"). This spec creates a parallel storage path; that relationship must be explicit.

**Position of `cross_repo_work_v2` in the convergence roadmap:**

- `cross_repo_work_v2` is a **pre-EventBridge materialization** for repos that haven't shipped their EventBridge publishers yet (mahavishnu, akosha, dhara, crackerjack are scheduled for 6.2a/6.2b; the rest of the 26 Bodai repos are not on that roadmap).
- EventBridge activity events for entry kinds `test_run.completed`, `workflow.completed`, `agent.task.*` are the **primary live path** once publishers ship. `cross_repo_work_v2` rows are a **checkpoint-time snapshot** that catches work the publishers missed (commits, manual `plan_ref` entries, `blocker` markers).
- Future routing/trigger consumers in Mahavishnu should be designed against the EventBridge envelope (per Bodai Observability Pattern); `cross_repo_work_v2` is a fallback for the gap period.
- The `contributor_sources JSON` column records `["ambient", "explicit"]` per row, providing the audit trail that EventBridge eventually replaces.

**Open question (deferred to the implementation plan):** when EventBridge publishers land, how does the existing `cross_repo_work_v2` table relate to the activity-event stream? Three options: (a) keep both, with `cross_repo_work_v2` as the checkpoint-time mirror; (b) deprecate `cross_repo_work_v2` once all publishers are live; (c) republish existing rows through EventBridge on first run. The implementation plan will pick one with a migration story.

**`correlation_id` and `causation_id` per work entry:** the per-entry fields `correlation_id` and `causation_id` (added to `WorkEntry` in §Schema) exist specifically to support future consumer patterns that join EventBridge events back to the conversation that triggered them. These fields are **optional at v2** — producers don't have to set them — but the columns exist so a v3 migration isn't required when consumers need the join.

**Documented boundary:** this design captures **completed work** (git commits, finished test runs, finalized plan refs). It does NOT capture **in-progress agent activity** (workflows mid-flight, blocked tasks, running tests, paused pools). Live activity is the EventBridge surface's job; this table is a lagging indicator, named accordingly.

## Testing

| Layer | Test |
|---|---|
| Unit | AmbientPuller: with fixtures for ecosystem.yaml (empty, malformed, 3-repo config). Verifies: empty → INFO skip, no rows written; malformed → WARNING skip; 3-repo → 3 ambient-pull invocations, 3 rows. Per-repo timeout: simulate a wedged sibling via a sleep-injected git wrapper, verify 10s timeout fires, repo is skipped, WARNING logged. Per-batch timeout: simulate 5 slow siblings, verify 30s cap fires with WARNING. (Review resilience C2.) |
| Unit | AmbientPuller: non-local filter (review resilience C4). Working dir matching one of the ecosystem.yaml paths → that repo excluded from ambient; the other siblings still captured. |
| Unit | AmbientPuller: asyncio event loop unblocked (review code-reviewer C3). Mock the orchestrator; assert no `subprocess.run` calls happen on the loop thread; only `asyncio.to_thread` invocations. |
| Unit | CrossRepoPusher: Pydantic validation (review code-reviewer I6 / python-pro #4 / mcp-integration-expert Critical #1). Valid payload → row stored; missing conversation_id → error returned; empty repos array → error; wrong kind enum → error; `WorkEntry(kind="commit")` without sha → error; `WorkEntry(kind="plan_ref")` without plan_path → error; unknown field → `extra="forbid"` rejection. |
| Unit | CrossRepoPusher: auth contract (review mcp-integration-expert Critical #7). Caller without `Permission.WRITE` → 403-shaped result; valid auth → stored. |
| Unit | Merge logic: idempotency on (conversation_id, repo_name, sha) (review code-reviewer C1 / database-ops Critical #2). Same sha pushed twice in same session → only 1 entry in work_entries. Ambient + explicit same sha → deduped, with `provenance="explicit"` preferred. Different shas from same repo → 2 entries. Test the full SQL merge inside `BEGIN IMMEDIATE` transaction with mocked DuckDB. |
| Unit | Merge logic: `contributor_sources` union. Ambient + explicit → `["ambient", "explicit"]` (order-preserving set). |
| Unit | HandoffLink.render_section. Session with 3 repos → 3-bullet markdown. Session with 0 cross_repo_work rows → `_No cross-repo work captured._` line (review resilience C7). Render failure → `> Cross-Repo Work could not be captured: <reason>. See <log_ref>.` sentinel. Renders within 50ms for typical workload; stress test with 500 rows asserts ≤200ms (review architect M2). |
| Unit | Session identity (review python-pro C2). Two consecutive checkpoints in the same session share the conversation_id; second checkpoint's ambient window still catches commits from before the second checkpoint. |
| Integration | End-to-end checkpoint with sibling repo. Temp dir setup with 2 sibling git repos. Make commits in each during a "session". Run session-buddy checkpoint. Verify 3 cross_repo_work rows (1 for working_directory via local path, 1 for sibling #1 ambient, 1 for sibling #2 ambient). Verify handoff doc includes "Cross-Repo Work" section. |
| Integration | Mahavishnu push simulation. Mock mcp client. Call store_cross_repo_work with realistic payload. Verify row stored + idempotency on second call + auth gate honored + multi-repo batch atomicity (one transaction, all-or-nothing). |
| Integration | EventBridge alignment smoke (review trend-analyst C1). Wire a fake EventBridge subscriber alongside `cross_repo_work_v2` writes; verify both surfaces receive the row's `work_entries` (no real EventBridge yet — verify the adapter interface supports it). |
| Manual | Wave-1 checkpoint in real session-buddy against sibling mahavishnu repo. |

## Migration / backfill

- New table `cross_repo_work_v2` is additive; no existing tables changed.
- Existing checkpoints unaffected (no backfill).
- `settings/ecosystem.yaml` is gitignored; ships empty initially.
- `scripts/bootstrap_ecosystem_manifest.py` reads mahavishnu's `repos.yaml` on first run and generates the file.

## Out of scope (deferred)

- Routing decisions in mahavishnu that consume cross-repo state — when those land, they'll read from EventBridge (primary) and `cross_repo_work_v2` (fallback), per §Convergence-plan alignment.
- Trigger follow-ups via `broadcast_repository_message`.
- Per-task attribution finer than git commits.
- Cross-repo identifier registry (`ext:<id>`); git SHAs serve as canonical work IDs for now.
- EventBridge publishers for the rest of the 26 Bodai repos (mahavishnu/akosha/crackerjack/dhara publishers are scheduled for Phase 6.2a/6.2b).
- Migration story for when EventBridge publishers land (open question in §Convergence-plan alignment — the implementation plan will pick one of (a)/(b)/(c)).

## References

- **Existing write pattern (corrected):** the spec's earlier reference to `session_buddy/mcp/tools/code_graph.py::store_code_graph_from_mahavishnu` is the read-side search facade, not the writer. The actual writer pattern lives in `session_buddy/subscribers/code_graph_subscriber.py:265-337` and `session_buddy/reflection/storage.py:457-533` — both are the worked examples for the new CrossRepoPusher. (Review mcp-integration-expert Important #6.)
- Mahavishnu manifest: `mahavishnu/settings/repos.yaml` — 26 Bodai repos with role/tags.
- p7-cross-repo-playbook: `session-buddy/docs/plans/2026-07-16-p7-cross-repo-playbook.md:309` — open question about cross-repo `superseded_by` chain IDs (related but distinct from this work).
- Routing guide: `mahavishnu/docs/ROUTING_GUIDE.md:83-84` — deferred Phase 6B publishers (same class of cross-repo work).
- Ecosystem status surface: `mahavishnu/mcp/tools/coordination_tools.py:coord_get_ecosystem_status` — possible consumer for future routing.
- Bodai Observability Pattern: `.claude/decisions/bodai-observability-pattern.md` — establishes EventBridge as the canonical live-activity surface; `cross_repo_work_v2` is the pre-EventBridge materialization (see §Convergence-plan alignment).
- Auth decorators: `mcp-common/mcp_common/auth/decorator.py` — `@require_auth()` and `Permission.WRITE` for the CrossRepoPusher (review mcp-integration-expert Critical #7).
- Existing session tracker reference: `session_buddy/mcp/tools/session/admin_shell_tracking_tools.py:147-262` and `session_buddy/mcp/tools/session/channel_tracking_tools.py:224-337` — the new tool's `@require_auth()` precedent.
- MCP registration surface: `session_buddy/mcp/tools/__init__.py`, `session_buddy/mcp/server.py:40-153`, `session_buddy/mcp/tools/profiles.py:42-76` — `_ALL_REGISTERS` and `STANDARD` profile wiring for the new tool (review mcp-integration-expert Critical #6).

---

## Spec self-review checklist

- [x] **Placeholder scan**: No TBD/TODO/"add appropriate". All scripts and code blocks are concrete.
- [x] **Internal consistency**: Architecture diagram matches component list; data flow matches schema; error table covers the named failure modes.
- [x] **Scope check**: Single-implementation plan scope (CheckpointCrossRepoAccountant + AmbientPuller + CrossRepoPusher + HandoffLink + schema migration + ecosystem.yaml + bootstrap script). Out-of-scope items called out explicitly.
- [x] **Ambiguity check**: "session_window" is concrete (session_start to now); "idempotent on (conversation_id, repo_name, sha)" is precise (and the merge primitive enforces it, not the schema); "NEVER breaks the checkpoint" is a hard principle.
- [x] **Skill compliance**: Reuses existing `subscribers/code_graph_subscriber.py` writer pattern (NOT the read-side facade that the original spec cited); respects Bodai pre-1.0 ff-merge policy (no PRs); respects crackerjack-compliant-code conventions (per latest CLAUDE.md).
- [x] **External alignment (review trend-analyst M2)**:
  - Convergence plan ownership: §Convergence-plan alignment names `cross_repo_work_v2` as a pre-EventBridge materialization with explicit roadmap position.
  - EventBridge envelope compatibility: `correlation_id`/`causation_id` per-entry fields added to §Schema so future consumers don't need a v3 migration.
  - `ext:<id>` registry decision: deferred (out of scope).
  - Phase 6B publisher roadmap: mahavishnu/akosha/crackerjack publishers are scheduled for 6.2a/6.2b; not in scope here.
  - Mahavishnu `coord_get_ecosystem_status` consumer shape: listed in References; future routing consumers will read EventBridge primarily.
- [x] **Multi-agent review applied (this revision)**: 9 convergent Criticals + EventBridge addendum from 7-agent review incorporated. Late-arriving mcp-integration-expert review added registration/auth/request-response contracts.