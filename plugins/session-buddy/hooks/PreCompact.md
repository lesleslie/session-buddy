# Session-Buddy PreCompact Hook

Before context compaction, sync Session-Buddy state.

Calls `mcp__session_buddy__pre_compact_sync` to flush pending reflections
and ensure the reflection database is in a consistent state for compaction.

This hook is **non-blocking**: failures here do not stop compaction.
