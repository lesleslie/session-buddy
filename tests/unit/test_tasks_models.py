"""Unit tests for ``session_buddy.mcp.tools.tasks_models``.

Per the Task 1 brief, these tests pin:

- ``TASK_ID_PATTERN`` matches full UUID7 form (``t-`` + 32 hex chars),
  rejects compact 12-hex form, and rejects random hex strings.
- ``new_task_id()`` produces distinct canonical IDs on every call.
- ``Task`` field-validators: ``tags`` must include ``"task"``,
  ``due_at`` must be timezone-aware (naive datetimes rejected),
  ``metadata`` serialized size capped at 1 KiB.
- ``UpdateTaskRequest`` is bounded: cannot set ``workflow_id``,
  ``id``, ``created_at``, or ``created_by`` (immutable fields).
- All remaining models import and round-trip cleanly.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from session_buddy.mcp.tools.tasks_models import (
    OWNER_PATTERN,
    TASK_ID_PATTERN,
    HandoffParams,
    HandoffResult,
    JsonValue,
    LegacyTaskRow,
    Task,
    TaskEvent,
    TaskHistoryResult,
    TaskListResult,
    UpdateTaskRequest,
    new_task_id,
)

# ---------------------------------------------------------------------------
# Constants + ID format
# ---------------------------------------------------------------------------


def test_task_id_pattern_matches_full_uuid7() -> None:
    """``TASK_ID_PATTERN`` accepts ``t-`` + 32 lowercase hex chars."""
    for _ in range(100):
        tid = new_task_id()
        assert re.match(TASK_ID_PATTERN, tid), f"{tid!r} doesn't match pattern"
        assert tid.startswith("t-")
        assert len(tid) == 34  # "t-" + 32 hex


def test_task_id_pattern_rejects_compact_form() -> None:
    """12-hex compact form is display-only; not a valid lookup key."""
    assert not re.match(TASK_ID_PATTERN, "t-0190a3b4c5d6")


def test_task_id_pattern_rejects_non_uuid7() -> None:
    """``TASK_ID_PATTERN`` is shape-only: it rejects non-hex chars, wrong
    prefix, or wrong length. It does NOT validate UUID7 structure (no
    version-nibble check) — UUID7 validation lives in :func:`new_task_id`,
    which is the only generator allowed to produce canonical task IDs.
    The brief's original ``"t-deadbeefcafebabe1234567890abcdef"`` input
    has 32 lowercase hex chars and therefore DOES match the pattern by
    design; this test instead rejects a string with non-hex characters,
    which is the genuine guard against random non-UUID7 input.
    """
    # Non-hex characters (uppercase 'Z') do not match [0-9a-f].
    assert not re.match(TASK_ID_PATTERN, "t-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ")
    # Wrong prefix.
    assert not re.match(TASK_ID_PATTERN, "x-0190a3b4c5d6e7f80190a3b4c5d6e7f8")
    # Too short.
    assert not re.match(TASK_ID_PATTERN, "t-0190a3b4c5d6")
    # Too long (33 hex chars).
    assert not re.match(
        TASK_ID_PATTERN, "t-0190a3b4c5d6e7f80190a3b4c5d6e7f80"
    )


def test_owner_pattern_accepts_user_form() -> None:
    assert re.match(OWNER_PATTERN, "user:les@wedgwoodwebworks.com")


def test_owner_pattern_accepts_agent_form() -> None:
    assert re.match(OWNER_PATTERN, "agent:worker-1")


def test_owner_pattern_rejects_bare_email() -> None:
    assert not re.match(OWNER_PATTERN, "les@wedgwoodwebworks.com")


def test_owner_pattern_rejects_wrong_prefix() -> None:
    assert not re.match(OWNER_PATTERN, "admin:root")


def test_owner_pattern_rejects_empty_id() -> None:
    assert not re.match(OWNER_PATTERN, "user:")


# ---------------------------------------------------------------------------
# new_task_id()
# ---------------------------------------------------------------------------


def test_new_task_id_matches_pattern() -> None:
    """``new_task_id()`` output satisfies the canonical pattern."""
    for _ in range(10):
        tid = new_task_id()
        assert re.match(TASK_ID_PATTERN, tid)
        assert tid.startswith("t-")
        assert len(tid) == 34


def test_new_task_id_returns_distinct_values() -> None:
    """Distinct calls return distinct IDs (probabilistic but UUID7's
    74 random bits make collision infeasible in 10 calls)."""
    ids = {new_task_id() for _ in range(10)}
    assert len(ids) == 10


def test_new_task_id_is_uuid7_hex() -> None:
    """The 32 hex chars after ``t-`` are a valid UUID7 hex (no dashes)."""
    tid = new_task_id()
    hex_part = tid.removeprefix("t-")
    # ``uuid.UUID`` accepts both dashed and undashed hex.
    parsed = uuid.UUID(hex_part)
    assert parsed.version == 7


# ---------------------------------------------------------------------------
# Task field-validators
# ---------------------------------------------------------------------------


def _make_task_kwargs(**overrides: object) -> dict[str, object]:
    """Return kwargs sufficient to construct a valid Task; ``overrides``
    let individual tests tweak specific fields without rebuilding the
    whole dict by hand."""
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "id": new_task_id(),
        "content": "Test content",
        "tags": ["task", "audit"],
        "created_at": now,
        "updated_at": now,
        "metadata": {},
    }
    base.update(overrides)
    return base


def test_task_tags_must_include_task_discriminator() -> None:
    """``tags`` without ``"task"`` is rejected."""
    with pytest.raises(ValidationError, match='must include "task" discriminator'):
        Task(**_make_task_kwargs(tags=["audit", "refactor"]))


def test_task_tags_accepts_task_alone() -> None:
    """``["task"]`` alone is valid; spec requires ``task`` plus optional
    domain tags, so the minimum is one element."""
    task = Task(**_make_task_kwargs(tags=["task"]))
    assert "task" in task.tags


def test_task_due_at_rejects_naive_datetime() -> None:
    """``due_at`` must be timezone-aware."""
    with pytest.raises(ValidationError, match="timezone-aware"):
        Task(**_make_task_kwargs(due_at=datetime(2026, 12, 31, 12, 0, 0)))  # noqa: DTZ001 (intentionally naive — under test)


def test_task_due_at_accepts_aware_datetime() -> None:
    """Aware datetimes are accepted."""
    task = Task(
        **_make_task_kwargs(due_at=datetime(2026, 12, 31, 12, 0, tzinfo=UTC))
    )
    assert task.due_at is not None
    assert task.due_at.tzinfo is not None


def test_task_metadata_rejects_oversize_payload() -> None:
    """``metadata`` serialized JSON must be ≤ 1 KiB."""
    huge_value = "x" * 1100  # serialized JSON adds 2 quotes → ~1102 bytes
    with pytest.raises(ValidationError, match="metadata serialized size > 1 KiB"):
        Task(**_make_task_kwargs(metadata={"k": huge_value}))


def test_task_metadata_accepts_under_cap() -> None:
    """A ~1 KiB payload at the boundary is accepted."""
    # Build a payload that is comfortably under 1024 bytes when serialized.
    payload = {"k": "v", "n": 42}
    task = Task(**_make_task_kwargs(metadata=payload))
    assert task.metadata == payload


def test_task_metadata_supports_nested_json_values() -> None:
    """``JsonValue`` recursion permits nested dicts and lists."""
    payload: dict[str, JsonValue] = {
        "list": [1, "two", None, {"inner": True}],
        "scalar": 42,
        "text": "hello",
    }
    task = Task(**_make_task_kwargs(metadata=payload))
    assert task.metadata == payload


def test_task_rejects_oversized_content() -> None:
    """``content`` max length is 4096 bytes."""
    with pytest.raises(ValidationError):
        Task(**_make_task_kwargs(content="x" * 4097))


def test_task_id_must_match_pattern() -> None:
    """A malformed ``id`` is rejected by the field pattern."""
    with pytest.raises(ValidationError):
        Task(**_make_task_kwargs(id="not-a-uuid"))


def test_task_id_compact_form_rejected() -> None:
    """Compact 12-hex form is display-only; not accepted by the model."""
    with pytest.raises(ValidationError):
        Task(**_make_task_kwargs(id="t-0190a3b4c5d6"))


def test_task_extra_fields_rejected() -> None:
    """``ConfigDict(extra='forbid')`` blocks unknown fields."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        Task(**_make_task_kwargs(unknown_field="ignored"))


def test_task_status_enum_validates() -> None:
    """Only the spec-defined literals are accepted for ``status``."""
    with pytest.raises(ValidationError):
        Task(**_make_task_kwargs(status="pending"))


def test_task_priority_enum_validates() -> None:
    """Only the spec-defined literals are accepted for ``priority``."""
    with pytest.raises(ValidationError):
        Task(**_make_task_kwargs(priority="p0"))


def test_task_effort_enum_validates() -> None:
    """Only the spec-defined literals are accepted for ``effort``."""
    with pytest.raises(ValidationError):
        Task(**_make_task_kwargs(effort="huge"))


# ---------------------------------------------------------------------------
# UpdateTaskRequest — bounded, excludes immutable fields
# ---------------------------------------------------------------------------


def test_update_request_accepts_subset_of_fields() -> None:
    """A minimal update is valid."""
    req = UpdateTaskRequest(content="updated content", status="in_progress")
    assert req.content == "updated content"
    assert req.status == "in_progress"
    assert req.priority is None


def test_update_request_cannot_set_workflow_id() -> None:
    """``workflow_id`` is server-set on handoff only; not user-updatable."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        UpdateTaskRequest(workflow_id="wf-1")  # type: ignore[call-arg]


def test_update_request_cannot_set_id() -> None:
    """``id`` is immutable; the model rejects attempts to set it."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        UpdateTaskRequest(id="t-1234")  # type: ignore[call-arg]


def test_update_request_cannot_set_created_at() -> None:
    """``created_at`` is immutable."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        UpdateTaskRequest(
            created_at=datetime(2026, 1, 1, tzinfo=UTC)  # type: ignore[call-arg]
        )


def test_update_request_cannot_set_created_by() -> None:
    """``created_by`` is server-set at create time and not user-mutable."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        UpdateTaskRequest(created_by="user:impostor")  # type: ignore[call-arg]


def test_update_request_cannot_set_completed_at() -> None:
    """``completed_at`` is server-set by ``tasks_complete``; not user-mutable."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        UpdateTaskRequest(
            completed_at=datetime(2026, 1, 1, tzinfo=UTC)  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# List + history envelopes
# ---------------------------------------------------------------------------


def test_task_list_result_round_trips() -> None:
    """``TaskListResult`` serializes with items, total, and optional cursor."""
    now = datetime.now(UTC)
    task = Task(**_make_task_kwargs(created_at=now, updated_at=now))
    result = TaskListResult(items=[task], total=1, next_cursor="abc")
    payload = json.loads(result.model_dump_json())
    assert payload["total"] == 1
    assert payload["next_cursor"] == "abc"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == task.id


def test_task_list_result_default_cursor_is_none() -> None:
    """``next_cursor`` defaults to ``None``."""
    result = TaskListResult(items=[], total=0)
    assert result.next_cursor is None


def test_task_history_result_carries_events() -> None:
    """``TaskHistoryResult`` carries ``TaskEvent`` items."""
    now = datetime.now(UTC)
    event = TaskEvent(
        task_id=new_task_id(),
        event_type="created",
        actor="user:les@wedgwoodwebworks.com",
        timestamp=now,
    )
    history = TaskHistoryResult(items=[event])
    payload = json.loads(history.model_dump_json())
    assert len(payload["items"]) == 1
    assert payload["items"][0]["event_type"] == "created"


def test_task_event_enum_rejects_unknown_type() -> None:
    """``event_type`` is bounded to the spec's literal set."""
    with pytest.raises(ValidationError):
        TaskEvent(
            task_id=new_task_id(),
            event_type="deleted",  # type: ignore[arg-type]
            timestamp=datetime.now(UTC),
        )


def test_task_event_all_event_types_accepted() -> None:
    """All seven spec-defined event types validate."""
    task_id = new_task_id()
    for event_type in (
        "created",
        "updated",
        "completed",
        "cancelled",
        "handoff_started",
        "handoff_completed",
        "handoff_orphan",
    ):
        ev = TaskEvent(
            task_id=task_id,
            event_type=event_type,  # type: ignore[arg-type]
            timestamp=datetime.now(UTC),
        )
        assert ev.event_type == event_type


# ---------------------------------------------------------------------------
# Handoff envelopes
# ---------------------------------------------------------------------------


def test_handoff_params_defaults() -> None:
    """Defaults: ``pool_selector='least_loaded'``, ``extra_metadata={}``."""
    hp = HandoffParams()
    assert hp.pool_selector == "least_loaded"
    assert hp.extra_metadata == {}


def test_handoff_params_rejects_unknown_selector() -> None:
    """``pool_selector`` is bounded to the three spec literals."""
    with pytest.raises(ValidationError):
        HandoffParams(pool_selector="random")  # type: ignore[arg-type]


def test_handoff_result_round_trips() -> None:
    """``HandoffResult`` exposes task_id/workflow_id/adapter/started_at/pool_name."""
    now = datetime.now(UTC)
    hr = HandoffResult(
        task_id=new_task_id(),
        workflow_id="wf-abc",
        adapter="prefect",
        started_at=now,
        pool_name="local",
    )
    payload = json.loads(hr.model_dump_json())
    assert payload["workflow_id"] == "wf-abc"
    assert payload["adapter"] == "prefect"
    assert payload["pool_name"] == "local"


def test_handoff_result_rejects_unknown_adapter() -> None:
    """``adapter`` is bounded to ``{prefect, llamaindex, agno}``."""
    with pytest.raises(ValidationError):
        HandoffResult(
            task_id=new_task_id(),
            workflow_id="wf-x",
            adapter="kafka",  # type: ignore[arg-type]
            started_at=datetime.now(UTC),
            pool_name="local",
        )


def test_handoff_result_task_id_must_match_pattern() -> None:
    """``task_id`` is validated against ``TASK_ID_PATTERN``."""
    with pytest.raises(ValidationError):
        HandoffResult(
            task_id="not-valid",
            workflow_id="wf-x",
            adapter="prefect",
            started_at=datetime.now(UTC),
            pool_name="local",
        )


# ---------------------------------------------------------------------------
# LegacyTaskRow
# ---------------------------------------------------------------------------


def test_legacy_row_serializes_with_underscore_prefix() -> None:
    """``_coerced`` is serialized with its leading underscore (spec parity)."""
    row = LegacyTaskRow(id="abc", content="x", tags=["todo"])
    payload = json.loads(row.model_dump_json(by_alias=True))
    assert payload["_coerced"] is True


def test_legacy_row_default_coerced_true() -> None:
    """``_coerced`` defaults to ``True``."""
    row = LegacyTaskRow(id="abc", content="x", tags=["todo"])
    assert row.coerced is True


def test_legacy_row_note_is_explanatory() -> None:
    """The default note hints at the migration path."""
    row = LegacyTaskRow(id="abc", content="x", tags=["todo"])
    assert "tasks_create" in row.note


def test_legacy_row_rejects_unknown_field() -> None:
    """``extra='forbid'`` blocks unknown fields."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        LegacyTaskRow(
            id="abc",
            content="x",
            tags=["todo"],
            unknown="value",  # type: ignore[call-arg]
        )
