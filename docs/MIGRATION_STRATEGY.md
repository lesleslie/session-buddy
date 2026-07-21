______________________________________________________________________

## status: complete role: historical date: 2026-07-16 last_reviewed: 2026-07-16 superseded_by: null blocks_on: [] topic: oneiric-config

# Migration Strategy: Schema v1 → v2

This guide explains how session-buddy migrates legacy `conversations` and `reflections` tables to the enhanced Memori-inspired schema v2.

## Overview

- Parallel schema: v1 tables continue to exist alongside v2 during rollout
- Auto-detect version on startup (tools or hooks may call migration utilities)
- Backup before migration and rollback support
- Preserve ONNX embeddings and metadata

## Versioning

- `schema_meta(schema_version)` tracks the active schema version
- `schema_migrations` logs migration attempts (pending/success/failed)

## What Changes

- New tables: `conversations_v2`, `reflections_v2`, `memory_entities`, `memory_relationships`, `memory_promotions`, `memory_access_log`
- Categorization, tiering, access tracking, and indexing for performance

## Commands (Python API)

- `needs_migration()` → bool
- `migrate_v1_to_v2(dry_run: bool = False)` → MigrationResult
- `get_migration_status()` → dict
- `create_backup()` / `restore_backup(path)`

## Rollout

1. Run with feature flags OFF (default)
1. Migrate data while v1 continues to work
1. Enable `use_schema_v2` once validated
1. Gradually enable LLM extraction and conscious agent

## Safety

- Migration is idempotent and best-effort
- Stats and errors recorded in `schema_migrations`
- Rollback by restoring the DB backup
