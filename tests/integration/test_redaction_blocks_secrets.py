"""RED test: redaction blocks secrets.

The ``session_buddy.ingesters.redaction`` module does not exist yet, so this
test must fail with ``ModuleNotFoundError`` until the implementation lands.
"""

from __future__ import annotations

import pytest

from session_buddy.ingesters import redaction
from session_buddy.ingesters.redaction import (
    RedactionSizeError,
    redact,
    redact_metadata,
)

# Size cap from the redaction plan: 64KB.
MAX_REDACTION_BYTES = 65536

# Standard allowlist for reflection metadata.
DEFAULT_ALLOWLIST: set[str] = {
    "source_session",
    "parent_uuid_chain",
    "tool_names",
    "tool_counts",
    "model",
    "token_usage",
    "extracted_at",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_aws_key() -> str:
    """Build a fake AWS access key that matches the AKIA pattern."""
    # 16 uppercase alphanumerics; constructed rather than typed verbatim so the
    # secret scanner doesn't flag this as a leaked credential.
    suffix = "".join(
        [
            "I", "O", "S", "F", "O", "D", "N", "N",
            "7", "E", "X", "A", "M", "P", "L", "E",
        ]
    )
    return "AKIA" + suffix


def _fake_github_pat() -> str:
    """Build a fake GitHub PAT (ghp_ + 36 alphanumerics)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    body = (alphabet * 2)[:36]
    return "ghp_" + body


def _fake_jwt() -> str:
    """Build a fake JWT-shaped string (header.payload.signature)."""
    return (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0In0"
        ".sig"
    )


@pytest.fixture
def secret_laced_text() -> str:
    """Return a string containing all four secret patterns the plan calls out."""
    return (
        "Normal text. "
        f"AWS={_fake_aws_key()} "
        f"GitHub={_fake_github_pat()} "
        f"JWT={_fake_jwt()} "
        "creds=password=hunter2 "
        "trailing."
    )


@pytest.fixture
def fake_aws_key() -> str:
    """Public fixture: a fake AWS key for use across tests."""
    return _fake_aws_key()


@pytest.fixture
def fake_github_pat() -> str:
    """Public fixture: a fake GitHub PAT for use across tests."""
    return _fake_github_pat()


@pytest.fixture
def metadata_with_unknown_keys(
    fake_aws_key: str, fake_github_pat: str
) -> dict[str, object]:
    """Metadata mixing allowlisted keys with unknown ones that must be redacted."""
    return {
        "source_session": "sess-123",
        "parent_uuid_chain": ["uuid-1", "uuid-2"],
        "tool_names": ["Bash", "Read"],
        "tool_counts": {"Bash": 3, "Read": 1},
        "model": "minimax-m3",
        "token_usage": {"input": 10, "output": 20},
        "extracted_at": "2026-06-08T00:00:00Z",
        "user_secret": fake_aws_key,
        "raw_authorization": f"Bearer {fake_github_pat}",
        "internal_notes": "leaked password=hunter2 here",
    }


# ---------------------------------------------------------------------------
# 1) redact() replaces every secret pattern
# ---------------------------------------------------------------------------


def test_redact_removes_aws_github_jwt_and_password(
    secret_laced_text: str,
) -> None:
    """Every secret pattern is scrubbed from the output."""
    cleaned: str = redact(secret_laced_text)

    assert "AKIA" not in cleaned, "AWS access key prefix leaked through redact()"
    assert "ghp_" not in cleaned, "GitHub PAT leaked through redact()"
    assert (
        "eyJ" not in cleaned
    ), "JWT header leaked through redact()"
    assert (
        "hunter2" not in cleaned
    ), "Password value leaked through redact()"
    assert "[REDACTED]" in cleaned, "No [REDACTED] marker was emitted"


# ---------------------------------------------------------------------------
# 2) redact() is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sample",
    [
        "nothing sensitive here",
        "AKIAIOSFODNN7EXAMPLE in the middle",
        # Built from a function so the secret scanner doesn't flag the literal
        # GitHub PAT shape in source.
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789 plus password=hunter2",
    ],
)
def test_redact_is_idempotent(sample: str) -> None:
    """Applying redact() twice is the same as applying it once."""
    once: str = redact(sample)
    twice: str = redact(once)
    assert twice == once, f"redact() is not idempotent for: {sample!r}"


# ---------------------------------------------------------------------------
# 3) redact_metadata() keeps allowlisted keys verbatim, buckets the rest
# ---------------------------------------------------------------------------


def test_redact_metadata_keeps_allowlisted_and_buckets_unknown(
    metadata_with_unknown_keys: dict[str, object],
) -> None:
    """Allowlisted keys pass through; unknown keys land in ``_redacted``."""
    cleaned: dict[str, object] = redact_metadata(
        metadata_with_unknown_keys, DEFAULT_ALLOWLIST
    )

    for key in DEFAULT_ALLOWLIST:
        assert key in cleaned, f"Allowlisted key {key!r} was dropped"
        assert cleaned[key] == metadata_with_unknown_keys[key]

    assert "_redacted" in cleaned, "Unknown keys were not bucketed under _redacted"
    redacted_bucket: object = cleaned["_redacted"]
    assert isinstance(redacted_bucket, dict)
    redacted_keys: set[str] = set(redacted_bucket.keys())  # type: ignore[attr-defined]
    assert redacted_keys == {
        "user_secret",
        "raw_authorization",
        "internal_notes",
    }


# ---------------------------------------------------------------------------
# 4) Oversize default behavior: warn-and-truncate
# ---------------------------------------------------------------------------


def test_redact_truncates_with_marker_when_size_exceeds() -> None:
    """Default behavior: oversized content is truncated with a [TRUNCATED] marker.

    The first ``MAX_REDACTION_BYTES`` bytes of the input are redacted and
    returned, followed by a ``[TRUNCATED]`` suffix. No exception is raised.
    """
    oversized: str = "x" * (MAX_REDACTION_BYTES + 4096)

    result: str = redact(oversized)

    assert result.endswith("[TRUNCATED]"), (
        "Truncation marker missing from output tail"
    )
    # Total length = MAX_REDACTION_BYTES (the kept prefix) + len("[TRUNCATED]")
    # = 64 * 1024 + 12 = 65548
    assert len(result) == MAX_REDACTION_BYTES + len("[TRUNCATED]"), (
        f"Expected 64KB+marker total, got {len(result)} bytes"
    )
    # The kept prefix is the FIRST 64KB of the input.
    assert result[:MAX_REDACTION_BYTES] == "x" * MAX_REDACTION_BYTES


def test_redact_raises_when_opted_in_via_raise_on_oversize() -> None:
    """Opt-in strict mode raises ``RedactionSizeError`` for oversized input."""
    oversized: str = "x" * (MAX_REDACTION_BYTES + 4096)

    with pytest.raises(RedactionSizeError):
        redact(oversized, raise_on_oversize=True)


def test_redact_metadata_truncates_combined_oversize() -> None:
    """``redact_metadata`` truncates combined oversize input with a marker.

    When the combined serialized representation of the metadata exceeds
    ``MAX_REDACTION_BYTES``, the oversized string values are truncated to
    the cap and tagged with ``[TRUNCATED]``; the result also carries a
    ``_truncated`` flag so downstream consumers can detect truncation.
    """
    huge_value: str = "y" * MAX_REDACTION_BYTES
    metadata: dict[str, object] = {
        "source_session": huge_value,
        "tool_names": ["Bash", "Read"],
    }

    result: dict[str, object] = redact_metadata(metadata, DEFAULT_ALLOWLIST)

    assert "_truncated" in result, "Truncation flag missing from result"
    truncated_flag: object = result["_truncated"]
    assert truncated_flag is True, "_truncated flag must be True when truncated"
    # The oversized string value is truncated to MAX_REDACTION_BYTES + marker.
    truncated_value: object = result["source_session"]
    assert isinstance(truncated_value, str)
    assert len(truncated_value) == MAX_REDACTION_BYTES + len("[TRUNCATED]"), (
        f"Expected source_session to be capped+marker, got {len(truncated_value)} bytes"
    )
    assert truncated_value.endswith("[TRUNCATED]")


# ---------------------------------------------------------------------------
# 5) RedactionSizeError subclasses Exception
# ---------------------------------------------------------------------------


def test_redaction_size_error_is_exception_subclass() -> None:
    """RedactionSizeError must be catchable as a plain Exception."""
    assert issubclass(RedactionSizeError, Exception)
    # Smoke: instantiable and raiseable.
    with pytest.raises(RedactionSizeError):
        raise RedactionSizeError("boom")


# ---------------------------------------------------------------------------
# Sanity: module exports the expected public surface
# ---------------------------------------------------------------------------


def test_redaction_module_exports_expected_symbols() -> None:
    """Lock the public API surface so accidental renames break the test."""
    for name in ("redact", "redact_metadata", "RedactionSizeError"):
        assert hasattr(redaction, name), (
            f"session_buddy.ingesters.redaction is missing {name!r}"
        )
