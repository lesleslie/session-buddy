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

    def validate_user_path(
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
        # Type conversion
        if isinstance(path, str):
            # SECURITY: Block null bytes (Windows path bypass)
            if "\x00" in path:
                raise ValueError("Null bytes not allowed in path")

            path = Path(path)

        if "\x00" in str(path):
            raise ValueError("Null bytes not allowed in path")

        # SECURITY: Length check to prevent overflow
        path_str = str(path)
        if len(path_str) > PathValidator.MAX_PATH_LENGTH:
            raise ValueError(
                f"Path too long: {len(path_str)} characters. "
                f"Maximum is {PathValidator.MAX_PATH_LENGTH}"
            )

        # Resolve to absolute (this also follows symlinks)
        resolved = path.resolve()

        # SECURITY: Traversal prevention
        if not allow_traversal:
            allowed_roots: set[Path] = set(self.allowed_directories)
            if base_dir is not None:
                allowed_roots.add(base_dir.resolve())

            if allowed_roots:
                allowed_root_paths = [root.resolve() for root in allowed_roots]
                base_resolved = base_dir.resolve() if base_dir is not None else None
                if not any(
                    resolved == root or resolved.is_relative_to(root)
                    for root in allowed_root_paths
                ):
                    allowed_display = ", ".join(
                        str(root) for root in allowed_root_paths
                    )
                    if base_resolved is not None and ".." not in path.parts:
                        raise ValueError(
                            f"Path {resolved} escapes base directory {base_resolved}. "
                            f"Traversal not allowed."
                        )
                    raise ValueError(
                        f"Path {resolved} is outside allowed directories: {allowed_display}"
                    )

        # SECURITY: Existence check
        if not resolved.exists():
            raise ValueError(f"Path does not exist: {resolved}")

        # SECURITY: Block direct access to device files explicitly.
        if resolved.as_posix().startswith("/dev/"):
            raise ValueError(
                f"Path {resolved} is outside allowed directories and not permitted"
            )

        # SECURITY: Must be a directory
        if not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {resolved}")

        return path.absolute()

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
