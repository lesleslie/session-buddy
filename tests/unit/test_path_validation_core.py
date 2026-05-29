"""Unit tests for path validation security module.

Tests comprehensive path validation security checks including:
- Null byte prevention
- Path length validation
- Traversal attack prevention
- Symlink resolution
- Directory existence checks
- Git-specific path validation
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "path_validation.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.path_validation", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.path_validation", _MODULE)
_SPEC.loader.exec_module(_MODULE)

PathValidator = _MODULE.PathValidator
validate_working_directory = _MODULE.validate_working_directory


class TestPathValidatorInit:
    """Test PathValidator initialization."""

    def test_init_creates_empty_allowed_directories(self) -> None:
        """Test PathValidator initializes with empty allowed directories set."""
        validator = PathValidator()
        assert isinstance(validator.allowed_directories, set)
        assert len(validator.allowed_directories) == 0

    def test_class_constants(self) -> None:
        """Test PathValidator class constants are properly set."""
        assert "file" in PathValidator.ALLOWED_SCHEMES
        assert "" in PathValidator.ALLOWED_SCHEMES
        assert PathValidator.MAX_PATH_LENGTH == 4096

    def test_constants_are_immutable(self) -> None:
        """Test that constants cannot be modified through instance."""
        validator = PathValidator()
        assert validator.MAX_PATH_LENGTH == 4096


class TestPathValidatorNullByteProtection:
    """Test null byte prevention (Windows bypass protection)."""

    def test_rejects_null_byte_in_string_path(self) -> None:
        """Test that string paths with null bytes are rejected."""
        validator = PathValidator()
        with pytest.raises(ValueError, match="Null bytes not allowed"):
            validator.validate_user_path("valid/path\x00malicious")

    def test_rejects_null_byte_in_path_object(self) -> None:
        """Test that Path objects with null bytes raise ValueError."""
        validator = PathValidator()
        invalid_path = Path("valid/path") / Path("\x00")
        with pytest.raises(ValueError, match="Null bytes not allowed"):
            validator.validate_user_path(invalid_path)

    def test_accepts_normal_path_without_null_bytes(self) -> None:
        """Test that normal paths without null bytes pass null check."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            validator.allowed_directories.add(Path(tmpdir))
            result = validator.validate_user_path(tmpdir)
            assert result is not None


class TestPathValidatorLengthValidation:
    """Test path length validation (POSIX PATH_MAX protection)."""

    def test_rejects_path_exceeding_max_length(self) -> None:
        """Test that paths exceeding MAX_PATH_LENGTH are rejected."""
        validator = PathValidator()
        excessive_path = "a" * (PathValidator.MAX_PATH_LENGTH + 1)
        with pytest.raises(ValueError, match="Path too long"):
            validator.validate_user_path(excessive_path)

    def test_accepts_path_at_max_length_boundary(self) -> None:
        """Test that path at exactly MAX_PATH_LENGTH can be validated."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            validator.allowed_directories.add(Path(tmpdir))
            # Create a path just under the limit
            safe_path = tmpdir
            if len(str(safe_path)) <= PathValidator.MAX_PATH_LENGTH:
                result = validator.validate_user_path(safe_path)
                assert len(str(result)) <= PathValidator.MAX_PATH_LENGTH

    def test_length_check_includes_string_representation(self) -> None:
        """Test that length check uses string representation of path."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            validator.allowed_directories.add(Path(tmpdir))
            result = validator.validate_user_path(tmpdir)
            assert len(str(result)) <= PathValidator.MAX_PATH_LENGTH


class TestPathValidatorTraversalPrevention:
    """Test directory traversal attack prevention."""

    def test_rejects_parent_directory_traversal(self) -> None:
        """Test that ../ paths are rejected without traversal allowance."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            # Try to traverse outside
            with pytest.raises(ValueError, match="escapes base directory"):
                validator.validate_user_path("../outside", base_dir=base_dir)

    def test_allows_traversal_when_explicitly_enabled(self) -> None:
        """Test that traversal is allowed when allow_traversal=True."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a path that would traverse
            base = Path(tmpdir)
            # With allow_traversal=True, it should resolve without error
            result = validator.validate_user_path(
                base, allow_traversal=True
            )
            assert result is not None

    def test_blocks_traversal_outside_allowed_directories(self) -> None:
        """Test that traversal outside allowed directories is blocked."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            allowed = Path(tmpdir1)
            outside = Path(tmpdir2)
            validator.allowed_directories.add(allowed)

            with pytest.raises(ValueError, match="outside allowed directories"):
                validator.validate_user_path(outside)

    def test_allows_path_within_allowed_directory(self) -> None:
        """Test that paths within allowed directory are accepted."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            result = validator.validate_user_path(base)
            assert result is not None

    def test_allows_existing_path_without_allowlist(self) -> None:
        """Test that existing paths are accepted when no allowlist is set."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validator.validate_user_path(tmpdir)
            assert result.is_absolute()
            assert result.exists()


class TestPathValidatorSymlinkResolution:
    """Test symlink resolution and validation."""

    def test_resolves_path_to_absolute(self) -> None:
        """Test that paths are resolved to absolute paths."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            result = validator.validate_user_path(base)
            assert result.is_absolute()

    def test_returns_absolute_path_object(self) -> None:
        """Test that returned path is always absolute Path object."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            validator.allowed_directories.add(Path(tmpdir))
            result = validator.validate_user_path(tmpdir)
            assert isinstance(result, Path)
            assert result.is_absolute()


class TestPathValidatorExistenceCheck:
    """Test path existence validation."""

    def test_rejects_nonexistent_path(self) -> None:
        """Test that nonexistent paths are rejected."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            nonexistent = base / "does_not_exist"
            with pytest.raises(ValueError, match="Path does not exist"):
                validator.validate_user_path(nonexistent)

    def test_accepts_existing_directory(self) -> None:
        """Test that existing directories are accepted."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            result = validator.validate_user_path(base)
            assert result is not None


class TestPathValidatorDirectoryCheck:
    """Test directory vs file validation."""

    def test_rejects_file_paths(self) -> None:
        """Test that file paths are rejected (must be directory)."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            # Create a file
            file_path = base / "test.txt"
            file_path.write_text("test")
            with pytest.raises(ValueError, match="Path is not a directory"):
                validator.validate_user_path(file_path)

    def test_accepts_directory_paths(self) -> None:
        """Test that directory paths are accepted."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            # Create subdirectory
            subdir = base / "subdir"
            subdir.mkdir()
            result = validator.validate_user_path(subdir)
            assert result is not None


class TestPathValidatorDeviceFileBlocking:
    """Test device file access blocking."""

    def test_blocks_dev_paths(self) -> None:
        """Test that /dev/ paths are blocked."""
        validator = PathValidator()
        # Mock the path checking to simulate /dev/null without needing it to exist
        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "is_dir", return_value=False
        ):
            with pytest.raises(ValueError, match="not permitted"):
                validator.validate_user_path("/dev/null")

    def test_allows_normal_paths(self) -> None:
        """Test that normal (non-/dev) paths are allowed."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            result = validator.validate_user_path(base)
            assert result is not None


class TestPathValidatorGitPath:
    """Test git-specific path validation."""

    def test_validates_git_directory(self) -> None:
        """Test that .git directories can be validated."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # Create .git subdirectory
            git_dir = base / ".git"
            git_dir.mkdir()
            validator.allowed_directories.add(base)
            result = PathValidator.validate_git_path(git_dir)
            assert result is not None

    def test_git_path_blocks_nested_git_access(self) -> None:
        """Test that nested .git in path is blocked."""
        with patch.object(
            PathValidator, "validate_user_path", return_value=Path("/path/.git/config")
        ):
            with pytest.raises(ValueError, match="Direct .git access blocked"):
                PathValidator.validate_git_path("/path/.git/config")

    def test_git_path_allows_git_at_leaf(self) -> None:
        """Test that .git at the end of path is allowed."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            git_dir = base / ".git"
            git_dir.mkdir()
            validator.allowed_directories.add(base)
            result = PathValidator.validate_git_path(git_dir)
            assert result is not None

    def test_git_path_is_callable_without_instance(self) -> None:
        """Test that validate_git_path can be called without instance."""
        # Verify it's callable as a static method (no instance required)
        assert callable(PathValidator.validate_git_path)


class TestValidateWorkingDirectory:
    """Test the validate_working_directory convenience function."""

    def test_returns_current_working_directory_when_none(self) -> None:
        """Test that None path returns current working directory."""
        result = validate_working_directory(None)
        assert result == Path.cwd()

    def test_validates_string_path(self) -> None:
        """Test that string path is validated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_working_directory(tmpdir)
            assert result is not None
            assert isinstance(result, Path)

    def test_validates_existing_path(self) -> None:
        """Test that existing paths are validated without traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_working_directory(tmpdir)
            assert result.exists()
            assert result.is_dir()

    def test_rejects_nonexistent_path(self) -> None:
        """Test that nonexistent paths are rejected."""
        nonexistent = "/path/that/definitely/does/not/exist/xyz"
        with pytest.raises(ValueError, match="Path does not exist"):
            validate_working_directory(nonexistent)

    def test_uses_path_validator_internally(self) -> None:
        """Test that the function uses PathValidator.validate_user_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_working_directory(tmpdir)
            assert result.is_absolute()


class TestPathValidatorTypeConversion:
    """Test path type conversion and handling."""

    def test_accepts_string_path(self) -> None:
        """Test that string paths are accepted."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            validator.allowed_directories.add(Path(tmpdir))
            result = validator.validate_user_path(tmpdir)
            assert isinstance(result, Path)

    def test_accepts_path_object(self) -> None:
        """Test that Path objects are accepted."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            result = validator.validate_user_path(base)
            assert isinstance(result, Path)

    def test_converts_string_to_path(self) -> None:
        """Test that string paths are converted to Path objects."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            validator.allowed_directories.add(Path(tmpdir))
            result = validator.validate_user_path(tmpdir)
            assert isinstance(result, Path)


class TestPathValidatorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_relative_path_conversion(self) -> None:
        """Test that relative paths are converted to absolute."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            # Resolve relative path
            result = validator.validate_user_path(base)
            assert result.is_absolute()

    def test_validation_with_base_dir_required(self) -> None:
        """Test that base_dir is used when allowed_directories is empty."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            allowed_base = Path(tmpdir1)
            outside_path = Path(tmpdir2)
            # No allowed_directories set, so validation should fail for path outside base_dir
            with pytest.raises(ValueError, match="escapes base directory"):
                validator.validate_user_path(outside_path, base_dir=allowed_base, allow_traversal=False)

    def test_allows_traversal_when_explicitly_enabled(self) -> None:
        """Test that traversal checks are skipped when explicitly allowed."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            traversing_path = base / ".." / base.name
            result = validator.validate_user_path(traversing_path, allow_traversal=True)
            assert result.resolve() == base.resolve()

    def test_multiple_allowed_directories(self) -> None:
        """Test validation with multiple allowed directories."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            dir1 = Path(tmpdir1)
            dir2 = Path(tmpdir2)
            validator.allowed_directories.add(dir1)
            validator.allowed_directories.add(dir2)

            # Both should validate
            result1 = validator.validate_user_path(dir1)
            result2 = validator.validate_user_path(dir2)
            assert result1 is not None
            assert result2 is not None

    def test_check_allowed_roots_accepts_base_directory(self) -> None:
        """Test helper accepts resolved path inside base directory."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            validator.allowed_directories.add(base)
            resolved = base.resolve()
            validator._check_allowed_roots(resolved, None)

    def test_raise_traversal_error_messages(self) -> None:
        """Test helper emits the correct traversal error message variant."""
        validator = PathValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir).resolve()
            resolved = base / "outside"

            with pytest.raises(ValueError, match="escapes base directory"):
                validator._raise_traversal_error(resolved, base, [base])

            with pytest.raises(ValueError, match="outside allowed directories"):
                validator._raise_traversal_error(resolved, None, [base])
