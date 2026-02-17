"""ULID Generation Module for Session-Buddy.

Provides standalone ULID generation functions that can be imported
without requiring the full storage layer.
"""

import time
import os


def generate_ulid() -> str:
    """Generate ULID using Dhruva implementation or timestamp-based fallback.

    Returns:
        26-character Crockford Base32 ULID string
    """
    # Try Dhruva first
    try:
        from dhruva import generate as generate_ulid_impl
        return generate_ulid_impl()
    except ImportError:
        # Use timestamp-based fallback
        import struct

        timestamp_ms = int(time.time() * 1000)
        timestamp_bytes = timestamp_ms.to_bytes(6, byteorder='big')

        # Generate 10 bytes of randomness
        randomness = os.urandom(10)

        # Combine: 6 bytes timestamp + 10 bytes randomness = 16 bytes
        ulid_bytes = timestamp_bytes + randomness

        # Encode to Crockford Base32 (Dhruva's alphabet)
        alphabet = "0123456789abcdefghjkmnpqrstvwxyz"

        # Convert 16 bytes to 128 bits, then encode as base32 (5 bits per char)
        # This gives us 26 characters (last char only uses 3 bits)
        result = []
        value = int.from_bytes(ulid_bytes, byteorder='big')

        for _ in range(26):
            index = value & 0x1F  # Get lowest 5 bits
            result.append(alphabet[index])
            value >>= 5  # Shift right by 5 bits

        # Reverse to get correct order (most significant first)
        return ''.join(reversed(result))


def is_valid_ulid(value: str) -> bool:
    """Check if value is a valid ULID.

    Args:
        value: String to validate

    Returns:
        True if 26-character Crockford Base32
    """
    if len(value) != 26:
        return False
    return all(c in "0123456789abcdefghjkmnpqrstvwxyz" for c in value)


# Export public API
__all__ = [
    "generate_ulid",
    "is_valid_ulid",
]
