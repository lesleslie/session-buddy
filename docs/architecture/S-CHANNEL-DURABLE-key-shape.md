# S-CHANNEL-DURABLE Substrate Key Shape

**Status:** Architectural decision (2026-08-10)
**Scope:** session-buddy only.

## Substrate key format

Channel-session records are persisted at:

```
channel-sessions/{channel_id}/{sender_id}
```

No trailing slash. The consumer's `get` call must use the same shape
(no trailing slash) for the lookup to succeed. The producer-half test
at `tests/integration/channel/test_durable_restart.py::test_channel_session_state_producer_emits_correct_key`
pins this key shape.

## Why no thread_id in the substrate key?

The in-memory store (`_ChannelSessionStore._key`) DOES include `thread_id`
because that's the full identity tuple for an active channel session
(distinguishes a Slack thread from the same user's main-channel session).

The substrate key omits `thread_id` because:

1. **Substrate index efficiency** — keys are bounded by `{channel_id, sender_id}`.
   thread_id can be long (Slack thread_ts is e.g. `1712345678.123456`) and
   unbounded across channels.
1. **Thread lives in payload** — `ChannelSessionState.metadata` already carries
   the active thread context (if any) via the producer's `metadata={...}`
   passthrough. Future thread-scoped reads can filter on metadata, not key.
1. **Multi-thread semantics** — a single `(channel_id, sender_id)` can have
   multiple active threads. Putting thread_id in the substrate key would
   either (a) fan out to multiple records (changes durability semantics) or
   (b) overwrite the main thread record on each thread event (data loss).
   Both options are worse than keeping thread_id in metadata.

## Consumer invariant

When `channel_session_get_state` is restored under the canonical MCP
path (see `docs/feature-tracking/2026-08-10-s-channel-durable.md`
follow-ups), its lookup will use the exact substrate key shape above
(no trailing slash) and return the `ChannelSessionState` struct (or
None if absent). Callers that need thread scoping must inspect
`record.metadata` after the fetch — the substrate key is NOT scoped
to thread.

## Trailing-slash policy

Producer writes the exact key above. Consumer reads the exact key above.
No trailing slash anywhere. If you find yourself adding a trailing slash
to either side, stop and re-read this document.

The M-APPROVAL-LOG and M-WORKFLOW-OUTCOME producers in mahavishnu use
trailing slashes (e.g. `approval-history/{id}/`); that convention is
intentional for those plans and does NOT transfer to S-CHANNEL-DURABLE.
The Bodai portfolio deliberately mixes both conventions per the
producer's intent — see
`dhara/docs/superpowers/specs/2026-08-10-substrate-call-boundary-contract.md`
for the broader substrate contract.
