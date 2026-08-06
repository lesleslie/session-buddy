# Cross-Repo Work Accounting in Checkpoint — Design

> **For agentic workers:** This spec captures the design for cross-repo work accounting in session-buddy checkpoints. The implementation plan will follow in a separate document under `docs/superpowers/plans/`.

**Date:** 2026-08-05
**Status:** Draft v1
**Author:** Claude (per user brainstorming)
**Brainstorm:** `superpowers:brainstorming`

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
- **G2**: Other Bodai repos can explicitly push cross-repo work entries (commits, plan refs, blockers, test runs) into the checkpoint via an MCP write.
- **G3**: The handoff doc includes a "Cross-Repo Work" section listing per-repo activity.
- **G4**: Existing checkpoint behavior is preserved (no breaking changes to existing callers).
- **G5**: Storage is idempotent on `(session_id, repo_name, sha)` — duplicate pushes are deduped.
- **G6**: Cross-repo accounting failures NEVER break the checkpoint. They're observational metadata; the actual git commit / handoff doc must proceed even if ambient-pull or explicit-push fails.

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
│       │       - git log --since session_start │   │ - writes cross_repo_work v2 row   │
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
- Single public method: `capture(working_directory: Path, session_id: str) -> CrossRepoCaptureSummary`
- Coordinates AmbientPuller + existing pushed rows + merge + write to `cross_repo_work_v2`.
- Never raises. Returns a summary `{repos_captured: int, ambient_failures: list[str], explicit_count: int}` for the checkpoint log.

### NEW: `AmbientPuller`

- Location: `session_buddy/core/checkpoint/ambient_puller.py`
- Reads `settings/ecosystem.yaml` (a new session-buddy-side manifest cache modeled on mahavishnu's `repos.yaml`).
- For each non-local sibling repo: `git log --since <session_start> --until <now> --format=%H%x09%s%x09%an%x09%aI -- <repo_path>`.
- Returns `list[WorkEntry]` keyed by `repo_name`.
- Never raises; per-repo failures are logged + the repo is skipped.

### NEW: `CrossRepoPusher` (MCP tool)

- Location: `session_buddy/mcp/tools/cross_repo_work.py`
- Registers: `mcp__session-buddy__store_cross_repo_work(session_id: str, repos: list[RepoWorkEntry]) -> CrossRepoStoreResult`
- Pydantic validation: rejects malformed payloads with 4xx-shaped error (existing pattern).
- Idempotency: re-pushing same `(session_id, repo_name, sha)` is a no-op.

### NEW: `HandoffLink` (consumer in `core/lifecycle/handoff.py`)

- Reads `cross_repo_work_v2` rows for the current session.
- Renders "## Cross-Repo Work" section between "Quality" and "Recovery" in the handoff markdown.
- Per-repo bullets: `repo_name (role): N commits since <start>` + first 5 commit SHAs (7-char) + subjects.

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
mcp__session-buddy__store_cross_repo_work(session_id, repos=[...])
   │
   ▼
[CrossRepoPusher validates + writes to cross_repo_work_v2]

[Session-buddy's own checkpoint workflow]
   │
   ▼
SessionLifecycleManager.checkpoint_session(working_directory)
   │
   ▼
CheckpointCrossRepoAccountant.capture(working_directory, session_id)
   │
   ├─▶ AmbientPuller.run(working_directory, session_id, session_window)
   │     │
   │     ├─ Read settings/ecosystem.yaml (sibling repos)
   │     ├─ For each non-local repo:
   │     │     ├─ Skip if not a git repo (graceful)
   │     │     ├─ git log --since session_start --until now
   │     │     └─ Capture: {sha, subject, files_changed_count, author, timestamp}
   │     └─ Returns list of repos with work entries
   │
   ├─▶ Merge with explicit-pushed entries (idempotent on (session_id, repo_name, sha))
   │
   └─▶ Write merged result to cross_repo_work_v2

[Read path: handoff]
   │
   ▼
HandoffLink.render_section(session_id, handoff_context)
   │
   ├─ Read cross_repo_work rows for session_id
   ├─ Group by repo_name
   ├─ Render markdown section
   └─ Return for inclusion in handoff
```

**Lifecycle properties:**

- **Idempotent on `(session_id, repo_name, sha)`**: re-running checkpoint won't duplicate commits.
- **Per-session window**: `session_start = first checkpoint_session invocation; session_window = session_start..now`.
- **No hot path**: ambient pull adds ~50-200ms per sibling repo (git log is fast); explicit push is just an MCP write.
- **Failures**: AmbientPuller failures are logged + the repo is skipped, NOT fatal. Explicit push failures return error to caller.

## Schema

```sql
-- New v2 reflection table. Modeled on session_buddy/reflection/database.py:v2 schema style.
CREATE TABLE cross_repo_work_v2 (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,                    -- FK to conversations_v2.session_id
    repo_name       TEXT NOT NULL,                    -- e.g. "mahavishnu"
    repo_path       TEXT NOT NULL,                    -- absolute path on disk
    repo_role       TEXT,                            -- e.g. "orchestrator", "quality" — from ecosystem.yaml
    captured_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    session_window_start  TIMESTAMP WITH TIME ZONE NOT NULL,
    session_window_end    TIMESTAMP WITH TIME ZONE NOT NULL,
    work_entries    JSON NOT NULL,                   -- see shape below
    source          TEXT NOT NULL CHECK (source IN ('ambient', 'explicit', 'merged')),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, repo_name)                   -- one row per (session, repo); work_entries accumulates
);

-- work_entries JSON shape:
[
  {
    "kind": "commit",                          -- extensible: 'commit' | 'pr' | 'test_run' | 'plan_ref' | 'blocker'
    "sha": "abc123def456...",                   -- git SHA (canonical ID for commits/PRs)
    "subject": "feat(mahavishnu): wire pool routing",
    "files_changed_count": 3,
    "author": "les <les@...",
    "timestamp": "2026-08-05T01:23:45Z"
  },
  {
    "kind": "plan_ref",
    "plan_path": "docs/superpowers/plans/2026-08-05-foo.md",
    "phase": "phase-1"
  }
]
```

**Pydantic mirror in `session_buddy/memory/cross_repo_work.py`:**

```python
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

class WorkEntry(BaseModel):
    kind: Literal["commit", "pr", "test_run", "plan_ref", "blocker"]
    sha: str | None = None
    subject: str | None = None
    files_changed_count: int | None = None
    author: str | None = None
    timestamp: datetime | None = None
    # Extensible:
    plan_path: str | None = None
    phase: str | None = None

class CrossRepoWorkRow(BaseModel):
    id: str
    session_id: str
    repo_name: str
    repo_path: str
    repo_role: str | None = None
    captured_at: datetime
    session_window_start: datetime
    session_window_end: datetime
    work_entries: list[WorkEntry]
    source: Literal["ambient", "explicit", "merged"]
    created_at: datetime
    updated_at: datetime
```

## Error handling

| Failure mode | Behavior |
|---|---|
| `settings/ecosystem.yaml` missing | AmbientPuller skips pull entirely; logs INFO; checkpoint continues normally. (No ambient, but explicit push still works.) |
| `settings/ecosystem.yaml` present but malformed | Skip ambient + emit WARNING to checkpoint log; do NOT raise (don't break checkpoint on bad config). |
| Sibling repo path not a git repo | Skip that repo; emit DEBUG; continue with others. |
| `git log` on sibling fails (timeout, permission, etc.) | Skip that repo; emit ERROR to checkpoint log; continue. |
| Explicit push with malformed payload | Return 4xx-shaped error to caller (existing pattern). Log WARNING; do not store. |
| Explicit push with `session_id` that doesn't exist | Return error "session not found"; no store. |
| Storage write fails (DuckDB lock) | Retry 3x with backoff; surface as part of checkpoint failure (existing pattern). |
| HandoffLink.render_section fails | Log ERROR; handoff doc still written without cross-repo section. (Degrade, not fail.) |

**General principle: cross-repo accounting NEVER breaks the checkpoint.** It's observational metadata; a failure to capture it should not block the actual git commit / handoff doc.

## Testing

| Layer | Test |
|---|---|
| Unit | AmbientPuller: with fixtures for ecosystem.yaml (empty, malformed, 3-repo config). Verifies: empty → INFO skip, no rows written; malformed → WARNING skip; 3-repo → 3 ambient-pull invocations, 3 rows. |
| Unit | CrossRepoPusher: Pydantic validation. Valid payload → row stored; missing session_id → error returned; empty repos array → 4xx error; wrong kind enum → 4xx error. |
| Unit | Merge logic: idempotency on (session_id, repo_name, sha). Same sha pushed twice in same session → only 1 entry in work_entries. Ambient + explicit same sha → deduped. Different shas from same repo → 2 entries. |
| Unit | HandoffLink.render_section. Session with 3 repos → 3-bullet markdown. Session with 0 cross_repo_work rows → "No cross-repo work recorded" line. Renders within 50ms for typical workload. |
| Integration | End-to-end checkpoint with sibling repo. Temp dir setup with 2 sibling git repos. Make commits in each during a "session". Run session-buddy checkpoint. Verify 3 cross_repo_work rows (1 for working_directory, 1 for sibling #1 ambient, 1 for sibling #2 ambient). Verify handoff doc includes "Cross-Repo Work" section. |
| Integration | Mahavishnu push simulation. Mock mcp client. Call store_cross_repo_work with realistic payload. Verify row stored + idempotency on second call. |
| Manual | Wave-1 checkpoint in real session-buddy against sibling mahavishnu repo. |

## Migration / backfill

- New table `cross_repo_work_v2` is additive; no existing tables changed.
- Existing checkpoints unaffected (no backfill).
- `settings/ecosystem.yaml` is gitignored; ships empty initially.
- `scripts/bootstrap_ecosystem_manifest.py` reads mahavishnu's `repos.yaml` on first run and generates the file.

## Out of scope (deferred)

- Routing decisions in mahavishnu that consume cross-repo state.
- Trigger follow-ups via `broadcast_repository_message`.
- Per-task attribution finer than git commits.
- Cross-repo identifier registry (`ext:<id>`); git SHAs serve as canonical work IDs for now.

## References

- Existing pattern: `session_buddy/mcp/tools/code_graph.py::store_code_graph_from_mahavishnu` — same shape (per-repo data attributed to specific other repo).
- Mahavishnu manifest: `mahavishnu/settings/repos.yaml` — 26 Bodai repos with role/tags.
- p7-cross-repo-playbook: `session-buddy/docs/plans/2026-07-16-p7-cross-repo-playbook.md:309` — open question about cross-repo `superseded_by` chain IDs (related but distinct from this work).
- Routing guide: `mahavishnu/docs/ROUTING_GUIDE.md:83-84` — deferred Phase 6B publishers (same class of cross-repo work).
- Ecosystem status surface: `mahavishnu/mcp/tools/coordination_tools.py:coord_get_ecosystem_status` — possible consumer for future routing.

---

## Spec self-review checklist

- [x] **Placeholder scan**: No TBD/TODO/"add appropriate". All scripts and code blocks are concrete.
- [x] **Internal consistency**: Architecture diagram matches component list; data flow matches schema; error table covers the named failure modes.
- [x] **Scope check**: Single-implementation plan scope (CheckpointCrossRepoAccountant + AmbientPuller + CrossRepoPusher + HandoffLink + schema migration + ecosystem.yaml + bootstrap script). Out-of-scope items called out explicitly.
- [x] **Ambiguity check**: "session_window" is concrete (session_start to now); "idempotent on (session_id, repo_name, sha)" is precise; "NEVER breaks the checkpoint" is a hard principle.
- [x] **Skill compliance**: Reuses existing `store_code_graph_from_mahavishnu` pattern; respects Bodai pre-1.0 ff-merge policy (no PRs); respects crackerjack-compliant-code conventions (per latest CLAUDE.md).