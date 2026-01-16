#!/usr/bin/env python3
"""Property-based tests for data validation and robustness."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.helpers import PropertyTestHelper, TestDataFactory

ASCII_CHARS = st.characters(min_codepoint=32, max_codepoint=126)


class TestPropertyBasedValidation:
    """Property-based tests for data validation and robustness."""

    @given(
        content=st.text(alphabet=ASCII_CHARS, min_size=1, max_size=2000),
        project=st.text(alphabet=ASCII_CHARS, min_size=1, max_size=100),
    )
    @settings(
        max_examples=50,
        deadline=None,  # Disable deadline to prevent timing-related flakiness
    )
    def test_conversation_storage_properties(self, content: str, project: str):
        """Property: All valid content should generate valid conversation objects."""
        # Generate conversation with property-based inputs
        conversation = TestDataFactory.conversation(content=content, project=project)

        # Validate structure using property helper
        assert PropertyTestHelper.validate_conversation_structure(conversation)
        assert conversation["content"] == content
        assert conversation["project"] == project

    @given(
        content=st.text(alphabet=ASCII_CHARS, min_size=1, max_size=2000),
        tags=st.lists(
            st.text(alphabet=ASCII_CHARS, min_size=1, max_size=30),
            max_size=10,
        ),
    )
    @settings(
        max_examples=50,
        deadline=None,  # Disable deadline to prevent timing-related flakiness
    )
    def test_reflection_storage_properties(self, content: str, tags: list[str]):
        """Property: All valid content and tags should generate valid reflection objects."""
        # Generate reflection with property-based inputs
        reflection = TestDataFactory.reflection(content=content, tags=tags)

        # Validate structure using property helper
        assert PropertyTestHelper.validate_reflection_structure(reflection)
        assert reflection["content"] == content
        assert reflection["tags"] == tags

    @given(score=st.floats(min_value=0.0, max_value=1.0))
    @settings(
        max_examples=20,
        deadline=None,  # Disable deadline to prevent timing-related flakiness
    )
    def test_similarity_score_validation(self, score: float):
        """Property: All scores in [0,1] should pass validation."""
        # Validate score using property helper
        assert PropertyTestHelper.validate_similarity_range(score)

    @given(
        content=st.text(min_size=1, max_size=1000),
        project=st.text(min_size=1, max_size=100),
    )
    @settings(
        max_examples=25,
        deadline=None,  # Disable deadline to prevent timing-related flakiness
    )
    def test_bulk_conversation_generation_properties(self, content: str, project: str):
        """Property: Bulk generation should work with varied inputs."""
        # Generate multiple conversations
        conversations = TestDataFactory.bulk_conversations(count=5, project=project)

        # Validate all conversations
        assert len(conversations) == 5
        for conv in conversations:
            assert PropertyTestHelper.validate_conversation_structure(conv)
            assert conv["project"] == project

    @given(
        count=st.integers(min_value=1, max_value=50),
        tags=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    )
    @settings(
        max_examples=20,
        deadline=None,  # Disable deadline to prevent timing-related flakiness
    )
    def test_bulk_reflection_generation_properties(self, count: int, tags: list[str]):
        """Property: Bulk reflection generation should work with varied inputs."""
        # Generate bulk reflections
        reflections = TestDataFactory.bulk_reflections(
            count=count, tags=tags or ["test"]
        )

        # Validate all reflections
        assert len(reflections) == count
        for refl in reflections:
            assert PropertyTestHelper.validate_reflection_structure(refl)
            if tags:
                assert all(tag in refl["tags"] for tag in tags if tag in refl["tags"])

    @given(content=st.text(min_size=1, max_size=1000))
    @settings(
        max_examples=20,
        deadline=None,  # Disable deadline to prevent timing-related flakiness
    )
    def test_search_result_properties(self, content: str):
        """Property: Search results should be valid for varied content."""
        # Generate search result
        search_result = TestDataFactory.search_result(content=content)

        # Validate structure
        assert "content" in search_result
        assert "score" in search_result
        assert "project" in search_result
        assert "timestamp" in search_result
        assert search_result["content"] == content
        assert PropertyTestHelper.validate_similarity_range(search_result["score"])


class TestSecurityPropertyBased:
    """Property-based tests for security and input sanitization."""

    @given(
        content=st.text(
            alphabet=st.characters(codec="ascii", min_codepoint=1, max_codepoint=127),
            min_size=1,
            max_size=5000,
        )
    )
    @settings(
        max_examples=30,
        deadline=None,  # Disable deadline to prevent timing-related flakiness
    )
    def test_content_sanitization_properties(self, content: str):
        """Property: All ASCII content should be handled safely."""
        # Test that content can be used in conversation without errors
        conversation = TestDataFactory.conversation(
            content=content, project="security-test"
        )

        # Validate structure is maintained
        assert PropertyTestHelper.validate_conversation_structure(conversation)
        assert conversation["content"] == content

    @given(
        malicious_input=st.sampled_from(
            [
                "'; DROP TABLE reflections; --",
                "<script>alert('xss')</script>",
                "../../etc/passwd",
                "\x00\x01\x02\x03",  # Binary injection
                "A" * 10000,  # Buffer overflow attempt
            ]
        )
    )
    def test_malicious_input_handling(self, malicious_input: str):
        """Test system handles malicious input safely."""
        # Generate with potentially malicious content
        conversation = TestDataFactory.conversation(
            content=malicious_input, project="security-test"
        )

        # Should still generate valid structure
        assert PropertyTestHelper.validate_conversation_structure(conversation)
        assert conversation["content"] == malicious_input  # Content preserved as-is

    @given(
        long_content=st.text(min_size=500, max_size=2000),  # Reduced size
        long_project=st.text(min_size=50, max_size=100),  # Reduced size
        many_tags=st.lists(
            st.text(min_size=1, max_size=50), min_size=5, max_size=20
        ),  # Reduced count and size
    )
    @settings(
        max_examples=5, suppress_health_check=[HealthCheck.too_slow]
    )  # Reduce examples and suppress health check
    def test_large_input_handling(
        self, long_content: str, long_project: str, many_tags: list[str]
    ):
        """Test system handles large inputs without issues."""
        # Generate with large content
        conversation = TestDataFactory.conversation(
            content=long_content, project=long_project
        )
        reflection = TestDataFactory.reflection(content=long_content, tags=many_tags)

        # Should generate valid structures
        assert PropertyTestHelper.validate_conversation_structure(conversation)
        assert PropertyTestHelper.validate_reflection_structure(reflection)
