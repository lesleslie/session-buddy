# Manual Shell Integration Test

This guide walks you through manually testing the session tracking integration.

## Prerequisites

1. Session-Buddy MCP server must be running
2. Mahavishnu must be installed
3. Oneiric must be installed

## Step 1: Verify Dependencies

```bash
# Check installations
pip show session-buddy
pip show oneiric
pip show mahavishnu
```

**Expected**: All three packages should be installed.

## Step 2: Start Session-Buddy MCP Server

```bash
cd /Users/les/Projects/session-buddy

# Generate secret if not set
export SESSION_BUDDY_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

# Start server in background
session-buddy mcp start > /tmp/session-buddy-mcp.log 2>&1 &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Verify server is running
lsof -i :8678

# Check server health
session-buddy mcp health
```

**Expected**:
- Server starts successfully
- Port 8678 is open
- Health check passes

## Step 3: List Existing Sessions (Baseline)

```bash
# List admin shell sessions BEFORE starting Mahavishnu shell
session-buddy list-sessions --type admin_shell

# Count sessions
session-buddy list-sessions --type admin_shell | wc -l
```

**Expected**: List of existing sessions (if any)

## Step 4: Start Mahavishnu Shell

```bash
cd /Users/les/Projects/mahavishnu

# Start the interactive admin shell
python -m mahavishnu shell
```

**Expected Output**:
```
Mahavishnu v0.1.0 - Admin Shell
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Adapters: prefect, llamaindex, agno
CLI Commands: Enabled (475 commands)
Tab Completion: Enabled
Session Tracking: ✓ Enabled
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Key Checks**:
- ✓ "Session Tracking: ✓ Enabled" should appear in banner
- ✓ Shell should enter IPython environment
- ✓ No errors on startup

## Step 5: Check Session in Database (While Shell is Running)

Open a new terminal window and run:

```bash
# List admin shell sessions
session-buddy list-sessions --type admin_shell

# Get the most recent session
SESSION_ID=$(session-buddy list-sessions --type admin_shell | head -1 | awk '{print $1}')
echo "Session ID: $SESSION_ID"

# Show session details
session-buddy show-session $SESSION_ID
```

**Expected**:
- ✓ New session should appear in list
- ✓ Session should have:
  - session_id
  - component: "mahavishnu"
  - session_type: "admin_shell"
  - start_time (set)
  - end_time: NULL (still running)
  - metadata (adapters, version)

## Step 6: Exit Shell and Verify Session End

Back in the Mahavishnu shell:

```python
exit()
```

**Expected**:
- ✓ Shell exits cleanly
- ✓ Session end event emitted

## Step 7: Verify Session in Database (After Exit)

```bash
# Show the session again
session-buddy show-session $SESSION_ID
```

**Expected**:
- ✓ end_time should be set
- ✓ duration_seconds should be calculated
- ✓ status should be "completed" or similar

## Step 8: Check Session Metadata

```bash
# View session metadata
session-buddy show-session $SESSION_ID | grep -A 20 "metadata"
```

**Expected Metadata Fields**:
- component: "mahavishnu"
- version: "0.1.0" (or current version)
- adapters: ["prefect", "llamaindex", "agno"] (or enabled adapters)
- session_type: "admin_shell"
- cli_preprocessing_enabled: true/false
- tab_completion_enabled: true/false
- command_tree_size: <number>

## Troubleshooting

### Issue: "Session Tracking: ✗ Disabled" in Banner

**Cause**: Session tracking is disabled in configuration.

**Fix**:
```bash
# Check Mahavishnu config
cat /Users/les/Projects/mahavishnu/settings/mahavishnu.yaml | grep -A 5 "session"

# Enable session tracking if needed
# Edit settings/mahavishnu.yaml and set:
# session:
#   enabled: true
```

### Issue: Session Not Appearing in Database

**Cause**: MCP connection failed or Session-Buddy not running.

**Fix**:
```bash
# Check Session-Buddy server status
session-buddy mcp status

# Check server logs
tail -f /tmp/session-buddy-mcp.log

# Restart server if needed
kill $SERVER_PID
session-buddy mcp start > /tmp/session-buddy-mcp.log 2>&1 &
```

### Issue: Missing Session Metadata

**Cause**: SessionEventEmitter not properly initialized.

**Fix**:
```bash
# Check Mahavishnu shell logs
# Look for errors during shell initialization

# Verify Oneiric AdminShell is properly imported
python -c "from oneiric.shell import AdminShell; print('OK')"
```

## Test Results Template

Copy this template to record your test results:

```markdown
## Test Results

**Date**: YYYY-MM-DD
**Tester**: Your Name

### Environment
- session-buddy version: X.X.X
- oneiric version: X.X.X
- mahavishnu version: X.X.X
- Python version: X.X.X

### Phase 1: Dependencies
- [ ] session-buddy installed
- [ ] oneiric installed
- [ ] mahavishnu installed

### Phase 2: Session-Buddy Server
- [ ] Server started successfully
- [ ] Port 8678 open
- [ ] Health check passed

### Phase 3: Mahavishnu Shell
- [ ] Shell started successfully
- [ ] Banner shows "Session Tracking: ✓ Enabled"
- [ ] IPython environment loaded
- [ ] No startup errors

### Phase 4: Session Start Event
- [ ] Session appeared in database
- [ ] Session ID assigned
- [ ] start_time set
- [ ] Metadata populated

### Phase 5: Session End Event
- [ ] Shell exited cleanly
- [ ] Session end_time set
- [ ] duration_seconds calculated

### Phase 6: Session Metadata
- [ ] component: "mahavishnu"
- [ ] version populated
- [ ] adapters list populated
- [ ] session_type: "admin_shell"

### Issues Found
1. [Description]
2. [Description]

### Overall Status
- [ ] PASS - All tests passed
- [ ] FAIL - Some tests failed
- [ ] PARTIAL - Some tests could not be completed

### Notes
[Any additional notes or observations]
```

## Next Steps After Testing

1. If all tests pass: Document as production-ready
2. If tests fail: Create GitHub issues with details
3. Update documentation with any workarounds
4. Re-test after fixes
