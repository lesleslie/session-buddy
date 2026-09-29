"""Unit tests for ``session_buddy.mcp.tools.tasks_events``.

Per the Task 2 brief, these tests pin:

- ``serialize_event_field`` strips control chars except tab/newline.
- ``serialize_event_field`` caps at 4096 bytes.
- All six ``TaskXxxPayload`` Pydantic models accept a canonical
  ``t-`` + 32 hex ``task_id`` and reject a malformed one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from session_buddy.mcp.tools.tasks_events import (
    TaskCompletedPayload,
    TaskCreatedPayload,
    TaskHandoffCompletedPayload,
    TaskHandoffOrphanPayload,
    TaskHandoffStartedPayload,
    TaskUpdatedPayload,
    serialize_event_field,
)

# Canonical task_id used by the positive tests below. Hex digits are
# intentionally zero so a typo (mixing in real UUID7 bytes) can't silently
# shadow the pattern check.
_VALID_TASK_ID = "t-" + "0" * 32
_NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

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
    """A canonical ``t-`` + 32 hex task_id is accepted — construction goes
    through the *real* ``__init__`` path with all required fields filled
    in, so the ``TASK_ID_PATTERN`` field-validator actually fires. Pairs
    with the parametrized negative test above to pin the pattern in
    isolation, without relying on the ``extra='forbid'`` side-effect.

    Per-model kwargs are necessary because the six payload models have
    different required fields (e.g. ``TaskHandoffStartedPayload`` carries
    ``adapter`` and ``workflow_id``; ``TaskCreatedPayload`` carries
    ``owner`` and ``content_hash``). ``_kwargs_for`` keeps the kwargs
    table next to the test it's used in.
    """
    instance = cls(task_id=_VALID_TASK_ID, **_kwargs_for(cls))
    assert instance.task_id == _VALID_TASK_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kwargs_for(cls: type[BaseModel]) -> dict[str, object]:
    """Return kwargs sufficient to construct ``cls`` with all required
    fields filled in. The ``task_id`` slot is intentionally excluded — the
    test that uses this helper injects it via the parametrize table."""
    if cls is TaskCreatedPayload:
        return {
            "owner": "user:les",
            "actor": "user:les",
            "created_at": _NOW,
            "content_hash": "0" * 64,
        }
    if cls is TaskUpdatedPayload:
        return {
            "actor": "user:les",
            "updated_at": _NOW,
            "diff": {"status": ("open", "in_progress")},
        }
    if cls is TaskCompletedPayload:
        return {
            "actor": "user:les",
            "completed_at": _NOW,
            "has_workflow_id": False,
        }
    if cls is TaskHandoffStartedPayload:
        return {
            "workflow_id": "wf-abc",
            "actor": "user:les",
            "adapter": "prefect",
            "started_at": _NOW,
        }
    if cls is TaskHandoffCompletedPayload:
        return {
            "workflow_id": "wf-abc",
            "actor": "user:les",
            "completed_at": _NOW,
        }
    if cls is TaskHandoffOrphanPayload:
        return {
            "workflow_id": "wf-abc",
            "actor": "user:les",
            "reason": "step_3_update_failed",
            "orphaned_at": _NOW,
        }
    raise AssertionError(f"unhandled payload class: {cls.__name__}")
