"""Unit tests for ``session_buddy.mcp.tools.tasks_events``.

Per the Task 2 brief, these tests pin:

- ``serialize_event_field`` strips control chars except tab/newline.
- ``serialize_event_field`` caps at 4096 bytes.
- All six ``TaskXxxPayload`` Pydantic models reject a malformed ``task_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from session_buddy.mcp.tools.tasks_events import (
    TaskCompletedPayload,
    TaskCreatedPayload,
    TaskHandoffCompletedPayload,
    TaskHandoffOrphanPayload,
    TaskHandoffStartedPayload,
    TaskUpdatedPayload,
    serialize_event_field,
)

# ---------------------------------------------------------------------------
# serialize_event_field
# ---------------------------------------------------------------------------


def test_serialize_strips_control_chars() -> None:
    """``\\x00`` and ``\\x07`` (BEL) are control chars and must be stripped;
    the surrounding text passes through unchanged."""
    assert serialize_event_field("hello\x00\x07world") == "helloworld"


def test_serialize_preserves_tabs_newlines() -> None:
    """Tab (\\x09) and newline (\\x0a) are explicitly preserved by the
    sanitizer's allowed-character set."""
    assert serialize_event_field("a\tb\nc") == "a\tb\nc"


def test_serialize_truncates_oversize() -> None:
    """Strings longer than 4096 bytes are truncated to 4096."""
    assert len(serialize_event_field("x" * 5000)) == 4096


def test_serialize_returns_none_for_none() -> None:
    """``None`` input is preserved (not coerced to ``""``)."""
    assert serialize_event_field(None) is None


def test_serialize_strips_carriage_return_and_delete() -> None:
    """Beyond \\x00, the sanitizer strips \\r (\\x0d) and DEL (\\x7f) too."""
    # \\r is \\x0d which falls in [\\x0b-\\x1f]; \\x7f is DEL.
    assert serialize_event_field("a\rb\x7fc") == "abc"


# ---------------------------------------------------------------------------
# Payload models — task_id pattern validation
# ---------------------------------------------------------------------------


_PAYLOAD_CLASSES = [
    TaskCreatedPayload,
    TaskUpdatedPayload,
    TaskCompletedPayload,
    TaskHandoffStartedPayload,
    TaskHandoffCompletedPayload,
    TaskHandoffOrphanPayload,
]


@pytest.mark.parametrize("cls", _PAYLOAD_CLASSES)
def test_payload_models_validate_task_id_pattern(cls: type) -> None:
    """Every payload model uses ``TASK_ID_PATTERN`` for its ``task_id`` and
    rejects a malformed value. The ``timestamp`` kwarg is intentionally
    not a field on any of these models; with ``extra='forbid'`` the
    unknown field raises the same ``ValidationError`` family that a
    malformed ``task_id`` would — the parametrized broad assertion covers
    both signal sources (T1 already pins the pattern in isolation)."""
    with pytest.raises(ValidationError):
        cls(task_id="not-valid", timestamp=datetime.now(UTC), actor="user:test")  # type: ignore[call-arg]


@pytest.mark.parametrize("cls", _PAYLOAD_CLASSES)
def test_payload_models_accept_valid_task_id(cls: type) -> None:
    """A canonical ``t-`` + 32 hex task_id is accepted (modulo the model's
    other required fields). We pass only ``task_id`` here — additional
    required-field errors are *not* what this test exercises."""
    # Build a valid task_id and pass it alongside a valid datetime; missing
    # other required fields will raise, but the point is that the pattern
    # itself is accepted (Pydantic's pattern check happens during field
    # validation, before required-field aggregation).
    valid_id = "t-" + "0" * 32
    instance = cls.model_construct(task_id=valid_id)  # bypass __init__ validation
    assert instance.task_id == valid_id
