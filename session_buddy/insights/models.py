"""
Insight data models with security-focused validation.

This module provides type-safe, immutable data structures for insights
capture with comprehensive input validation to prevent security vulnerabilities.

Uses Pydantic BaseModel for automatic validation, type coercion, and serialization.
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Final

from pydantic import BaseModel, Field, field_validator

# Security constants
MAX_CONTENT_LENGTH: Final[int] = 10000  # Prevent DoS from huge insights
MAX_TOPICS: Final[int] = 20  # Reasonable limit for topic tags
MAX_PROJECTS: Final[int] = 50  # Prevent abuse with massive project lists
MIN_QUALITY: Final[float] = 0.0
MAX_QUALITY: Final[float] = 1.0

# Validation patterns
SAFE_PROJECT_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_-]+$")
SAFE_COLLECTION_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_]+$")


class Insight(BaseModel):
    """
    Immutable insight model with comprehensive validation.

    This frozen Pydantic model ensures immutability and thread safety for insights
    stored in the database. All fields are validated at construction time to
    prevent invalid data from entering the system.

    Security Features:
    - Frozen structure prevents accidental modification
    - Content length limits prevent DoS attacks
    - Project name sanitization prevents information disclosure
    - Type safety with comprehensive type hints
    - Automatic type coercion from database strings

    Example:
        ```python
        insight = Insight(
            id=str(uuid.uuid4()),
            content="Use async/await for database operations",
            topics=["async-patterns", "database"],
            projects=["session-buddy"],
            quality_score=0.8,
        )
        ```

    Pydantic Advantages:
    - Automatic validation via Field constraints
    - Type coercion handles DuckDB string outputs
    - Built-in model_dump() for serialization
    - Built-in model_validate() for deserialization
    - Declarative validators are self-documenting

    """

    # Configuration: frozen = True makes it immutable
    model_config = {"frozen": True}

    # Primary fields
    id: str = Field(..., description="Unique identifier (UUID format)")

    content: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CONTENT_LENGTH,
        description="Insight content (educational pattern or best practice)",
    )

    # Classification metadata
    topics: list[str] = Field(
        default_factory=list,
        max_length=MAX_TOPICS,
        description="Topic tags for categorization",
    )

    projects: list[str] = Field(
        default_factory=list,
        max_length=MAX_PROJECTS,
        description="Associated project names",
    )

    # Quality metrics
    quality_score: float = Field(
        default=0.5,
        ge=MIN_QUALITY,
        le=MAX_QUALITY,
        description="Quality score (0.0 to 1.0)",
    )

    confidence_score: float = Field(
        default=0.5,
        ge=MIN_QUALITY,
        le=MAX_QUALITY,
        description="Confidence in extraction accuracy (0.0 to 1.0)",
    )

    usage_count: int = Field(
        default=0, ge=0, description="Number of times this insight has been retrieved"
    )

    last_used_at: datetime | None = Field(
        default=None, description="Last timestamp when this insight was used"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )

    # Source tracking
    source_conversation_id: str | None = Field(
        default=None, description="ID of conversation that generated this insight"
    )

    source_reflection_id: str | None = Field(
        default=None, description="ID of reflection that generated this insight"
    )

    # Insight type for categorization
    insight_type: str = Field(
        default="general",
        description="Type of insight (general, pattern, architecture, etc.)",
    )

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        """Validate content is not just whitespace."""
        if not v.strip():
            msg = "Content cannot be empty or whitespace"
            raise ValueError(msg)
        return v

    @field_validator("last_used_at")
    @classmethod
    def last_used_not_future(cls, v: datetime | None) -> datetime | None:
        """Validate last_used_at is not in the future."""
        if v is not None and v > datetime.now(UTC):
            msg = "last_used_at cannot be in the future"
            raise ValueError(msg)
        return v

    @field_validator("id")
    @classmethod
    def valid_uuid_format(cls, v: str) -> str:
        """Validate ID is a valid UUID format."""
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        if not uuid_pattern.match(v):
            msg = f"id '{v}' is not a valid UUID format"
            raise ValueError(msg)
        return v

    @field_validator("insight_type")
    @classmethod
    def insight_type_safe_characters(cls, v: str) -> str:
        """Validate insight_type contains only safe characters."""
        if not SAFE_COLLECTION_NAME_PATTERN.match(v):
            msg = (
                f"insight_type '{v}' contains invalid characters. "
                f"Only alphanumeric and underscore allowed."
            )
            raise ValueError(msg)
        return v

    # Serialization is automatic with Pydantic:
    # - model_dump() replaces to_dict()
    # - model_validate() replaces from_dict()


def validate_collection_name(collection_name: str) -> str:
    """
    Validate collection name to prevent SQL injection.

    Collection names are used directly in SQL table names, so they must be
    strictly validated to prevent injection attacks.

    Args:
        collection_name: Collection name to validate

    Returns:
        Validated collection name

    Raises:
        ValueError: If collection name contains invalid characters

    Example:
        ```python
        validate_collection_name("default")  # Returns "default"
        validate_collection_name(
            "malicious); DROP TABLE users; --"
        )  # Raises ValueError
        ```

    """
    if not collection_name:
        msg = "Collection name cannot be empty"
        raise ValueError(msg)

    if not SAFE_COLLECTION_NAME_PATTERN.match(collection_name):
        msg = (
            f"Collection name '{collection_name}' contains invalid characters. "
            f"Only alphanumeric and underscore allowed."
        )
        raise ValueError(msg)

    # Prevent SQL injection keywords
    sql_keywords = {
        "DROP",
        "DELETE",
        "INSERT",
        "UPDATE",
        "SELECT",
        "UNION",
        "JOIN",
        "WHERE",
        "EXEC",
        "EXECUTE",
    }
    upper_name = collection_name.upper()
    for keyword in sql_keywords:
        if keyword in upper_name:
            msg = (
                f"Collection name '{collection_name}' contains SQL keyword '{keyword}'"
            )
            raise ValueError(msg)

    return collection_name


def sanitize_project_name(
    project_name: str, sensitive_keywords: set[str] | None = None
) -> str:
    """
    Sanitize project name to prevent information disclosure.

    Project names can leak sensitive information about filesystem structure.
    This function hashes project names that match sensitive patterns.

    Args:
        project_name: Raw project name from Path.cwd().name
        sensitive_keywords: Set of keywords that trigger hashing (default: common sensitive terms)

    Returns:
        Safe project identifier (original or hashed)

    Example:
        ```python
        sanitize_project_name("my-project")  # Returns "my-project"
        sanitize_project_name("secret-acquisition-target")  # Returns "a1b2c3d4e5f6"
        ```

    """
    if sensitive_keywords is None:
        sensitive_keywords = {
            "secret",
            "private",
            "confidential",
            "internal",
            "acquisition",
            "merger",
            "takeover",
            "buyout",
            "password",
            "credential",
            "auth",
            "token",
            "backdoor",
            "exploit",
            "vulnerability",
        }

    # Check if project name contains sensitive keywords
    lower_name = project_name.lower()
    for keyword in sensitive_keywords:
        if keyword in lower_name:
            # Hash the sensitive name
            hash_obj = hashlib.sha256(project_name.encode())
            return hash_obj.hexdigest()[:12]

    # Validate safe characters
    if not SAFE_PROJECT_NAME_PATTERN.match(project_name):
        # Hash if contains special characters
        hash_obj = hashlib.sha256(project_name.encode())
        return hash_obj.hexdigest()[:12]

    return project_name
