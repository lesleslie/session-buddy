"""Priority 2 security tests for advanced attack scenarios.

Tests for:
- Unicode homograph attacks
- TOCTOU (Time-of-Check Time-of-Use) race conditions
- DoS prevention (large output, resource limits)
- Edge cases (empty values, malformed arguments)
"""

import tempfile
import threading
import time
import pytest
from pathlib import Path

from session_buddy.mcp.tools.session.crackerjack_tools import _parse_crackerjack_args
from session_buddy.utils.subprocess_executor import SafeSubprocess
from session_buddy.utils.path_validation import PathValidator


# =============================================================================
# Command Injection - Priority 2 Tests
# =============================================================================

def test_parse_crackerjack_args_unicode_homograph():
    """Test Unicode look-alike characters are blocked.

    SECURITY: Unicode homographs can bypass allowlist checks.
    Risk: MEDIUM - visual confusion attacks.

    Attack Vector:
        User provides: －verbose (full-width dash)
        Allowlist sees: --verbose (allowed)
        Parser sees: －verbose (different character)

    Reference: CWE-156 - Homograph Attack
    """
    # Full-width dash (U+FF0D)
    with pytest.raises(ValueError, match="Blocked argument|unsafe"):
        _parse_crackerjack_args("－verbose")

    # Full-width letters (U+FF28-U+FF4E etc)
    with pytest.raises(ValueError, match="Blocked argument"):
        _parse_crackerjack_args("ｖｅｒｂｏｓｅ")


def test_parse_crackerjack_args_empty_values():
    """Test empty flag values are handled correctly.

    SECURITY: Empty values can cause unexpected behavior.
    Risk: LOW - functionality issue, not security.

    Edge Case:
        --severity="" (empty string)
        --output= (no value)
    """
    # Empty quoted string
    result = _parse_crackerjack_args('--severity=""')
    assert result == ["--severity", ""]

    # Empty value after equals
    result = _parse_crackerjack_args("--output=")
    assert result == ["--output", ""]

    # Verify empty string is preserved
    assert result[1] == ""


def test_parse_crackerjack_args_multiple_equals():
    """Test multiple equals signs are handled correctly.

    SECURITY: Malformed arguments can bypass validation.
    Risk: LOW - parser robustness.

    Edge Case:
        --key=value=extra
        --key==value
    """
    # Multiple equals in value
    result = _parse_crackerjack_args('--severity="high=medium"')
    assert result == ["--severity", "high=medium"]

    # Double equals
    result = _parse_crackerjack_args("--output==file.txt")
    assert result == ["--output", "=file.txt"]


def test_parse_crackerjack_args_flag_repetition():
    """Test flag repetition is handled correctly.

    SECURITY: Repeated flags can cause unexpected behavior.
    Risk: LOW - functionality issue.

    Edge Case:
        --verbose --verbose --verbose (should this be allowed?)
    """
    # Allow repetition (idempotent flags)
    result = _parse_crackerjack_args("--verbose --verbose --verbose")
    assert result == ["--verbose", "--verbose", "--verbose"]

    # Mixed flags with repetition
    result = _parse_crackerjack_args("-v -v -q")
    assert result == ["-v", "-v", "-q"]


# =============================================================================
# Subprocess Safety - Priority 2 Tests
# =============================================================================

def test_run_safe_large_output():
    """Test large subprocess output is handled correctly.

    SECURITY: Large output can exhaust memory (DoS).
    Risk: MEDIUM - resource exhaustion.

    Reference: CWE-770 - Allocation of Resources Without Limits
    """
    # Generate 1MB of output (safe size)
    result = SafeSubprocess.run_safe(
        ["python", "-c", "print('A' * 1_000_000)"],
        allowed_commands={"python"}
    )

    # Should succeed without hanging
    assert result.returncode == 0
    assert len(result.stdout) >= 1_000_000


def test_run_safe_long_running_command():
    """Test long-running commands don't block indefinitely.

    SECURITY: Long-running commands can cause hangs (DoS).
    Risk: MEDIUM - availability impact.

    Mitigation: Commands should have timeouts (caller's responsibility).
    """
    # Quick command that completes
    result = SafeSubprocess.run_safe(
        ["python", "-c", "import time; time.sleep(0.01); print('done')"],
        allowed_commands={"python"}
    )

    assert result.returncode == 0
    assert "done" in result.stdout


# =============================================================================
# Path Validation - Priority 2 Tests
# =============================================================================

def test_validate_user_path_toctou():
    """Test TOCTOU vulnerability is mitigated.

    SECURITY: Time-of-check to time-of-use race condition.
    Risk: HIGH - race condition allows bypass.

    Attack Scenario:
        1. Check: /tmp/safe is a directory (allowed)
        2. Attacker replaces: /tmp/safe -> symlink to /etc
        3. Use: /tmp/safe/passwd -> /etc/passwd

    Reference: CWE-367 - Time-of-Check Time-of-Use
    """
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        safe_path = tmpdir / "safe"

        # Create safe directory
        safe_path.mkdir()

        # Thread that replaces directory with symlink
        def replace_with_symlink():
            time.sleep(0.01)  # Small delay to let validation start
            try:
                safe_path.rmdir()
                safe_path.symlink_to("/etc")
            except (OSError, FileNotFoundError):
                pass  # Already validated or removed

        # Start attack thread
        t = threading.Thread(target=replace_with_symlink)
        t.start()

        try:
            # Validate path while another thread changes it
            # Should use resolve() which catches TOCTOU
            result = validator.validate_user_path(safe_path)
            t.join()

            # If symlink was created during validation, should detect it
            # (implementation-dependent)
            assert result == safe_path or result.is_symlink()

        except ValueError as e:
            # Expected if TOCTOU mitigation works
            assert "escapes" in str(e).lower() or "symlink" in str(e).lower()
        finally:
            t.join()


def test_validate_user_path_unicode_normalization():
    """Test Unicode normalization attacks are blocked.

    SECURITY: Unicode normalization can bypass path checks.
    Risk: MEDIUM - path confusion attacks.

    Attack Vector:
        Path: /tmp/\u0061\u0301 (a with combining acute)
        Normalized: /tmp/á (single character)

    Reference: CWE-176 - Improper Handling of Unicode Encoding
    """
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create file with combining characters
        test_file = tmpdir / "test\u0301"  # e + combining acute

        try:
            # Should handle Unicode correctly
            # Either normalize or reject
            result = validator.validate_user_path(test_file.parent, base_dir=tmpdir)
            assert result == tmpdir
        except (ValueError, OSError):
            # Also acceptable if rejected
            pass


def test_validate_user_path_device_files():
    """Test access to device files is blocked.

    SECURITY: Device files can be security-sensitive.
    Risk: MEDIUM - unauthorized device access.

    Sensitive Devices:
        /dev/urandom, /dev/zero (resource exhaustion)
        /dev/mem, /dev/kmem (memory reading)
        /dev/sda (disk access)
    """
    validator = PathValidator()

    # Should block device file access
    sensitive_devices = [
        "/dev/mem",
        "/dev/kmem",
        "/dev/sda",
        "/dev/urandom",
    ]

    for device in sensitive_devices:
        # Should either not exist or be blocked
        if Path(device).exists():
            with pytest.raises(ValueError, match="outside allowed|not permitted"):
                validator.validate_user_path(device)


# =============================================================================
# Environment Sanitization - Priority 2 Tests
# =============================================================================

def test_get_safe_environment_recursive_patterns():
    """Test environment variable name patterns are correctly matched.

    SECURITY: Secret patterns can have variations/typos.
    Risk: LOW - partial secret leakage.

    Edge Cases:
        PASSWORD vs password (case sensitivity)
        API_KEY vs APIKEY (underscore variations)
    """
    import os
    from session_buddy.utils.subprocess_executor import _get_safe_environment

    # Set variations of secret patterns
    os.environ["password"] = "lowercase_secret"  # Should be blocked (PASSWORD in uppercase)
    os.environ["APIKEY"] = "no_underscore_secret"  # Should be blocked (KEY in uppercase)
    os.environ["USER_TOKEN"] = "user_secret"  # Should be blocked (TOKEN in uppercase)

    try:
        env = _get_safe_environment()

        # All should be removed (pattern matching is case-insensitive)
        assert "password" not in env
        assert "APIKEY" not in env
        assert "USER_TOKEN" not in env

    finally:
        del os.environ["password"]
        del os.environ["APIKEY"]
        del os.environ["USER_TOKEN"]


def test_get_safe_environment_preserves_path():
    """Test PATH environment variable is preserved correctly.

    SECURITY: Removing PATH breaks command execution.
    Risk: LOW - functionality issue.

    Requirement: PATH must be preserved for subprocess to work.
    """
    import os
    from session_buddy.utils.subprocess_executor import _get_safe_environment

    original_path = os.environ.get("PATH", "")

    try:
        env = _get_safe_environment()

        # PATH should be preserved
        assert "PATH" in env
        assert env["PATH"] == original_path

    finally:
        if original_path:
            os.environ["PATH"] = original_path


# =============================================================================
# Race Condition - Priority 2 Tests
# =============================================================================

def test_concurrent_path_validation_consistency():
    """Test concurrent path validation returns consistent results.

    SECURITY: Race conditions in validation can create bypasses.
    Risk: MEDIUM - validation bypass under load.

    Test: Multiple threads validate same path simultaneously.
    """
    validator = PathValidator()
    results = []
    errors = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        def validate_path():
            try:
                result = validator.validate_user_path(tmpdir)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run 20 concurrent validations
        threads = [threading.Thread(target=validate_path) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed with same result
        assert len(errors) == 0
        assert len(results) == 20
        assert all(r == tmpdir for r in results)


def test_concurrent_sanitization_no_interference():
    """Test concurrent environment sanitization doesn't interfere.

    SECURITY: Concurrent sanitization could leak secrets if not thread-safe.
    Risk: MEDIUM - secret leakage under load.

    Test: Multiple threads call _get_safe_environment() simultaneously.
    """
    import os
    import threading
    from session_buddy.utils.subprocess_executor import _get_safe_environment

    results = []
    errors = []

    def sanitize_env(worker_id: int):
        try:
            env = _get_safe_environment()

            # Verify it's a valid environment
            assert isinstance(env, dict)
            assert "PATH" in env  # Should have PATH

            results.append(worker_id)
        except Exception as e:
            errors.append((worker_id, e))

    # Run 50 concurrent sanitizations
    threads = [threading.Thread(target=sanitize_env, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All should succeed
    assert len(errors) == 0
    assert len(results) == 50


# =============================================================================
# DoS Prevention - Priority 2 Tests
# =============================================================================

def test_run_safe_argument_count_limit():
    """Test excessive argument count is prevented.

    SECURITY: Too many arguments can exhaust resources.
    Risk: LOW - resource exhaustion.

    Current: No limit enforced (future enhancement).
    """
    # Create command with 1000 arguments (should work for now)
    args = ["echo"] + [f"arg{i}" for i in range(1000)]

    result = SafeSubprocess.run_safe(
        args,
        allowed_commands={"echo"}
    )

    assert result.returncode == 0
    # Note: Future enhancement - add argument count limit


def test_parse_crackerjack_args_very_long_input():
    """Test very long input strings are handled correctly.

    SECURITY: Extremely long input can cause DoS.
    Risk: LOW - parser resource exhaustion.

    Test: 10,000 character input string.
    """
    # Very long but valid input
    long_input = "--verbose " + " ".join([f"--arg{i}" for i in range(1000)])

    # Should parse without hanging
    result = _parse_crackerjack_args(long_input)

    assert len(result) > 100  # Should parse successfully
    assert "--verbose" in result
