from __future__ import annotations

import tempfile
import typing as t
from contextlib import suppress
from pathlib import Path

from session_buddy.di.container import depends

from .config import SessionPaths
from .constants import CLAUDE_DIR_KEY, COMMANDS_DIR_KEY, LOGS_DIR_KEY

_configured = False


def get_sync_typed[T](key: type[T]) -> T:
    """Type-safe wrapper for depends.get_sync.

    This helper provides proper type information for the dependency injection
    container, avoiding 'no-any-return' type checker errors.

    Args:
        key: The class type to retrieve from the DI container

    Returns:
        The instance of type T from the DI container

    Example:
        >>> from session_buddy.core.session_manager import SessionLifecycleManager
        >>> manager = get_sync_typed(SessionLifecycleManager)  # Properly typed

    """
    result: t.Any = depends.get_sync(key)
    # Type assertion: we trust the DI container to return the correct type
    return t.cast(T, result)  # Use PEP 695 type param, not string literal


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
    _register_hooks_manager(force)  # Register HooksManager for automation

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
        in the DI container to avoid type resolution conflicts. Components
        should use direct logging imports instead of DI lookup.

    """
    # Skip registration entirely - we don't need to register the logger in DI
    # Components should use `import logging; logger = logging.getLogger(__name__)`
    # This avoids DI type confusion when crackerjack runs


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


def _register_hooks_manager(force: bool) -> None:
    """Register HooksManager with the DI container.

    Args:
        force: If True, re-registers even if already registered

    Note:
        The HooksManager provides automation capabilities through priority-based
        async hook execution with error handling and causal chain tracking.

    """
    from session_buddy.core.hooks import HooksManager

    if not force:
        with suppress(Exception):  # Catch all DI resolution errors
            existing = depends.get_sync(HooksManager)
            if isinstance(existing, HooksManager):
                return

    # Create and register hooks manager instance
    hooks_manager = HooksManager()
    depends.set(HooksManager, hooks_manager)


__all__ = [
    # Legacy string keys (deprecated - use SessionPaths instead)
    "CLAUDE_DIR_KEY",
    "COMMANDS_DIR_KEY",
    "LOGS_DIR_KEY",
    "SessionPaths",
    "configure",
    "depends",
    "get_sync_typed",
    "reset",
]
