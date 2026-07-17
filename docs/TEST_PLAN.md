---
status: complete
role: historical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: architecture
---

# Phase 5: Test Plan

This plan summarizes test coverage for the Memori-inspired features and the suggested verifications.

## Unit Tests

- Schema & Migration
  - `tests/unit/test_schema_v2.py` – creates v2 tables
  - `tests/unit/test_migration.py` – dry run and migration, version checks
- Extraction Cascade & Persistence
  - `tests/unit/test_entity_extraction.py` – cascade success ordering
  - `tests/unit/test_extraction_retry.py` – timeouts/retries per provider
  - `tests/unit/test_persistence.py` – v2 inserts for conversations/entities/relationships
- Conscious Agent
  - `tests/unit/test_conscious_agent.py` – promotions and demotions
- Filesystem Integration
  - `tests/unit/test_fs_dedupe.py` – persistent dedupe behavior

## Integration Tests

- Filesystem-triggered extraction path (tool-level):
  - `tests/integration/test_filesystem_extraction.py` – tool persists v2 row with activity-weighted importance

## Manual & Smoke Tests

- Run the server with feature flags defaulted to ON; confirm extraction, access logging, agent tools, and v2 schema behave as expected. Then toggle flags OFF via env to verify graceful degradation with pattern fallback and no side-effects.
- Enable v2 and run `migration_status`, `trigger_migration(dry_run=true)`, then backup+migrate
- Verify access logging by running searches and checking `access_log_stats`
- Start the Conscious Agent and verify a promotion/demotion run using `force_conscious_analysis`
- Enable filesystem extraction and edit a file in a monitored project; verify a new v2 entry

## Coverage & Performance

- Target 85% coverage overall (progressive)
- Latency/Performance: collect extraction `extraction_time_ms` values at call sites; aggregate externally
