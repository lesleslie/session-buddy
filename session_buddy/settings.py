"""MCPBaseSettings-based configuration for Session Buddy MCP Server.

Configuration Loading:
    Settings are loaded with layered priority (highest to lowest):
    1. Environment variables SESSION_BUDDY_*
    2. settings/local.yaml (local overrides, gitignored)
    3. settings/session-buddy.yaml (base configuration)
    4. Defaults from this class (lowest)

Settings Directory Structure:
    settings/
    ├── session-buddy.yaml   # Base configuration (committed)
    └── local.yaml           # Local overrides (gitignored)
"""

from __future__ import annotations

import os
import typing as t
from pathlib import Path

from oneiric.core.config import OneiricMCPConfig
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# Oneiric-shaped schema (SessionBuddySettings) — nested *Config groups
#
# Added 2026-10-04 alongside the legacy SessionMgmtSettings. Every leaf
# group extends ``_BaseConfig`` (extra="forbid") to enforce the
# Oneiric/Mahavishnu typo-rejection policy. Group names follow the
# ``<Domain>Config`` convention used by MahavishnuSettings.
# ============================================================================


class _BaseConfig(BaseModel):
    """Base for every nested ``*Config`` group.

    Adds the Oneiric/Mahavishnu ``extra="forbid"`` policy so a typo'd
    YAML key raises a parse error at startup rather than silently
    being ignored. The policy lives here rather than on the root
    class (which uses ``extra="allow"``) so Oneiric's framework
    groups (``app``/``adapters``/...) can still flow through the
    loader filter unchanged.
    """

    model_config = ConfigDict(extra="forbid")


class LLMApiKeysConfig(_BaseConfig):
    """Per-provider LLM API keys.

    All fields default to ``None`` because providers may be unset; only
    ``llm/security.py`` and ``llm_providers.py`` should reach into
    this group. Each key is read via the OneiricSettings env-var
    pattern (e.g. ``SESSION_BUDDY_LLM__API_KEYS__MINIMAX``).
    """

    openai: str | None = Field(default=None, description="OpenAI API key")
    anthropic: str | None = Field(
        default=None, description="Anthropic API key"
    )
    gemini: str | None = Field(default=None, description="Google Gemini API key")
    qwen: str | None = Field(default=None, description="Qwen API key")
    minimax: str | None = Field(
        default=None, description="MiniMax API key (primary cloud LLM)"
    )
    zai: str | None = Field(default=None, description="Z.AI API key")


class LLMConfig(_BaseConfig):
    """LLM provider configuration (consolidated). Absorbs the legacy
    ``LLMProvidersConfig`` and the flat ``minimax_*`` / ``zai_*`` /
    ``llama_server_model`` / ``default_llm_provider`` / ``llm_fallback_chain``
    fields. Nested ``api_keys`` follows the Mahavishnu
    ``AgnoAdapterConfig.llm: AgnoLLMConfig`` precedent.
    """

    # Primary + fallback chain
    default_provider: t.Literal[
        "minimax", "zai", "openai", "gemini", "ollama", "llama_server"
    ] = Field(default="minimax", description="Primary LLM provider")
    fallback_providers: list[str] = Field(
        default_factory=lambda: ["minimax", "llama_server", "ollama"],
        description="Ordered fallback chain",
    )

    # Provider endpoints and default models
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL",
    )
    ollama_default_model: str = Field(
        default="qwen2.5-coder:7b",
        description="Default Ollama model",
    )
    # NOTE (2026-09-27 audit): ``llama_server_base_url`` had no consumer in
    # the Bodai ecosystem — the actual llama.cpp URL is read via the
    # ``LLAMA_SERVER_URL`` env var at runtime (see
    # ``mahavishnu/workers/cloud_worker.py`` and
    # ``crackerjack/crackerjack/adapters/ai/unified.py``). Same dead-on-arrival
    # pattern as Crackerjack's removed ``ai.llama_server_url``. Removed.
    llama_server_default_model: str = Field(
        default="qwen3.5",
        description="Default llama-server model",
    )
    llama_server_model: str = Field(
        default="qwen3.5",
        description="Default llama.cpp model (flat duplicate; canonical is llama_server_default_model)",
    )
    minimax_base_url: str = Field(
        default="https://api.minimax.io/v1",
        description="MiniMax API base URL",
    )
    minimax_default_model: str = Field(
        default="MiniMax-M2.7",
        description="Default MiniMax model",
    )
    zai_base_url: str = Field(
        default="https://api.z.ai/api/coding/paas/v4",
        description="Z.AI base URL",
    )
    zai_default_model: str = Field(
        default="glm-4.7",
        description="Default Z.AI model",
    )

    # Provider-specific API keys
    api_keys: LLMApiKeysConfig = Field(
        default_factory=LLMApiKeysConfig,
        description="Per-provider API keys",
    )


class ServerIdentityConfig(_BaseConfig):
    """MCP server identity + log level.

    Renamed from the flat ``server_name`` / ``server_description`` /
    ``log_level`` / ``enable_debug_mode`` cluster.
    """

    server_name: str = Field(
        default="Session Buddy MCP",
        description="Display name for the MCP server",
    )
    server_description: str = Field(
        default="Session management and tooling MCP server",
        description="Brief description of server functionality",
    )
    log_level: t.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging verbosity",
    )
    enable_debug_mode: bool = Field(
        default=False,
        description="Enable debug features (verbose logging, additional validation)",
    )


class MCPTransportConfig(_BaseConfig):
    """MCP transport layer.

    The fields on this group correspond to the HTTP/WS endpoints the
    MCP server exposes. Note that ``http_port`` / ``http_host`` /
    ``enable_http_transport`` stay on the root
    ``OneiricMCPConfig`` class (not nested) because they predate the
    nested convention and are read by mcp-common's factory directly.
    """

    server_host: str = Field(
        default="localhost",
        description="MCP server bind host",
    )
    server_port: int = Field(
        default=8678,
        ge=1024,
        le=65535,
        description="MCP server bind port",
    )
    enable_websockets: bool = Field(
        default=True,
        description="Enable WebSocket transport",
    )


class PathsConfig(_BaseConfig):
    """Filesystem path settings.

    Expands ``~`` on load via ``@field_validator``. ``data_dir`` and
    ``log_dir`` are the parent directories that ``database.path`` and
    ``log_file_path`` may resolve relative to.
    """

    data_dir: Path = Field(
        default=Path("~/.claude/data"),
        description="Base data directory",
    )
    log_dir: Path = Field(
        default=Path("~/.claude/logs"),
        description="Base log directory",
    )
    global_workspace_path: Path = Field(
        default=Path("~/Projects/claude"),
        description="Global workspace path",
    )
    log_file_path: Path = Field(
        default=Path("~/.claude/logs/session-buddy.log"),
        description="Log file path",
    )

    @field_validator(
        "data_dir", "log_dir", "global_workspace_path", "log_file_path"
    )
    @classmethod
    def _expand_user_paths(cls, v: Path | str) -> Path:
        """Expand ``~`` to home directory."""
        path = v if isinstance(v, Path) else Path(v)
        return Path(os.path.expanduser(str(path)))


class DatabaseConfig(_BaseConfig):
    """DuckDB connection settings."""

    path: Path = Field(
        default=Path("~/.claude/data/reflection.duckdb"),
        description="Path to the DuckDB database file",
    )
    connection_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Database connection timeout in seconds",
    )
    query_timeout: int = Field(
        default=120,
        ge=1,
        le=3600,
        description="Database query timeout in seconds",
    )
    max_connections: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of database connections",
    )

    @field_validator("path")
    @classmethod
    def _expand_path(cls, v: Path | str) -> Path:
        return Path(os.path.expanduser(str(v)))


class MultiProjectConfig(_BaseConfig):
    """Multi-project coordination."""

    enable_multi_project: bool = Field(
        default=True,
        description="Enable multi-project coordination features",
    )
    auto_detect_projects: bool = Field(
        default=True,
        description="Auto-detect project relationships",
    )
    project_groups_enabled: bool = Field(
        default=True,
        description="Enable project grouping functionality",
    )


class SearchConfig(_BaseConfig):
    """Database search and embedding settings."""

    enable_full_text_search: bool = Field(
        default=True,
        description="Enable full-text search capabilities",
    )
    search_index_update_interval: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Search index update interval (seconds)",
    )
    max_search_results: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum search results returned",
    )
    enable_semantic_search: bool = Field(
        default=True,
        description="Enable semantic search capabilities",
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence-transformers embedding model",
    )
    embedding_cache_size: int = Field(
        default=1000,
        ge=10,
        le=100000,
        description="Embedding cache size",
    )
    enable_faceted_search: bool = Field(
        default=True,
        description="Enable faceted search",
    )
    max_facet_values: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum facet values per facet",
    )
    enable_search_suggestions: bool = Field(
        default=True,
        description="Enable search suggestions",
    )
    suggestion_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum suggestions per query",
    )
    enable_stemming: bool = Field(
        default=True,
        description="Enable query stemming",
    )
    enable_fuzzy_matching: bool = Field(
        default=True,
        description="Enable fuzzy matching",
    )
    fuzzy_threshold: float = Field(
        default=0.8,
        ge=0.1,
        le=1.0,
        description="Fuzzy match threshold (0.0-1.0)",
    )


class TokensConfig(_BaseConfig):
    """Token optimization and usage tracking."""

    enable_token_optimization: bool = Field(
        default=True,
        description="Enable token optimization",
    )
    default_max_tokens: int = Field(
        default=4000,
        ge=100,
        le=200000,
        description="Default max tokens per response",
    )
    default_chunk_size: int = Field(
        default=2000,
        ge=50,
        le=100000,
        description="Default chunk size for streaming",
    )
    optimization_strategy: str = Field(
        default="auto",
        description="Token optimization strategy (auto|fixed|adaptive)",
    )
    enable_response_chunking: bool = Field(
        default=True,
        description="Enable response chunking",
    )
    enable_duplicate_filtering: bool = Field(
        default=True,
        description="Enable duplicate-message filtering",
    )
    track_token_usage: bool = Field(
        default=True,
        description="Track token usage in storage",
    )
    usage_retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Token usage retention in days",
    )


class SessionConfig(_BaseConfig):
    """Checkpoint, auto-commit, and session lifecycle."""

    auto_checkpoint_interval: int = Field(
        default=1800,
        ge=60,
        le=86400,
        description="Auto-checkpoint interval (seconds)",
    )
    midpoint_commits_enabled: bool = Field(
        default=False,
        description="Enable midpoint commits during long sessions",
    )
    midpoint_commit_min_quality_delta: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Minimum quality delta to trigger midpoint commit",
    )
    midpoint_commit_interval_s: int = Field(
        default=600,
        ge=60,
        le=86400,
        description="Midpoint commit interval (seconds)",
    )
    enable_auto_commit: bool = Field(
        default=True,
        description="Enable auto-commit on checkpoint",
    )
    commit_message_template: str = Field(
        default="checkpoint: Session checkpoint - {timestamp}",
        min_length=10,
        description="Commit message template (must include {timestamp})",
    )
    enable_permission_system: bool = Field(
        default=True,
        description="Enable permission system",
    )
    default_trusted_operations: list[str] = Field(
        default_factory=lambda: ["git_commit", "uv_sync", "file_operations"],
        description="Default trusted operations",
    )
    auto_cleanup_old_sessions: bool = Field(
        default=True,
        description="Auto-cleanup old sessions",
    )
    session_retention_days: int = Field(
        default=365,
        ge=1,
        le=3650,
        description="Session retention in days",
    )

    @field_validator("commit_message_template")
    @classmethod
    def _validate_commit_template(cls, v: str) -> str:
        """Ensure commit message template contains timestamp placeholder."""
        if "{timestamp}" not in v:
            msg = "Commit message template must contain {timestamp} placeholder"
            raise ValueError(msg)
        return v


class ConversationStorageConfig(_BaseConfig):
    """Conversation auto-storage settings."""

    enable_conversation_storage: bool = Field(
        default=True,
        description="Enable conversation auto-storage",
    )
    conversation_storage_min_length: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Minimum conversation length to store",
    )
    conversation_storage_max_length: int = Field(
        default=50000,
        ge=1000,
        le=1000000,
        description="Maximum conversation length to store",
    )
    auto_store_conversations_on_checkpoint: bool = Field(
        default=True,
        description="Auto-store conversations at checkpoints",
    )
    auto_store_conversations_on_session_end: bool = Field(
        default=True,
        description="Auto-store conversations at session end",
    )


class ReflectionAutoStoreConfig(_BaseConfig):
    """Reflection auto-store settings.

    The thresholds were lowered in 2026-09 from 90 → 70 to capture
    more sessions. See commit history for the rationale.
    """

    enable_auto_store_reflections: bool = Field(
        default=True,
        description="Enable reflection auto-store",
    )
    auto_store_quality_delta_threshold: int = Field(
        default=10,
        ge=5,
        le=50,
        description="Minimum quality delta to trigger auto-store",
    )
    auto_store_exceptional_quality_threshold: int = Field(
        default=70,
        ge=70,
        le=100,
        description="Quality threshold for exceptional auto-store",
    )
    auto_store_manual_checkpoints: bool = Field(
        default=True,
        description="Auto-store at manual checkpoints",
    )
    auto_store_session_end: bool = Field(
        default=True,
        description="Auto-store at session end",
    )


class IntegrationsConfig(_BaseConfig):
    """External tool integrations.

    Note: ``enable_crackerjack_fallback`` lives in
    ``FeatureFlagsConfig`` (the toggle belongs to the feature-flag
    surface, not to integration config).
    """

    enable_crackerjack: bool = Field(
        default=True,
        description="Enable Crackerjack code quality integration",
    )
    crackerjack_command: str = Field(
        default="crackerjack",
        min_length=1,
        description="Command to run Crackerjack",
    )
    enable_git_integration: bool = Field(
        default=True,
        description="Enable git integration",
    )
    git_auto_stage: bool = Field(
        default=False,
        description="Auto-stage checkpoint files",
    )


class GitMaintenanceConfig(_BaseConfig):
    """Git gc scheduling."""

    git_auto_gc: bool = Field(
        default=True,
        description="Enable automatic git gc during checkpoints",
    )
    git_gc_prune_delay: str = Field(
        default="2.weeks",
        min_length=2,
        description="Git gc prune delay (e.g. 2.weeks, 1.month)",
    )
    git_gc_auto_threshold: int = Field(
        default=6700,
        ge=100,
        le=50000,
        description="Loose-object threshold to trigger gc",
    )
    git_gc_only_when_clean: bool = Field(
        default=True,
        description="Only run gc when no git op is in progress",
    )

    @field_validator("git_gc_prune_delay")
    @classmethod
    def _validate_prune_delay(cls, v: str) -> str:
        """Allowlist safe prune delay formats."""
        import re
        import warnings

        safe_patterns = [
            r"^\d+\.(seconds?|minutes?|hours?|days?|weeks?|months?|years?)$",
            r"^(now|never)$",
        ]
        for pattern in safe_patterns:
            if re.match(pattern, v, re.IGNORECASE):
                if v.lower() == "now":
                    warnings.warn(
                        "git_gc_prune_delay set to 'now' - this can cause "
                        "permanent data loss! Consider using '2.weeks' or "
                        "'1.month' instead.",
                        stacklevel=2,
                    )
                return v
        msg = (
            f"Invalid git_gc_prune_delay '{v}'. "
            "Must be in format '<number>.<unit>' (e.g. '2.weeks') or 'now'."
        )
        raise ValueError(msg)


class PrometheusConfig(_BaseConfig):
    """Prometheus metrics exporter."""

    enable_prometheus_metrics: bool = Field(
        default=True,
        description="Enable Prometheus metrics",
    )
    prometheus_metrics_port: int = Field(
        default=9090,
        ge=1024,
        le=65535,
        description="Prometheus exporter port",
    )
    prometheus_metrics_path: str = Field(
        default="/metrics",
        min_length=1,
        description="Prometheus metrics path",
    )


class DevelopmentConfig(_BaseConfig):
    """Development-mode toggles."""

    enable_hot_reload: bool = Field(
        default=False,
        description="Enable hot reload (development only)",
    )


class LoggingConfig(_BaseConfig):
    """File logging + performance instrumentation."""

    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        min_length=10,
        description="Log message format string",
    )
    enable_file_logging: bool = Field(
        default=True,
        description="Enable file logging",
    )
    log_file_max_size: int = Field(
        default=10485760,
        ge=1024,
        le=1073741824,
        description="Log file max size (bytes)",
    )
    log_file_backup_count: int = Field(
        default=5,
        ge=0,
        le=100,
        description="Log file backup count",
    )
    enable_performance_logging: bool = Field(
        default=False,
        description="Enable performance logging",
    )
    log_slow_queries: bool = Field(
        default=True,
        description="Log slow queries",
    )
    slow_query_threshold: float = Field(
        default=1.0,
        ge=0.1,
        le=60,
        description="Slow query threshold (seconds)",
    )


class SecurityConfig(_BaseConfig):
    """Rate limits, query size limits, path anonymization."""

    anonymize_paths: bool = Field(
        default=False,
        description="Anonymize paths in logs",
    )
    enable_rate_limiting: bool = Field(
        default=True,
        description="Enable rate limiting",
    )
    max_requests_per_minute: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Max requests per minute per client",
    )
    max_query_length: int = Field(
        default=10000,
        ge=100,
        le=1000000,
        description="Max query length (chars)",
    )
    max_content_length: int = Field(
        default=1000000,
        ge=1000,
        le=100000000,
        description="Max content length (chars)",
    )


class EntityExtractionConfig(_BaseConfig):
    """LLM entity extraction knobs. Renamed from the legacy flat
    ``enable_llm_entity_extraction`` + ``llm_extraction_timeout`` +
    ``llm_extraction_retries`` cluster.
    """

    enable: bool = Field(
        default=True,
        description="Enable LLM entity extraction (legacy: enable_llm_entity_extraction)",
    )
    timeout: int = Field(
        default=10,
        ge=1,
        le=120,
        description="LLM extraction timeout (seconds; legacy: llm_extraction_timeout)",
    )
    retries: int = Field(
        default=1,
        ge=0,
        le=3,
        description="LLM extraction retries (legacy: llm_extraction_retries)",
    )


class FeatureFlagsConfig(_BaseConfig):
    """Per-feature toggles.

    Holds the runtime feature flags that gate Memori-inspired
    capabilities and the staged-rollout plan. Each flag has its own
    ``SESSION_BUDDY_ENABLE_*`` env-var override (see
    ``config/feature_flags.py:_get_env_bool``).
    """

    enable_anthropic: bool = Field(default=False)
    enable_ollama: bool = Field(default=False)
    enable_conscious_agent: bool = Field(default=False)
    enable_filesystem_extraction: bool = Field(default=False)
    enable_crackerjack_fallback: bool = Field(
        default=False,
        description="Enable Crackerjack CLI fallback layer when metrics are missing",
    )


class FilesystemExtractionConfig(_BaseConfig):
    """Filesystem extraction knobs (kept co-located with the
    ``enable_filesystem_extraction`` toggle in FeatureFlagsConfig
    per the architectural review of 2026-10-04).
    """

    dedupe_ttl_seconds: int = Field(
        default=120,
        ge=10,
        le=3600,
        description="Dedupe TTL for filesystem extraction",
    )
    max_file_size_bytes: int = Field(
        default=1000000,
        ge=10000,
        le=100000000,
        description="Max file size for extraction",
    )
    ignore_dirs: list[str] = Field(
        default_factory=lambda: [
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
        ],
        description="Directories to ignore during extraction",
    )


class AkoshaSyncConfig(_BaseConfig):
    """Cloud sync settings for the Akosha intelligence component.

    Renamed from ``CloudSyncConfig`` per the plan; matches the
    ``akosha_config.py:from_settings()`` factory that strips the
    ``akosha_`` prefix.
    """

    cloud_bucket: str = Field(default="", description="Akosha cloud bucket name")
    cloud_endpoint: str = Field(default="", description="Akosha cloud endpoint")
    cloud_region: str = Field(default="auto", description="Akosha cloud region")
    system_id: str = Field(default="", description="Akosha system identifier")
    upload_on_session_end: bool = Field(
        default=True, description="Upload to Akosha on session end"
    )
    enable_fallback: bool = Field(
        default=True, description="Enable Akosha upload fallback"
    )
    force_method: t.Literal["auto", "sync", "async"] = Field(
        default="auto", description="Force upload method"
    )
    upload_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Akosha upload timeout (seconds)",
    )
    max_retries: int = Field(
        default=3, ge=0, le=10, description="Akosha upload max retries"
    )
    retry_backoff_seconds: float = Field(
        default=2.0,
        ge=0.1,
        le=60,
        description="Akosha upload retry backoff (seconds)",
    )
    enable_compression: bool = Field(
        default=True, description="Enable Akosha upload compression"
    )
    enable_deduplication: bool = Field(
        default=True, description="Enable Akosha upload deduplication"
    )
    chunk_size_mb: int = Field(
        default=5, ge=1, le=100, description="Akosha upload chunk size (MB)"
    )


class BodaiEventsConfig(_BaseConfig):
    """Bodai task-system event bus settings.

    Migrated from ``BaseModel`` to ``_BaseConfig`` so the
    ``extra="forbid"`` policy applies here too. The legacy
    BodaiEventsConfig used ``BaseModel`` directly.

    Consumed by ``_lifespan_with_dhara_cleanup`` (session_buddy/mcp/server.py)
    to construct the singleton ``BodaiEventsPublisher``.
    """

    enabled: bool = Field(
        default=True,
        description="Enable the bodai:events Redis Streams publisher",
    )
    stream: str = Field(
        default="bodai:events",
        description="Redis Streams name for bodai task events",
    )
    consumer_group: str = Field(
        default="bodai-default",
        description="Consumer group name for bodai:events consumers",
    )


class LLMProvidersConfig(BaseModel):
    """LLM provider configuration."""

    default_provider: t.Literal[
        "minimax", "zai", "openai", "gemini", "ollama", "llama_server"
    ] = Field(default="minimax", description="Primary LLM provider")
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL",
    )
    ollama_default_model: str = Field(
        default="qwen2.5-coder:7b",
        description="Default Ollama model",
    )
    # NOTE (2026-09-27 audit): ``llama_server_base_url`` had no consumer in
    # the Bodai ecosystem — the actual llama.cpp URL is read via the
    # ``LLAMA_SERVER_URL`` env var at runtime (see
    # ``mahavishnu/workers/cloud_worker.py`` and
    # ``crackerjack/crackerjack/adapters/ai/unified.py``). Same dead-on-arrival
    # pattern as Crackerjack's removed ``ai.llama_server_url``. Removed.
    llama_server_default_model: str = Field(
        default="qwen3.5",
        description="Default llama-server model",
    )
    fallback_providers: list[str] = Field(
        default_factory=lambda: ["minimax", "llama_server", "ollama"],
        description="Ordered list of LLM providers for fallback",
    )


class SessionMgmtSettings(OneiricMCPConfig):
    """Unified MCPBaseSettings for session-buddy.

    All configuration consolidated into a single flat structure
    for Oneiric/mcp-common compatibility and simplicity.
    """

    # === LLM Provider Configuration ===
    llm_providers: LLMProvidersConfig = Field(
        default_factory=LLMProvidersConfig,
        description="LLM provider configuration",
    )

    # === Core MCP settings ===
    server_name: str = Field(
        default="Session Buddy MCP",
        description="Display name for the MCP server",
    )
    server_description: str = Field(
        default="Session management and tooling MCP server",
        description="Brief description of server functionality",
    )
    log_level: t.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    enable_debug_mode: bool = Field(
        default=False,
        description="Enable debug features (verbose logging, additional validation)",
    )

    # === Core Paths ===
    data_dir: Path = Field(
        default=Path("~/.claude/data"),
        description="Base data directory",
    )
    log_dir: Path = Field(
        default=Path("~/.claude/logs"),
        description="Base log directory",
    )

    # === Database Settings ===
    database_path: Path = Field(
        default=Path("~/.claude/data/reflection.duckdb"),
        description="Path to the DuckDB database file",
    )
    database_connection_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Database connection timeout in seconds",
    )
    database_query_timeout: int = Field(
        default=120,
        ge=1,
        le=3600,
        description="Database query timeout in seconds",
    )
    database_max_connections: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of database connections",
    )

    # Multi-project settings
    enable_multi_project: bool = Field(
        default=True,
        description="Enable multi-project coordination features",
    )
    auto_detect_projects: bool = Field(
        default=True,
        description="Auto-detect project relationships",
    )
    project_groups_enabled: bool = Field(
        default=True,
        description="Enable project grouping functionality",
    )

    # Database search settings
    enable_full_text_search: bool = Field(
        default=True,
        description="Enable full-text search capabilities",
    )
    search_index_update_interval: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Search index update interval in seconds",
    )
    max_search_results: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum number of search results to return",
    )

    # === Search Settings ===
    enable_semantic_search: bool = Field(
        default=True,
        description="Enable semantic search using embeddings",
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Embedding model for semantic search",
    )
    embedding_cache_size: int = Field(
        default=1000,
        ge=10,
        le=100000,
        description="Number of embeddings to cache in memory",
    )

    # Advanced search
    enable_faceted_search: bool = Field(
        default=True,
        description="Enable faceted search capabilities",
    )
    max_facet_values: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of facet values to return",
    )
    enable_search_suggestions: bool = Field(
        default=True,
        description="Enable search suggestions and autocomplete",
    )
    suggestion_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of search suggestions",
    )
    enable_stemming: bool = Field(
        default=True,
        description="Enable word stemming in search",
    )
    enable_fuzzy_matching: bool = Field(
        default=True,
        description="Enable fuzzy matching for typos",
    )
    fuzzy_threshold: float = Field(
        default=0.8,
        ge=0.1,
        le=1.0,
        description="Fuzzy matching similarity threshold",
    )

    # === Token Optimization Settings ===
    enable_token_optimization: bool = Field(
        default=True,
        description="Enable token optimization features",
    )
    default_max_tokens: int = Field(
        default=4000,
        ge=100,
        le=200000,
        description="Default maximum tokens for responses",
    )
    default_chunk_size: int = Field(
        default=2000,
        ge=50,
        le=100000,
        description="Default chunk size for response splitting",
    )
    optimization_strategy: str = Field(
        default="auto",
        description="Preferred optimization strategy (auto, truncate_old, summarize_content, compress)",
    )
    enable_response_chunking: bool = Field(
        default=True,
        description="Enable automatic response chunking for large outputs",
    )
    enable_duplicate_filtering: bool = Field(
        default=True,
        description="Filter out duplicate content in responses",
    )
    track_token_usage: bool = Field(
        default=True,
        description="Track token usage statistics",
    )
    usage_retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Number of days to retain usage statistics",
    )

    # === Session Management Settings ===
    auto_checkpoint_interval: int = Field(
        default=1800,
        ge=60,
        le=86400,
        description="Auto-checkpoint interval in seconds (default: 30 minutes)",
    )
    midpoint_commits_enabled: bool = Field(
        default=False,
        description=(
            "Enable mid-task checkpoint commits (in addition to analytics snapshots). "
            "Default off for noise control; opt-in for autonomous/subagent-heavy workflows. "
            "When enabled, midpoint_commit_interval_s replaces auto_checkpoint_interval."
        ),
    )
    midpoint_commit_min_quality_delta: int = Field(
        default=10,
        ge=1,
        le=50,
        description=(
            "Minimum quality score delta between ticks before a midpoint commit fires. "
            "Inactive when no quality source is configured."
        ),
    )
    midpoint_commit_interval_s: int = Field(
        default=600,  # 10 min when commits enabled
        ge=60,
        le=86400,
        description=(
            "Mid-task checkpoint interval in seconds when midpoint_commits_enabled=True. "
            "Defaults to 600 (10 min) vs. 1800 (30 min) for analytics-only."
        ),
    )
    enable_auto_commit: bool = Field(
        default=True,
        description="Enable automatic git commits during checkpoints",
    )
    commit_message_template: str = Field(
        default="checkpoint: Session checkpoint - {timestamp}",
        min_length=10,
        description="Template for automatic commit messages",
    )
    enable_permission_system: bool = Field(
        default=True,
        description="Enable the permission system for trusted operations",
    )
    default_trusted_operations: list[str] = Field(
        default_factory=lambda: ["git_commit", "uv_sync", "file_operations"],
        description="List of operations that are trusted by default",
    )
    auto_cleanup_old_sessions: bool = Field(
        default=True,
        description="Automatically clean up old session data",
    )
    session_retention_days: int = Field(
        default=365,
        ge=1,
        le=3650,
        description="Number of days to retain session data",
    )

    # Selective auto-store
    enable_auto_store_reflections: bool = Field(
        default=True,
        description="Enable automatic reflection storage at meaningful checkpoints",
    )
    auto_store_quality_delta_threshold: int = Field(
        default=10,
        ge=5,
        le=50,
        description="Minimum quality score change to trigger auto-store",
    )
    auto_store_exceptional_quality_threshold: int = Field(
        default=90,
        ge=70,
        le=100,
        description="Quality score threshold for exceptional sessions",
    )
    auto_store_manual_checkpoints: bool = Field(
        default=True,
        description="Always store reflections for manually-triggered checkpoints",
    )
    auto_store_session_end: bool = Field(
        default=True,
        description="Always store reflections at session end",
    )

    # === Conversation Storage Settings ===
    enable_conversation_storage: bool = Field(
        default=True,
        description="Enable automatic conversation storage at checkpoints",
    )
    conversation_storage_min_length: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Minimum conversation length to store (characters)",
    )
    conversation_storage_max_length: int = Field(
        default=50000,
        ge=1000,
        le=1000000,
        description="Maximum conversation length before truncation (characters)",
    )
    auto_store_conversations_on_checkpoint: bool = Field(
        default=True,
        description="Automatically store conversations at checkpoints",
    )
    auto_store_conversations_on_session_end: bool = Field(
        default=True,
        description="Automatically store conversations at session end",
    )

    # === Integration Settings ===
    # NOTE (2026-10-04): the obsolete ``dhara_url`` field was removed.
    # The Dhara URL is now read exclusively from the
    # ``SESSION_BUDDY_DHARA_URL`` environment variable in
    # ``channel_tracking_tools._make_dhara_publisher()``.
    enable_crackerjack: bool = Field(
        default=True,
        description="Enable Crackerjack code quality integration",
    )
    enable_crackerjack_fallback: bool = Field(
        default=False,
        description="Enable the Crackerjack CLI fallback layer when metrics are missing (opt-in; default off)",
    )
    crackerjack_command: str = Field(
        default="crackerjack",
        min_length=1,
        description="Command to run Crackerjack",
    )
    enable_git_integration: bool = Field(
        default=True,
        description="Enable Git integration features",
    )
    git_auto_stage: bool = Field(
        default=False,
        description="Automatically stage changes before commits",
    )

    # === Git Maintenance Settings ===
    git_auto_gc: bool = Field(
        default=True,
        description="Enable automatic git garbage collection during checkpoints",
    )
    git_gc_prune_delay: str = Field(
        default="2.weeks",
        min_length=2,
        description="Prune delay for git gc (e.g., 'now', '2.weeks', '1.month') - Git default is 2 weeks",
    )
    git_gc_auto_threshold: int = Field(
        default=6700,
        ge=100,
        le=50000,
        description="Loose object threshold to trigger automatic gc (Git default: 6700)",
    )
    git_gc_only_when_clean: bool = Field(
        default=True,
        description="Only run git gc when no git operation (rebase, merge, bisect) is in progress",
    )
    global_workspace_path: Path = Field(
        default=Path("~/Projects/claude"),
        description="Path to global workspace directory",
    )
    # NOTE (2026-09-27 audit): ``enable_global_toolkits`` had no consumer in
    # the Bodai ecosystem — only set as a fixture attribute in
    # ``tests/conftest.py`` (``mock_settings_instance.enable_global_toolkits = True``),
    # not read by any runtime code path. Removed.

    # === Prometheus Metrics Settings ===
    enable_prometheus_metrics: bool = Field(
        default=True,
        description="Enable Prometheus metrics collection",
    )
    prometheus_metrics_port: int = Field(
        default=9090,
        ge=1024,
        le=65535,
        description="Port for Prometheus metrics endpoint",
    )
    prometheus_metrics_path: str = Field(
        default="/metrics",
        min_length=1,
        description="Path for Prometheus metrics endpoint",
    )

    # === LLM API Keys (optional, overrides env vars) ===
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key (overrides OPENAI_API_KEY)",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key (overrides ANTHROPIC_API_KEY)",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Gemini API key (overrides GEMINI_API_KEY/GOOGLE_API_KEY)",
    )
    qwen_api_key: str | None = Field(
        default=None,
        description="Qwen API key (overrides QWEN_API_KEY)",
    )
    minimax_api_key: str | None = Field(
        default=None,
        description="MiniMax API key (overrides MINIMAX_API_KEY)",
    )
    zai_api_key: str | None = Field(
        default=None,
        description="ZAI API key (overrides ZAI_API_KEY)",
    )

    # === LLM Provider URLs ===
    minimax_base_url: str = Field(
        default="https://api.minimax.io/v1",
        description="MiniMax OpenAI-compatible API endpoint",
    )
    minimax_default_model: str = Field(
        default="MiniMax-M2.7",
        description="Default MiniMax model for LLM operations",
    )
    zai_base_url: str = Field(
        default="https://api.z.ai/api/coding/paas/v4",
        description="ZAI coding plan API endpoint",
    )
    zai_default_model: str = Field(
        default="glm-4.7",
        description="Default ZAI model for LLM operations",
    )

    # === llama-server (llama.cpp) settings ===
    # NOTE (2026-09-27 audit): ``llama_server_base_url`` had no consumer in
    # the Bodai ecosystem — the actual llama.cpp URL is read via the
    # ``LLAMA_SERVER_URL`` env var at runtime (see
    # ``mahavishnu/workers/cloud_worker.py`` and
    # ``crackerjack/crackerjack/adapters/ai/unified.py``). Same dead-on-arrival
    # pattern as Crackerjack's removed ``ai.llama_server_url``. Removed.
    llama_server_model: str = Field(
        default="qwen3.5",
        description="Default model served by llama.cpp",
    )

    # === LLM Fallback Chain ===
    default_llm_provider: str = Field(
        default="minimax",
        description="Primary LLM provider (minimax, llama_server, ollama)",
    )
    llm_fallback_chain: list[str] = Field(
        default=["minimax", "llama_server", "ollama"],
        description="Ordered list of LLM providers for fallback",
    )

    # === Akosha Sync Settings ===
    akosha_cloud_bucket: str = Field(
        default="",
        description="S3/R2 bucket name for cloud sync (empty disables cloud)",
    )
    akosha_cloud_endpoint: str = Field(
        default="",
        description="S3/R2 endpoint URL (e.g., https://<account>.r2.cloudflarestorage.com)",
    )
    akosha_cloud_region: str = Field(
        default="auto",
        description="Storage region for cloud operations",
    )
    akosha_system_id: str = Field(
        default="",
        description="Unique system identifier (defaults to hostname if empty)",
    )
    akosha_upload_on_session_end: bool = Field(
        default=True,
        description="Automatically upload memories on session end",
    )
    akosha_enable_fallback: bool = Field(
        default=True,
        description="Allow cloud → HTTP fallback for sync",
    )
    akosha_force_method: t.Literal["auto", "cloud", "http"] = Field(
        default="auto",
        description="Force specific sync method (auto, cloud, http)",
    )
    akosha_upload_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Maximum time to wait for upload completion (default: 5 minutes)",
    )
    akosha_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed uploads",
    )
    akosha_retry_backoff_seconds: float = Field(
        default=2.0,
        ge=0.1,
        le=60.0,
        description="Base delay in seconds for exponential backoff",
    )
    akosha_enable_compression: bool = Field(
        default=True,
        description="Compress databases with gzip before uploading",
    )
    akosha_enable_deduplication: bool = Field(
        default=True,
        description="Skip uploads if database hasn't changed (SHA-256 comparison)",
    )
    akosha_chunk_size_mb: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Upload chunk size in MB for large files",
    )

    # === Logging Settings ===
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        min_length=10,
        description="Log message format string",
    )
    enable_file_logging: bool = Field(
        default=True,
        description="Enable logging to file",
    )
    log_file_path: Path = Field(
        default=Path("~/.claude/logs/session-buddy.log"),
        description="Path to log file",
    )
    log_file_max_size: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        le=1024 * 1024 * 1024,
        description="Maximum log file size in bytes (default: 10MB)",
    )
    log_file_backup_count: int = Field(
        default=5,
        ge=0,
        le=100,
        description="Number of backup log files to keep",
    )
    enable_performance_logging: bool = Field(
        default=False,
        description="Enable detailed performance logging",
    )
    log_slow_queries: bool = Field(
        default=True,
        description="Log slow database queries",
    )
    slow_query_threshold: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Threshold for slow query logging in seconds",
    )

    # === Security Settings ===
    anonymize_paths: bool = Field(
        default=False,
        description="Anonymize file paths in logs and data",
    )
    enable_rate_limiting: bool = Field(
        default=True,
        description="Enable rate limiting for API requests",
    )
    max_requests_per_minute: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum requests per minute per client",
    )
    max_query_length: int = Field(
        default=10000,
        ge=100,
        le=1000000,
        description="Maximum length for search queries",
    )
    max_content_length: int = Field(
        default=1000000,
        ge=1000,
        le=100000000,
        description="Maximum content length in bytes (default: 1MB)",
    )

    # === MCP Server Settings ===
    server_host: str = Field(
        default="localhost",
        description="MCP server host address",
    )
    server_port: int = Field(
        default=8678,
        ge=1024,
        le=65535,
        description="MCP server port number",
    )
    enable_websockets: bool = Field(
        default=True,
        description="Enable WebSocket support for MCP server",
    )

    # === Development Settings ===
    enable_hot_reload: bool = Field(
        default=False,
        description="Enable hot reloading during development",
    )

    # === Feature Flags (rollout) ===
    # Schema v2 is the only schema as of 2026-10-04 (V1 retired).
    enable_llm_entity_extraction: bool = Field(
        default=True,
        description="Enable multi-provider LLM entity extraction",
    )
    enable_anthropic: bool = Field(
        default=True,
        description="Enable Anthropic provider in cascade",
    )
    enable_ollama: bool = Field(
        default=False,
        description="Enable Ollama provider in cascade",
    )
    enable_conscious_agent: bool = Field(
        default=True,
        description="Enable background Conscious Agent",
    )

    # === Bodai Task System Events (Phase 1) ===
    # See ``BodaiEventsConfig`` above; consumed by the FastMCP lifespan
    # in session_buddy/mcp/server.py to construct the singleton publisher.
    bodai_events: BodaiEventsConfig = Field(
        default_factory=BodaiEventsConfig,
        description="Bodai task-system event bus configuration",
    )
    enable_filesystem_extraction: bool = Field(
        default=True,
        description="Enable filesystem-triggered entity extraction",
    )

    # === Extraction Controls ===
    llm_extraction_timeout: int = Field(
        default=10,
        ge=1,
        le=120,
        description="Timeout in seconds for LLM extraction requests",
    )
    llm_extraction_retries: int = Field(
        default=1,
        ge=0,
        le=3,
        description="Retry attempts per provider before cascading",
    )

    # === Filesystem Extraction Settings ===
    filesystem_dedupe_ttl_seconds: int = Field(
        default=120,
        ge=10,
        le=3600,
        description="Time window to skip reprocessing the same file",
    )
    filesystem_max_file_size_bytes: int = Field(
        default=1_000_000,
        ge=10_000,
        le=100_000_000,
        description="Maximum file size to consider for extraction",
    )
    filesystem_ignore_dirs: list[str] = Field(
        default_factory=lambda: [
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
        ],
        description="Directory names to ignore for extraction",
    )

    # === Field Validators ===
    @model_validator(mode="before")
    @classmethod
    def map_legacy_debug_flag(cls, data: t.Any) -> t.Any:
        """
        Map legacy 'debug' flag to 'enable_debug_mode'.

        Must be a classmethod for Pydantic v2.12.5+ compatibility.
        """
        # Handle Pydantic ValidationInfo (Protocol) objects
        # This can happen when mcp-common's MCPBaseSettings.load() method
        # processes the data through validators
        if not isinstance(data, dict):
            return data

        if "debug" in data and "enable_debug_mode" not in data:
            data = dict(data)
            data["enable_debug_mode"] = bool(data["debug"])
        return data

    @field_validator(
        "data_dir",
        "log_dir",
        "database_path",
        "log_file_path",
        "global_workspace_path",
    )
    @classmethod
    def expand_user_paths(cls, v: Path | str) -> Path:
        """Expand user paths (~ to home directory)."""
        path = v if isinstance(v, Path) else Path(v)
        return Path(os.path.expanduser(str(path)))

    @field_validator("commit_message_template")
    @classmethod
    def validate_commit_template(cls, v: str) -> str:
        """Ensure commit message template contains timestamp placeholder."""
        if "{timestamp}" not in v:
            msg = "Commit message template must contain {timestamp} placeholder"
            raise ValueError(msg)
        return v

    @field_validator("git_gc_prune_delay")
    @classmethod
    def validate_prune_delay(cls, v: str) -> str:
        """Validate git prune delay format to prevent command injection."""
        import re

        # Allowlist of safe prune delay patterns
        # Format: <number>.<timeunit> (e.g., '2.weeks', '1.month')
        # Or special values 'now' or 'never'
        safe_patterns = [
            r"^\d+\.(seconds?|minutes?|hours?|days?|weeks?|months?|years?)$",
            r"^(now|never)$",
        ]

        for pattern in safe_patterns:
            if re.match(pattern, v, re.IGNORECASE):
                # Warn about dangerous 'now' option
                if v.lower() == "now":
                    import warnings

                    warnings.warn(
                        "git_gc_prune_delay set to 'now' - this can cause permanent data loss! "
                        "Consider using '2.weeks' or '1.month' instead.",
                        stacklevel=2,
                    )
                return v

        msg = (
            f"Invalid git_gc_prune_delay '{v}'. "
            "Must be in format '<number>.<unit>' (e.g., '2.weeks', '1.month') or 'now'."
        )
        raise ValueError(msg)

    def get_api_key(self, key_name: str = "api_key") -> str:
        """Backwards-compatible method preserved from MCPBaseSettings.

        Returns the value of the named field on this instance with
        validation. Raises ValueError if the key is missing or empty.
        """
        value = getattr(self, key_name, None)
        if not isinstance(value, str) or not value.strip():
            msg = f"API key {key_name!r} is missing or empty"
            raise ValueError(msg)
        return value

    def get_api_key_secure(
        self, key_name: str = "api_key", provider: str = "default"
    ) -> str:
        """Backwards-compatible secure getter preserved from MCPBaseSettings.

        Returns the named API key after basic format validation. The
        ``provider`` arg is accepted for API parity but does not affect
        the returned value (no encryption layer in this implementation).
        """
        return self.get_api_key(key_name=key_name)

    @classmethod
    def load(
        cls,
        server_name: str,
        config_path: str | Path | None = None,
    ) -> SessionMgmtSettings:
        """Backwards-compatible classmethod preserving MCPBaseSettings.load().

        MCPBaseSettings.load read a flat YAML file (top-level keys map
        to SessionMgmtSettings fields). Oneiric's loader reads a
        nested OneiricSettings schema, so the flat fields don't
        propagate. To preserve compat, this method:

        1. Loads via oneiric.core.config.load_settings for the nested
           schema defaults.
        2. ALSO reads the flat YAML file directly (when one exists at
           ``settings/{server_name}.yaml`` or the explicit
           ``config_path``) and merges those top-level keys with
           priority over the oneiric defaults.

        Filters ``model_dump()`` to ``SessionMgmtSettings`` fields
        with non-None values so OneiricMCPConfig's inherited
        None-valued fields don't trip the type validator.
        """
        from pathlib import Path

        import yaml
        from oneiric.core.config import load_settings as _oneiric_load

        # Anchor at package install location for CWD-independent load.
        # oneiric's load_settings accepts ``project_root=`` to anchor
        # Layer 6-7 (settings/{name}.yaml, settings/local.yaml) at
        # the package directory while still honoring Layer 1-5
        # (explicit path, env vars, XDG). When the caller passes an
        # explicit ``config_path``, that's used as the explicit-config
        # layer (highest priority). Do NOT use ``path=`` as a fallback
        # for the package install — that would short-circuit the
        # explicit-config layer and disable XDG lookup at
        # ``~/.config/{project_name}/*.yaml``.
        loaded = _oneiric_load(
            path=str(config_path) if config_path else None,
            project_name=server_name,
            project_root=Path(__file__).resolve().parent.parent,
        )
        relevant_data: dict[str, t.Any] = {
            k: v
            for k, v in loaded.model_dump().items()
            if k in cls.model_fields and v is not None
        }

        # Read the flat YAML file (legacy MCPBaseSettings schema).
        # MCPBaseSettings looked at settings/{server_name}.yaml first,
        # then settings/local.yaml. We mirror that ordering.
        if config_path:
            flat_paths = [Path(config_path)]
        else:
            flat_paths = [
                Path("settings") / f"{server_name}.yaml",
                Path("settings") / "local.yaml",
            ]
        for flat_path in flat_paths:
            if not flat_path.exists():
                continue
            try:
                with flat_path.open() as f:
                    flat_data = yaml.safe_load(f)
            except OSError, yaml.YAMLError:
                continue
            if not isinstance(flat_data, dict):
                continue
            # Flat keys map directly to SessionMgmtSettings fields.
            # Nested dicts (``llm_providers:``, ``bodai_events:``,
            # ``storage:``) are merged into whatever the prior layer
            # (Oneiric or an earlier file in ``flat_paths``) put in
            # ``relevant_data[k]`` so a downstream ``local.yaml`` can
            # override individual nested keys without wiping the rest.
            # Without this, ``local.yaml``'s partial ``llm_providers``
            # block erases the committed ``ollama_base_url`` and
            # ``ollama_default_model`` (drift observed 2026-10-04).
            for k, v in flat_data.items():
                if k not in cls.model_fields or v is None:
                    continue
                if isinstance(v, dict) and isinstance(relevant_data.get(k), dict):
                    merged = dict(relevant_data[k])
                    merged.update(v)
                    relevant_data[k] = merged
                else:
                    relevant_data[k] = v

        return cls(**relevant_data)

    # --- Path helpers (migrated from MCPServerSettings) ---------------
    # OneiricMCPConfig exposes ``cache_dir`` (typed as ``str``) but not
    # the ``cache_root``-based path helpers that mcp-common's old base
    # class provided. These three methods compose the same paths on
    # top of the new ``cache_dir`` field so call sites that used to
    # read ``settings.pid_path()`` etc. keep working unchanged --
    # including the test fixtures that still pass plain
    # MCPServerSettings (whose own methods have the same callable
    # shape).

    def pid_path(self) -> Path:
        """Get PID file path (.oneiric_cache/mcp_server.pid)."""
        return Path(self.cache_dir) / "mcp_server.pid"

    def health_snapshot_path(self) -> Path:
        """Get runtime health snapshot path (.oneiric_cache/runtime_health.json)."""
        return Path(self.cache_dir) / "runtime_health.json"

    def telemetry_snapshot_path(self) -> Path:
        """Get runtime telemetry snapshot path (.oneiric_cache/runtime_telemetry.json)."""
        return Path(self.cache_dir) / "runtime_telemetry.json"

    def get_masked_key(self, key_name: str, visible_chars: int = 4) -> str:
        """Return a masked representation of the named API-key field.

        Migrated compatibility shim: ``llm/security.get_masked_api_key``
        used to call ``settings.get_masked_key(...)`` (an
        ``MCPServerSettings`` method). We replicate it on top of the
        ``MCPBaseSettings`` semantics by reading the named field and
        keeping only the trailing ``visible_chars`` characters.
        """
        raw = getattr(self, key_name, None)
        if not isinstance(raw, str) or not raw.strip():
            return "***"
        if visible_chars <= 0 or len(raw) <= visible_chars:
            return f"...{raw[-4:]}" if len(raw) >= 4 else "***"
        return f"...{raw[-visible_chars:]}"


# ============================================================================
# SessionBuddySettings — Oneiric-shaped root class
#
# Introduced 2026-10-04 as the canonical replacement for the legacy flat
# ``SessionMgmtSettings``. Composed of nested ``*Config`` groups; every
# leaf extends ``_BaseConfig`` (extra="forbid"). The root class uses
# ``extra="allow"`` (per Mahavishnu pattern) so the Oneiric loader's
# framework groups (app/adapters/services/...) can be filtered out
# cleanly without tripping validation.
# ============================================================================


class SessionBuddySettings(OneiricMCPConfig):
    """Oneiric-shaped session-buddy settings.

    Inherits ``http_port``, ``http_host``, ``enable_http_transport``,
    ``debug``, ``environment``, ``cache_dir`` from OneiricMCPConfig
    (these stay flat at the root because mcp-common reads them
    directly). Adds the 22 nested ``*Config`` groups below.

    Env-var prefix: ``SESSION_BUDDY_`` (e.g.
    ``SESSION_BUDDY_LLM__DEFAULT_PROVIDER``). The ``__`` delimiter is
    Oneiric's nested-key syntax for env overrides.
    """

    model_config = ConfigDict(
        env_prefix="SESSION_BUDDY_",
        env_nested_delimiter="__",
        extra="allow",
    )

    # === Nested groups (defined above) ===
    mcp_server: ServerIdentityConfig = Field(
        default_factory=ServerIdentityConfig,
        description="MCP server identity + log level",
    )
    mcp_transport: MCPTransportConfig = Field(
        default_factory=MCPTransportConfig,
        description="MCP transport layer",
    )
    paths: PathsConfig = Field(
        default_factory=PathsConfig,
        description="Filesystem path settings",
    )
    database: DatabaseConfig = Field(
        default_factory=DatabaseConfig,
        description="DuckDB connection settings",
    )
    multi_project: MultiProjectConfig = Field(
        default_factory=MultiProjectConfig,
        description="Multi-project coordination",
    )
    search: SearchConfig = Field(
        default_factory=SearchConfig,
        description="Database search and embeddings",
    )
    tokens: TokensConfig = Field(
        default_factory=TokensConfig,
        description="Token optimization",
    )
    session: SessionConfig = Field(
        default_factory=SessionConfig,
        description="Checkpoint, auto-commit, session lifecycle",
    )
    conversation_storage: ConversationStorageConfig = Field(
        default_factory=ConversationStorageConfig,
        description="Conversation auto-storage",
    )
    reflection_auto_store: ReflectionAutoStoreConfig = Field(
        default_factory=ReflectionAutoStoreConfig,
        description="Reflection auto-store",
    )
    integrations: IntegrationsConfig = Field(
        default_factory=IntegrationsConfig,
        description="External tool integrations",
    )
    git_maintenance: GitMaintenanceConfig = Field(
        default_factory=GitMaintenanceConfig,
        description="Git gc scheduling",
    )
    prometheus: PrometheusConfig = Field(
        default_factory=PrometheusConfig,
        description="Prometheus metrics exporter",
    )
    development: DevelopmentConfig = Field(
        default_factory=DevelopmentConfig,
        description="Development-mode toggles",
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="File logging + performance instrumentation",
    )
    security: SecurityConfig = Field(
        default_factory=SecurityConfig,
        description="Rate limits, query size limits",
    )
    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="LLM provider configuration (consolidated)",
    )
    entity_extraction: EntityExtractionConfig = Field(
        default_factory=EntityExtractionConfig,
        description="LLM entity extraction knobs",
    )
    feature_flags: FeatureFlagsConfig = Field(
        default_factory=FeatureFlagsConfig,
        description="Per-feature toggles",
    )
    filesystem_extraction: FilesystemExtractionConfig = Field(
        default_factory=FilesystemExtractionConfig,
        description="Filesystem extraction knobs",
    )
    cloud_sync: AkoshaSyncConfig = Field(
        default_factory=AkoshaSyncConfig,
        description="Cloud sync settings for Akosha",
    )
    bodai_events: BodaiEventsConfig = Field(
        default_factory=BodaiEventsConfig,
        description="Bodai task-system event bus",
    )

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_debug_flag(cls, data: t.Any) -> t.Any:
        """Map legacy ``debug`` YAML key to root ``debug``.

        Preserves the same translation that
        ``SessionMgmtSettings.map_legacy_debug_flag`` does for the
        legacy flat class — keeps operator YAMLs that use the
        shorthand ``debug: true`` working.
        """
        if not isinstance(data, dict):
            return data
        if "debug" in data and "enable_debug_mode" not in data:
            data = dict(data)
            data["enable_debug_mode"] = bool(data["debug"])
        return data

    def pid_path(self) -> Path:
        """Get PID file path (.oneiric_cache/mcp_server.pid).

        Reads ``cache_dir`` from OneiricMCPConfig; preserved here
        so the structural protocol in ``utils/runtime_snapshots`` is
        satisfied.
        """
        return Path(self.cache_dir) / "mcp_server.pid"

    def health_snapshot_path(self) -> Path:
        """Get health snapshot path (.oneiric_cache/runtime_health.json)."""
        return Path(self.cache_dir) / "runtime_health.json"

    def telemetry_snapshot_path(self) -> Path:
        """Get telemetry snapshot path (.oneiric_cache/runtime_telemetry.json)."""
        return Path(self.cache_dir) / "runtime_telemetry.json"

    def get_masked_key(self, key_name: str, visible_chars: int = 4) -> str:
        """Return a masked representation of the named API-key field.

        Migration shim: ``llm/security.get_masked_api_key`` used to
        call ``settings.get_masked_key(...)``. Reads from the nested
        ``llm.api_keys`` group when given the ``api_keys.<provider>``
        convention, falling back to flat ``getattr`` for legacy keys.
        """
        if key_name.startswith("api_keys."):
            provider = key_name.removeprefix("api_keys.")
            raw = getattr(self.llm.api_keys, provider, None)
        else:
            raw = getattr(self, key_name, None)
        if not isinstance(raw, str) or not raw.strip():
            return "***"
        if visible_chars <= 0 or len(raw) <= visible_chars:
            return f"...{raw[-4:]}" if len(raw) >= 4 else "***"
        return f"...{raw[-visible_chars:]}"

    def get_api_key(self, key_name: str = "api_key") -> str:
        """Migration shim: returns the value of the named field.

        Reads from the nested ``llm.api_keys`` group when called
        with the ``api_keys.<provider>`` key-name convention (used
        by ``get_llm_api_key``). Falls back to flat ``getattr`` for
        legacy callers that pass a bare field name.

        Raises ``ValueError`` if the key is missing or empty.
        """
        if key_name.startswith("api_keys."):
            provider = key_name.removeprefix("api_keys.")
            value = getattr(self.llm.api_keys, provider, None)
        else:
            value = getattr(self, key_name, None)
        if not isinstance(value, str) or not value.strip():
            msg = f"API key {key_name!r} is missing or empty"
            raise ValueError(msg)
        return value

    def get_api_key_secure(
        self, key_name: str = "api_key", provider: str = "default"
    ) -> str:
        """Migration shim: secure getter with provider label."""
        return self.get_api_key(key_name=key_name)

    # Shim for mcp-common compatibility: factory.py:387 calls
    # ``self.settings.cache_root`` (Path), but OneiricMCPConfig only
    # exposes ``cache_dir`` (str). Mirror the value into cache_root so
    # mcp-common's ``validate_cache_ownership`` can read it.
    @property
    def cache_root(self) -> Path:
        return Path(self.cache_dir)

    @classmethod
    def load(
        cls,
        *,
        config_path: str | Path | None = None,
    ) -> SessionBuddySettings:
        """Load via Oneiric's layered loader.

        Oneiric's loader returns a ``OneiricSettings`` whose
        ``model_dump()`` includes framework groups (app / adapters /
        services / **logging** / secrets / ...) whose shape differs
        from the session-buddy groups of the same name. ``extra=allow``
        at the root would silently keep them as ``__pydantic_extra__``,
        and ``extra=forbid`` on each leaf group rejects them outright.

        Solution: recursively filter the Oneiric dump to only the
        fields each group declares. Oneiric's ``logging.environment``
        drops at the leaf, ``llm.api_keys.minimax`` keeps only the six
        declared keys, etc.
        """
        from pathlib import Path

        from oneiric.core.config import load_settings as _oneiric_load

        loaded = _oneiric_load(
            path=str(config_path) if config_path else None,
            project_name="session-buddy",
            project_root=Path(__file__).resolve().parent.parent,
        )

        # Combine Oneiric's model_dump() with its __pydantic_extra__
        # storage. OneiricSettings is configured with extra="allow",
        # so unknown YAML keys (our session-buddy groups) survive
        # only as ``__pydantic_extra__`` and are absent from
        # model_dump(). Merge with extra winning on conflict (an
        # operator override should always beat the framework default).
        dump = dict(loaded.model_dump())
        extra = getattr(loaded, "__pydantic_extra__", None) or {}
        dump.update(extra)

        # Apply SESSION_BUDDY_ env-var overrides. OneiricSettings reads
        # env vars with its own ``env_prefix="ONEIRIC_"``; session-buddy
        # needs its own prefix, so we apply a second pass here. Nested
        # delimiter is ``__`` (matching the SessionBuddySettings
        # model_config). e.g. SESSION_BUDDY_LLM__DEFAULT_PROVIDER=zai
        # overrides dump["llm"]["default_provider"] = "zai".
        _apply_session_buddy_env_overrides(dump)

        # Recursive filter: keep only fields each declared model knows
        # about, recursing into nested BaseModel groups.
        relevant = _filter_model_dump(dump, cls)
        return cls.model_validate(relevant)


# Global settings instance
_settings: SessionBuddySettings | None = None


def _filter_model_dump(
    data: dict[str, t.Any], model_cls: t.Any
) -> dict[str, t.Any]:
    """Recursively filter a model_dump() dict to fields each declared
    BaseModel knows about. Drops unknown keys at every level so
    nested-dict collisions between Oneiric's framework groups and
    session-buddy's domain groups don't trip ``extra="forbid"``.
    """
    out: dict[str, t.Any] = {}
    for key, field_info in model_cls.model_fields.items():
        if key not in data:
            continue
        value = data[key]
        annotation = field_info.annotation
        # Pydantic v2 may store annotation as a string for forward refs
        sub_cls: t.Any = None
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            sub_cls = annotation
        if sub_cls is not None and isinstance(value, dict):
            out[key] = _filter_model_dump(value, sub_cls)
        elif sub_cls is not None and isinstance(value, list):
            # List-of-leaf: keep only the items that parse against the
            # leaf type. session-buddy has no list-of-BaseModel today
            # so this is a no-op for current schema.
            out[key] = value
        elif value is None:
            # Drop None so the dataclass default fills the field
            # (Oneiric returns None for some fields that
            # OneiricMCPConfig declares as required, e.g. ``cache_dir``).
            continue
        else:
            out[key] = value
    return out


def _apply_session_buddy_env_overrides(dump: dict[str, t.Any]) -> None:
    """Apply ``SESSION_BUDDY_*`` env overrides to ``dump`` in place.

    OneiricSettings reads env vars with its own ``env_prefix="ONEIRIC_"``
    — session-buddy needs its own prefix, so a second pass applies
    ``SESSION_BUDDY_*`` overrides here. The nested delimiter is
    ``__`` (matching SessionBuddySettings.model_config).

    Examples:
        SESSION_BUDDY_LLM__DEFAULT_PROVIDER=zai      → dump["llm"]["default_provider"]
        SESSION_BUDDY_LLM__API_KEYS__MINIMAX=sk-...  → dump["llm"]["api_keys"]["minimax"]
        SESSION_BUDDY_DATABASE__PATH=/tmp/x.db        → dump["database"]["path"]
        SESSION_BUDDY_FEATURE_FLAGS__ENABLE_CONSCIOUS_AGENT=1 → dump["feature_flags"]["enable_conscious_agent"]

    Booleans are parsed via a small truthy/falsy allowlist; other
    values are passed through as strings (Pydantic's validators
    cast at ``model_validate`` time).
    """
    prefix = "SESSION_BUDDY_"
    delim = "__"
    truthy = {"true", "1", "yes", "on"}
    falsy = {"false", "0", "no", "off"}

    for env_name, raw_value in os.environ.items():
        if not env_name.startswith(prefix):
            continue
        parts = [p.lower() for p in env_name[len(prefix):].split(delim)]
        if not parts:
            continue
        # Walk the dump dict, creating intermediate dicts as needed.
        cur = dump
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        # Cast booleans; everything else stays as string.
        v = raw_value.strip().lower()
        if v in truthy:
            value: t.Any = True
        elif v in falsy:
            value = False
        else:
            value = raw_value
        cur[parts[-1]] = value


def get_settings(reload: bool = False) -> SessionBuddySettings:
    """Get the global settings instance.

    Args:
        reload: Force reload settings from files

    Returns:
        Global SessionBuddySettings instance

    """
    global _settings

    if _settings is None or reload:
        # Delegates to SessionBuddySettings.load which uses Oneiric's
        # layered loader. The legacy SessionMgmtSettings.load is kept
        # for direct test callers and removed in Phase 6.
        _settings = SessionBuddySettings.load()

    # _settings is guaranteed non-None here
    assert _settings is not None
    return _settings


def reload_settings() -> SessionBuddySettings:
    """Force reload settings from files.

    Returns:
        Freshly loaded SessionBuddySettings instance

    """
    return get_settings(reload=True)


def get_database_path() -> Path:
    """Resolve the database path, joining with data_dir if relative.

    Reads from the nested ``database.path`` and ``paths.data_dir``
    fields of SessionBuddySettings.
    """
    settings = get_settings()
    raw = settings.database.path
    path = raw.expanduser() if isinstance(raw, Path) else Path(str(raw)).expanduser()
    if not path.is_absolute():
        data_dir_raw = settings.paths.data_dir
        data_dir = (
            data_dir_raw.expanduser()
            if isinstance(data_dir_raw, Path)
            else Path(str(data_dir_raw)).expanduser()
        )
        path = data_dir / path
    return path


def get_log_file_path() -> Path:
    """Resolve the log file path, joining with log_dir if relative.

    Reads from the nested ``paths.log_file_path`` and
    ``paths.log_dir`` fields of SessionBuddySettings.
    """
    settings = get_settings()
    raw = settings.paths.log_file_path
    path = raw.expanduser() if isinstance(raw, Path) else Path(str(raw)).expanduser()
    if not path.is_absolute():
        log_dir_raw = settings.paths.log_dir
        log_dir = (
            log_dir_raw.expanduser()
            if isinstance(log_dir_raw, Path)
            else Path(str(log_dir_raw)).expanduser()
        )
        path = log_dir / path
    return path


def get_llm_api_key(provider: str) -> str | None:
    """Look up the API key for ``provider`` from the nested
    ``llm.api_keys.<provider>`` field of SessionBuddySettings.

    Returns ``None`` if the provider is unknown or the key is unset.
    Phase 3b deduplicates the ``field_map`` literal at the 4 other
    sites that read this same data.
    """
    settings = get_settings()
    raw = getattr(settings.llm.api_keys, provider, None)
    if not isinstance(raw, str) or not raw.strip():
        return None
    if provider in ("openai", "anthropic"):
        return settings.get_api_key_secure(
            key_name=f"api_keys.{provider}", provider=provider
        )
    return settings.get_api_key(key_name=f"api_keys.{provider}")


__all__ = [
    "SessionMgmtSettings",
    "get_database_path",
    "get_llm_api_key",
    "get_log_file_path",
    "get_settings",
    "reload_settings",
]
