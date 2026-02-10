"""Lite operational mode - zero-dependency, in-memory mode.

Lite mode is designed for:
- Quick testing and development
- CI/CD pipelines
- Temporary sessions
- Performance testing

Features:
- In-memory database (:memory:)
- In-memory storage
- No embeddings (faster startup)
- No multi-project coordination
- No token optimization
- No auto-checkpoint

Setup Time: < 2 minutes
"""

from __future__ import annotations

from session_buddy.modes.base import ModeConfig, OperationMode


class LiteMode(OperationMode):
    """Lite operational mode with in-memory database and storage.

    This mode provides the fastest startup time and minimal dependencies,
    but does not persist data across restarts.

    Example:
        >>> from session_buddy.modes import LiteMode
        >>>
        >>> mode = LiteMode()
        >>> config = mode.get_config()
        >>> print(config.database_path)  # :memory:
    """

    @property
    def name(self) -> str:
        """Get mode name.

        Returns:
            Mode name
        """
        return "lite"

    def get_config(self) -> ModeConfig:
        """Get lite mode configuration.

        Returns:
            ModeConfig optimized for minimal dependencies and fast startup

        Example:
            >>> mode = LiteMode()
            >>> config = mode.get_config()
            >>> print(config.database_path)  # :memory:
            >>> print(config.storage_backend)  # memory
            >>> print(config.enable_embeddings)  # False
        """
        return ModeConfig(
            name="lite",
            database_path=":memory:",  # In-memory database
            storage_backend="memory",  # In-memory storage
            # Disable heavy features for fast startup
            enable_embeddings=False,  # No ONNX model loading
            enable_multi_project=False,  # No cross-project coordination
            enable_token_optimization=False,  # No token optimization
            enable_auto_checkpoint=False,  # No auto-checkpoint
            enable_full_text_search=True,  # Keep basic search
            enable_faceted_search=False,  # No faceted search
            enable_search_suggestions=False,  # No search suggestions
            enable_auto_store=False,  # No auto-store
            enable_crackerjack=False,  # No Crackerjack integration
            enable_git_integration=False,  # No git integration
        )

    def validate_environment(self) -> list[str]:
        """Validate that the environment supports lite mode.

        Lite mode has minimal requirements, so validation always passes.

        Returns:
            Empty list (no errors)

        Example:
            >>> mode = LiteMode()
            >>> errors = mode.validate_environment()
            >>> assert len(errors) == 0
        """
        return []

    def get_startup_message(self) -> str:
        """Get startup message for lite mode.

        Returns:
            Human-readable startup message with mode characteristics

        Example:
            >>> mode = LiteMode()
            >>> message = mode.get_startup_message()
            >>> print(message)
            🚀 Starting Session-Buddy in lite mode...
            ⚡ In-memory database (no persistence)
            📦 Minimal dependencies
            ⏱️  Fast startup (< 2 seconds)
        """
        return """🚀 Starting Session-Buddy in lite mode...
⚡ In-memory database (no persistence)
📦 Minimal dependencies
⏱️  Fast startup (< 2 seconds)

⚠️  WARNING: Data will not persist across restarts!
"""

    def to_dict(self) -> dict[str, bool | str]:
        """Get lite mode configuration as dictionary.

        Returns:
            Dictionary with mode settings

        Example:
            >>> mode = LiteMode()
            >>> config_dict = mode.to_dict()
            >>> print(config_dict['mode'])  # lite
            >>> print(config_dict['database_path'])  # :memory:
        """
        config = self.get_config()
        return config.to_dict()
