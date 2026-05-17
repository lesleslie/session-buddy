"""Unit tests for Session Buddy settings and configuration.

Tests configuration loading, validation, and defaults for:
- LLM provider configuration
- Core MCP settings
- Database configuration
- Search and semantic search settings
- Token optimization settings
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from session_buddy.settings import LLMProvidersConfig, SessionMgmtSettings


class TestLLMProvidersConfig:
    """Test LLMProvidersConfig dataclass."""

    def test_default_provider_is_minimax(self) -> None:
        """Test that default provider is minimax."""
        config = LLMProvidersConfig()
        assert config.default_provider == "minimax"

    def test_ollama_url_default(self) -> None:
        """Test default Ollama URL."""
        config = LLMProvidersConfig()
        assert config.ollama_base_url == "http://localhost:11434"

    def test_ollama_model_default(self) -> None:
        """Test default Ollama model."""
        config = LLMProvidersConfig()
        assert config.ollama_default_model == "qwen2.5-coder:7b"

    def test_llama_server_url_default(self) -> None:
        """Test default llama-server URL."""
        config = LLMProvidersConfig()
        assert config.llama_server_base_url == "http://localhost:8081"

    def test_llama_server_model_default(self) -> None:
        """Test default llama-server model."""
        config = LLMProvidersConfig()
        assert config.llama_server_default_model == "qwen3.5"

    def test_fallback_providers_default(self) -> None:
        """Test default fallback provider chain."""
        config = LLMProvidersConfig()
        assert config.fallback_providers == [
            "minimax",
            "llama_server",
            "ollama",
        ]

    def test_custom_provider(self) -> None:
        """Test setting custom provider."""
        config = LLMProvidersConfig(default_provider="ollama")
        assert config.default_provider == "ollama"

    def test_custom_fallback_chain(self) -> None:
        """Test setting custom fallback chain."""
        custom_chain = ["ollama", "minimax"]
        config = LLMProvidersConfig(fallback_providers=custom_chain)
        assert config.fallback_providers == custom_chain

    def test_custom_urls(self) -> None:
        """Test setting custom service URLs."""
        config = LLMProvidersConfig(
            ollama_base_url="http://custom:11434",
            llama_server_base_url="http://custom:8081",
        )
        assert config.ollama_base_url == "http://custom:11434"
        assert config.llama_server_base_url == "http://custom:8081"

    def test_valid_provider_values(self) -> None:
        """Test that all valid provider values work."""
        providers = ["minimax", "zai", "openai", "gemini", "ollama", "llama_server"]
        for provider in providers:
            config = LLMProvidersConfig(default_provider=provider)
            assert config.default_provider == provider


class TestSessionMgmtSettingsBasics:
    """Test SessionMgmtSettings basic initialization."""

    def test_server_name_default(self) -> None:
        """Test default server name."""
        settings = SessionMgmtSettings()
        assert settings.server_name == "Session Buddy MCP"

    def test_server_description_default(self) -> None:
        """Test default server description."""
        settings = SessionMgmtSettings()
        assert settings.server_description == "Session management and tooling MCP server"

    def test_log_level_default(self) -> None:
        """Test default log level."""
        settings = SessionMgmtSettings()
        assert settings.log_level == "INFO"

    def test_debug_mode_default(self) -> None:
        """Test that debug mode is disabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_debug_mode is False

    def test_custom_server_name(self) -> None:
        """Test setting custom server name."""
        settings = SessionMgmtSettings(server_name="Custom Server")
        assert settings.server_name == "Custom Server"

    def test_enable_debug_mode(self) -> None:
        """Test enabling debug mode."""
        settings = SessionMgmtSettings(enable_debug_mode=True)
        assert settings.enable_debug_mode is True

    def test_custom_log_level(self) -> None:
        """Test setting custom log level."""
        settings = SessionMgmtSettings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"

    def test_valid_log_levels(self) -> None:
        """Test all valid log level values."""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in levels:
            settings = SessionMgmtSettings(log_level=level)
            assert settings.log_level == level


class TestSessionMgmtSettingsPaths:
    """Test SessionMgmtSettings path configuration."""

    def test_default_data_dir(self) -> None:
        """Test default data directory."""
        settings = SessionMgmtSettings()
        assert str(settings.data_dir) == "~/.claude/data"

    def test_default_log_dir(self) -> None:
        """Test default log directory."""
        settings = SessionMgmtSettings()
        assert str(settings.log_dir) == "~/.claude/logs"

    def test_default_database_path(self) -> None:
        """Test default database path."""
        settings = SessionMgmtSettings()
        assert str(settings.database_path) == "~/.claude/data/reflection.duckdb"

    def test_custom_data_dir(self) -> None:
        """Test setting custom data directory."""
        custom_path = Path("/custom/data")
        settings = SessionMgmtSettings(data_dir=custom_path)
        assert settings.data_dir == custom_path

    def test_custom_database_path(self) -> None:
        """Test setting custom database path."""
        custom_path = Path("/custom/db.duckdb")
        settings = SessionMgmtSettings(database_path=custom_path)
        assert settings.database_path == custom_path


class TestSessionMgmtSettingsDatabaseConfig:
    """Test SessionMgmtSettings database configuration."""

    def test_database_connection_timeout_default(self) -> None:
        """Test default database connection timeout."""
        settings = SessionMgmtSettings()
        assert settings.database_connection_timeout == 30

    def test_database_query_timeout_default(self) -> None:
        """Test default database query timeout."""
        settings = SessionMgmtSettings()
        assert settings.database_query_timeout == 120

    def test_database_max_connections_default(self) -> None:
        """Test default max database connections."""
        settings = SessionMgmtSettings()
        assert settings.database_max_connections == 10

    def test_custom_connection_timeout(self) -> None:
        """Test setting custom connection timeout."""
        settings = SessionMgmtSettings(database_connection_timeout=60)
        assert settings.database_connection_timeout == 60

    def test_custom_query_timeout(self) -> None:
        """Test setting custom query timeout."""
        settings = SessionMgmtSettings(database_query_timeout=300)
        assert settings.database_query_timeout == 300

    def test_custom_max_connections(self) -> None:
        """Test setting custom max connections."""
        settings = SessionMgmtSettings(database_max_connections=20)
        assert settings.database_max_connections == 20

    def test_connection_timeout_constraints(self) -> None:
        """Test connection timeout constraints."""
        # Min value
        settings = SessionMgmtSettings(database_connection_timeout=1)
        assert settings.database_connection_timeout == 1
        # Max value
        settings = SessionMgmtSettings(database_connection_timeout=300)
        assert settings.database_connection_timeout == 300

    def test_query_timeout_constraints(self) -> None:
        """Test query timeout constraints."""
        # Min value
        settings = SessionMgmtSettings(database_query_timeout=1)
        assert settings.database_query_timeout == 1
        # Max value
        settings = SessionMgmtSettings(database_query_timeout=3600)
        assert settings.database_query_timeout == 3600


class TestSessionMgmtSettingsMultiProject:
    """Test SessionMgmtSettings multi-project configuration."""

    def test_multi_project_enabled_default(self) -> None:
        """Test that multi-project is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_multi_project is True

    def test_auto_detect_projects_default(self) -> None:
        """Test that auto-detect projects is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.auto_detect_projects is True

    def test_project_groups_enabled_default(self) -> None:
        """Test that project groups are enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.project_groups_enabled is True

    def test_disable_multi_project(self) -> None:
        """Test disabling multi-project features."""
        settings = SessionMgmtSettings(enable_multi_project=False)
        assert settings.enable_multi_project is False

    def test_disable_auto_detect(self) -> None:
        """Test disabling auto-detect projects."""
        settings = SessionMgmtSettings(auto_detect_projects=False)
        assert settings.auto_detect_projects is False


class TestSessionMgmtSettingsSearch:
    """Test SessionMgmtSettings search configuration."""

    def test_full_text_search_enabled_default(self) -> None:
        """Test that full-text search is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_full_text_search is True

    def test_semantic_search_enabled_default(self) -> None:
        """Test that semantic search is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_semantic_search is True

    def test_faceted_search_enabled_default(self) -> None:
        """Test that faceted search is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_faceted_search is True

    def test_search_suggestions_enabled_default(self) -> None:
        """Test that search suggestions are enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_search_suggestions is True

    def test_stemming_enabled_default(self) -> None:
        """Test that stemming is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_stemming is True

    def test_fuzzy_matching_enabled_default(self) -> None:
        """Test that fuzzy matching is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_fuzzy_matching is True

    def test_max_search_results_default(self) -> None:
        """Test default max search results."""
        settings = SessionMgmtSettings()
        assert settings.max_search_results == 100

    def test_embedding_model_default(self) -> None:
        """Test default embedding model."""
        settings = SessionMgmtSettings()
        assert settings.embedding_model == "all-MiniLM-L6-v2"

    def test_search_index_update_interval_default(self) -> None:
        """Test default search index update interval."""
        settings = SessionMgmtSettings()
        assert settings.search_index_update_interval == 3600

    def test_fuzzy_threshold_default(self) -> None:
        """Test default fuzzy matching threshold."""
        settings = SessionMgmtSettings()
        assert settings.fuzzy_threshold == 0.8

    def test_custom_fuzzy_threshold(self) -> None:
        """Test setting custom fuzzy threshold."""
        settings = SessionMgmtSettings(fuzzy_threshold=0.7)
        assert settings.fuzzy_threshold == 0.7

    def test_disable_features(self) -> None:
        """Test disabling search features."""
        settings = SessionMgmtSettings(
            enable_full_text_search=False,
            enable_semantic_search=False,
            enable_faceted_search=False,
            enable_search_suggestions=False,
            enable_stemming=False,
            enable_fuzzy_matching=False,
        )
        assert settings.enable_full_text_search is False
        assert settings.enable_semantic_search is False
        assert settings.enable_faceted_search is False
        assert settings.enable_search_suggestions is False
        assert settings.enable_stemming is False
        assert settings.enable_fuzzy_matching is False


class TestSessionMgmtSettingsTokenOptimization:
    """Test SessionMgmtSettings token optimization configuration."""

    def test_token_optimization_enabled_default(self) -> None:
        """Test that token optimization is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_token_optimization is True

    def test_response_chunking_enabled_default(self) -> None:
        """Test that response chunking is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_response_chunking is True

    def test_duplicate_filtering_enabled_default(self) -> None:
        """Test that duplicate filtering is enabled by default."""
        settings = SessionMgmtSettings()
        assert settings.enable_duplicate_filtering is True

    def test_default_max_tokens(self) -> None:
        """Test default max tokens."""
        settings = SessionMgmtSettings()
        assert settings.default_max_tokens == 4000

    def test_default_chunk_size(self) -> None:
        """Test default chunk size."""
        settings = SessionMgmtSettings()
        assert settings.default_chunk_size == 2000

    def test_optimization_strategy_default(self) -> None:
        """Test default optimization strategy."""
        settings = SessionMgmtSettings()
        assert settings.optimization_strategy == "auto"

    def test_custom_max_tokens(self) -> None:
        """Test setting custom max tokens."""
        settings = SessionMgmtSettings(default_max_tokens=8000)
        assert settings.default_max_tokens == 8000

    def test_custom_chunk_size(self) -> None:
        """Test setting custom chunk size."""
        settings = SessionMgmtSettings(default_chunk_size=5000)
        assert settings.default_chunk_size == 5000

    def test_custom_optimization_strategy(self) -> None:
        """Test setting custom optimization strategy."""
        settings = SessionMgmtSettings(optimization_strategy="summarize_content")
        assert settings.optimization_strategy == "summarize_content"

    def test_disable_token_optimization(self) -> None:
        """Test disabling token optimization."""
        settings = SessionMgmtSettings(enable_token_optimization=False)
        assert settings.enable_token_optimization is False

    def test_disable_chunking(self) -> None:
        """Test disabling response chunking."""
        settings = SessionMgmtSettings(enable_response_chunking=False)
        assert settings.enable_response_chunking is False


class TestSessionMgmtSettingsIntegration:
    """Test SessionMgmtSettings integrated configuration."""

    def test_all_settings_together(self) -> None:
        """Test setting multiple configurations together."""
        settings = SessionMgmtSettings(
            server_name="Custom",
            enable_debug_mode=True,
            enable_token_optimization=True,
            enable_semantic_search=False,
            database_max_connections=20,
            default_max_tokens=8000,
        )
        assert settings.server_name == "Custom"
        assert settings.enable_debug_mode is True
        assert settings.enable_token_optimization is True
        assert settings.enable_semantic_search is False
        assert settings.database_max_connections == 20
        assert settings.default_max_tokens == 8000

    def test_llm_providers_nested(self) -> None:
        """Test LLM providers nested configuration."""
        settings = SessionMgmtSettings()
        assert isinstance(settings.llm_providers, LLMProvidersConfig)
        assert settings.llm_providers.default_provider == "minimax"

    def test_custom_llm_providers_config(self) -> None:
        """Test customizing LLM providers configuration."""
        custom_llm_config = LLMProvidersConfig(
            default_provider="ollama",
            fallback_providers=["ollama", "minimax"],
        )
        settings = SessionMgmtSettings(llm_providers=custom_llm_config)
        assert settings.llm_providers.default_provider == "ollama"
        assert settings.llm_providers.fallback_providers == ["ollama", "minimax"]
