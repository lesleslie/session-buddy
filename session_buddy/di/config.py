"""Type-safe configuration for dependency injection.

This module provides type-safe configuration classes for the Oneiric-backed
service container, replacing string-based keys with proper type-based
dependency resolution.

Phase: Week 7 Day 1 - ACB DI Refactoring
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from session_buddy.paths import data_dir, data_dir_under, state_dir, state_dir_under


@dataclass(frozen=True)
class SessionPaths:
    """Type-safe path configuration for session management.

    This class replaces string-based DI keys (like "paths.claude_dir") with
    a proper type-based configuration object that works correctly with Bevy's
    type checking system.

    ``claude_dir`` and ``commands_dir`` stay under ``~/.claude`` — those
    really are Claude-Code-specific. ``data_dir`` and ``logs_dir`` are
    owned by Session-Buddy and resolve through the XDG Base Directory
    layout (see :mod:`session_buddy.paths`).

    Attributes:
        claude_dir: Root directory for Claude session data (~/.claude)
        logs_dir: Directory for session logs (XDG state dir)
        commands_dir: Directory for slash commands (~/.claude/commands)
        data_dir: Directory for database storage (XDG data dir)

    Example:
        >>> paths = SessionPaths.from_home()
        >>> print(paths.claude_dir)
        PosixPath('/Users/username/.claude')

        >>> # Use with DI container
        >>> depends.set(SessionPaths, paths)
        >>> resolved = depends.get_sync(SessionPaths)

    """

    claude_dir: Path
    logs_dir: Path
    commands_dir: Path
    data_dir: Path

    @classmethod
    def from_home(cls, home: Path | None = None) -> SessionPaths:
        """Create SessionPaths from home directory.

        Args:
            home: Optional home directory path. If None, uses current user's home
                  directory via os.path.expanduser("~"). This method respects the
                  HOME environment variable, making it test-friendly. When given,
                  the XDG data and state roots are anchored beneath it so the
                  whole tree stays isolated.

        Returns:
            SessionPaths instance with directories based on the home path.

        Example:
            >>> # Use default home directory
            >>> paths = SessionPaths.from_home()

            >>> # Use custom home (useful for testing)
            >>> test_home = Path("/tmp/test_home")
            >>> paths = SessionPaths.from_home(test_home)

        """
        if home is None:
            # Use os.path.expanduser to respect HOME environment variable
            # This is test-friendly, unlike Path.home() which uses system APIs
            home = Path(os.path.expanduser("~"))
            logs_dir = state_dir()
            data_root = data_dir()
        else:
            logs_dir = state_dir_under(home)
            data_root = data_dir_under(home)

        claude_dir = home / ".claude"

        return cls(
            claude_dir=claude_dir,
            logs_dir=logs_dir,
            commands_dir=claude_dir / "commands",
            data_dir=data_root,
        )

    def ensure_directories(self) -> None:
        """Create all configured directories if they don't exist.

        This method is idempotent and safe to call multiple times.
        Uses mkdir(parents=True, exist_ok=True) to handle missing parent
        directories gracefully.

        Example:
            >>> paths = SessionPaths.from_home()
            >>> paths.ensure_directories()
            >>> assert paths.claude_dir.exists()
            >>> assert paths.logs_dir.exists()
            >>> assert paths.data_dir.exists()

        """
        self.claude_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.commands_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
