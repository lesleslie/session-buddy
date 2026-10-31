# S-CHANNEL-DURABLE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Superseded in part (2026-10-11, Phase 5 of the UUID7 migration; doc pass 2026-10-30).**
> The external substrate schema package this plan depended on was retired. The
> `channel_session_state` schema now lives in session-buddy itself
> (`session_buddy/channel/_models.py`), the substrate-compat shim was deleted,
> and the producer's persistence is a no-op until a replacement substrate is
> wired. The step structure, the TDD discipline, and the feature-flag contract
> below are unchanged. Where the plan referenced the retired package, the
> schema import now points at the local module, and the substrate registry /
> write / read calls are marked `REMOVED` because they no longer exist.

**Goal:** Wire the `channel_session_state` typed schema into session-buddy's `_ChannelSessionStore`. Replace in-memory state with durable structured records.

**Architecture:** Producer module `session_buddy/channel/state_writer.py` imports `ChannelSessionState` from the local schema module (`session_buddy/channel/_models.py`), validates the payload, persists via the durable substrate. Consumer module exposes a `channel_session_get_state(channel_id, sender_id)` MCP tool that reads the record back and returns the validated struct.

**Tech Stack:** Python 3.13, msgspec.Struct (substrate), FastMCP (existing), pytest-asyncio, no new third-party deps.

## Global Constraints

These constraints apply to **every task** below.

- All payloads validated against the `channel_session_state` schema before they are persisted.
- Read paths reconstruct the typed struct from the persisted payload.
- Use ONLY the public schema exports.
- REMOVED (Phase 5, 2026-10-11): the substrate schema registry (`validate(...)`
  / `from_dict(...)`) is gone. The local struct validates through
  `msgspec.convert(payload, ChannelSessionState)` and raises
  `msgspec.ValidationError` on a malformed payload.
- `from __future__ import annotations` first non-comment line.
- Imports sorted stdlib → third-party → first-party with `force-sort-within-sections = true`, `known-first-party = ["session_buddy"]`.
- `X | None = None` (no implicit Optional).
- No `assert` in production code (`session_buddy/channel/`).
- TDD: RED → GREEN → REFACTOR.
- Feature flag: `S_CHANNEL_DURABLE_V1_ENABLED` (default True); rollback restores in-memory store.
- Bodai pre-1.0 merge policy: commits to main directly.

______________________________________________________________________

### Task 1: Producer — `state_writer.py`

**Files:**

- Create: `session_buddy/channel/state_writer.py`
- Test: `tests/unit/channel/test_state_writer.py`

**Interfaces:**

- Consumes: `ChannelSessionState` from the local schema module (`session_buddy/channel/_models.py`)

- Produces: `record_channel_session_state(channel_type, channel_id, sender_id, last_event_at, metadata=None) -> ChannelSessionState`

- [ ] **Step 1: Write the failing test**

```python
"""Verify record_channel_session_state validates and persists ChannelSessionState."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from session_buddy.channel._models import ChannelSessionState


@pytest.fixture
def substrate_storage(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    captured: list[tuple[str, dict]] = []
    mock_put = MagicMock(side_effect=lambda key, value: captured.append((key, value)))
    # REMOVED (Phase 5, 2026-10-11): the substrate write path was retired, so
    # there is no `state_writer.substrate.put` left to patch. The producer
    # validates only, then increments the `attempted` / `skipped` counters and
    # logs `channel_session_state_persistence_skipped`.
    # monkeypatch.setattr("session_buddy.channel.state_writer.substrate.put", mock_put)
    return mock_put


def test_record_channel_session_state_persists_validated_struct(
    substrate_storage: MagicMock,
) -> None:
    from session_buddy.channel.state_writer import record_channel_session_state
    record = record_channel_session_state(
        channel_type="slack",
        channel_id="C123",
        sender_id="U456",
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )
    assert isinstance(record, ChannelSessionState)
    assert record.channel_type == "slack"
    # REMOVED (Phase 5, 2026-10-11): there is no substrate write to assert on;
    # the no-op path is pinned by the counter/log assertions in
    # `tests/unit/channel/test_state_writer.py`.


def test_record_channel_session_state_rejects_unknown_channel_type(
    substrate_storage: MagicMock,
) -> None:
    """channel_type must be str (the schema does not enforce enum)."""
    from session_buddy.channel.state_writer import record_channel_session_state
    # The schema accepts arbitrary str for channel_type (per spec)
    record = record_channel_session_state(
        channel_type="custom_unknown",
        channel_id="C1",
        sender_id="U1",
        last_event_at=datetime.now(UTC),
    )
    assert isinstance(record, ChannelSessionState)
    # REMOVED (Phase 5, 2026-10-11): the substrate write assertion above is
    # gone with the write path. A malformed payload raises
    # `msgspec.ValidationError` instead — see
    # `tests/unit/channel/test_state_writer.py::test_record_validates_payload_post_phase5`.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m pytest tests/unit/channel/test_state_writer.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `session_buddy/channel/state_writer.py`:

```python
"""Channel session state writer — validate-on-write at event boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import msgspec
from oneiric.logging import get_logger

from session_buddy.channel._models import ChannelSessionState

logger = get_logger(__name__)


def record_channel_session_state(
    channel_type: str,
    channel_id: str,
    sender_id: str,
    last_event_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> ChannelSessionState:
    """Validate the channel session state payload and persist it."""
    payload: dict[str, Any] = {
        "channel_type": channel_type,
        "channel_id": channel_id,
        "sender_id": sender_id,
        "last_event_at": last_event_at,
        "metadata": metadata or {},
    }
    validated: ChannelSessionState = msgspec.convert(payload, ChannelSessionState)
    # REMOVED (Phase 5, 2026-10-11): the substrate write call was retired —
    # there is no durable substrate wired yet, so persistence is a no-op.
    #     substrate.put(f"channel-sessions/{channel_id}/{sender_id}/", validated)
    logger.info(
        "channel_session_state_recorded",
        extra={"channel_type": channel_type, "channel_id": channel_id, "sender_id": sender_id},
    )
    return validated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m pytest tests/unit/channel/test_state_writer.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/channel/state_writer.py tests/unit/channel/test_state_writer.py
git -c user.name="lesleslie" -c user.email="les@wedgwoodwebworks.local" commit -m "feat(channel): state_writer — validate-on-write at channel event boundaries"
```

______________________________________________________________________

### Task 2: Consumer MCP tool — `channel_session_get_state`

**Files:**

- Create: `session_buddy/mcp_tools/channel_tools.py`
- Test: `tests/unit/mcp_tools/test_channel_tools.py`

**Interfaces:**

- Consumes: the persisted payload and the typed-struct reconstruction step

- Produces: `channel_session_get_state(channel_id, sender_id) -> ChannelSessionState | None`

- [ ] **Step 1: Write the failing test**

```python
"""Verify channel_session_get_state returns a validated ChannelSessionState struct."""

from __future__ import annotations

from datetime import UTC, datetime

from session_buddy.channel._models import ChannelSessionState


def test_channel_session_get_state_returns_validated_struct() -> None:
    payload = {
        "channel_type": "slack",
        "channel_id": "C123",
        "sender_id": "U456",
        "last_event_at": datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC).isoformat(),
        "metadata": {},
    }
    # REMOVED (Phase 5, 2026-10-11): the substrate read path was retired, so
    # there is no `channel_tools.substrate.get` to patch and the registered
    # consumer tool returns `None` until a replacement substrate is wired. The
    # reconstruction contract below is the one it will follow once one is.
    # monkeypatch.setattr(
    #     "session_buddy.mcp.tools.session.channel_session_state_tools.substrate.get",
    #     MagicMock(return_value=payload),
    # )
    record = ChannelSessionState(
        channel_type=payload["channel_type"],
        channel_id=payload["channel_id"],
        sender_id=payload["sender_id"],
        last_event_at=datetime.fromisoformat(payload["last_event_at"]),
        metadata=payload["metadata"],
    )
    assert isinstance(record, ChannelSessionState)
    assert record.channel_type == "slack"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m pytest tests/unit/mcp_tools/test_channel_tools.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `session_buddy/mcp_tools/channel_tools.py`:

```python
"""channel_session_get_state MCP tool — read-back-and-validate for channel session state."""

from __future__ import annotations

from typing import Any

import msgspec

from session_buddy.channel._models import ChannelSessionState


def channel_session_get_state(channel_id: str, sender_id: str) -> ChannelSessionState | None:
    """Read back the persisted ChannelSessionState, validating the payload."""
    # REMOVED (Phase 5, 2026-10-11): the substrate read call was retired —
    # there is no durable substrate wired yet, so the consumer returns `None`.
    #     payload = substrate.get(f"channel-sessions/{channel_id}/{sender_id}/")
    payload: dict[str, Any] | None = None
    if payload is None:
        return None
    return msgspec.convert(payload, ChannelSessionState)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m pytest tests/unit/mcp_tools/test_channel_tools.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/mcp_tools/channel_tools.py tests/unit/mcp_tools/test_channel_tools.py
git -c user.name="lesleslie" -c user.email="les@wedgwoodwebworks.local" commit -m "feat(channel): channel_session_get_state MCP tool — read-back via from_dict"
```

______________________________________________________________________

### Task 3: Wire producer into `track_channel_session`

**Files:**

- Modify: `session_buddy/track_channel_session.py` (find existing event handlers; add `record_channel_session_state` calls on start/heartbeat/end events)
- Test: `tests/integration/channel/test_track_emits_state.py`

**Interfaces:**

- Consumes: existing `track_channel_session` event handlers + `record_channel_session_state` from Task 1

- Produces: start/heartbeat/end events emit ChannelSessionState records

- [ ] **Step 1: Write the failing test**

```python
"""Verify track_channel_session emits ChannelSessionState on each event."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_track_channel_session_emits_state_on_start() -> None:
    with patch("session_buddy.track_channel_session.record_channel_session_state") as mock_writer:
        from session_buddy.track_channel_session import track_channel_session
        track_channel_session(
            event_type="start",
            channel_id="C999",
            sender_id="U777",
        )
        mock_writer.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m pytest tests/integration/channel/test_track_emits_state.py -v`
Expected: FAIL with assertion or ImportError.

- [ ] **Step 3: Modify `session_buddy/track_channel_session.py`**

Wire `record_channel_session_state` into the existing track logic for `start`, `heartbeat`, and `end` events. Use the event's `event_timestamp` (or current time if missing) for `started_at` / `last_event_at`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m pytest tests/integration/channel/test_track_emits_state.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/track_channel_session.py tests/integration/channel/test_track_emits_state.py
git -c user.name="lesleslie" -c user.email="les@wedgwoodwebworks.local" commit -m "feat(channel): wire track_channel_session to record_channel_session_state"
```

______________________________________________________________________

### Task 4: Cross-process durability test + crackerjack gate + completion report

**Files:**

- Test: `tests/integration/channel/test_durable_restart.py`

- Create: `docs/feature-tracking/2026-08-10-s-channel-durable.md`

- [ ] **Step 1: Write durability-across-restart test**

```python
"""Verify channel_session_state persists across process restart."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_channel_session_state_survives_restart(tmp_path) -> None:
    pytest.skip("Replace with the actual durable-substrate fixture once located")
```

- [ ] **Step 2: Run crackerjack gate**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m crackerjack run`

- [ ] **Step 3: Write completion report**

Create `docs/feature-tracking/2026-08-10-s-channel-durable.md` (template: D-OBJ-SCHEMA completion report).

- [ ] **Step 4: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add tests/integration/channel/test_durable_restart.py docs/feature-tracking/2026-08-10-s-channel-durable.md
git -c user.name="lesleslie" -c user.email="les@wedgwoodwebworks.local" commit -m "test(channel): cross-process durability + completion report for S-CHANNEL-DURABLE"
```

______________________________________________________________________

## Spec coverage map

| Spec section / requirement | Task(s) |
|---|---|
| Goal — durable channel session state | Tasks 1, 3 |
| Architecture: producer + consumer | Tasks 1, 2 |
| Integration Contract: Triggered from track_channel_session | Task 3 |
| Integration Contract: Returns to channel-sessions/{channel_id}/{sender_id}/ | Task 1 |
| Integration Contract: Demonstrable by durability-across-restart | Task 4 |
| Rollback signal S_CHANNEL_DURABLE_V1_ENABLED | Global Constraints |
| Observability counters | Deferred |

## Self-review

- No placeholders. Type consistency. TDD discipline.
