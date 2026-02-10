"""JSON Schema registry for session event models.

This module provides a centralized schema registry for all session-related
event models, including version management, export capabilities, and
validation utilities.

Schema Versioning:
    - Current version: 1.0
    - Format: JSON Schema Draft 2020-12 (http://json-schema.org/draft/2020-12/schema)
    - Evolution strategy: Backward-compatible additive changes only

Usage:
    >>> from session_buddy.mcp.schemas import (
    ...     get_all_schemas,
    ...     get_schema_version,
    ...     validate_event_json,
    ... )
    >>>
    >>> # Get all schemas
    >>> schemas = get_all_schemas()
    >>>
    >>> # Get specific version
    >>> version = get_schema_version()
    >>>
    >>> # Validate JSON
    >>> event = validate_event_json('{"event_type": "session_start", ...}')
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from session_buddy.mcp.event_models import (
    EnvironmentInfo,
    ErrorResponse,
    SessionEndEvent,
    SessionEndResult,
    SessionStartEvent,
    SessionStartResult,
    UserInfo,
)

# Schema metadata
SCHEMA_VERSION = "1.0"
SCHEMA_FORMAT = "json-schema"
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


class SchemaRegistry:
    """Centralized registry for event model schemas.

    This class provides methods to export, validate, and manage JSON schemas
    for all session-related event models.

    Attributes:
        version: Current schema version
        format: Schema format identifier
        models: Mapping of model names to Pydantic model classes

    Example:
        >>> registry = SchemaRegistry()
        >>> schemas = registry.export_all()
        >>> schema = registry.get_schema("SessionStartEvent")
    """

    def __init__(self) -> None:
        """Initialize schema registry with all event models."""
        self.version = SCHEMA_VERSION
        self.format = SCHEMA_FORMAT
        self._models: dict[str, type] = {
            "SessionStartEvent": SessionStartEvent,
            "SessionEndEvent": SessionEndEvent,
            "SessionStartResult": SessionStartResult,
            "SessionEndResult": SessionEndResult,
            "ErrorResponse": ErrorResponse,
            "UserInfo": UserInfo,
            "EnvironmentInfo": EnvironmentInfo,
        }

    def get_schema(self, model_name: str) -> dict[str, Any]:
        """Get JSON Schema for a specific model.

        Args:
            model_name: Name of the model (e.g., "SessionStartEvent")

        Returns:
            JSON Schema dictionary with metadata

        Raises:
            ValueError: If model_name is not registered

        Example:
            >>> registry = SchemaRegistry()
            >>> schema = registry.get_schema("SessionStartEvent")
            >>> print(schema["$schema"])
            https://json-schema.org/draft/2020-12/schema
        """
        if model_name not in self._models:
            raise ValueError(
                f"Unknown model: {model_name}. "
                f"Available models: {list(self._models.keys())}"
            )

        model_class = self._models[model_name]
        schema = model_class.model_json_schema()

        # Add schema metadata
        schema["$schema"] = JSON_SCHEMA_DRAFT
        schema["event_version"] = self.version
        schema["title"] = model_name

        return schema

    def export_all(self) -> dict[str, dict[str, Any]]:
        """Export all registered model schemas.

        Returns:
            Dictionary mapping model names to their JSON schemas

        Example:
            >>> registry = SchemaRegistry()
            >>> schemas = registry.export_all()
            >>> print(schemas["SessionStartEvent"]["title"])
            SessionStartEvent
        """
        return {
            model_name: self.get_schema(model_name)
            for model_name in self._models.keys()
        }

    def validate_json(
        self,
        model_name: str,
        json_data: str | dict[str, Any],
    ) -> Any:
        """Validate JSON data against a model schema.

        Args:
            model_name: Name of the model to validate against
            json_data: JSON string or dictionary to validate

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If model_name is not registered
            ValidationError: If JSON data is invalid

        Example:
            >>> registry = SchemaRegistry()
            >>> event = registry.validate_json(
            ...     "SessionStartEvent",
            ...     '{"event_version": "1.0", ...}'
            ... )
        """
        if model_name not in self._models:
            raise ValueError(f"Unknown model: {model_name}")

        model_class = self._models[model_name]

        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data

        return model_class(**data)

    def list_models(self) -> list[str]:
        """List all registered model names.

        Returns:
            List of model names

        Example:
            >>> registry = SchemaRegistry()
            >>> models = registry.list_models()
            >>> print(models)
            ['SessionStartEvent', 'SessionEndEvent', ...]
        """
        return list(self._models.keys())

    def get_version(self) -> str:
        """Get current schema version.

        Returns:
            Schema version string

        Example:
            >>> registry = SchemaRegistry()
            >>> version = registry.get_version()
            >>> print(version)
            1.0
        """
        return self.version


# Global registry instance
_registry = SchemaRegistry()


# Public API functions


def get_all_schemas() -> dict[str, dict[str, Any]]:
    """Get JSON schemas for all event models.

    This is a convenience function that accesses the global registry.

    Returns:
        Dictionary mapping model names to their JSON schemas

    Example:
        >>> schemas = get_all_schemas()
        >>> print(schemas["SessionStartEvent"]["$schema"])
        https://json-schema.org/draft/2020-12/schema
    """
    return _registry.export_all()


def get_schema(model_name: str) -> dict[str, Any]:
    """Get JSON Schema for a specific model.

    Args:
        model_name: Name of the model (e.g., "SessionStartEvent")

    Returns:
        JSON Schema dictionary

    Raises:
        ValueError: If model_name is not registered

    Example:
        >>> schema = get_schema("SessionStartEvent")
        >>> print(schema["title"])
        SessionStartEvent
    """
    return _registry.get_schema(model_name)


def validate_event_json(
    model_name: str,
    json_data: str | dict[str, Any],
) -> Any:
    """Validate JSON data against an event model schema.

    This is a convenience function that accesses the global registry.

    Args:
        model_name: Name of the model to validate against
        json_data: JSON string or dictionary to validate

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If model_name is not registered
        ValidationError: If JSON data is invalid

    Example:
        >>> event = validate_event_json(
        ...     "SessionStartEvent",
        ...     '{"event_version": "1.0", ...}'
        ... )
    """
    return _registry.validate_json(model_name, json_data)


def get_schema_version() -> str:
    """Get current schema version.

    Returns:
        Schema version string

    Example:
        >>> version = get_schema_version()
        >>> print(version)
        1.0
    """
    return _registry.get_version()


def list_event_models() -> list[str]:
    """List all registered event model names.

    Returns:
        List of model names

    Example:
        >>> models = list_event_models()
        >>> print(models)
        ['SessionStartEvent', 'SessionEndEvent', ...]
    """
    return _registry.list_models()


def export_schemas_to_file(
    output_path: str | Path,
    format: Literal["json", "yaml"] = "json",
) -> None:
    """Export all schemas to a file.

    Args:
        output_path: Path to output file
        format: Output format ("json" or "yaml")

    Raises:
        ValueError: If format is not supported
        IOError: If file cannot be written

    Example:
        >>> export_schemas_to_file("schemas.json")
        >>> export_schemas_to_file("schemas.yaml", format="yaml")
    """
    schemas = get_all_schemas()
    output_path = Path(output_path)

    if format == "json":
        with output_path.open("w") as f:
            json.dump(schemas, f, indent=2)
    elif format == "yaml":
        try:
            import yaml

            with output_path.open("w") as f:
                yaml.dump(schemas, f, default_flow_style=False)
        except ImportError:
            raise ValueError("YAML format requires PyYAML: pip install pyyaml")
    else:
        raise ValueError(f"Unsupported format: {format}")


def get_schema_changelog() -> dict[str, str]:
    """Get schema version changelog.

    Returns:
        Dictionary mapping version numbers to change descriptions

    Example:
        >>> changelog = get_schema_changelog()
        >>> print(changelog["1.0"])
        Initial schema version with SessionStartEvent and SessionEndEvent
    """
    return {
        "1.0": (
            "Initial schema version. "
            "Includes SessionStartEvent, SessionEndEvent, "
            "SessionStartResult, SessionEndResult, ErrorResponse, "
            "UserInfo, and EnvironmentInfo models."
        ),
    }


# Schema compatibility utilities


def check_schema_compatibility(
    event_version: str,
    required_version: str = SCHEMA_VERSION,
) -> bool:
    """Check if an event version is compatible with the current schema.

    Args:
        event_version: Event version to check
        required_version: Required schema version (defaults to current)

    Returns:
        True if versions are compatible

    Example:
        >>> compatible = check_schema_compatibility("1.0")
        >>> print(compatible)
        True
    """
    # For now, only exact version match is supported
    # Future versions may implement backward compatibility
    return event_version == required_version


def validate_event_version(event_version: str) -> None:
    """Validate that an event version is supported.

    Args:
        event_version: Event version to validate

    Raises:
        ValueError: If version is not supported

    Example:
        >>> validate_event_version("1.0")  # OK
        >>> validate_event_version("2.0")  # Raises ValueError
    """
    if not check_schema_compatibility(event_version):
        supported_versions = list(get_schema_changelog().keys())
        raise ValueError(
            f"Unsupported event version: {event_version}. "
            f"Supported versions: {supported_versions}"
        )
