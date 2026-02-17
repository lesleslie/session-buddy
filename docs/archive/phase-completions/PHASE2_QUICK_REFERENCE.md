# Phase 2 Test Quick Reference

## Quick Commands

### Run All Phase 2 Tests
```bash
cd /Users/les/Projects/session-buddy

# Run all MCP tools and CLI tests
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -v

# Run with coverage report
pytest tests/unit/test_mcp/ tests/unit/test_cli/ --cov=session_buddy.mcp.tools --cov=session_buddy.cli --cov-report=html

# Run with coverage to terminal
pytest tests/unit/test_mcp/ tests/unit/test_cli/ --cov=session_buddy.mcp.tools --cov=session_buddy.cli --cov-report=term-missing
```

### Session Tools Tests
```bash
# All session tools tests
pytest tests/unit/test_mcp/test_session_tools.py -v

# Specific test class
pytest tests/unit/test_mcp/test_session_tools.py::TestSessionTools -v

# Specific test
pytest tests/unit/test_mcp/test_session_tools.py::TestSessionTools::test_start_tool_success -v

# Integration tests only
pytest tests/unit/test_mcp/test_session_tools.py::TestSessionToolIntegration -v
```

### Memory Tools Tests
```bash
# All memory tools tests
pytest tests/unit/test_mcp/test_memory_tools.py -v

# Storage tools only
pytest tests/unit/test_mcp/test_memory_tools.py::TestReflectionStorageTools -v

# Search tools only
pytest tests/unit/test_mcp/test_memory_tools.py::TestSearchTools -v

# Edge cases only
pytest tests/unit/test/mcp/test_memory_tools.py::TestMemoryToolEdgeCases -v
```

### CLI Tests
```bash
# All CLI tests
pytest tests/unit/test_cli/test_cli_commands.py -v

# Server commands only
pytest tests/unit/test_cli/test_cli_commands.py::TestCLIServerCommands -v

# Error handling only
pytest tests/unit/test_cli/test_cli_commands.py::TestCLIErrorHandling -v
```

## Test Breakdown

| Test Suite | File | Test Count | Coverage |
|------------|------|------------|----------|
| Session Tools | `test_session_tools.py` | 18 | 75-80% |
| Memory Tools | `test_memory_tools.py` | 34 | 70-75% |
| CLI Commands | `test_cli_commands.py` | 30 | 80-85% |
| **TOTAL** | **3 files** | **82 tests** | **~75% avg** |

## Key Test Files

- `/Users/les/Projects/session-buddy/tests/unit/test_mcp/test_session_tools.py`
- `/Users/les/Projects/session-buddy/tests/unit/test_mcp/test_memory_tools.py`
- `/Users/les/Projects/session-buddy/tests/unit/test_cli/test_cli_commands.py`

## Running with Different Options

### Verbose Output
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -vv
```

### Show Print Statements
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -v -s
```

### Stop on First Failure
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -x
```

### Run Failed Tests Only
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ --lf
```

### Run Last Failed Tests First
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ --ff
```

## Coverage Analysis

### Generate HTML Coverage Report
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ \
  --cov=session_buddy.mcp.tools \
  --cov=session_buddy.cli \
  --cov-report=html \
  --cov-report=term

# Open report (macOS)
open htmlcov/index.html
```

### Coverage for Specific Module
```bash
# Session tools only
pytest tests/unit/test_mcp/test_session_tools.py \
  --cov=session_buddy.mcp.tools.session.session_tools \
  --cov-report=term-missing

# Memory tools only
pytest tests/unit/test_mcp/test_memory_tools.py \
  --cov=session_buddy.mcp.tools.memory.memory_tools \
  --cov-report=term-missing

# CLI only
pytest tests/unit/test_cli/test_cli_commands.py \
  --cov=session_buddy.cli \
  --cov-report=term-missing
```

## Debugging Failed Tests

### Run with PDB on Failure
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ --pdb
```

### Show Local Variables on Failure
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -l
```

### Show Extra Traceback Info
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ --tb=long
```

## Parallel Execution

### Run with pytest-xdist (if installed)
```bash
# Use all available CPUs
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -n auto

# Use specific number of workers
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -n 4
```

## Markers and Filtering

### Run Only Async Tests
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -m asyncio
```

### Run Only Unit Tests
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -m unit
```

### Skip Slow Tests
```bash
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -m "not slow"
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run Phase 2 Tests
  run: |
    pytest tests/unit/test_mcp/ tests/unit/test_cli/ \
      --cov=session_buddy.mcp.tools \
      --cov=session_buddy.cli \
      --cov-report=xml \
      --junitxml=test-results.xml
```

### GitLab CI Example
```yaml
test:phase2:
  script:
    - pytest tests/unit/test_mcp/ tests/unit/test_cli/ --cov --cov-report=term
  artifacts:
    reports:
      junit: test-results.xml
```

## Expected Test Results

### All Tests Passing
```
tests/unit/test_mcp/test_session_tools.py::TestSessionTools::test_start_tool_success PASSED
tests/unit/test_mcp/test_session_tools.py::TestSessionTools::test_start_tool_failure PASSED
tests/unit/test_mcp/test_session_tools.py::TestSessionTools::test_checkpoint_tool_success PASSED
...

======================== 82 passed in 15.23s ========================
```

### Coverage Report
```
Name                                                         Stmts   Miss  Cover
----------------------------------------------------------------------------------------
session_buddy/mcp/tools/session/session_tools.py                250     60    76%
session_buddy/mcp/tools/memory/memory_tools.py                  400    100    75%
session_buddy/cli.py                                             80     15    81%
----------------------------------------------------------------------------------------
TOTAL                                                          730    175    76%
```

## Troubleshooting

### Import Errors
```bash
# Ensure you're in the correct directory
cd /Users/les/Projects/session-buddy

# Install dependencies
pip install -e ".[dev]"

# Run from project root
pytest tests/unit/test_mcp/ tests/unit/test_cli/
```

### Database Lock Errors
```bash
# Tests use temporary databases, but if you see lock errors:
pytest tests/unit/test_mcp/ tests/unit/test_cli/ --forked
```

### Asyncio Errors
```bash
# Ensure async tests are marked properly
pytest tests/unit/test_mcp/ tests/unit/test_cli/ -m asyncio -v
```

## Next Steps

After Phase 2 tests are passing:

1. **Phase 3**: Integration tests
2. **Phase 4**: Performance tests
3. **Phase 5**: Security tests

See `PHASE2_MCP_TOOLS_TESTS_COMPLETE.md` for detailed documentation.
