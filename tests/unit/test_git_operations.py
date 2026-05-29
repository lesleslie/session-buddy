"""Comprehensive tests for Git integration functionality.

Week 8 Day 2 - Phase 5: Test git operations, checkpoint commits, and worktree support.
Tests subprocess-based git operations with realistic repository scenarios.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest


def _load_git_worktrees_module():
    repo_root = Path(__file__).resolve().parents[2]

    if "session_buddy" not in sys.modules:
        package = types.ModuleType("session_buddy")
        package.__path__ = [str(repo_root / "session_buddy")]  # type: ignore[attr-defined]
        sys.modules["session_buddy"] = package
    else:
        package = sys.modules["session_buddy"]

    utils_package_name = "session_buddy.utils"
    if utils_package_name not in sys.modules:
        utils_package = types.ModuleType(utils_package_name)
        utils_package.__path__ = [str(repo_root / "session_buddy" / "utils")]  # type: ignore[attr-defined]
        sys.modules[utils_package_name] = utils_package
    else:
        utils_package = sys.modules[utils_package_name]

    setattr(package, "utils", utils_package)

    module_path = repo_root / "session_buddy" / "utils" / "git_worktrees.py"
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.git_worktrees",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    setattr(utils_package, "git_worktrees", module)
    spec.loader.exec_module(module)
    return module


git_worktrees = _load_git_worktrees_module()
WorktreeInfo = git_worktrees.WorktreeInfo
_add_worktree_context_output = git_worktrees._add_worktree_context_output
_check_for_changes = git_worktrees._check_for_changes
_format_untracked_files = git_worktrees._format_untracked_files
_matches_safe_pattern = git_worktrees._matches_safe_pattern
_optimize_git_repository = git_worktrees._optimize_git_repository
_parse_worktree_entry = git_worktrees._parse_worktree_entry
_parse_worktree_list_output = git_worktrees._parse_worktree_list_output
_perform_staging_and_commit = git_worktrees._perform_staging_and_commit
_process_worktree_line = git_worktrees._process_worktree_line
_validate_numeric_range = git_worktrees._validate_numeric_range
_validate_prune_delay = git_worktrees._validate_prune_delay
create_checkpoint_commit = git_worktrees.create_checkpoint_commit
create_commit = git_worktrees.create_commit
get_git_root = git_worktrees.get_git_root
get_git_status = git_worktrees.get_git_status
get_staged_files = git_worktrees.get_staged_files
get_worktree_info = git_worktrees.get_worktree_info
is_git_operation_in_progress = git_worktrees.is_git_operation_in_progress
is_git_repository = git_worktrees.is_git_repository
is_git_worktree = git_worktrees.is_git_worktree
list_worktrees = git_worktrees.list_worktrees
schedule_automatic_git_gc = git_worktrees.schedule_automatic_git_gc
stage_files = git_worktrees.stage_files
from tests.fixtures import (
    tmp_git_repo,
    tmp_git_repo_with_changes,
    tmp_git_repo_with_commits,
)

if TYPE_CHECKING:
    from pathlib import Path


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

    def test_is_git_worktree_accepts_string_path(self, tmp_git_repo: Path):
        """is_git_worktree accepts string paths."""
        assert is_git_worktree(str(tmp_git_repo)) is False

    def test_get_git_root_with_valid_repo(self, tmp_git_repo: Path):
        """get_git_root returns repository root path."""
        root = get_git_root(tmp_git_repo)
        assert root is not None
        assert root == tmp_git_repo

    def test_get_git_root_with_non_repo(self, tmp_path: Path):
        """get_git_root returns None for non-git directory."""
        assert get_git_root(tmp_path) is None

    def test_get_git_root_handles_called_process_error(self, tmp_git_repo: Path):
        """get_git_root returns None when git lookup fails."""
        with patch(
            "session_buddy.utils.git_worktrees.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["git"]),
        ):
            assert get_git_root(tmp_git_repo) is None


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

    def test_get_git_status_handles_called_process_error(self, tmp_git_repo: Path):
        """get_git_status returns empty lists when git status fails."""
        with patch(
            "session_buddy.utils.git_worktrees.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["git"]),
        ):
            modified, untracked = get_git_status(tmp_git_repo)

        assert modified == []
        assert untracked == []


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

    def test_stage_files_handles_called_process_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_git_repo: Path
    ) -> None:
        """stage_files returns False when git add fails."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.subprocess.run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, ["git", "add", "-A"])
            ),
        )

        assert stage_files(tmp_git_repo, ["file.txt"]) is False

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

    def test_get_staged_files_handles_called_process_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_git_repo: Path
    ) -> None:
        """get_staged_files returns an empty list when git diff fails."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.subprocess.run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, ["git", "diff"])
            ),
        )

        assert get_staged_files(tmp_git_repo) == []


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

    def test_get_worktree_info_handles_detached_head(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """get_worktree_info formats detached HEAD state correctly."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_repository",
            lambda _directory: True,
        )
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_worktree",
            lambda _directory: True,
        )

        def fake_run(command: list[str], **kwargs: object) -> Mock:
            if command == ["git", "branch", "--show-current"]:
                return Mock(stdout="", returncode=0)
            if command == ["git", "rev-parse", "--short", "HEAD"]:
                return Mock(stdout="abc1234\n", returncode=0)
            if command == ["git", "rev-parse", "--show-toplevel"]:
                return Mock(stdout=f"{tmp_path}\n", returncode=0)
            raise AssertionError(f"Unexpected command: {command}")

        monkeypatch.setattr("session_buddy.utils.git_worktrees.subprocess.run", fake_run)

        info = get_worktree_info(tmp_path)

        assert info is not None
        assert info.is_detached is True
        assert info.branch == "HEAD (abc1234)"
        assert info.is_main_worktree is False

    def test_get_worktree_info_handles_called_process_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_git_repo: Path
    ) -> None:
        """get_worktree_info returns None when git lookups fail."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.subprocess.run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, ["git"])
            ),
        )

        assert get_worktree_info(tmp_git_repo) is None

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

    def test_list_worktrees_returns_empty_when_runner_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_git_repo: Path
    ) -> None:
        """list_worktrees returns an empty list when git worktree list fails."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees._run_git_worktree_list",
            lambda _directory: None,
        )

        assert list_worktrees(tmp_git_repo) == []

    def test_list_worktrees_returns_empty_when_runner_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_git_repo: Path
    ) -> None:
        """list_worktrees returns an empty list when git worktree list fails."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees._run_git_worktree_list",
            lambda _directory: None,
        )

        assert list_worktrees(tmp_git_repo) == []


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

    def test_validate_numeric_range_and_safe_pattern_helpers(self):
        """Helper validation functions handle the expected boundary cases."""
        assert _validate_numeric_range(1) == (True, "")
        assert _validate_numeric_range(1000) == (True, "")
        assert _validate_numeric_range(0) == (
            False,
            "Value too small: 0. Must be at least 1.",
        )
        assert _validate_numeric_range(1001) == (
            False,
            "Value too large: 1001. Maximum allowed is 1000.",
        )

        assert _matches_safe_pattern("now") == (True, "")
        assert _matches_safe_pattern("2.weeks") == (True, "")
        assert _matches_safe_pattern("bad") == (False, "")
        assert _matches_safe_pattern("9999.weeks") == (
            False,
            "Value too large: 9999. Maximum allowed is 1000.",
        )

    def test_matches_safe_pattern_handles_value_error(self, monkeypatch: pytest.MonkeyPatch):
        """_matches_safe_pattern handles invalid numeric conversions."""
        import re

        class FakeMatch:
            def group(self, _index: int) -> str:
                return "oops"

        monkeypatch.setattr(
            re,
            "match",
            lambda pattern, value, flags=0: FakeMatch()
            if "\\d+" in pattern and value == "1.weeks"
            else None,
        )
        assert _matches_safe_pattern("1.weeks") == (False, "Invalid numeric value in: 1.weeks")

    def test_process_worktree_line_and_parse_output(self, tmp_path: Path):
        """Worktree parsing helpers produce structured entries."""
        current: dict[str, object] = {}
        _process_worktree_line(f"worktree {tmp_path}", current)
        _process_worktree_line("HEAD abc123", current)
        _process_worktree_line("branch refs/heads/main", current)
        _process_worktree_line("bare", current)
        _process_worktree_line("detached", current)
        _process_worktree_line("locked", current)
        _process_worktree_line("prunable", current)

        assert current == {
            "path": str(tmp_path),
            "head": "abc123",
            "branch": "refs/heads/main",
            "bare": True,
            "detached": True,
            "locked": True,
            "prunable": True,
        }

        output = "\n".join(
            [
                f"worktree {tmp_path}",
                "HEAD abc123",
                "branch refs/heads/main",
                "",
            ]
        )
        parsed = _parse_worktree_list_output(output)
        assert len(parsed) == 1
        assert parsed[0].branch == "refs/heads/main"

        detached = _parse_worktree_list_output(
            "\n".join(
                [
                    f"worktree {tmp_path / 'wt'}",
                    "HEAD abc123",
                    "detached",
                    "locked",
                    "prunable",
                ]
            ),
        )
        assert detached[0].is_detached is True
        assert detached[0].locked is True

    def test_parse_worktree_entry_and_context_output(self, tmp_path: Path):
        """Worktree entry formatting and context output cover both branches."""
        entry = _parse_worktree_entry(
            {
                "path": str(tmp_path),
                "branch": "refs/heads/main",
                "bare": True,
                "detached": False,
                "locked": True,
                "prunable": False,
            }
        )
        assert entry.path == tmp_path
        assert entry.branch == "refs/heads/main"
        assert entry.is_main_worktree is True
        assert entry.is_bare is True

        output: list[str] = []
        _add_worktree_context_output(None, output)
        assert output == []

        output = []
        _add_worktree_context_output(
            WorktreeInfo(path=tmp_path, branch="feature", is_main_worktree=True),
            output,
        )
        _add_worktree_context_output(
            WorktreeInfo(path=tmp_path, branch="feature", is_main_worktree=False),
            output,
        )
        assert output == [
            "📝 Main repository on branch 'feature'",
            f"🌿 Worktree on branch 'feature' at {tmp_path}",
        ]

        missing = _parse_worktree_entry({})
        assert missing.branch == "unknown"
        assert missing.is_main_worktree is True

    def test_format_untracked_files_truncates_list(self):
        """Untracked file formatting limits the display list."""
        output = _format_untracked_files([f"file_{i}.txt" for i in range(12)])

        assert output[0] == "🆕 Untracked files found:"
        assert "file_0.txt" in output[1]
        assert output[-2].startswith("⚠️ Please manually review")
        assert any("... and 2 more" in line for line in output)

    def test_format_untracked_files_short_list(self):
        """Untracked file formatting omits truncation for short lists."""
        output = _format_untracked_files(["one.txt", "two.txt"])
        assert not any("more" in line for line in output)

    def test_check_for_changes_clean_and_dirty(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Change detection handles clean and dirty working trees."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.get_worktree_info",
            lambda _directory: None,
        )
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.get_git_status",
            lambda _directory: ([], []),
        )
        modified, untracked, output = _check_for_changes(tmp_path)
        assert modified == []
        assert untracked == []
        assert any("clean" in line.lower() for line in output)

        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.get_worktree_info",
            lambda _directory: WorktreeInfo(
                path=tmp_path,
                branch="feature",
                is_main_worktree=False,
            ),
        )
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.get_git_status",
            lambda _directory: (["modified.txt"], ["new.txt"]),
        )
        modified, untracked, output = _check_for_changes(tmp_path)
        assert modified == ["modified.txt"]
        assert untracked == ["new.txt"]
        assert any("Worktree on branch" in line for line in output)

    def test_check_for_changes_non_repo(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Change detection handles non-repo inputs."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_repository",
            lambda _directory: False,
        )
        modified, untracked, output = _check_for_changes(tmp_path)
        assert modified == []
        assert untracked == []
        assert output == ["✅ Working directory is clean - no changes to commit"]

    def test_perform_staging_and_commit_failure_paths(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """Staging and commit failures return explicit messages."""
        stage_fail = Mock(returncode=1, stderr="stage error")
        commit_fail = Mock(returncode=1, stderr="commit error")
        hash_ok = Mock(returncode=0, stdout="abcdef123456\n")

        runs = [stage_fail, commit_fail, hash_ok]
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.subprocess.run",
            lambda *args, **kwargs: runs.pop(0),
        )

        success, result, output = _perform_staging_and_commit(tmp_path, "proj", 77)
        assert success is False
        assert result == "staging failed"
        assert any("stage error" in line for line in output)

        runs = [Mock(returncode=0), commit_fail, hash_ok]
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.subprocess.run",
            lambda *args, **kwargs: runs.pop(0),
        )

        success, result, output = _perform_staging_and_commit(tmp_path, "proj", 77)
        assert success is False
        assert result == "commit failed"
        assert any("commit error" in line for line in output)

    def test_optimize_git_repository_branches(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """Optimization helper handles repo, busy, and non-repo branches."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_repository",
            lambda _directory: False,
        )
        assert _optimize_git_repository(tmp_path) == [
            "⚠️  Not a git repository, skipping optimization"
        ]

        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_repository",
            lambda _directory: True,
        )
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_operation_in_progress",
            lambda _directory: True,
        )
        assert _optimize_git_repository(tmp_path) == [
            "⚠️  Git operation in progress, skipping optimization"
        ]

        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_operation_in_progress",
            lambda _directory: False,
        )
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.schedule_automatic_git_gc",
            lambda **kwargs: (True, "scheduled"),
        )
        assert _optimize_git_repository(tmp_path) == ["scheduled"]

        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.schedule_automatic_git_gc",
            lambda **kwargs: (False, "failed"),
        )
        assert _optimize_git_repository(tmp_path) == ["❌ failed"]

    def test_optimize_git_repository_exception(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """Optimization helper handles scheduling exceptions."""
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_repository",
            lambda _directory: True,
        )
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.is_git_operation_in_progress",
            lambda _directory: False,
        )
        monkeypatch.setattr(
            "session_buddy.utils.git_worktrees.schedule_automatic_git_gc",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        with pytest.raises(RuntimeError, match="boom"):
            _optimize_git_repository(tmp_path)

    def test_schedule_automatic_git_gc_failure(self, tmp_git_repo: Path):
        """schedule_automatic_git_gc returns failure on unexpected errors."""
        with patch(
            "session_buddy.utils.git_worktrees.subprocess.run",
            return_value=Mock(returncode=0, stdout=""),
        ), patch(
            "session_buddy.utils.subprocess_executor.SafeSubprocess.popen_safe",
            side_effect=RuntimeError("boom"),
        ):
            success, message = schedule_automatic_git_gc(
                tmp_git_repo, prune_delay="now", auto_threshold=6700
            )
        assert success is False
        assert "boom" in message

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

    def test_schedule_automatic_git_gc_with_string_path(
        self, tmp_git_repo: Path
    ):
        """schedule_automatic_git_gc accepts string paths."""
        with patch(
            "session_buddy.utils.git_worktrees.subprocess.run",
            return_value=Mock(returncode=0, stdout=""),
        ), patch(
            "session_buddy.utils.subprocess_executor.SafeSubprocess.popen_safe",
            return_value=Mock(),
        ):
            success, message = schedule_automatic_git_gc(
                str(tmp_git_repo), prune_delay="now", auto_threshold=6700
            )
        assert success is True
        assert "Scheduled git gc" in message

    def test_validate_numeric_range_invalid(self):
        """_validate_numeric_range rejects out-of-range values."""
        assert _validate_numeric_range(1001) == (
            False,
            "Value too large: 1001. Maximum allowed is 1000.",
        )
