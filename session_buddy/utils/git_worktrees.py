#!/usr/bin/env python3
"""Git operations utilities for session management."""

from __future__ import annotations

import subprocess  # nosec B404
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    "WorktreeInfo",
    "is_git_repository",
    "is_git_worktree",
    "get_git_root",
    "get_worktree_info",
    "list_worktrees",
    "get_git_status",
    "stage_files",
    "get_staged_files",
    "create_commit",
    "create_checkpoint_commit",
    "is_git_operation_in_progress",
    "schedule_automatic_git_gc",
]


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    path: Path
    branch: str
    is_bare: bool = False
    is_detached: bool = False
    is_main_worktree: bool = False
    locked: bool = False
    prunable: bool = False


def is_git_repository(directory: str | Path) -> bool:
    """Check if the given directory is a git repository or worktree."""
    if isinstance(directory, str):
        directory = Path(directory)
    git_dir = directory / ".git"
    # Check for both main repo (.git directory) and worktree (.git file)
    return git_dir.exists() and (git_dir.is_dir() or git_dir.is_file())


def is_git_worktree(directory: Path) -> bool:
    """Check if the directory is a git worktree (not the main repository)."""
    if isinstance(directory, str):
        directory = Path(directory)
    git_path = directory / ".git"
    # Worktrees have a .git file that points to the actual git directory
    return git_path.exists() and git_path.is_file()


def get_git_root(directory: str | Path) -> Path | None:
    """Get the root directory of the git repository."""
    if not is_git_repository(directory):
        return None

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def get_worktree_info(directory: Path) -> WorktreeInfo | None:
    """Get information about the current worktree."""
    if not is_git_repository(directory):
        return None

    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )
        branch = branch_result.stdout.strip()

        # Check if detached HEAD
        is_detached = False
        if not branch:
            head_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=directory,
                check=True,
            )
            branch = f"HEAD ({head_result.stdout.strip()})"
            is_detached = True

        # Get worktree path (normalized)
        toplevel_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )
        path = Path(toplevel_result.stdout.strip())

        return WorktreeInfo(
            path=path,
            branch=branch,
            is_detached=is_detached,
            is_main_worktree=not is_git_worktree(directory),
        )

    except subprocess.CalledProcessError:
        return None


def _process_worktree_line(line: str, current_worktree: dict[str, Any]) -> None:
    """Process a single line from git worktree list --porcelain output."""
    if line.startswith("worktree "):
        current_worktree["path"] = line[9:]  # Remove 'worktree ' prefix
    elif line.startswith("HEAD "):
        current_worktree["head"] = line[5:]  # Remove 'HEAD ' prefix
    elif line.startswith("branch "):
        current_worktree["branch"] = line[7:]  # Remove 'branch ' prefix
    elif line == "bare":
        current_worktree["bare"] = True
    elif line == "detached":
        current_worktree["detached"] = True
    elif line.startswith("locked"):
        current_worktree["locked"] = True
    elif line == "prunable":
        current_worktree["prunable"] = True


def list_worktrees(directory: Path) -> list[WorktreeInfo]:
    """List all worktrees for the repository."""
    if not is_git_repository(directory):
        return []

    result = _run_git_worktree_list(directory)
    if result is None:
        return []

    return _parse_worktree_list_output(result.stdout)


def _run_git_worktree_list(directory: Path) -> subprocess.CompletedProcess[str] | None:
    """Run git worktree list command and return result or None on error."""
    try:
        return subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None


def _parse_worktree_list_output(output: str) -> list[WorktreeInfo]:
    """Parse the output of git worktree list command."""
    worktrees = []
    current_worktree: dict[str, Any] = {}

    for line in output.strip().split("\n"):
        if not line:
            if current_worktree:
                worktrees.append(_parse_worktree_entry(current_worktree))
                current_worktree = {}
            continue

        _process_worktree_line(line, current_worktree)

    # Handle last worktree if exists
    if current_worktree:
        worktrees.append(_parse_worktree_entry(current_worktree))

    return worktrees


def _parse_worktree_entry(entry: dict[str, Any]) -> WorktreeInfo:
    """Parse a single worktree entry from git worktree list output."""
    path = Path(entry.get("path", ""))
    branch = entry.get("branch", entry.get("head", "unknown"))

    # Check if this is the main worktree (bare repos don't have .git file)
    is_main = not (path / ".git").is_file() if path.exists() else False

    return WorktreeInfo(
        path=path,
        branch=str(branch),
        is_bare=entry.get("bare", False),
        is_detached=entry.get("detached", False),
        is_main_worktree=is_main,
        locked=entry.get("locked", False),
        prunable=entry.get("prunable", False),
    )


def get_git_status(directory: Path) -> tuple[list[str], list[str]]:
    """Get modified and untracked files from git status."""
    if not is_git_repository(directory):
        return [], []

    try:
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )

        status_lines = (
            status_result.stdout.strip().split("\n")
            if status_result.stdout.strip()
            else []
        )

        return _parse_git_status(status_lines)
    except subprocess.CalledProcessError:
        return [], []


def _parse_git_status(status_lines: list[str]) -> tuple[list[str], list[str]]:
    """Parse git status output into modified and untracked files."""
    modified_files = []
    untracked_files = []

    for line in status_lines:
        if line:
            # Extract the status (first 2 characters) and file path
            status = line[:2]
            filepath = line[2:].lstrip()  # Remove leading whitespace

            if status == "??":
                untracked_files.append(filepath)
            elif status.strip():  # If status has meaningful content (not just spaces)
                modified_files.append(filepath)

    return modified_files, untracked_files


def stage_files(directory: Path, files: list[str]) -> bool:
    """Stage files for commit."""
    if not is_git_repository(directory) or not files:
        return False

    try:
        # Stage all changes (handles modified, deleted, and new files)
        subprocess.run(
            ["git", "add", "-A"],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        # Debug: Print the actual error
        return False


def get_staged_files(directory: Path) -> list[str]:
    """Get list of staged files."""
    if not is_git_repository(directory):
        return []

    try:
        staged_result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )

        return (
            staged_result.stdout.strip().split("\n")
            if staged_result.stdout.strip()
            else []
        )
    except subprocess.CalledProcessError:
        return []


def create_commit(directory: Path, message: str) -> tuple[bool, str]:
    """Create a git commit with the given message.

    Returns:
        tuple: (success, commit_hash or error_message)

    """
    if not is_git_repository(directory):
        return False, "Not a git repository"

    try:
        subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )

        # Get commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=directory,
            check=True,
        )

        commit_hash = hash_result.stdout.strip()[:8]
        return True, commit_hash

    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() if e.stderr else str(e)


def _add_worktree_context_output(
    worktree_info: WorktreeInfo | None,
    output: list[str],
) -> None:
    """Add worktree context information to output."""
    if worktree_info:
        if worktree_info.is_main_worktree:
            output.append(f"📝 Main repository on branch '{worktree_info.branch}'")
        else:
            output.append(
                f"🌿 Worktree on branch '{worktree_info.branch}' at {worktree_info.path}",
            )


def _create_checkpoint_message(
    project: str,
    quality_score: int,
    worktree_info: WorktreeInfo | None,
) -> str:
    """Create the checkpoint commit message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Enhanced commit message with worktree info
    worktree_suffix = ""
    if worktree_info and not worktree_info.is_main_worktree:
        worktree_suffix = f" [worktree: {worktree_info.branch}]"

    commit_message = (
        f"checkpoint: Session checkpoint - {timestamp}{worktree_suffix}\n\n"
        f"Automatic checkpoint commit via session-management MCP server\n"
        f"Project: {project}\n"
        f"Quality Score: {quality_score}/100"
    )

    if worktree_info:
        commit_message += f"\nBranch: {worktree_info.branch}"
        if not worktree_info.is_main_worktree:
            commit_message += f"\nWorktree: {worktree_info.path}"

    return commit_message


def _validate_git_repository(directory: Path) -> tuple[bool, str, list[str]]:
    """Validate that the directory is a git repository."""
    output = []
    if not is_git_repository(directory):
        output.append("ℹ️ Not a git repository - skipping commit")
        return False, "Not a git repository", output
    return True, "", output


def _check_for_changes(directory: Path) -> tuple[list[str], list[str], list[str]]:
    """Check for modified and untracked files."""
    worktree_info = get_worktree_info(directory)
    modified_files, untracked_files = get_git_status(directory)

    output = []
    if not modified_files and not untracked_files:
        output.append("✅ Working directory is clean - no changes to commit")
        return [], [], output

    _add_worktree_context_output(worktree_info, output)
    output.append(
        f"📝 Found {len(modified_files)} modified files and {len(untracked_files)} untracked files",
    )

    if untracked_files:
        output.extend(_format_untracked_files(untracked_files))

    return modified_files, untracked_files, output


def _perform_staging_and_commit(
    directory: Path,
    project: str,
    quality_score: int,
) -> tuple[bool, str, list[str]]:
    """Stage changes and create commit."""
    output = []

    # Create commit message
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_message = (
        f"checkpoint: {project} (quality: {quality_score}/100) - {timestamp}"
    )

    # Stage changes
    stage_result = subprocess.run(
        ["git", "add", "-A"],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )

    if stage_result.returncode != 0:
        output.append(f"⚠️ Failed to stage changes: {stage_result.stderr.strip()}")
        return False, "staging failed", output

    # Create commit
    commit_result = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )

    if commit_result.returncode != 0:
        output.append(f"⚠️ Commit failed: {commit_result.stderr.strip()}")
        return False, "commit failed", output

    # Get commit hash
    hash_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )

    commit_hash = (
        hash_result.stdout.strip()[:8] if hash_result.returncode == 0 else "unknown"
    )

    output.extend(
        (
            f"✅ Checkpoint commit created successfully ({commit_hash})",
            f"   Message: {commit_message}",
        )
    )
    return True, commit_hash, output


def create_checkpoint_commit(
    directory: Path,
    project: str,
    quality_score: int,
) -> tuple[bool, str, list[str]]:
    """Create an automatic checkpoint commit.

    Returns:
        tuple: (success, commit_hash_or_error, output_messages)

    """
    # Validate git repository
    valid, error, output = _validate_git_repository(directory)
    if not valid:
        return False, error, output

    try:
        # Check for changes
        modified_files, untracked_files, check_output = _check_for_changes(directory)
        output.extend(check_output)

        if not modified_files and not untracked_files:
            return True, "clean", output

        # Handle modified files
        if modified_files:
            success, result, commit_output = _perform_staging_and_commit(
                directory,
                project,
                quality_score,
            )
            output.extend(commit_output)
            return success, result, output

        # Only untracked files remain
        if untracked_files:
            output.extend(
                (
                    "ℹ️ No staged changes to commit",
                    "   💡 Add untracked files with 'git add' if you want to include them",
                )
            )
            return False, "No staged changes", output

    except Exception as e:
        error_msg = f"Git operations error: {e}"
        output.append(f"⚠️ {error_msg}")
        return False, error_msg, output

    return False, "Unexpected error", output


def _format_untracked_files(untracked_files: list[str]) -> list[str]:
    """Format untracked files display."""
    output = []
    output.append("🆕 Untracked files found:")

    for file in untracked_files[:10]:  # Limit to first 10 for display
        output.append(f"   • {file}")

    if len(untracked_files) > 10:
        output.append(f"   ... and {len(untracked_files) - 10} more")

    output.extend(
        (
            "⚠️ Please manually review and add untracked files if needed:",
            "   Use: git add <file> for files you want to include",
        )
    )

    return output


def _validate_numeric_range(value: int) -> tuple[bool, str]:
    """Validate numeric value is within acceptable range.

    Args:
        value: Numeric value to validate

    Returns:
        tuple: (is_valid, error_message_or_empty)
    """
    if value > 1000:
        return False, f"Value too large: {value}. Maximum allowed is 1000."
    if value < 1:
        return False, f"Value too small: {value}. Must be at least 1."
    return True, ""


def _matches_safe_pattern(prune_delay: str) -> tuple[bool, str]:
    """Check if prune delay matches any safe pattern.

    Args:
        prune_delay: Prune delay string to validate

    Returns:
        tuple: (is_valid, error_message_or_empty)
    """
    import re

    safe_patterns = [
        r"^(\d+)\.(seconds?|minutes?|hours?|days?|weeks?|months?|years?)$",
        r"^(now|never)$",
    ]

    for pattern in safe_patterns:
        match = re.match(pattern, prune_delay, re.IGNORECASE)
        if match:
            if match.groups() and match.group(1):
                try:
                    value = int(match.group(1))
                    return _validate_numeric_range(value)
                except ValueError:
                    return False, f"Invalid numeric value in: {prune_delay}"
            return True, ""

    return False, ""


def _validate_prune_delay(prune_delay: str) -> tuple[bool, str]:
    """Validate prune delay parameter to prevent command injection.

    SECURITY ENHANCEMENT: Added numeric range validation to prevent excessive values.

    Uses strict allowlist validation to ensure only safe git prune delays
    are accepted. Git's prune delay format is: <number>.<timeunit> or 'now'.

    Args:
        prune_delay: Prune delay string to validate

    Returns:
        tuple: (is_valid, error_message_or_empty)

    """
    is_valid, error_msg = _matches_safe_pattern(prune_delay)

    if not is_valid and not error_msg:
        return False, (
            f"Invalid prune delay '{prune_delay}'. "
            "Must be in format '<number>.<unit>' (e.g., '2.weeks') or 'now'."
        )

    return is_valid, error_msg


def is_git_operation_in_progress(directory: Path | str) -> bool:
    """Check if a git operation (rebase, merge, bisect) is in progress.

    Args:
        directory: Path to the git repository

    Returns:
        True if a git operation is in progress, False otherwise

    """
    if isinstance(directory, str):
        directory = Path(directory)

    if not is_git_repository(directory):
        return False

    git_dir = directory / ".git"

    # Check for various in-progress operation indicators
    operation_indicators = [
        "rebase-merge",  # Interactive rebase
        "rebase-apply",  # Non-interactive rebase
        "MERGE_HEAD",  # Merge in progress
        "BISECT_LOG",  # Bisect in progress
        "CHERRY_PICK_HEAD",  # Cherry-pick in progress
        "REVERT_HEAD",  # Revert in progress
        "PATCH_APPLY",  # Apply in progress
    ]

    for indicator in operation_indicators:
        if (git_dir / indicator).exists():
            return True

    return False


def schedule_automatic_git_gc(
    directory: Path | str,
    prune_delay: str = "2.weeks",
    auto_threshold: int = 6700,
) -> tuple[bool, str]:
    """Schedule automatic git garbage collection in the background.

    This runs git gc --auto in the background to avoid blocking the
    checkpoint process. The --auto flag ensures gc only runs when
    the number of loose objects exceeds the threshold.

    Args:
        directory: Path to the git repository
        prune_delay: Prune delay (e.g., 'now', '2.weeks', '1.month')
        auto_threshold: Loose object threshold to trigger gc

    Returns:
        tuple: (success, message)

    """
    if isinstance(directory, str):
        directory = Path(directory)

    if not is_git_repository(directory):
        return False, "Not a git repository"

    # Validate prune delay to prevent command injection
    is_valid, error_msg = _validate_prune_delay(prune_delay)
    if not is_valid:
        return False, error_msg

    try:
        # Configure gc.auto threshold
        subprocess.run(
            ["git", "config", "gc.auto", str(auto_threshold)],
            cwd=directory,
            capture_output=True,
            check=False,
        )

        # Schedule gc in background (non-blocking)
        # Note: prune_delay is now validated, so this is safe
        # SECURITY: Use sanitized environment to prevent sensitive data leakage
        from .subprocess_executor import popen_safe

        popen_safe(
            ["git", "gc", "--auto", f"--prune={prune_delay}"],
            allowed_commands={"git"},
            cwd=directory,
        )

        return True, f"Scheduled git gc (prune delay: {prune_delay})"

    except Exception as e:
        return False, f"Failed to schedule git gc: {e}"
