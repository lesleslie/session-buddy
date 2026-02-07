"""Integration tests for concurrent environment sanitization.

Tests thread safety and performance of environment sanitization
under concurrent load.
"""

import os
import time
import threading
import pytest
from session_buddy.utils.subprocess_executor import _get_safe_environment, SafeSubprocess


def test_get_safe_environment_isolated_calls():
    """Test _get_safe_environment returns independent copies."""
    # Get two environment copies
    env1 = _get_safe_environment()
    env2 = _get_safe_environment()

    # Modify one
    env1["TEST_VAR"] = "value1"

    # Other should be unchanged
    assert "TEST_VAR" not in env2
    assert "TEST_VAR" in env1


def test_get_safe_environment_performance():
    """Test _get_safe_environment performance under load."""
    iterations = 1000

    start = time.perf_counter()
    for _ in range(iterations):
        env = _get_safe_environment()
    end = time.perf_counter()

    elapsed_ms = (end - start) * 1000
    avg_us = elapsed_ms / iterations * 1000

    # Should be very fast (< 1ms per call)
    assert avg_us < 1000, f"Average time {avg_us:.0f}μs exceeds 1ms threshold"
    assert elapsed_ms < 1000, f"Total time {elapsed_ms:.0f}ms exceeds 1s for {iterations} calls"


def test_concurrent_sanitization_no_secrets_leaked():
    """Test concurrent sanitization doesn't leak secrets."""
    results = []
    errors = []

    def sanitization_worker(worker_id: int):
        """Worker that sets secret and sanitizes environment."""
        secret_name = f"WORKER_SECRET_{worker_id}"
        secret_value = f"secret_value_{worker_id}"

        # Set secret
        os.environ[secret_name] = secret_value

        try:
            # Get sanitized environment
            env = _get_safe_environment()

            # Verify secret not leaked
            assert secret_name not in env, f"Secret {secret_name} leaked!"
            assert secret_value not in env.values(), f"Secret value {secret_value} leaked!"

            results.append(worker_id)

        except AssertionError as e:
            errors.append((worker_id, e))
        finally:
            # Cleanup
            if secret_name in os.environ:
                del os.environ[secret_name]

    # Run 20 concurrent workers
    threads = [
        threading.Thread(target=sanitization_worker, args=(i,))
        for i in range(20)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All workers should succeed
    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 20


def test_concurrent_subprocess_execution():
    """Test concurrent subprocess execution with safe environments."""
    results = []
    errors = []

    def subprocess_worker(worker_id: int):
        """Worker that runs subprocess with secret."""
        secret_name = f"SUBPROCESS_SECRET_{worker_id}"

        os.environ[secret_name] = f"should_not_appear_{worker_id}"

        try:
            # Run command with sanitized environment
            result = SafeSubprocess.run_safe(
                ["echo", f"worker_{worker_id}"],
                allowed_commands={"echo"}
            )

            # Verify secret not in output
            assert secret_name not in result.stdout
            assert f"should_not_appear_{worker_id}" not in result.stdout
            assert f"worker_{worker_id}" in result.stdout

            results.append(worker_id)

        except Exception as e:
            errors.append((worker_id, e))
        finally:
            if secret_name in os.environ:
                del os.environ[secret_name]

    # Run 15 concurrent workers
    threads = [
        threading.Thread(target=subprocess_worker, args=(i,))
        for i in range(15)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All should succeed
    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 15


def test_environment_sanitization_removes_common_secrets():
    """Test that common secret patterns are removed."""
    # Set various secret patterns
    secrets = {
        "API_KEY": "secret_key",
        "PASSWORD": "my_password",
        "SECRET_TOKEN": "token123",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "GITHUB_TOKEN": "ghp_example_token",
        "SESSION_COOKIE": "session_data",
    }

    for key, value in secrets.items():
        os.environ[key] = value

    try:
        # Get sanitized environment
        env = _get_safe_environment()

        # All secrets should be removed
        for key in secrets:
            assert key not in env, f"Secret {key} not removed!"
            assert secrets[key] not in env.values(), f"Secret value for {key} leaked!"

    finally:
        # Cleanup
        for key in secrets:
            if key in os.environ:
                del os.environ[key]


def test_environment_preserves_safe_variables():
    """Test that safe variables are preserved."""
    # Set safe variables
    safe_vars = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/home/user",
        "USER": "testuser",
        "SHELL": "/bin/bash",
        "LANG": "en_US.UTF-8",
        "EDITOR": "vim",
        "PYTHONPATH": "/path/to/python",
    }

    for key, value in safe_vars.items():
        os.environ[key] = value

    try:
        env = _get_safe_environment()

        # Safe variables should be preserved
        for key, value in safe_vars.items():
            assert key in env, f"Safe variable {key} was removed!"
            assert env[key] == value, f"Safe variable {key} has wrong value!"

    finally:
        for key in safe_vars:
            if key in os.environ:
                del os.environ[key]


def test_concurrent_mixed_operations():
    """Test concurrent mixed operations (sanitization + subprocess)."""
    results = {"sanitization": 0, "subprocess": 0}
    errors = []

    def sanitization_worker():
        """Worker performing sanitization."""
        try:
            env = _get_safe_environment()
            assert isinstance(env, dict)
            results["sanitization"] += 1
        except Exception as e:
            errors.append(("sanitization", e))

    def subprocess_worker():
        """Worker running subprocess."""
        try:
            result = SafeSubprocess.run_safe(
                ["echo", "test"],
                allowed_commands={"echo"}
            )
            assert result.returncode == 0
            results["subprocess"] += 1
        except Exception as e:
            errors.append(("subprocess", e))

    # Run mixed workload
    threads = []
    for i in range(10):
        threads.append(threading.Thread(target=sanitization_worker))
        threads.append(threading.Thread(target=subprocess_worker))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All operations should succeed
    assert len(errors) == 0, f"Errors: {errors}"
    assert results["sanitization"] == 10
    assert results["subprocess"] == 10


def test_environment_sanitization_under_load():
    """Test environment sanitization under heavy concurrent load."""
    workers = 50
    operations_per_worker = 100
    total_operations = workers * operations_per_worker
    errors = []

    def heavy_worker(worker_id: int):
        """Worker performing many sanitization operations."""
        try:
            for i in range(operations_per_worker):
                env = _get_safe_environment()
                assert isinstance(env, dict)
                assert "PATH" in env or len(env) >= 0  # Basic sanity
        except Exception as e:
            errors.append((worker_id, e))

    # Run heavy workload
    threads = [
        threading.Thread(target=heavy_worker, args=(i,))
        for i in range(workers)
    ]

    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    end = time.perf_counter()

    # All operations should succeed
    assert len(errors) == 0, f"Errors: {errors}"

    # Performance should be reasonable
    elapsed = end - start
    ops_per_second = total_operations / elapsed

    assert ops_per_second > 100, f"Performance too slow: {ops_per_second:.0f} ops/sec"
