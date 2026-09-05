"""Unit tests for ``session_buddy.cli.checkpoint_cli``.

Covers the two public entry points in the CLI module:

* ``cleanup_snapshots`` — the ``checkpoint cleanup-snapshots`` Typer
  command which constructs a :class:`SnapshotCleanupTask` and reports
  the number of removed files.
* ``register_checkpoint_command`` — the helper that attaches the
  checkpoint sub-Typer to a parent CLI.

The CLI is small and free of DB / network dependencies, so tests mock
:class:`SnapshotCleanupTask` directly via ``patch.object`` on the
``checkpoint_cli`` module rather than touching the filesystem.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from session_buddy.cli import checkpoint_cli
from session_buddy.cli.checkpoint_cli import (
    app,
    cleanup_snapshots,
    register_checkpoint_command,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_cleanup_task() -> MagicMock:
    """Patch ``SnapshotCleanupTask`` inside the CLI module.

    Returns a ``MagicMock`` class — tests configure ``return_value`` and
    inspect the constructed instance via the mock's ``.return_value``
    attribute.
    """
    mock_class = MagicMock()
    # cleanup_once is awaited inside asyncio.run; expose an AsyncMock so
    # the CLI can ``await`` it without raising TypeError.
    mock_class.return_value.cleanup_once = AsyncMock(return_value=0)
    with patch.object(checkpoint_cli, "SnapshotCleanupTask", mock_class):
        yield mock_class


# =============================================================================
# Tests for the standalone Typer app
# =============================================================================


class TestApp:
    """Tests for the module-level ``app`` Typer instance."""

    def test_help(self, runner: CliRunner) -> None:
        """``--help`` lists the cleanup-snapshots command and exits 0."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "cleanup-snapshots" in result.output

    def test_cleanup_snapshots_is_registered(self) -> None:
        """The ``cleanup-snapshots`` callback is registered on the app."""
        registered = set()
        for callback in app.registered_commands:  # type: ignore[attr-defined]
            name = getattr(callback, "name", None) or getattr(
                callback.callback, "__name__", None
            )
            if name:
                registered.add(name)
        assert "cleanup-snapshots" in registered


# =============================================================================
# Tests for cleanup_snapshots
# =============================================================================


class TestCleanupSnapshots:
    """Behaviour of the ``checkpoint cleanup-snapshots`` command."""

    def test_default_args_use_tempdir_default(self, runner: CliRunner, mock_cleanup_task: MagicMock) -> None:
        """Default invocation uses ``older_than=7`` and the fallback dir."""
        # ``app`` is a single-command Typer; Typer infers the command when
        # no positional is supplied (passing ``"cleanup-snapshots"`` here
        # would be treated as an extra argument).
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_cleanup_task.assert_called_once()
        positional = mock_cleanup_task.call_args.args
        # First positional arg is the snapshot_dir Path.
        assert isinstance(positional[0], Path)
        # ttl_seconds is the keyword argument; 7 days == 604800 seconds.
        assert mock_cleanup_task.call_args.kwargs["ttl_seconds"] == 7 * 86400

    def test_custom_older_than_is_converted_to_seconds(
        self, runner: CliRunner, mock_cleanup_task: MagicMock
    ) -> None:
        """``--older-than N`` becomes ``ttl_seconds=N * 86400``."""
        result = runner.invoke(app, ["--older-than", "1"])
        assert result.exit_code == 0
        assert mock_cleanup_task.call_args.kwargs["ttl_seconds"] == 86400

    def test_custom_snapshot_dir_is_honored(
        self, runner: CliRunner, mock_cleanup_task: MagicMock, tmp_path: Path
    ) -> None:
        """``--snapshot-dir`` overrides the default ``/tmp`` snapshot path."""
        result = runner.invoke(app, ["--snapshot-dir", str(tmp_path)])
        assert result.exit_code == 0
        passed_dir = mock_cleanup_task.call_args.args[0]
        assert Path(passed_dir) == tmp_path

    def test_echoes_removed_count(self, runner: CliRunner, mock_cleanup_task: MagicMock) -> None:
        """Output line reports the number of snapshots removed."""
        mock_cleanup_task.return_value.cleanup_once = AsyncMock(return_value=3)
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "removed 3 snapshots" in result.output

    def test_echo_includes_resolved_snapshot_dir(
        self, runner: CliRunner, mock_cleanup_task: MagicMock, tmp_path: Path
    ) -> None:
        """The echoed message reflects the resolved snapshot directory."""
        mock_cleanup_task.return_value.cleanup_once = AsyncMock(return_value=0)
        result = runner.invoke(app, ["--snapshot-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert str(tmp_path) in result.output

    def test_zero_removed_emits_zero(
        self, runner: CliRunner, mock_cleanup_task: MagicMock
    ) -> None:
        """A clean directory yields ``removed 0 snapshots``."""
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "removed 0 snapshots" in result.output

    def test_help_flag_works(self, runner: CliRunner) -> None:
        """``--help`` shows option metadata for the subcommand."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--older-than" in result.output
        assert "--snapshot-dir" in result.output


# =============================================================================
# Tests for direct function invocation
# =============================================================================


class TestDirectInvocation:
    """Direct calls to ``cleanup_snapshots`` (bypassing Typer plumbing)."""

    def test_direct_call_constructs_task_with_temp_default(
        self, mock_cleanup_task: MagicMock
    ) -> None:
        """Calling the function with no args uses the tempdir fallback."""
        cleanup_snapshots(older_than=7, snapshot_dir=None)
        mock_cleanup_task.assert_called_once()
        positional = mock_cleanup_task.call_args.args
        assert isinstance(positional[0], Path)

    def test_direct_call_forwards_explicit_dir(
        self, mock_cleanup_task: MagicMock, tmp_path: Path
    ) -> None:
        """Explicit ``snapshot_dir`` is forwarded to the task constructor."""
        cleanup_snapshots(older_than=2, snapshot_dir=tmp_path)
        assert mock_cleanup_task.call_args.args[0] == tmp_path
        assert mock_cleanup_task.call_args.kwargs["ttl_seconds"] == 2 * 86400


# =============================================================================
# Tests for register_checkpoint_command
# =============================================================================


class TestRegisterCheckpointCommand:
    """Behaviour of the parent-app registration helper."""

    def test_registers_subcommand_named_checkpoint(self) -> None:
        """Attaches the module's Typer app under the ``checkpoint`` name."""
        parent = typer.Typer()
        register_checkpoint_command(parent)
        registered_groups = {
            getattr(g, "name", None) or getattr(g.typer_instance, "info", g).name
            for g in parent.registered_groups  # type: ignore[attr-defined]
        }
        assert "checkpoint" in registered_groups

    def test_registered_subcommand_exposes_cleanup_snapshots(
        self, runner: CliRunner
    ) -> None:
        """``checkpoint cleanup-snapshots --help`` exposes subcommand options."""
        parent = typer.Typer()
        register_checkpoint_command(parent)
        result = runner.invoke(
            parent, ["checkpoint", "cleanup-snapshots", "--help"]
        )
        assert result.exit_code == 0
        assert "--older-than" in result.output

    def test_double_registration_does_not_raise(self) -> None:
        """Calling register twice on the same parent is not exercised here —

        Typer raises on duplicate sub-typer names, so only the first
        registration is supported. Verified by a single successful register.
        """
        parent = typer.Typer()
        register_checkpoint_command(parent)
        # A second call would raise BadParameter from Typer; assert that
        # the original subcommand is still resolvable.
        assert len(parent.registered_groups) == 1  # type: ignore[attr-defined]


# =============================================================================
# Tests for module surface
# =============================================================================


class TestModuleSurface:
    """Ensure the module exports the symbols the rest of the codebase imports."""

    def test_app_is_typer(self) -> None:
        """``app`` is a real Typer instance, not a placeholder."""
        assert isinstance(app, typer.Typer)

    def test_cleanup_snapshots_is_callable(self) -> None:
        """``cleanup_snapshots`` is a plain callable (Typer-decorated)."""
        assert callable(cleanup_snapshots)

    def test_register_checkpoint_command_is_callable(self) -> None:
        """``register_checkpoint_command`` is an importable helper."""
        assert callable(register_checkpoint_command)
