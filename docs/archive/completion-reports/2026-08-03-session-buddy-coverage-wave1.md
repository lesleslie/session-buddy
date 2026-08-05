# Wave-1 Coverage Completion Report

**Date:** 2026-08-05T02:05:32.865485Z
**Wave spec:** `docs/superpowers/specs/2026-08-03-session-buddy-coverage-improvement-design.md` (v2)
**Baseline:** `docs/baselines/wave1-baseline.json`
**Delta:** `docs/baselines/wave1-delta.json`

## Summary

- **Modules lifted to ≥95% line:** 13
- **New failures introduced by wave-1:** 0
- **Sync/async defensiveness `sync_async_hit_count`:** 73 unjustified hits, 3 justified
- **CLAUDE.md gate (`--cov-fail-under=85`):** UNCHANGED — wave-1 prepares, does not raise

## Per-module before / after

| Module | Before | After | Δ | Tier |
|---|---|---|---|---|
| `session_buddy/cli.py` | 71.7% | 98.3% | +26.6 | good |
| `session_buddy/cli_with_modes.py` | 78.7% | 98.0% | +19.2 | good |
| `session_buddy/core/causal_chains.py` | 57.0% | 100.0% | +43.0 | good |
| `session_buddy/core/conversation_storage.py` | 76.7% | 100.0% | +23.3 | good |
| `session_buddy/mcp/tools/code_graph.py` | 74.3% | 100.0% | +25.7 | good |
| `session_buddy/mcp/tools/collaboration/team_tools.py` | 94.3% | 95.0% | +0.7 | good |
| `session_buddy/mcp/tools/infrastructure/history_cache.py` | 94.0% | 100.0% | +6.0 | good |
| `session_buddy/mcp/tools/memory/akosha_tools.py` | 84.4% | 100.0% | +15.6 | good |
| `session_buddy/mcp/tools/session/admin_shell_tracking_tools.py` | 62.5% | 100.0% | +37.5 | good |
| `session_buddy/mcp/tools/session/prompt_tools.py` | 85.0% | 100.0% | +15.0 | good |
| `session_buddy/utils/database_pool.py` | 88.0% | 96.4% | +8.4 | good |
| `session_buddy/utils/quality_scoring.py` | 91.9% | 96.1% | +4.2 | good |
| `session_buddy/utils/scheduler/time_parser.py` | 71.0% | 97.8% | +26.8 | good |
| `session_buddy/__main__.py` | 100.0% | 71.4% | -28.6 | partial |
| `session_buddy/adapters/knowledge_graph_adapter.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/adapters/knowledge_graph_adapter_oneiric.py` | 81.8% | 80.3% | -1.5 | good |
| `session_buddy/adapters/knowledge_graph_adapter_phase3.py` | 97.3% | 97.3% | -0.0 | good |
| `session_buddy/adapters/knowledge_graph_phase3_patch.py` | 96.6% | 96.6% | -0.0 | good |
| `session_buddy/adapters/lifecycle.py` | 43.7% | 43.5% | -0.2 | low |
| `session_buddy/adapters/reflection_adapter.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/adapters/reflection_adapter_oneiric.py` | 85.2% | 74.4% | -10.8 | partial |
| `session_buddy/adapters/serverless_storage_adapter.py` | 83.6% | 83.6% | +0.0 | good |
| `session_buddy/adapters/session_storage_adapter.py` | 93.6% | 93.6% | -0.0 | good |
| `session_buddy/adapters/settings.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/adapters/storage_oneiric.py` | 87.3% | 87.3% | +0.0 | good |
| `session_buddy/advanced_features.py` | 95.2% | 94.9% | -0.3 | good |
| `session_buddy/advanced_search.py` | 75.5% | 75.5% | -0.0 | partial |
| `session_buddy/analytics/ab_testing.py` | 98.8% | 100.0% | +1.2 | good |
| `session_buddy/analytics/cli.py` | 100.0% | 99.1% | -0.9 | good |
| `session_buddy/analytics/collaborative_filtering.py` | 71.1% | 15.3% | -55.8 | low |
| `session_buddy/analytics/predictive.py` | 20.6% | 20.6% | +0.0 | low |
| `session_buddy/analytics/session_analytics.py` | 93.5% | 92.6% | -0.8 | good |
| `session_buddy/analytics/time_series.py` | 80.9% | 80.9% | +0.0 | good |
| `session_buddy/analytics/usage_tracker.py` | 94.2% | 94.2% | +0.0 | good |
| `session_buddy/app_monitor.py` | 89.1% | 86.2% | -2.8 | good |
| `session_buddy/backends/base.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/backends/local_backend.py` | 84.3% | 84.3% | -0.0 | good |
| `session_buddy/backends/redis_backend.py` | 86.7% | 87.2% | +0.5 | good |
| `session_buddy/backends/s3_backend.py` | 82.9% | 83.2% | +0.3 | good |
| `session_buddy/cache/query_cache.py` | 60.9% | 60.9% | -0.0 | partial |
| `session_buddy/code_analysis/kg_extractor.py` | 99.1% | 99.1% | +0.0 | good |
| `session_buddy/commands/checkpoint.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/config/feature_flags.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/context/optimizer.py` | 72.1% | 72.3% | +0.2 | partial |
| `session_buddy/context_manager.py` | 95.7% | 95.7% | +0.0 | good |
| `session_buddy/core/bottleneck_detector.py` | 75.3% | 75.3% | -0.0 | partial |
| `session_buddy/core/features.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/core/hooks.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/core/intelligence.py` | 90.0% | 90.1% | +0.1 | good |
| `session_buddy/core/intent_detector.py` | 98.2% | 97.7% | -0.6 | good |
| `session_buddy/core/lifecycle/handoff.py` | 95.8% | 95.8% | +0.0 | good |
| `session_buddy/core/lifecycle/project_context.py` | 97.9% | 97.9% | -0.0 | good |
| `session_buddy/core/lifecycle/service_registry.py` | 94.5% | 94.5% | -0.0 | good |
| `session_buddy/core/lifecycle/session_info.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/core/memory_health.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/core/permissions.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/core/quality_scoring.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/core/session_analytics.py` | 21.4% | 21.4% | -0.0 | low |
| `session_buddy/core/session_manager.py` | 96.8% | 92.1% | -4.7 | good |
| `session_buddy/core/skills_tracker.py` | 68.7% | 68.4% | -0.3 | partial |
| `session_buddy/core/ulid_generator.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/core/workflow_metrics.py` | 95.4% | 93.7% | -1.7 | good |
| `session_buddy/crackerjack_integration.py` | 91.2% | 90.1% | -1.1 | good |
| `session_buddy/di/config.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/di/constants.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/di/container.py` | 62.6% | 63.9% | +1.2 | partial |
| `session_buddy/doctor.py` | 96.0% | 96.0% | +0.1 | good |
| `session_buddy/health_checks.py` | 90.4% | 89.2% | -1.2 | good |
| `session_buddy/hooks/single_flight.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/ingesters/claude_code_transcript.py` | 97.8% | 97.8% | +0.0 | good |
| `session_buddy/ingesters/redaction.py` | 96.6% | 63.3% | -33.3 | partial |
| `session_buddy/insights/console.py` | 84.8% | 84.7% | -0.0 | good |
| `session_buddy/insights/extractor.py` | 91.7% | 91.7% | -0.0 | good |
| `session_buddy/insights/models.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/integrations/cicd_tracker.py` | 97.3% | 97.3% | +0.0 | good |
| `session_buddy/integrations/crackerjack_hooks.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/integrations/ide_plugin.py` | 91.4% | 91.4% | -0.0 | good |
| `session_buddy/interruption_manager.py` | 74.4% | 82.8% | +8.4 | good |
| `session_buddy/knowledge_graph_db.py` | 95.4% | 94.3% | -1.1 | good |
| `session_buddy/llm/base.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/llm/models.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/llm/providers/anthropic_provider.py` | 100.0% | 98.7% | -1.3 | good |
| `session_buddy/llm/providers/gemini_provider.py` | 97.2% | 97.3% | +0.1 | good |
| `session_buddy/llm/providers/ollama_provider.py` | 83.8% | 82.6% | -1.1 | good |
| `session_buddy/llm/providers/openai_provider.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/llm/security.py` | 97.9% | 96.7% | -1.3 | good |
| `session_buddy/llm_providers.py` | 87.3% | 86.7% | -0.7 | good |
| `session_buddy/mcp/auth.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/code_formatter.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/event_models.py` | 99.6% | 83.5% | -16.1 | good |
| `session_buddy/mcp/metrics.py` | 100.0% | 99.1% | -0.9 | good |
| `session_buddy/mcp/quality_scorer.py` | 75.0% | 70.6% | -4.4 | partial |
| `session_buddy/mcp/schemas.py` | 100.0% | 97.5% | -2.5 | good |
| `session_buddy/mcp/server.py` | 75.9% | 75.9% | -0.0 | partial |
| `session_buddy/mcp/server_core.py` | 94.1% | 93.6% | -0.5 | good |
| `session_buddy/mcp/session_tracker.py` | 100.0% | 17.2% | -82.8 | low |
| `session_buddy/mcp/telemetry.py` | 100.0% | 88.9% | -11.1 | good |
| `session_buddy/mcp/tools/advanced/conscious_agent_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/advanced/entity_extraction_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/advanced/fingerprint_tools.py` | 85.2% | 77.6% | -7.6 | partial |
| `session_buddy/mcp/tools/advanced/intent_detection_tools.py` | 87.0% | 87.0% | -0.0 | good |
| `session_buddy/mcp/tools/advanced/intent_tools_registration.py` | 100.0% | 80.3% | -19.7 | good |
| `session_buddy/mcp/tools/advanced/recommendation_engine.py` | 84.7% | 84.7% | -0.0 | good |
| `session_buddy/mcp/tools/advanced/rewriting_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/code_analysis/tools.py` | 40.8% | 40.8% | -0.0 | low |
| `session_buddy/mcp/tools/collaboration/knowledge_graph_phase3_tools.py` | 85.7% | 85.7% | +0.0 | good |
| `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py` | 85.4% | 85.4% | -0.0 | good |
| `session_buddy/mcp/tools/conversation/conversation_tools.py` | 19.4% | 19.4% | -0.0 | low |
| `session_buddy/mcp/tools/discovery_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/ide.py` | 99.3% | 99.7% | +0.3 | good |
| `session_buddy/mcp/tools/infrastructure/access_log_tools.py` | 96.1% | 96.1% | +0.0 | good |
| `session_buddy/mcp/tools/infrastructure/cache_tools.py` | 32.5% | 32.5% | -0.0 | low |
| `session_buddy/mcp/tools/infrastructure/feature_flags_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/infrastructure/hook_parser.py` | 96.0% | 96.2% | +0.2 | good |
| `session_buddy/mcp/tools/infrastructure/pools.py` | 51.4% | 51.4% | -0.0 | partial |
| `session_buddy/mcp/tools/infrastructure/protocols.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/infrastructure/serverless_tools.py` | 93.5% | 93.5% | +0.0 | good |
| `session_buddy/mcp/tools/intelligence/agent_analyzer.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/intelligence/intelligence_tools.py` | 22.3% | 22.3% | -0.0 | low |
| `session_buddy/mcp/tools/intelligence/llm_tools.py` | 85.2% | 85.4% | +0.1 | good |
| `session_buddy/mcp/tools/memory/category_tools.py` | 11.9% | 11.9% | -0.0 | low |
| `session_buddy/mcp/tools/memory/export_tools.py` | 54.2% | 54.2% | +0.0 | partial |
| `session_buddy/mcp/tools/memory/memory_tools.py` | 93.2% | 93.2% | -0.0 | good |
| `session_buddy/mcp/tools/memory/otel_trace_tools.py` | 68.0% | 68.0% | +0.0 | partial |
| `session_buddy/mcp/tools/memory/search_tools.py` | 57.1% | 55.5% | -1.6 | partial |
| `session_buddy/mcp/tools/memory/validated_memory_tools.py` | 91.4% | 88.7% | -2.7 | good |
| `session_buddy/mcp/tools/monitoring/bottleneck_tools.py` | 65.3% | 65.3% | +0.0 | partial |
| `session_buddy/mcp/tools/monitoring/health_tools.py` | 20.3% | 20.3% | -0.0 | low |
| `session_buddy/mcp/tools/monitoring/memory_health_tools.py` | 79.0% | 79.0% | +0.0 | partial |
| `session_buddy/mcp/tools/monitoring/monitoring_tools.py` | 81.6% | 81.6% | +0.0 | good |
| `session_buddy/mcp/tools/monitoring/prometheus_metrics_tools.py` | 91.7% | 86.0% | -5.6 | good |
| `session_buddy/mcp/tools/monitoring/session_analytics_tools.py` | 50.4% | 50.4% | -0.0 | partial |
| `session_buddy/mcp/tools/monitoring/workflow_metrics_tools.py` | 79.0% | 78.9% | -0.0 | partial |
| `session_buddy/mcp/tools/profiles.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/session/channel_tracking_tools.py` | 88.7% | 87.6% | -1.1 | good |
| `session_buddy/mcp/tools/session/crackerjack_tools.py` | 81.7% | 82.4% | +0.7 | good |
| `session_buddy/mcp/tools/session/hooks_tools.py` | 26.1% | 26.1% | -0.0 | low |
| `session_buddy/mcp/tools/session/migration_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/session/session_tools.py` | 73.5% | 74.0% | +0.5 | partial |
| `session_buddy/mcp/tools/skills/phase4_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/mcp/tools/worktree_tools.py` | 65.0% | 65.0% | +0.0 | partial |
| `session_buddy/memory/category_evolution.py` | 86.3% | 86.5% | +0.2 | good |
| `session_buddy/memory/causal.py` | 85.8% | 15.8% | -70.0 | low |
| `session_buddy/memory/conscious_agent.py` | 67.2% | 52.7% | -14.5 | partial |
| `session_buddy/memory/entity_extractor.py` | 65.5% | 64.2% | -1.3 | partial |
| `session_buddy/memory/evolution_config.py` | 71.8% | 71.8% | -0.0 | partial |
| `session_buddy/memory/file_context.py` | 92.0% | 92.0% | +0.0 | good |
| `session_buddy/memory/migration.py` | 73.9% | 63.8% | -10.1 | partial |
| `session_buddy/memory/peer_modeling.py` | 62.3% | 15.6% | -46.8 | low |
| `session_buddy/memory/persistence.py` | 89.5% | 86.1% | -3.4 | good |
| `session_buddy/memory/schema_v2.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/memory_optimizer.py` | 93.9% | 93.9% | +0.0 | good |
| `session_buddy/metrics.py` | 88.4% | 76.7% | -11.6 | partial |
| `session_buddy/modes/base.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/modes/lite.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/modes/standard.py` | 100.0% | 93.3% | -6.7 | good |
| `session_buddy/multi_project_coordinator.py` | 94.0% | 94.0% | +0.0 | good |
| `session_buddy/natural_scheduler.py` | 94.0% | 94.0% | -0.0 | good |
| `session_buddy/parameter_models.py` | 84.0% | 84.0% | +0.0 | good |
| `session_buddy/pools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/quality_engine.py` | 96.1% | 95.4% | -0.7 | good |
| `session_buddy/realtime/auth.py` | 90.9% | 90.9% | -0.0 | good |
| `session_buddy/realtime/metrics_exporter.py` | 100.0% | 66.0% | -34.0 | partial |
| `session_buddy/realtime/websocket_server.py` | 60.5% | 12.3% | -48.2 | low |
| `session_buddy/reflection/database.py` | 69.5% | 74.5% | +5.0 | partial |
| `session_buddy/reflection/embeddings.py` | 66.1% | 41.7% | -24.4 | low |
| `session_buddy/reflection/schema.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/reflection/search.py` | 54.7% | 54.7% | -0.0 | partial |
| `session_buddy/reflection/storage.py` | 47.6% | 57.9% | +10.2 | partial |
| `session_buddy/reflection_tools.py` | 100.0% | 91.3% | -8.7 | good |
| `session_buddy/resource_cleanup.py` | 98.7% | 97.9% | -0.8 | good |
| `session_buddy/rewriting/hooks_integration.py` | 21.6% | 21.6% | +0.0 | low |
| `session_buddy/rewriting/query_rewriter.py` | 97.2% | 97.2% | +0.0 | good |
| `session_buddy/search/progressive_search.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/search_enhanced.py` | 98.5% | 98.0% | -0.6 | good |
| `session_buddy/security/memory_guard_adapter.py` | 88.8% | 88.9% | +0.1 | good |
| `session_buddy/server.py` | 91.0% | 89.5% | -1.4 | good |
| `session_buddy/server_optimized.py` | 87.0% | 81.0% | -6.0 | good |
| `session_buddy/serverless_mode.py` | 98.3% | 98.3% | +0.0 | good |
| `session_buddy/services/git_maintenance.py` | 92.0% | 92.0% | -0.0 | good |
| `session_buddy/session_commands.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/session_types.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/settings.py` | 91.0% | 91.0% | +0.0 | good |
| `session_buddy/shell/adapter.py` | 98.4% | 98.4% | -0.0 | good |
| `session_buddy/shutdown_manager.py` | 97.7% | 97.6% | -0.0 | good |
| `session_buddy/skills/distiller.py` | 86.5% | 21.9% | -64.6 | low |
| `session_buddy/storage/akosha_config.py` | 92.9% | 81.7% | -11.2 | good |
| `session_buddy/storage/akosha_sync.py` | 52.4% | 48.1% | -4.3 | low |
| `session_buddy/storage/cloud_sync.py` | 65.8% | 43.7% | -22.1 | low |
| `session_buddy/storage/ipfs.py` | 15.5% | 15.5% | -0.0 | low |
| `session_buddy/storage/skills_embeddings.py` | 84.0% | 49.0% | -35.0 | low |
| `session_buddy/storage/skills_storage.py` | 60.5% | 17.6% | -42.9 | low |
| `session_buddy/storage/sync_protocol.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/subscribers/code_graph_subscriber.py` | 11.9% | 11.9% | -0.0 | low |
| `session_buddy/sync.py` | 93.4% | 91.1% | -2.3 | good |
| `session_buddy/team_knowledge.py` | 95.8% | 95.8% | +0.0 | good |
| `session_buddy/token_optimizer.py` | 96.1% | 95.6% | -0.5 | good |
| `session_buddy/tools/health_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/tools/memory_tools.py` | 56.2% | 56.2% | +0.0 | partial |
| `session_buddy/tools/quality_metrics.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/tools/search_tools.py` | 61.5% | 61.5% | -0.0 | partial |
| `session_buddy/tools/session_tools.py` | 66.7% | 66.7% | -0.0 | partial |
| `session_buddy/types.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/crackerjack/fallback.py` | 85.4% | 81.2% | -4.2 | good |
| `session_buddy/utils/crackerjack/output_parser.py` | 66.3% | 62.6% | -3.7 | partial |
| `session_buddy/utils/crackerjack/pattern_builder.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/database_tools.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/encryption.py` | 100.0% | 98.3% | -1.7 | good |
| `session_buddy/utils/error_management.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/file_utils.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/filesystem.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/fingerprint.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/git_operations.py` | 99.0% | 99.0% | -0.0 | good |
| `session_buddy/utils/git_worktrees.py` | 87.7% | 87.5% | -0.2 | good |
| `session_buddy/utils/instance_managers.py` | 96.8% | 95.7% | -1.1 | good |
| `session_buddy/utils/lazy_imports.py` | 99.3% | 98.7% | -0.6 | good |
| `session_buddy/utils/logging.py` | 99.3% | 99.3% | -0.0 | good |
| `session_buddy/utils/logging_utils.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/messages.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/path_validation.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/project_analysis.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/quality/compaction.py` | 98.6% | 98.6% | +0.0 | good |
| `session_buddy/utils/quality/recommendations.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/quality/summary.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/quality_score_parser.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/quality_utils_v2.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/reflection_utils.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/regex_patterns.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/runtime_snapshots.py` | 97.3% | 97.3% | +0.0 | good |
| `session_buddy/utils/scheduler/models.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/search/models.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/search/utilities.py` | 98.9% | 98.9% | +0.0 | good |
| `session_buddy/utils/session_formatters.py` | 97.2% | 97.2% | +0.0 | good |
| `session_buddy/utils/subprocess_executor.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/text_formatter.py` | 97.7% | 97.7% | +0.0 | good |
| `session_buddy/utils/time.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/utils/tool_wrapper.py` | 100.0% | 100.0% | +0.0 | good |
| `session_buddy/worker.py` | 99.4% | 99.4% | +0.0 | good |
| `session_buddy/worktree_manager.py` | 82.7% | 87.1% | +4.4 | good |

## Batch gates

- **Batch 1a:** 5 modules merged; new failures = 0
- **Batch 1b:** 5 modules merged; new failures = 0

## Outcomes vs spec

- **G1 (backlog doc):** PASS
- **G2 (audit script):** PASS
- **G3 (10 modules ≥95% line + ≥90% branch):** PASS — count=13
- **G4 (sync/async blocking):** FAIL — 73 unjustified hits
- **G5 (no new failures):** PASS
- **G6 (this report):** PASS

## Blockers hit

(None yet — see commit history or task reports.)

## Wave-2 next steps

- Modules still in `untested` or `low` tier are wave-2/3 candidates.
- If wave-1 reaches >95% lifted, a follow-up plan may propose raising per-module coverage or amending CLAUDE.md's `--cov-fail-under=85` for the (now achievable) global gate.

## Raw artifacts

- `coverage.json` (gitignored)
- `docs/baselines/wave1-baseline.json`
- `docs/baselines/wave1-batch1a-delta.json`
- `docs/baselines/wave1-batch1b-delta.json`
- `docs/baselines/wave1-delta.json`
- `docs/baselines/wave1-anti-targets.json`
- `docs/baselines/wave1-selected.json`
