"""Path traversal security tests.

Tests for path validation to prevent directory traversal attacks.
"""

import pytest
from pathlib import Path
from session_buddy.core.session_manager import SessionLifecycleManager


def test_validate_user_path_normal():
    """Test normal path validation."""
    manager = SessionLifecycleManager()

    # Should allow normal paths
    valid_path = manager._validate_working_directory(str(Path.cwd()))
    assert valid_path == Path.cwd()


def test_validate_user_path_home_directory():
    """Test home directory is allowed."""
    manager = SessionLifecycleManager()

    # Should allow home directory
    valid_path = manager._validate_working_directory(str(Path.home()))
    assert valid_path == Path.home()


def test_validate_user_path_traversal_blocked():
    """Test path traversal attacks are blocked."""
    manager = SessionLifecycleManager()

    # Should block traversal attempts
    traversal_attempts = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "....//....//....//etc/passwd",
    ]

    for attempt in traversal_attempts:
        with pytest.raises(ValueError, match="outside allowed directories"):
            manager._validate_working_directory(attempt)


def test_validate_user_path_nonexistent():
    """Test non-existent paths are blocked."""
    manager = SessionLifecycleManager()

    # Should block non-existent paths
    with pytest.raises(ValueError, match="does not exist"):
        manager._validate_working_directory("/nonexistent/path/that/does/not/exist")


def test_validate_user_path_file_not_directory():
    """Test files are blocked (only directories allowed)."""
    manager = SessionLifecycleManager()

    # Create a temporary file
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Should block file paths (only directories allowed)
        with pytest.raises(ValueError, match="not a directory"):
            manager._validate_working_directory(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_setup_working_directory_with_validation():
    """Test _setup_working_directory uses validation."""
    manager = SessionLifecycleManager()

    # Should work with valid path
    result = manager._setup_working_directory(str(Path.cwd()))
    assert result == Path.cwd()
    assert manager.current_project == Path.cwd().name


def test_setup_working_directory_blocks_traversal():
    """Test _setup_working_directory blocks traversal."""
    manager = SessionLifecycleManager()

    # Should block traversal attempts
    with pytest.raises(ValueError, match="outside allowed directories"):
        manager._setup_working_directory("../../../etc")


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
    from session_buddy.utils.path_validation import PathValidator

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
    from session_buddy.utils.path_validation import PathValidator

    validator = PathValidator()

    # Path at boundary (should be blocked)
    path_at_limit = "/tmp/" + "a" * 4092  # 5 + 4092 = 4097 chars (>4096)
    assert len(path_at_limit) > 4096  # Ensure we're testing the limit
    with pytest.raises(ValueError, match="too long"):
        validator.validate_user_path(path_at_limit)

    # Path well over limit
    path_over_limit = "/tmp/" + "a" * 10000
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
    import tempfile

    from session_buddy.utils.path_validation import PathValidator

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

