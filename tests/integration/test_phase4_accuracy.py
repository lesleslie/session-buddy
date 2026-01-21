"""Simplified integration tests for Phase 4 fingerprinting accuracy.

These tests verify the MinHash algorithm meets Phase 4 success criteria:
- >90% exact duplicate detection
- >70% near-duplicate detection
- <1% false positive rate

Tests use direct fingerprint operations without database complexity.
"""

import pytest

from session_buddy.utils.fingerprint import MinHashSignature, extract_ngrams


class TestPhase4ExactDuplicateDetection:
    """Test exact duplicate detection meets >90% threshold."""

    def test_exact_identical_content(self):
        """Test that identical content has 100% similarity."""
        content = "Python async patterns improve code performance"
        sig1 = MinHashSignature.from_text(content)
        sig2 = MinHashSignature.from_text(content)

        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity == 1.0, "Exact duplicates should have 100% similarity"

    def test_exact_duplicates_with_normalization(self):
        """Test exact duplicates after normalization."""
        sig1 = MinHashSignature.from_text("Python Async Patterns")
        sig2 = MinHashSignature.from_text("python async patterns")

        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity == 1.0, "Normalized exact duplicates should match"

    def test_exact_duplicate_batch(self):
        """Test exact duplicate detection across multiple samples.

        Success criterion: >90% exact duplicate detection rate.
        """
        test_cases = [
            "Python async patterns make code faster",
            "FastAPI simplifies REST API development",
            "DuckDB provides fast analytical queries",
            "JavaScript promises handle asynchronous operations",
            "MinHash algorithm detects content similarity",
            "PostgreSQL offers robust relational databases",
            "Redis provides high-speed caching solutions",
            "GraphQL enables flexible data querying",
            "Docker containers simplify deployment",
            "Kubernetes orchestrates containerized applications",
        ]

        exact_matches = 0
        total = len(test_cases)

        for content in test_cases:
            sig1 = MinHashSignature.from_text(content)
            sig2 = MinHashSignature.from_text(content)
            similarity = sig1.estimate_jaccard_similarity(sig2)

            if similarity == 1.0:
                exact_matches += 1

        detection_rate = (exact_matches / total) * 100
        assert (
            detection_rate >= 90.0
        ), f"Exact duplicate detection rate {detection_rate:.1f}% is below 90% threshold"


class TestPhase4NearDuplicateDetection:
    """Test near-duplicate detection meets >70% threshold."""

    def test_near_duplicate_minor_edit(self):
        """Test near-duplicate with one word change."""
        original = "Python async patterns are useful for developers"
        variant = "Python async pattern is useful for developers"

        sig1 = MinHashSignature.from_text(original)
        sig2 = MinHashSignature.from_text(variant)

        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Should detect as near-duplicate (high similarity)
        assert similarity >= 0.60, f"Near-duplicate similarity {similarity:.2f} is too low"

    def test_near_duplicate_whitespace(self):
        """Test near-duplicate with different whitespace."""
        original = "Python async patterns"
        variant = "Python   async   patterns"  # Extra spaces

        sig1 = MinHashSignature.from_text(original)
        sig2 = MinHashSignature.from_text(variant)

        similarity = sig1.estimate_jaccard_similarity(sig2)
        # After normalization, should be exact match
        assert similarity >= 0.90, f"Whitespace near-duplicate similarity {similarity:.2f} is too low"

    def test_near_duplicate_case(self):
        """Test near-duplicate with case differences."""
        original = "Python Async Patterns"
        variant = "PYTHON async PATTERNS"

        sig1 = MinHashSignature.from_text(original)
        sig2 = MinHashSignature.from_text(variant)

        similarity = sig1.estimate_jaccard_similarity(sig2)
        # After normalization, should be exact match
        assert similarity >= 0.90, f"Case near-duplicate similarity {similarity:.2f} is too low"

    def test_near_duplicate_batch(self):
        """Test near-duplicate detection across multiple samples.

        Success criterion: >70% near-duplicate detection rate.
        Using threshold 0.60 for near-duplicates.
        """
        near_duplicate_pairs = [
            ("Python async patterns are useful", "Python async pattern is useful"),
            ("FastAPI is great for building APIs", "FastAPI is great for API building"),
            ("DuckDB provides fast analytics", "DuckDB provides fast analytical queries"),
            ("JavaScript promises help with async", "JavaScript promises help with asynchronous code"),
            ("MinHash detects similar content", "MinHash detects similar text content"),
            ("PostgreSQL offers robust databases", "PostgreSQL offers robust relational databases"),
            ("Redis provides high-speed caching", "Redis provides high speed cache solutions"),
            ("GraphQL enables flexible querying", "GraphQL enables flexible data query capabilities"),
            ("Docker simplifies application deployment", "Docker simplifies app deployment"),
            ("Kubernetes orchestrates containers", "Kubernetes orchestrates containerized apps"),
        ]

        detected_near_dups = 0
        total = len(near_duplicate_pairs)
        threshold = 0.60  # Near-duplicate threshold

        for original, variant in near_duplicate_pairs:
            sig1 = MinHashSignature.from_text(original)
            sig2 = MinHashSignature.from_text(variant)
            similarity = sig1.estimate_jaccard_similarity(sig2)

            if similarity >= threshold:
                detected_near_dups += 1

        detection_rate = (detected_near_dups / total) * 100
        assert (
            detection_rate >= 70.0
        ), f"Near-duplicate detection rate {detection_rate:.1f}% is below 70% threshold (using {threshold} threshold)"


class TestPhase4FalsePositiveRate:
    """Test false positive rate stays below <1% threshold."""

    def test_different_content_low_similarity(self):
        """Test that different content has low similarity."""
        content1 = "Python async patterns improve performance"
        content2 = "JavaScript promises handle asynchronous operations"

        sig1 = MinHashSignature.from_text(content1)
        sig2 = MinHashSignature.from_text(content2)

        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Should be low (not false positive)
        assert similarity < 0.50, f"Different content similarity {similarity:.2f} is too high (false positive)"

    def test_completely_different_topics(self):
        """Test completely different topics have very low similarity."""
        topics = [
            "Python async programming",
            " gardening and landscaping",
            " automotive repair techniques",
            " culinary arts and cooking",
            " quantum physics theories",
            " classical music composition",
            " marine biology research",
            " architecture and design",
            " financial investment strategies",
            " space exploration history",
        ]

        false_positives = 0
        threshold = 0.70  # Similarity threshold for considering something a "duplicate"
        total_comparisons = 0

        # Compare all pairs (avoiding self-comparison)
        for i in range(len(topics)):
            for j in range(i + 1, len(topics)):
                sig1 = MinHashSignature.from_text(topics[i])
                sig2 = MinHashSignature.from_text(topics[j])
                similarity = sig1.estimate_jaccard_similarity(sig2)

                total_comparisons += 1

                # If similarity exceeds threshold, it's a false positive
                # (these topics are completely different)
                if similarity >= threshold:
                    false_positives += 1

        # Calculate false positive rate
        false_positive_rate = (false_positives / total_comparisons) * 100

        assert (
            false_positive_rate < 1.0
        ), f"False positive rate {false_positive_rate:.2f}% exceeds 1% threshold ({false_positives}/{total_comparisons} comparisons)"

    def test_diverse_content_similarity_distribution(self):
        """Test that diverse content has appropriately distributed similarities."""
        diverse_content = [
            "Python async patterns",
            "JavaScript promises",
            "FastAPI framework",
            "DuckDB analytics",
            "Redis caching",
            "PostgreSQL databases",
            "GraphQL queries",
            "Docker containers",
            "Kubernetes orchestration",
            "MinHash algorithm",
        ]

        # Calculate pairwise similarities
        similarities = []
        for i in range(len(diverse_content)):
            for j in range(i + 1, len(diverse_content)):
                sig1 = MinHashSignature.from_text(diverse_content[i])
                sig2 = MinHashSignature.from_text(diverse_content[j])
                similarity = sig1.estimate_jaccard_similarity(sig2)
                similarities.append(similarity)

        # Most similarities should be low (for diverse content)
        avg_similarity = sum(similarities) / len(similarities)

        # Verify average similarity is low (indicating good discrimination)
        assert (
            avg_similarity < 0.40
        ), f"Average similarity {avg_similarity:.2f} for diverse content is too high (poor discrimination)"

        # Verify no similarities are extremely high (>0.80)
        high_similarities = [s for s in similarities if s >= 0.80]
        assert len(high_similarities) == 0, f"Found {len(high_similarities)} false positives with similarity >= 0.80"


class TestPhase4NgramExtraction:
    """Test n-gram extraction accuracy."""

    def test_ngram_extraction_basic(self):
        """Test basic n-gram extraction."""
        text = "python"
        ngrams = extract_ngrams(text, n=3)
        expected = ["pyt", "yth", "tho", "hon"]
        assert ngrams == expected, f"Expected {expected}, got {ngrams}"

    def test_ngram_extraction_short_text(self):
        """Test n-gram extraction with text shorter than n."""
        text = "py"
        ngrams = extract_ngrams(text, n=3)
        assert ngrams == ["py"], "Should return text as single n-gram when shorter than n"

    def test_ngram_extraction_empty(self):
        """Test n-gram extraction with empty text."""
        ngrams = extract_ngrams("", n=3)
        assert ngrams == [], "Should return empty list for empty text"


class TestPhase4SignatureProperties:
    """Test MinHash signature properties."""

    def test_signature_consistency(self):
        """Test that same input produces same signature."""
        text = "Python async patterns"
        sig1 = MinHashSignature.from_text(text)
        sig2 = MinHashSignature.from_text(text)

        assert sig1.signature == sig2.signature, "Same text should produce identical signature"

    def test_signature_length(self):
        """Test signature has correct length."""
        sig = MinHashSignature.from_text("test")
        assert len(sig.signature) == 128, "Signature should have 128 hash values"

    def test_serialization_roundtrip(self):
        """Test signature serialization/deserialization."""
        sig1 = MinHashSignature.from_text("test content")
        bytes_data = sig1.to_bytes()

        assert len(bytes_data) == 1024, "Serialized signature should be 1024 bytes"

        sig2 = MinHashSignature.from_bytes(bytes_data)

        # Account for modulo 2^64 applied during packing
        sig1_modulo = [h % (2**64) for h in sig1.signature]
        assert sig1_modulo == sig2.signature, "Roundtrip should preserve signature"

    def test_jaccard_bounds(self):
        """Test Jaccard similarity is always between 0 and 1."""
        sig1 = MinHashSignature.from_text("first text")
        sig2 = MinHashSignature.from_text("second text")

        similarity = sig1.estimate_jaccard_similarity(sig2)

        assert 0.0 <= similarity <= 1.0, f"Similarity {similarity} must be between 0 and 1"


class TestPhase4SuccessCriteria:
    """Comprehensive test of Phase 4 success criteria."""

    def test_all_success_criteria(self):
        """Test that Phase 4 meets all success criteria.

        Criteria:
        1. >90% exact duplicate detection
        2. >70% near-duplicate detection
        3. <1% false positive rate
        """
        # Criterion 1: Exact duplicates (>90%)
        exact_test_cases = [
            "Python async patterns improve code performance",
            "FastAPI simplifies REST API development",
            "DuckDB provides fast analytical queries",
        ]

        exact_matches = 0
        for content in exact_test_cases:
            sig1 = MinHashSignature.from_text(content)
            sig2 = MinHashSignature.from_text(content)
            if sig1.estimate_jaccard_similarity(sig2) == 1.0:
                exact_matches += 1

        exact_rate = (exact_matches / len(exact_test_cases)) * 100
        assert exact_rate >= 90.0, f"Exact duplicate rate {exact_rate:.1f}% < 90%"

        # Criterion 2: Near-duplicates (>70%)
        near_test_cases = [
            ("Python async patterns are useful", "Python async pattern is useful"),
            ("FastAPI is great for APIs", "FastAPI is great for API development"),
            ("DuckDB provides fast analytics", "DuckDB provides fast analytical queries"),
        ]

        near_matches = 0
        for original, variant in near_test_cases:
            sig1 = MinHashSignature.from_text(original)
            sig2 = MinHashSignature.from_text(variant)
            if sig1.estimate_jaccard_similarity(sig2) >= 0.60:
                near_matches += 1

        near_rate = (near_matches / len(near_test_cases)) * 100
        assert near_rate >= 70.0, f"Near-duplicate rate {near_rate:.1f}% < 70%"

        # Criterion 3: False positives (<1%)
        different_topics = [
            "Python async programming",
            "gardening and landscaping",
            "automotive repair techniques",
        ]

        false_positives = 0
        total_comparisons = 0
        for i in range(len(different_topics)):
            for j in range(i + 1, len(different_topics)):
                sig1 = MinHashSignature.from_text(different_topics[i])
                sig2 = MinHashSignature.from_text(different_topics[j])
                if sig1.estimate_jaccard_similarity(sig2) >= 0.70:
                    false_positives += 1
                total_comparisons += 1

        fp_rate = (false_positives / total_comparisons) * 100 if total_comparisons > 0 else 0
        assert fp_rate < 1.0, f"False positive rate {fp_rate:.1f}% >= 1%"

        print(f"\n✅ Phase 4 Success Criteria Met:")
        print(f"   Exact duplicate detection: {exact_rate:.1f}% (≥90%)")
        print(f"   Near-duplicate detection: {near_rate:.1f}% (≥70%)")
        print(f"   False positive rate: {fp_rate:.2f}% (<1%)")
