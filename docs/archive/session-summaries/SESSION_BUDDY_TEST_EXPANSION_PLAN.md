# Session-Buddy Test Coverage Expansion Plan

## Executive Summary

**Current Coverage**: 45.6% (per README.md badge)
**Target Coverage**: 60%+ overall
**Timeline**: 6 days (3 phases)
**Priority**: Core functionality, MCP tools, CLI commands

## Phase 1: Coverage Audit (Day 1)

### 1.1 Run Initial Coverage Report

```bash
cd /Users/les/Projects/session-buddy
pytest --cov=session_buddy --cov-report=html --cov-report=json
open htmlcov/index.html
```

### 1.2 Identify Low-Coverage Modules

Based on codebase analysis, critical modules needing coverage:

**Core Functionality:**
- `session_buddy/core/session_manager.py` - SessionLifecycleManager
- `session_buddy/core/permissions.py` - SessionPermissionsManager
- `session_buddy/core/hooks.py` - HooksManager
- `session_buddy/core/quality_scoring.py` - QualityScorer

**MCP Tools:**
- `session_buddy/mcp/tools/` - All 79+ MCP tools
- `session_buddy/mcp/server_core.py` - Server initialization
- `session_buddy/mcp/session_tracker.py` - Session tracking

**CLI Commands:**
- `session_buddy/cli/` - CLI entry points
- Command handlers for session operations

**Integrations:**
- `session_buddy/integrations/` - External integrations
- Mahavishnu integration
- Crackerjack integration

### 1.3 Coverage Targets by Module

| Module | Current | Target | Priority |
|--------|---------|--------|----------|
| Core session management | ~30% | 70% | HIGH |
| MCP tools | ~20% | 70% | HIGH |
| CLI commands | ~25% | 70% | MEDIUM |
| Integrations | ~15% | 60% | MEDIUM |
| Utilities | ~40% | 65% | LOW |

## Phase 2: Core Tests (Days 2-3)

### 2.1 SessionLifecycleManager Tests

**File**: `tests/unit/test_core/test_session_manager.py`

Test Coverage Areas:
- ✅ Initialization (existing)
- ✅ Project context analysis (existing)
- ❌ Session start workflow
- ❌ Quality scoring calculation
- ❌ Checkpoint creation
- ❌ Session end cleanup
- ❌ Handoff documentation generation
- ❌ Insight extraction
- ❌ Error handling

**New Tests to Add:**
```python
class TestSessionStartWorkflow:
    """Test session start initialization."""
    - test_start_with_git_repo
    - test_start_without_git_repo
    - test_start_with_checkpoint_resume
    - test_start_with_quality_baseline
    - test_start_error_handling

class TestQualityScoring:
    """Test quality score calculation."""
    - test_calculate_quality_score_basic
    - test_calculate_quality_score_with_tests
    - test_calculate_quality_score_with_coverage
    - test_quality_score_history_tracking
    - test_quality_score_delta_calculation

class TestCheckpointWorkflow:
    """Test checkpoint creation and management."""
    - test_create_checkpoint_basic
    - test_create_checkpoint_with_git_commit
    - test_create_checkpoint_with_quality_assessment
    - test_checkpoint_insight_capture
    - test_checkpoint_error_recovery

class TestSessionEndWorkflow:
    """Test session end cleanup."""
    - test_end_session_basic_cleanup
    - test_end_session_with_handoff_doc
    - test_end_session_with_git_commit
    - test_end_session_final_insights_capture
    - test_end_session_error_handling

class TestInsightExtraction:
    """Test automatic insight extraction."""
    - test_extract_insights_from_conversation
    - test_insight_deduplication
    - test_insight_storage
    - test_insight_confidence_scoring
```

### 2.2 SessionPermissionsManager Tests

**File**: `tests/unit/test_core/test_permissions.py`

Test Coverage Areas:
- ❌ Singleton pattern
- ❌ Permission loading/saving
- ❌ Operation trust/untrust
- ❌ Session ID generation
- ❌ Permission status queries

**New Tests to Add:**
```python
class TestPermissionsManagerSingleton:
    """Test singleton pattern implementation."""
    - test_singleton_returns_same_instance
    - test_singleton_with_different_paths
    - test_class_level_session_id_persistence

class TestPermissionOperations:
    """Test permission operations."""
    - test_trust_operation_basic
    - test_trust_operation_with_description
    - test_untrust_operation
    - test_is_operation_trusted
    - test_trust_operation_none_raises_error

class TestPermissionPersistence:
    """Test permission loading and saving."""
    - test_load_permissions_from_file
    - test_save_permissions_to_file
    - test_permissions_persistence_across_instances
    - test_corrupted_permissions_file_handling

class TestSessionManagement:
    """Test session ID management."""
    - test_session_id_generation
    - test_session_id_persistence
    - test_session_id_uniqueness
    - test_get_permission_status
```

### 2.3 HooksManager Tests

**File**: `tests/unit/test_core/test_hooks.py`

Test Coverage Areas:
- ❌ Hook registration
- ❌ Hook execution
- ❌ Hook result aggregation
- ❌ Error handling in hooks

**New Tests to Add:**
```python
class TestHooksManager:
    """Test hooks management system."""
    - test_register_hook
    - test_execute_hook_success
    - test_execute_hook_with_error
    - test_execute_hook_multiple_hooks
    - test_hook_result_aggregation
    - test_hook_timeout_handling
```

### 2.4 QualityScorer Tests

**File**: `tests/unit/test_core/test_quality_scoring.py`

Test Coverage Areas:
- ❌ Quality calculation
- ❌ Test coverage analysis
- ❌ Documentation assessment
- ❌ Code quality metrics

**New Tests to Add:**
```python
class TestQualityScorer:
    """Test quality scoring system."""
    - test_calculate_quality_score_basic
    - test_calculate_with_test_coverage
    - test_calculate_with_documentation
    - test_calculate_with_code_quality
    - test_quality_score_weighting
    - test_quality_score_normalization
```

## Phase 3: MCP Tools Tests (Days 4-5)

### 3.1 Core Session Tools

**File**: `tests/unit/test_mcp/tools/test_session_tools.py`

Tools to Test:
- `start` - Session initialization
- `checkpoint` - Mid-session quality check
- `end` - Session cleanup
- `status` - Session status query

```python
class TestStartTool:
    """Test start session tool."""
    - test_start_basic_session
    - test_start_with_git_repo
    - test_start_with_quality_check
    - test_start_error_handling
    - test_start_with_invalid_path

class TestCheckpointTool:
    """Test checkpoint tool."""
    - test_checkpoint_basic
    - test_checkpoint_with_git_commit
    - test_checkpoint_with_quality_score
    - test_checkpoint_auto_compaction
    - test_checkpoint_error_recovery

class TestEndTool:
    """Test end session tool."""
    - test_end_basic_cleanup
    - test_end_with_handoff_doc
    - test_end_with_git_commit
    - test_end_with_final_quality_score
    - test_end_error_handling

class TestStatusTool:
    """Test status tool."""
    - test_status_active_session
    - test_status_no_session
    - test_status_with_quality_metrics
    - test_status_with_git_info
```

### 3.2 Memory & Search Tools

**File**: `tests/unit/test_mcp/tools/test_memory_tools.py`

Tools to Test:
- `store_reflection` - Store insights
- `quick_search` - Fast search
- `search_summary` - Aggregated results
- `search_by_file` - File-based search
- `search_by_concept` - Semantic search

```python
class TestStoreReflectionTool:
    """Test reflection storage."""
    - test_store_reflection_basic
    - test_store_reflection_with_tags
    - test_store_reflection_with_embedding
    - test_store_reflection_duplicate_handling
    - test_store_reflection_error_handling

class TestQuickSearchTool:
    """Test quick search functionality."""
    - test_quick_search_basic
    - test_quick_search_with_filters
    - test_quick_search_pagination
    - test_quick_search_empty_results
    - test_quick_search_error_handling

class TestSearchByFileTool:
    """Test file-based search."""
    - test_search_by_file_basic
    - test_search_by_file_with_context
    - test_search_by_file_nonexistent
    - test_search_by_file_error_handling

class TestSearchByConceptTool:
    """Test semantic concept search."""
    - test_search_by_concept_basic
    - test_search_by_concept_with_file_context
    - test_search_by_concept_with_threshold
    - test_search_by_concept_empty_results
```

### 3.3 Intelligence Tools

**File**: `tests/unit/test_mcp/tools/test_intelligence_tools.py`

Tools to Test:
- `search_insights` - Search captured insights
- `insights_statistics` - View insight stats
- `create_project_group` - Create project groups
- `add_project_dependency` - Track dependencies
- `search_across_projects` - Cross-project search

```python
class TestInsightsTools:
    """Test insights management tools."""
    - test_search_insights_basic
    - test_search_insights_wildcard
    - test_insights_statistics
    - test_insights_statistics_by_type
    - test_insights_empty_database

class TestProjectGroupsTools:
    """Test project group management."""
    - test_create_project_group_basic
    - test_create_project_group_with_description
    - test_add_project_dependency
    - test_add_circular_dependency_detection
    - test_search_across_projects_basic
    - test_search_across_projects_with_dependency_ranking
```

### 3.4 Server Core Tests

**File**: `tests/unit/test_mcp/test_server_core.py`

Test Coverage Areas:
- ❌ Server initialization
- ❌ Tool registration
- ❌ Lifespan management
- ❌ Error handling

```python
class TestServerInitialization:
    """Test MCP server initialization."""
    - test_server_initialization_basic
    - test_server_with_settings
    - test_server_tool_registration
    - test_server_prompt_registration

class TestServerLifespan:
    """Test server lifespan management."""
    - test_lifespan_startup
    - test_lifespan_shutdown
    - test_lifespan_error_handling
```

## Phase 4: CLI Tests (Day 6)

### 4.1 CLI Command Tests

**File**: `tests/unit/test_cli/test_session_commands.py`

Commands to Test:
- `session-buddy start` - Start session
- `session-buddy checkpoint` - Create checkpoint
- `session-buddy end` - End session
- `session-buddy status` - Show status

```python
class TestStartCommand:
    """Test start CLI command."""
    - test_start_command_basic
    - test_start_command_with_path
    - test_start_command_with_options
    - test_start_command_error_handling

class TestCheckpointCommand:
    """Test checkpoint CLI command."""
    - test_checkpoint_command_basic
    - test_checkpoint_command_with_name
    - test_checkpoint_command_with_git
    - test_checkpoint_command_error_handling

class TestEndCommand:
    """Test end CLI command."""
    - test_end_command_basic
    - test_end_command_with_handoff
    - test_end_command_with_git
    - test_end_command_error_handling

class TestStatusCommand:
    """Test status CLI command."""
    - test_status_command_basic
    - test_status_command_json_output
    - test_status_command_no_session
```

### 4.2 Integration Tests

**File**: `tests/integration/test_cli_integration.py`

Test Coverage Areas:
- ❌ End-to-end CLI workflows
- ❌ MCP server integration
- ❌ Database integration

```python
class TestCLIIntegration:
    """Test CLI integration scenarios."""
    - test_full_session_lifecycle
    - test_session_with_checkpoints
    - test_session_with_mcp_tools
    - test_session_error_recovery
```

## Implementation Strategy

### Test Creation Workflow

1. **Analyze Source Code**: Read module to understand functionality
2. **Identify Test Cases**: Map out happy path and edge cases
3. **Create Test File**: Add to appropriate test directory
4. **Implement Tests**: Write comprehensive test cases
5. **Run Tests**: Execute and verify pass
6. **Check Coverage**: Review coverage reports
7. **Iterate**: Add missing tests until target reached

### Test Quality Standards

- **Clear Naming**: Test names should describe what they test
- **AAA Pattern**: Arrange, Act, Assert structure
- **Isolation**: Tests should be independent
- **Fixtures**: Use existing fixtures for common setup
- **Async Support**: Proper async/await handling
- **Error Cases**: Test both success and failure paths
- **Edge Cases**: Boundary conditions and special inputs

### Coverage Goals

**Overall Target**: 60%+
**Core Modules**: 70%+
**MCP Tools**: 70%+
**CLI Commands**: 70%+

## Success Metrics

### Coverage Targets

- ✅ Overall coverage ≥ 60%
- ✅ Core functionality ≥ 70%
- ✅ MCP tools ≥ 70%
- ✅ CLI ≥ 70%

### Test Quality

- ✅ All tests passing
- ✅ No flaky tests
- ✅ Fast execution (< 5 minutes)
- ✅ Clear test documentation
- ✅ Proper fixture usage

### Documentation

- ✅ Test coverage report (HTML + JSON)
- ✅ Test expansion completion report
- ✅ Known gaps documented
- ✅ Future improvements identified

## Execution Timeline

### Day 1: Audit
- Run coverage report
- Identify low-coverage modules
- Create detailed test plan
- Setup test infrastructure

### Day 2-3: Core Tests
- SessionLifecycleManager tests
- SessionPermissionsManager tests
- HooksManager tests
- QualityScorer tests

### Day 4-5: MCP Tools Tests
- Session tools tests
- Memory & search tools tests
- Intelligence tools tests
- Server core tests

### Day 6: CLI Tests
- CLI command tests
- Integration tests
- Final coverage validation
- Documentation

## Dependencies & Resources

### Required Files

- `/Users/les/Projects/session-buddy/tests/conftest.py` - Test fixtures
- `/Users/les/Projects/session-buddy/tests/fixtures/` - Test data factories
- `/Users/les/Projects/session-buddy/tests/helpers/` - Test utilities

### Key Fixtures to Use

- `fast_temp_db` - Fast temporary database
- `temp_test_dir` - Temporary test directory
- `mock_project_factory` - Mock project creation
- `mock_git_repo_factory` - Mock git repository
- `performance_monitor` - Performance tracking

### Test Configuration

- **Framework**: pytest with asyncio support
- **Markers**: unit, integration, e2e, slow, performance
- **Timeout**: 600 seconds per test
- **Parallel**: pytest-xdist for parallel execution
- **Coverage**: pytest-cov with HTML/JSON reports

## Risks & Mitigations

### Risk: Test Execution Time

**Mitigation**: Use fast in-memory databases, limit file I/O, use session-scoped fixtures

### Risk: Flaky Tests

**Mitigation**: Proper async handling, cleanup between tests, avoid shared state

### Risk: Coverage Goals Not Met

**Mitigation**: Focus on high-value paths first, accept that 100% is not realistic

### Risk: Test Maintenance Burden

**Mitigation**: Clear test structure, good fixtures, documentation

## Next Steps

1. ✅ Create this plan document
2. ⏭️ Run initial coverage report
3. ⏭️ Create Phase 2 tests (Core functionality)
4. ⏭️ Create Phase 3 tests (MCP tools)
5. ⏭️ Create Phase 4 tests (CLI)
6. ⏭️ Generate final coverage report
7. ⏭️ Document remaining gaps

## References

- **Project**: /Users/les/Projects/session-buddy
- **Tests**: /Users/les/Projects/session-buddy/tests/
- **Conftest**: /Users/les/Projects/session-buddy/tests/conftest.py
- **Coverage**: htmlcov/index.html (after running pytest)
- **Documentation**: /Users/les/Projects/session-buddy/docs/
