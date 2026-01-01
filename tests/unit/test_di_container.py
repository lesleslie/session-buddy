"""Tests for the Oneiric service container configuration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from session_buddy.core import SessionLifecycleManager
from session_buddy.core.permissions import SessionPermissionsManager
from session_buddy.di import SessionPaths, configure, reset
from session_buddy.di.container import depends
from session_buddy.utils.logging import SessionLogger

if TYPE_CHECKING:
    import pytest


def test_configure_registers_singletons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """configure() should register shared instances for core services."""
    original_home = Path.home()

    # Monkeypatch HOME first, then reset singleton
    monkeypatch.setenv("HOME", str(tmp_path))
    SessionPermissionsManager.reset_singleton()

    configure(force=True)

    # Verify SessionPaths is registered
    paths = depends.get_sync(SessionPaths)
    assert isinstance(paths, SessionPaths)
    assert paths.claude_dir == tmp_path / ".claude"
    assert paths.logs_dir == tmp_path / ".claude" / "logs"
    assert paths.commands_dir == tmp_path / ".claude" / "commands"

    # Verify SessionLogger uses paths from SessionPaths
    logger = depends.get_sync(SessionLogger)
    assert isinstance(logger, SessionLogger)
    assert logger.log_dir == paths.logs_dir
    logger2 = depends.get_sync(SessionLogger)
    assert logger2 is logger

    # Verify SessionPermissionsManager uses paths from SessionPaths
    permissions = depends.get_sync(SessionPermissionsManager)
    assert permissions.permissions_file.parent == paths.claude_dir / "sessions"
    permissions2 = depends.get_sync(SessionPermissionsManager)
    assert permissions2 is permissions

    # Verify SessionLifecycleManager is registered
    lifecycle = depends.get_sync(SessionLifecycleManager)
    lifecycle2 = depends.get_sync(SessionLifecycleManager)
    assert lifecycle2 is lifecycle

    monkeypatch.setenv("HOME", str(original_home))
    reset()


def test_reset_restores_default_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reset() should replace overrides with freshly configured defaults."""
    original_home = Path.home()

    # Monkeypatch HOME first, then reset singleton
    monkeypatch.setenv("HOME", str(tmp_path))
    SessionPermissionsManager.reset_singleton()

    configure(force=True)

    custom_logs = tmp_path / "custom" / "logs"
    custom_logger = SessionLogger(custom_logs)
    depends.set(SessionLogger, custom_logger)
    assert depends.get_sync(SessionLogger) is custom_logger

    reset()

    restored_logger = depends.get_sync(SessionLogger)
    assert restored_logger is not custom_logger
    assert restored_logger.log_dir == tmp_path / ".claude" / "logs"

    monkeypatch.setenv("HOME", str(original_home))
    reset()
