---
feature: s-channel-durable
status: built
created: 2026-08-10
last_updated: 2026-10-30
adopted_at: 2026-08-10
state_history:
  - "2026-08-10: adopted (initial v1 ship — Task 4 cross-process test)"
  - "2026-08-10: built (multi-agent review surfaced 3 Critical findings: consumer not registered, flag is constant, producer resolves substrate at import time)"
  - "2026-08-10: built (v1.1 fix cycle complete — C2 + C3 fixed in commit 109b1d98; C1 closed via consumer deletion in commit 7b5c746a because the function had zero canonical-MCP callers)"
  - "2026-08-11: built (consumer restored as channel_session_get_state_tool under session_buddy/mcp/tools/session/)"
  - "2026-10-11: built (Phase 5 of the UUID7 migration retired the external substrate: the schema moved to session_buddy/channel/_models.py, the substrate-compat shim was deleted, and persistence became a no-op until a replacement substrate is wired)"
  - "2026-10-30: built (documentation pass — external substrate references generalized to 'substrate'; no behaviour change)"
---

# S-CHANNEL-DURABLE: Channel Session State Durability

## Built (corrected)
- `ChannelSessionState` schema in `session_buddy/channel/_models.py` (Task 1) — survives review. It is a session-buddy-local `msgspec.Struct` that mirrors the original substrate schema field-for-field; the entity type moved off the external substrate schema in Phase 8 Task 7 of the UUID7 migration.
- `record_channel_session_state` producer in `session_buddy/channel/state_writer.py` (Task 1) — **v1.1 fixes landed in commit 109b1d98**:
  - (a) Import-time substrate-client snapshot replaced with `hasattr` stamp + call-time `getattr(substrate, "put", None)` gate (mirrors consumer's correct pattern). *(The shim itself was removed 2026-10-11 — see "Phase 5 supersession" below.)*
  - (b) Module constant `S_CHANNEL_DURABLE_V1_ENABLED` replaced with `_channel_session_state_v1_enabled()` env-var helper reading `CHANNEL_SESSION_STATE_V1_ENABLED` (default `'true'`); flag check moved to call site in `channel_tracking_tools.py:track_channel_session`.
- `channel_session_get_state` consumer — **RESTORED in commit f18b71dd under canonical MCP path** (`session_buddy/mcp/tools/session/channel_session_state_tools.py`). Round-trip is now demonstrable via `test_channel_session_state_round_trip`. Mirrors the producer's substrate-compat pattern (call-time `getattr(substrate, "get", None)` gate) and the G6 contract (swallow substrate failures, return `None`, log WARNING).
- Wiring: `track_channel_session` MCP tool invokes the producer on every `start`/`heartbeat`/`end` event (Task 3) — survives review.

## Wired (no — flipped to `built`)
Original `wired` claim was overstated. Three Critical findings from the 2026-08-10 multi-agent review:

1. **C1 — Consumer is dead code.** `channel_session_get_state` was a bare module-level function in `session_buddy/mcp_tools/channel_tools.py`; no `@mcp.tool()` decorator, no FastMCP registration. The package was entirely disconnected from `session_buddy/mcp/`. **Resolution:** deleted the orphan package and its test mirror. C1 is closed by removal rather than re-registration; see follow-up if restoration is later needed.
2. **C2 — Feature flag was a module constant, not an env var.** Spec calls for `CHANNEL_SESSION_STATE_V1_ENABLED`; actual was hard-coded `S_CHANNEL_DURABLE_V1_ENABLED: bool = True`. **Resolution:** env-var helper + call-site gate at `channel_tracking_tools.py:track_channel_session`. Operational rollback lever now exists.
3. **C3 — Producer resolved the substrate client's `put` at import time.** **Resolution:** replaced with `hasattr` stamp + call-time `getattr(substrate, "put", None)` gate (mirrors the consumer's correct pattern).

All three findings closed in the v1.1 hardening cycle.

## Adopted (no — was overstated, partial restoration since)
The original `adopted` claim cited a cross-process durability test against a dict-backed substrate. A shared in-process dict cannot demonstrate cross-process durability. The producer half is pinned (no-trailing-slash key shape, payload validation, struct reconstruction) and the round-trip is now demonstrable via `test_channel_session_state_round_trip` (in-process, shared-dict substrate). True cross-process durability still awaits a wired durable substrate.

Cross-portfolio pattern drift (compared against M-APPROVAL-LOG and M-WORKFLOW-OUTCOME in mahavishnu):

| Dimension | M-APPROVAL-LOG / M-WORKFLOW-OUTCOME | S-CHANNEL-DURABLE |
|---|---|---|
| Key format | `approval-history/{id}/`, `workflow-results/{id}/` (trailing slash) | `channel-sessions/{cid}/{sid}` (no trailing slash, pinned by test) |
| Substrate gate | `hasattr` stamp + call-time `getattr` on both halves | Producer: correct (v1.1). Consumer: deleted. |
| Feature flag | Env-var gated at the call site | Env-var gated at the call site (v1.1) |
| Consumer registration | Registered MCP tools | N/A — consumer deleted |
| Package placement | Consumer inside the MCP tool tree | Consumer was in a parallel `session_buddy/mcp_tools/` package; now gone |

### Phase 5 supersession (2026-10-11)

Phase 5 of the UUID7-only migration plan retired the external substrate:

- The `ChannelSessionState` schema is now session-buddy-local (`session_buddy/channel/_models.py`); there is no external schema package to import.
- The substrate-compat shim (`hasattr` stamp + call-time `getattr(substrate, ...)` gate) was deleted in the same phase.
- Persistence is a **no-op**: the producer validates the payload, increments the `attempted`/`skipped` counters, and logs `channel_session_state_persistence_skipped` with reason `no_substrate_wired_post_phase5`. The consumer tool always returns `None`.

The key shape `channel-sessions/{channel_id}/{sender_id}` (no trailing slash) remains the documented convention so producers can align when a replacement substrate is wired — it is no longer observed at runtime.

## Integration Contract
- Triggered from: `track_channel_session` MCP tool on `channel_session_start`, `channel_heartbeat`, `channel_session_end`.
- Returns to: `channel-sessions/{channel_id}/{sender_id}` in the durable substrate (no-op until a replacement substrate is wired — see "Phase 5 supersession").
- Demonstrable by: `tests/integration/channel/test_durable_restart.py::test_channel_session_state_validates_payload_post_phase5` (producer half only) and `tests/unit/channel/test_models.py::test_channel_session_state_roundtrip_matches_substrate_shape` (schema round-trip).
- Rollback signal: `CHANNEL_SESSION_STATE_V1_ENABLED=false` short-circuits the producer at the call site — no validation, no persistence, no side effects.
- Observability: substrate failures are logged at WARNING level (G6 contract); structured counters deferred.

## Pre-existing issues (not addressed — out of scope)
- 12+ files in the working tree carry pre-existing changes from the auto-checkpoint-safety-and-trigger branch.
- **Resolved 2026-10-11 (Phase 5).** The external substrate schema package is no longer a dependency: the schema is local, the integration test module no longer skips via `pytest.importorskip`, and there is no version pin to bump.
- **Resolved 2026-10-11 (Phase 5).** The substrate-compat path is gone entirely — persistence is a no-op and the shared-dict substrate in `test_durable_restart.py` is no longer the demonstrable-by contract. The current contract is the Phase 5 no-op pinned by `test_channel_session_state_validates_payload_post_phase5`.

## Open follow-ups
- Wire a real durable substrate backend so the test exercises true cross-process persistence (currently the producer is a validate-only no-op).
- RBAC: gate consumer reads to authorized senders / channels (consumer is restored, RBAC is not yet enforced).
- Sink-arg tightening: pass metadata through a typed schema instead of `dict[str, Any]`.
- Observability counters: success/failure-per-channel, p99 write latency.
