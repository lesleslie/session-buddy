"""Unit tests for ``SessionBuddySettings`` nested ``*Config`` groups.

Tests configuration loading, validation, and defaults for:

- LLM provider configuration (``LLMConfig`` + ``LLMApiKeysConfig``)
- Core MCP identity + transport (``ServerIdentityConfig``,
  ``MCPTransportConfig``)
- Paths (``PathsConfig``) and database (``DatabaseConfig``)
- Multi-project coordination (``MultiProjectConfig``)
- Search + embedding settings (``SearchConfig``)
- Token optimization (``TokensConfig``)

Replaces the legacy flat-shape ``SessionMgmtSettings`` test suite
(deleted in Phase 6). Each test constructs a real
``SessionBuddySettings`` instance via the nested constructor pattern:

    SessionBuddySettings(
        multi_project=MultiProjectConfig(enable_multi_project=False),
    )
"""

from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.settings import (
    AkoshaSyncConfig,
    ConversationStorageConfig,
    DatabaseConfig,
    FeatureFlagsConfig,
    GitMaintenanceConfig,
    IntegrationsConfig,
    LLMApiKeysConfig,
    LLMConfig,
    LoggingConfig,
    MCPTransportConfig,
    MultiProjectConfig,
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


class TestLLMConfig:
    """Test the consolidated ``LLMConfig`` group."""

    def test_default_provider_is_minimax(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.default_provider == "minimax"

    def test_ollama_url_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.ollama_base_url == "http://localhost:11434"

    def test_ollama_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.ollama_default_model == "qwen2.5-coder:7b"

    def test_llama_server_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.llama_server_default_model == "qwen3.5"

    def test_llama_server_model_field_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.llm.llama_server_model == "qwen3.5"

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

    def test_custom_provider(self) -> None:
        settings = SessionBuddySettings(
            llm=LLMConfig(default_provider="ollama"),
        )
        assert settings.llm.default_provider == "ollama"

    def test_custom_fallback_chain(self) -> None:
        settings = SessionBuddySettings(
            llm=LLMConfig(fallback_providers=["ollama", "minimax"]),
        )
        assert settings.llm.fallback_providers == ["ollama", "minimax"]

    def test_custom_ollama_url(self) -> None:
        settings = SessionBuddySettings(
            llm=LLMConfig(ollama_base_url="http://custom:11434"),
        )
        assert settings.llm.ollama_base_url == "http://custom:11434"

    def test_valid_provider_values(self) -> None:
        providers = ["minimax", "zai", "openai", "gemini", "ollama", "llama_server"]
        for provider in providers:
            settings = SessionBuddySettings(
                llm=LLMConfig(default_provider=provider),
            )
            assert settings.llm.default_provider == provider

    def test_api_keys_group_is_nested(self) -> None:
        settings = SessionBuddySettings()
        assert isinstance(settings.llm.api_keys, LLMApiKeysConfig)
        assert settings.llm.api_keys.openai is None
        assert settings.llm.api_keys.minimax is None


class TestServerIdentityConfig:
    """Test ``ServerIdentityConfig`` (MCP server identity)."""

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

    def test_enable_debug_mode_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_server.enable_debug_mode is False

    def test_custom_server_name(self) -> None:
        settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(server_name="Custom Server"),
        )
        assert settings.mcp_server.server_name == "Custom Server"

    def test_enable_debug_mode(self) -> None:
        settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(enable_debug_mode=True),
        )
        assert settings.mcp_server.enable_debug_mode is True

    def test_custom_log_level(self) -> None:
        settings = SessionBuddySettings(
            mcp_server=ServerIdentityConfig(log_level="DEBUG"),
        )
        assert settings.mcp_server.log_level == "DEBUG"

    def test_valid_log_levels(self) -> None:
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in levels:
            settings = SessionBuddySettings(
                mcp_server=ServerIdentityConfig(log_level=level),
            )
            assert settings.mcp_server.log_level == level


class TestPathsConfig:
    """Test ``PathsConfig`` (filesystem path settings + ~ expansion)."""

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

    def test_custom_data_dir(self) -> None:
        settings = SessionBuddySettings(
            paths=PathsConfig(data_dir=Path("/custom/data")),
        )
        assert settings.paths.data_dir == Path("/custom/data")

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


class TestDatabaseConfig:
    """Test ``DatabaseConfig`` (DuckDB connection settings)."""

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

    def test_custom_connection_timeout(self) -> None:
        settings = SessionBuddySettings(
            database=DatabaseConfig(connection_timeout=60),
        )
        assert settings.database.connection_timeout == 60

    def test_custom_query_timeout(self) -> None:
        settings = SessionBuddySettings(
            database=DatabaseConfig(query_timeout=300),
        )
        assert settings.database.query_timeout == 300

    def test_custom_max_connections(self) -> None:
        settings = SessionBuddySettings(
            database=DatabaseConfig(max_connections=20),
        )
        assert settings.database.max_connections == 20

    def test_connection_timeout_constraints(self) -> None:
        # Min value
        settings = SessionBuddySettings(
            database=DatabaseConfig(connection_timeout=1),
        )
        assert settings.database.connection_timeout == 1
        # Max value
        settings = SessionBuddySettings(
            database=DatabaseConfig(connection_timeout=300),
        )
        assert settings.database.connection_timeout == 300

    def test_query_timeout_constraints(self) -> None:
        # Min value
        settings = SessionBuddySettings(
            database=DatabaseConfig(query_timeout=1),
        )
        assert settings.database.query_timeout == 1
        # Max value
        settings = SessionBuddySettings(
            database=DatabaseConfig(query_timeout=3600),
        )
        assert settings.database.query_timeout == 3600


class TestMultiProjectConfig:
    """Test ``MultiProjectConfig``."""

    def test_multi_project_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.multi_project.enable_multi_project is True

    def test_auto_detect_projects_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.multi_project.auto_detect_projects is True

    def test_project_groups_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.multi_project.project_groups_enabled is True

    def test_disable_multi_project(self) -> None:
        settings = SessionBuddySettings(
            multi_project=MultiProjectConfig(enable_multi_project=False),
        )
        assert settings.multi_project.enable_multi_project is False

    def test_disable_auto_detect(self) -> None:
        settings = SessionBuddySettings(
            multi_project=MultiProjectConfig(auto_detect_projects=False),
        )
        assert settings.multi_project.auto_detect_projects is False


class TestSearchConfig:
    """Test ``SearchConfig`` (database search + embeddings)."""

    def test_full_text_search_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_full_text_search is True

    def test_semantic_search_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_semantic_search is True

    def test_faceted_search_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_faceted_search is True

    def test_search_suggestions_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_search_suggestions is True

    def test_stemming_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_stemming is True

    def test_fuzzy_matching_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.enable_fuzzy_matching is True

    def test_max_search_results_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.max_search_results == 100

    def test_embedding_model_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.embedding_model == "all-MiniLM-L6-v2"

    def test_search_index_update_interval_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.search_index_update_interval == 3600

    def test_fuzzy_threshold_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.search.fuzzy_threshold == 0.8

    def test_custom_fuzzy_threshold(self) -> None:
        settings = SessionBuddySettings(
            search=SearchConfig(fuzzy_threshold=0.7),
        )
        assert settings.search.fuzzy_threshold == 0.7

    def test_disable_features(self) -> None:
        settings = SessionBuddySettings(
            search=SearchConfig(
                enable_full_text_search=False,
                enable_semantic_search=False,
                enable_faceted_search=False,
                enable_search_suggestions=False,
                enable_stemming=False,
                enable_fuzzy_matching=False,
            ),
        )
        assert settings.search.enable_full_text_search is False
        assert settings.search.enable_semantic_search is False
        assert settings.search.enable_faceted_search is False
        assert settings.search.enable_search_suggestions is False
        assert settings.search.enable_stemming is False
        assert settings.search.enable_fuzzy_matching is False


class TestTokensConfig:
    """Test ``TokensConfig`` (token optimization)."""

    def test_token_optimization_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.enable_token_optimization is True

    def test_response_chunking_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.enable_response_chunking is True

    def test_duplicate_filtering_enabled_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.enable_duplicate_filtering is True

    def test_default_max_tokens(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.default_max_tokens == 4000

    def test_default_chunk_size(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.default_chunk_size == 2000

    def test_optimization_strategy_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.tokens.optimization_strategy == "auto"

    def test_custom_max_tokens(self) -> None:
        settings = SessionBuddySettings(
            tokens=TokensConfig(default_max_tokens=8000),
        )
        assert settings.tokens.default_max_tokens == 8000

    def test_custom_chunk_size(self) -> None:
        settings = SessionBuddySettings(
            tokens=TokensConfig(default_chunk_size=5000),
        )
        assert settings.tokens.default_chunk_size == 5000

    def test_custom_optimization_strategy(self) -> None:
        settings = SessionBuddySettings(
            tokens=TokensConfig(optimization_strategy="summarize_content"),
        )
        assert settings.tokens.optimization_strategy == "summarize_content"

    def test_disable_token_optimization(self) -> None:
        settings = SessionBuddySettings(
            tokens=TokensConfig(enable_token_optimization=False),
        )
        assert settings.tokens.enable_token_optimization is False

    def test_disable_chunking(self) -> None:
        settings = SessionBuddySettings(
            tokens=TokensConfig(enable_response_chunking=False),
        )
        assert settings.tokens.enable_response_chunking is False


class TestMCPTransportConfig:
    """Test ``MCPTransportConfig`` (HTTP/WS transport layer)."""

    def test_server_host_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_transport.server_host == "localhost"

    def test_server_port_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_transport.server_port == 8678

    def test_enable_websockets_default(self) -> None:
        settings = SessionBuddySettings()
        assert settings.mcp_transport.enable_websockets is True

    def test_custom_port(self) -> None:
        settings = SessionBuddySettings(
            mcp_transport=MCPTransportConfig(server_port=9000),
        )
        assert settings.mcp_transport.server_port == 9000


class TestIntegratedConstruction:
    """Test multi-group construction in one ``SessionBuddySettings`` call."""

    def test_all_settings_together(self) -> None:
        # ``debug: True`` at the root flows through the
        # ``_map_legacy_debug_flag`` model_validator to populate
        # ``mcp_server.enable_debug_mode``.
        settings = SessionBuddySettings.model_validate(
            {
                "debug": True,
                "mcp_server": {"server_name": "Custom"},
                "tokens": {
                    "enable_token_optimization": True,
                    "default_max_tokens": 8000,
                },
                "search": {"enable_semantic_search": False},
                "database": {"max_connections": 20},
            }
        )
        assert settings.mcp_server.server_name == "Custom"
        assert settings.mcp_server.enable_debug_mode is True
        assert settings.tokens.enable_token_optimization is True
        assert settings.tokens.default_max_tokens == 8000
        assert settings.search.enable_semantic_search is False
        assert settings.database.max_connections == 20

    def test_default_construction_returns_correct_types(self) -> None:
        """Each nested group has the expected type on the default
        ``SessionBuddySettings()`` instance.
        """
        settings = SessionBuddySettings()
        assert isinstance(settings.mcp_server, ServerIdentityConfig)
        assert isinstance(settings.mcp_transport, MCPTransportConfig)
        assert isinstance(settings.paths, PathsConfig)
        assert isinstance(settings.database, DatabaseConfig)
        assert isinstance(settings.multi_project, MultiProjectConfig)
        assert isinstance(settings.search, SearchConfig)
        assert isinstance(settings.tokens, TokensConfig)
        assert isinstance(settings.session, SessionConfig)
        assert isinstance(
            settings.conversation_storage, ConversationStorageConfig
        )
        assert isinstance(
            settings.reflection_auto_store, ReflectionAutoStoreConfig
        )
        assert isinstance(settings.integrations, IntegrationsConfig)
        assert isinstance(settings.git_maintenance, GitMaintenanceConfig)
        assert isinstance(settings.prometheus, PrometheusConfig)
        assert isinstance(settings.logging, LoggingConfig)
        assert isinstance(settings.security, SecurityConfig)
        assert isinstance(settings.llm, LLMConfig)
        assert isinstance(settings.feature_flags, FeatureFlagsConfig)
        assert isinstance(settings.cloud_sync, AkoshaSyncConfig)
