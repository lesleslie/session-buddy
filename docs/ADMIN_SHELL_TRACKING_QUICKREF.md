# Admin Shell Session Tracking - Quick Reference

## Overview

The Session-Buddy MCP server now provides two tools for tracking admin shell session lifecycle events:

- `track_session_start`: Called when admin shell starts
- `track_session_end`: Called when admin shell exits

## Setup

### 1. Enable Authentication (Recommended for Production)

```bash
# Generate JWT secret
export SESSION_BUDDY_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')

# Verify it's set
echo $SESSION_BUDDY_SECRET
```

### 2. Generate JWT Token (for Admin Shells)

```python
import jwt
from datetime import datetime, timedelta, UTC

SECRET = "your-session-buddy-secret"

token = jwt.encode(
    {
        "user_id": "admin-shell",
        "exp": datetime.now(tz=UTC) + timedelta(hours=24),
        "iat": datetime.now(tz=UTC),
        "type": "access",
        "iss": "session-buddy",
    },
    SECRET,
    algorithm="HS256"
)

print(token)
```

## Tool Usage

### Track Session Start

```python
from uuid import uuid4
from datetime import datetime, timezone

# Generate event data
event_id = str(uuid4())
timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# Call MCP tool
result = await mcp.call_tool("track_session_start", {
    "event_version": "1.0",
    "event_id": event_id,
    "event_type": "session_start",
    "component_name": "mahavishnu",  # or "session-buddy", "oneiric"
    "shell_type": "MahavishnuShell",
    "timestamp": timestamp,
    "pid": 12345,
    "user": {
        "username": "john",
        "home": "/home/john"
    },
    "hostname": "server01",
    "environment": {
        "python_version": "3.13.0",
        "platform": "Linux-6.5.0-x86_64",
        "cwd": "/home/john/projects/mahavishnu"
    },
    "metadata": {},  # Optional
    "token": jwt_token  # Required if SESSION_BUDDY_SECRET is set
})

# Result format:
# {
#     "session_id": "mahavishnu-20260206-123456",
#     "status": "tracked",
#     "error": null
# }

# Store session_id for later use
session_id = result["session_id"]
```

### Track Session End

```python
from datetime import datetime, timezone

# Generate timestamp
timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# Call MCP tool
result = await mcp.call_tool("track_session_end", {
    "session_id": session_id,  # From track_session_start
    "timestamp": timestamp,
    "event_type": "session_end",
    "metadata": {
        "exit_reason": "user_exit"  # Optional
    },
    "token": jwt_token  # Required if SESSION_BUDDY_SECRET is set
})

# Result format:
# {
#     "session_id": "mahavishnu-20260206-123456",
#     "status": "ended",
#     "error": null
# }
```

## Error Handling

### Authentication Error

```python
# If token is invalid or missing
{
    "session_id": None,
    "status": "error",
    "error": "❌ Authentication failed: Token required (SESSION_BUDDY_SECRET is set)"
}
```

### Validation Error

```python
# If event data is invalid
{
    "session_id": None,
    "status": "error",
    "error": "Session start tracking failed: Invalid UUID v4 format: ..."
}
```

### Session Not Found

```python
# If session_id doesn't exist
{
    "session_id": "mahavishnu-20260206-123456",
    "status": "not_found",
    "error": null
}
```

## Integration Example (Mahavishnu Admin Shell)

```python
import asyncio
import sys
from datetime import datetime, timezone
from uuid import uuid4
import jwt

class MahavishnuShell:
    """Mahavishnu admin shell with session tracking."""

    def __init__(self, mcp_client, jwt_token):
        self.mcp_client = mcp_client
        self.jwt_token = jwt_token
        self.session_id = None

    async def start(self):
        """Initialize shell and track session start."""
        # ... existing initialization code ...

        # Track session start
        result = await self.mcp_client.call_tool("track_session_start", {
            "event_version": "1.0",
            "event_id": str(uuid4()),
            "event_type": "session_start",
            "component_name": "mahavishnu",
            "shell_type": "MahavishnuShell",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pid": sys.pid or os.getpid(),
            "user": {
                "username": os.getenv("USER", os.getenv("USERNAME", "unknown")),
                "home": os.path.expanduser("~")
            },
            "hostname": os.uname().nodename,
            "environment": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": sys.platform,
                "cwd": os.getcwd()
            },
            "token": self.jwt_token
        })

        if result["status"] == "tracked":
            self.session_id = result["session_id"]
            print(f"Session tracked: {self.session_id}")
        else:
            print(f"Session tracking failed: {result['error']}")

    async def exit(self):
        """Cleanup and track session end."""
        # ... existing cleanup code ...

        # Track session end
        if self.session_id:
            result = await self.mcp_client.call_tool("track_session_end", {
                "session_id": self.session_id,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event_type": "session_end",
                "metadata": {"exit_reason": "user_exit"},
                "token": self.jwt_token
            })

            if result["status"] == "ended":
                print(f"Session ended: {self.session_id}")
            else:
                print(f"Session end tracking failed: {result['error']}")

# Usage
async def main():
    mcp_client = get_mcp_client()  # Your MCP client implementation
    jwt_token = get_jwt_token()     # Your JWT token

    shell = MahavishnuShell(mcp_client, jwt_token)
    await shell.start()

    # ... shell runs ...

    await shell.exit()

asyncio.run(main())
```

## Testing Without Authentication

If `SESSION_BUDDY_SECRET` is not set, authentication is disabled:

```bash
# Unset SESSION_BUDDY_SECRET for testing
unset SESSION_BUDDY_SECRET

# Tools will accept any token value (including None)
result = await mcp.call_tool("track_session_start", {
    # ... parameters ...
    "token": None  # Authentication disabled
})
```

## Troubleshooting

### Issue: "Authentication failed: Token required"

**Solution**: Set `SESSION_BUDDY_SECRET` and provide valid JWT token.

```bash
export SESSION_BUDDY_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

### Issue: "Invalid UUID v4 format"

**Solution**: Use proper UUID v4 format.

```python
from uuid import uuid4
event_id = str(uuid4())  # Correct: "550e8400-e29b-41d4-a716-446655440000"
```

### Issue: "Invalid ISO 8601 timestamp"

**Solution**: Use ISO 8601 format with 'T' separator and 'Z' suffix.

```python
from datetime import datetime, timezone
timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
# Correct: "2026-02-06T12:34:56.789Z"
```

### Issue: "Session initialization failed"

**Solution**: Check that working directory exists and is accessible.

```python
import os
cwd = os.getcwd()
assert os.path.exists(cwd), f"Working directory does not exist: {cwd}"
```

## Monitoring

Check Session-Buddy logs for tracking events:

```bash
# View session tracking logs
tail -f /path/to/session-buddy.log | grep "Session start tracked\|Session end tracked"
```

Expected log format:

```
INFO - Session start tracked: session_id=mahavishnu-20260206-123456, component=mahavishnu, shell_type=MahavishnuShell, pid=12345, status=tracked
INFO - Session end tracked: session_id=mahavishnu-20260206-123456, status=ended
```

## Additional Resources

- Full implementation: `/Users/les/Projects/session-buddy/session_buddy/mcp/tools/session/admin_shell_tracking_tools.py`
- Event models: `/Users/les/Projects/session-buddy/session_buddy/mcp/event_models.py`
- Session tracker: `/Users/les/Projects/session-buddy/session_buddy/mcp/session_tracker.py`
- Complete documentation: `/Users/les/Projects/session-buddy/ADMIN_SHELL_TRACKING_MCP_TOOLS.md`
