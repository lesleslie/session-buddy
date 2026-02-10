"""Base operational mode interface.

Defines the abstract interface that all operational modes must implement.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModeConfig:
    """Configuration for an operational mode.

    Attributes:
        name: Mode name (lite, standard, etc.)
        database_path: Path to database (:memory: for lite mode)
        storage_backend: Storage backend (memory, file, s3, etc.)
        enable_embeddings: Whether to enable ONNX embeddings
        enable_multi_project: Whether to enable multi-project coordination
        enable_token_optimization: Whether to enable token optimization
        enable_auto_checkpoint: Whether to enable auto-checkpoint
        enable_full_text_search: Whether to enable full-text search
        enable_faceted_search: Whether to enable faceted search
        enable_search_suggestions: Whether to enable search suggestions
        enable_auto_store: Whether to enable auto-store reflections
        enable_crackerjack: Whether to enable Crackerjack integration
        enable_git_integration: Whether to enable git integration

    Example:
        >>> config = ModeConfig(
        ...     name="lite",
        ...     database_path=":memory:",
        ...     storage_backend="memory",
        ...     enable_embeddings=False
        ... )
    """

    name: str
    database_path: str
    storage_backend: str

    # Feature flags
    enable_embeddings: bool = True
    enable_multi_project: bool = True
    enable_token_optimization: bool = True
    enable_auto_checkpoint: bool = True
    enable_full_text_search: bool = True
    enable_faceted_search: bool = True
    enable_search_suggestions: bool = True
    enable_auto_store: bool = True
    enable_crackerjack: bool = True
    enable_git_integration: bool = True

    # Additional settings
    additional_settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary.

        Returns:
            Dictionary representation of the config
        """
        return {
            "mode": self.name,
            "database_path": self.database_path,
            "storage_backend": self.storage_backend,
            "enable_embeddings": self.enable_embeddings,
            "enable_multi_project": self.enable_multi_project,
            "enable_token_optimization": self.enable_token_optimization,
            "enable_auto_checkpoint": self.enable_auto_checkpoint,
            "enable_full_text_search": self.enable_full_text_search,
            "enable_faceted_search": self.enable_faceted_search,
            "enable_search_suggestions": self.enable_search_suggestions,
            "enable_auto_store": self.enable_auto_store,
            "enable_crackerjack": self.enable_crackerjack,
            "enable_git_integration": self.enable_git_integration,
            **self.additional_settings,
        }


class OperationMode(ABC):
    """Abstract base class for operational modes.

    All operational modes must inherit from this class and implement
    the abstract methods.

    Example:
        >>> class LiteMode(OperationMode):
        ...     @property
        ...     def name(self) -> str:
        ...         return "lite"
        ...
        ...     def get_config(self) -> ModeConfig:
        ...         return ModeConfig(
        ...             name="lite",
        ...             database_path=":memory:",
        ...             storage_backend="memory"
        ...         )
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get mode name.

        Returns:
            Mode name (e.g., "lite", "standard")
        """
        ...

    @abstractmethod
    def get_config(self) -> ModeConfig:
        """Get mode configuration.

        Returns:
            ModeConfig instance with all mode-specific settings
        """
        ...

    def validate_environment(self) -> list[str]:
        """Validate that the environment supports this mode.

        Returns:
            List of validation errors (empty if valid)

        Example:
            >>> errors = mode.validate_environment()
            >>> if errors:
            ...     print(f"Validation errors: {errors}")
        """
        return []

    def get_startup_message(self) -> str:
        """Get startup message for this mode.

        Returns:
            Human-readable startup message

        Example:
            >>> message = mode.get_startup_message()
            >>> print(message)
            🚀 Starting Session-Buddy in lite mode...
        """
        return f"🚀 Starting Session-Buddy in {self.name} mode..."


# Mode registry
_MODE_REGISTRY: dict[str, type[OperationMode]] = {}


def register_mode(mode_class: type[OperationMode]) -> None:
    """Register a mode class.

    Args:
        mode_class: Mode class to register

    Example:
        >>> @register_mode
        ... class LiteMode(OperationMode):
        ...     pass
    """
    _MODE_REGISTRY[mode_class.__name__.lower()] = mode_class


def get_mode(mode_name: str | None = None) -> OperationMode:
    """Get mode instance by name.

    Args:
        mode_name: Mode name (lite, standard). If None, detects from environment.

    Returns:
        OperationMode instance

    Raises:
        ValueError: If mode name is invalid

    Example:
        >>> # Detect from environment
        >>> mode = get_mode()
        >>>
        >>> # Specify mode explicitly
        >>> mode = get_mode("lite")
    """
    if mode_name is None:
        # Detect from environment variable
        mode_name = os.getenv("SESSION_BUDDY_MODE", "standard").lower()

    # Normalize mode name
    mode_name = mode_name.lower().replace("_", "").replace("-", "")

    # Map mode names to classes
    mode_classes: dict[str, type[OperationMode]] = {
        "lite": LiteMode,
        "standard": StandardMode,
    }

    mode_class = mode_classes.get(mode_name)
    if mode_class is None:
        available = ", ".join(mode_classes.keys())
        msg = f"Invalid mode '{mode_name}'. Available modes: {available}"
        raise ValueError(msg)

    return mode_class()


# Import mode implementations to register them
from session_buddy.modes.lite import LiteMode
from session_buddy.modes.standard import StandardMode
