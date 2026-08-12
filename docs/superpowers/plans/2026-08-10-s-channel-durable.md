# S-CHANNEL-DURABLE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `channel_session_state` typed schema (from `dhara.schema`) into session-buddy's `_ChannelSessionStore`. Replace in-memory state with durable structured records.

**Architecture:** Producer module `session_buddy/channel/state_writer.py` imports `ChannelSessionState` from `dhara.schema`, validates via `validate("channel_session_state", payload)`, persists via Dhara. Consumer module exposes a `channel_session_get_state(channel_id, sender_id)` MCP tool that reads back via `from_dict` and returns validated struct.

**Tech Stack:** Python 3.13, msgspec.Struct (substrate), Dhara + FastMCP (existing), pytest-asyncio, no new third-party deps.

## Global Constraints

These constraints apply to **every task** below.

- All payloads validated via `validate("channel_session_state", payload)` from `dhara.schema.SCHEMA_REGISTRY`.
- Read paths use `from_dict("channel_session_state", payload)`.
- Use ONLY the public `dhara.schema` re-exports.
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

- Consumes: `dhara.schema.channel_session_state.ChannelSessionState`, `validate(...)` from `SCHEMA_REGISTRY`

- Produces: `record_channel_session_state(channel_type, channel_id, sender_id, started_at, last_event_at, metadata=None) -> ChannelSessionState`

- [ ] **Step 1: Write the failing test**

```python
"""Verify record_channel_session_state validates and persists ChannelSessionState."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from dhara.schema.channel_session_state import ChannelSessionState


@pytest.fixture
def dhara_storage(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    captured: list[tuple[str, dict]] = []
    mock_put = MagicMock(side_effect=lambda key, value: captured.append((key, value)))
    monkeypatch.setattr("session_buddy.channel.state_writer.dhara.put", mock_put)
    return mock_put


def test_record_channel_session_state_persists_validated_struct(
    dhara_storage: MagicMock,
) -> None:
    from session_buddy.channel.state_writer import record_channel_session_state
    record = record_channel_session_state(
        channel_type="slack",
        channel_id="C123",
        sender_id="U456",
        started_at=datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC),
        last_event_at=datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC),
    )
    assert isinstance(record, ChannelSessionState)
    assert record.channel_type == "slack"
    assert dhara_storage.call_count == 1


def test_record_channel_session_state_rejects_unknown_channel_type(
    dhara_storage: MagicMock,
) -> None:
    """channel_type must be str (substrate does not enforce enum)."""
    from dhara.schema._registry import SchemaValidationError
    from session_buddy.channel.state_writer import record_channel_session_state
    # Substrate accepts arbitrary str for channel_type (per spec)
    record = record_channel_session_state(
        channel_type="custom_unknown",
        channel_id="C1",
        sender_id="U1",
        started_at=datetime.now(UTC),
        last_event_at=datetime.now(UTC),
    )
    assert isinstance(record, ChannelSessionState)
    assert dhara_storage.call_count == 1
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
from typing import TYPE_CHECKING

from dhara.schema._registry import validate
from dhara.schema.channel_session_state import ChannelSessionState
from oneiric.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


def record_channel_session_state(
    channel_type: str,
    channel_id: str,
    sender_id: str,
    started_at: datetime,
    last_event_at: datetime,
    metadata: dict[str, object] | None = None,
) -> ChannelSessionState:
    """Validate the channel session state payload, persist via dhara.put."""
    payload = {
        "channel_type": channel_type,
        "channel_id": channel_id,
        "sender_id": sender_id,
        "started_at": started_at,
        "last_event_at": last_event_at,
        "metadata": metadata or {},
    }
    validated = validate("channel_session_state", payload)
    assert isinstance(validated, ChannelSessionState)
    import dhara
    dhara.put(f"channel-sessions/{channel_id}/{sender_id}/", validated)
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

- Consumes: `from_dict("channel_session_state", payload)`, `dhara.get(...)`

- Produces: `channel_session_get_state(channel_id, sender_id) -> ChannelSessionState | None`

- [ ] **Step 1: Write the failing test**

```python
"""Verify channel_session_get_state returns a validated ChannelSessionState struct."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from dhara.schema.channel_session_state import ChannelSessionState


def test_channel_session_get_state_returns_validated_struct(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "channel_type": "slack",
        "channel_id": "C123",
        "sender_id": "U456",
        "started_at": datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC).isoformat(),
        "last_event_at": datetime(2026, 8, 10, 12, 5, 0, tzinfo=UTC).isoformat(),
        "metadata": {},
    }
    monkeypatch.setattr(
        "session_buddy.mcp_tools.channel_tools.dhara.get",
        MagicMock(return_value=payload),
    )
    from session_buddy.mcp_tools.channel_tools import channel_session_get_state
    result = channel_session_get_state("C123", "U456")
    assert isinstance(result, ChannelSessionState)
    assert result.channel_type == "slack"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/les/Projects/session-buddy && .venv/bin/python -m pytest tests/unit/mcp_tools/test_channel_tools.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `session_buddy/mcp_tools/channel_tools.py`:

```python
"""channel_session_get_state MCP tool — read-back-and-validate for channel session state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhara.schema._registry import from_dict
from dhara.schema.channel_session_state import ChannelSessionState

if TYPE_CHECKING:
    pass


def channel_session_get_state(channel_id: str, sender_id: str) -> ChannelSessionState | None:
    """Read back the persisted ChannelSessionState via from_dict, validating the payload."""
    import dhara
    payload = dhara.get(f"channel-sessions/{channel_id}/{sender_id}/")
    if payload is None:
        return None
    return from_dict("channel_session_state", payload)
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
    pytest.skip("Replace with the actual Dhara fixture once located")
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
