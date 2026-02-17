# Week 8 Day 2 - server.py Coverage Expansion Plan

**Date:** 2025-10-29
**Objective:** Increase server.py coverage from 50.83% to 70%+
**Estimated Effort:** 6-8 hours
**Status:** Planning

______________________________________________________________________

## Current State

**server.py Coverage:**

- Current: 50.83% (89 lines missing out of 204 statements)
- Target: ≥70% (reduce missing to ~60 lines)
- Gap: Need to test ~30 additional lines

**server_core.py Coverage:**

- Current: 40.34% (199 lines missing out of 382 statements)
- Target: ≥70% (reduce missing to ~115 lines)
- Gap: Need to test ~85 additional lines

**Combined Effort:** ~115 lines to test across both modules

______________________________________________________________________

## Implementation Strategy

### Phase 1: Analyze Untested Areas (1 hour)

**Tasks:**

1. Generate fresh coverage report with line numbers
1. Identify specific untested functions/methods
1. Categorize by difficulty (easy/medium/hard)
1. Prioritize high-value areas

**Deliverable:** Detailed gap analysis with test plan

### Phase 2: Create Test Infrastructure (1-2 hours)

**Tasks:**

1. Create MockMCP server fixture
1. Create mock git repository fixture
1. Create mock crackerjack integration fixtures
1. Create test data factories for server operations

**Test Files to Create/Update:**

- `tests/fixtures/server_fixtures.py` - MCP server mocking
- `tests/fixtures/git_fixtures.py` - Git operations mocking
- `tests/unit/test_server_tools.py` - MCP tool testing

### Phase 3: Test MCP Tool Registration (2 hours)

**Focus Areas:**

- Tool registration mechanics
- Tool parameter validation
- Tool error handling
- Tool response formatting

**Target Functions (server.py):**

- MCP tool decorator registration
- Parameter parsing and validation
- Response structure validation
- Error response formatting

**Expected Coverage Gain:** +15-20%

### Phase 4: Test Quality Scoring (1-2 hours)

**Focus Areas:**

- Quality score calculation algorithms
- Project health assessment
- Permissions impact on scoring
- Tool availability impact

**Target Functions:**

- Quality scoring V2 algorithm
- Project maturity assessment
- Health check integration

**Expected Coverage Gain:** +10-15%

### Phase 5: Test Git Integration (1-2 hours)

**Focus Areas:**

- Git commit creation
- Checkpoint metadata
- Branch detection
- Repository validation

**Target Functions:**

- Git commit workflow
- Checkpoint commit formatting
- Git status integration

**Expected Coverage Gain:** +8-12%

### Phase 6: Test Session Lifecycle (1 hour)

**Focus Areas:**

- Session initialization
- Session cleanup
- Session state transitions
- Session handoff documentation

**Target Functions:**

- Session start logic
- Session end logic
- Status reporting

**Expected Coverage Gain:** +5-10%

______________________________________________________________________

## Test Structure Plan

### New Test Classes

```python
# tests/unit/test_server_tools.py


class TestMCPToolRegistration:
    """Test MCP tool registration and execution."""

    async def test_tool_registration_success(self, mock_mcp_server):
        """Tools are registered with correct parameters."""
        pass

    async def test_tool_parameter_validation(self, mock_mcp_server):
        """Invalid parameters are rejected."""
        pass

    async def test_tool_error_handling(self, mock_mcp_server):
        """Tool errors are properly formatted."""
        pass


class TestQualityScoring:
    """Test quality scoring algorithms."""

    def test_quality_score_calculation(self, tmp_git_repo):
        """Quality score calculated correctly from metrics."""
        pass

    def test_project_health_assessment(self, tmp_git_repo):
        """Project health factors into quality score."""
        pass

    def test_permissions_impact_on_score(self, tmp_git_repo):
        """Permissions affect quality score."""
        pass


class TestGitIntegration:
    """Test Git commit and checkpoint functionality."""

    def test_checkpoint_commit_creation(self, tmp_git_repo):
        """Checkpoint creates Git commit with metadata."""
        pass

    def test_commit_message_format(self, tmp_git_repo):
        """Commit messages follow standard format."""
        pass

    def test_git_status_integration(self, tmp_git_repo):
        """Git status properly detected."""
        pass


class TestSessionLifecycle:
    """Test session start, checkpoint, end workflows."""

    async def test_session_start_initialization(self, mock_mcp_server):
        """Session start initializes correctly."""
        pass

    async def test_session_checkpoint_workflow(self, mock_mcp_server):
        """Checkpoint creates state snapshot."""
        pass

    async def test_session_end_cleanup(self, mock_mcp_server):
        """Session end performs cleanup and handoff."""
        pass
```

______________________________________________________________________

## Success Criteria

| Criterion | Target | How to Measure |
|-----------|--------|----------------|
| server.py coverage | ≥70% | `coverage report session_buddy/server.py` |
| server_core.py coverage | ≥70% | `coverage report session_buddy/server_core.py` |
| New tests passing | 100% | All new tests pass |
| No regressions | ≥980 passing | Full suite test count maintained |
| Test execution time | \<5min | New tests complete quickly |

______________________________________________________________________

## Risk Mitigation

### Risk 1: Mock Complexity

**Issue:** MCP server mocking may be complex
**Mitigation:** Start with simple mock, add features incrementally

### Risk 2: Async Testing Challenges

**Issue:** Async tool testing can be tricky
**Mitigation:** Use existing async test patterns from test_server.py

### Risk 3: Git Repository Setup

**Issue:** Creating test git repos can be slow
**Mitigation:** Use tmp_path fixtures, cache where possible

### Risk 4: Time Overrun

**Issue:** May take longer than 6-8 hours
**Mitigation:** Focus on high-value tests first, defer edge cases

______________________________________________________________________

## Implementation Order

1. **Hour 1**: Analyze untested areas, create test plan
1. **Hour 2-3**: Create test infrastructure (fixtures, mocks)
1. **Hour 4-5**: Implement MCP tool registration tests
1. **Hour 6**: Implement quality scoring tests
1. **Hour 7**: Implement Git integration tests
1. **Hour 8**: Implement session lifecycle tests, documentation

______________________________________________________________________

## Deliverables

### Code Artifacts

- [ ] `tests/fixtures/server_fixtures.py` - MCP server mocking
- [ ] `tests/fixtures/git_fixtures.py` - Git operation mocking
- [ ] `tests/unit/test_server_tools.py` - MCP tool tests (new/updated)
- [ ] `tests/unit/test_server_quality.py` - Quality scoring tests (new)
- [ ] `tests/unit/test_server_git.py` - Git integration tests (new)
- [ ] `tests/unit/test_server_lifecycle.py` - Session lifecycle tests (new)

### Documentation

- [ ] `docs/WEEK8_DAY2_PROGRESS.md` - Day 2 completion summary
- [ ] Update `docs/WEEK8_COVERAGE_BASELINE.md` with Day 2 results
- [ ] Update test best practices if new patterns emerge

______________________________________________________________________

## Next Steps After Day 2

**Day 3 Focus:** reflection_tools.py coverage (44.66% → 75%+)

- DuckDB database operations
- Embedding generation
- Search functionality
- Vector similarity

______________________________________________________________________

**Created:** 2025-10-29
**Author:** Claude Code + Les
**Project:** session-buddy
**Phase:** Week 8 Day 2 Planning
