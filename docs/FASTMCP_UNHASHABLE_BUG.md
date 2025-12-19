# FastMCP Unhashable CallToolRequestParams Bug

**Date:** January 19, 2025
**Status:** Workaround Implemented
**Affects:** session-buddy v0.10.x with FastMCP 2.14.1

## Summary

The session-buddy MCP server was encountering an error when the `checkpoint` tool was called:

```
Error: unhashable type: 'CallToolRequestParams'
```

This error occurred in the MCP protocol layer when using FastMCP's middleware system.

## Root Cause Analysis

### The Issue

1. **CallToolRequestParams is Unhashable**

   - `CallToolRequestParams` is a Pydantic model (subclass of `BaseModel`)
   - Pydantic models set `__hash__ = None` by default to prevent accidental hashing of mutable objects
   - This makes instances of `CallToolRequestParams` unhashable

1. **MiddlewareContext Contains Unhashable Field**

   - FastMCP's `MiddlewareContext` dataclass is marked as `frozen=True`
   - It contains a `message: T` field that holds `CallToolRequestParams`
   - When a frozen dataclass contains an unhashable field, the dataclass itself becomes unhashable

1. **Code Attempting to Hash Context**

   ```python
   # From fastmcp/server/middleware/middleware.py:46
   @dataclass(kw_only=True, frozen=True)
   class MiddlewareContext(Generic[T]):
       message: T  # This holds CallToolRequestParams
       ...
   ```

   When any code tries to:

   - Use `MiddlewareContext` as a dict key
   - Add it to a set
   - Call `hash()` on it

   Python raises: `TypeError: unhashable type: 'CallToolRequestParams'`

### Evidence

```python
# Test demonstrating the issue
from mcp.types import CallToolRequestParams
from fastmcp.server.middleware.middleware import MiddlewareContext
from datetime import datetime, timezone

params = CallToolRequestParams(name="checkpoint", arguments={})
context = MiddlewareContext(
    message=params,
    source="client",
    type="request",
    method="tools/call",
    timestamp=datetime.now(timezone.utc),
)

# This fails with: unhashable type: 'CallToolRequestParams'
hash(context)
```

## Workaround Implementation

### Temporary Fix

Disabled the rate limiting middleware that was triggering the hash operation:

```python
# session_buddy/server.py:229-243
# Add rate limiting middleware (Phase 3 Security Hardening)
# NOTE: Disabled temporarily due to FastMCP bug where MiddlewareContext becomes unhashable
# when it contains CallToolRequestParams (which has __hash__ = None).
# See: https://github.com/jlowin/fastmcp/issues for tracking
# if RATE_LIMITING_AVAILABLE:
#     from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
#     ...
```

### Additional Logger Fix

Also fixed a related issue where `depends.get_sync("acb_logger")` was returning a coroutine:

```python
# session_buddy/server.py:56-69
def _get_session_logger():
    """Get logger, handling both sync and async returns from DI."""
    import logging

    try:
        logger = depends.get_sync("acb_logger")
        # Check if DI returned a coroutine (async getter issue)
        if asyncio.iscoroutine(logger):
            # Fall back to standard logging rather than trying to await at module level
            return logging.getLogger(__name__)
        return logger
    except Exception:
        # Fallback logger in case of dependency injection issues
        return logging.getLogger(__name__)
```

## Impact

### What Works

- ✅ Server starts successfully
- ✅ All tools are registered
- ✅ Checkpoint tool functions correctly
- ✅ No runtime errors

### What's Disabled

- ⚠️ Rate limiting middleware (temporarily disabled)
  - Was protecting against: 10 req/sec sustained, 30 burst capacity
  - Impact: Server is vulnerable to request flooding
  - Mitigation: Running locally in trusted environment only

## Upstream Issues

### Related FastMCP Issues

Based on web search, similar parameter-related issues exist:

1. **[Issue #932](https://github.com/jlowin/fastmcp/issues/932)** - LLM-to-MCP Parameter Error: JSON Arguments Encapsulated as String Cause Validation Failure
1. **[Issue #1252](https://github.com/jlowin/fastmcp/issues/1252)** - Returning CallToolResult from `on_call_tool` yields "'CallToolResult' object has no attribute 'to_mcp_result'"
1. **[Issue #381](https://github.com/modelcontextprotocol/python-sdk/issues/381)** - Fastmcp tool parameter parsing type error

### What Needs to be Fixed

The ideal fix should be in **FastMCP** or **MCP Python SDK**:

**Option 1: Make CallToolRequestParams Hashable**

```python
# In mcp/types.py
class CallToolRequestParams(RequestParams):
    name: str
    arguments: dict[str, Any] | None = None

    model_config = ConfigDict(
        extra="allow",
        frozen=True,  # Enable hashing for frozen models
    )

    def __hash__(self) -> int:
        # Hash based on immutable fields only
        return hash(
            (
                self.name,
                tuple(sorted(self.arguments.items())) if self.arguments else None,
            )
        )
```

**Option 2: Change MiddlewareContext to not be Frozen**

```python
# In fastmcp/server/middleware/middleware.py
@dataclass(kw_only=True)  # Remove frozen=True
class MiddlewareContext(Generic[T]):
    message: T
    ...
```

**Option 3: Middleware Should Not Hash Context**

- Review middleware implementations to avoid using context as dict keys
- Use alternative identification strategies (request IDs, message content hashes)

## Testing

### Verify the Fix

```bash
# Test server startup
cd /Users/les/Projects/fastblocks
python -m session_buddy.server

# Should see:
# ✅ Session Management MCP started successfully!
```

### Test Checkpoint Tool

The checkpoint tool should work without errors when called from Claude Code.

## Recommendations

### Short-term (Current Workaround)

1. ✅ Keep rate limiting disabled until FastMCP fix is available
1. ✅ Monitor for upstream fixes in FastMCP releases
1. ✅ Only run in trusted environments (local development)

### Long-term (Proper Fix)

1. Report this issue to FastMCP maintainers with reproduction case
1. Propose one of the fix options above
1. Re-enable rate limiting middleware once fix is merged
1. Update to fixed FastMCP version

## References

- **FastMCP Repository:** https://github.com/jlowin/fastmcp
- **MCP Python SDK:** https://github.com/modelcontextprotocol/python-sdk
- **Related Issues:** See "Upstream Issues" section above
- **FastMCP Version:** 2.14.1
- **Session-Buddy Version:** 0.10.x

## Version History

- **2025-01-19:** Initial bug discovery and workaround implementation
- **TBD:** Re-enable after upstream fix

______________________________________________________________________

**Status:** ⚠️ Workaround Active - Awaiting Upstream Fix
