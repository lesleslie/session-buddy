"""Standard operational mode - full-featured production mode.

Standard mode is designed for:
- Daily development
- Production deployments
- Persistent data storage
- Full feature set

Features:
- File-based database (~/.claude/data/reflection.duckdb)
- File-based storage
- ONNX embeddings (semantic search)
- Multi-project coordination
- Token optimization
- Auto-checkpoint
- Crackerjack integration
- Git integration

Setup Time: ~ 5 minutes
"""

from __future__ import annotations

import os
from pathlib import Path

from session_buddy.modes.base import ModeConfig, OperationMode


class StandardMode(OperationMode):
    """Standard operational mode with persistent storage and full features.

    This mode provides the complete Session-Buddy experience with all
    features enabled and persistent data storage.

    Example:
        >>> from session_buddy.modes import StandardMode
        >>>
        >>> mode = StandardMode()
        >>> config = mode.get_config()
        >>> print(config.database_path)  # ~/.claude/data/reflection.duckdb
        >>> print(config.enable_embeddings)  # True
    """

    @property
    def name(self) -> str:
        """Get mode name.

        Returns:
            Mode name
        """
        return "standard"

    def get_config(self) -> ModeConfig:
        """Get standard mode configuration.

        Returns:
            ModeConfig with all features enabled

        Example:
            >>> mode = StandardMode()
            >>> config = mode.get_config()
            >>> print(config.database_path)  # ~/.claude/data/reflection.duckdb
            >>> print(config.storage_backend)  # file
            >>> print(config.enable_embeddings)  # True
        """
        # Use default database path
        data_dir = Path(os.path.expanduser("~/.claude/data"))
        database_path = str(data_dir / "reflection.duckdb")

        return ModeConfig(
            name="standard",
            database_path=database_path,  # File-based database
            storage_backend="file",  # File-based storage
            # Enable all features
            enable_embeddings=True,  # ONNX embeddings
            enable_multi_project=True,  # Cross-project coordination
            enable_token_optimization=True,  # Token optimization
            enable_auto_checkpoint=True,  # Auto-checkpoint
            enable_full_text_search=True,  # Full-text search
            enable_faceted_search=True,  # Faceted search
            enable_search_suggestions=True,  # Search suggestions
            enable_auto_store=True,  # Auto-store reflections
            enable_crackerjack=True,  # Crackerjack integration
            enable_git_integration=True,  # Git integration
        )

    def validate_environment(self) -> list[str]:
        """Validate that the environment supports standard mode.

        Checks for:
        - Writable data directory
        - Sufficient disk space

        Returns:
            List of validation errors (empty if valid)

        Example:
            >>> mode = StandardMode()
            >>> errors = mode.validate_environment()
            >>> if errors:
            ...     print(f"Validation errors: {errors}")
        """
        errors = []

        # Check data directory is writable
        data_dir = Path(os.path.expanduser("~/.claude/data"))
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = data_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            errors.append(
                f"Data directory {data_dir} is not writable. Check permissions."
            )
        except Exception as e:
            errors.append(f"Failed to access data directory: {e}")

        return errors

    def get_startup_message(self) -> str:
        """Get startup message for standard mode.

        Returns:
            Human-readable startup message with mode characteristics

        Example:
            >>> mode = StandardMode()
            >>> message = mode.get_startup_message()
            >>> print(message)
            🚀 Starting Session-Buddy in standard mode...
            💾 Persistent database (~/.claude/data/reflection.duckdb)
            📦 Full feature set
            🧠 Semantic search enabled
        """
        return """🚀 Starting Session-Buddy in standard mode...
💾 Persistent database (~/.claude/data/reflection.duckdb)
📦 Full feature set
🧠 Semantic search enabled
🌐 Multi-project coordination enabled
⚡ Token optimization enabled
🔄 Auto-checkpoint enabled
"""

    def to_dict(self) -> dict[str, bool | str]:
        """Get standard mode configuration as dictionary.

        Returns:
            Dictionary with mode settings

        Example:
            >>> mode = StandardMode()
            >>> config_dict = mode.to_dict()
            >>> print(config_dict['mode'])  # standard
            >>> print(config_dict['database_path'])  # ~/.claude/data/reflection.duckdb
        """
        config = self.get_config()
        return config.to_dict()
