# Subagent Lockfile — Stash-Clobber Producer/Consumer Story

## Purpose

The session-buddy checkpoint subsystem uses a per-working-tree lockfile
(`<working_dir>/.session-buddy/subagent.lock`) as a "subagent active" signal.
The **consumer** side (`SubagentDetector.is_active()` /
`wait_until_idle()`) is wired into `CheckpointPolicy` and
`CheckpointOrchestrator` and protects end-of-task checkpoints via fail-open →
True semantics. The **producer** side is what this document tracks.

## Producer/consumer split

| Side | Class | File | Function |
|---|---|---|---|
| Consumer | `SubagentDetector` | `session_buddy/checkpoint/subagent_detector.py` | `is_active()`, `wait_until_idle()` — fail-open on read errors |
| Consumer (low-level) | `LockfileSignalSource` | same file | `read()` — returns `True` when lockfile exists |
| **Producer** | `SubagentDetector` | same file | `write(active, metadata)` — atomic write-temp+rename |
| **Producer** (low-level) | `LockfileSignalSource` | same file | `write(active, payload)` — atomic JSON write when payload is supplied |
| **Lifecycle hook** | `DefaultSubagentLifecycleHook` | same file | `on_subagent_start()` / `on_subagent_end()` — wraps `SubagentDetector.write` |
| **Protocol** | `SubagentLifecycleHook` | same file | Implementable by Claude Code Task tool, Mahavishnu `PoolManager`, etc. |

## Three runtime paths

Runtime hooks (Claude Code Task tool wrappers, Mahavishnu
`PoolManager.worker_execute`, shell init scripts) can produce the lockfile
through any of three surfaces:

### 1. Python API

```python
from pathlib import Path
from session_buddy.checkpoint.subagent_detector import (
    LockfileSignalSource, SubagentDetector, SubagentMetadata,
)

wd = Path("/path/to/project")
lock = wd / ".session-buddy" / "subagent.lock"
detector = SubagentDetector(wd, LockfileSignalSource(lock))

# Mark active with explicit metadata
detector.write(
    active=True,
    metadata=SubagentMetadata(
        pid=os.getpid(),
        started_at_ms=int(time.time() * 1000),
        node_id="host-1",
        parent_agent_id="agent-2",
    ),
)

# Clear (no metadata needed)
detector.write(active=False)
```

When `metadata` is omitted, `SubagentDetector._default_metadata` constructs
the payload from `os.getpid()`, `time.time()`, and the
`SESSION_BUDDY_NODE_ID` / `SESSION_BUDDY_PARENT_AGENT_ID` env vars (falling
back to `socket.gethostname()` for `node_id`).

### 2. CLI

```bash
# Mark active (auto-generates metadata)
python -m session_buddy checkpoint subagent-marker \
    --action mark --working-dir /path/to/project

# Clear
python -m session_buddy checkpoint subagent-marker \
    --action clear --working-dir /path/to/project
```

The CLI is intended for shell scripts, init systems, and any other context
that can't import the Python API directly.

### 3. MCP tool

```python
# Via Mahavishnu's CommonMCPClient.call_tool, or any MCP client
await client.call_tool(
    "subagent_marker",
    {"working_dir": "/path/to/project", "action": "mark"},
)
```

Return shape:

```json
{"success": true, "lockfile_path": "/path/to/project/.session-buddy/subagent.lock", "action": "mark"}
```

Errors are surfaced as structured `{"success": false, "error": "...", "error_code": "..."}`
envelopes — never raised past the MCP boundary.

## Atomicity invariant

When a payload is supplied, the lockfile is written atomically via
`tempfile.mkstemp` + `os.replace()`. Concurrent readers never observe a
partial file; if the write fails partway, the orphan tmp file is
best-effort cleaned up. The fast-path (`LockfileSignalSource.write(active)`
without payload) is non-atomic by design — it preserves the legacy
`path.touch()` contract for callers that don't care about payload.

Fail-open semantics (per spec invariant): a write failure is logged, not
raised. The consumer's `is_active()` continues to work — it cannot tell
the difference between a "lockfile missing" and a "lockfile write failed".

## Cross-repo followup

`docs/followups/2026-09-19-sb-subagent-lockfile-producer.md` (in mahavishnu)
tracks the closure of this work. That followup closes when:

1. `SubagentDetector.write()` is implemented in session-buddy and covered by
   tests (≥ 90% coverage on the new code).
2. The lockfile is created/removed by at least one runtime path.
3. The "functionally dormant" caveat is removed from `subagent_detector.py`.
4. The two blocking plans (`docs/superpowers/plans/2026-07-15-sb-checkpoint-stash-clobber-fix.md`
   and `docs/followups/2026-07-15-sb-checkpoint-stash-clobber.md`) promote
   from `partial` to `complete` via PLAN_INDEX regeneration.

## Verification

```bash
cd /Users/les/Projects/session-buddy

# Targeted tests
.venv/bin/pytest tests/unit/core/checkpoint/test_subagent_detector.py -v
.venv/bin/pytest tests/integration/test_subagent_marker_tool.py -v

# CLI smoke test
TMPDIR=$(mktemp -d)
.venv/bin/python -m session_buddy checkpoint subagent-marker \
    --action mark --working-dir "$TMPDIR"
cat "$TMPDIR/.session-buddy/subagent.lock"  # JSON payload
.venv/bin/python -m session_buddy checkpoint subagent-marker \
    --action clear --working-dir "$TMPDIR"
rm -rf "$TMPDIR"
```

## Tracking

- Originating observation: 2026-07-15 comprehensive-hooks-cleanup wave
  (`docs/followups/2026-07-15-comprehensive-hooks-cleanup-checkpoint.md`).
- Parent memory:
  `~/.claude/projects/-Users-les-Projects-mahavishnu/memory/session-buddy-checkpoint-hooks-fire-during-subagent-sessions.md`.
- Cross-repo followup: `docs/followups/2026-09-19-sb-subagent-lockfile-producer.md`
  (in mahavishnu).
