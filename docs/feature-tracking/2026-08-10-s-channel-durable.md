---
feature: s-channel-durable
status: built
created: 2026-08-10
last_updated: 2026-08-10
adopted_at: 2026-08-10
state_history:
  - "2026-08-10: adopted (initial v1 ship — Task 4 cross-process test)"
  - "2026-08-10: built (multi-agent review surfaced 3 Critical findings: consumer not registered, flag is constant, producer resolves substrate at import time)"
  - "2026-08-10: built (v1.1 fix cycle complete — C2 + C3 fixed in commit 109b1d98; C1 closed via consumer deletion in commit 7b5c746a because the function had zero canonical-MCP callers)"
---

# S-CHANNEL-DURABLE: Channel Session State Durability

## Built (corrected)
- `ChannelSessionState` schema in `dhara/schema/channel_session_state.py` (Task 1) — survives review.
- `record_channel_session_state` producer in `session_buddy/channel/state_writer.py` (Task 1) — **v1.1 fixes landed in commit 109b1d98**:
  - (a) Import-time `_dhara_put` snapshot replaced with `hasattr` stamp + call-time `getattr(dhara, "put", None)` gate (mirrors consumer's correct pattern).
  - (b) Module constant `S_CHANNEL_DURABLE_V1_ENABLED` replaced with `_channel_session_state_v1_enabled()` env-var helper reading `CHANNEL_SESSION_STATE_V1_ENABLED` (default `'true'`); flag check moved to call site in `channel_tracking_tools.py:track_channel_session`.
- `channel_session_get_state` consumer — **DELETED in commit 7b5c746a** after discovery that the function had zero callers in the canonical MCP registry. The parallel-package hazard (C1) is closed; the read path is now an explicit non-goal until demand materializes. See "Open follow-ups" for the restoration path if a future caller needs it.
- Wiring: `track_channel_session` MCP tool invokes the producer on every `start`/`heartbeat`/`end` event (Task 3) — survives review.

## Wired (no — flipped to `built`)
Original `wired` claim was overstated. Three Critical findings from the 2026-08-10 multi-agent review:

1. **C1 — Consumer is dead code.** `channel_session_get_state` was a bare module-level function in `session_buddy/mcp_tools/channel_tools.py`; no `@mcp.tool()` decorator, no FastMCP registration. The package was entirely disconnected from `session_buddy/mcp/`. **Resolution:** deleted the orphan package and its test mirror. C1 is closed by removal rather than re-registration; see follow-up if restoration is later needed.
2. **C2 — Feature flag was a module constant, not an env var.** Spec calls for `CHANNEL_SESSION_STATE_V1_ENABLED`; actual was hard-coded `S_CHANNEL_DURABLE_V1_ENABLED: bool = True`. **Resolution:** env-var helper + call-site gate at `channel_tracking_tools.py:track_channel_session`. Operational rollback lever now exists.
3. **C3 — Producer resolved `dhara.put` at import time.** **Resolution:** replaced with `hasattr` stamp + call-time `getattr(dhara, "put", None)` gate (mirrors the consumer's correct pattern).

All three findings closed in the v1.1 hardening cycle.

## Adopted (no — was overstated)
The original `adopted` claim cited a cross-process durability test against a dict-backed substrate. A shared in-process dict cannot demonstrate cross-process durability. The producer half is now pinned (no-trailing-slash key shape, payload validation, struct reconstruction) but the round-trip assertion is gone with the consumer's deletion. The producer-only contract is demonstrable; the cross-process round-trip awaits both a wired dhara backend AND a decision on consumer restoration.

Cross-portfolio pattern drift (compared against M-APPROVAL-LOG and M-WORKFLOW-OUTCOME in mahavishnu):

| Dimension | M-APPROVAL-LOG / M-WORKFLOW-OUTCOME | S-CHANNEL-DURABLE |
|---|---|---|
| Key format | `approval-history/{id}/`, `workflow-results/{id}/` (trailing slash) | `channel-sessions/{cid}/{sid}` (no trailing slash, pinned by test) |
| Substrate gate | `hasattr` stamp + call-time `getattr` on both halves | Producer: correct (v1.1). Consumer: deleted. |
| Feature flag | Env-var gated at the call site | Env-var gated at the call site (v1.1) |
| Consumer registration | Registered MCP tools | N/A — consumer deleted |
| Package placement | Consumer inside the MCP tool tree | Consumer was in a parallel `session_buddy/mcp_tools/` package; now gone |

## Integration Contract
- Triggered from: `track_channel_session` MCP tool on `channel_session_start`, `channel_heartbeat`, `channel_session_end`.
- Returns to: `channel-sessions/{channel_id}/{sender_id}` in the dhara substrate.
- Demonstrable by: `tests/integration/channel/test_durable_restart.py::test_channel_session_state_producer_emits_correct_key` (producer half only). Module skips cleanly via `pytest.importorskip("dhara.schema", ...)` until session-buddy's pinned dhara version ships the schema package.
- Rollback signal: `CHANNEL_SESSION_STATE_V1_ENABLED=false` short-circuits the producer at the call site — no validation, no persistence, no side effects.
- Observability: substrate failures are logged at WARNING level (G6 contract); structured counters deferred.

## Pre-existing issues (not addressed — out of scope)
- 12+ files in the working tree carry pre-existing changes from the auto-checkpoint-safety-and-trigger branch.
- dhara pinned in session-buddy's lockfile predates D-OBJ-SCHEMA, so the integration test module skips via `pytest.importorskip`. Bumping the dhara dependency is tracked separately.
- dhara 0.14.0 ships without a wired persistence backend — substrate-compat path is always active in tests; the dict-backed substrate in `test_durable_restart.py` is the demonstrable-by contract for the producer half, not a stand-in for a real backend.

## Open follow-ups
- **Restore `channel_session_get_state` under canonical path** if a future MCP caller needs the read-back half. Restoration path: create `session_buddy/mcp/tools/session/channel_session_state_tools.py` with `@mcp.tool()` + `@require_auth()` registration mirroring `track_channel_session`; rewrite `test_durable_restart.py` round-trip assertions against the canonical import. Until then, reads via direct `dhara.list("channel-sessions/")` are sufficient.
- Wire a real dhara backend so the test exercises true cross-process persistence (currently uses shared dict).
- RBAC: when consumer is restored, gate reads to authorized senders / channels.
- Sink-arg tightening: pass metadata through a typed schema instead of `dict[str, Any]`.
- Observability counters: success/failure-per-channel, p99 write latency.

