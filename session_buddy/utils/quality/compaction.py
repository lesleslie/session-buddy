"""Compaction analysis utilities for context optimization.

This module provides helper functions for analyzing when context compaction
would be beneficial based on project characteristics, git activity, and
development patterns.
"""

from __future__ import annotations

import subprocess  # nosec B404
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def get_default_compaction_reason() -> str:
    """Get the default reason when no strong indicators are found."""
    return "Context appears manageable - compaction not immediately needed"


def get_fallback_compaction_reason() -> str:
    """Get fallback reason when evaluation fails."""
    return "Unable to assess context complexity - compaction may be beneficial as a precaution"


def count_significant_files(current_dir: Path) -> int:
    """Count significant files in project as a complexity indicator."""
    file_count = 0
    with suppress(OSError, PermissionError, FileNotFoundError, ValueError):
        for file_path in current_dir.rglob("*"):
            if (
                file_path.is_file()
                and not any(
                    part.startswith(".")
                    for part in file_path.relative_to(current_dir).parts
                )
                and file_path.suffix
                in {
                    ".py",
                    ".js",
                    ".ts",
                    ".jsx",
                    ".tsx",
                    ".go",
                    ".rs",
                    ".java",
                    ".cpp",
                    ".c",
                    ".h",
                }
            ):
                file_count += 1
                if file_count > 50:  # Stop counting after threshold
                    break
    return file_count


def check_git_activity(current_dir: Path) -> tuple[int, int] | None:
    """Check for active development via git and return (recent_commits, modified_files)."""
    git_dir = current_dir / ".git"
    if not git_dir.exists():
        return None

    try:
        # Check number of recent commits as activity indicator
        result = subprocess.run(
            ["git", "log", "--oneline", "-20", "--since='24 hours ago'"],
            check=False,
            capture_output=True,
            text=True,
            cwd=current_dir,
            timeout=5,
        )
        if result.returncode == 0:
            recent_commits = len(
                [line for line in result.stdout.strip().split("\n") if line.strip()],
            )
        else:
            recent_commits = 0

        # Check for large number of modified files
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            cwd=current_dir,
            timeout=5,
        )
        if status_result.returncode == 0:
            modified_files = len(
                [
                    line
                    for line in status_result.stdout.strip().split("\n")
                    if line.strip()
                ],
            )
        else:
            modified_files = 0

        return recent_commits, modified_files

    except (subprocess.TimeoutExpired, Exception):
        return None


def evaluate_large_project_heuristic(file_count: int) -> tuple[bool, str]:
    """Evaluate if the project is large enough to benefit from compaction."""
    if file_count > 50:
        return (
            True,
            "Large codebase with 50+ source files detected - context compaction recommended",
        )
    return False, ""


def evaluate_git_activity_heuristic(
    git_activity: tuple[int, int] | None,
) -> tuple[bool, str]:
    """Evaluate if git activity suggests compaction would be beneficial."""
    if git_activity:
        recent_commits, modified_files = git_activity

        if recent_commits >= 3:
            return (
                True,
                f"High development activity ({recent_commits} commits in 24h) - compaction recommended",
            )

        if modified_files >= 10:
            return (
                True,
                f"Many modified files ({modified_files}) detected - context optimization beneficial",
            )

    return False, ""


def evaluate_python_project_heuristic(current_dir: Path) -> tuple[bool, str]:
    """Evaluate if this is a Python project that might benefit from compaction."""
    if (current_dir / "tests").exists() and (current_dir / "pyproject.toml").exists():
        return (
            True,
            "Python project with tests detected - compaction may improve focus",
        )
    return False, ""
