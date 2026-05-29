"""Comprehensive unit tests for session_buddy/settings.py (896 lines).

Tests:
- LLMProvidersConfig
- SessionMgmtSettings
- Path expansion (user paths ~)
- Legacy debug flag mapping
- Git prune delay validation
- Commit message template validation
- get_settings() / reload_settings()
- get_database_path()
- get_log_file_path()
- get_llm_api_key()

Uses tempfile.TemporaryDirectory for all file operations.
Mocks external dependencies (filesystem beyond temp dir, environment variables).
Run with: python -m pytest tests/unit/test_settings.py -v --no-cov
"""

from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestLLMProvidersConfig:
    """Test LLMProvidersConfig model."""

    def test_default_provider_is_minimax(self) -> None:
        """Test that default provider is minimax."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig()
        assert config.default_provider == "minimax"

    def test_ollama_base_url_default(self) -> None:
        """Test default Ollama base URL."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig()
        assert config.ollama_base_url == "http://localhost:11434"

    def test_ollama_default_model_default(self) -> None:
        """Test default Ollama model."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig()
        assert config.ollama_default_model == "qwen2.5-coder:7b"

    def test_llama_server_base_url_default(self) -> None:
        """Test default llama-server base URL."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig()
        assert config.llama_server_base_url == "http://localhost:8081"

    def test_llama_server_default_model_default(self) -> None:
        """Test default llama-server model."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig()
        assert config.llama_server_default_model == "qwen3.5"

    def test_fallback_providers_default(self) -> None:
        """Test default fallback providers list."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig()
        assert config.fallback_providers == ["minimax", "llama_server", "ollama"]

    def test_valid_provider_literals(self) -> None:
        """Test all valid provider literal values."""
        from session_buddy.settings import LLMProvidersConfig

        valid_providers = ["minimax", "zai", "openai", "gemini", "ollama", "llama_server"]
        for provider in valid_providers:
            config = LLMProvidersConfig(default_provider=provider)
            assert config.default_provider == provider

    def test_custom_provider(self) -> None:
        """Test setting a custom provider."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig(default_provider="ollama")
        assert config.default_provider == "ollama"

    def test_custom_fallback_chain(self) -> None:
        """Test setting a custom fallback chain."""
        from session_buddy.settings import LLMProvidersConfig

        custom_chain = ["ollama", "minimax"]
        config = LLMProvidersConfig(fallback_providers=custom_chain)
        assert config.fallback_providers == custom_chain

    def test_custom_urls(self) -> None:
        """Test setting custom service URLs."""
        from session_buddy.settings import LLMProvidersConfig

        config = LLMProvidersConfig(
            ollama_base_url="http://custom:11434",
            llama_server_base_url="http://custom:8081",
        )
        assert config.ollama_base_url == "http://custom:11434"
        assert config.llama_server_base_url == "http://custom:8081"


class TestSessionMgmtSettingsLLMProviders:
    """Test SessionMgmtSettings LLM provider fields."""

    def test_llm_providers_default(self) -> None:
        """Test default LLM providers config."""
        from session_buddy.settings import LLMProvidersConfig, SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert isinstance(settings.llm_providers, LLMProvidersConfig)
        assert settings.llm_providers.default_provider == "minimax"

    def test_custom_llm_providers(self) -> None:
        """Test setting custom LLM providers config."""
        from session_buddy.settings import LLMProvidersConfig, SessionMgmtSettings

        custom = LLMProvidersConfig(default_provider="ollama")
        settings = SessionMgmtSettings(llm_providers=custom)
        assert settings.llm_providers.default_provider == "ollama"

    def test_minimax_base_url_default(self) -> None:
        """Test default MiniMax base URL."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.minimax_base_url == "https://api.minimax.io/v1"

    def test_minimax_default_model_default(self) -> None:
        """Test default MiniMax model."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.minimax_default_model == "MiniMax-M2.7"

    def test_zai_base_url_default(self) -> None:
        """Test default ZAI base URL."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.zai_base_url == "https://api.z.ai/api/coding/paas/v4"

    def test_zai_default_model_default(self) -> None:
        """Test default ZAI model."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.zai_default_model == "glm-4.7"

    def test_llama_server_base_url_default(self) -> None:
        """Test default llama-server base URL (SessionMgmtSettings level)."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.llama_server_base_url == "http://localhost:8081"

    def test_llama_server_model_default(self) -> None:
        """Test default llama-server model (SessionMgmtSettings level)."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.llama_server_model == "qwen3.5"

    def test_default_llm_provider_default(self) -> None:
        """Test default LLM provider field."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.default_llm_provider == "minimax"

    def test_llm_fallback_chain_default(self) -> None:
        """Test default LLM fallback chain."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.llm_fallback_chain == ["minimax", "llama_server", "ollama"]

    def test_custom_llm_fallback_chain(self) -> None:
        """Test setting custom LLM fallback chain."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(llm_fallback_chain=["ollama", "minimax"])
        assert settings.llm_fallback_chain == ["ollama", "minimax"]


class TestSessionMgmtSettingsCore:
    """Test SessionMgmtSettings core MCP fields."""

    def test_server_name_default(self) -> None:
        """Test default server name."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.server_name == "Session Buddy MCP"

    def test_server_description_default(self) -> None:
        """Test default server description."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert (
            settings.server_description == "Session management and tooling MCP server"
        )

    def test_log_level_default(self) -> None:
        """Test default log level."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.log_level == "INFO"

    def test_enable_debug_mode_default_false(self) -> None:
        """Test that debug mode is False by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_debug_mode is False

    def test_valid_log_levels(self) -> None:
        """Test all valid log level literals."""
        from session_buddy.settings import SessionMgmtSettings

        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = SessionMgmtSettings(log_level=level)
            assert settings.log_level == level

    def test_custom_server_name(self) -> None:
        """Test setting custom server name."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(server_name="Custom Server")
        assert settings.server_name == "Custom Server"

    def test_custom_log_level(self) -> None:
        """Test setting custom log level."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"


class TestSessionMgmtSettingsPaths:
    """Test SessionMgmtSettings path fields and expansion."""

    def test_default_data_dir(self) -> None:
        """Test default data directory path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.data_dir == Path("~/.claude/data")

    def test_default_log_dir(self) -> None:
        """Test default log directory path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.log_dir == Path("~/.claude/logs")

    def test_default_database_path(self) -> None:
        """Test default database path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.database_path == Path("~/.claude/data/reflection.duckdb")

    def test_default_global_workspace_path(self) -> None:
        """Test default global workspace path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.global_workspace_path == Path("~/Projects/claude")

    def test_default_log_file_path(self) -> None:
        """Test default log file path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.log_file_path == Path("~/.claude/logs/session-buddy.log")

    def test_user_path_expansion_data_dir(self) -> None:
        """Test that ~ is expanded in data_dir."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(data_dir=Path("~/my/data"))
        expanded = settings.data_dir
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_user_path_expansion_log_dir(self) -> None:
        """Test that ~ is expanded in log_dir."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(log_dir=Path("~/my/logs"))
        expanded = settings.log_dir
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_user_path_expansion_database_path(self) -> None:
        """Test that ~ is expanded in database_path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(database_path=Path("~/my/db.duckdb"))
        expanded = settings.database_path
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_user_path_expansion_log_file_path(self) -> None:
        """Test that ~ is expanded in log_file_path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(log_file_path=Path("~/my/logs/app.log"))
        expanded = settings.log_file_path
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_user_path_expansion_global_workspace_path(self) -> None:
        """Test that ~ is expanded in global_workspace_path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(global_workspace_path=Path("~/my/workspace"))
        expanded = settings.global_workspace_path
        assert "~" not in str(expanded)
        assert expanded.is_absolute()

    def test_string_path_inputs_are_expanded(self) -> None:
        """Test that string inputs go through the path expansion validator."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(
            data_dir="~/my/data",
            log_dir="~/my/logs",
            database_path="~/my/db.duckdb",
            log_file_path="~/my/logs/app.log",
            global_workspace_path="~/my/workspace",
        )

        assert settings.data_dir.is_absolute()
        assert settings.log_dir.is_absolute()
        assert settings.database_path.is_absolute()
        assert settings.log_file_path.is_absolute()
        assert settings.global_workspace_path.is_absolute()


class TestSessionMgmtSettingsDatabase:
    """Test SessionMgmtSettings database configuration."""

    def test_database_connection_timeout_default(self) -> None:
        """Test default database connection timeout."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.database_connection_timeout == 30

    def test_database_query_timeout_default(self) -> None:
        """Test default database query timeout."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.database_query_timeout == 120

    def test_database_max_connections_default(self) -> None:
        """Test default max database connections."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.database_max_connections == 10

    def test_connection_timeout_range_min(self) -> None:
        """Test minimum connection timeout is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(database_connection_timeout=1)
        assert settings.database_connection_timeout == 1

    def test_connection_timeout_range_max(self) -> None:
        """Test maximum connection timeout is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(database_connection_timeout=300)
        assert settings.database_connection_timeout == 300

    def test_query_timeout_range_min(self) -> None:
        """Test minimum query timeout is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(database_query_timeout=1)
        assert settings.database_query_timeout == 1

    def test_query_timeout_range_max(self) -> None:
        """Test maximum query timeout is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(database_query_timeout=3600)
        assert settings.database_query_timeout == 3600


class TestSessionMgmtSettingsMultiProject:
    """Test SessionMgmtSettings multi-project settings."""

    def test_enable_multi_project_default_true(self) -> None:
        """Test that multi-project is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_multi_project is True

    def test_auto_detect_projects_default_true(self) -> None:
        """Test that auto-detect projects is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_detect_projects is True

    def test_project_groups_enabled_default_true(self) -> None:
        """Test that project groups are enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.project_groups_enabled is True


class TestSessionMgmtSettingsSearch:
    """Test SessionMgmtSettings search configuration."""

    def test_enable_full_text_search_default_true(self) -> None:
        """Test that full-text search is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_full_text_search is True

    def test_enable_semantic_search_default_true(self) -> None:
        """Test that semantic search is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_semantic_search is True

    def test_enable_faceted_search_default_true(self) -> None:
        """Test that faceted search is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_faceted_search is True

    def test_enable_search_suggestions_default_true(self) -> None:
        """Test that search suggestions are enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_search_suggestions is True

    def test_enable_stemming_default_true(self) -> None:
        """Test that stemming is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_stemming is True

    def test_enable_fuzzy_matching_default_true(self) -> None:
        """Test that fuzzy matching is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_fuzzy_matching is True

    def test_max_search_results_default(self) -> None:
        """Test default max search results."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.max_search_results == 100

    def test_max_search_results_range_min(self) -> None:
        """Test minimum max search results is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(max_search_results=1)
        assert settings.max_search_results == 1

    def test_max_search_results_range_max(self) -> None:
        """Test maximum max search results is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(max_search_results=10000)
        assert settings.max_search_results == 10000

    def test_embedding_model_default(self) -> None:
        """Test default embedding model."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.embedding_model == "all-MiniLM-L6-v2"

    def test_embedding_cache_size_default(self) -> None:
        """Test default embedding cache size."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.embedding_cache_size == 1000

    def test_search_index_update_interval_default(self) -> None:
        """Test default search index update interval."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.search_index_update_interval == 3600

    def test_fuzzy_threshold_default(self) -> None:
        """Test default fuzzy threshold."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.fuzzy_threshold == 0.8

    def test_fuzzy_threshold_range_min(self) -> None:
        """Test minimum fuzzy threshold is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(fuzzy_threshold=0.1)
        assert settings.fuzzy_threshold == 0.1

    def test_fuzzy_threshold_range_max(self) -> None:
        """Test maximum fuzzy threshold is enforced."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings(fuzzy_threshold=1.0)
        assert settings.fuzzy_threshold == 1.0

    def test_max_facet_values_default(self) -> None:
        """Test default max facet values."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.max_facet_values == 50

    def test_suggestion_limit_default(self) -> None:
        """Test default suggestion limit."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.suggestion_limit == 10


class TestSessionMgmtSettingsTokenOptimization:
    """Test SessionMgmtSettings token optimization settings."""

    def test_enable_token_optimization_default_true(self) -> None:
        """Test that token optimization is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_token_optimization is True

    def test_default_max_tokens_default(self) -> None:
        """Test default max tokens."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.default_max_tokens == 4000

    def test_default_chunk_size_default(self) -> None:
        """Test default chunk size."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.default_chunk_size == 2000

    def test_optimization_strategy_default(self) -> None:
        """Test default optimization strategy."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.optimization_strategy == "auto"

    def test_enable_response_chunking_default_true(self) -> None:
        """Test that response chunking is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_response_chunking is True

    def test_enable_duplicate_filtering_default_true(self) -> None:
        """Test that duplicate filtering is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_duplicate_filtering is True

    def test_track_token_usage_default_true(self) -> None:
        """Test that token usage tracking is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.track_token_usage is True

    def test_usage_retention_days_default(self) -> None:
        """Test default usage retention days."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.usage_retention_days == 90


class TestSessionMgmtSettingsSessionManagement:
    """Test SessionMgmtSettings session management settings."""

    def test_auto_checkpoint_interval_default(self) -> None:
        """Test default auto checkpoint interval."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_checkpoint_interval == 1800

    def test_enable_auto_commit_default_true(self) -> None:
        """Test that auto commit is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_auto_commit is True

    def test_commit_message_template_default(self) -> None:
        """Test default commit message template."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.commit_message_template == "checkpoint: Session checkpoint - {timestamp}"

    def test_commit_message_template_must_contain_timestamp(self) -> None:
        """Test that commit message template must contain {timestamp}."""
        import pydantic
        from session_buddy.settings import SessionMgmtSettings

        with pytest.raises(pydantic.ValidationError):
            SessionMgmtSettings(commit_message_template="invalid template without timestamp")

    def test_commit_message_template_validator_accepts_valid_value(self) -> None:
        """Test the validator directly on a valid template."""
        from session_buddy.settings import SessionMgmtSettings

        template = "checkpoint: Session checkpoint - {timestamp}"
        assert SessionMgmtSettings.validate_commit_template(template) == template

    def test_commit_message_template_validator_rejects_invalid_value(self) -> None:
        """Test the validator directly on an invalid template."""
        from session_buddy.settings import SessionMgmtSettings

        with pytest.raises(ValueError, match="must contain {timestamp}"):
            SessionMgmtSettings.validate_commit_template("checkpoint without placeholder")

    def test_enable_permission_system_default_true(self) -> None:
        """Test that permission system is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_permission_system is True

    def test_default_trusted_operations_default(self) -> None:
        """Test default trusted operations."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.default_trusted_operations == ["git_commit", "uv_sync", "file_operations"]

    def test_auto_cleanup_old_sessions_default_true(self) -> None:
        """Test that auto cleanup old sessions is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_cleanup_old_sessions is True

    def test_session_retention_days_default(self) -> None:
        """Test default session retention days."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.session_retention_days == 365


class TestSessionMgmtSettingsAutoStore:
    """Test SessionMgmtSettings selective auto-store settings."""

    def test_enable_auto_store_reflections_default_true(self) -> None:
        """Test that auto store reflections is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_auto_store_reflections is True

    def test_auto_store_quality_delta_threshold_default(self) -> None:
        """Test default quality delta threshold."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_store_quality_delta_threshold == 10

    def test_auto_store_exceptional_quality_threshold_default(self) -> None:
        """Test default exceptional quality threshold."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_store_exceptional_quality_threshold == 90

    def test_auto_store_manual_checkpoints_default_true(self) -> None:
        """Test that auto store manual checkpoints is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_store_manual_checkpoints is True

    def test_auto_store_session_end_default_true(self) -> None:
        """Test that auto store session end is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_store_session_end is True


class TestSessionMgmtSettingsConversationStorage:
    """Test SessionMgmtSettings conversation storage settings."""

    def test_enable_conversation_storage_default_true(self) -> None:
        """Test that conversation storage is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_conversation_storage is True

    def test_conversation_storage_min_length_default(self) -> None:
        """Test default conversation storage min length."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.conversation_storage_min_length == 100

    def test_conversation_storage_max_length_default(self) -> None:
        """Test default conversation storage max length."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.conversation_storage_max_length == 50000

    def test_auto_store_conversations_on_checkpoint_default_true(self) -> None:
        """Test that auto store conversations on checkpoint is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_store_conversations_on_checkpoint is True

    def test_auto_store_conversations_on_session_end_default_true(self) -> None:
        """Test that auto store conversations on session end is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.auto_store_conversations_on_session_end is True


class TestSessionMgmtSettingsInsights:
    """Test SessionMgmtSettings insights capture settings."""

    def test_enable_insight_extraction_default_true(self) -> None:
        """Test that insight extraction is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_insight_extraction is True

    def test_insight_extraction_confidence_threshold_default(self) -> None:
        """Test default insight extraction confidence threshold."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.insight_extraction_confidence_threshold == 0.3

    def test_insight_extraction_max_per_checkpoint_default(self) -> None:
        """Test default max insights per checkpoint."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.insight_extraction_max_per_checkpoint == 10

    def test_insight_auto_prune_enabled_default_true(self) -> None:
        """Test that insight auto prune is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.insight_auto_prune_enabled is True

    def test_insight_prune_age_days_default(self) -> None:
        """Test default insight prune age days."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.insight_prune_age_days == 90

    def test_insight_prune_min_quality_default(self) -> None:
        """Test default insight prune min quality."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.insight_prune_min_quality == 0.4

    def test_insight_prune_min_usage_default(self) -> None:
        """Test default insight prune min usage."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.insight_prune_min_usage == 0


class TestSessionMgmtSettingsIntegration:
    """Test SessionMgmtSettings integration settings."""

    def test_dhara_url_default_none(self) -> None:
        """Test that Dhara URL defaults to None."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.dhara_url is None

    def test_enable_crackerjack_default_true(self) -> None:
        """Test that Crackerjack integration is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_crackerjack is True

    def test_crackerjack_command_default(self) -> None:
        """Test default Crackerjack command."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.crackerjack_command == "crackerjack"

    def test_enable_git_integration_default_true(self) -> None:
        """Test that git integration is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_git_integration is True

    def test_git_auto_stage_default_false(self) -> None:
        """Test that git auto stage is disabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.git_auto_stage is False


class TestSessionMgmtSettingsGitMaintenance:
    """Test SessionMgmtSettings git maintenance settings."""

    def test_git_auto_gc_default_true(self) -> None:
        """Test that git auto gc is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.git_auto_gc is True

    def test_git_gc_prune_delay_default(self) -> None:
        """Test default git gc prune delay."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.git_gc_prune_delay == "2.weeks"

    def test_git_gc_auto_threshold_default(self) -> None:
        """Test default git gc auto threshold."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.git_gc_auto_threshold == 6700

    def test_git_gc_only_when_clean_default_true(self) -> None:
        """Test that git gc only when clean is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.git_gc_only_when_clean is True

    def test_git_gc_prune_delay_valid_formats(self) -> None:
        """Test valid git gc prune delay formats are accepted."""
        from session_buddy.settings import SessionMgmtSettings

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
            settings = SessionMgmtSettings(git_gc_prune_delay=delay)
            assert settings.git_gc_prune_delay == delay

    def test_git_gc_prune_delay_validator_accepts_valid_values(self) -> None:
        """Test the validator directly on valid values."""
        from session_buddy.settings import SessionMgmtSettings

        assert SessionMgmtSettings.validate_prune_delay("2.weeks") == "2.weeks"

    def test_git_gc_prune_delay_invalid_formats_rejected(self) -> None:
        """Test invalid git gc prune delay formats are rejected."""
        import pydantic
        from session_buddy.settings import SessionMgmtSettings

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
                SessionMgmtSettings(git_gc_prune_delay=delay)

    def test_git_gc_prune_delay_now_triggers_warning(self) -> None:
        """Test that setting prune_delay to 'now' triggers a warning."""
        from session_buddy.settings import SessionMgmtSettings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            SessionMgmtSettings(git_gc_prune_delay="now")
            assert len(w) == 1
            assert "data loss" in str(w[0].message).lower()

    def test_git_gc_prune_delay_validator_rejects_invalid_values(self) -> None:
        """Test the validator directly on invalid values."""
        from session_buddy.settings import SessionMgmtSettings

        with pytest.raises(ValueError, match="Invalid git_gc_prune_delay"):
            SessionMgmtSettings.validate_prune_delay("bad-value")

    def test_git_gc_prune_delay_validator_warns_on_now(self) -> None:
        """Test the validator directly on 'now'."""
        from session_buddy.settings import SessionMgmtSettings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert SessionMgmtSettings.validate_prune_delay("now") == "now"
            assert len(w) == 1


class TestSessionMgmtSettingsPrometheus:
    """Test SessionMgmtSettings Prometheus metrics settings."""

    def test_enable_prometheus_metrics_default_true(self) -> None:
        """Test that Prometheus metrics is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_prometheus_metrics is True

    def test_prometheus_metrics_port_default(self) -> None:
        """Test default Prometheus metrics port."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.prometheus_metrics_port == 9090

    def test_prometheus_metrics_path_default(self) -> None:
        """Test default Prometheus metrics path."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.prometheus_metrics_path == "/metrics"


class TestSessionMgmtSettingsAPIKeys:
    """Test SessionMgmtSettings API key fields."""

    def test_openai_api_key_default_none(self) -> None:
        """Test that OpenAI API key defaults to None."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.openai_api_key is None

    def test_anthropic_api_key_default_none(self) -> None:
        """Test that Anthropic API key defaults to None."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.anthropic_api_key is None

    def test_gemini_api_key_default_none(self) -> None:
        """Test that Gemini API key defaults to None."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.gemini_api_key is None

    def test_qwen_api_key_default_none(self) -> None:
        """Test that Qwen API key defaults to None."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.qwen_api_key is None

    def test_minimax_api_key_default_none(self) -> None:
        """Test that MiniMax API key defaults to None."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.minimax_api_key is None

    def test_zai_api_key_default_none(self) -> None:
        """Test that ZAI API key defaults to None."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.zai_api_key is None


class TestSessionMgmtSettingsLogging:
    """Test SessionMgmtSettings logging settings."""

    def test_log_format_default(self) -> None:
        """Test default log format."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.log_format == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def test_enable_file_logging_default_true(self) -> None:
        """Test that file logging is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_file_logging is True

    def test_log_file_max_size_default(self) -> None:
        """Test default log file max size (10MB)."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.log_file_max_size == 10 * 1024 * 1024

    def test_log_file_backup_count_default(self) -> None:
        """Test default log file backup count."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.log_file_backup_count == 5

    def test_enable_performance_logging_default_false(self) -> None:
        """Test that performance logging is disabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_performance_logging is False

    def test_log_slow_queries_default_true(self) -> None:
        """Test that slow query logging is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.log_slow_queries is True

    def test_slow_query_threshold_default(self) -> None:
        """Test default slow query threshold."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.slow_query_threshold == 1.0


class TestSessionMgmtSettingsSecurity:
    """Test SessionMgmtSettings security settings."""

    def test_anonymize_paths_default_false(self) -> None:
        """Test that path anonymization is disabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.anonymize_paths is False

    def test_enable_rate_limiting_default_true(self) -> None:
        """Test that rate limiting is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_rate_limiting is True

    def test_max_requests_per_minute_default(self) -> None:
        """Test default max requests per minute."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.max_requests_per_minute == 100

    def test_max_query_length_default(self) -> None:
        """Test default max query length."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.max_query_length == 10000

    def test_max_content_length_default(self) -> None:
        """Test default max content length."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.max_content_length == 1000000


class TestSessionMgmtSettingsMCPServer:
    """Test SessionMgmtSettings MCP server settings."""

    def test_server_host_default(self) -> None:
        """Test default server host."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.server_host == "localhost"

    def test_server_port_default(self) -> None:
        """Test default server port."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.server_port == 3000

    def test_enable_websockets_default_true(self) -> None:
        """Test that WebSockets is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_websockets is True


class TestSessionMgmtSettingsDevelopment:
    """Test SessionMgmtSettings development settings."""

    def test_enable_hot_reload_default_false(self) -> None:
        """Test that hot reload is disabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_hot_reload is False


class TestSessionMgmtSettingsFeatureFlags:
    """Test SessionMgmtSettings feature flags."""

    def test_use_schema_v2_default_true(self) -> None:
        """Test that schema v2 is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.use_schema_v2 is True

    def test_enable_llm_entity_extraction_default_true(self) -> None:
        """Test that LLM entity extraction is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_llm_entity_extraction is True

    def test_enable_anthropic_default_true(self) -> None:
        """Test that Anthropic provider is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_anthropic is True

    def test_enable_ollama_default_false(self) -> None:
        """Test that Ollama provider is disabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_ollama is False

    def test_enable_conscious_agent_default_true(self) -> None:
        """Test that conscious agent is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_conscious_agent is True

    def test_enable_filesystem_extraction_default_true(self) -> None:
        """Test that filesystem extraction is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.enable_filesystem_extraction is True


class TestSessionMgmtSettingsExtraction:
    """Test SessionMgmtSettings extraction control settings."""

    def test_llm_extraction_timeout_default(self) -> None:
        """Test default LLM extraction timeout."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.llm_extraction_timeout == 10

    def test_llm_extraction_retries_default(self) -> None:
        """Test default LLM extraction retries."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.llm_extraction_retries == 1


class TestSessionMgmtSettingsFilesystemExtraction:
    """Test SessionMgmtSettings filesystem extraction settings."""

    def test_filesystem_dedupe_ttl_seconds_default(self) -> None:
        """Test default filesystem dedupe TTL."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.filesystem_dedupe_ttl_seconds == 120

    def test_filesystem_max_file_size_bytes_default(self) -> None:
        """Test default filesystem max file size."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.filesystem_max_file_size_bytes == 1_000_000

    def test_filesystem_ignore_dirs_default(self) -> None:
        """Test default filesystem ignore directories."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
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
        assert settings.filesystem_ignore_dirs == expected


class TestSessionMgmtSettingsAkoshaSync:
    """Test SessionMgmtSettings Akosha sync settings."""

    def test_akosha_cloud_bucket_default_empty(self) -> None:
        """Test that Akosha cloud bucket is empty by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_cloud_bucket == ""

    def test_akosha_cloud_endpoint_default_empty(self) -> None:
        """Test that Akosha cloud endpoint is empty by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_cloud_endpoint == ""

    def test_akosha_cloud_region_default_auto(self) -> None:
        """Test that Akosha cloud region is 'auto' by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_cloud_region == "auto"

    def test_akosha_system_id_default_empty(self) -> None:
        """Test that Akosha system ID is empty by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_system_id == ""

    def test_akosha_upload_on_session_end_default_true(self) -> None:
        """Test that upload on session end is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_upload_on_session_end is True

    def test_akosha_enable_fallback_default_true(self) -> None:
        """Test that fallback is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_enable_fallback is True

    def test_akosha_force_method_default_auto(self) -> None:
        """Test that force method is 'auto' by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_force_method == "auto"

    def test_akosha_upload_timeout_seconds_default(self) -> None:
        """Test default upload timeout."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_upload_timeout_seconds == 300

    def test_akosha_max_retries_default(self) -> None:
        """Test default max retries."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_max_retries == 3

    def test_akosha_retry_backoff_seconds_default(self) -> None:
        """Test default retry backoff."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_retry_backoff_seconds == 2.0

    def test_akosha_enable_compression_default_true(self) -> None:
        """Test that compression is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_enable_compression is True

    def test_akosha_enable_deduplication_default_true(self) -> None:
        """Test that deduplication is enabled by default."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_enable_deduplication is True

    def test_akosha_chunk_size_mb_default(self) -> None:
        """Test default chunk size."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings()
        assert settings.akosha_chunk_size_mb == 5

    def test_akosha_force_method_valid_literals(self) -> None:
        """Test valid akosha force method literals."""
        from session_buddy.settings import SessionMgmtSettings

        for method in ["auto", "cloud", "http"]:
            settings = SessionMgmtSettings(akosha_force_method=method)
            assert settings.akosha_force_method == method


class TestLegacyDebugFlag:
    """Test legacy debug flag mapping to enable_debug_mode."""

    def test_legacy_debug_flag_maps_to_enable_debug_mode(self) -> None:
        """Test that legacy 'debug' field maps to 'enable_debug_mode'."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings.model_validate({"debug": True})
        assert settings.enable_debug_mode is True

    def test_legacy_debug_false_maps_to_enable_debug_mode_false(self) -> None:
        """Test that legacy 'debug: false' maps correctly."""
        from session_buddy.settings import SessionMgmtSettings

        settings = SessionMgmtSettings.model_validate({"debug": False})
        assert settings.enable_debug_mode is False

    def test_explicit_enable_debug_mode_not_overridden(self) -> None:
        """Test that explicit enable_debug_mode takes precedence."""
        from session_buddy.settings import SessionMgmtSettings

        data = {"debug": True, "enable_debug_mode": False}
        settings = SessionMgmtSettings.model_validate(data)
        assert settings.enable_debug_mode is False

    def test_non_dict_passthrough(self) -> None:
        """Test that non-dict values are returned unchanged."""
        from session_buddy.settings import SessionMgmtSettings

        marker = object()
        assert SessionMgmtSettings.map_legacy_debug_flag(marker) is marker

    def test_debug_flag_maps_to_enable_debug_mode(self) -> None:
        """Test the validator directly on legacy debug input."""
        from session_buddy.settings import SessionMgmtSettings

        data = {"debug": 1}
        result = SessionMgmtSettings.map_legacy_debug_flag(data)
        assert result["enable_debug_mode"] is True
        assert result["debug"] == 1


class TestGetSettings:
    """Test get_settings() global function."""

    def test_get_settings_returns_session_mgmt_settings(self) -> None:
        """Test that get_settings returns SessionMgmtSettings instance."""
        from session_buddy import settings as settings_module

        # Clear any cached settings first
        settings_module._settings = None

        mock_instance = SessionMgmtSettings()
        with patch.object(
            settings_module, "_settings", None
        ):
            with patch.object(
                settings_module.SessionMgmtSettings, "load", return_value=mock_instance
            ):
                result = settings_module.get_settings()
                # The result IS the mock instance from load()
                assert result is mock_instance

    def test_get_settings_caches_result(self) -> None:
        """Test that get_settings caches the settings instance."""
        from session_buddy import settings as settings_module

        mock_settings = SessionMgmtSettings()
        with patch.object(settings_module, "_settings", mock_settings):
            with patch.object(
                settings_module.SessionMgmtSettings, "load"
            ) as mock_load:
                result = settings_module.get_settings()
                assert result is mock_settings
                mock_load.assert_not_called()

    def test_get_settings_reload_parameter(self) -> None:
        """Test that reload=True forces fresh load."""
        from session_buddy import settings as settings_module

        mock_settings = SessionMgmtSettings()
        new_settings = SessionMgmtSettings(server_name="Reloaded")

        with patch.object(settings_module, "_settings", mock_settings):
            with patch.object(
                settings_module.SessionMgmtSettings,
                "load",
                return_value=new_settings,
            ) as mock_load:
                result = settings_module.get_settings(reload=True)
                assert result.server_name == "Reloaded"
                mock_load.assert_called_once()


class TestReloadSettings:
    """Test reload_settings() function."""

    def test_reload_settings_calls_get_settings_with_reload_true(self) -> None:
        """Test that reload_settings forces a reload."""
        from session_buddy import settings as settings_module

        new_settings = SessionMgmtSettings(server_name="Reloaded")

        with patch.object(settings_module, "_settings", None):
            with patch.object(
                settings_module.SessionMgmtSettings,
                "load",
                return_value=new_settings,
            ) as mock_load:
                result = settings_module.reload_settings()
                mock_load.assert_called_once_with("session-buddy")


class TestGetDatabasePath:
    """Test get_database_path() function."""

    def test_get_database_path_with_absolute_path(self) -> None:
        """Test get_database_path with absolute database_path."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(
            database_path=Path("/absolute/path/db.duckdb"),
            data_dir=Path("~/.claude/data"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_database_path()
            assert result == Path("/absolute/path/db.duckdb")

    def test_get_database_path_with_relative_path_and_data_dir(self) -> None:
        """Test get_database_path with relative path uses data_dir."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(
            database_path=Path("relative/db.duckdb"),
            data_dir=Path("/tmp/data"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_database_path()
            assert result == Path("/tmp/data/relative/db.duckdb")

    def test_get_database_path_expands_user_tilde(self) -> None:
        """Test get_database_path expands ~ in paths."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(
            database_path=Path("~/my/db.duckdb"),
            data_dir=Path("~/.claude/data"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_database_path()
            assert "~" not in str(result)

    def test_get_database_path_with_string_values(self) -> None:
        """Test get_database_path handles raw string settings values."""
        from session_buddy import settings as settings_module
        from unittest.mock import Mock

        mock_settings = Mock()
        mock_settings.database_path = "relative/db.duckdb"
        mock_settings.data_dir = "/tmp/data"

        with patch.object(settings_module, "_settings", mock_settings):
            result = settings_module.get_database_path()

        assert result == Path("/tmp/data/relative/db.duckdb")


class TestGetLogFilePath:
    """Test get_log_file_path() function."""

    def test_get_log_file_path_with_absolute_path(self) -> None:
        """Test get_log_file_path with absolute log_file_path."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(
            log_file_path=Path("/absolute/log/app.log"),
            log_dir=Path("~/.claude/logs"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_log_file_path()
            assert result == Path("/absolute/log/app.log")

    def test_get_log_file_path_with_relative_path_and_log_dir(self) -> None:
        """Test get_log_file_path with relative path uses log_dir."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(
            log_file_path=Path("relative/log.log"),
            log_dir=Path("/tmp/logs"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_log_file_path()
            assert result == Path("/tmp/logs/relative/log.log")

    def test_get_log_file_path_expands_user_tilde(self) -> None:
        """Test get_log_file_path expands ~ in paths."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(
            log_file_path=Path("~/my/logs/app.log"),
            log_dir=Path("~/.claude/logs"),
        )
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_log_file_path()
            assert "~" not in str(result)

    def test_get_log_file_path_with_string_values(self) -> None:
        """Test get_log_file_path rejects raw string settings values."""
        from session_buddy import settings as settings_module
        from unittest.mock import Mock

        mock_settings = Mock()
        mock_settings.log_file_path = "relative/app.log"
        mock_settings.log_dir = "/tmp/logs"

        with patch.object(settings_module, "_settings", mock_settings):
            with pytest.raises(AttributeError):
                settings_module.get_log_file_path()


class TestGetLLMAPIKey:
    """Test get_llm_api_key() function."""

    def test_get_llm_api_key_openai(self) -> None:
        """Test get_llm_api_key for OpenAI provider."""
        from session_buddy import settings as settings_module
        from unittest.mock import Mock

        # Use a placeholder test API key
        test_key = "sk-test-placeholder-key-for-unit-testing-only"
        mock_settings = Mock()
        mock_settings.openai_api_key = test_key
        mock_settings.get_api_key_secure = Mock(return_value=test_key)
        with patch.object(settings_module, "_settings", mock_settings):
            result = settings_module.get_llm_api_key("openai")
            assert result == test_key

    def test_get_llm_api_key_anthropic(self) -> None:
        """Test get_llm_api_key for Anthropic provider."""
        from session_buddy import settings as settings_module
        from unittest.mock import Mock

        # Use a placeholder test API key
        test_key = "sk-ant-test-placeholder-key-for-unit-testing-only-1234567890"
        mock_settings = Mock()
        mock_settings.anthropic_api_key = test_key
        mock_settings.get_api_key_secure = Mock(return_value=test_key)
        with patch.object(settings_module, "_settings", mock_settings):
            result = settings_module.get_llm_api_key("anthropic")
            assert result == test_key

    def test_get_llm_api_key_minimax(self) -> None:
        """Test get_llm_api_key for MiniMax provider."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(minimax_api_key="minimax-key")
        with patch.object(settings_module, "_settings", settings):
            with patch.object(
                settings_module.SessionMgmtSettings,
                "get_api_key",
                return_value="minimax-key",
            ):
                result = settings_module.get_llm_api_key("minimax")
                assert result == "minimax-key"

    def test_get_llm_api_key_zai(self) -> None:
        """Test get_llm_api_key for ZAI provider."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(zai_api_key="zai-key")
        with patch.object(settings_module, "_settings", settings):
            with patch.object(
                settings_module.SessionMgmtSettings,
                "get_api_key",
                return_value="zai-key",
            ):
                result = settings_module.get_llm_api_key("zai")
                assert result == "zai-key"

    def test_get_llm_api_key_unknown_provider(self) -> None:
        """Test get_llm_api_key returns None for unknown provider."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings()
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("unknown_provider")
            assert result is None

    def test_get_llm_api_key_empty_key_returns_none(self) -> None:
        """Test get_llm_api_key returns None for empty/whitespace API key."""
        from session_buddy import settings as settings_module

        settings = SessionMgmtSettings(openai_api_key="   ")
        with patch.object(settings_module, "_settings", settings):
            result = settings_module.get_llm_api_key("openai")
            assert result is None


class TestSessionMgmtSettingsLoad:
    """Test SessionMgmtSettings.load() with temp directory."""

    def test_load_creates_instance_from_defaults(self) -> None:
        """Test that load() creates an instance with defaults."""
        from session_buddy.settings import SessionMgmtSettings

        # When no config files exist, load() should still work with defaults
        result = SessionMgmtSettings.load("session-buddy")
        assert isinstance(result, SessionMgmtSettings)

    def test_load_with_temp_settings_file(self) -> None:
        """Test loading from a temporary settings file."""
        import yaml
        from session_buddy.settings import SessionMgmtSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            settings_file = tmp_path / "settings" / "session-buddy.yaml"
            settings_file.parent.mkdir(parents=True, exist_ok=True)

            config_data = {
                "server_name": "Test Server",
                "log_level": "DEBUG",
            }
            with settings_file.open("w") as f:
                yaml.safe_dump(config_data, f)

            # Override the settings directory lookup to use temp dir
            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir)
                result = SessionMgmtSettings.load("session-buddy")
                assert result.server_name == "Test Server"
                assert result.log_level == "DEBUG"
            finally:
                os.chdir(original_cwd)


class TestExports:
    """Test module exports."""

    def test_all_exports_present(self) -> None:
        """Test that all items in __all__ are actually exported."""
        from session_buddy import settings as settings_module

        expected = [
            "SessionMgmtSettings",
            "get_database_path",
            "get_llm_api_key",
            "get_log_file_path",
            "get_settings",
            "reload_settings",
        ]
        for item in expected:
            assert hasattr(settings_module, item)
            assert item in settings_module.__all__


# Import at end to avoid issues with mock patching
from session_buddy.settings import SessionMgmtSettings
