"""
Security tests for Insights system.

Tests all critical security vulnerabilities identified in code review:
1. SQL injection - Collection name validation
2. Regex DoS - Bounded patterns with length limits
3. Information disclosure - Project name sanitization
4. Input validation - Content length, type validation
5. Data integrity - Immutable structures
"""

import re
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from session_buddy.insights.models import (
    MAX_CONTENT_LENGTH,
    MAX_PROJECTS,
    MAX_TOPICS,
    Insight,
    sanitize_project_name,
    validate_collection_name,
)


class TestSQLInjectionProtection:
    """Test collection name validation prevents SQL injection."""

    def test_valid_collection_names(self):
        """Valid collection names should pass validation."""
        valid_names = [
            "default",
            "my_collection",
            "Collection123",
            "test_db_2025",
        ]
        for name in valid_names:
            result = validate_collection_name(name)
            assert result == name

    def test_sql_injection_drop_table(self):
        """SQL injection attempt with DROP TABLE should be blocked."""
        malicious = "default); DROP TABLE users; --"
        # Character validation happens first, then keyword check
        with pytest.raises(ValueError, match=r"invalid characters|SQL keyword"):
            validate_collection_name(malicious)

    def test_sql_injection_union_select(self):
        """SQL injection attempt with UNION SELECT should be blocked."""
        malicious = "default' UNION SELECT * FROM users--"
        # Character validation happens first, then keyword check
        with pytest.raises(ValueError, match=r"invalid characters|SQL keyword"):
            validate_collection_name(malicious)

    def test_special_characters_rejected(self):
        """Special characters that could enable injection should be blocked."""
        invalid_names = [
            "collection; DROP TABLE",
            "collection' OR '1'='1",
            'collection" OR "1"="1',
            "collection--",
            "collection/*",
            "collection;",
            "collection xp_cmdshell",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError):
                validate_collection_name(name)

    def test_empty_collection_name_rejected(self):
        """Empty collection name should be rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_collection_name("")

    def test_sql_keywords_blocked(self):
        """All major SQL keywords should be blocked."""
        sql_keywords = [
            "DROP", "DELETE", "INSERT", "UPDATE", "SELECT",
            "UNION", "JOIN", "WHERE", "EXEC", "EXECUTE"
        ]
        for keyword in sql_keywords:
            malicious = f"collection_{keyword}"
            with pytest.raises(ValueError, match="SQL keyword"):
                validate_collection_name(malicious)


class TestRegexDoSProtection:
    """Test bounded patterns prevent denial-of-service attacks."""

    def test_content_length_limit_enforced(self):
        """Content length should be enforced to prevent DoS."""
        # Create content exactly at limit
        valid_content = "x" * MAX_CONTENT_LENGTH
        insight = Insight(
            id="123e4567-e89b-12d3-a456-426614174000",
            content=valid_content,
        )
        assert len(insight.content) == MAX_CONTENT_LENGTH

    def test_content_too_long_rejected(self):
        """Content exceeding limit should be rejected."""
        too_long = "x" * (MAX_CONTENT_LENGTH + 1)
        with pytest.raises(ValidationError, match="at most 10000"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content=too_long,
            )

    def test_empty_content_rejected(self):
        """Empty content should be rejected."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="   ",
            )

    def test_topics_array_limit_enforced(self):
        """Topics array should have reasonable size limit."""
        # Create exactly at limit
        topics = [f"topic{i}" for i in range(MAX_TOPICS)]
        insight = Insight(
            id="123e4567-e89b-12d3-a456-426614174000",
            content="Valid content",
            topics=topics,
        )
        assert len(insight.topics) == MAX_TOPICS

    def test_too_many_topics_rejected(self):
        """Excessive topics array should be rejected."""
        too_many = [f"topic{i}" for i in range(MAX_TOPICS + 1)]
        with pytest.raises(ValidationError, match="at most 20"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Valid content",
                topics=too_many,
            )

    def test_projects_array_limit_enforced(self):
        """Projects array should have reasonable size limit."""
        # Create exactly at limit
        projects = [f"project{i}" for i in range(MAX_PROJECTS)]
        insight = Insight(
            id="123e4567-e89b-12d3-a456-426614174000",
            content="Valid content",
            projects=projects,
        )
        assert len(insight.projects) == MAX_PROJECTS

    def test_too_many_projects_rejected(self):
        """Excessive projects array should be rejected."""
        too_many = [f"project{i}" for i in range(MAX_PROJECTS + 1)]
        with pytest.raises(ValidationError, match="at most 50"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Valid content",
                projects=too_many,
            )


class TestInformationDisclosureProtection:
    """Test project name sanitization prevents information leakage."""

    def test_safe_project_name_unchanged(self):
        """Safe project names should pass through unchanged."""
        safe_names = [
            "my-project",
            "session_buddy",
            "FastMCP",
            "test_123",
        ]
        for name in safe_names:
            result = sanitize_project_name(name)
            assert result == name

    def test_sensitive_keywords_hashed(self):
        """Project names with sensitive keywords should be hashed."""
        sensitive_names = [
            "secret-project",
            "private-repo",
            "acquisition-target",
            "password-manager",
            "backdoor-access",
        ]
        for name in sensitive_names:
            result = sanitize_project_name(name)
            # Should be hashed (12 character hex string)
            assert len(result) == 12
            assert re.match(r"^[0-9a-f]+$", result)
            # Should not contain original name
            assert name.split("-")[0] not in result

    def test_custom_sensitive_keywords(self):
        """Custom sensitive keyword set should be respected."""
        custom_keywords = {"confidential", "internal"}
        result = sanitize_project_name(
            "confidential-data",
            sensitive_keywords=custom_keywords
        )
        assert len(result) == 12  # Hashed
        assert re.match(r"^[0-9a-f]+$", result)

    def test_special_characters_hashed(self):
        """Project names with special characters should be hashed."""
        special_names = [
            "project/with/slashes",
            "project\\with\\backslashes",
            "project with spaces",
            "project;with;semicolons",
        ]
        for name in special_names:
            result = sanitize_project_name(name)
            # Should be hashed
            assert len(result) == 12
            assert re.match(r"^[0-9a-f]+$", result)

    def test_hash_deterministic(self):
        """Hashing should be deterministic for same input."""
        name = "secret-project"
        hash1 = sanitize_project_name(name)
        hash2 = sanitize_project_name(name)
        assert hash1 == hash2


class TestInputValidation:
    """Test comprehensive input validation."""

    def test_quality_score_bounds(self):
        """Quality score must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Test",
                quality_score=1.5,
            )

        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Test",
                quality_score=-0.1,
            )

    def test_confidence_score_bounds(self):
        """Confidence score must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Test",
                confidence_score=2.0,
            )

    def test_usage_count_cannot_be_negative(self):
        """Usage count must be non-negative."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Test",
                usage_count=-1,
            )

    def test_last_used_at_cannot_be_future(self):
        """Last used timestamp cannot be in the future."""
        future_time = datetime.now(UTC).replace(year=2099)
        with pytest.raises(ValidationError, match="cannot be in the future"):
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Test",
                last_used_at=future_time,
            )

    def test_invalid_uuid_format_rejected(self):
        """Invalid UUID format should be rejected."""
        invalid_uuids = [
            "not-a-uuid",
            "123456789",
            "g23e4567-e89b-12d3-a456-426614174000",  # Invalid hex char
            "",
        ]
        for invalid_id in invalid_uuids:
            with pytest.raises(ValidationError, match="not a valid UUID"):
                Insight(
                    id=invalid_id,
                    content="Test",
                )

    def test_valid_uuid_accepted(self):
        """Valid UUID formats should be accepted."""
        valid_uuids = [
            "123e4567-e89b-12d3-a456-426614174000",
            "123E4567-E89B-12D3-A456-426614174000",  # Uppercase
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
        ]
        for valid_id in valid_uuids:
            # Should not raise
            Insight(
                id=valid_id,
                content="Test",
            )


class TestDataIntegrity:
    """Test data integrity and immutability."""

    def test_insight_is_frozen(self):
        """Insight Pydantic model should be frozen (immutable)."""
        insight = Insight(
            id="123e4567-e89b-12d3-a456-426614174000",
            content="Test content",
        )
        # Attempting to modify should raise ValidationError
        with pytest.raises(ValidationError):
            insight.content = "modified content"

    def test_model_dump_roundtrip(self):
        """Converting Insight to dict and back should preserve data."""
        original = Insight(
            id="123e4567-e89b-12d3-a456-426614174000",
            content="Test content with insight",
            topics=["async", "database"],
            projects=["session-buddy"],
            quality_score=0.8,
            confidence_score=0.7,
            usage_count=5,
            insight_type="pattern",
        )

        # Convert to dict (Pydantic's model_dump)
        data = original.model_dump()

        # Convert back to Insight (Pydantic's model_validate)
        restored = Insight.model_validate(data)

        # Verify all fields match
        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.topics == original.topics
        assert restored.projects == original.projects
        assert restored.quality_score == original.quality_score
        assert restored.confidence_score == original.confidence_score
        assert restored.usage_count == original.usage_count
        assert restored.insight_type == original.insight_type

    def test_model_validate_type_coercion(self):
        """model_validate should handle type coercion automatically."""
        data = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "content": "Test",
            "topics": ["async", "database"],  # List
            "projects": ["session-buddy"],
            "quality_score": "0.8",  # String coerced to float
            "usage_count": "5",  # String coerced to int
        }

        insight = Insight.model_validate(data)

        # Should coerce to proper types automatically
        assert isinstance(insight.topics, list)
        assert isinstance(insight.projects, list)
        assert isinstance(insight.quality_score, float)
        assert isinstance(insight.usage_count, int)


class TestInsightTypeValidation:
    """Test insight type field validation."""

    def test_valid_insight_types(self):
        """Valid insight types should be accepted."""
        valid_types = [
            "general",
            "pattern",
            "architecture",
            "best_practice",
            "gotcha",
        ]
        for insight_type in valid_types:
            Insight(
                id="123e4567-e89b-12d3-a456-426614174000",
                content="Test",
                insight_type=insight_type,
            )

    def test_invalid_insight_type_rejected(self):
        """Invalid insight types should be rejected."""
        invalid_types = [
            "type-with-dash",
            "type with spaces",
            "type;semicolon",
            "type'quote",
            'type"doublequote',
        ]
        for invalid_type in invalid_types:
            with pytest.raises(ValidationError, match="invalid characters"):
                Insight(
                    id="123e4567-e89b-12d3-a456-426614174000",
                    content="Test",
                    insight_type=invalid_type,
                )
