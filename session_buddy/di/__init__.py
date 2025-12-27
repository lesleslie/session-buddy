from __future__ import annotations

import tempfile
import typing as t
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from acb.depends import depends

if t.TYPE_CHECKING:
    from session_buddy.core import (
        SessionLifecycleManager as SessionLifecycleManagerT,
    )
    from session_buddy.core.permissions import (
        SessionPermissionsManager as SessionPermissionsManagerT,
    )
    from session_buddy.utils.logging import (  # type: ignore[attr-defined]
        SessionLogger as SessionLoggerT,
    )

from .config import SessionPaths
from .constants import CLAUDE_DIR_KEY, COMMANDS_DIR_KEY, LOGS_DIR_KEY

_configured = False


def configure(*, force: bool = False) -> None:
    """Register default dependencies for the session-buddy MCP stack.

    This function sets up the dependency injection container with type-safe
    configuration and singleton instances for the session management system.

    Args:
        force: If True, re-registers all dependencies even if already configured.
               Used primarily for testing to reset singleton state.

    Example:
        >>> from session_buddy.di import configure
        >>> configure()  # First call registers dependencies
        >>> configure()  # Subsequent calls are no-ops unless force=True
        >>> configure(force=True)  # Re-registers all dependencies

    """
    global _configured
    if _configured and not force:
        return

    # Register type-safe path configuration
    paths = SessionPaths.from_home()
    paths.ensure_directories()
    depends.set(SessionPaths, paths)

    # Register services with type-safe path access
    _register_logger(paths.logs_dir, force)
    _register_session_logger(paths.logs_dir, force)  # Register SessionLogger
    _register_permissions_manager(paths.claude_dir, force)
    _register_lifecycle_manager(force)

    # Register ACB adapters (Phase 2.7: DuckDB migration)
    _register_vector_adapter(paths, force)
    _register_graph_adapter(paths, force)  # Fixed: ACB ssl_enabled bug resolved
    _register_storage_adapters(paths, force)  # Phase 1: Storage adapters

    _configured = True


def reset() -> None:
    """Reset dependencies to defaults."""
    # Reset singleton instances that have class-level state
    with suppress(ImportError, AttributeError):
        from session_buddy.core.permissions import SessionPermissionsManager

        SessionPermissionsManager.reset_singleton()

    configure(force=True)


def _register_logger(logs_dir: Path, force: bool) -> None:
    """Register ACB logger adapter with the given logs directory.

    Args:
        logs_dir: Directory for session log files
        force: If True, re-registers even if already registered

    Note:
        This function configures ACB's logger adapter but does NOT register it
        in the DI container to avoid bevy type resolution conflicts. Components
        should use direct logging imports instead of DI lookup.

    """
    # Skip registration entirely - we don't need to register the logger in DI
    # Components should use `import logging; logger = logging.getLogger(__name__)`
    # This avoids bevy DI type confusion when crackerjack runs


def _register_session_logger(logs_dir: Path, force: bool) -> None:
    """Register SessionLogger with the given logs directory.

    Args:
        logs_dir: Directory for session log files
        force: If True, re-registers even if already registered

    """
    from session_buddy.utils.logging import SessionLogger

    if not force:
        with suppress(Exception):
            existing = depends.get_sync(SessionLogger)
            if isinstance(existing, SessionLogger):
                return

    # Create SessionLogger instance with fallback to temp logs if needed
    try:
        session_logger = SessionLogger(logs_dir)
    except Exception:
        tmp_logs = Path(tempfile.gettempdir()) / "session-buddy" / "logs"
        tmp_logs.mkdir(parents=True, exist_ok=True)
        depends.set(LOGS_DIR_KEY, tmp_logs)
        session_logger = SessionLogger(tmp_logs)
    depends.set(SessionLogger, session_logger)


def _register_vector_adapter(paths: SessionPaths, force: bool) -> None:
    """Register ACB vector adapter with DuckDB backend.

    Args:
        paths: Session paths configuration with data directory
        force: If True, re-registers even if already registered

    Note:
        Uses ACB's vector adapter with VSS extension for semantic search.
        Configured for 384-dimensional embeddings (all-MiniLM-L6-v2 model).

    """
    # Import ACB's Vector adapter and settings
    from acb.adapters.vector.duckdb import Vector, VectorSettings
    from acb.config import Config

    if not force:
        with suppress(KeyError, AttributeError, RuntimeError):
            existing = depends.get_sync(Vector)
            if isinstance(existing, Vector):
                return

    # Get Config singleton and ensure it's initialized
    config = depends.get_sync(Config)
    config.ensure_initialized()

    # Create settings for vector adapter
    settings = VectorSettings(
        database_path=str(paths.data_dir / "reflection.duckdb"),
        default_dimension=384,  # all-MiniLM-L6-v2 embeddings
        default_distance_metric="cosine",
        enable_vss=True,  # Enable DuckDB VSS extension
        threads=4,
        memory_limit="2GB",
    )

    # Register settings in Config object
    config.vector = settings  # type: ignore[attr-defined]

    # Create adapter instance and manually set config (ACB test pattern)
    vector_adapter = Vector()
    vector_adapter.config = config  # Override _DependencyMarker with actual Config

    # Set logger directly to avoid DI type resolution conflicts
    # Using string-based DI keys for logger causes bevy type inference issues
    # when resolving other dependencies like SessionLogger
    import logging

    vector_adapter.logger = logging.getLogger("acb.vector")
    vector_adapter.logger.setLevel(logging.INFO)

    # Initialize adapter to create vectors schema (ACB requirement)
    # Note: Initialization is deferred - schema creation happens on first use
    # This avoids event loop conflicts when configure() is called from async contexts
    depends.set(Vector, vector_adapter)

    # Mark that initialization is needed
    vector_adapter._schema_initialized = False


def _register_graph_adapter(paths: SessionPaths, force: bool) -> None:
    """Register ACB graph adapter with DuckDB PGQ backend.

    Args:
        paths: Session paths configuration with data directory
        force: If True, re-registers even if already registered

    Note:
        Uses ACB's graph adapter with DuckPGQ extension for property graphs.
        Maintains compatibility with existing kg_entities/kg_relationships schema.

    """
    # Import ACB's Graph adapter and settings
    from acb.adapters.graph.duckdb_pgq import DuckDBPGQSettings, Graph
    from acb.config import Config

    if not force:
        with suppress(KeyError, AttributeError, RuntimeError):
            existing = depends.get_sync(Graph)
            if isinstance(existing, Graph):
                return

    # Get Config singleton and ensure it's initialized
    config = depends.get_sync(Config)
    config.ensure_initialized()

    data_dir = paths.data_dir
    if not data_dir.is_absolute():
        data_dir = Path.home() / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create settings for graph adapter
    settings = DuckDBPGQSettings(
        database_url=f"duckdb:///{data_dir}/knowledge_graph.duckdb",
        graph_name="session_mgmt_graph",
        nodes_table="kg_entities",
        edges_table="kg_relationships",
        install_extensions=["duckpgq"],
    )

    # Register settings in Config object
    config.graph = settings  # type: ignore[attr-defined]

    # Create adapter instance and manually set config (ACB test pattern)
    graph_adapter = Graph(settings=settings)
    graph_adapter.config = config  # Override _DependencyMarker with actual Config
    depends.set(Graph, graph_adapter)


def _register_storage_adapters(paths: SessionPaths, force: bool) -> None:
    """Register ACB storage adapters for session state persistence.

    Args:
        paths: Session paths configuration with data directory
        force: If True, re-registers even if already registered

    Note:
        Registers file storage adapter by default for local session storage.
        Additional backends (S3, Azure, GCS, Memory) can be registered on-demand
        via the storage_registry module when needed for serverless deployments.

    """
    from session_buddy.adapters.storage_registry import (
        configure_storage_buckets,
        get_default_session_buckets,
        register_storage_adapter,
    )

    # Configure default buckets for session management
    buckets = get_default_session_buckets(paths.data_dir)
    configure_storage_buckets(buckets)

    # Register file storage adapter by default (local session storage)
    config_overrides = {
        "local_path": str(paths.data_dir),
        "buckets": buckets,
    }

    try:
        storage_adapter = register_storage_adapter(
            "file",
            config_overrides=config_overrides,
            force=force,
        )
        # Initialize buckets
        # Note: Initialization is deferred to avoid event loop conflicts
        # Buckets will be created on first use
        storage_adapter._buckets_initialized = False
    except Exception as e:
        # Log but don't fail - storage is optional for basic session management
        import logging

        logger = logging.getLogger("session_buddy.di")
        logger.warning(f"Failed to register storage adapter: {e}")


def _register_permissions_manager(claude_dir: Path, force: bool) -> None:
    """Register SessionPermissionsManager with the given Claude directory.

    Args:
        claude_dir: Root Claude directory for session data
        force: If True, re-registers even if already registered

    Note:
        Accepts Path directly instead of resolving from string keys,
        following ACB's type-based dependency injection pattern.

    """
    from session_buddy.core.permissions import SessionPermissionsManager

    if not force:
        with suppress(Exception):  # Catch all DI resolution errors
            existing = depends.get_sync(SessionPermissionsManager)
            if isinstance(existing, SessionPermissionsManager):
                return

    # Create and register permissions manager instance
    permissions_manager = SessionPermissionsManager(claude_dir)
    depends.set(SessionPermissionsManager, permissions_manager)


def _register_lifecycle_manager(force: bool) -> None:
    """Register SessionLifecycleManager with the DI container.

    Args:
        force: If True, re-registers even if already registered

    """
    from session_buddy.core.session_manager import SessionLifecycleManager

    if not force:
        with suppress(Exception):  # Catch all DI resolution errors
            existing = depends.get_sync(SessionLifecycleManager)
            if isinstance(existing, SessionLifecycleManager):
                return

    # Create and register lifecycle manager instance
    lifecycle_manager = SessionLifecycleManager()
    depends.set(SessionLifecycleManager, lifecycle_manager)


__all__ = [
    # Legacy string keys (deprecated - use SessionPaths instead)
    "CLAUDE_DIR_KEY",
    "COMMANDS_DIR_KEY",
    "LOGS_DIR_KEY",
    "SessionPaths",
    "configure",
    "reset",
]
