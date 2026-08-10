---
feature: cross-repo-checkpoint-accounting
status: adopted
created: 2026-08-05
last_updated: 2026-08-10
adopted_at: 2026-08-10
---

# Cross-Repo Work Accounting in Checkpoint

## Built
- `session_windows` + `cross_repo_work_v2` schema + migration registered (this task, v2.1).

## Wired (yes)
- `CheckpointCrossRepoAccountant.capture()` invoked from `session_manager.checkpoint_session` (Task 11c).
- `HandoffLink.render_section()` injected into `_generate_handoff_documentation` (Task 11b).
- `store_cross_repo_work` MCP tool registered via `register_cross_repo_work_tools` in `STANDARD_REGISTRATIONS` (Task 8/9).

## Adopted (yes — Task 13, 2026-08-10)
- First wave-1 checkpoint produces "## Cross-Repo Work" section in handoff doc.
- Gate: PASS_WITH_KNOWN_GATE_DEBT (18 ruff UP017/RUF100/EXE001 parked; 9 pre-existing ruff issues in non-plan files).
- Orphan audit: zero plan-introduced orphans.
- e2e test (Task 12) green: 1 test, 5.87s, exercises full pipeline.

## Open follow-ups
- `bind_conversation` MCP tool for cross-pusher conversation_id discovery (mahavishnu C2)
- Cross-MCP auth identity ADR (mahavishnu C3)
- STANDARD profile gating CI guard (mahavishnu I3)
- EventBridge sibling for push-time fan-out (see `.claude/decisions/cross-repo-work-vs-eventbridge.md`)
- Ruff cleanup wave for plan-introduced stylistic issues
