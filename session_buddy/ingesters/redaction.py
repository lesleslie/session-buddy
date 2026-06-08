"""Secret redaction for reflection text and metadata.

Pattern-based scrubbing that replaces common credential shapes with a
``[REDACTED]`` marker. The module is intentionally dependency-free so it
can run on hot ingestion paths without pulling in ``detect-secrets``.

Idempotency: a second ``redact()`` pass over already-redacted text is a
no-op because ``[REDACTED]`` does not match any of the patterns.
"""

from __future__ import annotations

import re

MAX_REDACTION_BYTES = 65536
REDACTED_MARKER = "[REDACTED]"

# Standard allowlist for reflection metadata. Keys outside this set are
# moved into a ``_redacted`` bucket by :func:`redact_metadata`.
ALLOWED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "source_session",
        "parent_uuid_chain",
        "tool_names",
        "tool_counts",
        "model",
        "token_usage",
        "extracted_at",
    }
)

# Each pattern is compiled once at import time for reuse across calls.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(r"password=\S+", re.IGNORECASE),
    re.compile(r"Authorization:\s*\S+", re.IGNORECASE),
    re.compile(r"\b10\.\d+\.\d+\.\d+\b"),
    re.compile(r"\b192\.168\.\d+\.\d+\b"),
    re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+\b"),
    re.compile(r"/Users/[^/\s]+/\.ssh/"),
    re.compile(r"~/\.ssh/"),
    re.compile(r"\S+@\S+\.\S+"),
    re.compile(r"\+?\d{1,3}[-.\s]??\(?\d{1,4}\)?[-.\s]??\d{1,4}[-.\s]??\d{1,9}"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
)


class RedactionSizeError(Exception):
    """Raised when input to :func:`redact` exceeds the 64KB size cap."""


def redact(text: str) -> str:
    """Replace secret-shaped substrings with ``[REDACTED]``.

    Raises :class:`RedactionSizeError` if ``text`` is larger than 64KB.
    """
    if len(text) > MAX_REDACTION_BYTES:
        raise RedactionSizeError(
            f"Input of {len(text)} bytes exceeds {MAX_REDACTION_BYTES} cap"
        )
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED_MARKER, text)
    return text


def redact_metadata(
    metadata: dict[str, object], allowlist: set[str]
) -> dict[str, object]:
    """Return a copy of ``metadata`` with allowlisted keys untouched.

    Keys outside the allowlist are moved into a ``_redacted`` mapping.
    """
    redacted: dict[str, object] = {}
    bucket: dict[str, object] = {}
    for key, value in metadata.items():
        if key in allowlist:
            redacted[key] = value
        else:
            bucket[key] = value
    if bucket:
        redacted["_redacted"] = bucket
    return redacted


__all__ = [
    "ALLOWED_METADATA_KEYS",
    "MAX_REDACTION_BYTES",
    "REDACTED_MARKER",
    "RedactionSizeError",
    "redact",
    "redact_metadata",
]
