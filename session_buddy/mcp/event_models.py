"""Pydantic models for admin shell session event validation.

This module provides type-safe models for session lifecycle events received
from admin shells (Mahavishnu, Session-Buddy, Oneiric, etc.) via MCP tools.

It also includes response models for MCP tool results.

Event Flow:
    1. Admin shell starts → emits SessionStartEvent
    2. MCP tool receives event → validates with Pydantic
    3. SessionTracker creates session record
    4. Returns SessionStartResult with session_id
    5. Admin shell exits → emits SessionEndEvent
    6. MCP tool receives event → validates with Pydantic
    7. SessionTracker updates record
    8. Returns SessionEndResult with status

Example:
    >>> from session_buddy.mcp.event_models import SessionStartEvent, SessionStartResult
    >>> event = SessionStartEvent(
    ...     event_version="1.0",
    ...     event_id="550e8400-e29b-41d4-a716-446655440000",
    ...     component_name="mahavishnu",
    ...     shell_type="MahavishnuShell",
    ...     pid=12345,
    ...     user=UserInfo(username="john", home="/home/john"),
    ...     hostname="server01",
    ...     environment=EnvironmentInfo(
    ...         python_version="3.13.0",
    ...         platform="Linux-6.5.0-x86_64",
    ...         cwd="/home/john/projects/mahavishnu"
    ...     )
    ... )
    >>> result = SessionStartResult(session_id="sess_abc123", status="tracked")
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# Schema metadata
SCHEMA_VERSION = "1.0"
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


class JsonSchemaMixin:
    """Mixin class providing JSON Schema export and validation methods.

    This mixin adds standardized schema methods to Pydantic models for
    consistent schema export and JSON validation across all event models.

    Example:
        >>> class MyEvent(BaseModel, JsonSchemaMixin):
        ...     pass
        >>>
        >>> schema = MyEvent.json_schema()
        >>> event = MyEvent.validate_json('{"field": "value"}')
    """

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        """Get JSON Schema for this model.

        Returns:
            JSON Schema dictionary with metadata

        Example:
            >>> schema = SessionStartEvent.json_schema()
            >>> print(schema["$schema"])
            https://json-schema.org/draft/2020-12/schema
        """
        schema = cls.model_json_schema()
        schema["$schema"] = JSON_SCHEMA_DRAFT
        schema["event_version"] = SCHEMA_VERSION
        return schema

    @classmethod
    def validate_json(cls, json_data: str | dict[str, Any]) -> JsonSchemaMixin:
        """Validate JSON data and return model instance.

        Args:
            json_data: JSON string or dictionary to validate

        Returns:
            Validated model instance

        Raises:
            ValidationError: If JSON data is invalid

        Example:
            >>> event = SessionStartEvent.validate_json('{"..."}')
            >>> assert isinstance(event, SessionStartEvent)
        """
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data

        return cls(**data)

    @classmethod
    def validate_json_safe(
        cls,
        json_data: str | dict[str, Any],
    ) -> tuple[JsonSchemaMixin | None, ValidationError | None]:
        """Validate JSON data with error handling.

        Args:
            json_data: JSON string or dictionary to validate

        Returns:
            Tuple of (model_instance, validation_error)
            One will always be None

        Example:
            >>> event, error = SessionStartEvent.validate_json_safe(data)
            >>> if error:
            ...     print(f"Validation failed: {error}")
        """
        try:
            return cls.validate_json(json_data), None
        except ValidationError as e:
            return None, e


class UserInfo(BaseModel, JsonSchemaMixin):
    """User information for session tracking.

    Attributes:
        username: System username (sanitized, max 100 chars)
        home: User home directory path (max 500 chars)

    Example:
        >>> user = UserInfo(username="john", home="/home/john")
    """

    username: str = Field(
        ...,
        max_length=100,
        description="System username (truncated to 100 characters)",
    )
    home: str = Field(
        ...,
        max_length=500,
        description="User home directory path (truncated to 500 characters)",
    )

    @field_validator("username", "home")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip leading/trailing whitespace from user fields.

        Args:
            v: Field value to validate

        Returns:
            Stripped string value
        """
        return v.strip()


class EnvironmentInfo(BaseModel, JsonSchemaMixin):
    """Environment information for session tracking.

    Attributes:
        python_version: Python interpreter version (e.g., "3.13.0")
        platform: Platform identifier (e.g., "Linux-6.5.0-x86_64")
        cwd: Current working directory (max 500 chars)

    Example:
        >>> env = EnvironmentInfo(
        ...     python_version="3.13.0",
        ...     platform="Linux-6.5.0-x86_64",
        ...     cwd="/home/john/projects"
        ... )
    """

    python_version: str = Field(
        ...,
        description="Python interpreter version",
    )
    platform: str = Field(
        ...,
        description="Operating system and platform identifier",
    )
    cwd: str = Field(
        ...,
        max_length=500,
        description="Current working directory (truncated to 500 characters)",
    )

    @field_validator("cwd")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip leading/trailing whitespace from path.

        Args:
            v: Field value to validate

        Returns:
            Stripped string value
        """
        return v.strip()


class SessionStartEvent(BaseModel, JsonSchemaMixin):
    """Session start event received from admin shells.

    This event is received when an admin shell (MahavishnuShell, SessionBuddyShell,
    etc.) starts up. It contains comprehensive metadata about the session for
    tracking and analysis.

    Attributes:
        event_version: Event format version (must be "1.0")
        event_id: Unique event identifier (UUID v4)
        event_type: Event type discriminator (must be "session_start")
        component_name: Component name (alphanumeric, underscore, hyphen only)
        shell_type: Shell class name (e.g., "MahavishnuShell")
        timestamp: ISO 8601 timestamp in UTC
        pid: Process ID (1-4194304 range)
        user: User information (username, home directory)
        hostname: System hostname
        environment: Environment information (Python version, platform, cwd)
        metadata: Optional additional metadata dict

    Example:
        >>> event = SessionStartEvent(
        ...     event_version="1.0",
        ...     event_id="550e8400-e29b-41d4-a716-446655440000",
        ...     component_name="mahavishnu",
        ...     shell_type="MahavishnuShell",
        ...     timestamp="2026-02-06T12:34:56.789Z",
        ...     pid=12345,
        ...     user=UserInfo(username="john", home="/home/john"),
        ...     hostname="server01",
        ...     environment=EnvironmentInfo(
        ...         python_version="3.13.0",
        ...         platform="Linux-6.5.0-x86_64",
        ...         cwd="/home/john/projects"
        ...     )
        ... )
    """

    event_version: str = Field(
        ...,
        description="Event format version (currently '1.0')",
    )
    event_id: str = Field(
        ...,
        description="Unique event identifier (UUID v4 string)",
    )
    event_type: str = Field(
        default="session_start",
        description="Event type discriminator",
    )
    component_name: str = Field(
        ...,
        description="Component name (e.g., 'mahavishnu', 'session-buddy')",
    )
    shell_type: str = Field(
        ...,
        description="Shell class name (e.g., 'MahavishnuShell')",
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp in UTC",
    )
    pid: int = Field(
        ...,
        description="Process ID (1-4194304)",
        ge=1,
        le=4194304,
    )
    user: UserInfo = Field(
        ...,
        description="User information",
    )
    hostname: str = Field(
        ...,
        description="System hostname",
    )
    environment: EnvironmentInfo = Field(
        ...,
        description="Environment information",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional metadata",
    )

    @field_validator("event_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        """Validate that event_id is a valid UUID v4.

        Args:
            v: Event ID string to validate

        Returns:
            Validated event ID

        Raises:
            ValueError: If event_id is not a valid UUID
        """
        try:
            UUID(v, version=4)
        except ValueError as e:
            raise ValueError(f"Invalid UUID v4 format: {v}") from e
        return v

    @field_validator("event_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate that event_version is supported.

        Args:
            v: Event version string to validate

        Returns:
            Validated version

        Raises:
            ValueError: If version is not supported
        """
        if v != "1.0":
            raise ValueError(f"Unsupported event version: {v} (expected '1.0')")
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Validate that event_type matches model.

        Args:
            v: Event type string to validate

        Returns:
            Validated event type

        Raises:
            ValueError: If event_type is incorrect
        """
        if v != "session_start":
            raise ValueError(f"Invalid event_type for SessionStartEvent: {v}")
        return v

    @field_validator("component_name")
    @classmethod
    def validate_component_name(cls, v: str) -> str:
        """Validate component name format (alphanumeric, underscore, hyphen).

        Args:
            v: Component name to validate

        Returns:
            Validated component name

        Raises:
            ValueError: If component name contains invalid characters
        """
        pattern = r"^[a-zA-Z0-9_-]+$"
        if not re.match(pattern, v):
            raise ValueError(
                f"Invalid component_name '{v}': must match pattern {pattern}"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate ISO 8601 timestamp format.

        Args:
            v: Timestamp string to validate

        Returns:
            Validated timestamp

        Raises:
            ValueError: If timestamp is not valid ISO 8601
        """
        # Check for 'T' separator to ensure time component is present
        if "T" not in v:
            raise ValueError(
                f"Invalid ISO 8601 timestamp: {v} (missing time component, expected format: 2026-02-06T12:34:56.789Z)"
            )

        try:
            # Try parsing with timezone
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(
                f"Invalid ISO 8601 timestamp: {v} (expected format: 2026-02-06T12:34:56.789Z)"
            ) from e
        return v

    @model_validator(mode="after")
    def validate_consistency(self) -> SessionStartEvent:
        """Validate cross-field consistency.

        Returns:
            Validated SessionStartEvent instance

        Raises:
            ValueError: If fields are inconsistent
        """
        # Ensure event_type matches model
        if self.event_type != "session_start":
            raise ValueError(
                f"event_type must be 'session_start' for SessionStartEvent, got '{self.event_type}'"
            )
        return self


class SessionEndEvent(BaseModel, JsonSchemaMixin):
    """Session end event received from admin shells.

    This event is received when an admin shell exits. It references the
    session_id from the initial SessionStartEvent to link the lifecycle.

    Attributes:
        event_type: Event type discriminator (must be "session_end")
        session_id: Session ID from SessionStartEvent response
        timestamp: ISO 8601 timestamp in UTC
        metadata: Optional additional metadata dict

    Example:
        >>> event = SessionEndEvent(
        ...     session_id="sess_abc123",
        ...     timestamp="2026-02-06T13:45:67.890Z",
        ...     metadata={"exit_reason": "user_exit"}
        ... )
    """

    event_type: str = Field(
        default="session_end",
        description="Event type discriminator",
    )
    session_id: str = Field(
        ...,
        description="Session ID from SessionStartEvent response",
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp in UTC",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional metadata",
    )

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Validate that event_type matches model.

        Args:
            v: Event type string to validate

        Returns:
            Validated event type

        Raises:
            ValueError: If event_type is incorrect
        """
        if v != "session_end":
            raise ValueError(f"Invalid event_type for SessionEndEvent: {v}")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate ISO 8601 timestamp format.

        Args:
            v: Timestamp string to validate

        Returns:
            Validated timestamp

        Raises:
            ValueError: If timestamp is not valid ISO 8601
        """
        # Check for 'T' separator to ensure time component is present
        if "T" not in v:
            raise ValueError(
                f"Invalid ISO 8601 timestamp: {v} (missing time component, expected format: 2026-02-06T12:34:56.789Z)"
            )

        try:
            # Try parsing with timezone
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(
                f"Invalid ISO 8601 timestamp: {v} (expected format: 2026-02-06T12:34:56.789Z)"
            ) from e
        return v


# Result models for MCP tool responses


class SessionStartResult(BaseModel, JsonSchemaMixin):
    """Result model for session start MCP tool.

    This model is returned by the track_session_start MCP tool to indicate
    the result of session creation.

    Attributes:
        session_id: Unique session identifier (or None if failed)
        status: Status discriminator ("tracked", "error")
        error: Error message if status is "error"

    Example:
        >>> result = SessionStartResult(
        ...     session_id="sess_abc123",
        ...     status="tracked"
        ... )
    """

    session_id: str | None = Field(
        ...,
        description="Unique session identifier (None if creation failed)",
    )
    status: str = Field(
        ...,
        description="Operation status ('tracked', 'error')",
    )
    error: str | None = Field(
        default=None,
        description="Error message if status is 'error'",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status value.

        Args:
            v: Status string to validate

        Returns:
            Validated status

        Raises:
            ValueError: If status is not valid
        """
        valid_statuses = {"tracked", "error"}
        if v not in valid_statuses:
            raise ValueError(f"Invalid status: {v} (must be one of {valid_statuses})")
        return v

    @model_validator(mode="after")
    def validate_consistency(self) -> SessionStartResult:
        """Validate cross-field consistency.

        Returns:
            Validated SessionStartResult instance

        Raises:
            ValueError: If fields are inconsistent
        """
        if self.status == "error":
            if self.session_id is not None:
                raise ValueError("session_id must be None when status is 'error'")
            if self.error is None:
                raise ValueError("error message required when status is 'error'")
        elif self.status == "tracked":
            if self.session_id is None:
                raise ValueError("session_id required when status is 'tracked'")
            if self.error is not None:
                raise ValueError("error must be None when status is 'tracked'")
        return self


class SessionEndResult(BaseModel, JsonSchemaMixin):
    """Result model for session end MCP tool.

    This model is returned by the track_session_end MCP tool to indicate
    the result of session update.

    Attributes:
        session_id: Session ID that was updated
        status: Status discriminator ("ended", "error", "not_found")
        error: Error message if status is "error"

    Example:
        >>> result = SessionEndResult(
        ...     session_id="sess_abc123",
        ...     status="ended"
        ... )
    """

    session_id: str = Field(
        ...,
        description="Session ID that was updated",
    )
    status: str = Field(
        ...,
        description="Operation status ('ended', 'error', 'not_found')",
    )
    error: str | None = Field(
        default=None,
        description="Error message if status is 'error'",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status value.

        Args:
            v: Status string to validate

        Returns:
            Validated status

        Raises:
            ValueError: If status is not valid
        """
        valid_statuses = {"ended", "error", "not_found"}
        if v not in valid_statuses:
            raise ValueError(f"Invalid status: {v} (must be one of {valid_statuses})")
        return v

    @model_validator(mode="after")
    def validate_consistency(self) -> SessionEndResult:
        """Validate cross-field consistency.

        Returns:
            Validated SessionEndResult instance

        Raises:
            ValueError: If fields are inconsistent
        """
        if self.status == "error" and self.error is None:
            raise ValueError("error message required when status is 'error'")
        if self.status in {"ended", "not_found"} and self.error is not None:
            raise ValueError("error must be None when status is 'ended' or 'not_found'")
        return self


class ErrorResponse(BaseModel, JsonSchemaMixin):
    """Generic error response model for MCP tools.

    This model is used for standardized error responses across all
    session tracking MCP tools.

    Attributes:
        error: Error message
        detail: Detailed error information
        error_code: Optional error code for programmatic handling

    Example:
        >>> error = ErrorResponse(
        ...     error="Invalid session ID",
        ...     detail="Session 'sess_invalid' not found in database",
        ...     error_code="SESSION_NOT_FOUND"
        ... )
    """

    error: str = Field(
        ...,
        description="Error message",
    )
    detail: str = Field(
        ...,
        description="Detailed error information",
    )
    error_code: str | None = Field(
        default=None,
        description="Optional error code for programmatic handling",
    )


# JSON Schema exports for external validation


def get_session_start_event_schema() -> dict[str, Any]:
    """Get JSON Schema for SessionStartEvent validation.

    This schema can be used for external validation or documentation.

    Returns:
        JSON Schema dictionary

    Example:
        >>> schema = get_session_start_event_schema()
        >>> # Use with jsonschema library or other validators
    """
    return SessionStartEvent.json_schema()


def get_session_end_event_schema() -> dict[str, Any]:
    """Get JSON Schema for SessionEndEvent validation.

    This schema can be used for external validation or documentation.

    Returns:
        JSON Schema dictionary

    Example:
        >>> schema = get_session_end_event_schema()
        >>> # Use with jsonschema library or other validators
    """
    return SessionEndEvent.json_schema()


def get_session_start_result_schema() -> dict[str, Any]:
    """Get JSON Schema for SessionStartResult validation.

    This schema can be used for external validation or documentation.

    Returns:
        JSON Schema dictionary
    """
    return SessionStartResult.json_schema()


def get_session_end_result_schema() -> dict[str, Any]:
    """Get JSON Schema for SessionEndResult validation.

    This schema can be used for external validation or documentation.

    Returns:
        JSON Schema dictionary
    """
    return SessionEndResult.json_schema()
