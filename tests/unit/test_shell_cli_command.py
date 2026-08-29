"""Tests for `session-buddy shell` CLI command (Plan Task 3.1.1).

Wires SessionBuddyShell (previously library-only) into the CLI surface.
Lazy-imports the heavy admin-shell modules so the rest of the test
suite still loads quickly.
"""
from __future__ import annotations

from typer.testing import CliRunner

from session_buddy.cli import app

runner = CliRunner()


def test_shell_command_registered() -> None:
    """`session-buddy --help` lists the shell command."""
    result = runner.invoke(app, ["--help"])
    assert "shell" in result.output, f"missing 'shell' in: {result.output!r}"