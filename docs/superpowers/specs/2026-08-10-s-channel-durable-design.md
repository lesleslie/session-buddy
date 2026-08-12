---
status: draft
date: 2026-08-10
last_reviewed: 2026-08-10
role: canonical
topic: s-channel-durable
entity: channel_session_state
owner_repo: session-buddy
subscribes_to: dhara.schema.channel_session_state
---

# S-CHANNEL-DURABLE Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `channel_session_state` typed schema (from `dhara.schema`) into session-buddy's `_ChannelSessionStore`. Replace in-memory state with durable structured records. Both producer (validate-on-write on session start/heartbeat/end events) and consumer (read-back-and-validate via `channel_session_get_state` MCP tool) sides wired.

**Architecture:** Producer module sits in `session_buddy/channel/state_writer.py`; imports `ChannelSessionState` from `dhara.schema`, validates via `validate("channel_session_state", payload)` from `SCHEMA_REGISTRY`, persists via existing `_ChannelSessionStore` (which gains Dhara backend per S-CHANNEL-DURABLE-DHARMA dependency). Consumer module sits in `session_buddy/mcp_tools/channel_tools.py` as a new `channel_session_get_state(channel_id, sender_id)` MCP tool; reads back via `from_dict` and returns validated struct.

**Tech Stack:** Python 3.13, msgspec.Struct (substrate), Dhara + FastMCP (existing), pytest-asyncio, no new third-party deps.

## Integration Contract

- **Triggered from:** `session_buddy.track_channel_session(event_type, channel_id, sender_id, ...)` (existing function called on every channel event; modified to call state_writer)
- **Returns to / updates:** `_ChannelSessionStore` durable backend (Dhara-backed key namespace `channel-sessions/{channel_id}/{sender_id}/{event_id}/`)
- **Demonstrable by:** pytest `tests/unit/channel/test_state_writer.py::test_track_emits_validated_struct` + smoke `pytest tests/integration/test_channel_session_state_wiring.py::test_round_trip`
- **Rollback signal:** feature flag `S_CHANNEL_DURABLE_V1_ENABLED=False`; state_writer is a no-op (in-memory fallback restored)
- **Observability added:** counter `channel_session_state_recorded_total{event_type}` (start/heartbeat/end) + counter `channel_session_state_invalid_total{reason}` (validation_error, schema_drift)

## Tasks (Sketch)

1. Import `ChannelSessionState` from `dhara.schema` + producer module `state_writer.py` + tests (RED-first)
2. Consumer-side MCP tool `channel_session_get_state` + tests (RED-first)
3. Wire producer into `track_channel_session` event handlers (start/heartbeat/end)
4. Round-trip integration test (durable across process restart)
5. Crackerjack gate + completion report

## Open questions

None.
