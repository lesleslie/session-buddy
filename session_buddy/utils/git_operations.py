#!/usr/bin/env python3
"""Git operation utilities for session management.

This module provides Git-related functionality following crackerjack
architecture patterns with single responsibility principle.
"""

from __future__ import annotations

import subprocess  # nosec B404
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


__all__ = [
    "WorktreeInfo",
    "create_checkpoint_commit",
    "create_commit",
    "get_git_status",
    "get_staged_files",
    "is_git_operation_in_progress",
    "is_git_repository",
    "schedule_automatic_git_gc",
    "stage_files",
]


def _parse_git_status(status_lines: list[str]) -> tuple[list[str], list[str]]:
    """Parse git status output into staged and untracked files."""
    staged_files = []
    untracked_files = []

    for line in status_lines:
        if line.startswith(("A ", "M ", "D ")):
            staged_files.append(line[3:])  # Remove status prefix
        elif line.startswith("?? "):
            untracked_files.append(line[3:])  # Remove ?? prefix

    return staged_files, untracked_files


def _format_untracked_files(untracked_files: list[str]) -> list[str]:
    """Format untracked files for display."""
    if not untracked_files:
        return ["✅ No untracked files"]

    formatted = ["📁 Untracked Files:"]
    for file in untracked_files[:10]:  # Limit display
        formatted.append(f"   • {file}")

    if len(untracked_files) > 10:
        formatted.append(f"   ... and {len(untracked_files) - 10} more files")

    return formatted


def _stage_and_commit_files(
    current_dir: Path,
    commit_message: str,
    files_to_stage: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Stage files and create commit with given message."""
    output: list[str] = []
    try:
        stage_success = _stage_files(current_dir, files_to_stage, output)
        if not stage_success:
            return False, output

        return _commit_staged_changes(current_dir, commit_message, output)
    except Exception as exc:
        output.append(f"❌ Git operation error: {exc}")
        return False, output


def _stage_files(
    current_dir: Path,
    files_to_stage: list[str] | None,
    output: list[str],
) -> bool:
    """Stage specified files or all changes."""
    if files_to_stage:
        return all(
            _run_git_command(["git", "add", file_path], current_dir, output)
            for file_path in files_to_stage
        )

    if _run_git_command(["git", "add", "-A"], current_dir, output):
        return True

    output.append("⚠️ Failed to stage changes")
    return False


def _commit_staged_changes(
    current_dir: Path,
    commit_message: str,
    output: list[str],
) -> tuple[bool, list[str]]:
    """Commit staged changes and update output log."""
    success = _run_git_command(
        ["git", "commit", "-m", commit_message], current_dir, output
    )
    if success:
        output.append(f"✅ Committed changes: {commit_message}")
        return True, output

    output.append("⚠️ Commit failed")
    return False, output


def _run_git_command(
    command: list[str],
    current_dir: Path,
    output: list[str],
) -> bool:
    """Run a git command and append stderr output when it fails."""
    result = subprocess.run(
        command,
        cwd=current_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        return True

    stderr = result.stderr.strip()
    if stderr:
        output.append(f"⚠️ {' '.join(command[1:3])} failed: {stderr}")
    return False


def _optimize_git_repository(current_dir: Path) -> list[str]:
    """Optimize Git repository with garbage collection and pruning."""
    optimization_results = []

    try:
        # Git garbage collection
        gc_cmd = ["git", "gc", "--auto"]
        result = subprocess.run(
            gc_cmd,
            cwd=current_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            optimization_results.append("🗑️ Git garbage collection completed")
        else:
            optimization_results.append(f"⚠️ Git gc failed: {result.stderr.strip()}")

        # Prune remote tracking branches
        prune_cmd = ["git", "remote", "prune", "origin"]
        result = subprocess.run(
            prune_cmd,
            cwd=current_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            optimization_results.append("🌿 Pruned remote tracking branches")
        else:
            # Remote prune failure is non-critical
            optimization_results.append(
                "ℹ️ Remote pruning skipped (no remote or access issues)",
            )

    except Exception as e:
        optimization_results.append(f"⚠️ Git optimization error: {e}")

    return optimization_results


# Compatibility imports: These functions were moved to git_worktrees.py
# Re-export them here for backward compatibility
from session_buddy.utils.git_worktrees import (  # noqa: F401
    WorktreeInfo,
    create_checkpoint_commit,
    create_commit,
    get_git_status,
    get_staged_files,
    is_git_operation_in_progress,
    is_git_repository,
    schedule_automatic_git_gc,
    stage_files,
)
