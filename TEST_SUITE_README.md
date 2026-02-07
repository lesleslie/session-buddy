# Session Tracking Integration Test Suite

Complete end-to-end testing suite for Session-Buddy and Mahavishnu session tracking integration.

## Quick Start

```bash
# Run automated tests (2 minutes)
cd /Users/les/Projects/session-buddy
python test_session_tracking_integration.py

# Run manual shell test (5 minutes)
# Follow: manual_shell_test.md
```

## Test Suite Structure

```
session-buddy/
├── test_session_tracking_integration.py  # Automated test suite
├── test_e2e.sh                           # Bash test script
├── run_integration_test.sh               # Quick test runner
├── manual_shell_test.md                  # Manual test guide
├── SESSION_TRACKING_TEST_REPORT.md       # Comprehensive test report
├── SESSION_TRACKING_E2E_TEST.md          # Detailed test plan
└── TESTING_SUMMARY.md                    # Quick summary
```

## Test Coverage

### Phase 1: Environment Setup
- Package installations (session-buddy, oneiric, mahavishnu)
- Version validation
- Dependency checking

### Phase 2: Session-Buddy MCP Server
- Server startup
- Port availability (8678)
- Health endpoint
- Database connectivity

### Phase 3: Mahavishnu Shell Integration
- Shell startup
- Banner display
- Session tracking status
- IPython environment

### Phase 4: Database Verification
- Session recording
- Session metadata
- Duration calculation
- Lifecycle events

## Running Tests

### Option 1: Automated Tests Only

```bash
cd /Users/les/Projects/session-buddy
python test_session_tracking_integration.py
```

**Output**: `test_results.json`

### Option 2: Manual Shell Test

See `manual_shell_test.md` for step-by-step instructions.

### Option 3: Full Test Suite

```bash
# 1. Automated tests
python test_session_tracking_integration.py

# 2. Manual shell test
# (follow manual_shell_test.md)

# 3. Document results
# (use test results template in manual_shell_test.md)
```

## Expected Results

### Success Criteria

1. **Automated Tests**: All pass
2. **Shell Startup**: Clean start, banner shows "Session Tracking: ✓ Enabled"
3. **Session Recording**: Session appears in database
4. **Session Metadata**: All fields populated
5. **Session Completion**: end_time set, duration calculated

### Test Report

After testing, you should have:

- `test_results.json` - Automated test results
- Manual test results (documented in markdown)
- Session ID and metadata from database
- List of any issues found

## Architecture

```
User → Mahavishnu Shell → SessionEventEmitter → Session-Buddy MCP → DuckDB
```

### Components

1. **Mahavishnu Shell** (`mahavishnu/shell/adapter.py`)
   - IPython-based admin shell
   - Extends Oneiric AdminShell
   - Emits session events

2. **SessionEventEmitter** (`oneiric/shell/session_tracker.py`)
   - Tracks session lifecycle
   - Connects to MCP server
   - Sends start/end events

3. **Session-Buddy MCP Server** (`session-buddy/`)
   - MCP protocol server
   - Exposes session tracking tools
   - Stores in DuckDB

## Dependencies

Required packages:
- `session-buddy>=0.13.0`
- `oneiric>=0.3.12`
- `mahavishnu>=0.1.0`

Install with:
```bash
pip install -e /Users/les/Projects/session-buddy
pip install -e /Users/les/Projects/oneiric
pip install -e /Users/les/Projects/mahavishnu
```

## Troubleshooting

### Common Issues

**Issue**: Tests fail with "package not found"
**Fix**: Reinstall packages (see Dependencies above)

**Issue**: Server won't start
**Fix**:
```bash
# Check port
lsof -i :8678

# Kill existing
kill $(lsof -ti:8678)

# Restart
session-buddy mcp start
```

**Issue**: Session not recorded
**Fix**:
```bash
# Check server health
session-buddy mcp health

# Check logs
tail -f /tmp/session-buddy-mcp.log
```

See `manual_shell_test.md` for detailed troubleshooting.

## Documentation

- **`TESTING_SUMMARY.md`** - Quick start guide
- **`SESSION_TRACKING_TEST_REPORT.md`** - Comprehensive test strategy
- **`manual_shell_test.md`** - Step-by-step manual test
- **`SESSION_TRACKING_E2E_TEST.md`** - Detailed test plan

## Support

For issues or questions:
1. Check troubleshooting section in `manual_shell_test.md`
2. Review test report in `SESSION_TRACKING_TEST_REPORT.md`
3. Check Session-Buddy documentation
4. Check Mahavishnu documentation

## License

See individual project repositories for license information.

---

**Last Updated**: 2025-02-06
**Status**: Ready for Testing
