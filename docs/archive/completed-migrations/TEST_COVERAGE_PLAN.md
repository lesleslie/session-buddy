# Test Coverage Improvement Plan

**Date**: 2025-11-05
**Current Coverage**: 45.61% (7,153 / 14,395 lines)
**Target Coverage**: 80%+ (11,516+ lines)
**Gap**: 4,363 lines need test coverage

## Executive Summary

Successfully completed complexity refactoring (11 functions from 16-28 → ≤15) and fixed all DI pattern issues. Current coverage baseline established at 45.61% after running 1,027 passing tests (99 failing due to missing test fixtures, 127 errors from missing implementations).

## Test Run Statistics

- **Total Tests**: 1,152 (1,027 passed, 99 failed, 24 skipped, 2 deselected)
- **Errors**: 127 (mostly missing test implementations for advanced features)
- **Runtime**: 177.29 seconds (~3 minutes) with `test_perform_strategic_compaction` excluded
- **Timeout Issue**: `test_perform_strategic_compaction` causes 300s timeout due to recursive filesystem glob

## Priority 1: Critical Zero-Coverage Files (0% → 60%+)

### File 1: `session_buddy/adapters/knowledge_graph_adapter.py` (186 lines, 0%)

**Why Critical**: Core DuckPGQ graph adapter for knowledge graph operations
**Test Priority**: High
**Effort**: 4-6 hours
**Tests Needed**:

- Node CRUD operations (create, read, update, delete)
- Edge/relationship management
- Graph traversal queries
- Bulk operations
- Error handling for invalid graph structures

### File 2: `session_buddy/context_manager.py` (261 lines, 0%)

**Why Critical**: Session context preservation during interruptions
**Test Priority**: High
**Effort**: 5-7 hours
**Tests Needed**:

- Context snapshot creation
- Context restoration
- Interruption detection
- State serialization/deserialization
- Concurrent access safety

### File 3: `session_buddy/team_knowledge.py` (302 lines, 0%)

**Why Critical**: Team collaboration and knowledge sharing features
**Test Priority**: Medium
**Effort**: 6-8 hours
**Tests Needed**:

- Team creation and management
- Permission/access control
- Knowledge search across teams
- Voting and ranking system
- Team statistics aggregation

### File 4: `session_buddy/tools/health_tools.py` (28 lines, 0%)

**Why Critical**: System health monitoring
**Test Priority**: High (small, easy win)
**Effort**: 1-2 hours
**Tests Needed**:

- Health check endpoint
- Dependency availability checks
- System resource monitoring
- Error state detection

### File 5: `session_buddy/tools/validated_memory_tools.py` (208 lines, 0%)

**Why Critical**: Memory validation and integrity
**Test Priority**: High
**Effort**: 4-5 hours
**Tests Needed**:

- Input validation
- Schema validation
- Data integrity checks
- Rollback on validation failures
- Edge cases (empty, oversized, malformed data)

## Priority 2: Low-Coverage Refactored Files (Complexity Fixes)

### File 6: `session_buddy/llm_providers.py` (30% → 70% target, 351 missing lines)

**Refactored Functions**:

- `OllamaProvider::is_available()` (helper: `_check_with_mcp_common`, `_check_with_aiohttp`)
- `OllamaProvider::stream_generate()` (helper: `_stream_with_mcp_common`, `_stream_with_aiohttp`)
- `validate_llm_api_keys_at_startup()` (helpers: `_get_configured_providers`, `_validate_provider_with_security`, `_validate_provider_basic`)

**Tests Needed**:

- Test `_check_with_mcp_common` success and failure paths
- Test `_check_with_aiohttp` fallback when mcp-common unavailable
- Test `_stream_with_mcp_common` chunk processing
- Test `_stream_with_aiohttp` streaming fallback
- Test provider configuration detection (`_get_configured_providers`)
- Test security module validation (`_validate_provider_with_security`)
- Test basic validation fallback (`_validate_provider_basic`)
- Test API key masking and error messages

**Effort**: 6-8 hours

### File 7: `session_buddy/tools/knowledge_graph_tools.py` (13.68% → 60%, 239 missing lines)

**Refactored Functions**:

- `_extract_entities_from_context_impl()` (helpers: `_extract_patterns_from_context`, `_auto_create_entity_if_new`, `_format_extraction_output`)
- `_batch_create_entities_impl()` (helpers: similar pattern extraction)
- `_get_knowledge_graph_stats_impl()` (helpers: `_format_entity_types`, `_format_relationship_types`)
- `_search_entities_impl()` (helper: `_format_entity_search_results`)

**Tests Needed**:

- Test `_extract_patterns_from_context` with various entity types
- Test `_auto_create_entity_if_new` with existing and new entities
- Test `_format_extraction_output` with auto_create enabled/disabled
- Test batch creation with valid and invalid entities
- Test stats formatting for both entity and relationship types
- Test search result formatting with various result sets

**Effort**: 7-9 hours

## Priority 3: Medium-Coverage Files Needing Improvement

### File 8: `session_buddy/tools/monitoring_tools.py` (11.34% → 50%, 318 missing lines)

**Effort**: 5-7 hours
**Focus**: App activity monitoring, file system watching, context insights

### File 9: `session_buddy/search_enhanced.py` (11.47% → 60%, 197 missing lines)

**Effort**: 4-6 hours
**Focus**: Faceted search, aggregations, full-text indexing

### File 10: `session_buddy/tools/search_tools.py` (17.01% → 60%, 348 missing lines)

**Effort**: 6-8 hours
**Focus**: Advanced search capabilities, pagination, filtering

## Priority 4: Fix Failing Tests

### Issue 1: `test_perform_strategic_compaction_returns_list` (TIMEOUT)

**Problem**: Recursive glob `**/*.pyc` scans entire project including `.venv`
**Solution Options**:

1. Mock filesystem operations in test
1. Mark test as `@pytest.mark.slow` and exclude from coverage runs
1. Fix `_cleanup_temp_files()` to exclude `.venv` and large directories

**Recommended**: Option 1 (mock) + Option 2 (mark slow) for quick wins

### Issue 2: 99 Failing Tests (Missing DI/Test Fixtures)

**Categories**:

- SessionPermissionsManager not registered in DI (22 tests)
- ReflectionDatabase initialization failures (31 tests)
- Advanced search missing implementations (24 tests)
- Session tools integration failures (22 tests)

**Solution**: Complete DI registration for all components

### Issue 3: 127 Test Errors (Missing Implementations)

**Categories**:

- Performance tests (12 errors) - need benchmark baselines
- Security tests (5 errors) - need security test infrastructure
- Advanced search tests (30 errors) - need advanced search implementation
- Comprehensive reflection tests (80 errors) - need full reflection system

**Solution**: Prioritize based on feature importance

## Test Writing Strategy

### Phase 1: Quick Wins (Week 1 - Days 1-2)

**Target**: 45.61% → 55% (+1,355 lines)

1. Fix `test_perform_strategic_compaction` with mocks
1. Add tests for `health_tools.py` (28 lines, easy)
1. Add tests for refactored helper functions in `memory_tools.py` (current 84% → 90%)
1. Add tests for `server.py` helpers (current 65% → 75%)

**Estimated Effort**: 8-10 hours

### Phase 2: Core Coverage (Week 1 - Days 3-5)

**Target**: 55% → 70% (+2,159 lines)

1. Complete `llm_providers.py` helper function tests
1. Complete `knowledge_graph_tools.py` helper function tests
1. Add tests for `knowledge_graph_adapter.py` (186 lines, 0% → 60%)
1. Add tests for `validated_memory_tools.py` (208 lines, 0% → 60%)
1. Add tests for `context_manager.py` (261 lines, 0% → 60%)

**Estimated Effort**: 25-30 hours

### Phase 3: Advanced Features (Week 2)

**Target**: 70% → 80%+ (+1,439 lines)

1. Complete `team_knowledge.py` tests (302 lines, 0% → 60%)
1. Improve `monitoring_tools.py` (11% → 50%)
1. Improve `search_enhanced.py` (11% → 60%)
1. Improve `search_tools.py` (17% → 60%)
1. Fix remaining failing tests and errors

**Estimated Effort**: 30-35 hours

## Total Effort Estimate

- **Phase 1 (Quick Wins)**: 8-10 hours
- **Phase 2 (Core Coverage)**: 25-30 hours
- **Phase 3 (Advanced Features)**: 30-35 hours

**Total**: 63-75 hours (~9-11 working days at 7 hours/day)

## Success Metrics

- **Coverage Target**: 80%+ (11,516+ lines covered)
- **Test Count Target**: 1,400+ tests (from current 1,152)
- **Failing Tests Target**: \<10 (from current 99)
- **Test Errors Target**: \<5 (from current 127)
- **Test Runtime Target**: \<5 minutes for full suite (excluding slow tests)

## Immediate Next Steps

1. ✅ **COMPLETED**: Fix type hint issues (`import typing as t`)
1. ✅ **COMPLETED**: Establish baseline coverage (45.61%)
1. ✅ **COMPLETED**: Identify low-coverage files and refactored functions
1. **TODO**: Mark `test_perform_strategic_compaction` as slow and mock filesystem
1. **TODO**: Begin Phase 1 with `health_tools.py` tests (easiest win)
1. **TODO**: Add tests for all refactored helper functions

## Notes

- Complexity refactoring created many new helper functions with 0% coverage
- These helpers are prime targets for unit tests (small, focused, easy to test)
- Current test failures are mostly due to missing DI registrations, not code bugs
- Test timeout issues indicate need for better mocking of slow operations
- Coverage report excludes `test_perform_strategic_compaction` due to timeout

## References

- Coverage baseline: `coverage.json` (generated 2025-11-05)
- Complexity refactoring: `docs/COMPLEXITY_REFACTORING_PROGRESS.md`
- Test results: 1,027 passed, 99 failed, 127 errors (excluding slow tests)
