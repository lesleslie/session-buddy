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

from mcp_common import MCPBaseSettings
from pydantic import Field, field_validator, model_validator


class SessionMgmtSettings(MCPBaseSettings):
    """Unified MCPBaseSettings for session-buddy.

    All configuration consolidated into a single flat structure
    for Oneiric/mcp-common compatibility and simplicity.
    """

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

    # === Insights Capture Settings ===
    enable_insight_extraction: bool = Field(
        default=True,
        description="Enable automatic insight extraction from checkpoints",
    )
    insight_extraction_confidence_threshold: float = Field(
        default=0.3,
        ge=0.1,
        le=0.8,
        description="Minimum confidence score for extracted insights (0.1-0.8)",
    )
    insight_extraction_max_per_checkpoint: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum insights to extract per checkpoint",
    )
    insight_auto_prune_enabled: bool = Field(
        default=True,
        description="Enable automatic pruning of low-quality insights",
    )
    insight_prune_age_days: int = Field(
        default=90,
        ge=30,
        le=365,
        description="Days before pruning unused insights (90+ days recommended)",
    )
    insight_prune_min_quality: float = Field(
        default=0.4,
        ge=0.1,
        le=0.8,
        description="Minimum quality score to avoid pruning (0.1-0.8)",
    )
    insight_prune_min_usage: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Minimum usage count to avoid pruning (0-10 uses)",
    )

    # === Integration Settings ===
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
        description="Enable Git integration features",
    )
    git_auto_stage: bool = Field(
        default=False,
        description="Automatically stage changes before commits",
    )
    global_workspace_path: Path = Field(
        default=Path("~/Projects/claude"),
        description="Path to global workspace directory",
    )
    enable_global_toolkits: bool = Field(
        default=True,
        description="Enable global toolkit discovery and usage",
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
        default=3000,
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
    # Default to False; enable gradually and flip to True post-rollout
    use_schema_v2: bool = Field(
        default=True,
        description="Use enhanced schema v2 for memory tables",
    )
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
    def map_legacy_debug_flag(cls, data: t.Any) -> t.Any:  # type: ignore[operator]
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


# Global settings instance
_settings: SessionMgmtSettings | None = None


def get_settings(reload: bool = False) -> SessionMgmtSettings:
    """Get the global settings instance.

    Args:
        reload: Force reload settings from files

    Returns:
        Global SessionMgmtSettings instance

    """
    global _settings

    if _settings is None or reload:
        _settings = t.cast(
            "SessionMgmtSettings", SessionMgmtSettings.load("session-buddy")
        )

    # _settings is guaranteed non-None here
    assert _settings is not None
    return _settings


def reload_settings() -> SessionMgmtSettings:
    """Force reload settings from files.

    Returns:
        Freshly loaded SessionMgmtSettings instance

    """
    return get_settings(reload=True)


def get_database_path() -> Path:
    settings = get_settings()
    raw = settings.database_path
    path = raw.expanduser() if isinstance(raw, Path) else Path(str(raw)).expanduser()
    if not path.is_absolute():
        data_dir_raw = settings.data_dir
        data_dir = (
            data_dir_raw.expanduser()
            if isinstance(data_dir_raw, Path)
            else Path(str(data_dir_raw)).expanduser()
        )
        path = data_dir / path
    return path


def get_log_file_path() -> Path:
    settings = get_settings()
    path = settings.log_file_path.expanduser()
    if not path.is_absolute():
        path = settings.log_dir.expanduser() / path
    return path


def get_llm_api_key(provider: str) -> str | None:
    settings = get_settings()
    field_map = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
        "qwen": "qwen_api_key",
    }
    field = field_map.get(provider)
    if field is None:
        return None
    raw = getattr(settings, field, None)
    if not isinstance(raw, str) or not raw.strip():
        return None
    if provider in ("openai", "anthropic"):
        return settings.get_api_key_secure(key_name=field, provider=provider)
    return settings.get_api_key(key_name=field)


__all__ = [
    "SessionMgmtSettings",
    "get_database_path",
    "get_llm_api_key",
    "get_log_file_path",
    "get_settings",
    "reload_settings",
]
