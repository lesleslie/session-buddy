"""Unit tests for ``session_buddy.mcp.tools.tasks_legacy``.

Pins the legacy coercion contract per spec §Migration & Backwards
Compatibility (line 696-706):

- ``id`` is the reflection ID (NOT a synthetic ``t-{32hex}``)
- ``content`` is as-is from the reflection row; rejected if validation
  fails (length cap or control characters)
- ``tags`` is preserved as-is
- ``LegacyTaskRow.coerced`` defaults to ``True`` (consumer signal)
- ``LegacyTaskRow.note`` documents the legacy status
"""

from __future__ import annotations

import re

from session_buddy.mcp.tools.tasks_legacy import coerce_legacy_reflection
from session_buddy.mcp.tools.tasks_models import LegacyTaskRow

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_coerce_legacy_reflection_with_todo_tag_returns_legacy_task_row() -> None:
    """Reflection with tags=['todo', 'refactor'] coerces to LegacyTaskRow with _coerced=True."""
    reflection = {
        "id": "01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123",
        "content": "old todo content",
        "tags": ["todo", "refactor"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }
    row = coerce_legacy_reflection(reflection)
    assert isinstance(row, LegacyTaskRow)
    assert row.id == "01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
    assert row.content == "old todo content"
    assert row.tags == ["todo", "refactor"]
    assert row.coerced is True
    assert "legacy" in row.note.lower() or "store_reflection" in row.note.lower()


# ---------------------------------------------------------------------------
# Rejection: content validation (same rules as new tasks)
# ---------------------------------------------------------------------------


def test_coerce_legacy_rejects_content_failing_create_validation() -> None:
    """Content > 4096 chars is rejected; returns None."""
    big_content = "x" * 4097
    reflection = {
        "id": "abc123",
        "content": big_content,
        "tags": ["todo"],
    }
    assert coerce_legacy_reflection(reflection) is None


def test_coerce_legacy_rejects_control_char_content() -> None:
    """Content with control characters is rejected; returns None."""
    reflection = {
        "id": "abc123",
        "content": "hello\x00world",  # NUL byte
        "tags": ["todo"],
    }
    assert coerce_legacy_reflection(reflection) is None


# ---------------------------------------------------------------------------
# Rejection: malformed rows
# ---------------------------------------------------------------------------


def test_coerce_legacy_rejects_missing_id() -> None:
    """Reflection with no id returns None."""
    reflection = {"content": "x", "tags": ["todo"]}
    assert coerce_legacy_reflection(reflection) is None


def test_coerce_legacy_rejects_missing_content() -> None:
    """Reflection with no content returns None."""
    reflection = {"id": "abc123", "tags": ["todo"]}
    assert coerce_legacy_reflection(reflection) is None


# ---------------------------------------------------------------------------
# Coercion policy: id + tags preserved verbatim
# ---------------------------------------------------------------------------


def test_coerce_legacy_id_is_reflection_id_not_t_prefix() -> None:
    """Coerced id is the reflection's own id (UUID/ULID), NOT a synthetic t-{32hex}."""
    reflection = {
        "id": "01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123",
        "content": "x",
        "tags": ["todo"],
    }
    row = coerce_legacy_reflection(reflection)
    assert row is not None
    # The id should NOT match the typed task pattern t-[0-9a-f]{32}
    assert not re.match(r"^t-[0-9a-f]{32}$", row.id)
    assert row.id == "01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"


def test_coerce_legacy_preserves_all_tags_unchanged() -> None:
    """Tags list is preserved as-is (no synthesis, no filtering)."""
    reflection = {
        "id": "abc",
        "content": "x",
        "tags": ["todo", "alice", "high-priority", "session-buddy"],
    }
    row = coerce_legacy_reflection(reflection)
    assert row is not None
    assert row.tags == ["todo", "alice", "high-priority", "session-buddy"]


# ---------------------------------------------------------------------------
# Boundary
# ---------------------------------------------------------------------------


def test_coerce_legacy_content_at_max_length_accepted() -> None:
    """Content exactly at 4096 chars is accepted (boundary)."""
    max_content = "x" * 4096
    reflection = {
        "id": "abc",
        "content": max_content,
        "tags": ["todo"],
    }
    row = coerce_legacy_reflection(reflection)
    assert row is not None
    assert len(row.content) == 4096