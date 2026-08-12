# Coverage Backlog

> Regenerated from coverage.json

## Tier definitions

| Tier | Coverage | Action |
|---|---|---|
| untested | 0% | Write at least smoke tests |
| low | 1-49% | Targeted gap-fill |
| partial | 50-79% | Continue tests |
| good | 80%+ | Maintain |

## Per-directory backlog

### `session_buddy/__main__.py`

- pct: 71.4, lines: 5, tier: partial

### `session_buddy/adapters/knowledge_graph_adapter.py`

- pct: 100.0, lines: 3, tier: good

### `session_buddy/adapters/knowledge_graph_adapter_oneiric.py`

- pct: 80.3, lines: 358, tier: good

### `session_buddy/adapters/knowledge_graph_adapter_phase3.py`

- pct: 97.3, lines: 123, tier: good

### `session_buddy/adapters/knowledge_graph_phase3_patch.py`

- pct: 96.6, lines: 118, tier: good

### `session_buddy/adapters/lifecycle.py`

- pct: 43.5, lines: 142, tier: low

### `session_buddy/adapters/reflection_adapter.py`

- pct: 100.0, lines: 3, tier: good

### `session_buddy/adapters/reflection_adapter_oneiric.py`

- pct: 74.4, lines: 808, tier: partial

### `session_buddy/adapters/serverless_storage_adapter.py`

- pct: 83.6, lines: 112, tier: good

### `session_buddy/adapters/session_storage_adapter.py`

- pct: 93.6, lines: 98, tier: good

### `session_buddy/adapters/settings.py`

- pct: 100.0, lines: 55, tier: good

### `session_buddy/adapters/storage_oneiric.py`

- pct: 87.3, lines: 264, tier: good

### `session_buddy/advanced_features.py`

- pct: 94.9, lines: 389, tier: good

### `session_buddy/advanced_search.py`

- pct: 75.5, lines: 396, tier: partial

### `session_buddy/analytics/ab_testing.py`

- pct: 100.0, lines: 142, tier: good

### `session_buddy/analytics/cli.py`

- pct: 99.1, lines: 169, tier: good

### `session_buddy/analytics/collaborative_filtering.py`

- pct: 15.3, lines: 128, tier: low

### `session_buddy/analytics/predictive.py`

- pct: 20.6, lines: 95, tier: low

### `session_buddy/analytics/session_analytics.py`

- pct: 92.6, lines: 275, tier: good

### `session_buddy/analytics/time_series.py`

- pct: 80.9, lines: 118, tier: good

### `session_buddy/analytics/usage_tracker.py`

- pct: 94.2, lines: 112, tier: good

### `session_buddy/app_monitor.py`

- pct: 86.2, lines: 448, tier: good

### `session_buddy/backends/base.py`

- pct: 100.0, lines: 53, tier: good

### `session_buddy/backends/local_backend.py`

- pct: 84.3, lines: 90, tier: good

### `session_buddy/backends/redis_backend.py`

- pct: 87.2, lines: 128, tier: good

### `session_buddy/backends/s3_backend.py`

- pct: 83.2, lines: 131, tier: good

### `session_buddy/cache/query_cache.py`

- pct: 60.9, lines: 218, tier: partial

### `session_buddy/cli.py`

- pct: 98.3, lines: 97, tier: good

### `session_buddy/cli_with_modes.py`

- pct: 98.0, lines: 92, tier: good

### `session_buddy/code_analysis/kg_extractor.py`

- pct: 99.1, lines: 85, tier: good

### `session_buddy/commands/checkpoint.py`

- pct: 100.0, lines: 18, tier: good

### `session_buddy/config/feature_flags.py`

- pct: 100.0, lines: 24, tier: good

### `session_buddy/context/optimizer.py`

- pct: 72.3, lines: 113, tier: partial

### `session_buddy/context_manager.py`

- pct: 95.7, lines: 266, tier: good

### `session_buddy/core/bottleneck_detector.py`

- pct: 75.3, lines: 185, tier: partial

### `session_buddy/core/causal_chains.py`

- pct: 100.0, lines: 116, tier: good

### `session_buddy/core/conversation_storage.py`

- pct: 100.0, lines: 108, tier: good

### `session_buddy/core/features.py`

- pct: 100.0, lines: 104, tier: good

### `session_buddy/core/hooks.py`

- pct: 100.0, lines: 185, tier: good

### `session_buddy/core/intelligence.py`

- pct: 90.1, lines: 405, tier: good

### `session_buddy/core/intent_detector.py`

- pct: 97.7, lines: 123, tier: good

### `session_buddy/core/lifecycle/handoff.py`

- pct: 95.8, lines: 42, tier: good

### `session_buddy/core/lifecycle/project_context.py`

- pct: 97.9, lines: 40, tier: good

### `session_buddy/core/lifecycle/service_registry.py`

- pct: 94.5, lines: 163, tier: good

### `session_buddy/core/lifecycle/session_info.py`

- pct: 100.0, lines: 87, tier: good

### `session_buddy/core/memory_health.py`

- pct: 100.0, lines: 119, tier: good

### `session_buddy/core/permissions.py`

- pct: 100.0, lines: 103, tier: good

### `session_buddy/core/quality_scoring.py`

- pct: 100.0, lines: 25, tier: good

### `session_buddy/core/session_analytics.py`

- pct: 21.4, lines: 268, tier: low

### `session_buddy/core/session_manager.py`

- pct: 92.1, lines: 507, tier: good

### `session_buddy/core/skills_tracker.py`

- pct: 68.4, lines: 223, tier: partial

### `session_buddy/core/ulid_generator.py`

- pct: 100.0, lines: 27, tier: good

### `session_buddy/core/workflow_metrics.py`

- pct: 93.7, lines: 193, tier: good

### `session_buddy/crackerjack_integration.py`

- pct: 90.1, lines: 464, tier: good

### `session_buddy/di/config.py`

- pct: 100.0, lines: 21, tier: good

### `session_buddy/di/constants.py`

- pct: 100.0, lines: 5, tier: good

### `session_buddy/di/container.py`

- pct: 63.9, lines: 63, tier: partial

### `session_buddy/doctor.py`

- pct: 96.0, lines: 226, tier: good

### `session_buddy/health_checks.py`

- pct: 89.2, lines: 225, tier: good

### `session_buddy/hooks/single_flight.py`

- pct: 100.0, lines: 22, tier: good

### `session_buddy/ingesters/claude_code_transcript.py`

- pct: 97.8, lines: 130, tier: good

### `session_buddy/ingesters/redaction.py`

- pct: 63.3, lines: 40, tier: partial

### `session_buddy/insights/console.py`

- pct: 84.7, lines: 51, tier: good

### `session_buddy/insights/extractor.py`

- pct: 91.7, lines: 160, tier: good

### `session_buddy/insights/models.py`

- pct: 100.0, lines: 82, tier: good

### `session_buddy/integrations/cicd_tracker.py`

- pct: 97.3, lines: 161, tier: good

### `session_buddy/integrations/crackerjack_hooks.py`

- pct: 100.0, lines: 87, tier: good

### `session_buddy/integrations/ide_plugin.py`

- pct: 91.4, lines: 134, tier: good

### `session_buddy/interruption_manager.py`

- pct: 82.8, lines: 363, tier: good

### `session_buddy/knowledge_graph_db.py`

- pct: 94.3, lines: 222, tier: good

### `session_buddy/llm/base.py`

- pct: 100.0, lines: 17, tier: good

### `session_buddy/llm/models.py`

- pct: 100.0, lines: 46, tier: good

### `session_buddy/llm/providers/anthropic_provider.py`

- pct: 98.7, lines: 62, tier: good

### `session_buddy/llm/providers/gemini_provider.py`

- pct: 97.3, lines: 84, tier: good

### `session_buddy/llm/providers/ollama_provider.py`

- pct: 82.6, lines: 133, tier: good

### `session_buddy/llm/providers/openai_provider.py`

- pct: 100.0, lines: 60, tier: good

### `session_buddy/llm/security.py`

- pct: 96.7, lines: 96, tier: good

### `session_buddy/llm_providers.py`

- pct: 86.7, lines: 339, tier: good

### `session_buddy/mcp/auth.py`

- pct: 100.0, lines: 71, tier: good

### `session_buddy/mcp/code_formatter.py`

- pct: 100.0, lines: 8, tier: good

### `session_buddy/mcp/event_models.py`

- pct: 83.5, lines: 190, tier: good

### `session_buddy/mcp/metrics.py`

- pct: 99.1, lines: 98, tier: good

### `session_buddy/mcp/quality_scorer.py`

- pct: 70.6, lines: 30, tier: partial

### `session_buddy/mcp/schemas.py`

- pct: 97.5, lines: 69, tier: good

### `session_buddy/mcp/server.py`

- pct: 75.9, lines: 44, tier: partial

### `session_buddy/mcp/server_core.py`

- pct: 93.6, lines: 248, tier: good

### `session_buddy/mcp/session_tracker.py`

- pct: 17.2, lines: 104, tier: low

### `session_buddy/mcp/telemetry.py`

- pct: 88.9, lines: 70, tier: good

### `session_buddy/mcp/tools/advanced/conscious_agent_tools.py`

- pct: 100.0, lines: 35, tier: good

### `session_buddy/mcp/tools/advanced/entity_extraction_tools.py`

- pct: 100.0, lines: 38, tier: good

### `session_buddy/mcp/tools/advanced/fingerprint_tools.py`

- pct: 77.6, lines: 196, tier: partial

### `session_buddy/mcp/tools/advanced/intent_detection_tools.py`

- pct: 87.0, lines: 78, tier: good

### `session_buddy/mcp/tools/advanced/intent_tools_registration.py`

- pct: 80.3, lines: 68, tier: good

### `session_buddy/mcp/tools/advanced/recommendation_engine.py`

- pct: 84.7, lines: 211, tier: good

### `session_buddy/mcp/tools/advanced/rewriting_tools.py`

- pct: 100.0, lines: 54, tier: good

### `session_buddy/mcp/tools/code_analysis/tools.py`

- pct: 40.8, lines: 82, tier: low

### `session_buddy/mcp/tools/code_graph.py`

- pct: 100.0, lines: 64, tier: good

### `session_buddy/mcp/tools/collaboration/knowledge_graph_phase3_tools.py`

- pct: 85.7, lines: 98, tier: good

### `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`

- pct: 85.4, lines: 318, tier: good

### `session_buddy/mcp/tools/collaboration/team_tools.py`

- pct: 95.0, lines: 129, tier: good

### `session_buddy/mcp/tools/conversation/conversation_tools.py`

- pct: 19.4, lines: 99, tier: low

### `session_buddy/mcp/tools/discovery_tools.py`

- pct: 100.0, lines: 16, tier: good

### `session_buddy/mcp/tools/ide.py`

- pct: 99.7, lines: 241, tier: good

### `session_buddy/mcp/tools/infrastructure/access_log_tools.py`

- pct: 96.1, lines: 67, tier: good

### `session_buddy/mcp/tools/infrastructure/cache_tools.py`

- pct: 32.5, lines: 95, tier: low

### `session_buddy/mcp/tools/infrastructure/feature_flags_tools.py`

- pct: 100.0, lines: 11, tier: good

### `session_buddy/mcp/tools/infrastructure/history_cache.py`

- pct: 100.0, lines: 40, tier: good

### `session_buddy/mcp/tools/infrastructure/hook_parser.py`

- pct: 96.2, lines: 61, tier: good

### `session_buddy/mcp/tools/infrastructure/pools.py`

- pct: 51.4, lines: 149, tier: partial

### `session_buddy/mcp/tools/infrastructure/protocols.py`

- pct: 100.0, lines: 33, tier: good

### `session_buddy/mcp/tools/infrastructure/serverless_tools.py`

- pct: 93.5, lines: 140, tier: good

### `session_buddy/mcp/tools/intelligence/agent_analyzer.py`

- pct: 100.0, lines: 60, tier: good

### `session_buddy/mcp/tools/intelligence/intelligence_tools.py`

- pct: 22.3, lines: 120, tier: low

### `session_buddy/mcp/tools/intelligence/llm_tools.py`

- pct: 85.4, lines: 169, tier: good

### `session_buddy/mcp/tools/memory/akosha_tools.py`

- pct: 100.0, lines: 30, tier: good

### `session_buddy/mcp/tools/memory/category_tools.py`

- pct: 11.9, lines: 127, tier: low

### `session_buddy/mcp/tools/memory/export_tools.py`

- pct: 54.2, lines: 150, tier: partial

### `session_buddy/mcp/tools/memory/memory_tools.py`

- pct: 93.2, lines: 316, tier: good

### `session_buddy/mcp/tools/memory/otel_trace_tools.py`

- pct: 68.0, lines: 67, tier: partial

### `session_buddy/mcp/tools/memory/search_tools.py`

- pct: 55.5, lines: 648, tier: partial

### `session_buddy/mcp/tools/memory/validated_memory_tools.py`

- pct: 88.7, lines: 315, tier: good

### `session_buddy/mcp/tools/monitoring/bottleneck_tools.py`

- pct: 65.3, lines: 137, tier: partial

### `session_buddy/mcp/tools/monitoring/health_tools.py`

- pct: 20.3, lines: 53, tier: low

### `session_buddy/mcp/tools/monitoring/memory_health_tools.py`

- pct: 79.0, lines: 101, tier: unknown

### `session_buddy/mcp/tools/monitoring/monitoring_tools.py`

- pct: 81.6, lines: 232, tier: good

### `session_buddy/mcp/tools/monitoring/prometheus_metrics_tools.py`

- pct: 86.0, lines: 93, tier: good

### `session_buddy/mcp/tools/monitoring/session_analytics_tools.py`

- pct: 50.4, lines: 172, tier: partial

### `session_buddy/mcp/tools/monitoring/workflow_metrics_tools.py`

- pct: 78.9, lines: 112, tier: partial

### `session_buddy/mcp/tools/profiles.py`

- pct: 100.0, lines: 9, tier: good

### `session_buddy/mcp/tools/session/admin_shell_tracking_tools.py`

- pct: 100.0, lines: 60, tier: good

### `session_buddy/mcp/tools/session/channel_tracking_tools.py`

- pct: 87.6, lines: 123, tier: good

### `session_buddy/mcp/tools/session/crackerjack_tools.py`

- pct: 82.4, lines: 696, tier: good

### `session_buddy/mcp/tools/session/hooks_tools.py`

- pct: 26.1, lines: 76, tier: low

### `session_buddy/mcp/tools/session/migration_tools.py`

- pct: 100.0, lines: 24, tier: good

### `session_buddy/mcp/tools/session/prompt_tools.py`

- pct: 100.0, lines: 34, tier: good

### `session_buddy/mcp/tools/session/session_tools.py`

- pct: 74.0, lines: 483, tier: partial

### `session_buddy/mcp/tools/skills/phase4_tools.py`

- pct: 100.0, lines: 96, tier: good

### `session_buddy/mcp/tools/worktree_tools.py`

- pct: 65.0, lines: 78, tier: partial

### `session_buddy/memory/category_evolution.py`

- pct: 86.5, lines: 489, tier: good

### `session_buddy/memory/causal.py`

- pct: 15.8, lines: 86, tier: low

### `session_buddy/memory/conscious_agent.py`

- pct: 52.7, lines: 305, tier: partial

### `session_buddy/memory/entity_extractor.py`

- pct: 64.2, lines: 131, tier: partial

### `session_buddy/memory/evolution_config.py`

- pct: 71.8, lines: 80, tier: partial

### `session_buddy/memory/file_context.py`

- pct: 92.0, lines: 19, tier: good

### `session_buddy/memory/migration.py`

- pct: 63.8, lines: 175, tier: partial

### `session_buddy/memory/peer_modeling.py`

- pct: 15.6, lines: 55, tier: low

### `session_buddy/memory/persistence.py`

- pct: 86.1, lines: 67, tier: good

### `session_buddy/memory/schema_v2.py`

- pct: 100.0, lines: 14, tier: good

### `session_buddy/memory_optimizer.py`

- pct: 93.9, lines: 297, tier: good

### `session_buddy/metrics.py`

- pct: 76.7, lines: 31, tier: partial

### `session_buddy/modes/base.py`

- pct: 100.0, lines: 50, tier: good

### `session_buddy/modes/lite.py`

- pct: 100.0, lines: 15, tier: good

### `session_buddy/modes/standard.py`

- pct: 93.3, lines: 30, tier: good

### `session_buddy/multi_project_coordinator.py`

- pct: 94.0, lines: 243, tier: good

### `session_buddy/natural_scheduler.py`

- pct: 94.0, lines: 264, tier: good

### `session_buddy/parameter_models.py`

- pct: 84.0, lines: 316, tier: good

### `session_buddy/pools.py`

- pct: 100.0, lines: 168, tier: good

### `session_buddy/quality_engine.py`

- pct: 95.4, lines: 422, tier: good

### `session_buddy/realtime/auth.py`

- pct: 90.9, lines: 25, tier: good

### `session_buddy/realtime/metrics_exporter.py`

- pct: 66.0, lines: 87, tier: partial

### `session_buddy/realtime/websocket_server.py`

- pct: 12.3, lines: 215, tier: low

### `session_buddy/reflection/database.py`

- pct: 74.5, lines: 290, tier: partial

### `session_buddy/reflection/embeddings.py`

- pct: 41.7, lines: 87, tier: low

### `session_buddy/reflection/schema.py`

- pct: 100.0, lines: 36, tier: good

### `session_buddy/reflection/search.py`

- pct: 54.7, lines: 106, tier: partial

### `session_buddy/reflection/storage.py`

- pct: 57.9, lines: 157, tier: partial

### `session_buddy/reflection_tools.py`

- pct: 91.3, lines: 19, tier: good

### `session_buddy/resource_cleanup.py`

- pct: 97.9, lines: 185, tier: good

### `session_buddy/rewriting/hooks_integration.py`

- pct: 21.6, lines: 31, tier: low

### `session_buddy/rewriting/query_rewriter.py`

- pct: 97.2, lines: 196, tier: good

### `session_buddy/search/progressive_search.py`

- pct: 100.0, lines: 196, tier: good

### `session_buddy/search_enhanced.py`

- pct: 98.0, lines: 240, tier: good

### `session_buddy/security/memory_guard_adapter.py`

- pct: 88.9, lines: 86, tier: good

### `session_buddy/server.py`

- pct: 89.5, lines: 148, tier: good

### `session_buddy/server_optimized.py`

- pct: 81.0, lines: 307, tier: good

### `session_buddy/serverless_mode.py`

- pct: 98.3, lines: 96, tier: good

### `session_buddy/services/git_maintenance.py`

- pct: 92.0, lines: 188, tier: good

### `session_buddy/session_commands.py`

- pct: 100.0, lines: 2, tier: good

### `session_buddy/session_types.py`

- pct: 100.0, lines: 14, tier: good

### `session_buddy/settings.py`

- pct: 91.0, lines: 258, tier: good

### `session_buddy/shell/adapter.py`

- pct: 98.4, lines: 58, tier: good

### `session_buddy/shutdown_manager.py`

- pct: 97.6, lines: 144, tier: good

### `session_buddy/skills/distiller.py`

- pct: 21.9, lines: 72, tier: low

### `session_buddy/storage/akosha_config.py`

- pct: 81.7, lines: 125, tier: good

### `session_buddy/storage/akosha_sync.py`

- pct: 48.1, lines: 352, tier: low

### `session_buddy/storage/cloud_sync.py`

- pct: 43.7, lines: 158, tier: low

### `session_buddy/storage/ipfs.py`

- pct: 15.5, lines: 131, tier: low

### `session_buddy/storage/skills_embeddings.py`

- pct: 49.0, lines: 111, tier: low

### `session_buddy/storage/skills_storage.py`

- pct: 17.6, lines: 454, tier: low

### `session_buddy/storage/sync_protocol.py`

- pct: 100.0, lines: 19, tier: good

### `session_buddy/subscribers/code_graph_subscriber.py`

- pct: 11.9, lines: 263, tier: low

### `session_buddy/sync.py`

- pct: 91.1, lines: 203, tier: good

### `session_buddy/team_knowledge.py`

- pct: 95.8, lines: 303, tier: good

### `session_buddy/token_optimizer.py`

- pct: 95.6, lines: 273, tier: good

### `session_buddy/tools/health_tools.py`

- pct: 100.0, lines: 31, tier: good

### `session_buddy/tools/memory_tools.py`

- pct: 56.2, lines: 16, tier: partial

### `session_buddy/tools/quality_metrics.py`

- pct: 100.0, lines: 82, tier: good

### `session_buddy/tools/search_tools.py`

- pct: 61.5, lines: 13, tier: partial

### `session_buddy/tools/session_tools.py`

- pct: 66.7, lines: 9, tier: partial

### `session_buddy/types.py`

- pct: 100.0, lines: 3, tier: good

### `session_buddy/utils/crackerjack/fallback.py`

- pct: 81.2, lines: 197, tier: good

### `session_buddy/utils/crackerjack/output_parser.py`

- pct: 62.6, lines: 255, tier: partial

### `session_buddy/utils/crackerjack/pattern_builder.py`

- pct: 100.0, lines: 34, tier: good

### `session_buddy/utils/database_pool.py`

- pct: 96.4, lines: 159, tier: good

### `session_buddy/utils/database_tools.py`

- pct: 100.0, lines: 68, tier: good

### `session_buddy/utils/encryption.py`

- pct: 98.3, lines: 87, tier: good

### `session_buddy/utils/error_management.py`

- pct: 100.0, lines: 52, tier: good

### `session_buddy/utils/file_utils.py`

- pct: 100.0, lines: 2, tier: good

### `session_buddy/utils/filesystem.py`

- pct: 100.0, lines: 132, tier: good

### `session_buddy/utils/fingerprint.py`

- pct: 100.0, lines: 71, tier: good

### `session_buddy/utils/git_operations.py`

- pct: 99.0, lines: 71, tier: good

### `session_buddy/utils/git_worktrees.py`

- pct: 87.5, lines: 346, tier: good

### `session_buddy/utils/instance_managers.py`

- pct: 95.7, lines: 123, tier: good

### `session_buddy/utils/lazy_imports.py`

- pct: 98.7, lines: 130, tier: good

### `session_buddy/utils/logging.py`

- pct: 99.3, lines: 117, tier: good

### `session_buddy/utils/logging_utils.py`

- pct: 100.0, lines: 3, tier: good

### `session_buddy/utils/messages.py`

- pct: 100.0, lines: 94, tier: good

### `session_buddy/utils/path_validation.py`

- pct: 100.0, lines: 67, tier: good

### `session_buddy/utils/project_analysis.py`

- pct: 100.0, lines: 9, tier: good

### `session_buddy/utils/quality/compaction.py`

- pct: 98.6, lines: 49, tier: good

### `session_buddy/utils/quality/recommendations.py`

- pct: 100.0, lines: 20, tier: good

### `session_buddy/utils/quality/summary.py`

- pct: 100.0, lines: 52, tier: good

### `session_buddy/utils/quality_score_parser.py`

- pct: 100.0, lines: 107, tier: good

### `session_buddy/utils/quality_scoring.py`

- pct: 96.1, lines: 453, tier: good

### `session_buddy/utils/quality_utils_v2.py`

- pct: 100.0, lines: 4, tier: good

### `session_buddy/utils/reflection_utils.py`

- pct: 100.0, lines: 65, tier: good

### `session_buddy/utils/regex_patterns.py`

- pct: 100.0, lines: 3, tier: good

### `session_buddy/utils/runtime_snapshots.py`

- pct: 97.3, lines: 102, tier: good

### `session_buddy/utils/scheduler/models.py`

- pct: 100.0, lines: 36, tier: good

### `session_buddy/utils/scheduler/time_parser.py`

- pct: 97.8, lines: 159, tier: good

### `session_buddy/utils/search/models.py`

- pct: 100.0, lines: 26, tier: good

### `session_buddy/utils/search/utilities.py`

- pct: 98.9, lines: 69, tier: good

### `session_buddy/utils/session_formatters.py`

- pct: 97.2, lines: 190, tier: good

### `session_buddy/utils/subprocess_executor.py`

- pct: 100.0, lines: 82, tier: good

### `session_buddy/utils/text_formatter.py`

- pct: 97.7, lines: 97, tier: good

### `session_buddy/utils/time.py`

- pct: 100.0, lines: 9, tier: good

### `session_buddy/utils/tool_wrapper.py`

- pct: 100.0, lines: 106, tier: good

### `session_buddy/worker.py`

- pct: 99.4, lines: 139, tier: good

### `session_buddy/worktree_manager.py`

- pct: 87.1, lines: 284, tier: good
