# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.19.13] - 2026-06-15

### Testing

- Fan-out coverage push to 5 modules (~10% -> 77% peak)

## [0.19.12] - 2026-06-12

### Added

- akosha: Include source_type in sync payload (Item 1)
- conscious-agent: Multi-worker lock + unconditional access log
- ingesters: Claude_code_transcript ingester for LLM conversation capture
- mcp: Add distilled_skill_health tool (Item 4 cross-component)
- memory: Add migration --rollback and --verify-only safety nets
- memory: Add redaction library for transcript/PII scrubbing
- memory: Add v2 rewire columns, source_type CHECK, cross-tool index
- memory: Cross-tool search_by_source with source_type + project filter
- Memory_provenance table + memory_lineage MCP tool
- metrics: Expose Conscious Agent stats as Prometheus counters (Item 6)
- Rewire reflection adapter to v2 with redaction hook
- tier 10: add conftest-level db_path isolation fixture

### Changed

- search: Extract category-specific tool registration helpers (Item B)
- Session-buddy (quality: 60/100) - 2026-06-08 09:16:30
- Session-buddy (quality: 60/100) - 2026-06-08 11:59:08
- Session-buddy (quality: 60/100) - 2026-06-08 19:04:06
- Session-buddy (quality: 61/100) - 2026-06-05 18:46:10
- Session-buddy (quality: 61/100) - 2026-06-05 18:52:49
- Session-buddy (quality: 61/100) - 2026-06-05 19:11:31
- Session-buddy (quality: 61/100) - 2026-06-05 19:22:23
- Session-buddy (quality: 61/100) - 2026-06-05 19:28:42
- Session-buddy (quality: 62/100) - 2026-06-05 12:44:47
- Session-buddy (quality: 62/100) - 2026-06-05 18:30:24
- Session-buddy (quality: 62/100) - 2026-06-08 04:19:43
- Session-buddy (quality: 62/100) - 2026-06-08 06:23:30
- Session-buddy (quality: 62/100) - 2026-06-08 08:25:02
- Session-buddy (quality: 63/100) - 2026-06-08 06:35:48
- Session-buddy (quality: 64/100) - 2026-06-06 22:19:42
- Session-buddy (quality: 64/100) - 2026-06-07 00:24:56
- Switch v2 row IDs from UUID v4 to ULID
- tier 15: allow dots in branch names; reject .. for path traversal

### Fixed

- adapter+schema: Repair store_reflection + fingerprint_tools for v2 rewire
- fixup! chore(discovery): audit and fill ALL_TOOLS_REGISTRY (Item 5)
- fixup! feat(akosha): include source_type in sync payload (Item 1)
- fixup! feat(metrics): expose Conscious Agent stats as Prometheus counters (Item 6)
- tier 11: fix hardcoded dates and event loop staleness in tests
- tier 12: refine isolated_test_db_path fixture
- tier 13: fix broken DI fixture + worker hang/fail tests
- tier 14: route 4 DuckDB modules through get_settings() + fix telemetry test
- tier 16: fix 14 errors across 6 test files (logging, server_optimized, worktree_v2, instance_managers, query_rewriter, session_manager_high_impact, reflection_db)
- tier 17: fix get_stats key in health_checks + SSRF loopback allow
- tier 18: fix 3 more batch-isolated failures
- tier 19: fix 11 batch-isolated failures (git_operations + coverage_gaps)

### Documentation

- tier 20: doctor command + conftest pollution hardening + reflection shim

### Testing

- Mark DuckDB 1.5.3 bug as xfail in cascade tests

### Internal

- discovery: Audit and fill ALL_TOOLS_REGISTRY (Item 5)
- gitignore: Add backup file patterns to silence checkpoint tool artifacts
- tests: Clean up F401/F841 in test_akosha_sync_integration.py (Item C)
- Untrack and delete 55 historical *.backup/*.bak files

## [0.19.9] - 2026-06-02

### Changed

- Session-buddy (quality: 64/100) - 2026-06-02 15:18:05

## [0.19.8] - 2026-06-02

### Changed

- Session-buddy (quality: 62/100) - 2026-06-01 16:57:09
- Session-buddy (quality: 62/100) - 2026-06-01 17:08:42
- Session-buddy (quality: 62/100) - 2026-06-01 17:14:46
- Session-buddy (quality: 63/100) - 2026-06-01 18:49:23
- Session-buddy (quality: 63/100) - 2026-06-01 21:27:00
- Session-buddy (quality: 63/100) - 2026-06-02 04:10:50
- Session-buddy (quality: 63/100) - 2026-06-02 10:05:42

## [0.19.7] - 2026-05-31

### Changed

- Session-buddy (quality: 65/100) - 2026-05-31 06:58:06

## [0.19.5] - 2026-05-30

### Changed

- Session-buddy (quality: 63/100) - 2026-05-30 15:27:46

## [0.19.3] - 2026-05-30

### Changed

- Session-buddy (quality: 61/100) - 2026-05-22 07:57:08
- Session-buddy (quality: 63/100) - 2026-05-22 03:51:39
- Session-buddy (quality: 63/100) - 2026-05-23 02:18:51
- Session-buddy (quality: 63/100) - 2026-05-29 03:26:56

### Fixed

- reflection: Use settings pattern instead of deprecated db_path kwarg

### Testing

- session-buddy: Add tests for 3 uncovered adapters

## [0.19.0] - 2026-05-17

### Added

- llm: Add llama_server tier; update default fallback chain to minimax→llama_server→ollama

### Changed

- Consolidate LLMManager to delegate directly to mcp_common FallbackChain

### Fixed

- Address multi-agent review findings in LLMManager consolidation

## [0.18.0] - 2026-05-15

### Added

- Add DharaChannelPublisher for Phase 2 time-series publishing
- Wire DharaChannelPublisher in server startup via SESSION_BUDDY_DHARA_URL

### Fixed

- Correct dhara_url docstring priority, close publisher on shutdown
- DharaChannelPublisher aclose, named task, stable tests, declare httpx dep
- Hoist dhara publisher out of loop, settings integration, robust test task drain

## [0.17.0] - 2026-05-10

### Fixed

- quality-scorer: Read .coverage SQLite file when coverage.json absent

## [0.16.4] - 2026-05-01

### Added

- Add code_call_chain and code_impact_analysis MCP tools
- Delegate MCP auth to mcp_common.auth, keep full backward-compat API

### Changed

- Session-buddy (quality: 60/100) - 2026-04-21 05:11:16
- Session-buddy (quality: 60/100) - 2026-04-21 21:25:27
- Session-buddy (quality: 61/100) - 2026-04-24 13:09:06
- Session-buddy (quality: 61/100) - 2026-04-24 13:17:04
- Session-buddy (quality: 61/100) - 2026-04-24 15:36:12
- Session-buddy (quality: 61/100) - 2026-04-24 15:46:45
- Session-buddy (quality: 61/100) - 2026-04-26 21:17:07
- Session-buddy (quality: 62/100) - 2026-04-21 06:50:45
- Session-buddy (quality: 62/100) - 2026-04-21 20:36:13
- Session-buddy (quality: 62/100) - 2026-04-21 21:01:47
- Session-buddy (quality: 62/100) - 2026-04-21 21:18:01
- Session-buddy (quality: 62/100) - 2026-04-21 21:24:17

## [0.16.0] - 2026-04-13

### Changed

- Update config, core, deps, docs, tests

## [0.15.0] - 2026-04-07

### Changed

- Update dependencies

### Fixed

- session: Allow external workspace paths in \_setup_working_directory

## [0.14.8] - 2026-04-05

### Changed

- Update core, deps

### Internal

- repo: Ignore coverage artifacts

## [0.14.7] - 2026-04-03

### Changed

- Update config, core, deps, docs, tests

## [0.14.6] - 2026-03-20

### Changed

- Session-buddy (quality: 64/100) - 2026-03-20 08:39:33
- Update dependencies

## [0.14.5] - 2026-03-20

### Changed

- Update dependencies

## [0.14.4] - 2026-03-20

### Added

- Add health check tools using mcp-common
- Add pre_compact_sync tool for PreCompactHook integration
- Add PyCharm IDE tools for Session-Buddy
- treesitter: Add tree-sitter integration for code analysis

### Changed

- Session-buddy (quality: 75/100) - 2026-02-22 06:07:44
- Update dependencies

### Fixed

- Correct import paths for auto-compaction and reflection database
- Correct test fixtures and imports for IDE tools
- Initialize reflection database before storing checkpoint
- Register MCP prompts for slash command support

### Internal

- Add archive/backup directories to gitignore
- Remove .idea from git tracking, update dependencies
- Update LICENSE copyright to 2026

## [0.14.3] - 2026-02-20

### Fixed

- Resolve two MCP tool bugs

## [0.14.2] - 2026-02-18

### Changed

- Session-buddy (quality: 63/100) - 2026-02-18 00:42:35
- Session-buddy (quality: 75/100) - 2026-02-17 11:27:34

## [0.14.1] - 2026-02-17

### Added

- Add JWT authentication to Session-Buddy WebSocket

### Changed

- Session-buddy (quality: 63/100) - 2026-02-17 08:34:17
- Session-buddy (quality: 63/100) - 2026-02-17 08:52:43
- Session-buddy (quality: 63/100) - 2026-02-17 08:55:08
- Session-buddy (quality: 63/100) - 2026-02-17 08:58:00
- Session-buddy (quality: 75/100) - 2026-02-17 06:25:18
- Session-buddy (quality: 75/100) - 2026-02-17 07:39:00
- Session-buddy (quality: 75/100) - 2026-02-17 08:18:08
- Update core, docs

### Fixed

- WebSocket integration tests - V4 migration foreign key bug

### Documentation

- Add Phase 4 completion summary
- Add Phase 4 production monitoring and API documentation
- Add session checkpoint summary

### Testing

- Add Phase 4 analytics and integration tests
- Add WebSocket server load testing script

### Internal

- Session checkpoint - Phase 4 complete, production-ready
- Session checkpoint after Phase 4 WebSocket deployment

## [0.14.0] - 2026-02-10

### Added

- Add 10 Priority 1 security tests and fix subprocess helper bugs
- Implement category evolution enhancements with temporal decay
- Implement Session-Buddy Category Evolution TODOs
- Integrate Phase 3 semantic relationship enhancement

### Changed

- Update config, core, deps, docs, tests
- Update config, core, deps, docs, tests

### Fixed

- mcp: Align Session-Buddy with streamable-http transport

### Documentation

- Add complete Session Buddy database improvements summary
- Consolidate documentation - Phase 2.1 file migration
- Create core documentation - Phase 2.2/2.3 complete

## [0.13.0] - 2026-01-24

### Changed

- Update config, core, deps, tests

## [0.12.0] - 2026-01-24

### Changed

- Increase refurb timeout in crackerjack settings
- Session Checkpoint - 2026-01-23
- Update config, core, deps, docs, tests

## [0.11.1] - 2026-01-21

### Changed

- Phase 5 Category Evolution complete + Fast Hook Fixes
- Session-buddy (quality: 73/100)
- Session-buddy (quality: 73/100)
- Session-buddy (quality: 73/100) - 2026-01-19 13:32:16
- Session-buddy (quality: 73/100) - 2026-01-20 00:41:33
- Update config, core, deps, docs, tests

### Documentation

- Update references from session-mgmt to session-buddy

## [0.11.0] - 2026-01-18

### Changed

- Session-buddy (quality: 68/100) - 2026-01-11 15:59:11
- Session-buddy (quality: 68/100) - 2026-01-12 02:32:02
- Session-buddy (quality: 73/100) - 2026-01-15 20:30:12
- Session-buddy (quality: 73/100) - 2026-01-16 09:04:50
- Session-buddy (quality: 73/100) - 2026-01-18 17:09:44
- Session-buddy (quality: 73/100) - 2026-01-18 21:09:16

### Internal

- Organize and clean up working documentation
- Organize root directory scripts and tests

## [0.10.12] - 2026-01-08

### Changed

- Session-buddy (quality: 66/100) - 2026-01-08 03:25:05
- Update config, deps, docs

## [0.10.9] - 2026-01-05

### Changed

- Session-buddy (quality: 64/100) - 2026-01-05 08:54:44

## [0.10.8] - 2026-01-04

### Changed

- Session-buddy (quality: 64/100) - 2026-01-04 02:02:49

## [0.10.6] - 2026-01-03

### Changed

- Session-buddy (quality: 64/100) - 2026-01-03 09:18:41

## [0.10.4] - 2025-12-26

### Changed

- Session-buddy (quality: 58/100) - 2025-12-26 23:18:32
- Session-buddy (quality: 61/100) - 2025-12-20 14:20:48
- Session-buddy (quality: 61/100) - 2025-12-20 14:26:34
- Update config, deps, docs

## [0.10.3] - 2025-12-19

### Changed

- Session-buddy (quality: 66/100) - 2025-12-19 13:11:49
- Update config, deps, docs

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
