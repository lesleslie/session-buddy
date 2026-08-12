---
status: active
role: canonical
date: 2026-08-10
last_reviewed: 2026-08-10
topic: cross-repo-work-vs-eventbridge
---

# Cross-Repo Work (`cross_repo_work_v2`) vs EventBridge

One-line summary: session-buddy's `cross_repo_work_v2` table (checkpoint-time mirror) and a future EventBridge stream (push-time fan-out) are complementary, not competitive; we keep both and route distinct consumers to each.

## Background

The cross-repo-checkpoint-accounting plan added two write paths into `cross_repo_work_v2`:

1. **Active pull path** (Task 11c) — `SessionLifecycleManager.checkpoint_session` invokes `CheckpointCrossRepoAccountant.capture()` after git commit, before POST_CHECKPOINT hooks. Reads `session_windows.started_at` for G7 consistency.
2. **Explicit push path** (Task 8) — `store_cross_repo_work` MCP tool, called by external agents/CLIs that want to record work outside a checkpoint cycle.

mahavishnu I1 raised the question: does `cross_repo_work_v2` overlap with the planned EventBridge stream (push-based fan-out for downstream consumers)?

## Decision

**Keep both.** `cross_repo_work_v2` is the **checkpoint-time mirror** (durable, queryable, batch-shaped rows tied to `conversation_id` + `session_window_start`/`end`). EventBridge (when it lands) will be the **push-time fan-out** (low-latency, ephemeral, event-shaped messages).

The two serve different consumers:

| Consumer | Best fit |
|----------|----------|
| Handoff docs, audit reports, dashboard snapshots, weekly summaries | `cross_repo_work_v2` (checkpoint-time mirror) |
| Real-time alerts, external webhook integrations, ML feature freshness | EventBridge (push-time fan-out) |

Same underlying events, different shapes, different SLAs. Routing at write time: the pull path writes only to `cross_repo_work_v2`; the push path writes only to EventBridge. Neither path duplicates the other's row/event.

## Decision rule

1. **Don't add an EventBridge write to the checkpoint pull path.** The pull path's G6 contract is "never break the checkpoint" — adding a network call to a fan-out service violates that contract.
2. **Don't backfill `cross_repo_work_v2` from EventBridge.** The mirror is the source of truth for checkpoint-time state; reconciliation via backfill risks diverging from `session_windows.started_at`.
3. **When EventBridge lands, expose a separate consumer tool** (`subscribe_cross_repo_work` or similar) that does NOT touch `cross_repo_work_v2`. The two are siblings, not parent/child.
4. **If a future use case needs both real-time AND queryable**, write to both from the *producer* (e.g. an MCP pusher that wants its push to be queryable) — but the producer chooses, not a downstream consumer.

## Status

`active` — adopted 2026-08-10. Revisit when EventBridge ships (mahavishnu I1 follow-up).

## Related

- Plan: `docs/superpowers/plans/2026-08-05-cross-repo-checkpoint-accounting.md`
- Spec: `docs/superpowers/specs/2026-08-05-cross-repo-checkpoint-accounting-design.md`
- Feature tracking: `docs/feature-tracking/2026-08-05-cross-repo-checkpoint-accounting.md` (now `adopted`)
- Completion report: `docs/archive/completion-reports/2026-08-05-cross-repo-checkpoint-accounting.md`
- mahavishnu I1 (EventBridge): tracked separately
