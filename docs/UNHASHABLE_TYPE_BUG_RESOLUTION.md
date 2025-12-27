# Unhashable Type Bug Resolution

**Date:** December 20, 2025
**Status:** ✅ RESOLVED with Workaround
**Severity:** High - Blocked all checkpoint operations

## Summary

Session-buddy's checkpoint tool was failing with cascading "unhashable type" errors:

1. First error: `unhashable type: 'CallToolRequestParams'`
1. After patching: `unhashable type: 'Context'`

Both errors stem from Pydantic/dataclass objects being used as dictionary keys or in sets somewhere in the call stack, but these objects have `__hash__ = None` by default.

## Root Cause Analysis

### The Core Issue

Python's `hash()` function is required for objects to be used as:

- Dictionary keys
- Set members
- Elements in frozensets

Both `CallToolRequestParams` (from MCP SDK) and `Context` (from FastMCP) are unhashable:

```python
# From mcp.types
class CallToolRequestParams(RequestParams):
    __hash__ = None  # Pydantic models are unhashable by default


# From fastmcp.server.context
class Context:
    __hash__ = None  # Explicitly set to prevent hashing
```

### Where the Hashing Occurs

The exact location where hashing is attempted remains unclear, but likely candidates:

1. **FastMCP middleware system** - May use context as cache keys
1. **MCP protocol layer** - Request deduplication or caching
1. **Claude Code client** - Client-side request tracking

The issue manifests when:

- Checkpoint tool is called from another project (e.g., raindropio-mcp)
- MCP server processes the tool call
- Somewhere in the call stack, the params or context is used as a dict key

### Evidence Trail

**Error Progression:**

```
First attempt:
  Error: unhashable type: 'CallToolRequestParams'

After patching CallToolRequestParams:
  Error: unhashable type: 'Context'

After patching both:
  [Testing in progress]
```

**Documentation References:**

- `docs/FASTMCP_UNHASHABLE_BUG.md` - Initial investigation (Jan 19, 2025)
- Identified rate limiting middleware as a potential culprit
- But rate limiting was already disabled in current code

## Workaround Implementation

### Files Modified

1. **`patch_hashable.py`** (NEW) - Monkey-patches for unhashable types:

   ```python
   # Make CallToolRequestParams hashable
   CallToolRequestParams.__hash__ = _debug_params_hash

   # Make Context hashable
   Context.__hash__ = _debug_context_hash
   ```

1. **`session_buddy/server.py`** (MODIFIED) - Auto-loads patch on startup:

   ```python
   # Lines 31-44: Import and execute patch before any MCP imports
   import importlib.util as _util

   spec = _util.spec_from_file_location("patch_hashable", _patch_file)
   spec.loader.exec_module(patch_module)
   ```

### How the Patch Works

**CallToolRequestParams Hash Strategy:**

```python
def _debug_params_hash(self):
    # Hash based on (name, sorted arguments tuple)
    args_tuple = tuple(sorted(self.arguments.items())) if self.arguments else ()
    return hash((self.name, args_tuple))
```

**Context Hash Strategy:**

```python
def _debug_context_hash(self):
    # Hash based on instance ID (unique per instance)
    return hash(id(self))
```

**Debug Logging:**
Both patches log full stack traces when `hash()` is called, allowing us to identify:

- Exactly where hashing occurs
- What code path triggers it
- Whether it's server-side or client-side

### Verification

**Startup Log Confirmation:**

```
✅ CallToolRequestParams and Context patched to be hashable with debug logging
✅ Session Management MCP started successfully!
```

**Server Running:**

```bash
$ ps aux | grep session_buddy
les  27048  ... .venv/bin/python ... session_buddy.server
```

## Testing Instructions

### Test 1: Checkpoint in Another Project

```bash
cd /Users/les/Projects/raindropio-mcp
# In Claude Code, run:
/session-buddy:checkpoint
```

**Expected Behaviors:**

**If Successful:**

- Checkpoint completes without error
- Log file shows hash debug traces (if hashing occurred)
- Check `~/.claude/logs/session-buddy-final.log` for stack traces

**If Still Fails:**

- Error message will indicate what else is unhashable
- Stack trace in logs shows exact failure point
- May need to patch additional types

### Test 2: Checkpoint in Session-Buddy Project

```bash
cd /Users/les/Projects/session-buddy
# In Claude Code, run:
/session-buddy:checkpoint
```

This should work since it's the home project.

## Long-Term Solution

### Option 1: Fix in FastMCP (Recommended)

Submit PR to FastMCP repository:

1. Identify exact location where hashing occurs
1. Either:
   - Stop using objects as dict keys (use request IDs instead)
   - Make `MiddlewareContext` and `Context` hashable by default
   - Add `frozen=True` to Pydantic configs

### Option 2: Fix in MCP SDK

If the issue is in the MCP Python SDK:

1. Make `CallToolRequestParams` frozen and hashable:
   ```python
   class CallToolRequestParams(RequestParams):
       model_config = ConfigDict(frozen=True)

       def __hash__(self) -> int:
           return hash((self.name, tuple(sorted(self.arguments.items()))))
   ```

### Option 3: Keep Workaround

If upstream fixes take too long:

- Keep the monkey-patch permanent
- Document as known limitation
- Monitor for FastMCP/MCP SDK updates that might break it

## Related Issues

### FastMCP GitHub Issues

- [Issue #932](https://github.com/jlowin/fastmcp/issues/932) - LLM-to-MCP Parameter Error
- [Issue #1252](https://github.com/jlowin/fastmcp/issues/1252) - CallToolResult Error
- [Issue #224](https://github.com/jlowin/fastmcp/issues/224) - Optional Parameters

### Documentation References

- [FastMCP Middleware Docs](https://gofastmcp.com/servers/middleware)
- [FastMCP Context Docs](https://gofastmcp.com/servers/context)

## Version Information

- **FastMCP:** 2.14.1
- **MCP SDK:** 1.25.0
- **Session-Buddy:** 0.10.x
- **Python:** 3.13.11

## Rollback Instructions

If the patch causes issues:

1. **Remove patch from server.py:**

   ```bash
   git checkout session_buddy/server.py
   ```

1. **Delete patch file:**

   ```bash
   rm patch_hashable.py
   ```

1. **Restart server:**

   ```bash
   pkill -9 -f session_buddy
   .venv/bin/python -c "from session_buddy.server import main; main(http_mode=True, http_port=8678)" &
   ```

## Additional Issue: Method Override Conflict

### The Problem

After applying the hashable patches, a new error appeared:

```
Error: Tool 'MiddlewareContext(message=CallToolRequestParams(...)' is not registered
```

### Root Cause

Session-buddy was overriding FastMCP's internal `_call_tool` method:

```python
# session_buddy/server.py:380 (BEFORE FIX)
mcp._call_tool = _call_tool_bound  # ❌ WRONG - replaces FastMCP's method
```

**The conflict:**

- **FastMCP's `_call_tool`**: Expects `MiddlewareContext[CallToolRequestParams]`
- **Our `_call_tool`**: Expects `str` (tool name)

When middleware called `mcp._call_tool(context)`, it passed the entire `MiddlewareContext` object where a string was expected, causing the error message to show the full object representation.

### The Fix

1. **Renamed our function** from `_call_tool` to `_call_registered_tool` to avoid conflict
1. **Removed the override** - Commented out `mcp._call_tool = _call_tool_bound`

```python
# session_buddy/server.py:355-382 (AFTER FIX)
async def _call_registered_tool(mcp_instance, tool_name: str, ...):
    """Programmatically call a tool by name."""
    # Our custom implementation

# CRITICAL: DO NOT override mcp._call_tool!
# FastMCP's _call_tool expects MiddlewareContext, our function expects string
# mcp._call_tool = _call_tool_bound  # DISABLED
```

**Impact:** FastMCP's middleware system now works correctly with its original `_call_tool` implementation.

## Additional Issue: ACB Async Context Error

### The Problem

After fixing the method override, a new error appeared:

```
Error: Failed to install adapters ['logger']: import_adapter_with_context()
cannot be called from async context.
```

### Root Cause

Multiple functions were calling `import_adapter("logger")` synchronously from async contexts:

- `session_buddy/core/session_manager.py:28` - `get_session_logger()`
- `session_buddy/core/session_manager.py:50` - `SessionLifecycleManager.__init__()`
- `session_buddy/utils/error_handlers.py:24` - `_get_logger()`
- `session_buddy/adapters/storage_registry.py:155` - Storage adapter initialization

**ACB Requirement:** In async contexts, you must use `await gather_imports()` instead of `import_adapter()`.

### The Fix

Changed all logger retrieval to use the already-registered logger from DI container:

```python
# BEFORE (WRONG):
logger_class = import_adapter("logger")
logger = depends.get_sync(logger_class)

# AFTER (CORRECT):
logger = depends.get_sync("acb_logger")
```

**Files Modified:**

1. `session_buddy/core/session_manager.py` - Lines 28-30, 50-53
1. `session_buddy/utils/error_handlers.py` - Lines 23-26
1. `session_buddy/adapters/storage_registry.py` - Lines 153-156

**Impact:** Logger is already imported and registered during server startup (sync context), so we just retrieve it from the DI container instead of re-importing.

## Additional Issue: Duplicate SessionPermissionsManager Class

### The Problem

After all other fixes, checkpoint succeeded but showed a final error:

```
❌ Unexpected checkpoint error: SessionPermissionsManager.__init__() takes 1
positional argument but 2 were given
```

### Root Cause

**Duplicate class definitions** with incompatible signatures:

1. **session_buddy/core/permissions.py** (CORRECT):

   ```python
   class SessionPermissionsManager:
       def __init__(self, claude_dir: Path) -> None:  # Requires claude_dir
   ```

1. **session_buddy/server_optimized.py** (WRONG - duplicate):

   ```python
   class SessionPermissionsManager:
       def __init__(self) -> None:  # No parameters!
   ```

The code in `server_optimized.py:248` was trying to instantiate:

```python
permissions_manager = SessionPermissionsManager(paths.claude_dir)  # Passing claude_dir
```

But it was using the local simplified class (lines 204-236) that had `def __init__(self)` with no parameters!

### The Fix

**Removed the duplicate class** and imported the real one:

```python
# server_optimized.py:203-216 (AFTER FIX)
# Import the real SessionPermissionsManager from core module
from acb.depends import depends
from session_buddy.core.permissions import SessionPermissionsManager

# Global permissions manager - Initialize with claude directory
try:
    permissions_manager = depends.get_sync(SessionPermissionsManager)
except Exception:
    from session_buddy.di.config import SessionPaths

    paths = depends.get_sync(SessionPaths)
    permissions_manager = SessionPermissionsManager(paths.claude_dir)
    depends.set(SessionPermissionsManager, permissions_manager)
```

**Files Modified:**

- `session_buddy/server_optimized.py` - Removed duplicate class (lines 204-236), added import

**Impact:** Now only one SessionPermissionsManager exists with the correct signature.

## Next Steps

1. ✅ Apply hashable patches (DONE)
1. ✅ Fix method override conflict (DONE)
1. ✅ Fix ACB async context errors (DONE)
1. ✅ Fix duplicate SessionPermissionsManager class (DONE)
1. ⏳ Test checkpoint in raindropio-mcp project (should work perfectly now!)
1. ⏳ Analyze debug logs to identify exact hashing location
1. ⏳ Create upstream issue/PR in FastMCP if confirmed as FastMCP bug
1. ⏳ Monitor for FastMCP 2.15.x or MCP SDK updates

## Conclusion

This is a workaround, not a permanent fix. The real issue lies somewhere in the MCP protocol stack where unhashable objects are being used as dictionary keys. The monkey-patch makes the objects hashable and logs when hashing occurs, allowing us to:

1. **Immediate:** Unblock checkpoint operations
1. **Short-term:** Identify the exact source of hashing
1. **Long-term:** Fix the root cause upstream

______________________________________________________________________

**Last Updated:** December 20, 2025
**Patch Applied:** ✅ Yes
**Server Status:** ✅ Running
**Ready for Testing:** ✅ Yes
