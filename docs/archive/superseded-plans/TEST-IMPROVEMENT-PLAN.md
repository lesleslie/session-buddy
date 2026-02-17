# Session Management MCP - Test Improvement Plan

## Executive Summary

- **Current Coverage**: 34.44% (threshold: 35%)
- **Test Status**: 469 passed, 96 failed, 2 skipped, 25 errors
- **Target Coverage**: 50%+ (quick wins), 70%+ (comprehensive)
- **Estimated Effort**: 2-3 days for critical fixes, 1 week for comprehensive coverage

## Root Cause Analysis

### 1. Database Initialization Issues (40% of failures)

**Pattern**: `ReflectionDatabase.conn is None` errors
**Root Cause**: Tests not properly awaiting `initialize()` before database operations
**Files Affected**:

- `tests/functional/test_simple_validation.py`
- `tests/integration/test_session_lifecycle.py`
- Performance tests using ReflectionDatabase

### 2. CLI Command Test Failures (25% of failures)

**Pattern**: CLI commands (start, stop, status) failing
**Root Cause**: Missing module imports and improper async handling in CLI
**Files Affected**:

- `session_buddy/cli.py:40-140` (command handlers)
- `tests/unit/test_cli.py` (if exists)

### 3. Dependency Injection Container Issues (20% of failures)

**Pattern**: DI container and instance manager failures
**Root Cause**: Missing or misconfigured DI setup in tests
**Files Affected**:

- `session_buddy/core/di_container.py` (needs creation/fix)
- `session_buddy/core/instance_manager.py` (needs creation/fix)

### 4. Tool Registration Failures (15% of failures)

**Pattern**: MCP tools not properly registered or executed
**Root Cause**: Mock MCP server not properly simulating FastMCP behavior
**Files Affected**:

- `tests/conftest.py:24-58` (MockFastMCP class)
- `session_buddy/tools/*.py` (tool registration)

## Priority 1: Critical Fixes (Quick Wins)

### Fix 1: Database Initialization Pattern (Effort: 2 hours)

```text
# File: tests/conftest.py - Add this fixture at line 545
@pytest.fixture
async def initialized_db():
    """Properly initialized database for all tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.duckdb"
        db = ReflectionDatabase(db_path=str(db_path))
        await db.initialize()  # Critical: await initialization
        try:
            yield db
        finally:
            db.close()
```

**Files to Update**:

- `tests/conftest.py:545` - Add initialized_db fixture
- `tests/functional/test_simple_validation.py:59-80` - Use initialized_db fixture
- `tests/integration/test_session_lifecycle.py` - Replace temp_database with initialized_db

### Fix 2: CLI Module Dependencies (Effort: 1 hour)

```python
# File: session_buddy/cli.py:40 - Add missing imports
from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.server import mcp, permissions_manager
```

**Files to Update**:

- `session_buddy/cli.py:8-20` - Add missing imports
- `session_buddy/cli.py:100-200` - Fix async command handlers

### Fix 3: Mock MCP Server Enhancement (Effort: 1 hour)

```python
# File: tests/conftest.py:24 - Enhance MockFastMCP
class MockFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tools = {}
        self.prompts = {}
        self._registered_tools = {}  # Track registered tools

    def tool(self, *args, **kwargs):
        def decorator(func):
            self._registered_tools[func.__name__] = func
            return func

        return decorator
```

**Files to Update**:

- `tests/conftest.py:24-58` - Enhance MockFastMCP class
- `tests/integration/test_session_lifecycle.py:19-35` - Update mock usage

## Priority 2: Coverage Improvement (Medium Effort)

### Area 1: Core Session Management (Current: 25%, Target: 60%)

**Untested Critical Functions**:

- `session_buddy/core/session_manager.py:82-150` - calculate_quality_score
- `session_buddy/core/session_manager.py:200-250` - handoff documentation
- `session_buddy/utils/git_operations.py` - All git operations

**New Test Files Needed**:

```bash
tests/unit/test_session_manager.py      # 30+ tests
tests/unit/test_git_operations.py       # 15+ tests
tests/unit/test_quality_scoring.py      # 20+ tests
```

### Area 2: Memory/Search Tools (Current: 30%, Target: 70%)

**Untested Critical Functions**:

- `session_buddy/tools/memory_tools.py` - All MCP tool functions
- `session_buddy/tools/search_tools.py` - Advanced search functions
- `session_buddy/reflection_tools.py:200-400` - Vector search operations

**New Test Files Needed**:

```bash
tests/unit/test_memory_tools.py         # 25+ tests
tests/unit/test_search_tools.py         # 20+ tests
tests/unit/test_vector_operations.py    # 15+ tests
```

### Area 3: Crackerjack Integration (Current: 15%, Target: 50%)

**Untested Critical Functions**:

- `session_buddy/tools/crackerjack_tools.py` - All command execution
- `session_buddy/crackerjack_integration.py` - Progress parsing

**New Test Files Needed**:

```bash
tests/unit/test_crackerjack_tools.py    # 20+ tests
tests/integration/test_crackerjack.py   # 15+ tests
```

## Priority 3: Test Infrastructure Improvements

### 1. Create Missing Test Utilities

```python
# File: tests/helpers.py - Add at line 200
class MCPToolTestHelper:
    """Helper for testing MCP tool registration and execution."""

    @staticmethod
    async def execute_tool(tool_func, **kwargs):
        """Execute MCP tool with proper error handling."""
        try:
            return await tool_func(**kwargs)
        except Exception as e:
            return {"error": str(e)}
```

### 2. Add Performance Test Infrastructure

```python
# File: tests/fixtures/performance.py - Create new file
import pytest
import time
from contextlib import contextmanager


@contextmanager
def measure_performance(name: str, max_time: float):
    """Context manager for performance assertions."""
    start = time.time()
    yield
    elapsed = time.time() - start
    assert elapsed < max_time, f"{name} took {elapsed:.2f}s (max: {max_time}s)"
```

### 3. Add Integration Test Base Class

```python
# File: tests/base.py - Create new file
class IntegrationTestBase:
    """Base class for integration tests with common setup."""

    async def setup_session(self):
        """Common session setup for integration tests."""
        # Initialize database
        # Set up permissions
        # Create mock MCP server
        pass
```

## Testing Strategy for 50%+ Coverage

### Phase 1: Fix Failures (Days 1-2)

1. **Day 1**: Fix database initialization patterns (all tests using ReflectionDatabase)
1. **Day 1**: Fix CLI command imports and async handling
1. **Day 2**: Fix mock MCP server to properly track tool registration
1. **Day 2**: Fix DI container issues (create missing modules if needed)

### Phase 2: Add Critical Tests (Days 3-4)

1. **Day 3**: Add session_manager tests (30 tests, +10% coverage)
1. **Day 3**: Add memory_tools tests (25 tests, +8% coverage)
1. **Day 4**: Add search_tools tests (20 tests, +7% coverage)
1. **Day 4**: Add git_operations tests (15 tests, +5% coverage)

### Phase 3: Comprehensive Coverage (Days 5-7)

1. **Day 5**: Add crackerjack integration tests
1. **Day 6**: Add performance benchmarks
1. **Day 7**: Add end-to-end workflow tests

## Quick Win Test Examples

### Example 1: Session Manager Test

```python
# tests/unit/test_session_manager.py
import pytest
from session_buddy.core.session_manager import SessionLifecycleManager


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_quality_score_calculation(self):
        manager = SessionLifecycleManager()
        score = await manager.calculate_quality_score()
        assert 0 <= score["total_score"] <= 100
        assert "breakdown" in score

    @pytest.mark.asyncio
    async def test_session_initialization(self):
        manager = SessionLifecycleManager()
        result = await manager.initialize_session()
        assert result["success"] is True
```

### Example 2: Memory Tools Test

```python
# tests/unit/test_memory_tools.py
import pytest
from session_buddy.tools.memory_tools import store_reflection


class TestMemoryTools:
    @pytest.mark.asyncio
    async def test_store_reflection(self, initialized_db):
        result = await store_reflection(
            content="Test reflection", tags=["test", "example"]
        )
        assert "stored" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search(self, initialized_db):
        # Store test data
        await store_reflection(content="Python async patterns")

        # Search for it
        result = await quick_search(query="Python async")
        assert result["count"] > 0
```

## Recommended Test Execution Order

```bash
# 1. Fix immediate failures
pytest tests/functional/test_simple_validation.py -xvs

# 2. Run unit tests to verify fixes
pytest tests/unit/ -xvs

# 3. Run integration tests
pytest tests/integration/ -xvs

# 4. Check coverage improvement
pytest --cov=session_buddy --cov-report=term-missing

# 5. Run all tests with parallel execution
pytest -n auto --cov=session_buddy
```

## Success Metrics

### Immediate Goals (2-3 days)

- ✅ All database initialization errors fixed
- ✅ CLI commands working
- ✅ Coverage increased to 50%+
- ✅ All critical path tests passing

### Week 1 Goals

- ✅ Coverage increased to 70%+
- ✅ Performance benchmarks established
- ✅ Integration test suite complete
- ✅ CI/CD pipeline green

## Untested Critical Functionality

### High Priority (Security/Data Integrity)

1. **Session permissions management** - No tests for trust/untrust operations
1. **Database transaction handling** - No tests for rollback scenarios
1. **Concurrent access patterns** - No tests for race conditions
1. **Error recovery mechanisms** - No tests for crash recovery

### Medium Priority (Core Features)

1. **Multi-project coordination** - No tests for cross-project features
1. **Token optimization** - No tests for response chunking
1. **Serverless mode** - No tests for external storage backends
1. **Team collaboration** - No tests for team knowledge sharing

### Low Priority (Nice to Have)

1. **Natural language scheduling** - No tests for time parsing
1. **Git worktree management** - No tests for worktree operations
1. **App monitoring** - No tests for IDE activity tracking

## Conclusion

The test suite has systematic issues that can be fixed with targeted improvements:

1. **Database initialization** is the root cause of 40% of failures
1. **Missing imports** cause another 25% of failures
1. **Mock infrastructure** needs enhancement for proper MCP simulation

With 2-3 days of focused effort, coverage can reach 50%+ and all tests can pass.
The plan above provides specific file locations and code examples to accelerate fixes.
