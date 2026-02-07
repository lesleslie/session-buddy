"""Integration tests for PathValidator with filesystem operations.

Tests path validation with real filesystem operations to validate
security features work correctly against actual path traversal attacks.
"""

import os
import tempfile
import pytest
from pathlib import Path
from session_buddy.utils.path_validation import PathValidator


def test_path_validator_allows_safe_directories():
    """Test PathValidator allows safe directory access."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Should allow access to temporary directory
        result = validator.validate_user_path(tmpdir)
        assert result == tmpdir

        # Should allow subdirectory
        subdir = tmpdir / "subdir"
        subdir.mkdir()
        result = validator.validate_user_path(subdir, base_dir=tmpdir)
        assert result == subdir


def test_path_validator_blocks_symlink_traversal():
    """Test PathValidator blocks symlink-based directory traversal."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create symlink to /etc
        etc_link = tmpdir / "etc_link"
        try:
            etc_link.symlink_to("/etc")

            # Should block access through symlink
            with pytest.raises(ValueError, match="escapes base directory"):
                validator.validate_user_path(
                    etc_link / "passwd",
                    base_dir=tmpdir
                )
        except OSError:
            # Symlink creation might fail in some environments
            pytest.skip("Symlink creation not supported")


def test_path_validator_blocks_relative_traversal():
    """Test PathValidator blocks relative path traversal attempts."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a file outside base directory
        outside_file = tmpdir / ".." / "outside_test.txt"
        outside_file = outside_file.resolve()

        # Should block traversal
        with pytest.raises(ValueError, match="outside allowed directories"):
            validator.validate_user_path(
                tmpdir / ".." / "outside_test.txt",
                base_dir=tmpdir
            )


def test_path_validator_with_complex_paths():
    """Test PathValidator handles complex path patterns."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create nested directory structure
        nested = tmpdir / "a" / "b" / "c"
        nested.mkdir(parents=True)

        # Should allow nested access
        result = validator.validate_user_path(nested, base_dir=tmpdir)
        assert result == nested


def test_path_validator_null_byte_injection():
    """Test PathValidator blocks null byte injection attacks."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Null byte in path
        with pytest.raises(ValueError, match="Null bytes"):
            validator.validate_user_path(
                tmpdir / "test\x00file.txt"
            )


def test_path_validator_length_limits():
    """Test PathValidator enforces path length limits."""
    validator = PathValidator()

    # Very long path (should be blocked)
    long_path = "/tmp/" + "a" * 5000

    with pytest.raises(ValueError, match="too long"):
        validator.validate_user_path(long_path)


def test_path_validator_nonexistent_path():
    """Test PathValidator blocks access to nonexistent paths."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Path that doesn't exist
        nonexistent = tmpdir / "does_not_exist"

        with pytest.raises(ValueError, match="does not exist"):
            validator.validate_user_path(nonexistent)


def test_path_validator_file_not_directory():
    """Test PathValidator blocks file paths when directory required."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a file
        test_file = tmpdir / "test.txt"
        test_file.write_text("test content")

        # Should block file path (only directories allowed)
        with pytest.raises(ValueError, match="not a directory"):
            validator.validate_user_path(test_file)


def test_path_validator_with_real_project_structure():
    """Test PathValidator with realistic project structure."""
    validator = PathValidator()

    # Test with current directory (should be safe)
    cwd = Path.cwd()
    result = validator.validate_user_path(cwd)
    assert result == cwd

    # Test with home directory
    home = Path.home()
    result = validator.validate_user_path(home)
    assert result == home


def test_path_validator_allowlist_behavior():
    """Test PathValidator allowlist functionality."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Add to allowlist
        validator.allowed_directories.add(tmpdir)

        # Should allow access
        result = validator.validate_user_path(tmpdir)
        assert result == tmpdir


def test_path_validator_blocks_absolute_path_bypass():
    """Test PathValidator cannot be bypassed with absolute paths."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Try to access outside directory using absolute path
        outside = Path("/etc/passwd")

        with pytest.raises(ValueError):
            validator.validate_user_path(
                outside,
                base_dir=tmpdir
            )


def test_path_validator_with_temp_files():
    """Test PathValidator correctly handles temp file operations."""
    validator = PathValidator()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create temp file
        temp_file = tmpdir / "temp.txt"
        temp_file.write_text("test")

        # Validate directory (should work)
        result = validator.validate_user_path(tmpdir)
        assert result == tmpdir

        # Validate file (should fail - not a directory)
        with pytest.raises(ValueError, match="not a directory"):
            validator.validate_user_path(temp_file)
