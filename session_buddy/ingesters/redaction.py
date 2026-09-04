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
TRUNCATED_MARKER = "[TRUNCATED]"

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
        # Project scoping tag — needed by Cross-Tool Fabric and
        # peer_modeling to filter by project. Not a secret; this is
        # the project's filesystem path or repo name (already public
        # to the user's local environment).
        "project",
    }
)

# Each entry is ``(compiled_pattern, required_substring)``. The substring
# is a cheap O(n) ``in``-check used to short-circuit ``re.sub`` when the
# pattern cannot match the input. Without this guard, patterns such as
# ``\S+@\S+\.\S+`` exhibit catastrophic backtracking (ReDoS) on large
# non-matching inputs — e.g. a 64KB block of unrelated characters makes
# ``_redact_iter`` blow past the test-timeout. Needles for
# ``re.IGNORECASE`` patterns are lowercase and matched against the
# lowercased text in :func:`_redact_iter`.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "ghp_"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "eyJ"),
    (re.compile(r"password=\S+", re.IGNORECASE), "password"),
    (re.compile(r"Authorization:\s*\S+", re.IGNORECASE), "authorization"),
    (re.compile(r"\b10\.\d+\.\d+\.\d+\b"), "10."),
    (re.compile(r"\b192\.168\.\d+\.\d+\b"), "192"),
    (re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+\b"), "172"),
    (re.compile(r"/Users/[^/\s]+/\.ssh/"), "/.ssh/"),
    (re.compile(r"~/\.ssh/"), "~/.ssh/"),
    (re.compile(r"\S+@\S+\.\S+"), "@"),
    (re.compile(r"\+?\d{1,3}[-.\s]??\(?\d{1,4}\)?[-.\s]??\d{1,4}[-.\s]??\d{1,9}"), "0"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "0"),
)


class RedactionSizeError(Exception):
    """Raised when input to :func:`redact` exceeds the 64KB size cap."""


def _redact_iter(text: str) -> str:
    """Apply every secret pattern to ``text`` in order.

    Used by both :func:`redact` and the truncation path so redaction logic
    is defined in one place. Each pattern has a required-substring guard
    so we can skip ``re.sub`` cheaply when the needle is absent — see
    :data:`_SECRET_PATTERNS` for the ReDoS motivation.
    """
    text_lower = text.lower()
    for pattern, needle in _SECRET_PATTERNS:
        # ``needle in text`` covers case-sensitive patterns; the
        # ``needle in text_lower`` fallthrough covers ``re.IGNORECASE``
        # patterns whose needles are stored lowercase.
        if needle not in text and needle not in text_lower:
            continue
        text = pattern.sub(REDACTED_MARKER, text)
    return text


def redact(text: str, *, raise_on_oversize: bool = False) -> str:
    """Replace secret-shaped substrings with ``[REDACTED]``.

    By default, content larger than ``MAX_REDACTION_BYTES`` (64KB) is
    truncated to the first 64KB and tagged with a ``[TRUNCATED]`` suffix.
    Set ``raise_on_oversize=True`` to recover the strict behavior, which
    raises :class:`RedactionSizeError` for oversized input instead.
    """
    if len(text) > MAX_REDACTION_BYTES:
        if raise_on_oversize:
            raise RedactionSizeError(
                f"Input of {len(text)} bytes exceeds {MAX_REDACTION_BYTES} cap"
            )
        return _redact_iter(text[:MAX_REDACTION_BYTES]) + TRUNCATED_MARKER
    return _redact_iter(text)


def redact_metadata(
    metadata: dict[str, object],
    allowlist: set[str],
    *,
    raise_on_oversize: bool = False,
) -> dict[str, object]:
    """Return a copy of ``metadata`` with allowlisted keys untouched.

    Keys outside the allowlist are moved into a ``_redacted`` mapping.
    When the serialized form of the returned dict exceeds
    ``MAX_REDACTION_BYTES``, oversized string values are truncated and a
    ``_truncated`` flag is set. Set ``raise_on_oversize=True`` to opt
    back into :class:`RedactionSizeError` on oversize input.
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

    serialized: str = repr(redacted)
    if len(serialized) > MAX_REDACTION_BYTES:
        if raise_on_oversize:
            raise RedactionSizeError(
                f"Metadata of {len(serialized)} bytes exceeds {MAX_REDACTION_BYTES} cap"
            )
        truncated: dict[str, object] = {}
        for key, value in redacted.items():
            if isinstance(value, str) and len(value) >= MAX_REDACTION_BYTES:
                truncated[key] = value[:MAX_REDACTION_BYTES] + TRUNCATED_MARKER
            else:
                truncated[key] = value
        truncated["_truncated"] = True
        return truncated

    return redacted


__all__ = [
    "ALLOWED_METADATA_KEYS",
    "MAX_REDACTION_BYTES",
    "REDACTED_MARKER",
    "TRUNCATED_MARKER",
    "RedactionSizeError",
    "redact",
    "redact_metadata",
]
