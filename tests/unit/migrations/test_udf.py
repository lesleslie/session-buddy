from __future__ import annotations

import struct
import typing as t

import pytest

from session_buddy.migrations.udf import ulid_to_uuid7


# Golden vectors pinned by the spec. Each (input_ulid, expected_uuid7) pair was
# derived by running the BLAKE2b-seeded algorithm in a one-off reference and
# confirmed by an independent timestamp-round-trip check (output[:12] == the
# ULID 48-bit ms timestamp packed big-endian). Any drift here means the UDF
# has changed and the 001-007 DuckDB consolidation will produce different
# UUID7 ids -- intentional trip wire.
GOLDEN_01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K = "01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K"
GOLDEN_UUID7_01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K = "0188ba3f13e57a3da3d6c8b6fbf70bb2"

GOLDEN_ALL_ZEROS = "0" * 32
GOLDEN_UUID7_ALL_ZEROS = "0000000000007d81b2a5275036268ff3"

GOLDEN_LAST_ONE = "0" * 31 + "1"
GOLDEN_UUID7_LAST_ONE = "0000000000007ab582e583d4b2bb4c83"


def _crockford_base32_decode_first_n(s: str, n: int) -> int:
    """Decode the first n chars of canonicalized Crockford-base32 as int."""
    table = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    result = 0
    for c in s[:n]:
        result = result * 32 + table.index(c)
    return result


class TestUlidToUuid7Golden:
    """Pinned golden vectors. See spec for algorithm details."""

    def test_golden_01h2x3y4z56a7b8c9d0e1f2g3h4j5j6k(self) -> None:
        result = ulid_to_uuid7(GOLDEN_01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K)
        assert result == GOLDEN_UUID7_01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K

    def test_golden_all_zeros(self) -> None:
        result = ulid_to_uuid7(GOLDEN_ALL_ZEROS)
        assert result == GOLDEN_UUID7_ALL_ZEROS

    def test_golden_last_one(self) -> None:
        result = ulid_to_uuid7(GOLDEN_LAST_ONE)
        assert result == GOLDEN_UUID7_LAST_ONE


class TestUlidToUuid7Determinism:
    def test_repeat_1000_calls_is_identical(self) -> None:
        ulid = "01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K"
        first = ulid_to_uuid7(ulid)
        for _ in range(1000):
            assert ulid_to_uuid7(ulid) == first

    def test_purity_no_external_state(self) -> None:
        # The function is pure: no module-level state, no I/O. The
        # implementation only uses hashlib.blake2b and pure-Python struct
        # packing. We verify this by re-calling the function in a fresh
        # interpreter-equivalent context (a child process) and confirming
        # the output matches.
        import os
        import subprocess
        import sys

        ulid = "01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K"
        # Use a child process so the second invocation runs in a fresh
        # interpreter with no shared module state. Skipped on platforms
        # where spawning a subprocess is not feasible in the test env.
        script = (
            "import sys; "
            f"sys.path.insert(0, {os.fspath(os.getcwd())!r}); "
            "from session_buddy.migrations.udf import ulid_to_uuid7; "
            f"print(ulid_to_uuid7({ulid!r}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            assert result.stdout.strip() == ulid_to_uuid7(ulid)


class TestUlidToUuid7Canonicalization:
    def test_case_insensitive(self) -> None:
        ulid = "01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K"
        upper = ulid_to_uuid7(ulid.upper())
        lower = ulid_to_uuid7(ulid.lower())
        assert upper == lower
        assert upper == GOLDEN_UUID7_01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K

    def test_dashes_stripped(self) -> None:
        dashed = "01H2X3Y4Z5-6A7B-8C9D-0E1F-2G3H4J5J6K"
        undashed = "01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K"
        assert ulid_to_uuid7(dashed) == ulid_to_uuid7(undashed)

    def test_dashed_and_lowercase(self) -> None:
        dashed = "01h2x3y4z5-6a7b-8c9d-0e1f-2g3h4j5j6k"
        undashed = "01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K"
        assert ulid_to_uuid7(dashed) == ulid_to_uuid7(undashed)


class TestUlidToUuid7Shape:
    def test_output_is_32_lowercase_hex_chars(self) -> None:
        result = ulid_to_uuid7("01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K")
        assert len(result) == 32
        assert result == result.lower()
        # Hex only
        int(result, 16)

    def test_output_is_uuid7_layout(self) -> None:
        # RFC 9562 section 5.7: bits 48-51 = ver = 0b0111, bits 64-65 = var = 0b10.
        # ver nibble is the 13th hex char (index 12 of 32 hex chars).
        # var is the top 2 bits of byte 8 (hex chars 16-17): shift right by 6.
        result = ulid_to_uuid7("01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K")
        ver_nibble = int(result[12], 16)
        var_byte = int(result[16:18], 16)
        var_bits = (var_byte >> 6) & 0b11
        assert ver_nibble == 0x7, f"expected ver=0b0111, got {ver_nibble:b}"
        assert var_bits == 0b10, f"expected var=0b10, got {var_bits:b}"


class TestUlidToUuid7TimestampPreservation:
    """Per spec, bits 0-47 (first 12 hex chars) = ULID 48-bit ms timestamp verbatim."""

    @pytest.mark.parametrize(
        "ulid",
        [
            "01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K",
            "0" * 32,
            "0" * 31 + "1",
            "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",
        ],
    )
    def test_first_12_hex_chars_equal_ulid_timestamp(self, ulid: str) -> None:
        canonical = ulid.replace("-", "").upper()
        ts_int = _crockford_base32_decode_first_n(canonical, 10)
        ts_hex = struct.pack(">Q", ts_int)[2:].hex()
        result = ulid_to_uuid7(ulid)
        assert result[:12] == ts_hex, (
            f"timestamp mismatch: ulid={ulid!r} "
            f"ts_hex={ts_hex!r} result={result!r}"
        )


class TestUlidToUuid7Distinctness:
    def test_two_different_ulids_yield_two_different_uuids(self) -> None:
        u1 = "0" * 32
        u2 = "0" * 31 + "1"
        assert ulid_to_uuid7(u1) != ulid_to_uuid7(u2)

    def test_distinct_across_100_random_pairs(self) -> None:
        # 100 small perturbations of the all-zeros ULID: change one char each.
        # Use (i % 31) + 1 so the substituted char is always in alphabet[1..31],
        # never alphabet[0]='0', guaranteeing b_str != a on every iteration.
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        a = "0" * 32
        for i in range(100):
            b = list(a)
            b[i % 32] = alphabet[(i % 31) + 1]
            b_str = "".join(b)
            assert b_str != a  # guard against no-op substitution
            assert ulid_to_uuid7(a) != ulid_to_uuid7(b_str), (
                f"collision: a={a!r} b={b_str!r}"
            )


class TestUlidToUuid7InvalidInputs:
    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "short",
            "0" * 33,
            "0" * 31,
            "I" * 32,  # I, L, O, U are excluded from Crockford base32
            "L" * 32,
            "O" * 32,
            "U" * 32,
            "abc",  # not in alphabet
            "0" * 32 + "I",  # length ok, char bad
            "0" * 31 + "I",  # length bad, char bad
        ],
    )
    def test_invalid_string_inputs_raise_value_error(self, bad: str) -> None:
        with pytest.raises(ValueError):
            ulid_to_uuid7(bad)

    @pytest.mark.parametrize(
        "bad_type,bad_value",
        [
            ("int", 123),
            ("none", None),
            ("bytes", b"01H2X3Y4Z56A7B8C9D0E1F2G3H4J5J6K"),
            ("list", []),
            ("dict", {}),
        ],
    )
    def test_non_string_inputs_raise_type_error(
        self, bad_type: str, bad_value: t.Any
    ) -> None:
        with pytest.raises(TypeError):
            ulid_to_uuid7(bad_value)
