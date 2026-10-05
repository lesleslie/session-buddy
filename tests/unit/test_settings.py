"""Comprehensive unit tests for ``SessionBuddySettings`` (Oneiric-shaped).

Covers the 22 nested ``*Config`` groups, validators, loaders, and
helpers. Replaces the legacy flat-shape ``SessionMgmtSettings`` test
suite (deleted in Phase 6). Constructors use the nested
``Group(<field>=value)`` pattern.

Run with: ``python -m pytest tests/unit/test_settings.py -v --no-cov``
"""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import patch

import yaml

import pytest

from session_buddy.settings import (
    AkoshaSyncConfig,
    BodaiEventsConfig,
    ConversationStorageConfig,
    DatabaseConfig,
    DevelopmentConfig,
    EntityExtractionConfig,
    FeatureFlagsConfig,
    FilesystemExtractionConfig,
    GitMaintenanceConfig,
    IntegrationsConfig,
    LLMApiKeysConfig,
    LLMConfig,
    LoggingConfig,
    MCPTransportConfig,
    PathsConfig,
    PrometheusConfig,
    ReflectionAutoStoreConfig,
    SearchConfig,
    SecurityConfig,
    ServerIdentityConfig,
    SessionBuddySettings,
    SessionConfig,
    TokensConfig,
)


# ===========================================================================
# LLMConfig (consolidated; absorbs the legacy LLMProvidersConfig + flat
# minimax_*/zai_*/llama_server_*/default_llm_provider/llm_fallback_chain
# fields)
# ===========================================================================


class TestLLMConfig:
    """Test the consolidated ``LLMConfig`` group."""

    def test_default_provider_is_minimax(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.default_provider == "minimax"

    def test_ollama_base_url_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.ollama_base_url == "http://localhost:11434"

    def test_ollama_default_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.ollama_default_model == "qwen2.5-coder:7b"

    def test_llama_server_default_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.llama_server_default_model == "qwen3.5"

    def test_fallback_providers_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.fallback_providers == [
            "minimax",
            "llama_server",
            "ollama",
        ]

    def test_minimax_base_url_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.minimax_base_url == "https://api.minimax.io/v1"

    def test_minimax_default_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.minimax_default_model == "MiniMax-M2.7"

    def test_zai_base_url_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.zai_base_url == "https://api.z.ai/api/coding/paas/v4"

    def test_zai_default_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.zai_default_model == "glm-4.7"

    def test_llama_server_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.llama_server_model == "qwen3.5"

    def test_valid_provider_literals(self) -> None:
        valid_providers = ["minimax", "zai", "openai", "gemini", "ollama", "llama_server"]
        for provider in valid_providers:
            settings = SessionBuddySettings(
                llm=LLMConfig(default_provider=provider),
            )
            assert settings.llm.default_provider == provider

    def test_custom_provider(self) -> None:
        settings = SessionBuddySettings(
            llm=LLMConfig(default_provider="ollama"),
        )
        assert settings.llm.default_provider == "ollama"

    def test_custom_fallback_chain(self) -> None:
        custom_chain = ["ollama", "minimax"]
        settings = SessionBuddySettings(
            llm=LLMConfig(fallback_providers=custom_chain),
        )
        assert settings.llm.fallback_providers == custom_chain

    def test_custom_urls(self) -> None:
        settings = SessionBuddySettings(
            llm=LLMConfig(ollama_base_url="http://custom:11434"),
        )
        assert settings.llm.ollama_base_url == "http://custom:11434"


# ===========================================================================
# ServerIdentityConfig (MCP server identity + log level)
# ===========================================================================


class TestServerIdentityConfig:
    """Test the ``mcp_server`` group (formerly the flat ``server_name``/etc.)."""

    def test_server_name_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_server.server_name == "Session Buddy MCP"

    def test_server_description_default(self) -> None:
        settings = SessionBuddySettings()
        assert (
            settings.mcp_server.server_description
            == "Session management and tooling MCP server"
        )

    def test_log_level_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_server.log_level == "INFO"

    def test_enable_debug_mode_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_server.enable_debug_mode is False

    def test_valid_log_levels(self) -> None:
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = SessionBuddySettings(
                mcp_server=ServerIdentityConfig(log_level=level),
            )
            assert settings.mcp_server.log_level == level

    def test_custom_server_name(self) -> None:
        settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(server_name="Custom Server"),
        )
        assert settings.mcp_server.server_name == "Custom Server"

    def test_custom_log_level(self) -> None:
        settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(log_level="DEBUG"),
        )
        assert settings.mcp_server.log_level == "DEBUG"


# ===========================================================================
# PathsConfig (path settings + ~ expansion)
# ===========================================================================


class TestPathsConfig:
    """Test ``paths`` group (formerly flat ``data_dir``/``log_dir``/etc.)."""

    def test_default_data_dir(self) -> None:
        settings = SessionBuddySettings()
        assert settings.paths.data_dir == Path("~/.claude/data")

    def test_default_log_dir(self) -> None:
        settings = SessionBuddySettings()
        assert settings.paths.log_dir == Path("~/.claude/logs")

    def test_default_global_workspace_path(self) -> None:
        settings = SessionBuddySettings()
        assert settings.paths.global_workspace_path == Path("~/Projects/claude")

    def test_default_log_file_path(self) -> None:
        settings = SessionBuddySettings()
        assert settings.paths.log_file_path == Path(
            "~/.claude/logs/session-buddy.log"
        )

    def test_user_path_expansion_data_dir(self) -> None:
        settings = SessionBuddySettings(
            paths=PathsConfig(data_dir=Path("~/my/data")),
        )
        expanded = settings.paths.data_dir
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_user_path_expansion_log_dir(self) -> None:
        settings = SessionBuddySettings(
            paths=PathsConfig(log_dir=Path("~/my/logs")),
        )
        expanded = settings.paths.log_dir
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_user_path_expansion_global_workspace_path(self) -> None:
        settings = SessionBuddySettings(
            paths=PathsConfig(global_workspace_path=Path("~/my/workspace")),
        )
        expanded = settings.paths.global_workspace_path
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_user_path_expansion_log_file_path(self) -> None:
        settings = SessionBuddySettings(
            paths=PathsConfig(log_file_path=Path("~/my/logs/app.log")),
        )
        expanded = settings.paths.log_file_path
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_string_path_inputs_are_expanded(self) -> None:
        settings = SessionBuddySettings(
            paths=PathsConfig(
                data_dir="~/my/data",
                log_dir="~/my/logs",
                log_file_path="~/my/logs/app.log",
                global_workspace_path="~/my/workspace",
            ),
        )
        assert settings.paths.data_dir.is_absolute()
        assert settings.paths.log_dir.is_absolute()
        assert settings.paths.log_file_path.is_absolute()
        assert settings.paths.global_workspace_path.is_absolute()


# ===========================================================================
# DatabaseConfig
# ===========================================================================


class TestDatabaseConfig:
    """Test ``database`` group (formerly flat ``database_*``)."""

    def test_default_path(self) -> None:
        settings = SessionBuddySettings()
        assert settings.database.path == Path("~/.claude/data/reflection.duckdb")

    def test_default_connection_timeout(self) -> None:
        settings = SessionBuddySettings()
        assert settings.database.connection_timeout == 30

    def test_default_query_timeout(self) -> None:
        settings = SessionBuddySettings()
        assert settings.database.query_timeout == 120

    def test_default_max_connections(self) -> None:
        settings = SessionBuddySettings()
        assert settings.database.max_connections == 10

    def test_connection_timeout_range_min(self) -> None:
        settings = SessionBuddySettings(
            database=DatabaseConfig(connection_timeout=1),
        )
        assert settings.database.connection_timeout == 1

    def test_connection_timeout_range_max(self) -> None:
        settings = SessionBuddySettings(
            database=DatabaseConfig(connection_timeout=300),
        )
        assert settings.database.connection_timeout == 300

    def test_query_timeout_range_min(self) -> None:
        settings = SessionBuddySettings(
            database=DatabaseConfig(query_timeout=1),
        )
        assert settings.database.query_timeout == 1

    def test_query_timeout_range_max(self) -> None:
        settings = SessionBuddySettings(
            database=DatabaseConfig(query_timeout=3600),
        )
        assert settings.database.query_timeout == 3600


# ===========================================================================
# MultiProjectConfig
# ===========================================================================


class TestMultiProjectConfig:
    """Test ``multi_project`` group."""

    def test_enable_multi_project_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.multi_project.enable_multi_project is True

    def test_auto_detect_projects_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.multi_project.auto_detect_projects is True

    def test_project_groups_enabled_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.multi_project.project_groups_enabled is True


# ===========================================================================
# SearchConfig
# ===========================================================================


class TestSearchConfig:
    """Test ``search`` group."""

    def test_enable_full_text_search_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_full_text_search is True

    def test_enable_semantic_search_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_semantic_search is True

    def test_enable_faceted_search_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_faceted_search is True

    def test_enable_search_suggestions_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_search_suggestions is True

    def test_enable_stemming_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_stemming is True

    def test_enable_fuzzy_matching_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_fuzzy_matching is True

    def test_max_search_results_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.max_search_results == 100

    def test_max_search_results_range_min(self) -> None:
        settings = SessionBuddySettings(
            search=SearchConfig(max_search_results=1),
        )
        assert settings.search.max_search_results == 1

    def test_max_search_results_range_max(self) -> None:
        settings = SessionBuddySettings(
            search=SearchConfig(max_search_results=10000),
        )
        assert settings.search.max_search_results == 10000

    def test_embedding_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.embedding_model == "all-MiniLM-L6-v2"

    def test_embedding_cache_size_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.embedding_cache_size == 1000

    def test_search_index_update_interval_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.search_index_update_interval == 3600

    def test_fuzzy_threshold_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.fuzzy_threshold == 0.8

    def test_fuzzy_threshold_range_min(self) -> None:
        settings = SessionBuddySettings(
            search=SearchConfig(fuzzy_threshold=0.1),
        )
        assert settings.search.fuzzy_threshold == 0.1

    def test_fuzzy_threshold_range_max(self) -> None:
        settings = SessionBuddySettings(
            search=SearchConfig(fuzzy_threshold=1.0),
        )
        assert settings.search.fuzzy_threshold == 1.0

    def test_max_facet_values_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.max_facet_values == 50

    def test_suggestion_limit_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.suggestion_limit == 10


# ===========================================================================
# TokensConfig
# ===========================================================================


class TestTokensConfig:
    """Test ``tokens`` group."""

    def test_enable_token_optimization_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.enable_token_optimization is True

    def test_default_max_tokens_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.default_max_tokens == 4000

    def test_default_chunk_size_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.default_chunk_size == 2000

    def test_optimization_strategy_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.optimization_strategy == "auto"

    def test_enable_response_chunking_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.enable_response_chunking is True

    def test_enable_duplicate_filtering_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.enable_duplicate_filtering is True

    def test_track_token_usage_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.track_token_usage is True

    def test_usage_retention_days_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.usage_retention_days == 90


# ===========================================================================
# SessionConfig
# ===========================================================================


class TestSessionConfig:
    """Test ``session`` group (auto-checkpoint, commit template, etc.)."""

    def test_auto_checkpoint_interval_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.session.auto_checkpoint_interval == 1800

    def test_enable_auto_commit_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.session.enable_auto_commit is True

    def test_commit_message_template_default(self) -> None:
        settings = SessionBuddySettings()
        assert (
            settings.session.commit_message_template
            == "checkpoint: Session checkpoint - {timestamp}"
        )

    def test_commit_message_template_must_contain_timestamp(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            SessionConfig(commit_message_template="invalid template without timestamp")

    def test_commit_message_template_validator_accepts_valid_value(self) -> None:
        template = "checkpoint: Session checkpoint - {timestamp}"
        # The validator is now a private @field_validator on SessionConfig.
        assert SessionConfig._validate_commit_template(template) == template

    def test_commit_message_template_validator_rejects_invalid_value(self) -> None:
        with pytest.raises(ValueError, match="must contain {timestamp}"):
            SessionConfig._validate_commit_template("checkpoint without placeholder")

    def test_enable_permission_system_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.session.enable_permission_system is True

    def test_default_trusted_operations_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.session.default_trusted_operations == [
            "git_commit",
            "uv_sync",
            "file_operations",
        ]

    def test_auto_cleanup_old_sessions_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.session.auto_cleanup_old_sessions is True

    def test_session_retention_days_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.session.session_retention_days == 365


# ===========================================================================
# ReflectionAutoStoreConfig
# ===========================================================================


class TestReflectionAutoStoreConfig:
    """Test ``reflection_auto_store`` group."""

    def test_enable_auto_store_reflections_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.reflection_auto_store.enable_auto_store_reflections is True

    def test_auto_store_quality_delta_threshold_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.reflection_auto_store.auto_store_quality_delta_threshold == 10

    def test_auto_store_exceptional_quality_threshold_default(self) -> None:
        settings = SessionBuddySettings()
        assert (
            settings.reflection_auto_store.auto_store_exceptional_quality_threshold
            == 70
        )

    def test_auto_store_manual_checkpoints_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert (
            settings.reflection_auto_store.auto_store_manual_checkpoints is True
        )

    def test_auto_store_session_end_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.reflection_auto_store.auto_store_session_end is True


# ===========================================================================
# ConversationStorageConfig
# ===========================================================================


class TestConversationStorageConfig:
    """Test ``conversation_storage`` group."""

    def test_enable_conversation_storage_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.conversation_storage.enable_conversation_storage is True

    def test_conversation_storage_min_length_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.conversation_storage.conversation_storage_min_length == 100

    def test_conversation_storage_max_length_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.conversation_storage.conversation_storage_max_length == 50000

    def test_auto_store_conversations_on_checkpoint_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert (
            settings.conversation_storage.auto_store_conversations_on_checkpoint
            is True
        )

    def test_auto_store_conversations_on_session_end_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert (
            settings.conversation_storage.auto_store_conversations_on_session_end
            is True
        )


# ===========================================================================
# IntegrationsConfig
# ===========================================================================


class TestIntegrationsConfig:
    """Test ``integrations`` group."""

    def test_enable_crackerjack_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.integrations.enable_crackerjack is True

    def test_crackerjack_command_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.integrations.crackerjack_command == "crackerjack"

    def test_enable_git_integration_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.integrations.enable_git_integration is True

    def test_git_auto_stage_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.integrations.git_auto_stage is False


# ===========================================================================
# GitMaintenanceConfig
# ===========================================================================


class TestGitMaintenanceConfig:
    """Test ``git_maintenance`` group (git gc scheduling)."""

    def test_git_auto_gc_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.git_maintenance.git_auto_gc is True

    def test_git_gc_prune_delay_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.git_maintenance.git_gc_prune_delay == "2.weeks"

    def test_git_gc_auto_threshold_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.git_maintenance.git_gc_auto_threshold == 6700

    def test_git_gc_only_when_clean_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.git_maintenance.git_gc_only_when_clean is True

    def test_git_gc_prune_delay_valid_formats(self) -> None:
        valid_delays = [
            "2.weeks",
            "1.month",
            "30.days",
            "12.hours",
            "now",
            "never",
            "1.day",
            "1.minute",
            "1.second",
            "1.year",
        ]
        for delay in valid_delays:
            settings = SessionBuddySettings(
                git_maintenance=GitMaintenanceConfig(git_gc_prune_delay=delay),
            )
            assert settings.git_maintenance.git_gc_prune_delay == delay

    def test_git_gc_prune_delay_validator_accepts_valid_values(self) -> None:
        assert (
            GitMaintenanceConfig._validate_prune_delay("2.weeks") == "2.weeks"
        )

    def test_git_gc_prune_delay_invalid_formats_rejected(self) -> None:
        import pydantic

        invalid_delays = [
            "now; rm -rf /",
            "2.weeks; malicious",
            "$(whoami)",
            "",
            "invalid",
            "2",
            "weeks",
        ]
        for delay in invalid_delays:
            with pytest.raises(pydantic.ValidationError):
                GitMaintenanceConfig(git_gc_prune_delay=delay)

    def test_git_gc_prune_delay_now_triggers_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            GitMaintenanceConfig(git_gc_prune_delay="now")
            assert len(w) == 1
            assert "data loss" in str(w[0].message).lower()

    def test_git_gc_prune_delay_validator_rejects_invalid_values(self) -> None:
        with pytest.raises(ValueError, match="Invalid git_gc_prune_delay"):
            GitMaintenanceConfig._validate_prune_delay("bad-value")

    def test_git_gc_prune_delay_validator_warns_on_now(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert GitMaintenanceConfig._validate_prune_delay("now") == "now"
            assert len(w) == 1


# ===========================================================================
# PrometheusConfig
# ===========================================================================


class TestPrometheusConfig:
    """Test ``prometheus`` group."""

    def test_enable_prometheus_metrics_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.prometheus.enable_prometheus_metrics is True

    def test_prometheus_metrics_port_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.prometheus.prometheus_metrics_port == 9090

    def test_prometheus_metrics_path_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.prometheus.prometheus_metrics_path == "/metrics"


# ===========================================================================
# LLMApiKeysConfig
# ===========================================================================


class TestLLMApiKeysConfig:
    """Test the per-provider API keys nested under ``llm.api_keys``."""

    def test_openai_api_key_default_none(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.api_keys.openai is None

    def test_anthropic_api_key_default_none(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.api_keys.anthropic is None

    def test_gemini_api_key_default_none(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.api_keys.gemini is None

    def test_qwen_api_key_default_none(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.api_keys.qwen is None

    def test_minimax_api_key_default_none(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.api_keys.minimax is None

    def test_zai_api_key_default_none(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.api_keys.zai is None

    def test_api_keys_override(self) -> None:
        settings = SessionBuddySettings(
            llm=LLMConfig(api_keys=LLMApiKeysConfig(minimax="sk-test")),
        )
        assert settings.llm.api_keys.minimax == "sk-test"


# ===========================================================================
# LoggingConfig
# ===========================================================================


class TestLoggingConfig:
    """Test ``logging`` group."""

    def test_log_format_default(self) -> None:
        settings = SessionBuddySettings()
        assert (
            settings.logging.log_format
            == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    def test_enable_file_logging_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.logging.enable_file_logging is True

    def test_log_file_max_size_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.logging.log_file_max_size == 10 * 1024 * 1024

    def test_log_file_backup_count_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.logging.log_file_backup_count == 5

    def test_enable_performance_logging_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.logging.enable_performance_logging is False

    def test_log_slow_queries_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.logging.log_slow_queries is True

    def test_slow_query_threshold_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.logging.slow_query_threshold == 1.0


# ===========================================================================
# SecurityConfig
# ===========================================================================


class TestSecurityConfig:
    """Test ``security`` group."""

    def test_anonymize_paths_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.security.anonymize_paths is False

    def test_enable_rate_limiting_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.security.enable_rate_limiting is True

    def test_max_requests_per_minute_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.security.max_requests_per_minute == 100

    def test_max_query_length_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.security.max_query_length == 10000

    def test_max_content_length_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.security.max_content_length == 1000000


# ===========================================================================
# MCPTransportConfig
# ===========================================================================


class TestMCPTransportConfig:
    """Test ``mcp_transport`` group (HTTP/WS transport)."""

    def test_server_host_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_transport.server_host == "localhost"

    def test_server_port_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_transport.server_port == 8678

    def test_enable_websockets_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_transport.enable_websockets is True


# ===========================================================================
# DevelopmentConfig
# ===========================================================================


class TestDevelopmentConfig:
    """Test ``development`` group."""

    def test_enable_hot_reload_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.development.enable_hot_reload is False


# ===========================================================================
# FeatureFlagsConfig
# ===========================================================================


class TestFeatureFlagsConfig:
    """Test ``feature_flags`` group + retired-field assertions."""

    def test_use_schema_v2_field_removed(self) -> None:
        """V1 retired 2026-10-04 — schema v2 is unconditional.

        The ``use_schema_v2`` field is gone from the settings class.
        """
        assert "use_schema_v2" not in SessionBuddySettings.model_fields

    def test_enable_llm_entity_extraction_default_true(self) -> None:
        # ``enable_llm_entity_extraction`` is now ``entity_extraction.enable``.
        settings = SessionBuddySettings()
        assert settings.entity_extraction.enable is True

    def test_enable_anthropic_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.feature_flags.enable_anthropic is False

    def test_enable_ollama_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.feature_flags.enable_ollama is False

    def test_enable_conscious_agent_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.feature_flags.enable_conscious_agent is False

    def test_enable_filesystem_extraction_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.feature_flags.enable_filesystem_extraction is False

    def test_enable_crackerjack_fallback_default_false(self) -> None:
        settings = SessionBuddySettings()
        assert settings.feature_flags.enable_crackerjack_fallback is False

    def test_feature_flag_override(self) -> None:
        settings = SessionBuddySettings(
            feature_flags=FeatureFlagsConfig(
                enable_conscious_agent=True,
                enable_filesystem_extraction=True,
            ),
        )
        assert settings.feature_flags.enable_conscious_agent is True
        assert settings.feature_flags.enable_filesystem_extraction is True


# ===========================================================================
# EntityExtractionConfig
# ===========================================================================


class TestEntityExtractionConfig:
    """Test ``entity_extraction`` group (LLM extraction knobs)."""

    def test_llm_extraction_timeout_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.entity_extraction.timeout == 10

    def test_llm_extraction_retries_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.entity_extraction.retries == 1

    def test_custom_extraction(self) -> None:
        settings = SessionBuddySettings(
            entity_extraction=EntityExtractionConfig(timeout=30, retries=2),
        )
        assert settings.entity_extraction.timeout == 30
        assert settings.entity_extraction.retries == 2


# ===========================================================================
# FilesystemExtractionConfig
# ===========================================================================


class TestFilesystemExtractionConfig:
    """Test ``filesystem_extraction`` group."""

    def test_filesystem_dedupe_ttl_seconds_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.filesystem_extraction.dedupe_ttl_seconds == 120

    def test_filesystem_max_file_size_bytes_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.filesystem_extraction.max_file_size_bytes == 1_000_000

    def test_filesystem_ignore_dirs_default(self) -> None:
        settings = SessionBuddySettings()
        expected = [
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "dist",
            "build",
            ".DS_Store",
            ".idea",
            ".vscode",
        ]
        assert settings.filesystem_extraction.ignore_dirs == expected


# ===========================================================================
# AkoshaSyncConfig
# ===========================================================================


class TestAkoshaSyncConfig:
    """Test ``cloud_sync`` group (formerly flat ``akosha_*``)."""

    def test_akosha_cloud_bucket_default_empty(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.cloud_bucket == ""

    def test_akosha_cloud_endpoint_default_empty(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.cloud_endpoint == ""

    def test_akosha_cloud_region_default_auto(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.cloud_region == "auto"

    def test_akosha_system_id_default_empty(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.system_id == ""

    def test_akosha_upload_on_session_end_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.upload_on_session_end is True

    def test_akosha_enable_fallback_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.enable_fallback is True

    def test_akosha_force_method_default_auto(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.force_method == "auto"

    def test_akosha_upload_timeout_seconds_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.upload_timeout_seconds == 300

    def test_akosha_max_retries_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.max_retries == 3

    def test_akosha_retry_backoff_seconds_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.retry_backoff_seconds == 2.0

    def test_akosha_enable_compression_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.enable_compression is True

    def test_akosha_enable_deduplication_default_true(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.enable_deduplication is True

    def test_akosha_chunk_size_mb_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.cloud_sync.chunk_size_mb == 5

    def test_akosha_force_method_valid_literals(self) -> None:
        # New Literal: ["auto", "sync", "async"] (renamed from the legacy
        # ["auto", "cloud", "http"] in 2026-09-27 audit).
        for method in ["auto", "sync", "async"]:
            settings = SessionBuddySettings(
                cloud_sync=AkoshaSyncConfig(force_method=method),
            )
            assert settings.cloud_sync.force_method == method

    def test_custom_akosha_settings(self) -> None:
        settings = SessionBuddySettings(
            cloud_sync=AkoshaSyncConfig(
                cloud_bucket="my-bucket",
                cloud_endpoint="https://akosha.example.com",
                system_id="my-system",
            ),
        )
        assert settings.cloud_sync.cloud_bucket == "my-bucket"
        assert settings.cloud_sync.cloud_endpoint == "https://akosha.example.com"
        assert settings.cloud_sync.system_id == "my-system"


# ===========================================================================
# Legacy debug-flag mapping (now ``debug`` -> ``mcp_server.enable_debug_mode``)
# ===========================================================================


class TestLegacyDebugFlag:
    """Test the ``_map_legacy_debug_flag`` validator on ``SessionBuddySettings``."""

    def test_legacy_debug_flag_maps_to_mcp_server_enable_debug_mode(self) -> None:
        settings = SessionBuddySettings.model_validate({"debug": True})
        assert settings.mcp_server.enable_debug_mode is True

    def test_legacy_debug_false_maps_to_mcp_server_enable_debug_mode_false(
        self,
    ) -> None:
        settings = SessionBuddySettings.model_validate({"debug": False})
        assert settings.mcp_server.enable_debug_mode is False

    def test_explicit_mcp_server_enable_debug_mode_wins(self) -> None:
        """An explicit nested ``mcp_server.enable_debug_mode`` overrides
        the legacy ``debug`` shorthand."""
        settings = SessionBuddySettings.model_validate(
            {"debug": True, "mcp_server": {"enable_debug_mode": False}}
        )
        assert settings.mcp_server.enable_debug_mode is False

    def test_non_dict_passthrough(self) -> None:
        marker = object()
        assert SessionBuddySettings._map_legacy_debug_flag(marker) is marker

    def test_debug_flag_maps_to_mcp_server_enable_debug_mode(self) -> None:
        result = SessionBuddySettings._map_legacy_debug_flag({"debug": 1})
        assert result["mcp_server"]["enable_debug_mode"] is True
        assert result["debug"] == 1


# ===========================================================================
# get_settings() / reload_settings() / get_database_path() / get_log_file_path()
# / get_llm_api_key() — already rewritten in Phase 5 partial commit
# ===========================================================================


class TestGetSettings:
    """Test ``get_settings()`` global function."""

    def test_get_settings_returns_session_buddy_settings(self) -> None:
        from session_buddy import settings as settings_module

        settings_module._settings = None

        mock_instance = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(server_name="Loaded")
        )
        with patch.object(settings_module, "_settings", None):
            with patch.object(
                settings_module.SessionBuddySettings,
                "load",
                return_value=mock_instance,
            ):
                result = settings_module.get_settings()
                assert result is mock_instance

    def test_get_settings_caches_result(self) -> None:
        from session_buddy import settings as settings_module

        mock_settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(server_name="Cached")
        )
        with patch.object(settings_module, "_settings", mock_settings):
            with patch.object(
                settings_module.SessionBuddySettings, "load"
            ) as mock_load:
                result = settings_module.get_settings()
                assert result is mock_settings
                mock_load.assert_not_called()

    def test_get_settings_reload_parameter(self) -> None:
        from session_buddy import settings as settings_module

        mock_settings = SessionBuddySettings()
        new_settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(server_name="Reloaded")
        )

        with patch.object(settings_module, "_settings", mock_settings):
            with patch.object(
                settings_module.SessionBuddySettings,
                "load",
                return_value=new_settings,
            ) as mock_load:
                result = settings_module.get_settings(reload=True)
                assert result.mcp_server.server_name == "Reloaded"
                mock_load.assert_called_once()


class TestReloadSettings:
    """Test ``reload_settings()`` function."""

    def test_reload_settings_calls_get_settings_with_reload_true(self) -> None:
        from session_buddy import settings as settings_module

        new_settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(server_name="Reloaded")
        )

        with patch.object(settings_module, "_settings", None):
            with patch.object(
                settings_module.SessionBuddySettings,
                "load",
                return_value=new_settings,
            ) as mock_load:
                result = settings_module.reload_settings()
                mock_load.assert_called_once()


class TestGetDatabasePath:
    """Test ``get_database_path()`` function."""

    def _make(self, *, db_path: Path, data_dir: Path) -> SessionBuddySettings:
        return SessionBuddySettings(
            database=DatabaseConfig(path=db_path),
            paths=PathsConfig(data_dir=data_dir),
        )

    def test_get_database_path_with_absolute_path(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            db_path=Path("/absolute/path/db.duckdb"),
            data_dir=Path("~/.claude/data"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_database_path()
            assert result == Path("/absolute/path/db.duckdb")

    def test_get_database_path_with_relative_path_and_data_dir(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            db_path=Path("relative/db.duckdb"),
            data_dir=Path("/tmp/data"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_database_path()
            assert result == Path("/tmp/data/relative/db.duckdb")

    def test_get_database_path_expands_user_tilde(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            db_path=Path("~/my/db.duckdb"),
            data_dir=Path("~/.claude/data"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_database_path()
            assert "~" not in str(result)

    def test_get_database_path_with_string_values(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            db_path=Path("relative/db.duckdb"),
            data_dir=Path("/tmp/data"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_database_path()
        assert result == Path("/tmp/data/relative/db.duckdb")


class TestGetLogFilePath:
    """Test ``get_log_file_path()`` function."""

    def _make(self, *, log_file_path: Path, log_dir: Path) -> SessionBuddySettings:
        return SessionBuddySettings(
            paths=PathsConfig(log_file_path=log_file_path, log_dir=log_dir),
        )

    def test_get_log_file_path_with_absolute_path(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            log_file_path=Path("/absolute/log/app.log"),
            log_dir=Path("~/.claude/logs"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_log_file_path()
            assert result == Path("/absolute/log/app.log")

    def test_get_log_file_path_with_relative_path_and_log_dir(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            log_file_path=Path("relative/log.log"),
            log_dir=Path("/tmp/logs"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_log_file_path()
            assert result == Path("/tmp/logs/relative/log.log")

    def test_get_log_file_path_expands_user_tilde(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            log_file_path=Path("~/my/logs/app.log"),
            log_dir=Path("~/.claude/logs"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_log_file_path()
            assert "~" not in str(result)

    def test_get_log_file_path_with_string_values(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(
            log_file_path=Path("relative/app.log"),
            log_dir=Path("/tmp/logs"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_log_file_path()
        assert result == Path("/tmp/logs/relative/app.log")


class TestGetLLMAPIKey:
    """Test ``get_llm_api_key()`` function."""

    def _make(self, **api_keys: str | None) -> SessionBuddySettings:
        return SessionBuddySettings(
            llm=LLMConfig(api_keys=LLMApiKeysConfig(**api_keys)),
        )

    def test_get_llm_api_key_openai(self) -> None:
        from session_buddy import settings as settings_module

        test_key = "sk-test-placeholder-key-for-unit-testing-only"
        settings = self._make(openai=test_key)
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("openai")
            assert result == test_key

    def test_get_llm_api_key_anthropic(self) -> None:
        from session_buddy import settings as settings_module

        test_key = "sk-ant-test-placeholder-key-for-unit-testing-only-1234567890"
        settings = self._make(anthropic=test_key)
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("anthropic")
            assert result == test_key

    def test_get_llm_api_key_minimax(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(minimax="minimax-key")
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("minimax")
            assert result == "minimax-key"

    def test_get_llm_api_key_zai(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(zai="zai-key")
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("zai")
            assert result == "zai-key"

    def test_get_llm_api_key_unknown_provider(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make()
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("unknown_provider")
            assert result is None

    def test_get_llm_api_key_empty_key_returns_none(self) -> None:
        from session_buddy import settings as settings_module

        settings = self._make(openai="   ")
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("openai")
            assert result is None


# ===========================================================================
# SessionBuddySettings.load() — round-trip the Oneiric layered loader
# ===========================================================================


class TestSessionBuddySettingsLoad:
    """Test ``SessionBuddySettings.load()`` with explicit config_path."""

    def test_load_with_empty_path_uses_defaults(self) -> None:
        """``load()`` with no path falls back to the Oneiric search;
        even with no config files it must yield a usable instance."""
        # We can't fully exercise the Oneiric path without a real
        # project_root, but ``load()`` returns a ``SessionBuddySettings``
        # either way.
        result = SessionBuddySettings.load()
        assert isinstance(result, SessionBuddySettings)

    def test_load_from_explicit_yaml(self, tmp_path: Path) -> None:
        """A nested-shape YAML at an explicit path is honored by
        ``load(config_path=...)``."""
        config_file = tmp_path / "test-config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "mcp_server": {"server_name": "Test Server"},
                    "mcp_transport": {"server_port": 9999},
                }
            )
        )

        result = SessionBuddySettings.load(config_path=config_file)
        assert result.mcp_server.server_name == "Test Server"
        assert result.mcp_transport.server_port == 9999


# ===========================================================================
# __all__ exports
# ===========================================================================


class TestExports:
    """Test module exports."""

    def test_session_buddy_settings_in_all(self) -> None:
        from session_buddy import settings as settings_module

        assert "SessionBuddySettings" in settings_module.__all__

    def test_legacy_session_mgmt_settings_removed(self) -> None:
        """``SessionMgmtSettings`` was deleted in Phase 6; it must not
        appear in ``__all__`` or as a module attribute."""
        from session_buddy import settings as settings_module

        assert "SessionMgmtSettings" not in settings_module.__all__
        assert not hasattr(settings_module, "SessionMgmtSettings")

    def test_all_nested_configs_exported(self) -> None:
        from session_buddy import settings as settings_module

        expected_groups = [
            "ServerIdentityConfig",
            "MCPTransportConfig",
            "PathsConfig",
            "DatabaseConfig",
            "MultiProjectConfig",
            "SearchConfig",
            "TokensConfig",
            "SessionConfig",
            "ConversationStorageConfig",
            "ReflectionAutoStoreConfig",
            "IntegrationsConfig",
            "GitMaintenanceConfig",
            "PrometheusConfig",
            "DevelopmentConfig",
            "LoggingConfig",
            "SecurityConfig",
            "LLMConfig",
            "LLMApiKeysConfig",
            "EntityExtractionConfig",
            "FeatureFlagsConfig",
            "FilesystemExtractionConfig",
            "AkoshaSyncConfig",
            "BodaiEventsConfig",
        ]
        for cls_name in expected_groups:
            assert cls_name in settings_module.__all__
            assert hasattr(settings_module, cls_name)

    def test_helper_functions_exported(self) -> None:
        from session_buddy import settings as settings_module

        for name in [
            "get_database_path",
            "get_llm_api_key",
            "get_log_file_path",
            "get_settings",
            "reload_settings",
        ]:
            assert name in settings_module.__all__
            assert hasattr(settings_module, name)
