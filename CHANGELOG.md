# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.2] - 2025-12-19

### Changed

- Update core, deps, docs

## [0.10.1] - 2025-12-11

### Changed

- Update dependencies

## [0.10.0] - 2025-12-11

### Changed

- **BREAKING:** Rename project from session-mgmt-mcp to session-buddy
- Update config, core, deps, docs, tests

### Documentation

- Add comprehensive rename summary documentation

## [0.9.9] - 2025-12-09

### Changed

- Update config, core, deps

## [0.9.8] - 2025-12-03

### Changed

- Update config, core, deps, tests

## [0.9.7] - 2025-11-27

### Changed

- Update config, deps

## [0.9.6] - 2025-11-26

### Changed

- Update config, deps, docs

## [0.9.5] - 2025-11-26

### Changed

- Update config, core, deps, docs, tests

## [0.9.4] - 2025-11-19

### Changed

- Session-mgmt-mcp (quality: 68/100) - 2025-11-19 10:20:15
- Session-mgmt-mcp (quality: 68/100) - 2025-11-19 21:35:03
- Update documentation

## [0.9.3] - 2025-11-17

### Added

- Phase 1 Day 1 - Storage adapter foundation (ACB migration)
- Phase 2 Days 4-5 - Serverless backend consolidation (ACB migration)

### Changed

- Phase 1 quick wins - remove unused code, simplify patterns
- Phase 2 - context manager simplification across codebase
- Phase 3 Day 1 - Create reusable utility modules for code deduplication
- Phase 3 Day 2 - Refactor memory_tools.py using utility modules
- Phase 3 Day 2 - Refactor search_tools.py using utility modules
- Phase 3 Day 3 - Refactor knowledge_graph_tools.py using utility modules
- Phase 3 Day 3 - Refactor monitoring_tools.py using utility modules
- Phase 3 Day 3 - Refactor serverless_tools.py using utility modules
- Phase 3 Day 3 - Refactor validated_memory_tools.py using utility modules
- Phase 3 Day 4 - Refactor llm_tools.py using utility modules
- Phase 3 Day 4 - Refactor session_tools.py using utility modules
- Phase 3 Day 4 - Refactor team_tools.py using utility modules
- Phase 4 Day 1 - Extract crackerjack utilities for modularity
- Phase 4 Day 2 - Extract quality analysis utilities
- Phase 4 Day 3 - Extract serverless storage backends
- Phase 4 Day 4 - Extract session lifecycle utilities
- Phase 4 Day 5 - Extract LLM provider modules
- Phase 5 Day 1 - Extract advanced search utilities
- Phase 5 Day 2 - Extract scheduler utilities
- Phase 5 Day 3 - Extract server core modules
- Session-mgmt-mcp (quality: 68/100) - 2025-11-17 00:49:01
- Update config, core, deps
- Update config, deps
- Update documentation

### Fixed

- Add ACB_LIBRARY_MODE environment variable to crackerjack subprocess calls
- bugfixes
- Fix critical type checking errors exposed by crackerjack

### Documentation

- Add comprehensive ACB migration plan
- Add comprehensive ACB migration plan
- Add Phase 1 refactoring summary
- Cleanup and reorganize documentation structure
- Complete Phase 2.5 - ACB Graph Adapter Investigation
- Complete Phase 3 - Testing & Validation (Production Ready)
- Phase 3 Refactoring Complete - Summary Document
- Phase 4 Day 13 - User Documentation Complete
- Phase 4 Refactoring Complete - Summary Document
- Phase 4 Refactoring Plan - Large File Modularization
- Phase 5 Refactoring Complete - Summary Document
- Phase 5 Refactoring Plan - Advanced Feature Modularization
- Update migration plan - Phase 1 complete
- Update migration plan - Phase 2 complete
- Update migration plan - Phase 4 Day 13 complete

### Testing

- Improve test infrastructure and fix pytest 9.0+ compatibility
- Optimize test suite for speed and efficiency

### Internal

- Apply auto-formatting fixes from crackerjack hooks
- Update uv.lock with ACB GitHub source

## [0.9.2] - 2025-11-12

### Changed

- Session-mgmt-mcp (quality: 66/100) - 2025-11-09 01:16:15
- Session-mgmt-mcp (quality: 66/100) - 2025-11-09 03:04:03
- Update config, core, deps, docs, tests

## [0.9.1] - 2025-11-08

### Changed

- Update config, deps

## [0.8.0] - 2025-11-08

### Added

- architecture: Phase 2.1 - create server decomposition skeletons
- architecture: Phase 2.2 - extract 40 utility functions to server_helpers.py
- architecture: Phase 2.3 - extract quality engine (52 functions, 1,220 LOC)
- architecture: Phase 2.4 - extract advanced features (17 MCP tools, 621 LOC)
- architecture: Phase 2.5 - extract core infrastructure (17 functions, 2 classes, 614 LOC)
- architecture: Phase 2.6 - final cleanup (215 lines saved, 35.4% reduction)
- Complete Phase 1 ACB config migration
- Integrate mcp-common adapters and complete DuckPGQ knowledge graph (Week 2 Days 1-3)
- Migrate to ACB-backed cache adapters
- Phase 2 Priority 1 completion - add core module tests
- Phase 2 Priority 2 - comprehensive integration tests
- testing: Phase 2 - expand test coverage from 5.70% to 13.86% (111 new tests)
- Week 4 Day 3 - Knowledge Graph tests + Resource cleanup fixes
- Week 4 Days 1-2 - Health checks & server_core tests complete
- Week 4 Days 3-4 - Knowledge graph + LLM provider tests complete
- Week 5 Day 2 - Session Tools & Advanced Features Testing (51 tests, 100% pass rate)
- Week 5 Day 4 complete - Multi-project and app monitoring tests
- Week 8 Day 1 - Fix test isolation with before/after cleanup pattern

### Changed

- Complete all remaining complexity refactorings (11/11 done)
- DI pattern refinement and resource cleanup improvements
- Migrate serverless_mode.py to use aiocache instead of custom backends
- Modern Python style improvements (refurb FURB138, FURB107, FURB145, FURB168)
- Modernize SessionLifecycleManager DI pattern with Inject[] support
- Reduce cognitive complexity in OllamaProvider and knowledge graph tools
- Reduce complexity in cleanup and search functions (17→\<15)
- Reduce complexity of highest complexity functions (26, 28 → 10-12)
- Session-mgmt-mcp (quality: 68/100) - 2025-11-07 22:29:21
- Session-mgmt-mcp (quality: 68/100) - 2025-11-07 23:46:29
- Session-mgmt-mcp (quality: 70/100) - 2025-10-26 22:05:19
- Session-mgmt-mcp (quality: 70/100) - 2025-10-28 04:09:46
- Session-mgmt-mcp (quality: 70/100) - 2025-10-28 19:36:53
- Session-mgmt-mcp (quality: 70/100) - 2025-10-29 04:13:30
- Session-mgmt-mcp (quality: 70/100) - 2025-10-29 06:23:49
- Session-mgmt-mcp (quality: 70/100) - 2025-11-05 08:28:52
- Session-mgmt-mcp (quality: 70/100) - 2025-11-05 12:27:17
- Session-mgmt-mcp (quality: 70/100) - 2025-11-05 13:55:51
- Session-mgmt-mcp (quality: 71/100) - 2025-10-10 05:26:31
- Session-mgmt-mcp (quality: 71/100) - 2025-10-11 07:53:57
- Session-mgmt-mcp (quality: 75/100) - 2025-11-05 19:31:38
- Update config, core, deps, docs, tests
- Update depends.get() to depends.get_sync() for synchronous context

### Fixed

- Add safe JSON serialization for non-serializable objects in logging context
- Code quality improvements - type hints and style fixes
- Import typing as t to resolve NameError in SessionLifecycleManager
- PEP8 N806 - rename class variables from Logger/Requests to logger_class/requests_class
- Register SessionLogger in DI container to prevent checkpoint errors
- Replace all Any with t.Any and fix Logger DI reference
- Resolve remaining 7 unit test failures (Phase 2 Priority 2 completion)
- Resolve test infrastructure crisis - 14→0 collection errors
- Use depends.get_sync() for synchronous DI container access in server.py
- Week 4 regression fixes + technical debt documentation
- Week 6 Day 1 - DI environment handling and placeholder assertion

### Documentation

- Add ACB config migration summary and update README
- Add comprehensive code review for Week 2 Days 3-5 mcp-common integration
- Add comprehensive complexity refactoring progress tracker
- architecture: Add comprehensive server.py decomposition plan
- Comprehensive test coverage analysis and improvement plan
- Phase 2 Priority 1 completion summary and analysis
- phase1: Complete Phase 1 ACB foundation summary
- phase2: Add comprehensive Phase 2 progress summary
- Update comprehensive improvement plan with Phase 2 completion
- Week 3 checkpoint report - test infrastructure restoration complete
- Week 5 testing phase complete - comprehensive summary

### Testing

- Add comprehensive context manager tests (71 tests, 94.58% coverage)
- Add comprehensive health_tools tests and fix slow compaction test
- Add comprehensive tests for llm_providers.py helper functions
- Add comprehensive tests for memory_tools helper functions
- Add comprehensive tests for server.py helper functions
- Add comprehensive tests for Week 5 Day 3 modules (39 tests, 100% pass rate)
- Add comprehensive validated memory tools tests (38 tests, 80.86% coverage)
- Add knowledge graph adapter tests (27 tests, 17 passing, 52.16% coverage)
- Add knowledge_graph helper function tests (26 tests)
- Complete Week 5 Day 1 - Quality Engine & Crackerjack Tools coverage
- core: Update 9 files
- Implement comprehensive logging_utils tests

## [0.7.4] - 2025-10-08

### Documentation

- config: Update CHANGELOG, pyproject

## [0.7.3] - 2025-10-04

### Changed

- Session-mgmt-mcp (quality: 69/100) - 2025-10-04 12:39:57

### Documentation

- config: Update CHANGELOG, pyproject, uv

## [0.7.2] - 2025-10-04

### Testing

- config: Update 4 files

## [0.7.1] - 2025-10-04

### Testing

- test: Update 14 files

## [0.7.0] - 2025-10-04

### Added

- Add MCP tool input validation for crackerjack integration

### Changed

- Session-mgmt-mcp (quality: 69/100) - 2025-10-04 01:27:41

### Documentation

- Add comprehensive crackerjack integration guide
- config: Update CHANGELOG, pyproject, uv

## [0.6.5] - 2025-10-03

### Testing

- config: Update 4 files

## [0.6.4] - 2025-10-03

### Testing

- docs: Update 6 files

## [0.6.3] - 2025-10-03

### Testing

- docs: Update 9 files

## [0.6.2] - 2025-10-03

### Changed

- Session-mgmt-mcp (quality: 69/100) - 2025-10-03 02:50:35

### Testing

- config: Update 6 files

## [0.6.1] - 2025-10-03

### Testing

- config: Update 5 files

## [0.6.0] - 2025-10-03

### Changed

- Session-mgmt-mcp (quality: 69/100) - 2025-10-03 01:42:50

### Fixed

- Resolve hook failures and add coverage.json fallback

### Testing

- config: Update CHANGELOG, coverage, pyproject

## [0.5.3] - 2025-10-02

### Added

- Implement V2 quality scoring algorithm

### Changed

- quality_utils_v2: Fix refurb and complexipy violations
- Session-mgmt-mcp (quality: 73/100) - 2025-10-01 23:18:55

### Fixed

- quality: Add explicit float cast for type coverage
- quality: Resolve V2 linting issues

### Testing

- session_buddy: Update 7 files

### Internal

- Update coverage metrics to 32.6%
- Update coverage metrics to 32.7%

## [0.5.2] - 2025-10-01

### Documentation

- config: Update CHANGELOG, pyproject, uv

## [0.5.1] - 2025-10-01

### Documentation

- docs: Update 6 files

## [0.5.0] - 2025-10-01

### Changed

- Session-mgmt-mcp (quality: 73/100) - 2025-09-28 14:24:52
- Session-mgmt-mcp (quality: 73/100) - 2025-09-29 03:43:29
- Session-mgmt-mcp (quality: 73/100) - 2025-10-01 00:02:01

### Fixed

- test: Update 36 files

## [0.4.0] - 2025-09-28

### Changed

- Session-mgmt-mcp (quality: 73/100) - 2025-09-22 02:47:23
- Session-mgmt-mcp (quality: 73/100) - 2025-09-22 12:47:38
- Session-mgmt-mcp (quality: 73/100) - 2025-09-22 13:02:12
- Session-mgmt-mcp (quality: 73/100) - 2025-09-22 16:41:30
- Session-mgmt-mcp (quality: 73/100) - 2025-09-22 21:29:16
- Session-mgmt-mcp (quality: 76/100) - 2025-09-19 10:25:31
- Session-mgmt-mcp (quality: 76/100) - 2025-09-20 21:25:38
- Session-mgmt-mcp (quality: 76/100) - 2025-09-20 22:48:31
- Unknown (quality: 73/100) - 2025-09-25 05:20:04

### Fixed

- Resolve critical type annotation and missing function issues

### Removed

- Remove redundant Claude memory integration documentation

### Documentation

- config: Update CHANGELOG, pyproject, uv

## [0.3.13] - 2025-09-18

### Testing

- config: Update 6 files

## [0.3.12] - 2025-09-18

### Changed

- Session-mgmt-mcp (quality: 76/100) - 2025-09-18 16:08:50

### Documentation

- core: Update 12 files

## [0.3.11] - 2025-09-18

### Changed

- Unknown (quality: 76/100) - 2025-09-17 13:45:47

### Documentation

- config: Update 4 files

## [0.3.10] - 2025-09-16

### Testing

- test: Update 12 files

## [0.3.8] - 2025-09-15

### Documentation

- config: Update 4 files

## [0.3.7] - 2025-09-15

### Changed

- Session-mgmt-mcp (quality: 80/100) - 2025-09-15 19:18:59
- Update config, deps, docs

## [0.3.6] - 2025-09-15

### Changed

- Update config, core, deps, docs

## [0.3.5] - 2025-09-15

### Changed

- Update config, deps, docs

## [0.3.4] - 2025-09-14

### Changed

- Update config, deps, docs

## [0.3.3] - 2025-09-14

### Changed

- Update config, deps, docs

## [0.3.2] - 2025-09-14

### Changed

- Initial commit - Claude Session Management MCP Server
- Session-mgmt-mcp (quality: 80/100) - 2025-09-14 22:34:27
- Update config, deps, docs, tests
