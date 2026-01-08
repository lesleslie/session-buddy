# Test Debugging Summary - January 5, 2026

## Issues Found and Fixed

### 1. ✅ FIXED: pytest-benchmark Configuration Error

**Problem**: `[tool.pytest.benchmark]` section in pyproject.toml caused "ERROR: Unknown config option: benchmark" when running tests with pytest-xdist.

**Root Cause**: pytest-benchmark plugin configuration is incompatible with pytest-xdist parallel execution. When pytest runs with `-n auto`, worker processes cannot properly load the benchmark plugin configuration.

**Solution**: Removed the `[tool.pytest.benchmark]` configuration section from pyproject.toml and added a comment explaining how to use command-line options instead:

```toml
# Note: pytest-benchmark configuration removed due to incompatibility with pytest-xdist
# When running benchmarks with -m benchmark, use command-line options instead:
# python -m pytest -m benchmark --benchmark-disable-gc --benchmark-warmup=off
```

**Result**: Reduced errors from 26 to 0.

### 2. ⚠️ WORKAROUND: pytest-xdist and DuckDB Database Locking

**Problem**: Running tests with pytest-xdist (`-n auto`) causes DuckDB database lock contention errors:

- "Could not set lock on file: Conflicting lock file"
- Tests fail with `HealthStatus.UNHEALTHY` instead of expected `HEALTHY`
- 4 test failures in health check tests

**Root Cause**: DuckDB uses file-based locking that doesn't work well with parallel test execution. Multiple xdist worker processes trying to access the same temporary database file cause lock conflicts.

**Solution Applied**: Added `-p no:xdist` to pytest addopts in pyproject.toml to disable parallel test execution by default:

```toml
[tool.pytest]
minversion = "7.0"
addopts = [
    "--tb=short",
    "--strict-markers",
    "--durations=20",
    "-p",
    "no:xdist",  # Disable xdist to avoid DuckDB lock contention
]
```

**Result**: All 1,625 tests pass when run without xdist in ~5 minutes.

### 3. ⚠️ PENDING: Crackerjack Integration

**Current Issue**: Crackerjack's test runner is hardcoded to use `-n auto --dist=loadfile`, which conflicts with the `-p no:xdist` configuration:

```
ERROR: usage: __main__.py    [...]
__main__.py: error: unrecognized arguments: -n --dist=loadfile
```

**Workaround**: Run tests directly with pytest instead of crackerjack:

```bash
python -m pytest tests/ --tb=no -q
```

**Status**: Tests pass successfully (1,625 passed, 83 skipped) when run directly.

**Next Steps**: One of the following:

1. Remove `-p no:xdist` and accept DuckDB lock issues (re-enable xdist)
1. Fix crackerjack to respect `-p no:xdist` configuration
1. Improve test isolation to use truly unique temporary databases per test

## Test Results

### With pytest (no xdist)

- ✅ 1,625 tests passed
- ⏭ 83 tests skipped (performance tests requiring `-m benchmark`)
- ⏱ Duration: ~5 minutes
- 💥 0 errors

### With crackerjack (current state)

- ❌ Error: "unrecognized arguments: -n --dist=loadfile"
- Tests cannot complete due to configuration conflict

## Recommendations

1. **Keep `-p no:xdist` in pytest addopts** - Tests are reliable and fast enough without parallel execution
1. **Use pytest directly** for now: `python -m pytest tests/`
1. **For CI/CD**: Use `python -m pytest -m "not slow"` for faster feedback during development
1. **For benchmarks**: Run separately with `python -m pytest -m benchmark --benchmark-disable-gc`

## Performance Test Execution

Performance tests are properly marked with `@pytest.mark.benchmark` and skipped by default. To run them:

```bash
# Run all performance benchmarks
python -m pytest -m benchmark --benchmark-disable-gc --benchmark-warmup=off

# Run specific benchmark test
python -m pytest tests/performance/test_benchmarks.py::TestPerformanceBenchmarks::test_conversation_storage_performance -m benchmark -v
```

## Test Coverage

Current test coverage: **1,625 passing tests** across:

- Unit tests: Core functionality, database operations, quality scoring
- Integration tests: MCP tool registration, session workflows, health checks
- Functional tests: End-to-end session lifecycle
- Security tests: Input validation, permission security, database security
- Property-based tests: Hypothesis tests for database operations

Coverage target: 85% (maintained in tool.coverage.report)
