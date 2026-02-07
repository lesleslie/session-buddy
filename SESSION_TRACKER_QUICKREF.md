# SessionTracker Quick Reference

## Import

```python
from session_buddy.mcp import SessionTracker
from session_buddy.mcp.event_models import (
    SessionStartEvent,
    SessionEndEvent,
    SessionStartResult,
    SessionEndResult,
    UserInfo,
    EnvironmentInfo,
)
from session_buddy.core import SessionLifecycleManager
```

## Initialization

```python
# Create lifecycle manager
lifecycle_mgr = SessionLifecycleManager()

# Create tracker
tracker = SessionTracker(lifecycle_mgr)

# Or with custom logger
import logging
logger = logging.getLogger("my_app")
tracker = SessionTracker(lifecycle_mgr, logger=logger)
```

## Handle Session Start

```python
event = SessionStartEvent(
    event_version="1.0",  # Must be "1.0"
    event_id="550e8400-e29b-41d4-a716-446655440000",  # UUID v4
    component_name="mahavishnu",  # Alphanumeric, underscore, hyphen
    shell_type="MahavishnuShell",  # Shell class name
    timestamp="2026-02-06T12:34:56.789Z",  # ISO 8601 UTC
    pid=12345,  # Process ID (1-4194304)
    user=UserInfo(
        username="john",  # Max 100 chars
        home="/home/john"  # Max 500 chars
    ),
    hostname="server01",
    environment=EnvironmentInfo(
        python_version="3.13.0",
        platform="Linux-6.5.0-x86_64",
        cwd="/home/john/projects"  # Max 500 chars
    ),
    metadata={"key": "value"}  # Optional
)

result = await tracker.handle_session_start(event)

# Check result
if result.status == "tracked":
    print(f"Session ID: {result.session_id}")
elif result.status == "error":
    print(f"Error: {result.error}")
```

## Handle Session End

```python
event = SessionEndEvent(
    session_id="mahavishnu-20260206-123456",  # From start result
    timestamp="2026-02-06T13:45:07.890Z",  # ISO 8601 UTC
    metadata={"exit_reason": "user_exit"}  # Optional
)

result = await tracker.handle_session_end(event)

# Check result
if result.status == "ended":
    print(f"Session ended: {result.session_id}")
elif result.status == "error":
    print(f"Error: {result.error}")
elif result.status == "not_found":
    print(f"Session not found: {result.session_id}")
```

## Result Models

### SessionStartResult

```python
@dataclass
class SessionStartResult:
    session_id: str | None  # None if status is "error"
    status: str  # "tracked" or "error"
    error: str | None  # Error message if status is "error"
```

### SessionEndResult

```python
@dataclass
class SessionEndResult:
    session_id: str  # Always present
    status: str  # "ended", "error", or "not_found"
    error: str | None  # Error message if status is "error"
```

## Validation Rules

### SessionStartEvent

| Field | Validation |
|-------|------------|
| event_version | Must be "1.0" |
| event_id | Valid UUID v4 |
| event_type | Must be "session_start" (auto-set) |
| component_name | Alphanumeric, underscore, hyphen only |
| timestamp | Valid ISO 8601 with time component |
| pid | 1-4194304 |
| username | Max 100 chars, whitespace stripped |
| home | Max 500 chars, whitespace stripped |
| cwd | Max 500 chars, whitespace stripped |

### SessionEndEvent

| Field | Validation |
|-------|------------|
| event_type | Must be "session_end" (auto-set) |
| session_id | String from SessionStartResult |
| timestamp | Valid ISO 8601 with time component |

## Logging

### INFO Level

- Session started: `session_id, component, shell_type, pid, user, hostname, cwd`
- Session ended: `session_id, timestamp`

### ERROR Level

- Session start failed: `component, shell_type, pid, error`
- Session end failed: `session_id, error`
- Exceptions: Full traceback

## Common Patterns

### Pattern 1: Basic Session Tracking

```python
tracker = SessionTracker(lifecycle_mgr)

# Start session
start_result = await tracker.handle_session_start(start_event)
if start_result.status != "tracked":
    print(f"Failed to start session: {start_result.error}")
    return

session_id = start_result.session_id

# ... do work ...

# End session
end_result = await tracker.handle_session_end(
    SessionEndEvent(
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
)
```

### Pattern 2: Error Handling

```python
def safe_session_start(tracker, event):
    try:
        result = await tracker.handle_session_start(event)
        if result.status == "error":
            logger.error(f"Session start failed: {result.error}")
            return None
        return result.session_id
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return None

session_id = safe_session_start(tracker, start_event)
if not session_id:
    return  # Exit if session start failed
```

### Pattern 3: Event Creation Helper

```python
def create_start_event(
    component_name: str,
    shell_type: str,
    pid: int,
    cwd: str
) -> SessionStartEvent:
    from datetime import datetime, timezone

    return SessionStartEvent(
        event_version="1.0",
        event_id=uuid.uuid4(),
        component_name=component_name,
        shell_type=shell_type,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        pid=pid,
        user=UserInfo(
            username=os.getenv("USER", "unknown"),
            home=os.path.expanduser("~")
        ),
        hostname=socket.gethostname(),
        environment=EnvironmentInfo(
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            platform=platform.platform(),
            cwd=cwd
        )
    )
```

## Testing

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_session_start():
    # Mock lifecycle manager
    lifecycle_mgr = MagicMock(spec=SessionLifecycleManager)
    lifecycle_mgr.initialize_session = AsyncMock(return_value={
        "success": True,
        "project": "test"
    })

    # Create tracker
    tracker = SessionTracker(lifecycle_mgr)

    # Create event
    event = SessionStartEvent(
        event_version="1.0",
        event_id="550e8400-e29b-41d4-a716-446655440000",
        component_name="test",
        shell_type="TestShell",
        timestamp="2026-02-06T12:34:56.789Z",
        pid=12345,
        user=UserInfo(username="test", home="/home/test"),
        hostname="testhost",
        environment=EnvironmentInfo(
            python_version="3.13.0",
            platform="Linux",
            cwd="/home/test"
        )
    )

    # Handle event
    result = await tracker.handle_session_start(event)

    # Assert
    assert result.status == "tracked"
    assert result.session_id is not None
```

## File Locations

- Implementation: `/Users/les/Projects/session-buddy/session_buddy/mcp/session_tracker.py`
- Tests: `/Users/les/Projects/session-buddy/tests/mcp/test_session_tracker.py`
- Event Models: `/Users/les/Projects/session-buddy/session_buddy/mcp/event_models.py`
- Summary: `/Users/les/Projects/session-buddy/SESSION_TRACKER_IMPLEMENTATION.md`
