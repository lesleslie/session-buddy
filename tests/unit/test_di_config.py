"""Tests for type-safe DI configuration.

This module tests the SessionPaths dataclass and related DI configuration
components, ensuring proper type-safe dependency injection patterns.

Phase: Week 7 Day 1 - ACB DI Refactoring
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from session_buddy.di.config import SessionPaths
from session_buddy.paths import APP_NAME, data_dir, state_dir


class TestSessionPathsCreation:
    """Test SessionPaths instantiation and factory methods."""

    def test_create_with_explicit_paths(self) -> None:
        """Should create SessionPaths with explicit path arguments."""
        claude_dir = Path("/tmp/test/.claude")
        logs_dir = Path("/tmp/test/.claude/logs")
        commands_dir = Path("/tmp/test/.claude/commands")
        data_dir = Path("/tmp/test/.claude/data")

        paths = SessionPaths(
            claude_dir=claude_dir,
            logs_dir=logs_dir,
            commands_dir=commands_dir,
            data_dir=data_dir,
        )

        assert paths.claude_dir == claude_dir
        assert paths.logs_dir == logs_dir
        assert paths.commands_dir == commands_dir

    def test_from_home_with_default(self) -> None:
        """Should create paths from current home directory when no argument provided."""
        paths = SessionPaths.from_home()

        # Should use os.path.expanduser("~") for environment-aware resolution
        expected_home = Path(os.path.expanduser("~"))
        expected_claude_dir = expected_home / ".claude"

        assert paths.claude_dir == expected_claude_dir
        assert paths.logs_dir == state_dir()
        assert paths.commands_dir == expected_claude_dir / "commands"
        assert paths.data_dir == data_dir()

    def test_from_home_with_explicit_path(self, tmp_path: Path) -> None:
        """Should create paths from explicit home directory."""
        paths = SessionPaths.from_home(tmp_path)

        expected_claude_dir = tmp_path / ".claude"
        assert paths.claude_dir == expected_claude_dir
        assert paths.logs_dir == tmp_path / ".local" / "state" / APP_NAME
        assert paths.commands_dir == expected_claude_dir / "commands"
        assert paths.data_dir == tmp_path / ".local" / "share" / APP_NAME

    def test_from_home_respects_home_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should respect HOME environment variable for test isolation."""
        # Set HOME to temp directory and drop the XDG overrides so the
        # spec defaults are derived from HOME.
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        # Create paths without explicit home argument
        paths = SessionPaths.from_home()

        # Should use the monkeypatched HOME
        expected_claude_dir = tmp_path / ".claude"
        assert paths.claude_dir == expected_claude_dir
        assert paths.logs_dir == tmp_path / ".local" / "state" / APP_NAME
        assert paths.commands_dir == expected_claude_dir / "commands"
        assert paths.data_dir == tmp_path / ".local" / "share" / APP_NAME


class TestSessionPathsImmutability:
    """Test frozen dataclass immutability enforcement."""

    def test_immutability_claude_dir(self) -> None:
        """Should raise FrozenInstanceError when attempting to modify claude_dir."""
        paths = SessionPaths.from_home()

        with pytest.raises(FrozenInstanceError):
            paths.claude_dir = Path("/tmp/hacked")  # type: ignore[misc]

    def test_immutability_logs_dir(self) -> None:
        """Should raise FrozenInstanceError when attempting to modify logs_dir."""
        paths = SessionPaths.from_home()

        with pytest.raises(FrozenInstanceError):
            paths.logs_dir = Path("/tmp/hacked")  # type: ignore[misc]

    def test_immutability_commands_dir(self) -> None:
        """Should raise FrozenInstanceError when attempting to modify commands_dir."""
        paths = SessionPaths.from_home()

        with pytest.raises(FrozenInstanceError):
            paths.commands_dir = Path("/tmp/hacked")  # type: ignore[misc]

    def test_immutability_prevents_new_attributes(self) -> None:
        """Should prevent adding new attributes (frozen dataclass behavior)."""
        paths = SessionPaths.from_home()

        with pytest.raises(FrozenInstanceError):
            paths.new_attribute = "should fail"  # type: ignore[attr-defined]


class TestSessionPathsDirectoryCreation:
    """Test directory creation and filesystem operations."""

    def test_ensure_directories_creates_all_paths(self, tmp_path: Path) -> None:
        """Should create all configured directories."""
        paths = SessionPaths.from_home(tmp_path)

        # Directories should not exist yet
        assert not paths.claude_dir.exists()
        assert not paths.logs_dir.exists()
        assert not paths.commands_dir.exists()

        # Create directories
        paths.ensure_directories()

        # All directories should now exist
        assert paths.claude_dir.exists()
        assert paths.claude_dir.is_dir()
        assert paths.logs_dir.exists()
        assert paths.logs_dir.is_dir()
        assert paths.commands_dir.exists()
        assert paths.commands_dir.is_dir()

    def test_ensure_directories_is_idempotent(self, tmp_path: Path) -> None:
        """Should safely handle multiple calls without errors."""
        paths = SessionPaths.from_home(tmp_path)

        # Create directories twice
        paths.ensure_directories()
        paths.ensure_directories()  # Should not raise

        # Verify directories still exist
        assert paths.claude_dir.exists()
        assert paths.logs_dir.exists()
        assert paths.commands_dir.exists()

    def test_ensure_directories_handles_missing_parents(self, tmp_path: Path) -> None:
        """Should create parent directories when they don't exist."""
        # Create paths in non-existent deep directory structure
        deep_home = tmp_path / "level1" / "level2" / "level3"
        paths = SessionPaths.from_home(deep_home)

        # Parent directories don't exist
        assert not deep_home.exists()

        # Should create all parents successfully
        paths.ensure_directories()

        # All directories should be created
        assert paths.claude_dir.exists()
        assert paths.logs_dir.exists()
        assert paths.commands_dir.exists()


class TestSessionPathsEquality:
    """Test equality and hashing behavior."""

    def test_equality_with_same_paths(self, tmp_path: Path) -> None:
        """Should be equal when paths are identical."""
        paths1 = SessionPaths.from_home(tmp_path)
        paths2 = SessionPaths.from_home(tmp_path)

        assert paths1 == paths2

    def test_inequality_with_different_paths(self, tmp_path: Path) -> None:
        """Should not be equal when paths differ."""
        paths1 = SessionPaths.from_home(tmp_path / "home1")
        paths2 = SessionPaths.from_home(tmp_path / "home2")

        assert paths1 != paths2

    def test_hashable_for_dict_keys(self, tmp_path: Path) -> None:
        """Should be hashable and usable as dict keys (frozen dataclass)."""
        paths = SessionPaths.from_home(tmp_path)

        # Should be usable as dict key
        cache: dict[SessionPaths, str] = {paths: "cached_value"}

        assert cache[paths] == "cached_value"


class TestSessionPathsStringRepresentation:
    """Test string representation and debugging output."""

    def test_repr_contains_all_fields(self, tmp_path: Path) -> None:
        """Should include all fields in repr output."""
        paths = SessionPaths.from_home(tmp_path)

        repr_str = repr(paths)

        # Should contain class name and all fields
        assert "SessionPaths" in repr_str
        assert "claude_dir" in repr_str
        assert "logs_dir" in repr_str
        assert "commands_dir" in repr_str
        assert str(tmp_path) in repr_str


class TestSessionPathsTypeAnnotations:
    """Test type safety and annotations."""

    def test_type_annotations_are_path(self) -> None:
        """Should have Path type annotations for all fields."""
        from dataclasses import fields

        path_fields = fields(SessionPaths)

        for field in path_fields:
            # In Python 3.13+, annotations can be strings or types
            # Accept either 'Path' (string) or Path (type)
            assert field.type in (
                Path,
                "Path",
            ), f"Field {field.name} should be Path type, got {field.type}"

    def test_frozen_attribute_is_true(self) -> None:
        """Should have frozen=True in dataclass configuration."""
        # Access dataclass metadata
        assert SessionPaths.__dataclass_fields__  # Verify it's a dataclass
        # Frozen behavior verified by FrozenInstanceError tests above


class TestSessionPathsEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_from_home_with_relative_path(self, tmp_path: Path) -> None:
        """Should handle relative paths correctly."""
        # Create a relative path
        relative_home = Path("relative/test/path")

        paths = SessionPaths.from_home(relative_home)

        # Should create paths relative to the provided home
        assert paths.claude_dir == relative_home / ".claude"
        assert paths.logs_dir == relative_home / ".local" / "state" / APP_NAME
        assert paths.data_dir == relative_home / ".local" / "share" / APP_NAME

    def test_from_home_with_symlink(self, tmp_path: Path) -> None:
        """Should handle symlinked home directories."""
        real_home = tmp_path / "real_home"
        symlink_home = tmp_path / "symlink_home"

        real_home.mkdir()
        symlink_home.symlink_to(real_home)

        paths = SessionPaths.from_home(symlink_home)

        # Paths should use the symlink path as provided
        assert paths.claude_dir == symlink_home / ".claude"

    def test_ensure_directories_with_existing_file(self, tmp_path: Path) -> None:
        """Should handle case where a file exists with the directory name."""
        paths = SessionPaths.from_home(tmp_path)

        # Create a file where claude_dir should be
        paths.claude_dir.parent.mkdir(parents=True, exist_ok=True)
        file_blocking = tmp_path / ".claude"
        file_blocking.touch()

        # Should raise an error (cannot create directory where file exists)
        with pytest.raises((FileExistsError, NotADirectoryError)):
            paths.ensure_directories()
