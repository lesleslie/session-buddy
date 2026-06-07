"""Unit tests for WorktreeManager v2.

Tests cover:
- Worktree creation with mocked git operations
- Worktree listing with real git repositories
- Worktree removal and cleanup
- Edge cases: no git, invalid worktrees, cleanup failures
- Async methods with pytest.mark.asyncio
- Session coordination methods
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from session_buddy.worktree_manager import (
    GitOperationResult,
    WorktreeCreationOptions,
    WorktreeManager,
    WorktreeValidationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def worktree_manager():
    """Create a WorktreeManager instance without logger."""
    return WorktreeManager()


@pytest.fixture
def worktree_manager_with_logger():
    """Create a WorktreeManager instance with mock logger."""
    mock_logger = Mock()
    return WorktreeManager(session_logger=mock_logger)


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        # Create initial commit
        readme = repo_path / "README.md"
        readme.write_text("# Test Repository")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        yield repo_path


@pytest.fixture
def temp_git_worktree(temp_git_repo):
    """Create a temporary git repository with a worktree."""
    repo_path = temp_git_repo
    worktree_path = repo_path.parent / f"{repo_path.name}-worktree"
    worktree_path.mkdir()

    # Add worktree
    subprocess.run(
        ["git", "worktree", "add", "-b", "feature/test", str(worktree_path)],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path, worktree_path

    # Cleanup: remove worktree
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_path,
            capture_output=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Dataclass Tests
# ---------------------------------------------------------------------------


class TestWorktreeCreationOptions:
    """Tests for WorktreeCreationOptions dataclass."""

    def test_default_options(self):
        """Test default creation options are all False."""
        opts = WorktreeCreationOptions()
        assert opts.create_branch is False
        assert opts.checkout_existing is False
        assert opts.force is False

    def test_custom_options(self):
        """Test custom creation options."""
        opts = WorktreeCreationOptions(
            create_branch=True,
            checkout_existing=True,
            force=True,
        )
        assert opts.create_branch is True
        assert opts.checkout_existing is True
        assert opts.force is True


class TestWorktreeValidationResult:
    """Tests for WorktreeValidationResult dataclass."""

    def test_success(self):
        """Test successful validation result."""
        result = WorktreeValidationResult.success()
        assert result.is_valid is True
        assert result.errors == []

    def test_error(self):
        """Test error validation result."""
        result = WorktreeValidationResult.error("Something went wrong")
        assert result.is_valid is False
        assert result.errors == ["Something went wrong"]

    def test_multiple_errors(self):
        """Test validation result with multiple errors."""
        result = WorktreeValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 2


class TestGitOperationResult:
    """Tests for GitOperationResult dataclass."""

    def test_success_result(self):
        """Test successful git operation result."""
        result = GitOperationResult.success_result("output here")
        assert result.success is True
        assert result.output == "output here"
        assert result.error == ""

    def test_error_result(self):
        """Test error git operation result."""
        result = GitOperationResult.error_result("command failed")
        assert result.success is False
        assert result.output == ""
        assert result.error == "command failed"

    def test_defaults(self):
        """Test default field values."""
        result = GitOperationResult(success=True)
        assert result.output == ""
        assert result.error == ""


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


class TestWorktreeManagerInit:
    """Tests for WorktreeManager initialization."""

    def test_init_without_logger(self, worktree_manager):
        """Test initialization without logger."""
        assert worktree_manager.session_logger is None

    def test_init_with_logger(self):
        """Test initialization with logger."""
        mock_logger = Mock()
        manager = WorktreeManager(session_logger=mock_logger)
        assert manager.session_logger is mock_logger

    def test_log_no_logger(self, worktree_manager):
        """Test _log doesn't raise when logger is None."""
        # Should not raise
        worktree_manager._log("message")
        worktree_manager._log("error", level="error")


# ---------------------------------------------------------------------------
# Security Validation Tests
# ---------------------------------------------------------------------------


class TestSecurityValidation:
    """Tests for security validation methods."""

    def test_get_git_executable(self, worktree_manager):
        """Test getting git executable path."""
        git_path = worktree_manager._get_git_executable()
        assert git_path is not None
        assert "git" in git_path

    def test_get_git_executable_not_found(self, worktree_manager):
        """Test error when git not found in PATH."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(OSError, match="Git executable not found"):
                worktree_manager._get_git_executable()

    def test_validate_git_command_valid(self, worktree_manager):
        """Test validation accepts valid git commands."""
        valid_cmds = [
            ["/usr/bin/git", "worktree", "list"],
            ["/usr/bin/git", "status"],
            ["/usr/bin/git", "add", "."],
            ["/usr/bin/git", "commit", "-m", "msg"],
            ["/usr/bin/git", "branch", "main"],
            ["/usr/bin/git", "checkout", "main"],
        ]
        for cmd in valid_cmds:
            assert worktree_manager._validate_git_command(cmd) is True, f"Failed for {cmd}"

    def test_validate_git_command_invalid(self, worktree_manager):
        """Test validation rejects invalid commands."""
        invalid_cmds = [
            [],  # Empty
            ["/usr/bin/git"],  # No subcommand
            ["/usr/bin/git", "eval"],  # Invalid subcommand
            ["/usr/bin/git", "worktree", "test; rm -rf"],  # Injection
            ["/usr/bin/git", "worktree", "test&whoami"],  # Chaining
            ["/usr/bin/git", "worktree", "test|cat"],  # Pipe
            ["/usr/bin/git", "worktree", "test`id`"],  # Backticks
            ["/usr/bin/git", "worktree", "test$(id)"],  # Substitution
            ["/usr/bin/git", "worktree", "test\\\necho"],  # Newline
        ]
        for cmd in invalid_cmds:
            assert worktree_manager._validate_git_command(cmd) is False, f"Should reject: {cmd}"

    def test_is_safe_branch_name_valid(self, worktree_manager):
        """Test safe branch names pass validation."""
        safe_branches = [
            "main",
            "feature/new",
            "bugfix/issue-123",
            "develop",
            "feature_user_auth",
            "a" * 99,  # Max length
            # Note: dots are NOT allowed by the current regex
            # "release-1.0.0" would be invalid even though git allows it
        ]
        for branch in safe_branches:
            assert worktree_manager._is_safe_branch_name(branch) is True, f"Should accept: {branch}"

    def test_is_safe_branch_name_invalid(self, worktree_manager):
        """Test unsafe branch names are rejected."""
        unsafe_branches = [
            "main;rm -rf",  # Semicolon
            "test&whoami",  # Ampersand
            "test|cat",  # Pipe
            "test`id`",  # Backticks
            "test$(id)",  # Command substitution
            "a" * 100,  # Too long
            "..parent",  # Parent directory reference
            "main..parent",  # Path-traversal style name (two consecutive dots)
        ]
        for branch in unsafe_branches:
            assert worktree_manager._is_safe_branch_name(branch) is False, f"Should reject: {branch}"

    def test_is_safe_path_valid(self, worktree_manager):
        """Test safe paths pass validation."""
        safe_paths = [
            Path("/tmp/worktree"),
            Path("/home/user/project"),
            Path("./relative"),
            Path("."),
        ]
        for path in safe_paths:
            assert worktree_manager._is_safe_path(path) is True, f"Should accept: {path}"

    def test_is_safe_path_invalid(self, worktree_manager):
        """Test unsafe paths are rejected."""
        unsafe_paths = [
            Path("/tmp/..\\etc"),
            Path("/tmp/test\x00"),  # Null byte
        ]
        for path in unsafe_paths:
            assert worktree_manager._is_safe_path(path) is False, f"Should reject: {path}"

    def test_is_safe_path_too_long(self, worktree_manager):
        """Test excessively long paths are rejected."""
        long_path = Path("/tmp/" + "a" * 500)
        assert worktree_manager._is_safe_path(long_path) is False


# ---------------------------------------------------------------------------
# Validation Method Tests
# ---------------------------------------------------------------------------


class TestValidationMethod:
    """Tests for _validate_worktree_creation_request method."""

    def test_not_git_repository(self, worktree_manager, tmp_path):
        """Test validation fails when source is not a git repo."""
        result = worktree_manager._validate_worktree_creation_request(
            tmp_path,
            tmp_path / "new",
            "feature/test",
        )
        assert result.is_valid is False
        assert "not a git repository" in result.errors[0]

    def test_target_path_exists(self, worktree_manager, temp_git_repo):
        """Test validation fails when target path already exists."""
        result = worktree_manager._validate_worktree_creation_request(
            temp_git_repo,
            temp_git_repo / "README.md",  # Already exists
            "feature/test",
        )
        assert result.is_valid is False
        assert "already exists" in result.errors[0]

    def test_invalid_branch_name(self, worktree_manager, temp_git_repo):
        """Test validation fails with invalid branch name."""
        result = worktree_manager._validate_worktree_creation_request(
            temp_git_repo,
            temp_git_repo.parent / "new_worktree",
            "invalid;rm -rf",
        )
        assert result.is_valid is False
        assert "Invalid branch name" in result.errors[0]

    def test_valid_request(self, worktree_manager, temp_git_repo):
        """Test validation passes for valid request."""
        result = worktree_manager._validate_worktree_creation_request(
            temp_git_repo,
            temp_git_repo.parent / "new_worktree",
            "feature/valid",
        )
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Command Building Tests
# ---------------------------------------------------------------------------


class TestCommandBuilding:
    """Tests for command building methods."""

    def test_build_worktree_command_basic(self, worktree_manager, tmp_path):
        """Test building basic worktree command."""
        options = WorktreeCreationOptions()
        cmd = worktree_manager._build_worktree_command(
            tmp_path / "wt",
            "main",
            options,
        )
        assert "git" in cmd[0]
        assert "worktree" in cmd
        assert "add" in cmd

    def test_build_worktree_command_with_branch(self, worktree_manager, tmp_path):
        """Test building worktree command with -b flag."""
        options = WorktreeCreationOptions(create_branch=True)
        cmd = worktree_manager._build_worktree_command(
            tmp_path / "wt",
            "feature/new",
            options,
        )
        assert "-b" in cmd
        assert "feature/new" in cmd

    def test_build_worktree_command_track_existing(self, worktree_manager, tmp_path):
        """Test building worktree command with --track -B flags."""
        options = WorktreeCreationOptions(checkout_existing=True)
        cmd = worktree_manager._build_worktree_command(
            tmp_path / "wt",
            "main",
            options,
        )
        assert "--track" in cmd
        assert "-B" in cmd


# ---------------------------------------------------------------------------
# Async Method Tests - List Worktrees
# ---------------------------------------------------------------------------


class TestListWorktrees:
    """Tests for list_worktrees async method."""

    @pytest.mark.asyncio
    async def test_list_worktrees_not_git_repo(self, worktree_manager, tmp_path):
        """Test listing worktrees when directory is not a git repo."""
        result = await worktree_manager.list_worktrees(tmp_path)
        assert result["success"] is False
        assert "Not a git repository" in result["error"]

    @pytest.mark.asyncio
    async def test_list_worktrees_empty(self, worktree_manager, temp_git_repo):
        """Test listing worktrees in a repo with only main worktree."""
        result = await worktree_manager.list_worktrees(temp_git_repo)
        assert result["success"] is True
        assert result["total_count"] >= 1  # At least main worktree
        assert len(result["worktrees"]) >= 1

    @pytest.mark.asyncio
    async def test_list_worktrees_with_worktree(self, worktree_manager, temp_git_worktree):
        """Test listing worktrees when worktrees exist."""
        repo_path, _ = temp_git_worktree
        result = await worktree_manager.list_worktrees(repo_path)
        assert result["success"] is True
        assert result["total_count"] >= 2  # Main + feature/worktree

    @pytest.mark.asyncio
    async def test_list_worktrees_exception(self, worktree_manager, temp_git_repo):
        """Test handling exception during listing."""
        with patch(
            "session_buddy.worktree_manager.list_worktrees",
            side_effect=Exception("Simulated error"),
        ):
            result = await worktree_manager.list_worktrees(temp_git_repo)
            assert result["success"] is False
            assert "Simulated error" in result["error"]


# ---------------------------------------------------------------------------
# Async Method Tests - Create Worktree
# ---------------------------------------------------------------------------


class TestCreateWorktree:
    """Tests for create_worktree async method."""

    @pytest.mark.asyncio
    async def test_create_worktree_validation_failure(self, worktree_manager, tmp_path):
        """Test worktree creation fails validation."""
        result = await worktree_manager.create_worktree(
            tmp_path,  # Not a git repo
            tmp_path / "new",
            "feature/test",
        )
        assert result["success"] is False
        assert "not a git repository" in result["error"]

    @pytest.mark.asyncio
    async def test_create_worktree_invalid_branch(self, worktree_manager, temp_git_repo):
        """Test worktree creation fails with invalid branch name."""
        result = await worktree_manager.create_worktree(
            temp_git_repo,
            temp_git_repo.parent / "new_wt",
            "invalid;rm -rf",
        )
        assert result["success"] is False
        assert "Invalid branch name" in result["error"]

    @pytest.mark.asyncio
    async def test_create_worktree_subprocess_error(self, worktree_manager, temp_git_repo):
        """Test worktree creation handles subprocess errors."""
        new_path = temp_git_repo.parent / "new_wt"

        # Mock _validate_git_command to return True
        # but make _execute_worktree_creation fail
        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch.object(
            worktree_manager,
            "_execute_worktree_creation",
            side_effect=subprocess.CalledProcessError(
                1, "git",
                stderr="fatal: 'new_wt' already exists",
            ),
        ):
            result = await worktree_manager.create_worktree(
                temp_git_repo,
                new_path,
                "feature/test",
            )
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_create_worktree_success(self, worktree_manager, temp_git_repo):
        """Test successful worktree creation."""
        new_path = temp_git_repo.parent / "test_wt_branch"

        # Mock the verification to succeed
        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch.object(
            worktree_manager,
            "_execute_worktree_creation",
            return_value=MagicMock(stdout="Creating worktree...", stderr=""),
        ), patch(
            "session_buddy.worktree_manager.get_worktree_info",
            return_value=MagicMock(
                path=new_path,
                branch="test_wt_branch",
                is_main_worktree=False,
                is_detached=False,
            ),
        ):
            result = await worktree_manager.create_worktree(
                temp_git_repo,
                new_path,
                "test_wt_branch",
                create_branch=True,
            )
            assert result["success"] is True
            assert result["branch"] == "test_wt_branch"


# ---------------------------------------------------------------------------
# Async Method Tests - Remove Worktree
# ---------------------------------------------------------------------------


class TestRemoveWorktree:
    """Tests for remove_worktree async method."""

    @pytest.mark.asyncio
    async def test_remove_worktree_not_git_repo(self, worktree_manager, tmp_path):
        """Test removing worktree from non-git directory fails."""
        result = await worktree_manager.remove_worktree(tmp_path, tmp_path / "wt")
        assert result["success"] is False
        assert "not a git repository" in result["error"]

    @pytest.mark.asyncio
    async def test_remove_worktree_success(self, worktree_manager, temp_git_worktree):
        """Test successful worktree removal."""
        repo_path, wt_path = temp_git_worktree

        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch(
            "subprocess.run",
            return_value=MagicMock(
                returncode=0,
                stdout="Removing worktree...",
                stderr="",
            ),
        ):
            result = await worktree_manager.remove_worktree(
                repo_path,
                wt_path,
                force=True,
            )
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_remove_worktree_subprocess_error(self, worktree_manager, temp_git_worktree):
        """Test worktree removal handles subprocess errors."""
        repo_path, wt_path = temp_git_worktree

        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(
                1, "git",
                stderr="fatal: worktree not found",
            ),
        ):
            result = await worktree_manager.remove_worktree(repo_path, wt_path)
            assert result["success"] is False
            assert "worktree not found" in result["error"]

    @pytest.mark.asyncio
    async def test_remove_worktree_security_rejection(self, worktree_manager, temp_git_repo):
        """Test worktree removal rejected by security validation."""
        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=False,
        ):
            result = await worktree_manager.remove_worktree(
                temp_git_repo,
                temp_git_repo.parent / "nonexistent",
            )
            assert result["success"] is False
            assert "security" in result["error"].lower()


# ---------------------------------------------------------------------------
# Async Method Tests - Prune Worktrees
# ---------------------------------------------------------------------------


class TestPruneWorktrees:
    """Tests for prune_worktrees async method."""

    @pytest.mark.asyncio
    async def test_prune_not_git_repo(self, worktree_manager, tmp_path):
        """Test pruning fails when directory is not a git repo."""
        result = await worktree_manager.prune_worktrees(tmp_path)
        assert result["success"] is False
        assert "not a git repository" in result["error"]

    @pytest.mark.asyncio
    async def test_prune_success(self, worktree_manager, temp_git_repo):
        """Test successful worktree pruning."""
        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch(
            "subprocess.run",
            return_value=MagicMock(
                returncode=0,
                stdout="Removing pruned worktree",
                stderr="",
            ),
        ):
            result = await worktree_manager.prune_worktrees(temp_git_repo)
            assert result["success"] is True
            assert "pruned_count" in result

    @pytest.mark.asyncio
    async def test_prune_subprocess_error(self, worktree_manager, temp_git_repo):
        """Test pruning handles subprocess errors."""
        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git", stderr="error"),
        ):
            result = await worktree_manager.prune_worktrees(temp_git_repo)
            assert result["success"] is False
            assert "error" in result["error"]


# ---------------------------------------------------------------------------
# Async Method Tests - Worktree Status
# ---------------------------------------------------------------------------


class TestGetWorktreeStatus:
    """Tests for get_worktree_status async method."""

    @pytest.mark.asyncio
    async def test_status_not_git_repo(self, worktree_manager, tmp_path):
        """Test status fails when directory is not a git repo."""
        result = await worktree_manager.get_worktree_status(tmp_path)
        assert result["success"] is False
        assert "Not a git repository" in result["error"]

    @pytest.mark.asyncio
    async def test_status_success(self, worktree_manager, temp_git_repo):
        """Test successful status retrieval."""
        result = await worktree_manager.get_worktree_status(temp_git_repo)
        assert result["success"] is True
        assert "current_worktree" in result
        assert "all_worktrees" in result
        assert result["total_worktrees"] >= 1

    @pytest.mark.asyncio
    async def test_status_no_current_info(self, worktree_manager, temp_git_repo):
        """Test status when current worktree info unavailable."""
        with patch(
            "session_buddy.worktree_manager.get_worktree_info",
            return_value=None,
        ):
            result = await worktree_manager.get_worktree_status(temp_git_repo)
            assert result["success"] is False
            assert "Could not determine" in result["error"]

    @pytest.mark.asyncio
    async def test_status_exception(self, worktree_manager, temp_git_repo):
        """Test status handles exceptions."""
        with patch(
            "session_buddy.worktree_manager.list_worktrees",
            side_effect=Exception("Simulated failure"),
        ):
            result = await worktree_manager.get_worktree_status(temp_git_repo)
            assert result["success"] is False
            assert "Simulated failure" in result["error"]


# ---------------------------------------------------------------------------
# Session Coordination Tests
# ---------------------------------------------------------------------------


class TestSessionCoordination:
    """Tests for session coordination methods."""

    def test_check_session_exists_no_path(self, worktree_manager, tmp_path):
        """Test _check_session_exists returns False for non-existent path."""
        assert worktree_manager._check_session_exists(tmp_path / "nonexistent") is False

    def test_check_session_exists_string_arg(self, worktree_manager, tmp_path):
        """Test _check_session_exists handles string argument."""
        assert worktree_manager._check_session_exists(str(tmp_path / "nonexistent")) is False

    def test_check_session_exists_with_project_files(self, worktree_manager, temp_git_repo):
        """Test _check_session_exists detects project files."""
        # Create a project file
        (temp_git_repo / "pyproject.toml").touch()
        assert worktree_manager._check_session_exists(temp_git_repo) is True

    def test_get_session_summary(self, worktree_manager):
        """Test _get_session_summary aggregates correctly."""
        from session_buddy.utils.git_worktrees import WorktreeInfo

        worktrees = [
            WorktreeInfo(Path("/tmp/wt1"), "main"),
            WorktreeInfo(Path("/tmp/wt2"), "feature"),
            WorktreeInfo(Path("/tmp/wt3"), "main"),
        ]
        # Mock _check_session_exists to return True for all
        with patch.object(
            worktree_manager,
            "_check_session_exists",
            return_value=True,
        ):
            summary = worktree_manager._get_session_summary(worktrees)
            assert summary["active_sessions"] == 3
            assert summary["unique_branches"] == 2
            assert "main" in summary["branches"]
            assert "feature" in summary["branches"]

    def test_save_current_session_state(self, worktree_manager, tmp_path):
        """Test _save_current_session_state creates state file."""
        state = worktree_manager._save_current_session_state(tmp_path)
        assert state is not None
        assert "timestamp" in state
        assert "worktree_path" in state


# ---------------------------------------------------------------------------
# Async Method Tests - Switch Worktree Context
# ---------------------------------------------------------------------------


class TestSwitchWorktreeContext:
    """Tests for switch_worktree_context async method."""

    @pytest.mark.asyncio
    async def test_switch_from_not_git_repo(self, worktree_manager, temp_git_repo):
        """Test switch fails when source is not git repo."""
        result = await worktree_manager.switch_worktree_context(
            Path("/not/git"),
            temp_git_repo,
        )
        assert result["success"] is False
        assert "not a git repository" in result["error"]

    @pytest.mark.asyncio
    async def test_switch_to_not_git_repo(self, worktree_manager, temp_git_repo):
        """Test switch fails when target is not git repo."""
        result = await worktree_manager.switch_worktree_context(
            temp_git_repo,
            Path("/not/git"),
        )
        assert result["success"] is False
        assert "not a git repository" in result["error"]

    @pytest.mark.asyncio
    async def test_switch_success(self, worktree_manager, temp_git_worktree):
        """Test successful context switch between worktrees."""
        repo_path, wt_path = temp_git_worktree

        with patch.object(
            worktree_manager,
            "_save_current_session_state",
            return_value={"timestamp": "2024-01-01"},
        ), patch.object(
            worktree_manager,
            "_restore_session_state",
            return_value=True,
        ):
            # Mock os.chdir to avoid actually changing directory
            with patch("os.chdir"):
                result = await worktree_manager.switch_worktree_context(
                    repo_path,
                    wt_path,
                )
                assert result["success"] is True
                assert "from_worktree" in result
                assert "to_worktree" in result
                assert result["session_state_saved"] is True
                assert result["session_state_restored"] is True

    @pytest.mark.asyncio
    async def test_switch_session_preservation_fails(self, worktree_manager, temp_git_worktree):
        """Test switch falls back when session preservation fails."""
        repo_path, wt_path = temp_git_worktree

        with patch.object(
            worktree_manager,
            "_save_current_session_state",
            side_effect=Exception("Save failed"),
        ), patch("os.chdir"):
            result = await worktree_manager.switch_worktree_context(
                repo_path,
                wt_path,
            )
            assert result["success"] is True
            assert "session_error" in result
            assert result["context_preserved"] is False


# ---------------------------------------------------------------------------
# Execute Git Worktree Creation Tests
# ---------------------------------------------------------------------------


class TestExecuteGitWorktreeCreation:
    """Tests for _execute_git_worktree_creation async method."""

    @pytest.mark.asyncio
    async def test_security_rejection(self, worktree_manager, tmp_path):
        """Test command rejected by security validation."""
        options = WorktreeCreationOptions(create_branch=True)

        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=False,
        ):
            result = await worktree_manager._execute_git_worktree_creation(
                tmp_path / "wt",
                "feature/test",
                options,
                tmp_path,
            )
            assert result.success is False
            assert "security" in result.error.lower()

    @pytest.mark.asyncio
    async def test_subprocess_error(self, worktree_manager, tmp_path):
        """Test handles subprocess errors."""
        options = WorktreeCreationOptions()

        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch.object(
            worktree_manager,
            "_execute_worktree_creation",
            side_effect=subprocess.CalledProcessError(
                1, "git",
                stderr="fatal: worktree exists",
            ),
        ):
            result = await worktree_manager._execute_git_worktree_creation(
                tmp_path / "wt",
                "main",
                options,
                tmp_path,
            )
            assert result.success is False
            assert "worktree exists" in result.error

    @pytest.mark.asyncio
    async def test_unexpected_error(self, worktree_manager, tmp_path):
        """Test handles unexpected errors."""
        options = WorktreeCreationOptions()

        with patch.object(
            worktree_manager,
            "_validate_git_command",
            return_value=True,
        ), patch.object(
            worktree_manager,
            "_execute_worktree_creation",
            side_effect=RuntimeError("Unexpected"),
        ):
            result = await worktree_manager._execute_git_worktree_creation(
                tmp_path / "wt",
                "main",
                options,
                tmp_path,
            )
            assert result.success is False
            assert "Unexpected" in result.error


# ---------------------------------------------------------------------------
# Verify Worktree Creation Tests
# ---------------------------------------------------------------------------


class TestVerifyWorktreeCreation:
    """Tests for _verify_worktree_creation method."""

    def test_verify_nonexistent_worktree(self, worktree_manager, tmp_path):
        """Test verification fails for nonexistent worktree."""
        result = worktree_manager._verify_worktree_creation(tmp_path / "nonexistent")
        assert result.success is False
        assert "cannot be accessed" in result.error

    def test_verify_existing_worktree(self, worktree_manager, temp_git_worktree):
        """Test verification succeeds for existing worktree."""
        _, wt_path = temp_git_worktree
        result = worktree_manager._verify_worktree_creation(wt_path)
        assert result.success is True


# ---------------------------------------------------------------------------
# Build Success Response Tests
# ---------------------------------------------------------------------------


class TestBuildSuccessResponse:
    """Tests for _build_success_response_from_info method."""

    def test_build_response(self, worktree_manager, tmp_path):
        """Test building success response."""
        from session_buddy.utils.git_worktrees import WorktreeInfo

        worktree_info = WorktreeInfo(
            path=tmp_path / "wt",
            branch="feature/test",
            is_main_worktree=False,
            is_detached=False,
        )

        response = worktree_manager._build_success_response_from_info(
            tmp_path / "wt",
            "feature/test",
            worktree_info,
            "output here",
        )

        assert response["success"] is True
        assert response["branch"] == "feature/test"
        assert response["output"] == "output here"
        assert "worktree_info" in response


# ---------------------------------------------------------------------------
# Logging Tests
# ---------------------------------------------------------------------------


class TestLogging:
    """Tests for logging functionality."""

    def test_log_with_logger(self, worktree_manager_with_logger):
        """Test logging with logger attached."""
        manager = worktree_manager_with_logger
        manager._log("Test message", level="info", key="value")

        manager.session_logger.info.assert_called_once_with(
            "Test message",
            key="value",
        )

    def test_log_error_level(self, worktree_manager_with_logger):
        """Test logging at error level."""
        manager = worktree_manager_with_logger
        manager._log("Error occurred", level="error", code=500)

        manager.session_logger.error.assert_called_once_with(
            "Error occurred",
            code=500,
        )

    def test_log_warning_level(self, worktree_manager_with_logger):
        """Test logging at warning level."""
        manager = worktree_manager_with_logger
        manager._log("Warning", level="warning")

        manager.session_logger.warning.assert_called_once()

    def test_log_no_logger(self, worktree_manager):
        """Test logging doesn't raise when logger is None."""
        # Should not raise
        worktree_manager._log("message")
        worktree_manager._log("error", level="error")
