"""Unit tests for core.ulid_generator module."""

from __future__ import annotations

import sys
import time
import types

import pytest

from session_buddy.core.ulid_generator import generate_ulid, is_valid_ulid


class TestGenerateULID:
    """Tests for generate_ulid() function."""

    def test_returns_string(self):
        result = generate_ulid()
        assert isinstance(result, str)

    def test_returns_26_characters(self):
        result = generate_ulid()
        assert len(result) == 26

    def test_returns_lowercase(self):
        result = generate_ulid()
        # ULID uses lowercase Crockford Base32
        assert result == result.lower()

    def test_returns_unique_per_call(self):
        """Test that successive calls return different ULIDs."""
        results = set()
        for _ in range(100):
            ulid = generate_ulid()
            assert ulid not in results
            results.add(ulid)

    def test_returns_deterministic_length(self):
        """Test that all generated ULIDs have the same length."""
        for _ in range(50):
            ulid = generate_ulid()
            assert len(ulid) == 26

    def test_uses_crockford_base32_alphabet(self):
        """Test that generated ULID only contains valid Crockford Base32 chars."""
        alphabet = "0123456789abcdefghjkmnpqrstvwxyz"
        result = generate_ulid()
        for char in result:
            assert char in alphabet, f"Invalid character: {char}"

    def test_consecutive_calls_produce_different_results(self):
        """Test that consecutive calls don't return the same value."""
        results = []
        for _ in range(10):
            results.append(generate_ulid())

        # All should be unique
        assert len(set(results)) == len(results)


class TestIsValidULID:
    """Tests for is_valid_ulid() function."""

    @pytest.mark.parametrize(
        "valid_ulid",
        [
            "01arz3ndektsv4rrffq69g5fav",  # Standard valid ULID (lowercase)
            "00000000000000000000000000",  # All zeros
            "zzzzzzzzzzzzzzzzzzzzzzzzzz",  # All z's (max Crockford Base32)
            "01arz3ndektsv4rrffq69g5fav",  # Another valid 26-char lowercase ULID
        ],
    )
    def test_valid_ulids_return_true(self, valid_ulid):
        result = is_valid_ulid(valid_ulid)
        assert result is True

    @pytest.mark.parametrize(
        "invalid_ulid",
        [
            "01ARZ3NDEKTSV4RRFFQ69G5FA",  # Too short (25 chars)
            "01ARZ3NDEKTSV4RRFFQ69G5FAVU",  # Too long (27 chars)
            "01ARZ3NDEKTSV4RRFFQ69G5FAVO",  # Contains 'O' (not in Crockford)
            "01ARZ3NDEKTSV4RRFFQ69G5FAI",  # Contains 'I' (not in Crockford)
            "01ARZ3NDEKTSV4RRFFQ69G5FAl",  # Contains 'l' (not in Crockford)
            "01ARZ3NDEKTSV4RRFFQ69G5FA0",  # Contains 'O' (not in Crockford)
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ",  # All uppercase (invalid)
            "01ARZ3NDEKTSV4RRFFQ69G5FA!",  # Contains special char
            "01ARZ3NDEKTSV4RRFFQ69G5FA ",  # Contains space
            "",  # Empty string
            "abc",  # Too short
        ],
    )
    def test_invalid_ulids_return_false(self, invalid_ulid):
        result = is_valid_ulid(invalid_ulid)
        assert result is False

    def test_exactly_26_characters_required(self):
        """Test that length must be exactly 26."""
        # 25 chars - invalid
        assert is_valid_ulid("01ARZ3NDEKTSV4RRFFQ69G5FA") is False
        # 27 chars - invalid
        assert is_valid_ulid("01ARZ3NDEKTSV4RRFFQ69G5FAVU") is False

    def test_crockford_base32_excludes_uppercase(self):
        """Test that uppercase letters are invalid (Crockford Base32 lowercase only)."""
        # All lowercase string - should be valid
        valid_lower = "01arz3ndektsv4rrffq69g5fav"
        assert is_valid_ulid(valid_lower) is True

        # Same string with uppercase - should be invalid
        invalid_upper = valid_lower.upper()
        assert is_valid_ulid(invalid_upper) is False

    def test_crockford_base32_excludes_similar_chars(self):
        """Test that Crockford Base32 excludes I, O, l, u."""
        # These are the characters excluded by Crockford Base32
        excluded_chars = "iouIOL"

        # A valid ULID with each excluded char replaced in sequence
        for char in excluded_chars:
            invalid_ulid = "01ARZ3NDEKTSV4RRFFQ69G5FA"  # 25 chars
            invalid_ulid = invalid_ulid[:10] + char + invalid_ulid[11:]
            assert is_valid_ulid(invalid_ulid) is False

    def test_empty_string_returns_false(self):
        assert is_valid_ulid("") is False

    def test_whitespace_returns_false(self):
        assert is_valid_ulid(" ") is False
        assert is_valid_ulid("  ") is False
        assert is_valid_ulid("01ARZ3NDEKTSV4RRFFQ69G5FA ") is False
        assert is_valid_ulid(" 01ARZ3NDEKTSV4RRFFQ69G5FA") is False


class TestULIDRoundtrip:
    """Tests for ULID validation of generated values."""

    def test_generated_ulid_is_valid(self):
        """Test that any generated ULID passes validation."""
        for _ in range(100):
            ulid = generate_ulid()
            assert is_valid_ulid(ulid) is True

    def test_consistency_multiple_validations(self):
        """Test that validating the same ULID multiple times is consistent."""
        ulid = generate_ulid()
        for _ in range(10):
            assert is_valid_ulid(ulid) is True


class TestULIDUniqueness:
    """Tests for ULID uniqueness guarantees."""

    def test_mass_generation_all_unique(self):
        """Test that generating many ULIDs produces all unique values."""
        ulids = set()
        for _ in range(1000):
            ulid = generate_ulid()
            assert ulid not in ulids
            ulids.add(ulid)
        assert len(ulids) == 1000

    def test_no_collisions_in_1000_generations(self):
        """Test no collisions in large batch generation."""
        ulids = [generate_ulid() for _ in range(1000)]
        assert len(set(ulids)) == 1000


class TestULIDFormat:
    """Tests for ULID format compliance."""

    def test_no_uppercase(self):
        """Test that generated ULIDs contain no uppercase letters."""
        for _ in range(50):
            ulid = generate_ulid()
            assert ulid == ulid.lower()
            assert ulid.upper() != ulid  # At least some uppercase would fail

    def test_no_special_characters(self):
        """Test that generated ULIDs contain only Base32 characters."""
        for _ in range(50):
            ulid = generate_ulid()
            for char in ulid:
                assert char.isalnum() or char in "abcdefghjkmnpqrstvwxyz"

    def test_starts_with_alphanumeric(self):
        """Test that ULIDs start with alphanumeric characters."""
        for _ in range(50):
            ulid = generate_ulid()
            assert ulid[0].isalnum()


class TestGenerateULIDWithDruva:
    """Tests for generate_ulid() with druva module available."""

    def test_uses_druva_when_available(self, monkeypatch) -> None:
        """Test that druva is used when available."""
        fake_druva = types.ModuleType("druva")
        fake_druva.generate = lambda: "druva-generated-ulid-000000"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "druva", fake_druva)

        from session_buddy.core import ulid_generator
        result = ulid_generator.generate_ulid()
        assert result == "druva-generated-ulid-000000"


class TestGenerateULIDFallback:
    """Tests for generate_ulid() fallback implementation (no druva)."""

    def test_fallback_returns_26_characters(self, monkeypatch) -> None:
        """Test fallback returns correct length."""
        monkeypatch.delitem(sys.modules, "druva", raising=False)
        from session_buddy.core import ulid_generator

        result = ulid_generator.generate_ulid()
        assert len(result) == 26

    def test_fallback_is_valid_ulid(self, monkeypatch) -> None:
        """Test fallback produces valid ULID."""
        monkeypatch.delitem(sys.modules, "druva", raising=False)
        from session_buddy.core import ulid_generator

        result = ulid_generator.generate_ulid()
        assert ulid_generator.is_valid_ulid(result) is True

    def test_fallback_uses_timestamp_bytes(self, monkeypatch) -> None:
        """Test fallback uses timestamp in first 10 chars."""
        monkeypatch.delitem(sys.modules, "druva", raising=False)
        from session_buddy.core import ulid_generator

        # Patch time to be deterministic
        monkeypatch.setattr(ulid_generator.time, "time", lambda: 1_700_000_000.123)
        monkeypatch.setattr(ulid_generator.os, "urandom", lambda n: b"\x01" * n)

        result = ulid_generator.generate_ulid()

        assert len(result) == 26
        assert ulid_generator.is_valid_ulid(result) is True

    def test_fallback_different_timestamps_different_ulids(self, monkeypatch) -> None:
        """Test that different timestamps produce different ULIDs."""
        from session_buddy.core import ulid_generator

        # First ULID
        ulid1 = ulid_generator.generate_ulid()

        # Change time
        monkeypatch.setattr(ulid_generator.time, "time", lambda: ulid1[:10].encode()[0] / 1_000_000 + 1)
        ulid2 = ulid_generator.generate_ulid()

        # They should be different
        assert ulid1 != ulid2

    def test_fallback_randomness_changes_each_call(self, monkeypatch) -> None:
        """Test that randomness portion changes even with same timestamp."""
        from session_buddy.core import ulid_generator

        # Use a fixed timestamp but varying randomness
        counter = [0]
        original_urandom = ulid_generator.os.urandom

        def fake_urandom(n):
            counter[0] += 1
            return bytes([counter[0]] * n)

        monkeypatch.setattr(ulid_generator.os, "urandom", fake_urandom)
        monkeypatch.setattr(ulid_generator.time, "time", lambda: 1_700_000_000.0)

        ulid1 = ulid_generator.generate_ulid()
        ulid2 = ulid_generator.generate_ulid()

        # Should be different due to different randomness
        assert ulid1 != ulid2


class TestIsValidULIDEdgeCases:
    """Edge case tests for is_valid_ulid()."""

    def test_single_character_returns_false(self):
        assert is_valid_ulid("a") is False

    def test_25_characters_returns_false(self):
        assert is_valid_ulid("a" * 25) is False

    def test_27_characters_returns_false(self):
        assert is_valid_ulid("a" * 27) is False

    def test_all_crockford_chars_valid(self):
        """Test all characters in Crockford Base32 alphabet are valid."""
        valid_chars = "0123456789abcdefghjkmnpqrstvwxyz"
        for char in valid_chars:
            ulid = "0" * 25 + char
            assert is_valid_ulid(ulid) is True, f"Character '{char}' should be valid"

    def test_boundary_values(self):
        """Test boundary values for ULID."""
        # All zeros
        assert is_valid_ulid("0" * 26) is True
        # Another valid 26-char lowercase string
        assert is_valid_ulid("01arz3ndektsv4rrffq69g5fav") is True
        # Too short (9 chars)
        assert is_valid_ulid("rstvwxyz0") is False
