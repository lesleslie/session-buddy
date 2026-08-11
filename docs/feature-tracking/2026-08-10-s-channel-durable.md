---
feature: s-channel-durable
status: built
created: 2026-08-10
last_updated: 2026-08-10
adopted_at: 2026-08-10
state_history:
  - "2026-08-10: adopted (initial v1 ship — Task 4 cross-process test)"
  - "2026-08-10: built (multi-agent review surfaced 3 Critical findings: consumer not registered, flag is constant, producer resolves substrate at import time)"
---

# S-CHANNEL-DURABLE: Channel Session State Durability

## Built (corrected)
- `ChannelSessionState` schema in `dhara/schema/channel_session_state.py` (Task 1) — survives review.
- `record_channel_session_state` producer in `session_buddy/channel/state_writer.py` (Task 1) — survives review with two v1 fixes pending: (a) `_dhara_put = getattr(dhara, "put", None)` snapshot at `state_writer.py:41` (import-time) must become `if not hasattr(dhara, "put"): dhara.put = None  # type: ignore[attr-defined]` plus call-time `getattr(dhara, "put", None)` gate — mirrors the consumer's correct pattern at `channel_tools.py:36-37`; (b) module-constant `S_CHANNEL_DURABLE_V1_ENABLED: bool = True` in `state_writer.py:31` must become env-var `CHANNEL_SESSION_STATE_V1_ENABLED` with a call-site gate — mirrors the `APPROVAL_LOG_V1_ENABLED` pattern in `mahavishnu/core/approval_manager.py:22-30`.
- `channel_session_get_state` consumer exists in `session_buddy/mcp_tools/channel_tools.py` (Task 2) — **NOT REACHABLE in production**: parallel-package bug (`session_buddy/mcp_tools/` was created next to the existing `session_buddy/mcp/tools/`, and the new package was never FastMCP-registered). Consumer must be moved into the real MCP tree and registered via `@mcp.tool()`.
- Wiring: `track_channel_session` MCP tool invokes the producer on every `start`/`heartbeat`/`end` event (Task 3) — survives review.

## Wired (no — flipped to `built`)
Original `wired` claim was overstated. Three Critical findings from the 2026-08-10 multi-agent review:

1. **C1 — Consumer is dead code.** `channel_session_get_state` is a bare module-level function; no `@mcp.tool()` decorator, no FastMCP registration. The package `session_buddy/mcp_tools/` is entirely disconnected from `session_buddy/mcp/`. Half the plan's read path was unreachable in production.
2. **C2 — Feature flag is a module constant, not an env var.** Spec calls for `CHANNEL_SESSION_STATE_V1_ENABLED`; actual is hard-coded `S_CHANNEL_DURABLE_V1_ENABLED: bool = True` in `state_writer.py:31`, with no `os.environ` read anywhere. There is no operational rollback lever.
3. **C3 — Producer resolves `dhara.put` at import time** (`_dhara_put = getattr(dhara, "put", None)` at module load). Producer and consumer resolve the substrate at different times (import vs call), risking silent disagreement on whether persistence is available.

Once all three land (target: v1.1 hardening cycle), flip back to `wired`.

## Adopted (no — was overstated)
The original `adopted` claim cited a cross-process durability test against a dict-backed substrate. A shared in-process dict cannot demonstrate cross-process durability. Combined with C1/C3, the evidence supporting `adopted` did not exist. Should be `wired` at most after the v1.1 fix cycle.

Cross-portfolio pattern drift (compared against M-APPROVAL-LOG and M-WORKFLOW-OUTCOME in mahavishnu):

| Dimension | M-APPROVAL-LOG / M-WORKFLOW-OUTCOME | S-CHANNEL-DURABLE |
|---|---|---|
| Key format | `approval-history/{id}/`, `workflow-results/{id}/` (trailing slash) | `channel-sessions/{cid}/{sid}` (no trailing slash, pinned by test) |
| Substrate gate | `hasattr` stamp + call-time `getattr` on both halves | Consumer: correct. Producer: import-time snapshot, no stamp |
| Feature flag | Env-var gated at the call site | Module constant checked inside the producer |
| Consumer registration | Registered MCP tools | Unregistered bare function in an orphan package |
| Package placement | Consumer inside the MCP tool tree | Consumer in a parallel `session_buddy/mcp_tools/` alongside the real `session_buddy/mcp/tools/` |

## Integration Contract
- Triggered from: `track_channel_session` MCP tool on `channel_session_start`, `channel_heartbeat`, `channel_session_end`.
- Returns to: `channel-sessions/{channel_id}/{sender_id}` in the dhara substrate.
- Demonstrable by: `tests/integration/channel/test_durable_restart.py::test_channel_session_state_survives_simulated_restart`.
- Rollback signal: `S_CHANNEL_DURABLE_V1_ENABLED = False` short-circuits the producer — no validation, no persistence, no side effects.
- Observability: substrate failures are logged at WARNING level (G6 contract); structured counters deferred.

## Pre-existing issues (not addressed — out of scope)
- 12 files in the working tree carry pre-existing changes from the auto-checkpoint-safety-and-trigger branch (Task 4 explicit constraint: do not resolve).
- dhara 0.14.0 ships without a wired persistence backend — substrate-compat path is always active in tests; the dict-backed substrate in `test_durable_restart.py` is the demonstrable-by contract, not a stand-in for a real backend.

## Open follow-ups
- Wire a real dhara backend so the test exercises true cross-process persistence (currently uses shared dict).
- RBAC: restrict `channel_session_get_state` reads to authorized senders / channels.
- Sink-arg tightening: pass metadata through a typed schema instead of `dict[str, Any]`.
- Observability counters: success/failure-per-channel, p99 write latency.
