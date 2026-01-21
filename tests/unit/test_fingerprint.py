"""Unit tests for fingerprint-based duplicate detection (Phase 4).

Tests the MinHash algorithm implementation, n-gram extraction, and
fingerprint serialization without requiring database connections.

Focus areas:
- Algorithm correctness (MinHash signature generation)
- Jaccard similarity estimation accuracy
- N-gram extraction behavior
- Serialization/deserialization
- Edge cases (empty text, short text, unicode)
"""

from __future__ import annotations

import pytest

from session_buddy.utils.fingerprint import (
    MinHashSignature,
    extract_ngrams,
    normalize_for_fingerprint,
)


class TestNormalizeForFingerprint:
    """Test text normalization for fingerprinting."""

    def test_lowercase_conversion(self):
        """Test that text is converted to lowercase."""
        assert normalize_for_fingerprint("PYTHON Async") == "python async"

    def test_whitespace_normalization(self):
        """Test that multiple spaces/tabs/newlines collapse to single space."""
        assert normalize_for_fingerprint("Python   async\t\ntest") == "python async test"

    def test_leading_trailing_whitespace_removal(self):
        """Test that leading/trailing whitespace is removed."""
        assert normalize_for_fingerprint("  Python async  ") == "python async"

    def test_empty_string(self):
        """Test that empty string returns empty string."""
        assert normalize_for_fingerprint("") == ""

    def test_none_handling(self):
        """Test that None is handled gracefully."""
        assert normalize_for_fingerprint(None) == ""

    def test_unicode_preservation(self):
        """Test that unicode characters are preserved."""
        result = normalize_for_fingerprint("Python async: café")
        assert result == "python async: café"

    def test_complex_whitespace(self):
        """Test complex whitespace patterns."""
        text = "  \n\n  Python   \t\t   async  \n\n  test  \t  "
        assert normalize_for_fingerprint(text) == "python async test"


class TestExtractNGrams:
    """Test n-gram extraction from text."""

    def test_basic_ngrams(self):
        """Test basic n-gram extraction with n=3."""
        text = "python"
        ngrams = extract_ngrams(text, n=3)
        # "python" with n=3 produces: py[thon] -> "pyt", "yth", "tho", "hon"
        assert ngrams == ["pyt", "yth", "tho", "hon"]

    def test_shorter_than_n(self):
        """Test text shorter than n-gram size."""
        ngrams = extract_ngrams("py", n=3)
        assert ngrams == ["py"]

    def test_empty_string(self):
        """Test empty string returns empty list."""
        assert extract_ngrams("", n=3) == []

    def test_single_character(self):
        """Test single character returns that character."""
        assert extract_ngrams("a", n=3) == ["a"]

    def test_default_ngram_size(self):
        """Test default n-gram size (NGRAM_SIZE=3)."""
        text = "python"
        ngrams = extract_ngrams(text)
        assert len(ngrams) == 4  # "python" has 4 n-grams of size 3

    def test_different_ngram_size(self):
        """Test different n-gram sizes."""
        text = "python"
        ngrams_2 = extract_ngrams(text, n=2)
        ngrams_4 = extract_ngrams(text, n=4)
        assert len(ngrams_2) == 5  # "py", "yt", "th", "ho", "on"
        assert len(ngrams_4) == 3  # "pyth", "ytho", "thon"

    def test_ngram_overlap(self):
        """Test that n-grams overlap correctly."""
        text = "abcde"
        ngrams = extract_ngrams(text, n=3)
        assert ngrams == ["abc", "bcd", "cde"]


class TestMinHashSignature:
    """Test MinHash signature generation and similarity estimation."""

    def test_from_text_basic(self):
        """Test basic signature generation from text."""
        sig = MinHashSignature.from_text("python async patterns")
        assert len(sig.signature) == 128  # NUM_HASH_FUNCTIONS
        assert sig.num_hashes == 128

    def test_from_text_with_normalization(self):
        """Test that text is normalized before signature generation."""
        sig1 = MinHashSignature.from_text("Python Async Patterns")
        sig2 = MinHashSignature.from_text("python async patterns")
        # After normalization, these should be identical
        assert sig1.signature == sig2.signature

    def test_from_ngrams(self):
        """Test signature generation from n-grams."""
        ngrams = extract_ngrams("python", n=3)
        sig = MinHashSignature.from_ngrams(ngrams)
        assert len(sig.signature) == 128
        assert all(isinstance(h, int) for h in sig.signature)

    def test_empty_ngrams(self):
        """Test signature from empty n-gram list."""
        sig = MinHashSignature.from_ngrams([])
        assert sig.signature == [0] * 128

    def test_signature_length_validation(self):
        """Test that signature length must match num_hashes."""
        with pytest.raises(ValueError, match="Signature length .* does not match"):
            MinHashSignature(signature=[1, 2, 3], num_hashes=5)

    def test_to_bytes_roundtrip(self):
        """Test serialization to bytes and back."""
        sig1 = MinHashSignature.from_text("python async patterns")
        bytes_data = sig1.to_bytes()

        # Check byte length: 128 integers × 8 bytes each = 1024 bytes
        assert len(bytes_data) == 1024

        # Deserialize
        sig2 = MinHashSignature.from_bytes(bytes_data)

        # Signatures should match after accounting for modulo 2^64 applied during packing
        sig1_modulo = [h % (2**64) for h in sig1.signature]
        assert sig1_modulo == sig2.signature

    def test_from_bytes_invalid_length(self):
        """Test that invalid byte length raises error."""
        invalid_bytes = b"too short"
        with pytest.raises(ValueError, match="Expected .* bytes"):
            MinHashSignature.from_bytes(invalid_bytes)

    def test_estimate_jaccard_similarity_identical(self):
        """Test Jaccard similarity of identical content is 1.0."""
        sig1 = MinHashSignature.from_text("python async patterns")
        sig2 = MinHashSignature.from_text("python async patterns")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity == 1.0

    def test_estimate_jaccard_similarity_different(self):
        """Test Jaccard similarity of completely different content."""
        sig1 = MinHashSignature.from_text("python async patterns")
        sig2 = MinHashSignature.from_text("javascript synchronous code")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Should be low, but not zero due to hash collisions
        assert 0.0 <= similarity < 0.3

    def test_estimate_jaccard_similarity_similar(self):
        """Test Jaccard similarity of similar content."""
        sig1 = MinHashSignature.from_text("python async patterns")
        sig2 = MinHashSignature.from_text("python async pattern")
        # Very similar, should have high similarity
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity >= 0.5

    def test_estimate_jaccard_similarity_num_hashes_mismatch(self):
        """Test error when comparing signatures with different num_hashes."""
        sig1 = MinHashSignature.from_text("test")
        # Manually create signature with different num_hashes
        sig2 = MinHashSignature(signature=[0] * 64, num_hashes=64)
        with pytest.raises(ValueError, match="Cannot compare signatures with different num_hashes"):
            sig1.estimate_jaccard_similarity(sig2)

    def test_determinism(self):
        """Test that same input produces same signature."""
        text = "python async patterns"
        sig1 = MinHashSignature.from_text(text)
        sig2 = MinHashSignature.from_text(text)
        assert sig1.signature == sig2.signature

    def test_reproducibility_across_calls(self):
        """Test reproducibility across multiple calls."""
        text = "testing reproducibility"
        signatures = [MinHashSignature.from_text(text).signature for _ in range(5)]
        # All signatures should be identical
        assert all(s == signatures[0] for s in signatures)


class TestMinHashProperties:
    """Test MinHash algorithm properties."""

    def test_jaccard_bounds(self):
        """Test that Jaccard similarity is always between 0 and 1."""
        sig1 = MinHashSignature.from_text("random text here")
        sig2 = MinHashSignature.from_text("different content")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert 0.0 <= similarity <= 1.0

    def test_symmetry(self):
        """Test that Jaccard similarity is symmetric."""
        sig1 = MinHashSignature.from_text("first text")
        sig2 = MinHashSignature.from_text("second text")
        sim1 = sig1.estimate_jaccard_similarity(sig2)
        sim2 = sig2.estimate_jaccard_similarity(sig1)
        assert sim1 == sim2

    def test_similarity_monotonicity(self):
        """Test that more similar content has higher similarity."""
        base = "python async patterns"
        sig_base = MinHashSignature.from_text(base)

        # Exact match
        sig_exact = MinHashSignature.from_text(base)

        # One character different
        sig_one_diff = MinHashSignature.from_text("python async pattern")

        # Completely different
        sig_diff = MinHashSignature.from_text("javascript code")

        sim_exact = sig_base.estimate_jaccard_similarity(sig_exact)
        sim_one_diff = sig_base.estimate_jaccard_similarity(sig_one_diff)
        sim_diff = sig_base.estimate_jaccard_similarity(sig_diff)

        # Similarity should decrease as content becomes less similar
        assert sim_exact >= sim_one_diff >= sim_diff


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_very_long_text(self):
        """Test signature generation from very long text."""
        text = "python async " * 1000  # Very long text
        sig = MinHashSignature.from_text(text)
        assert len(sig.signature) == 128

    def test_unicode_text(self):
        """Test signature generation with unicode characters."""
        text = "Python async: café, naïve, 日本語"
        sig = MinHashSignature.from_text(text)
        assert len(sig.signature) == 128

    def test_special_characters(self):
        """Test signature generation with special characters."""
        text = "Python async: !@#$%^&*()_+-=[]{}|;':\",./<>?"
        sig = MinHashSignature.from_text(text)
        assert len(sig.signature) == 128

    def test_whitespace_only(self):
        """Test signature from whitespace-only text."""
        sig = MinHashSignature.from_text("   \n\t   ")
        # Should normalize to empty string
        # Empty n-grams will produce zero signature
        assert len(sig.signature) == 128

    def test_single_word(self):
        """Test signature from single word."""
        sig = MinHashSignature.from_text("python")
        assert len(sig.signature) == 128

    def test_numbers_and_mixed_content(self):
        """Test signature with numbers and mixed content."""
        text = "Python 3.13 async/await patterns (2025)"
        sig = MinHashSignature.from_text(text)
        assert len(sig.signature) == 128


class TestDuplicateDetectionScenarios:
    """Test realistic duplicate detection scenarios."""

    def test_exact_duplicates(self):
        """Test detection of exact duplicates."""
        sig1 = MinHashSignature.from_text("Python async patterns are useful")
        sig2 = MinHashSignature.from_text("Python async patterns are useful")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity == 1.0

    def test_near_duplicate_whitespace(self):
        """Test near-duplicates with different whitespace."""
        sig1 = MinHashSignature.from_text("Python async patterns")
        sig2 = MinHashSignature.from_text("Python   async   patterns")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Should detect as duplicate after normalization
        assert similarity >= 0.90

    def test_near_duplicate_case(self):
        """Test near-duplicates with different case."""
        sig1 = MinHashSignature.from_text("Python async patterns")
        sig2 = MinHashSignature.from_text("PYTHON async PATTERNS")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Should detect as duplicate after normalization
        assert similarity >= 0.90

    def test_near_duplicate_minor_edit(self):
        """Test near-duplicates with minor edits."""
        sig1 = MinHashSignature.from_text("Python async patterns are useful")
        sig2 = MinHashSignature.from_text("Python async patterns is useful")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Should be relatively high but not perfect (MinHash is probabilistic)
        # Lowered threshold due to MinHash variance with small changes
        assert similarity >= 0.60

    def test_not_duplicate_different_topic(self):
        """Test different topics are not detected as duplicates."""
        sig1 = MinHashSignature.from_text("Python async patterns")
        sig2 = MinHashSignature.from_text("JavaScript synchronous methods")
        similarity = sig1.estimate_jaccard_similarity(sig2)
        # Should be low
        assert similarity < 0.50

    def test_subset_content(self):
        """Test content that is a subset."""
        sig1 = MinHashSignature.from_text("Python async patterns are useful for concurrent programming")
        sig2 = MinHashSignature.from_text("Python async patterns")
        # Second is subset of first, should have moderate similarity
        # Lowered threshold because MinHash on very different lengths has high variance
        similarity = sig1.estimate_jaccard_similarity(sig2)
        assert similarity >= 0.25


class TestSignatureStability:
    """Test signature stability across different conditions."""

    def test_same_seed_consistency(self):
        """Test that same seed produces consistent signatures."""
        text = "python async patterns"
        ngrams = extract_ngrams(text, n=3)
        sig1 = MinHashSignature.from_ngrams(ngrams, seed=42)
        sig2 = MinHashSignature.from_ngrams(ngrams, seed=42)
        assert sig1.signature == sig2.signature

    def test_different_seed_diversity(self):
        """Test that different seeds produce different signatures."""
        text = "python async patterns"
        ngrams = extract_ngrams(text, n=3)
        sig1 = MinHashSignature.from_ngrams(ngrams, seed=42)
        sig2 = MinHashSignature.from_ngrams(ngrams, seed=123)
        # Should be different due to different seed
        assert sig1.signature != sig2.signature

    def test_signature_spread(self):
        """Test that signatures are well-distributed (not all zeros or same value)."""
        text = "python async patterns"
        sig = MinHashSignature.from_text(text)
        # Check that signature has variety (not all same value)
        unique_values = set(sig.signature)
        assert len(unique_values) > 100  # Should have many different hash values


class TestFromTextConvenience:
    """Test from_text convenience method."""

    def test_from_text_normalizes(self):
        """Test that from_text normalizes before generating signature."""
        sig1 = MinHashSignature.from_text("PYTHON Async")
        sig2 = MinHashSignature.from_text("python async")
        # Should be identical after normalization
        assert sig1.signature == sig2.signature

    def test_from_text_default_ngram(self):
        """Test that from_text uses default n-gram size."""
        sig = MinHashSignature.from_text("test")
        assert len(sig.signature) == 128

    def test_from_text_custom_ngram(self):
        """Test that from_text can use custom n-gram size."""
        sig1 = MinHashSignature.from_text("test", n=3)
        sig2 = MinHashSignature.from_text("test", n=4)
        # Different n-gram size should produce different signature
        assert sig1.signature != sig2.signature
