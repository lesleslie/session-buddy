"""Integration tests for SafeSubprocess with real command execution.

Tests subprocess helper with actual system commands to validate
security features work correctly in real-world scenarios.
"""

import os
import subprocess
import pytest
from pathlib import Path
from session_buddy.utils.subprocess_executor import SafeSubprocess


def test_safe_subprocess_real_command_execution():
    """Test SafeSubprocess.run_safe executes real commands correctly."""
    # Test with echo command
    result = SafeSubprocess.run_safe(
        ["echo", "test output"],
        allowed_commands={"echo"}
    )

    assert result.returncode == 0
    assert "test output" in result.stdout
    assert result.stderr == ""


def test_safe_subprocess_ls_command():
    """Test SafeSubprocess with ls command (common use case)."""
    result = SafeSubprocess.run_safe(
        ["ls", "-la", "/tmp"],
        allowed_commands={"ls"}
    )

    assert result.returncode == 0
    # ls output should contain directory listing
    assert "total" in result.stdout or len(result.stdout) > 0


def test_safe_subprocess_fails_on_disallowed_command():
    """Test SafeSubprocess rejects disallowed commands."""
    with pytest.raises(ValueError, match="Command not allowed"):
        SafeSubprocess.run_safe(
            ["cat", "/etc/passwd"],
            allowed_commands={"echo", "ls"}
        )


def test_safe_subprocess_environment_sanitization():
    """Test environment sanitization removes sensitive variables."""
    # Set sensitive variable
    os.environ["TEST_SECRET_PASSWORD"] = "super_secret_value"
    os.environ["TEST_API_TOKEN"] = "secret_token_123"

    try:
        # Run command that prints environment
        result = SafeSubprocess.run_safe(
            ["sh", "-c", "echo $TEST_SECRET_PASSWORD"],
            allowed_commands={"sh"}
        )

        # Secret should NOT be in output
        assert "super_secret_value" not in result.stdout
        assert "TEST_SECRET_PASSWORD" not in result.stdout

    finally:
        # Cleanup
        del os.environ["TEST_SECRET_PASSWORD"]
        del os.environ["TEST_API_TOKEN"]


def test_safe_subprocess_with_git_command():
    """Test SafeSubprocess with git command (realistic use case)."""
    result = SafeSubprocess.run_safe(
        ["git", "status", "--short"],
        allowed_commands={"git"}
    )

    # Git should execute successfully
    assert result.returncode == 0
    # Output format varies, but command should work


def test_safe_subprocess_concurrent_execution():
    """Test multiple concurrent SafeSubprocess executions."""
    import threading

    results = []
    errors = []

    def run_echo_task(value: int):
        """Run echo command in thread."""
        try:
            result = SafeSubprocess.run_safe(
                ["echo", f"test_{value}"],
                allowed_commands={"echo"}
            )
            results.append(result.stdout.strip())
        except Exception as e:
            errors.append(e)

    # Run 10 concurrent commands
    threads = [
        threading.Thread(target=run_echo_task, args=(i,))
        for i in range(10)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All should complete successfully
    assert len(errors) == 0
    assert len(results) == 10
    assert all(f"test_{i}" in results[i] for i in range(10))


def test_safe_subprocess_popen_real_process():
    """Test SafeSubprocess.popen_safe with real process."""
    proc = SafeSubprocess.popen_safe(
        ["echo", "background task"],
        allowed_commands={"echo"}
    )

    proc.wait()
    assert proc.returncode == 0


def test_safe_subprocess_blocks_dangerous_real_commands():
    """Test dangerous real commands are blocked."""
    dangerous_commands = [
        # Command chaining
        ["echo", "test; rm -rf /"],
        # Piping to external processes
        ["cat", "/etc/passwd | grep root"],
        # Command substitution
        ["echo", "$(whoami)"],
        # Background execution
        ["echo", "test &"],
    ]

    for cmd in dangerous_commands:
        with pytest.raises(ValueError, match="Shell metacharacter"):
            SafeSubprocess.run_safe(cmd, allowed_commands={"echo", "cat"})


def test_safe_subprocess_with_python_command():
    """Test SafeSubprocess with Python command (script execution)."""
    test_script = Path("/tmp/test_safe_subprocess.py")
    test_script.write_text('print("Hello from Python")')

    try:
        result = SafeSubprocess.run_safe(
            ["python", str(test_script)],
            allowed_commands={"python"}
        )

        assert result.returncode == 0
        assert "Hello from Python" in result.stdout

    finally:
        test_script.unlink(missing_ok=True)


def test_safe_subprocess_error_handling():
    """Test SafeSubprocess handles command errors gracefully."""
    # Command that will fail
    result = SafeSubprocess.run_safe(
        ["ls", "/nonexistent/path/that/does/not/exist"],
        allowed_commands={"ls"}
    )

    # Should not raise exception (check=False)
    assert result.returncode != 0
    assert len(result.stdout) > 0 or len(result.stderr) > 0


def test_safe_subprocess_with_output_redirection():
    """Test SafeSubprocess captures output correctly."""
    result = SafeSubprocess.run_safe(
        ["python", "-c", "import sys; print('stdout'); print('stderr', file=sys.stderr)"],
        allowed_commands={"python"}
    )

    assert result.returncode == 0
    assert "stdout" in result.stdout
