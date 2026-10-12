from __future__ import annotations

import hashlib
import re
import struct

# Crockford base32 alphabet (RFC 9562 section 5.7 references this layout).
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{32}$")
_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _crockford_base32_decode(s: str) -> int:
    """Decode the first 10 chars of a canonicalized ULID as a base32 number.

    Returns the 48-bit big-endian ms timestamp embedded in the ULID.
    """
    result = 0
    for c in s:
        result = result * 32 + _CROCKFORD_BASE32.index(c)
    return result


def ulid_to_uuid7(ulid_text: str) -> str:
    """Convert a 32-char Crockford-base32 ULID to a deterministic UUID7 hex string.

    The function is pure: same input -> same output across processes, machines,
    and replays. No clock, no PRNG, no salt, no I/O. The output is a 32-char
    lowercase hex UUID7 per RFC 9562 section 5.7 with the ULID 48-bit ms
    timestamp preserved verbatim in bits 0-47.

    Args:
        ulid_text: Canonicalized 32-char Crockford-base32 ULID
            (case-insensitive, dashes stripped). All other inputs raise
            ValueError.

    Returns:
        32 lowercase hex chars in UUID7 layout (RFC 9562 section 5.7).

    Raises:
        TypeError: If ``input`` is not a :class:`str`.
        ValueError: If the input is the wrong length or contains
            characters outside the Crockford-base32 alphabet.
    """
    if not isinstance(ulid_text, str):
        raise TypeError(f"ulid_to_uuid7 expected str, got {type(ulid_text).__name__}")
    canonical = ulid_text.replace("-", "").upper()
    if not _ULID_RE.match(canonical):
        raise ValueError(
            f"ulid_to_uuid7 expected 32-char Crockford-base32 ULID, got {ulid_text!r}"
        )

    ts_int = _crockford_base32_decode(canonical[:10])
    h = hashlib.blake2b(canonical.encode("ascii"), digest_size=10).digest()
    ver = 0x7
    rand_a = int.from_bytes(h[0:2], "big") & 0x0FFF
    var = 0x2
    rand_b = int.from_bytes(h[2:10], "big") & 0x3FFFFFFFFFFFFFFF

    ts_b = struct.pack(">Q", ts_int)[2:]
    va_b = struct.pack(">H", (ver << 12) | rand_a)
    vb_b = struct.pack(">Q", (var << 62) | rand_b)
    raw = ts_b + va_b + vb_b
    return raw.hex()


__all__ = ["ulid_to_uuid7"]
