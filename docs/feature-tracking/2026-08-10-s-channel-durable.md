---
feature: s-channel-durable
status: adopted
created: 2026-08-10
last_updated: 2026-08-10
adopted_at: 2026-08-10
---

# S-CHANNEL-DURABLE: Channel Session State Durability

## Built
- `ChannelSessionState` schema in `dhara/schema/channel_session_state.py` (Task 1).
- `record_channel_session_state` producer in `session_buddy/channel/state_writer.py` (Task 1) — validates, persists, swallows substrate failures (G6 contract).
- `channel_session_get_state` consumer in `session_buddy/mcp_tools/channel_tools.py` (Task 2) — reads back via `from_dict`, returns `None` on missing backend or missing key.
- Wiring: `track_channel_session` MCP tool invokes the producer on every `start`/`heartbeat`/`end` event (Task 3).

## Wired (yes)
- `record_channel_session_state` invoked from `track_channel_session` in `session_buddy/mcp/tools/session/channel_tracking_tools.py` (Task 3).
- `channel_session_get_state` exposed as an MCP tool (Task 2).
- Producer/consumer persistence key contract pinned: `channel-sessions/{channel_id}/{sender_id}` (no trailing slash).
- `S_CHANNEL_DURABLE_V1_ENABLED` feature flag in `channel/state_writer.py` gates writes for instant rollback.

## Adopted (yes — Task 4, 2026-08-10)
- Cross-process durability test (Task 4) green: 2 tests, exercises producer ↔ consumer across a dict-backed substrate that survives across producer-A and consumer-B invocations.
- All channel-related tests pass: 13 tests across `tests/unit/channel/`, `tests/unit/mcp_tools/test_channel_tools.py`, `tests/integration/channel/`.
- Ruff lint clean on the new test file.
- Deferred security findings (RBAC, sink-arg tightening, observability counters) intentionally not addressed in this plan — documented as future work.

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
