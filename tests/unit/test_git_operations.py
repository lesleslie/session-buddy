"""Comprehensive tests for Git integration functionality.

Week 8 Day 2 - Phase 5: Test git operations, checkpoint commits, and worktree support.
Tests subprocess-based git operations with realistic repository scenarios.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from session_buddy.utils.git_worktrees import (
    WorktreeInfo,
    _validate_prune_delay,
    create_checkpoint_commit,
    create_commit,
    get_git_root,
    get_git_status,
    get_staged_files,
    get_worktree_info,
    is_git_operation_in_progress,
    is_git_repository,
    is_git_worktree,
    list_worktrees,
    schedule_automatic_git_gc,
    stage_files,
)
from tests.fixtures import (
    tmp_git_repo,
    tmp_git_repo_with_changes,
    tmp_git_repo_with_commits,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
class TestGitRepositoryDetection:
    """Test git repository detection functions."""

    def test_is_git_repository_with_valid_repo(self, tmp_git_repo: Path):
        """is_git_repository returns True for valid git repository."""
        assert is_git_repository(tmp_git_repo) is True

    def test_is_git_repository_with_string_path(self, tmp_git_repo: Path):
        """is_git_repository accepts string path."""
        assert is_git_repository(str(tmp_git_repo)) is True

    def test_is_git_repository_with_non_repo(self, tmp_path: Path):
        """is_git_repository returns False for non-git directory."""
        assert is_git_repository(tmp_path) is False

    def test_is_git_worktree_with_main_repo(self, tmp_git_repo: Path):
        """is_git_worktree returns False for main repository."""
        assert is_git_worktree(tmp_git_repo) is False

    def test_get_git_root_with_valid_repo(self, tmp_git_repo: Path):
        """get_git_root returns repository root path."""
        root = get_git_root(tmp_git_repo)
        assert root is not None
        assert root == tmp_git_repo

    def test_get_git_root_with_non_repo(self, tmp_path: Path):
        """get_git_root returns None for non-git directory."""
        assert get_git_root(tmp_path) is None


@pytest.mark.asyncio
class TestGitStatusOperations:
    """Test git status and file tracking."""

    def test_get_git_status_with_clean_repo(self, tmp_git_repo: Path):
        """get_git_status returns empty lists for clean repository."""
        modified, untracked = get_git_status(tmp_git_repo)

        assert modified == []
        assert untracked == []

    def test_get_git_status_with_modified_files(self, tmp_git_repo: Path):
        """get_git_status detects modified tracked files."""
        # Modify existing file
        readme = tmp_git_repo / "README.md"
        readme.write_text("# Modified Content\n")

        modified, untracked = get_git_status(tmp_git_repo)

        assert "README.md" in modified
        assert untracked == []

    def test_get_git_status_with_untracked_files(self, tmp_git_repo: Path):
        """get_git_status detects new untracked files."""
        # Create new untracked file
        (tmp_git_repo / "new_file.txt").write_text("new content\n")

        modified, untracked = get_git_status(tmp_git_repo)

        assert modified == []
        assert "new_file.txt" in untracked

    def test_get_git_status_with_mixed_changes(self, tmp_git_repo_with_changes: Path):
        """get_git_status handles both modified and untracked files."""
        modified, untracked = get_git_status(tmp_git_repo_with_changes)

        # Should have both types (fixture creates modified + untracked)
        assert len(modified) > 0
        assert len(untracked) > 0

    def test_get_git_status_with_non_repo(self, tmp_path: Path):
        """get_git_status returns empty lists for non-git directory."""
        modified, untracked = get_git_status(tmp_path)

        assert modified == []
        assert untracked == []


@pytest.mark.asyncio
class TestGitStagingOperations:
    """Test git staging and commit preparation."""

    def test_stage_files_with_valid_changes(self, tmp_git_repo: Path):
        """stage_files stages modified files successfully."""
        # Create changes
        (tmp_git_repo / "file1.txt").write_text("content\n")
        (tmp_git_repo / "file2.txt").write_text("content\n")

        # Stage files
        success = stage_files(tmp_git_repo, ["file1.txt", "file2.txt"])

        assert success is True

        # Verify files are staged
        staged = get_staged_files(tmp_git_repo)
        assert "file1.txt" in staged
        assert "file2.txt" in staged

    def test_stage_files_with_empty_list(self, tmp_git_repo: Path):
        """stage_files returns False with empty file list."""
        success = stage_files(tmp_git_repo, [])
        assert success is False

    def test_stage_files_with_non_repo(self, tmp_path: Path):
        """stage_files returns False for non-git directory."""
        success = stage_files(tmp_path, ["file.txt"])
        assert success is False

    def test_get_staged_files_with_staged_changes(self, tmp_git_repo: Path):
        """get_staged_files returns list of staged files."""
        # Create and stage file
        test_file = tmp_git_repo / "staged.txt"
        test_file.write_text("content\n")

        subprocess.run(
            ["git", "add", "staged.txt"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )

        staged = get_staged_files(tmp_git_repo)
        assert "staged.txt" in staged

    def test_get_staged_files_with_no_changes(self, tmp_git_repo: Path):
        """get_staged_files returns empty list when nothing staged."""
        staged = get_staged_files(tmp_git_repo)
        assert staged == []


@pytest.mark.asyncio
class TestGitCommitOperations:
    """Test git commit creation."""

    def test_create_commit_with_staged_changes(self, tmp_git_repo: Path):
        """create_commit creates commit successfully with staged changes."""
        # Create and stage file
        (tmp_git_repo / "new.txt").write_text("content\n")
        subprocess.run(
            ["git", "add", "new.txt"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )

        # Create commit
        success, commit_hash = create_commit(tmp_git_repo, "Test commit message")

        assert success is True
        assert len(commit_hash) == 8  # Short hash

    def test_create_commit_with_no_changes(self, tmp_git_repo: Path):
        """create_commit fails when no changes staged."""
        success, error = create_commit(tmp_git_repo, "Empty commit")

        assert success is False
        # Error message varies, just verify it failed
        assert len(error) > 0

    def test_create_commit_with_non_repo(self, tmp_path: Path):
        """create_commit returns error for non-git directory."""
        success, error = create_commit(tmp_path, "Test")

        assert success is False
        assert error == "Not a git repository"

    def test_create_commit_with_multiline_message(self, tmp_git_repo: Path):
        """create_commit handles multiline commit messages."""
        # Create and stage file
        (tmp_git_repo / "file.txt").write_text("content\n")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )

        message = "Short title\n\nLonger description with\nmultiple lines"
        success, commit_hash = create_commit(tmp_git_repo, message)

        assert success is True
        assert len(commit_hash) == 8


@pytest.mark.asyncio
class TestCheckpointCommitCreation:
    """Test automatic checkpoint commit creation."""

    def test_create_checkpoint_commit_with_changes(self, tmp_git_repo: Path):
        """create_checkpoint_commit creates commit with modified files."""
        # Create changes
        readme = tmp_git_repo / "README.md"
        readme.write_text("# Modified\n")

        success, commit_hash, output = create_checkpoint_commit(
            tmp_git_repo, "test-project", 85
        )

        assert success is True
        assert len(commit_hash) == 8
        assert any("Checkpoint commit created" in msg for msg in output)

    def test_create_checkpoint_commit_with_clean_repo(self, tmp_git_repo: Path):
        """create_checkpoint_commit handles clean repository gracefully."""
        success, result, output = create_checkpoint_commit(
            tmp_git_repo, "test-project", 85
        )

        assert success is True
        assert result == "clean"
        assert any("clean" in msg.lower() for msg in output)

    def test_create_checkpoint_commit_with_untracked_only(self, tmp_git_repo: Path):
        """create_checkpoint_commit skips untracked files."""
        # Create untracked file
        (tmp_git_repo / "untracked.txt").write_text("content\n")

        success, result, output = create_checkpoint_commit(
            tmp_git_repo, "test-project", 85
        )

        # Should fail with no staged changes (only untracked files)
        assert success is False or result == "clean"
        assert any("untracked" in msg.lower() for msg in output)

    def test_create_checkpoint_commit_with_non_repo(self, tmp_path: Path):
        """create_checkpoint_commit returns error for non-git directory."""
        success, error, output = create_checkpoint_commit(tmp_path, "test-project", 85)

        assert success is False
        assert error == "Not a git repository"
        assert any("Not a git repository" in msg for msg in output)

    def test_create_checkpoint_commit_message_format(self, tmp_git_repo: Path):
        """create_checkpoint_commit creates properly formatted message."""
        # Modify existing tracked file (untracked files won't be committed)
        readme = tmp_git_repo / "README.md"
        readme.write_text("# Modified for checkpoint test\n")

        success, _commit_hash, _output = create_checkpoint_commit(
            tmp_git_repo, "session-mgmt-mcp", 75
        )

        assert success is True

        # Verify commit message format
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            cwd=tmp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        )

        commit_msg = result.stdout
        assert "checkpoint:" in commit_msg.lower()
        assert "session-mgmt-mcp" in commit_msg
        assert "75/100" in commit_msg


@pytest.mark.asyncio
class TestWorktreeOperations:
    """Test git worktree detection and management."""

    def test_get_worktree_info_with_valid_repo(self, tmp_git_repo: Path):
        """get_worktree_info returns WorktreeInfo for valid repository."""
        info = get_worktree_info(tmp_git_repo)

        assert info is not None
        assert isinstance(info, WorktreeInfo)
        assert info.path == tmp_git_repo
        assert info.branch  # Should have a branch name
        assert info.is_main_worktree is True
        assert info.is_detached is False

    def test_get_worktree_info_with_non_repo(self, tmp_path: Path):
        """get_worktree_info returns None for non-git directory."""
        info = get_worktree_info(tmp_path)
        assert info is None

    def test_list_worktrees_with_single_repo(self, tmp_git_repo: Path):
        """list_worktrees returns main repository worktree."""
        worktrees = list_worktrees(tmp_git_repo)

        assert len(worktrees) >= 1
        assert worktrees[0].path == tmp_git_repo

    def test_list_worktrees_with_non_repo(self, tmp_path: Path):
        """list_worktrees returns empty list for non-git directory."""
        worktrees = list_worktrees(tmp_path)
        assert worktrees == []


@pytest.mark.asyncio
class TestGitOperationsEdgeCases:
    """Test edge cases and error handling."""

    def test_get_git_status_with_deleted_files(self, tmp_git_repo: Path):
        """get_git_status detects deleted tracked files."""
        # Delete tracked file
        readme = tmp_git_repo / "README.md"
        readme.unlink()

        modified, _untracked = get_git_status(tmp_git_repo)

        # Deleted files appear as modified
        assert "README.md" in modified

    def test_stage_files_handles_new_and_deleted(self, tmp_git_repo: Path):
        """stage_files handles both new and deleted files."""
        # Delete existing file
        (tmp_git_repo / "README.md").unlink()

        # Add new file
        (tmp_git_repo / "new.txt").write_text("content\n")

        success = stage_files(tmp_git_repo, ["README.md", "new.txt"])
        assert success is True

        staged = get_staged_files(tmp_git_repo)
        assert "README.md" in staged or "new.txt" in staged

    def test_create_checkpoint_commit_with_many_files(self, tmp_git_repo: Path):
        """create_checkpoint_commit handles many changed files."""
        # Modify the existing README file (tracked)
        readme = tmp_git_repo / "README.md"
        readme.write_text("# Modified with many changes\n" * 50)

        success, commit_hash, _output = create_checkpoint_commit(
            tmp_git_repo, "test-project", 90
        )

        assert success is True
        assert len(commit_hash) == 8

    def test_get_git_status_handles_special_characters(self, tmp_git_repo: Path):
        """get_git_status handles filenames with special characters."""
        # Create file with spaces
        special_file = tmp_git_repo / "file with spaces.txt"
        special_file.write_text("content\n")

        _modified, untracked = get_git_status(tmp_git_repo)

        # Git wraps filenames with spaces in quotes
        assert any("file with spaces.txt" in f for f in untracked)


@pytest.mark.asyncio
class TestGitMaintenanceOperations:
    """Test automatic git maintenance (gc) functionality."""

    def test_is_git_operation_in_progress_with_clean_repo(self, tmp_git_repo: Path):
        """is_git_operation_in_progress returns False for clean repository."""
        assert is_git_operation_in_progress(tmp_git_repo) is False

    def test_is_git_operation_in_progress_during_rebase(self, tmp_git_repo: Path):
        """is_git_operation_in_progress detects rebase in progress."""
        # Simulate rebase in progress by creating indicator file
        (tmp_git_repo / ".git" / "rebase-merge").mkdir(exist_ok=True)

        assert is_git_operation_in_progress(tmp_git_repo) is True

        # Clean up
        (tmp_git_repo / ".git" / "rebase-merge").rmdir()

    def test_is_git_operation_in_progress_during_merge(self, tmp_git_repo: Path):
        """is_git_operation_in_progress detects merge in progress."""
        # Create MERGE_HEAD indicator file
        (tmp_git_repo / ".git" / "MERGE_HEAD").write_text("abc123\n")

        assert is_git_operation_in_progress(tmp_git_repo) is True

        # Clean up
        (tmp_git_repo / ".git" / "MERGE_HEAD").unlink()

    def test_is_git_operation_in_progress_during_bisect(self, tmp_git_repo: Path):
        """is_git_operation_in_progress detects bisect in progress."""
        # Create BISECT_LOG indicator file
        (tmp_git_repo / ".git" / "BISECT_LOG").write_text("bisect log\n")

        assert is_git_operation_in_progress(tmp_git_repo) is True

        # Clean up
        (tmp_git_repo / ".git" / "BISECT_LOG").unlink()

    def test_is_git_operation_in_progress_with_non_repo(self, tmp_path: Path):
        """is_git_operation_in_progress returns False for non-git directory."""
        assert is_git_operation_in_progress(tmp_path) is False

    def test_is_git_operation_in_progress_with_string_path(self, tmp_git_repo: Path):
        """is_git_operation_in_progress accepts string path."""
        assert is_git_operation_in_progress(str(tmp_git_repo)) is False

    @patch("session_buddy.utils.git_operations.subprocess.Popen")
    @patch("session_buddy.utils.git_operations.subprocess.run")
    def test_schedule_automatic_git_gc_success(
        self, mock_run: Mock, mock_popen: Mock, tmp_git_repo: Path
    ):
        """schedule_automatic_git_gc schedules gc successfully."""
        # Configure mocks
        mock_run.return_value = Mock(returncode=0)
        mock_popen.return_value = Mock()

        success, message = schedule_automatic_git_gc(tmp_git_repo)

        assert success is True
        assert "Scheduled git gc" in message
        assert mock_run.called  # git config should be called
        assert mock_popen.called  # git gc should be scheduled

    @patch("session_buddy.utils.git_operations.subprocess.Popen")
    @patch("session_buddy.utils.git_operations.subprocess.run")
    def test_schedule_automatic_git_gc_with_custom_settings(
        self, mock_run: Mock, mock_popen: Mock, tmp_git_repo: Path
    ):
        """schedule_automatic_git_gc uses custom prune delay and threshold."""
        mock_run.return_value = Mock(returncode=0)
        mock_popen.return_value = Mock()

        success, message = schedule_automatic_git_gc(
            tmp_git_repo, prune_delay="1.month", auto_threshold=10000
        )

        assert success is True
        assert "1.month" in message

        # Verify gc threshold was configured
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        # call_args[0] contains the positional args tuple
        # call_args[0][0] is the list ["git", "config", "gc.auto", "10000"]
        assert "10000" in call_args[0][0]  # threshold in git config command

    def test_schedule_automatic_git_gc_with_non_repo(self, tmp_path: Path):
        """schedule_automatic_git_gc returns error for non-git directory."""
        success, message = schedule_automatic_git_gc(tmp_path)

        assert success is False
        assert "Not a git repository" in message

    @patch("session_buddy.utils.git_operations.subprocess.run")
    def test_schedule_automatic_git_gc_configures_threshold(
        self, mock_run: Mock, tmp_git_repo: Path
    ):
        """schedule_automatic_git_gc sets gc.auto config correctly."""
        mock_run.return_value = Mock(returncode=0)

        with patch("session_buddy.utils.git_operations.subprocess.Popen"):
            schedule_automatic_git_gc(tmp_git_repo, auto_threshold=5000)

            # Verify git config was called with threshold
            mock_run.assert_called()
            call_args = mock_run.call_args[0]
            assert call_args[0] == ["git", "config", "gc.auto", "5000"]

    @patch("session_buddy.utils.git_operations.subprocess.Popen")
    @patch("session_buddy.utils.git_operations.subprocess.run")
    def test_schedule_automatic_git_gc_background_execution(
        self, mock_run: Mock, mock_popen: Mock, tmp_git_repo: Path
    ):
        """schedule_automatic_git_gc runs gc in background."""
        mock_run.return_value = Mock(returncode=0)
        mock_popen.return_value = Mock()

        schedule_automatic_git_gc(tmp_git_repo, prune_delay="now")

        # Verify Popen was called (background execution)
        assert mock_popen.called
        call_args = mock_popen.call_args[0]
        assert call_args[0][0] == "git"  # Command
        assert call_args[0][1] == "gc"  # Subcommand
        assert "--auto" in call_args[0]  # Auto flag
        assert "--prune=now" in call_args[0]  # Prune delay

        # Verify stdout/stderr are suppressed
        kwargs = mock_popen.call_args[1]
        assert kwargs["stdout"] is not None
        assert kwargs["stderr"] is not None


@pytest.mark.asyncio
class TestPruneDelayValidation:
    """Test prune delay validation to prevent command injection."""

    def test_validate_prune_delay_valid_formats(self):
        """_validate_prune_delay accepts valid git prune delay formats."""
        valid_delays = [
            "2.weeks",
            "1.month",
            "30.days",
            "12.hours",
            "720.minutes",
            "now",
            "never",
            "1.day",  # Singular
            "5.years",  # Plural
        ]

        for delay in valid_delays:
            is_valid, error = _validate_prune_delay(delay)
            assert is_valid is True, f"Failed for valid delay: {delay}"
            assert error == "", f"Unexpected error for {delay}: {error}"

    def test_validate_prune_delay_invalid_formats(self):
        """_validate_prune_delay rejects invalid formats."""
        invalid_delays = [
            "now; rm -rf /",  # Command injection attempt
            "2.weeks; cat /etc/passwd",  # Another injection attempt
            "$(whoami)",  # Command substitution
            "`恶意命令`",  # Backtick injection
            "2.weeks && malicious",  # Chain injection
            "",  # Empty string
            "invalid",  # No number
            "2",  # No unit
            "weeks",  # No number
            ".weeks",  # No number
            "2.",  # No unit
            "x.weeks",  # Non-numeric
            " 2.weeks",  # Leading space
            "2.weeks ",  # Trailing space
        ]

        for delay in invalid_delays:
            is_valid, error = _validate_prune_delay(delay)
            assert is_valid is False, f"Should reject invalid delay: {delay}"
            assert len(error) > 0, f"Should have error message for: {delay}"

    def test_validate_prune_delay_case_insensitive(self):
        """_validate_prune_delay handles case variations."""
        # Case variations should all be valid
        valid_variations = ["2.Weeks", "2.WEEKS", "2.WeEkS", "2.weeks"]

        for delay in valid_variations:
            is_valid, _error = _validate_prune_delay(delay)
            assert is_valid is True, f"Should accept case variation: {delay}"

    def test_schedule_automatic_git_gc_rejects_invalid_delay(
        self, tmp_git_repo: Path
    ):
        """schedule_automatic_git_gc rejects invalid prune delay."""
        success, message = schedule_automatic_git_gc(
            tmp_git_repo, prune_delay="malicious; rm -rf /", auto_threshold=6700
        )

        assert success is False
        assert "Invalid prune delay" in message or "format" in message.lower()

    def test_schedule_automatic_git_gc_accepts_valid_delay(
        self, tmp_git_repo: Path
    ):
        """schedule_automatic_git_gc accepts valid prune delay."""
        with patch("session_buddy.utils.git_operations.subprocess.Popen"), patch(
            "session_buddy.utils.git_operations.subprocess.run"
        ):
            success, message = schedule_automatic_git_gc(
                tmp_git_repo, prune_delay="1.month", auto_threshold=5000
            )

            assert success is True
            assert "1.month" in message
