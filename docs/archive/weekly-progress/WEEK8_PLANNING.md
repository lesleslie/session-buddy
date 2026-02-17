# Week 8 - Test Coverage & Quality Improvement

**Status:** Planning
**Start Date:** 2025-10-29
**Estimated Duration:** 5-7 days
**Objective:** Increase test coverage from 14.4% to 80%+ and fix test isolation issues

______________________________________________________________________

## Executive Summary

Following the successful Week 7 ACB DI refactoring (production-ready, 99.6% test pass rate), Week 8 focuses on addressing the critical gap identified in the checkpoint: **test coverage at 14.4% (target: 80%+)**.

**Key Challenge:** While 954/978 tests pass (99.6%), overall code coverage is only 14.4%, indicating large portions of the codebase lack comprehensive tests.

______________________________________________________________________

## Current State Assessment

### Test Suite Status (from Week 7 completion)

**Unit Tests:**

- **Total tests:** 978 unit tests
- **Passing:** 954 (97.5%)
- **Failing:** 4-8 (test isolation issues)
- **Skipped:** 20
- **Coverage:** 14.4% (critical gap)

**DI Infrastructure (Week 7):**

- ✅ 25/25 DI tests passing (100%)
- ✅ SessionPaths fully tested
- ✅ Direct container access pattern validated

**Known Failing Tests:**

```
FAILED tests/unit/test_di_container.py::test_configure_registers_singletons
FAILED tests/unit/test_instance_managers.py::test_get_app_monitor_registers_singleton
FAILED tests/unit/test_instance_managers.py::test_get_llm_manager_uses_di_cache
FAILED tests/unit/test_instance_managers.py::test_serverless_manager_uses_config
FAILED tests/unit/test_server.py::TestServerQualityScoring::test_calculate_quality_score_with_no_args
FAILED tests/unit/test_server.py::TestServerQualityScoring::test_quality_score_returns_numeric
FAILED tests/unit/test_server.py::TestServerConcurrency::test_concurrent_quality_scoring
FAILED tests/unit/test_session_manager.py::TestSessionLifecycleManagerHandoffDocumentation::test_read_previous_session_info
```

**Root Cause:** Test isolation issues (tests pass individually but fail in suite due to shared DI state).

______________________________________________________________________

## Week 8 Objectives

### Primary Goal

**Increase test coverage from 14.4% to 80%+** through systematic test expansion

### Secondary Goals

1. Fix 4-8 test isolation issues
1. Establish test coverage baselines by module
1. Create test coverage improvement plan
1. Document testing patterns and best practices

### Success Criteria

- ✅ Test coverage ≥80% (target: 85%+)
- ✅ All test isolation issues resolved
- ✅ Test pass rate maintained at ≥99%
- ✅ No regressions introduced
- ✅ Comprehensive testing documentation created

______________________________________________________________________

## Coverage Gap Analysis

### Modules with Low Coverage (\<50%)

Based on checkpoint analysis, priority modules needing coverage:

**High Priority (Core Functionality):**

1. `server.py` (~3,500+ lines) - **Critical gap**

   - MCP tool registration
   - Session lifecycle management
   - Quality scoring algorithms

1. `reflection_tools.py` - **Critical gap**

   - DuckDB database operations
   - Embedding generation
   - Search functionality

1. `crackerjack_integration.py` - **Critical gap**

   - Command parsing
   - Quality metric aggregation
   - Test result analysis

**Medium Priority (Advanced Features):**
4\. `tools/` modules - **Moderate gap**

- session_tools.py
- memory_tools.py
- crackerjack_tools.py
- llm_tools.py
- team_tools.py

5. `core/session_manager.py` - **Moderate gap**
   - Session state management
   - Lifecycle coordination

**Lower Priority (Extended Features):**
6\. `multi_project_coordinator.py`
7\. `token_optimizer.py`
8\. `search_enhanced.py`
9\. `interruption_manager.py`
10\. `serverless_mode.py`
11\. `app_monitor.py`
12\. `natural_scheduler.py`
13\. `worktree_manager.py`

______________________________________________________________________

## Week 8 Implementation Plan

### Day 0: Analysis & Planning (2 hours)

**Objectives:**

- Generate detailed coverage report by module
- Identify specific untested code paths
- Create prioritized test implementation plan
- Set up coverage tracking infrastructure

**Tasks:**

1. Run comprehensive coverage analysis

   ```bash
   coverage run -m pytest tests/unit/
   coverage report --sort=cover
   coverage html  # For detailed inspection
   ```

1. Document coverage gaps by module

   - Create `docs/WEEK8_COVERAGE_BASELINE.md`
   - List specific functions/classes needing tests
   - Prioritize by criticality

1. Set up coverage tracking

   - Configure pytest-cov with fail-under threshold
   - Create coverage improvement tracking spreadsheet

**Deliverables:**

- `docs/WEEK8_PLANNING.md` (this document)
- `docs/WEEK8_COVERAGE_BASELINE.md`
- Coverage HTML report (`htmlcov/index.html`)

______________________________________________________________________

### Day 1: Fix Test Isolation Issues (4 hours)

**Objective:** Resolve 4-8 failing tests caused by DI state pollution

**Root Cause Analysis:**

- Tests share global bevy DI container state
- Previous tests leave registered instances
- SessionPaths and singleton services not properly cleaned up

**Solution Pattern:**

```text
@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset DI state after each test."""
    yield
    container = get_container()

    # Clean up all registered instances
    for cls in [
        SessionPaths,
        ApplicationMonitor,
        LLMManager,
        ServerlessSessionManager,
        # ... other singletons
    ]:
        with suppress(KeyError):
            container.instances.pop(cls, None)
```

**Tasks:**

1. Add autouse fixture for DI cleanup in `tests/conftest.py`
1. Update failing tests to use fixture
1. Verify all 978 tests pass in full suite
1. Document DI test isolation pattern

**Expected Outcome:** 978/978 tests passing (100%)

______________________________________________________________________

### Day 2: Server.py Core Coverage (6-8 hours)

**Objective:** Test core MCP server functionality (highest priority)

**Target Modules:**

1. FastMCP tool registration
1. Session lifecycle (start, checkpoint, end, status)
1. Quality scoring algorithm
1. Git integration

**Testing Strategy:**

- Use `MockMCP` server pattern from existing tests
- Mock external dependencies (git, filesystem, crackerjack)
- Test both success and error paths
- Include edge cases (empty projects, missing dependencies)

**Example Test Structure:**

```python
class TestServerSessionLifecycle:
    """Test complete session lifecycle workflows."""

    async def test_start_initializes_session(self, mock_mcp_server):
        result = await mock_mcp_server.call_tool("start")
        assert result["success"] is True
        assert "session_id" in result

    async def test_checkpoint_creates_git_commit(self, mock_mcp_server, tmp_git_repo):
        await mock_mcp_server.call_tool("start", working_directory=tmp_git_repo)
        result = await mock_mcp_server.call_tool("checkpoint")

        # Verify git commit created
        assert result["success"] is True
        assert "commit_sha" in result
```

**Target Coverage:** 60%+ for server.py

______________________________________________________________________

### Day 3: Reflection Tools Coverage (6-8 hours)

**Objective:** Test memory and search functionality

**Target Modules:**

1. `ReflectionDatabase` class
1. Embedding generation and fallback
1. Semantic search with vector similarity
1. Text search fallback
1. Database schema creation

**Testing Strategy:**

- Use in-memory DuckDB for fast tests
- Mock ONNX model for embedding tests
- Test both embedding and fallback modes
- Verify search ranking and relevance

**Example Test Structure:**

```python
class TestReflectionDatabaseSearch:
    """Test semantic and text search functionality."""

    async def test_semantic_search_with_embeddings(self, reflection_db):
        # Store conversations with embeddings
        await reflection_db.store_conversation("Python async patterns")
        await reflection_db.store_conversation("JavaScript promises")

        # Search for related content
        results = await reflection_db.search_reflections("async programming")

        assert len(results) > 0
        assert "Python" in results[0]["content"]

    async def test_text_search_fallback_when_no_embeddings(self, reflection_db_no_onnx):
        # Verify fallback to text search
        await reflection_db_no_onnx.store_conversation("Python async patterns")
        results = await reflection_db_no_onnx.search_reflections("async")

        assert len(results) > 0
```

**Target Coverage:** 70%+ for reflection_tools.py

______________________________________________________________________

### Day 4: Crackerjack Integration Coverage (5-6 hours)

**Objective:** Test code quality integration layer

**Target Modules:**

1. Command parsing and validation
1. Quality metric aggregation
1. Test result analysis
1. Command history and learning

**Testing Strategy:**

- Mock crackerjack command output
- Test various output formats
- Verify metric calculation accuracy
- Test error handling

**Example Test Structure:**

```python
class TestCrackerjackIntegration:
    """Test crackerjack command integration."""

    def test_parse_quality_output(self, mock_crackerjack_output):
        integration = CrackerjackIntegration()
        result = integration.parse_output(mock_crackerjack_output)

        assert result["quality_score"] == 85
        assert result["tests_passed"] == 42
        assert result["coverage"] == 90.5

    def test_command_execution_with_timeout(self):
        integration = CrackerjackIntegration()
        result = integration.execute_command("test", timeout=30)

        assert result["success"] is True
        assert result["execution_time"] < 30.0
```

**Target Coverage:** 75%+ for crackerjack_integration.py

______________________________________________________________________

### Day 5: Tools Module Coverage (6-8 hours)

**Objective:** Test MCP tool implementations

**Target Modules:**

- `tools/session_tools.py`
- `tools/memory_tools.py`
- `tools/crackerjack_tools.py`
- `tools/llm_tools.py`
- `tools/team_tools.py`

**Testing Strategy:**

- Test each tool's happy path
- Test error handling and validation
- Test parameter combinations
- Verify return value structures

**Target Coverage:** 70%+ for all tools/ modules

______________________________________________________________________

### Day 6: Session Manager & Utils Coverage (5-6 hours)

**Objective:** Test session state management and utilities

**Target Modules:**

1. `core/session_manager.py`
1. `utils/git_operations.py`
1. `utils/logging.py`
1. `utils/quality_utils_v2.py`

**Testing Strategy:**

- Test session lifecycle state transitions
- Mock git operations
- Verify logging output
- Test quality scoring V2 algorithm

**Target Coverage:** 75%+ for core/ and utils/ modules

______________________________________________________________________

### Day 7: Documentation & Verification (3-4 hours)

**Objective:** Final verification and documentation

**Tasks:**

1. Run full test suite with coverage
1. Generate final coverage report
1. Create Week 8 completion document
1. Update testing documentation

**Deliverables:**

- `docs/WEEK8_COMPLETION.md`
- `docs/developer/TESTING_BEST_PRACTICES.md`
- Updated `docs/developer/ARCHITECTURE.md` (testing section)
- Coverage report showing ≥80% coverage

______________________________________________________________________

## Testing Patterns & Best Practices

### Pattern 1: DI Test Isolation

```text
@pytest.fixture(autouse=True)
def reset_di_container():
    """Ensure clean DI state for each test."""
    yield
    container = get_container()
    for cls in ALL_SINGLETON_CLASSES:
        with suppress(KeyError):
            container.instances.pop(cls, None)
```

### Pattern 2: Mock MCP Server

```text
@pytest.fixture
async def mock_mcp_server(tmp_path):
    """Create isolated MCP server for testing."""
    from session_buddy.server import mcp

    # Configure with test environment
    os.environ["HOME"] = str(tmp_path)

    yield mcp

    # Cleanup
    del os.environ["HOME"]
```

### Pattern 3: Async Database Testing

```text
@pytest.fixture
async def reflection_db(tmp_path):
    """Create in-memory reflection database."""
    db_path = tmp_path / "test_reflections.duckdb"
    async with ReflectionDatabase(db_path) as db:
        await db._ensure_tables()
        yield db
```

### Pattern 4: Mock External Dependencies

```python
@pytest.fixture
def mock_crackerjack_command(monkeypatch):
    """Mock crackerjack command execution."""

    def mock_run(cmd, *args, **kwargs):
        return CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="Quality: 85/100\nTests: 42 passed",
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", mock_run)
```

______________________________________________________________________

## Risk Mitigation

### Risk 1: Test Suite Timeout

**Mitigation:** Use pytest-xdist for parallel execution, mark slow tests

### Risk 2: Coverage Plateau

**Mitigation:** Focus on critical paths first, accept lower coverage for rarely-used features

### Risk 3: Test Brittleness

**Mitigation:** Use fixtures for setup, avoid hardcoded paths, mock external dependencies

### Risk 4: Time Overrun

**Mitigation:** Prioritize high-impact modules, defer lower-priority modules if needed

______________________________________________________________________

## Success Metrics

### Quantitative

- **Coverage:** 14.4% → 80%+ (target: 85%)
- **Test Pass Rate:** ≥99% maintained
- **Tests Added:** ~200-300 new tests
- **Code Lines Tested:** ~15,000+ additional lines

### Qualitative

- All critical paths have test coverage
- Test isolation issues resolved
- Testing patterns documented
- Developer confidence improved

______________________________________________________________________

## Time Estimate

| Day | Focus | Estimated Hours | Notes |
|-----|-------|----------------|-------|
| Day 0 | Analysis & Planning | 2h | Coverage baseline |
| Day 1 | Test Isolation Fixes | 4h | DI cleanup |
| Day 2 | Server.py Coverage | 6-8h | Core MCP server |
| Day 3 | Reflection Tools | 6-8h | Memory & search |
| Day 4 | Crackerjack Integration | 5-6h | Quality metrics |
| Day 5 | Tools Module Coverage | 6-8h | MCP tools |
| Day 6 | Session Manager & Utils | 5-6h | State management |
| Day 7 | Documentation & Verification | 3-4h | Final docs |
| **Total** | | **37-48h** | **~5-7 days** |

______________________________________________________________________

## Dependencies & Prerequisites

**From Week 7:**

- ✅ SessionPaths frozen dataclass
- ✅ Direct container access pattern
- ✅ DI test fixtures established
- ✅ All DI tests passing (25/25)

**Required Tools:**

- pytest ≥7.0
- pytest-asyncio ≥0.21
- pytest-cov ≥4.0
- coverage ≥7.0
- hypothesis ≥6.70 (property-based testing)

______________________________________________________________________

## Deliverables Checklist

### Documentation

- [ ] `docs/WEEK8_PLANNING.md` (this document)
- [ ] `docs/WEEK8_COVERAGE_BASELINE.md` (Day 0)
- [ ] `docs/WEEK8_DAY1_PROGRESS.md` (test isolation fixes)
- [ ] `docs/WEEK8_DAY2_PROGRESS.md` (server.py coverage)
- [ ] `docs/WEEK8_DAY3_PROGRESS.md` (reflection tools)
- [ ] `docs/WEEK8_DAY4_PROGRESS.md` (crackerjack integration)
- [ ] `docs/WEEK8_DAY5_PROGRESS.md` (tools modules)
- [ ] `docs/WEEK8_DAY6_PROGRESS.md` (session manager & utils)
- [ ] `docs/WEEK8_COMPLETION.md` (final summary)
- [ ] `docs/developer/TESTING_BEST_PRACTICES.md` (patterns guide)

### Code Artifacts

- [ ] Test isolation fixture in `tests/conftest.py`
- [ ] ~200-300 new unit tests across modules
- [ ] Mock fixtures for external dependencies
- [ ] Test data factories (if needed)

### Reports

- [ ] Coverage baseline report (Day 0)
- [ ] Daily coverage progress reports
- [ ] Final coverage report (≥80%)
- [ ] Test execution time report

______________________________________________________________________

## Integration with Previous Work

**Week 5 (Testing Phase Complete):**

- Established test infrastructure
- Created comprehensive test suite baseline
- Set testing patterns

**Week 6 (DI Environment Handling):**

- Fixed environment variable handling
- Improved test isolation patterns

**Week 7 (ACB DI Refactoring):**

- Type-safe SessionPaths configuration
- Direct container access pattern
- 25 comprehensive DI tests

**Week 8 builds on this foundation** by expanding coverage to all core modules.

______________________________________________________________________

## Future Work (Post-Week 8)

**Week 9 Candidates:**

1. **Performance Optimization** (if coverage ≥80% achieved)

   - Profile hot paths
   - Optimize database queries
   - Reduce memory usage

1. **Integration Testing** (if time permits)

   - End-to-end workflow tests
   - Multi-component integration tests
   - Performance benchmarking

1. **Advanced Features Testing** (lower priority)

   - Multi-project coordination
   - Serverless mode
   - App monitoring
   - Natural scheduler
   - Worktree manager

______________________________________________________________________

## Notes & Considerations

**Coverage Philosophy:**

- Focus on critical paths and core functionality first
- Accept lower coverage for rarely-used features
- Prioritize test quality over raw coverage numbers
- Aim for meaningful tests, not just line coverage

**Test Development Approach:**

- Write tests in parallel with coverage analysis
- Test behavior, not implementation details
- Use property-based testing (hypothesis) for complex logic
- Mock external dependencies consistently

**Performance Considerations:**

- Use pytest-xdist for parallel execution
- Mark slow tests with `@pytest.mark.slow`
- Use in-memory databases for fast tests
- Cache expensive fixtures

______________________________________________________________________

## Conclusion

Week 8 represents a critical quality improvement initiative to address the test coverage gap (14.4% → 80%+). By systematically expanding test coverage across all core modules and resolving test isolation issues, we'll establish a robust testing foundation for future development.

**Key Success Factors:**

1. Prioritized approach (critical modules first)
1. Clear testing patterns established
1. Comprehensive documentation
1. Maintained test pass rate ≥99%

**Estimated Completion:** 5-7 days (~37-48 hours)

______________________________________________________________________

**Created:** 2025-10-29
**Author:** Claude Code + Les
**Project:** session-buddy
**Phase:** Week 8 Planning - Test Coverage Improvement
