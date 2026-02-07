# Session Tracking End-to-End Integration Test

**Date**: 2025-02-06
**Goal**: Verify session tracking works end-to-end between Session-Buddy and Mahavishnu

## Test Architecture

```
Mahavishnu Shell (IPython)
    ↓
SessionEventEmitter (oneiric)
    ↓
Session-Buddy MCP Server
    ↓
DuckDB Database
```

## Test Plan

### Phase 1: Environment Setup
- [x] Check dependencies (session-buddy, oneiric, mahavishnu)
- [ ] Install missing dependencies if needed
- [ ] Set environment variables

### Phase 2: Session-Buddy MCP Server
- [ ] Start Session-Buddy MCP server
- [ ] Verify tools are registered
- [ ] Check database connection

### Phase 3: Mahavishnu Shell Integration
- [ ] Start Mahavishnu shell
- [ ] Verify banner shows session tracking status
- [ ] Check session start event emission
- [ ] Exit shell and verify session end event

### Phase 4: Database Verification
- [ ] Query session database
- [ ] Verify session metadata
- [ ] Check session duration calculation

## Test Execution

### 1. Dependency Check

```bash
# Check if session-buddy is installed
pip show session-buddy

# Check if oneiric is installed
pip show oneiric

# Check if mahavishnu is installed
pip show mahavishnu
```

### 2. Session-Buddy MCP Server Start

```bash
cd /Users/les/Projects/session-buddy
export SESSION_BUDDY_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
session-buddy mcp start
```

**Expected Output**:
- Server starts successfully
- Tools registered: `track_session_start`, `track_session_end`
- No errors in startup logs

### 3. Mahavishnu Shell Start

```bash
cd /Users/les/Projects/mahavishnu
python -m mahavishnu shell
```

**Expected Output**:
- Banner shows "Session Tracking: ✓ Enabled" or "✗ Disabled"
- Shell enters IPython environment
- Session start event emitted

**Expected Banner Content**:
```
Mahavishnu v0.1.0 - Admin Shell
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Adapters: prefect, llamaindex, agno
CLI Commands: Enabled (475 commands)
Tab Completion: Enabled
Session Tracking: ✓ Enabled
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 4. Exit Shell and Verify Session End

```python
exit()
```

**Expected Behavior**:
- Session end event emitted
- Session record updated in database
- Duration calculated

### 5. Database Verification

```bash
session-buddy list-sessions --type admin_shell
```

**Expected Output**:
- List of admin shell sessions
- Most recent session should be the one we just created

```bash
session-buddy show-session <session_id>
```

**Expected Output**:
- Session details including:
  - session_id
  - component: "mahavishnu"
  - session_type: "admin_shell"
  - start_time
  - end_time
  - duration_seconds
  - metadata (adapters, version, etc.)

## Test Results

### Phase 1: Environment Setup
**Status**: ⏳ Pending

**Dependencies Installed**:
- session-buddy: TODO
- oneiric: TODO
- mahavishnu: TODO

**Environment Variables**:
- SESSION_BUDDY_SECRET: TODO

### Phase 2: Session-Buddy MCP Server
**Status**: ⏳ Pending

**Server Start**: TODO
**Tools Registered**: TODO
**Database Connection**: TODO

### Phase 3: Mahavishnu Shell Integration
**Status**: ⏳ Pending

**Shell Start**: TODO
**Banner Display**: TODO
**Session Start Event**: TODO
**Session End Event**: TODO

### Phase 4: Database Verification
**Status**: ⏳ Pending

**Session Record**: TODO
**Metadata Validation**: TODO
**Duration Calculation**: TODO

## Issues Found

### Issue 1: Description
**Status**: Open
**Severity**: TODO
**Description**: TODO
**Root Cause**: TODO
**Fix**: TODO
**Tested**: TODO

## Troubleshooting

### Problem: Session-Buddy MCP server fails to start
**Symptoms**: TODO
**Possible Causes**:
1. Missing dependencies
2. Port already in use
3. Configuration error
**Solutions**:
```bash
# Check dependencies
pip install -e /Users/les/Projects/session-buddy

# Check port
lsof -i :8678

# Check configuration
cat settings/session-buddy.yaml
```

### Problem: Mahavishnu shell doesn't show session tracking
**Symptoms**: TODO
**Possible Causes**:
1. Session-Buddy not running
2. MCP client not configured
3. Session tracking disabled in config
**Solutions**:
```bash
# Check Session-Buddy status
session-buddy mcp status

# Check Mahavishnu config
cat settings/mahavishnu.yaml | grep session

# Enable session tracking
# Edit settings/mahavishnu.yaml
```

### Problem: Session not recorded in database
**Symptoms**: TODO
**Possible Causes**:
1. MCP connection failed
2. SessionEventEmitter not initialized
3. Database write error
**Solutions**:
```bash
# Check MCP connection
session-buddy mcp health

# Check database
session-buddy list-sessions

# View logs
tail -f logs/session-buddy.log
```

## Conclusion

**Overall Status**: ⏳ Testing in Progress

**Session Tracking**: TODO

**Production Ready**: TODO

**Next Steps**:
1. Fix any issues found
2. Re-test after fixes
3. Document any workarounds
4. Update integration guide

## References

- Session-Buddy Documentation: `/Users/les/Projects/session-buddy/README.md`
- Mahavishnu Documentation: `/Users/les/Projects/mahavishnu/CLAUDE.md`
- Oneiric AdminShell: `/Users/les/Projects/oneiric/oneiric/shell/`
