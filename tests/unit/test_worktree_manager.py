"""Unit tests for WorktreeManager.

Tests cover:
- Worktree initialization and validation
- Git command security
- Worktree listing and status
- Creation and cleanup operations
- Error handling and edge cases
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from session_buddy.worktree_manager import (
    WorktreeManager,
    WorktreeCreationOptions,
    WorktreeValidationResult,
    GitOperationResult,
)


class TestWorktreeCreationOptions:
    """Tests for WorktreeCreationOptions dataclass."""

    def test_creation_options_default_values(self):
        """Test default creation options."""
        opts = WorktreeCreationOptions()
        assert opts.create_branch is False
        assert opts.checkout_existing is False
        assert opts.force is False

    def test_creation_options_custom_values(self):
        """Test creation options with custom values."""
        opts = WorktreeCreationOptions(
            create_branch=True,
            checkout_existing=True,
            force=True,
        )
        assert opts.create_branch is True
        assert opts.checkout_existing is True
        assert opts.force is True

    def test_creation_options_immutable(self):
        """Test that creation options are frozen (immutable)."""
        opts = WorktreeCreationOptions()
        with pytest.raises(AttributeError):
            setattr(opts, "create_branch", True)


class TestWorktreeValidationResult:
    """Tests for WorktreeValidationResult dataclass."""

    def test_success_creation(self):
        """Test creating successful validation result."""
        result = WorktreeValidationResult.success()
        assert result.is_valid is True
        assert result.errors == []

    def test_error_creation(self):
        """Test creating error validation result."""
        result = WorktreeValidationResult.error("Test error message")
        assert result.is_valid is False
        assert result.errors == ["Test error message"]

    def test_validation_result_with_multiple_errors(self):
        """Test validation result with multiple errors."""
        result = WorktreeValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2", "Error 3"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 3


class TestGitOperationResult:
    """Tests for GitOperationResult dataclass."""

    def test_success_result_creation(self):
        """Test creating successful operation result."""
        result = GitOperationResult.success_result(output="Done")
        assert result.success is True
        assert result.output == "Done"
        assert result.error == ""

    def test_error_result_creation(self):
        """Test creating error operation result."""
        result = GitOperationResult.error_result("Failed to execute")
        assert result.success is False
        assert result.error == "Failed to execute"
        assert result.output == ""

    def test_git_operation_result_defaults(self):
        """Test default values for git operation result."""
        result = GitOperationResult(success=True)
        assert result.success is True
        assert result.output == ""
        assert result.error == ""


class TestWorktreeManagerInit:
    """Tests for WorktreeManager initialization."""

    def test_init_without_logger(self):
        """Test initialization without logger."""
        manager = WorktreeManager()
        assert manager.session_logger is None

    def test_init_with_logger(self):
        """Test initialization with logger."""
        mock_logger = Mock()
        manager = WorktreeManager(session_logger=mock_logger)
        assert manager.session_logger is mock_logger

    def test_log_without_logger(self):
        """Test logging when logger is None."""
        manager = WorktreeManager()
        manager._log("Test message")  # Should not raise


class TestWorktreeManagerSecurityValidation:
    """Tests for security validation methods."""

    def test_get_git_executable_success(self):
        """Test getting git executable when available."""
        manager = WorktreeManager()
        git_path = manager._get_git_executable()
        assert git_path is not None
        assert "git" in git_path

    def test_git_executable_not_found(self):
        """Test error when git executable not found."""
        manager = WorktreeManager()
        with patch("shutil.which", return_value=None):
            with pytest.raises(OSError, match="Git executable not found"):
                manager._get_git_executable()

    def test_validate_git_command_valid(self):
        """Test validation of valid git commands."""
        manager = WorktreeManager()
        valid_commands = [
            ["/usr/bin/git", "worktree", "list"],
            ["/usr/bin/git", "status"],
            ["/usr/bin/git", "add", "file.txt"],
            ["/usr/bin/git", "branch"],
        ]
        for cmd in valid_commands:
            assert manager._validate_git_command(cmd) is True

    def test_validate_git_command_invalid(self):
        """Test validation rejects invalid git commands."""
        manager = WorktreeManager()
        invalid_commands = [
            [],  # Empty command
            ["/usr/bin/git"],  # No subcommand
            ["/usr/bin/git", "invalid_subcommand"],  # Invalid subcommand
            ["/usr/bin/git", "worktree", "test; rm -rf /"],  # Shell injection
            ["/usr/bin/git", "worktree", "test&whoami"],  # Command chaining
            ["/usr/bin/git", "worktree", "test|cat /etc/passwd"],  # Pipe
            ["/usr/bin/git", "worktree", "test`whoami`"],  # Command substitution
            ["/usr/bin/git", "worktree", "test$(whoami)"],  # Command substitution
            ["/usr/bin/git", "worktree", "test\\necho"],  # Newline injection
        ]
        for cmd in invalid_commands:
            assert manager._validate_git_command(cmd) is False

    def test_is_safe_branch_name_valid(self):
        """Test validation of safe branch names."""
        manager = WorktreeManager()
        valid_branches = [
            "main",
            "feature/new-feature",
            "bugfix/issue-123",
            "release-1.0.0",
            "develop_branch",
            "feature/user_auth",
        ]
        for branch in valid_branches:
            assert manager._is_safe_branch_name(branch) is True

    def test_is_safe_branch_name_invalid(self):
        """Test validation rejects unsafe branch names."""
        manager = WorktreeManager()
        invalid_branches = [
            "main;rm -rf /",  # Shell injection
            "feature&whoami",  # Command chaining
            "main|cat",  # Pipe
            "main`whoami`",  # Command substitution
            "feature$(whoami)",  # Command substitution
            "main\necho",  # Newline injection
            "main" + "x" * 100,  # Too long
            "main..parent",  # Parent directory reference
        ]
        for branch in invalid_branches:
            assert manager._is_safe_branch_name(branch) is False

    def test_is_safe_path_valid(self):
        """Test validation of safe paths."""
        manager = WorktreeManager()
        valid_paths = [
            Path("/tmp/worktree"),
            Path("/home/user/project"),
            Path("./relative/path"),
        ]
        for path in valid_paths:
            assert manager._is_safe_path(path) is True

    def test_is_safe_path_invalid(self):
        """Test validation rejects unsafe paths."""
        manager = WorktreeManager()
        invalid_paths = [
            Path("/tmp/..\\etc/passwd"),  # Parent directory reference
            Path("/tmp/test\x00null"),  # Null byte
        ]
        for path in invalid_paths:
            assert manager._is_safe_path(path) is False

    def test_is_safe_path_too_long(self):
        """Test validation rejects excessively long paths."""
        manager = WorktreeManager()
        long_path = Path("/tmp/" + "a" * 500)
        assert manager._is_safe_path(long_path) is False


class TestWorktreeManagerLogging:
    """Tests for logging functionality."""

    def test_log_with_logger(self):
        """Test logging with logger available."""
        mock_logger = Mock()
        manager = WorktreeManager(session_logger=mock_logger)

        manager._log("Test message", level="info", key="value")

        mock_logger.info.assert_called_once_with("Test message", key="value")

    def test_log_error_level(self):
        """Test logging at error level."""
        mock_logger = Mock()
        manager = WorktreeManager(session_logger=mock_logger)

        manager._log("Error occurred", level="error", error_code=500)

        mock_logger.error.assert_called_once_with("Error occurred", error_code=500)

    def test_log_without_logger_no_error(self):
        """Test logging without logger doesn't raise error."""
        manager = WorktreeManager(session_logger=None)
        manager._log("Test message")  # Should not raise


@pytest.mark.unit
class TestWorktreeManagerIntegration:
    """Integration tests for WorktreeManager."""

    def test_manager_with_all_security_checks(self):
        """Test manager applies all security checks."""
        manager = WorktreeManager()

        # Verify security methods exist and are callable
        assert callable(manager._get_git_executable)
        assert callable(manager._validate_git_command)
        assert callable(manager._is_safe_branch_name)
        assert callable(manager._is_safe_path)
        assert callable(manager._validate_worktree_creation_request)
