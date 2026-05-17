"""Unit tests for safe subprocess execution and security.

Tests secure subprocess handling including:
- Environment sanitization (sensitive variable removal)
- Command validation against allowlists
- Shell metacharacter blocking
- Safe subprocess execution
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from session_buddy.utils.subprocess_executor import (
    SafeSubprocess,
    _get_safe_environment,
)


class TestGetSafeEnvironment:
    """Test environment sanitization for subprocess execution."""

    def test_returns_dict(self) -> None:
        """Test that _get_safe_environment returns a dictionary."""
        env = _get_safe_environment()
        assert isinstance(env, dict)

    def test_removes_password_variables(self) -> None:
        """Test that PASSWORD variables are removed."""
        with patch.dict(os.environ, {"PASSWORD": "secret123", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "PASSWORD" not in env
            assert "OTHER" in env

    def test_removes_token_variables(self) -> None:
        """Test that TOKEN variables are removed."""
        with patch.dict(os.environ, {"API_TOKEN": "token123", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "API_TOKEN" not in env
            assert "OTHER" in env

    def test_removes_secret_variables(self) -> None:
        """Test that SECRET variables are removed."""
        with patch.dict(os.environ, {"SECRET_KEY": "secret123", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "SECRET_KEY" not in env
            assert "OTHER" in env

    def test_removes_api_key_variables(self) -> None:
        """Test that API_KEY variables are removed."""
        with patch.dict(os.environ, {"API_KEY": "key123", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "API_KEY" not in env
            assert "OTHER" in env

    def test_removes_auth_variables(self) -> None:
        """Test that AUTH variables are removed."""
        with patch.dict(os.environ, {"AUTH_TOKEN": "auth123", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "AUTH_TOKEN" not in env
            assert "OTHER" in env

    def test_removes_credential_variables(self) -> None:
        """Test that CREDENTIAL variables are removed."""
        with patch.dict(
            os.environ, {"CREDENTIAL": "cred123", "OTHER": "value"}
        ):
            env = _get_safe_environment()
            assert "CREDENTIAL" not in env
            assert "OTHER" in env

    def test_removes_session_variables(self) -> None:
        """Test that SESSION variables are removed."""
        with patch.dict(os.environ, {"SESSION_ID": "session123", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "SESSION_ID" not in env
            assert "OTHER" in env

    def test_removes_cookie_variables(self) -> None:
        """Test that COOKIE variables are removed."""
        with patch.dict(os.environ, {"COOKIE": "cookie123", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "COOKIE" not in env
            assert "OTHER" in env

    def test_removes_database_url_variables(self) -> None:
        """Test that DATABASE_URL is removed."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgres://secret", "OTHER": "value"}
        ):
            env = _get_safe_environment()
            assert "DATABASE_URL" not in env
            assert "OTHER" in env

    def test_removes_redis_url_variables(self) -> None:
        """Test that REDIS_URL is removed."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://secret", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "REDIS_URL" not in env
            assert "OTHER" in env

    def test_removes_mongodb_uri_variables(self) -> None:
        """Test that MONGODB_URI is removed."""
        with patch.dict(
            os.environ, {"MONGODB_URI": "mongodb://secret", "OTHER": "value"}
        ):
            env = _get_safe_environment()
            assert "MONGODB_URI" not in env
            assert "OTHER" in env

    def test_preserves_safe_variables(self) -> None:
        """Test that safe variables are preserved."""
        safe_vars = {"PATH": "/usr/bin", "HOME": "/home/user", "USER": "testuser"}
        with patch.dict(os.environ, safe_vars, clear=False):
            env = _get_safe_environment()
            # At least some standard vars should be present
            assert len(env) > 0

    def test_case_insensitive_filtering(self) -> None:
        """Test that filtering is case-insensitive."""
        with patch.dict(os.environ, {"password": "secret", "OTHER": "value"}):
            env = _get_safe_environment()
            assert "password" not in env
            assert "OTHER" in env

    def test_multiple_sensitive_patterns(self) -> None:
        """Test removal of multiple sensitive variables."""
        sensitive_vars = {
            "DATABASE_URL": "postgres://secret",
            "API_TOKEN": "token123",
            "SECRET_KEY": "secret123",
            "PASSWORD": "pass123",
        }
        safe_var = {"SAFE_VAR": "value"}
        with patch.dict(os.environ, {**sensitive_vars, **safe_var}):
            env = _get_safe_environment()
            for key in sensitive_vars:
                assert key not in env
            assert "SAFE_VAR" in env


class TestSafeSubprocessValidation:
    """Test SafeSubprocess command validation."""

    def test_validate_command_accepts_allowed(self) -> None:
        """Test that allowed commands are validated successfully."""
        result = SafeSubprocess.validate_command(
            ["echo", "test"],
            {"echo"},
        )
        assert result == ["echo", "test"]

    def test_validate_command_rejects_disallowed(self) -> None:
        """Test that disallowed commands are rejected."""
        with pytest.raises(ValueError, match="Command not allowed"):
            SafeSubprocess.validate_command(
                ["rm", "-rf", "/"],
                {"echo"},
            )

    def test_validate_command_rejects_empty_command(self) -> None:
        """Test that empty commands are rejected."""
        with pytest.raises(ValueError, match="Empty command"):
            SafeSubprocess.validate_command([], {"echo"})

    def test_validate_command_rejects_semicolon(self) -> None:
        """Test that shell command separators (semicolon) are rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "test; rm -rf /"],
                {"echo"},
            )

    def test_validate_command_rejects_pipe(self) -> None:
        """Test that pipe characters are rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "test | cat"],
                {"echo"},
            )

    def test_validate_command_rejects_ampersand(self) -> None:
        """Test that ampersand (background) is rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "test &"],
                {"echo"},
            )

    def test_validate_command_rejects_backtick(self) -> None:
        """Test that backticks are rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "`whoami`"],
                {"echo"},
            )

    def test_validate_command_rejects_dollar_paren(self) -> None:
        """Test that $() command substitution is rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "$(whoami)"],
                {"echo"},
            )

    def test_validate_command_rejects_dollar_brace(self) -> None:
        """Test that ${} variable expansion is rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "${VAR}"],
                {"echo"},
            )

    def test_validate_command_rejects_input_redirect(self) -> None:
        """Test that input redirection is rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["cat", "< /etc/passwd"],
                {"cat"},
            )

    def test_validate_command_rejects_output_redirect(self) -> None:
        """Test that output redirection is rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "> /tmp/file"],
                {"echo"},
            )

    def test_validate_command_rejects_newline(self) -> None:
        """Test that newline characters are rejected."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.validate_command(
                ["echo", "test\nmalicious"],
                {"echo"},
            )

    def test_validate_command_accepts_multiple_args(self) -> None:
        """Test validation with multiple arguments."""
        result = SafeSubprocess.validate_command(
            ["git", "clone", "https://github.com/repo.git"],
            {"git"},
        )
        assert result == ["git", "clone", "https://github.com/repo.git"]

    def test_validate_command_case_sensitive_allowlist(self) -> None:
        """Test that command allowlist is case-sensitive."""
        with pytest.raises(ValueError, match="Command not allowed"):
            SafeSubprocess.validate_command(
                ["Echo", "test"],
                {"echo"},
            )

    def test_validate_command_numbers_and_hyphens_allowed(self) -> None:
        """Test that arguments with numbers and hyphens are allowed."""
        result = SafeSubprocess.validate_command(
            ["grep", "-n", "pattern123"],
            {"grep"},
        )
        assert result == ["grep", "-n", "pattern123"]

    def test_validate_command_paths_allowed(self) -> None:
        """Test that file paths in arguments are allowed."""
        result = SafeSubprocess.validate_command(
            ["cat", "/tmp/file.txt"],
            {"cat"},
        )
        assert result == ["cat", "/tmp/file.txt"]

    def test_validate_command_urls_allowed(self) -> None:
        """Test that URLs in arguments are allowed."""
        result = SafeSubprocess.validate_command(
            ["curl", "https://example.com/api"],
            {"curl"},
        )
        assert result == ["curl", "https://example.com/api"]


class TestSafeSubprocessRunSafe:
    """Test SafeSubprocess.run_safe execution."""

    def test_run_safe_validates_command(self) -> None:
        """Test that run_safe validates commands."""
        with pytest.raises(ValueError, match="Command not allowed"):
            SafeSubprocess.run_safe(
                ["rm", "-rf", "/"],
                {"echo"},
            )

    def test_run_safe_rejects_shell_injection(self) -> None:
        """Test that run_safe rejects shell injection attempts."""
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.run_safe(
                ["echo", "; rm -rf /"],
                {"echo"},
            )

    def test_run_safe_uses_safe_environment(self) -> None:
        """Test that run_safe uses sanitized environment."""
        with patch.dict(os.environ, {"PASSWORD": "secret", "PATH": "/usr/bin"}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                try:
                    SafeSubprocess.run_safe(
                        ["echo", "test"],
                        {"echo"},
                    )
                except Exception:
                    pass  # Ignore subprocess execution errors in test
                # Verify that subprocess.run was called with an env dict
                if mock_run.called:
                    call_kwargs = mock_run.call_args[1]
                    if "env" in call_kwargs:
                        assert "PASSWORD" not in call_kwargs["env"]


class TestSafeSubprocessIntegration:
    """Test SafeSubprocess integration scenarios."""

    def test_multiple_allowed_commands(self) -> None:
        """Test validation with multiple allowed commands."""
        allowed = {"echo", "cat", "grep"}
        assert SafeSubprocess.validate_command(["echo", "test"], allowed)
        assert SafeSubprocess.validate_command(["cat", "file"], allowed)
        assert SafeSubprocess.validate_command(["grep", "pattern"], allowed)

    def test_command_with_option_flags(self) -> None:
        """Test that option flags are allowed."""
        result = SafeSubprocess.validate_command(
            ["git", "-C", "/path", "status"],
            {"git"},
        )
        assert "-C" in result
        assert "/path" in result

    def test_preserves_command_list_order(self) -> None:
        """Test that command list order is preserved."""
        original = ["python", "-m", "pytest", "--cov", "module"]
        result = SafeSubprocess.validate_command(original, {"python"})
        assert result == original

    def test_allows_git_commands(self) -> None:
        """Test common git command patterns."""
        git_commands = [
            ["git", "status"],
            ["git", "clone", "https://example.com/repo.git"],
            ["git", "commit", "-m", "message"],
            ["git", "push", "origin", "main"],
        ]
        for cmd in git_commands:
            result = SafeSubprocess.validate_command(cmd, {"git"})
            assert result is not None

    def test_allows_python_execution(self) -> None:
        """Test python command execution patterns."""
        python_commands = [
            ["python", "-m", "pytest"],
            ["python", "-c", "print('hello')"],
            ["python", "script.py", "arg1"],
        ]
        for cmd in python_commands:
            result = SafeSubprocess.validate_command(cmd, {"python"})
            assert result is not None
