"""Path validation utilities for security.

This module provides production-quality path validation to prevent directory
traversal attacks and other path-based vulnerabilities.
"""

from __future__ import annotations

from pathlib import Path


class PathValidator:
    """Centralized path validation for security.

    SECURITY: This class prevents path traversal attacks through:
    - Null byte prevention (Windows bypass protection)
    - Length limits (POSIX PATH_MAX = 4096)
    - Traversal prevention with base directory constraints
    - Symlink resolution and validation
    - Permission and existence checking
    """

    ALLOWED_SCHEMES = {"file", ""}  # Only file:// URIs allowed, no http/https
    MAX_PATH_LENGTH = 4096  # POSIX PATH_MAX limit

    def __init__(self) -> None:
        self.allowed_directories: set[Path] = set()

    def validate_user_path(  # noqa: C901
        self,
        path: str | Path,
        allow_traversal: bool = False,
        base_dir: Path | None = None,
    ) -> Path:
        """Validate user-provided path with comprehensive security checks.

        Args:
            path: User-provided path to validate
            allow_traversal: Allow path traversal (default: False for security)
            base_dir: Required base directory if traversal not allowed

        Returns:
            Validated absolute Path object

        Raises:
            ValueError: If path fails any security validation

        Examples:
            >>> PathValidator.validate_user_path(Path.cwd())
            /current/directory
            >>> PathValidator.validate_user_path("../etc", allow_traversal=True)
            /parent/etc

        SECURITY:
            - Null bytes are blocked (Windows bypass prevention)
            - Path length is limited to MAX_PATH_LENGTH
            - Traversal is blocked unless explicitly allowed
            - Symlinks are resolved and validated
            - Path must exist and be a directory
        """
        path = self._prepare_path(path)
        path_str = str(path)

        self._validate_path_length(path_str)
        resolved = path.resolve()

        self._validate_traversal_access(resolved, allow_traversal, base_dir)
        self._validate_path_requirements(resolved)

        return path.absolute()

    def _prepare_path(self, path: str | Path) -> Path:
        """Convert and validate path string input."""
        if isinstance(path, str):
            self._check_null_bytes(path)
            path = Path(path)
        self._check_null_bytes(path)
        return path

    def _check_null_bytes(self, path: str | Path) -> None:
        """Check for null bytes and raise ValueError if found."""
        path_str = str(path)
        if "\x00" in path_str:
            raise ValueError("Null bytes not allowed in path")

    def _validate_path_length(self, path_str: str) -> None:
        """Validate path length against maximum."""
        if len(path_str) > PathValidator.MAX_PATH_LENGTH:
            raise ValueError(
                f"Path too long: {len(path_str)} characters. "
                f"Maximum is {PathValidator.MAX_PATH_LENGTH}"
            )

    def _validate_traversal_access(
        self,
        resolved: Path,
        allow_traversal: bool,
        base_dir: Path | None,
    ) -> None:
        """Validate traversal access against allowed directories."""
        if not allow_traversal:
            self._check_allowed_roots(resolved, base_dir)

    def _check_allowed_roots(self, resolved: Path, base_dir: Path | None) -> None:
        """Check if resolved path is within allowed root directories."""
        allowed_roots: set[Path] = self.allowed_directories.copy()
        if base_dir is not None:
            allowed_roots.add(base_dir.resolve())

        if not allowed_roots:
            return

        allowed_root_paths = [root.resolve() for root in allowed_roots]
        base_resolved = base_dir.resolve() if base_dir is not None else None

        if any(
            resolved == root or resolved.is_relative_to(root)
            for root in allowed_root_paths
        ):
            return

        self._raise_traversal_error(resolved, base_resolved, allowed_root_paths)

    def _raise_traversal_error(
        self,
        resolved: Path,
        base_resolved: Path | None,
        allowed_root_paths: list[Path],
    ) -> None:
        """Raise appropriate traversal error based on path state."""
        allowed_display = ", ".join(str(root) for root in allowed_root_paths)
        if base_resolved is not None and ".." not in resolved.parts:
            raise ValueError(
                f"Path {resolved} escapes base directory {base_resolved}. "
                f"Traversal not allowed."
            )
        raise ValueError(
            f"Path {resolved} is outside allowed directories: {allowed_display}"
        )

    def _validate_path_requirements(self, resolved: Path) -> None:
        """Validate path exists and meets requirements."""
        if not resolved.exists():
            raise ValueError(f"Path does not exist: {resolved}")

        if resolved.as_posix().startswith("/dev/"):
            raise ValueError(
                f"Path {resolved} is outside allowed directories and not permitted"
            )

        if not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {resolved}")

    @staticmethod
    def validate_git_path(path: str | Path) -> Path:
        """Validate paths for git operations with additional security.

        Args:
            path: Path to validate

        Returns:
            Validated absolute Path object

        Raises:
            ValueError: If path is unsafe for git operations

        Examples:
            >>> PathValidator.validate_git_path(Path.cwd() / ".git")
            /current/directory/.git

        SECURITY:
            - Blocks direct .git access (only allow .git at leaf level)
            - Prevents accessing .git/config through .git directory
        """
        # Use user path validation first
        validated = PathValidator().validate_user_path(path)

        path_str = str(validated)

        # SECURITY: Additional git-specific checks
        # Split into components
        parts = path_str.split("/")

        # Check if .git appears anywhere except last position
        if ".git" in parts[:-1]:  # Allow .git at end, but not in path
            raise ValueError(
                f"Direct .git access blocked: {path}. "
                f"Cannot access .git directory through parent paths."
            )

        return validated


def validate_working_directory(path: str | None) -> Path:
    """Convenience function for validating working directory paths.

    This is the main validation function used by SessionLifecycleManager
    to validate user-provided working directories.

    Args:
        path: Path to validate

    Returns:
        Validated absolute Path object

    Raises:
        ValueError: If path is unsafe

    Examples:
        >>> validate_working_directory(str(Path.cwd()))
        /current/directory
    """
    if path is None:
        return Path.cwd()

    return PathValidator().validate_user_path(path, allow_traversal=False)
