# Phase 5: Rollout Plan and Operations

This document describes a staged rollout of the Memori-inspired features behind feature flags, including migration, extraction, background optimization, and filesystem integration.

## Staged Enablement

- Day 1–2: Enable Schema v2

  - Set `SESSION_BUDDY_USE_SCHEMA_V2=true`
  - Run `migration_status` and `trigger_migration(dry_run=true)` to preview
  - Backup and migrate: `trigger_migration(create_backup_first=true)`
  - Verify counts and health: `migration_status`

- Day 3–4: Enable LLM Extraction (limited)

  - Set `SESSION_BUDDY_ENABLE_LLM_ENTITY_EXTRACTION=true`
  - Provide API keys as needed (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
  - Monitor usage by provider: `access_log_stats(by_provider)`

- Day 5–6: Enable Conscious Agent

  - Set `SESSION_BUDDY_ENABLE_CONSCIOUS_AGENT=true`
  - Start agent: `start_conscious_agent(interval_hours=6)`
  - Force one-time analysis: `force_conscious_analysis`

- Day 7: Enable Filesystem Extraction

  - Set `SESSION_BUDDY_ENABLE_FILESYSTEM_EXTRACTION=true`
  - Tune settings: `filesystem_dedupe_ttl_seconds`, `filesystem_max_file_size_bytes`, `filesystem_ignore_dirs`

## Monitoring and Metrics

- Access Logs: `access_log_stats(hours=24, top_n=10, project?, namespace?)`
  - `total_accesses`, `distinct_memories`, `by_type`, `by_provider`, `top_memories`, `recent`
- Provider Costs: Estimate via `by_provider` counts and your model pricing
- Latency: Extraction tool returns `extraction_time_ms`; aggregate externally for SLOs

## Rollback

- Check `migration_status`
- Restore backup: `rollback_migration(backup_path)`

## Notes

- Flags now default `true`. If you prefer a staged rollout, disable selectively via environment variables (e.g., `SESSION_BUDDY_USE_SCHEMA_V2=false`, `SESSION_BUDDY_ENABLE_LLM_ENTITY_EXTRACTION=false`, `SESSION_BUDDY_ENABLE_CONSCIOUS_AGENT=false`, `SESSION_BUDDY_ENABLE_FILESYSTEM_EXTRACTION=false`).
- Use `feature_flags_status` and `rollout_plan` for operational guidance
- All changes are backward-compatible (parallel v1/v2)
