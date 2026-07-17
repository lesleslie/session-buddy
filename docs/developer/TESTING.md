---
status: complete
role: canonical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: lifecycle
---

# Testing Guide

This document provides comprehensive guidance on testing the Session Management MCP server, including strategy, current status, and quality standards.

## Quick Reference

```bash
# Run full test suite with coverage
pytest --cov=session_buddy --cov-report=term-missing

# Quick smoke tests (exclude slow tests)
pytest -m "not slow"

# Run specific test categories
pytest tests/unit/                    # Unit tests only
pytest tests/integration/             # Integration tests only
pytest -m performance                 # Performance tests only

# Coverage with fail threshold
pytest --cov=session_buddy --cov-fail-under=85
```

**Coverage Targets:**

- Overall: 85%+
- Critical components (ReflectionDatabase, SessionManager): 95%+
- New code: 100% required

______________________________________________________________________

## Current Status

### Coverage Metrics

- **Current Coverage**: ~14.7% (improving from initial 11.66%)
- **Target Coverage**: 85% overall, 95% for critical components
- **Test Pass Rate**: 90%+ for implemented suites

### Well-Covered Areas (✅)

- **Reflection Tools** (55%) - Database operations, storage, search
- **Memory Tools** (80%) - MCP tool interfaces, search features
- **Worktree Manager** (74%) - Operations, session preservation, git integration
- **SessionLifecycleManager** - Quality assessment, checkpoints, status reporting

### Areas Needing Attention (⚠️)

**Critical Components with No Coverage:**

- InterruptionManager (0% - 353 lines)
- NaturalScheduler (0% - 338 lines)
- TeamKnowledge (0% - 284 lines)

**Low-Coverage Core Modules:**

- AdvancedSearch (16.88%) - 16/24 tests passing, needs filtering/sorting implementation
- MultiProjectCoordinator (21.43%) - Cross-project functionality
- TokenOptimizer (13.20%) - Token management and chunking
- SessionManager (62.07%) - Core session operations

### Recent Improvements

**Infrastructure Fixes Completed:**

- ✅ Fixed database initialization issues in tests
- ✅ Resolved DuckDB connection and syntax problems
- ✅ Updated SessionPermissionsManager constructor handling
- ✅ Fixed import and fixture errors across test suites
- ✅ Implemented proper logging configuration for tests

**New Test Suites:**

- ✅ Reflection Tools Tests - 83 test cases (21/24 passing)
- ✅ Memory Tools Tests - 30 test cases (comprehensive coverage)
- ✅ Worktree Manager Tests - 32 test cases (edge cases included)
- ✅ SessionLifecycleManager Tests - Complete workflow coverage

______________________________________________________________________

## Testing Strategy

### Test Categories

#### 1. Unit Tests (`tests/unit/`)

**Focus:** Isolated functionality testing

- Test individual functions and methods
- Mock external dependencies
- 100% coverage of public API
- Fast execution (< 1 second per test)

**Example:**

```text
def test_reflection_storage():
    """Test basic reflection storage."""
    async with ReflectionDatabase() as db:
        reflection_id = await db.store_reflection("Test content")
        assert reflection_id is not None
```

#### 2. Integration Tests (`tests/integration/`)

**Focus:** Component interaction and workflows

- Test cross-component functionality
- Verify MCP tool registration and execution
- Test database integration with real operations
- Critical paths and user journeys

**Example:**

```python
async def test_session_lifecycle_integration():
    """Test complete session workflow."""
    # Start → Work → Checkpoint → End
    result = await start_session()
    await create_checkpoint()
    summary = await end_session()
    assert summary["success"]
```

#### 3. Functional Tests (`tests/functional/`)

**Focus:** End-to-end functionality

- User-facing features from user perspective
- Complete feature workflows
- Real-world usage scenarios

#### 4. Performance Tests (`tests/performance/`)

**Focus:** Scalability and resource usage

- Response time benchmarks
- Memory usage monitoring
- High-load scenario testing
- Tools: pytest-benchmark

#### 5. Security Tests (`tests/security/`)

**Focus:** Security aspects

- Input validation and sanitization
- Access control verification
- Injection attack protection
- Tools: pytest, bandit

#### 6. Property-Based Tests

**Focus:** Robustness with random inputs

- Edge cases and boundary conditions
- Input validation stress testing
- Concurrency testing
- Tools: Hypothesis

### Test Structure Guidelines

**File Organization:**

```
tests/
├── unit/           # Isolated component tests
├── integration/    # Cross-component tests
├── functional/     # End-to-end feature tests
├── performance/    # Benchmark tests
├── security/       # Security-focused tests
├── conftest.py     # Shared fixtures and configuration
└── helpers.py      # Test utilities and factories
```

**Naming Conventions:**

- Test files: `test_*.py`
- Test classes: `Test[ComponentName][TestType]`
- Test methods: `test_[action]_[expected_result]`

**Test Data Management:**

- Use temporary directories for file operations
- Mock external dependencies (APIs, file systems)
- Clean up resources in teardown
- Use pytest fixtures for reusable test setup

______________________________________________________________________

## Implementation Roadmap

### Phase 1: Critical Missing Tests (Weeks 1-2)

**Priority: HIGH**

1. **Complete AdvancedSearch Tests** ✅ In Progress

   - Fix remaining 8 failing tests
   - Implement content type filtering
   - Add sorting functionality
   - Implement timeframe-based filtering

1. **InterruptionManager Testing** 📅 Not Started

   - Create `tests/unit/test_interruption_manager.py`
   - Test context preservation and recovery
   - Test file system monitoring
   - Test activity pattern detection

1. **NaturalScheduler Testing** 📅 Not Started

   - Create `tests/unit/test_natural_scheduler.py`
   - Test time expression parsing
   - Test reminder creation and execution
   - Test background service operations

### Phase 2: Core Feature Expansion (Weeks 2-3)

**Priority: MEDIUM**

1. **MultiProjectCoordinator Testing**

   - Test project group management
   - Test dependency tracking
   - Test cross-project search
   - Test session linking

1. **TokenOptimizer Testing**

   - Test token counting accuracy
   - Test optimization strategies
   - Test caching mechanisms
   - Test chunking for large content

1. **Parameter Validation Testing**

   - Test all validation models
   - Test edge cases and invalid inputs
   - Test data normalization

### Phase 3: Integration & Advanced Testing (Weeks 3-4)

**Priority: MEDIUM-LOW**

1. **Integration Test Suites**

   - Memory and search integration
   - Worktree management workflows
   - Session lifecycle end-to-end

1. **Performance Baselines**

   - Reflection database operations
   - Search performance with large datasets
   - Worktree operations

### Phase 4: Quality & Security (Weeks 4-5)

**Priority: LOW (Future Work)**

1. **Security Testing**

   - Input validation comprehensive testing
   - Access control verification
   - Injection attack scenarios

1. **Property-Based Testing**

   - Use Hypothesis for generative testing
   - Test concurrency edge cases
   - Boundary condition exploration

______________________________________________________________________

## Quality Standards

### Code Coverage Requirements

| Component Type | Target Coverage | Status |
|---|---|---|
| Overall Project | 85%+ | 14.7% ⚠️ |
| Critical Modules | 95%+ | Varies |
| Reflection Tools | 95%+ | 55% 🔄 |
| Memory Tools | 95%+ | 80% ✅ |
| Worktree Manager | 95%+ | 74% 🔄 |
| New Code | 100% | Required |

### Test Quality Metrics

**Performance:**

- Unit tests: < 1 second execution time
- Integration tests: < 5 seconds execution time
- Full suite: < 5 minutes total

**Reliability:**

- Test pass rate: 100%
- Flaky test rate: < 10%
- Test determinism: Required

**Maintainability:**

- Clear, descriptive test names
- Comprehensive docstrings
- Minimal test duplication
- Well-documented fixtures

### Documentation Standards

All test files must include:

- Module-level docstring explaining purpose
- Complex scenario documentation
- Fixture documentation with examples
- Clear assertion messages

### Continuous Integration

**Requirements:**

- All tests run in CI pipeline
- Parallel test execution enabled
- Coverage reports generated automatically
- Performance regression detection

______________________________________________________________________

## Success Metrics

### Short-term Goals (Next 2-3 weeks)

- ✅ Fix all AdvancedSearch test failures
- ⏳ Implement missing functionality (filtering, sorting)
- ⏳ Reach 25%+ overall coverage
- ⏳ Zero failing tests in CI

### Medium-term Goals (Next 1-2 months)

- 📅 Complete all critical component tests
- 📅 Implement integration test suites
- 📅 Reach 50%+ overall coverage
- 📅 Establish performance baselines

### Long-term Goals (Next quarter)

- 📅 Achieve 85%+ overall coverage
- 📅 Complete security testing
- 📅 Full CI/CD integration
- 📅 Property-based test coverage

______________________________________________________________________

## Common Testing Patterns

### Async Test Pattern

```text
import pytest


@pytest.mark.asyncio
async def test_async_operation():
    """Test asynchronous database operation."""
    async with ReflectionDatabase() as db:
        result = await db.some_async_operation()
        assert result is not None
```

### Fixture Usage

```text
@pytest.fixture
async def temp_database():
    """Provide temporary database for testing."""
    db_path = tempfile.mktemp(suffix=".duckdb")
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)
```

### Mocking External Dependencies

```text
from unittest.mock import patch, MagicMock


def test_with_mocked_git():
    """Test git operations with mocked subprocess."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="mocked output")
        result = perform_git_operation()
        assert result == "expected"
```

______________________________________________________________________

## Troubleshooting

### Common Test Issues

**Issue: Tests failing with DuckDB connection errors**

```text
# Solution: Use temporary database in fixtures
@pytest.fixture
async def db():
    db_path = tempfile.mktemp(suffix=".duckdb")
    async with ReflectionDatabase(db_path=db_path) as database:
        yield database
```

**Issue: Async tests not running**

```python
# Solution: Add pytest-asyncio marker
@pytest.mark.asyncio
async def test_function(): ...
```

**Issue: Flaky tests due to timing**

```python
# Solution: Use proper async/await patterns
await asyncio.sleep(0.1)  # Give time for async operations
```

### Running Specific Tests

```bash
# Single test file
pytest tests/unit/test_reflection_tools.py -v

# Single test function
pytest tests/unit/test_reflection_tools.py::test_store_reflection -v

# Tests matching pattern
pytest -k "reflection" -v

# With debugging
pytest tests/unit/test_reflection_tools.py -v -s --pdb
```

______________________________________________________________________

## Resources

**Documentation:**

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Hypothesis](https://hypothesis.readthedocs.io/)

**Project Files:**

- Test configuration: `pyproject.toml` (tool.pytest.ini_options)
- Shared fixtures: `tests/conftest.py`
- Test utilities: `tests/helpers.py`

**Coverage Reports:**

```bash
# Generate HTML coverage report
pytest --cov=session_buddy --cov-report=html

# Open coverage report
open htmlcov/index.html
```

______________________________________________________________________

**Last Updated:** 2025-01-04
**Current Coverage:** 14.7%
**Next Milestone:** 25% coverage with AdvancedSearch completion
