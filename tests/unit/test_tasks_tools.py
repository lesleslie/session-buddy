"""Unit tests for ``session_buddy.mcp.tools.tasks_tools``.

Per the Task 4 brief, these tests pin the ``tasks_create`` tool:

- Caller-supplied ``owner`` is silently overwritten with the server-derived
  caller identity (the security-critical invariant called out in spec
  §Authz Model — owner is *not* caller-controlled).
- Tags must include the ``"task"`` discriminator; otherwise Pydantic
  raises ``ValidationError`` when the ``Task`` is constructed.
- Content above the 4096-byte cap is rejected.
- ``TaskCreatedPayload`` is published via ``publish_task_event`` with
  ``task_id``, ``owner``, ``actor``, ``created_at``, ``content_hash``.
- Over-quota rate-limit returns the canonical error envelope
  ``{"status": "error", "error_code": "rate_limited", ...}`` instead of
  propagating ``RateLimitError``.
- The task is persisted via ``store_reflection`` with ``kind=task`` in
  ``metadata`` and the task tags echoed back.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from session_buddy.mcp.tools.tasks_events import TaskCreatedPayload
from session_buddy.mcp.tools.tasks_models import (
    TASK_ID_PATTERN,
    Task,
)
from session_buddy.mcp.tools.tasks_security import (
    MAX_CONTENT_BYTES,
    RateLimiter,
)


def _make_ctx(auth: dict[str, str]) -> Any:
    """Build a stub ``Context``-like object whose ``request_state`` exposes ``auth``.

    ``derive_caller_identity`` only reads ``mcp_context["auth"]``; the
    task tool extracts that from ``ctx.request_state`` so tests can pass
    a plain mapping without standing up a full FastMCP server.
    """
    ctx = MagicMock()
    ctx.request_state = {"auth": auth}
    return ctx


# Per brief: "Caller does NOT supply owner — server sets from caller
# identity. Assert: returned Task.owner == 'user:les@example.com'".
@pytest.mark.asyncio
async def test_tasks_create_returns_task_with_server_derived_owner() -> None:
    from session_buddy.mcp.tools import tasks_tools

    # Fresh limiter per test so prior callers don't leak into this one.
    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=AsyncMock(return_value=True)),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
    ):
        result = await tasks_tools.tasks_create(
            ctx,
            content="Refactor the auth handler",
            tags=["task", "refactor"],
        )

    assert isinstance(result, Task), f"Expected Task, got {type(result).__name__}: {result!r}"
    assert result.owner == "user:les@example.com"
    assert result.created_by == "user:les@example.com"
    assert result.id.startswith("t-")
    assert len(result.id) == len("t-") + 32
    assert re.match(TASK_ID_PATTERN, result.id), f"id {result.id!r} does not match TASK_ID_PATTERN"
    assert "task" in result.tags


# Per brief: caller-supplied owner is silently overwritten.
@pytest.mark.asyncio
async def test_tasks_create_overwrites_caller_supplied_owner() -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=AsyncMock(return_value=True)),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
    ):
        result = await tasks_tools.tasks_create(
            ctx,
            content="Refactor the auth handler",
            tags=["task", "refactor"],
            owner="agent:victim",  # attempt to spoof
        )

    assert isinstance(result, Task)
    assert result.owner == "user:les@example.com", (
        f"owner must be server-derived, got {result.owner!r}"
    )
    assert result.created_by == "user:les@example.com"


# Per brief: caller supplies tags=["refactor"] without "task" → ValidationError.
@pytest.mark.asyncio
async def test_tasks_create_rejects_missing_tags_discriminator() -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=AsyncMock(return_value=True)),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        pytest.raises(ValidationError) as excinfo,
    ):
        await tasks_tools.tasks_create(
            ctx,
            content="Refactor the auth handler",
            tags=["refactor"],  # missing "task" discriminator
        )
    assert "task" in str(excinfo.value).lower()


# Per brief: content > MAX_CONTENT_BYTES (4096) → ValidationError.
@pytest.mark.asyncio
async def test_tasks_create_rejects_oversize_content() -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    oversize = "x" * (MAX_CONTENT_BYTES + 1)
    with (
        patch.object(tasks_tools, "store_reflection", new=AsyncMock(return_value=True)),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        pytest.raises(ValidationError),
    ):
        await tasks_tools.tasks_create(
            ctx,
            content=oversize,
            tags=["task"],
        )


# Per brief: TaskCreatedPayload published with correct fields.
@pytest.mark.asyncio
async def test_tasks_create_emits_task_created_event() -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    publish_mock = AsyncMock()
    with (
        patch.object(tasks_tools, "store_reflection", new=AsyncMock(return_value=True)),
        patch.object(tasks_tools, "publish_task_event", new=publish_mock),
    ):
        result = await tasks_tools.tasks_create(
            ctx,
            content="Refactor the auth handler",
            tags=["task", "refactor"],
        )

    publish_mock.assert_awaited_once()
    call_args = publish_mock.await_args
    # Publish called as publish_task_event(event_type, payload).
    assert call_args is not None
    args, _ = call_args
    event_type, payload = args[0], args[1]
    assert event_type == "task.created"
    assert isinstance(payload, TaskCreatedPayload)
    assert payload.task_id == result.id
    assert payload.owner == "user:les@example.com"
    assert payload.actor == "user:les@example.com"
    expected_hash = hashlib.sha256(b"Refactor the auth handler").hexdigest()
    assert payload.content_hash == expected_hash


# Per brief: over 60/min returns the rate-limited envelope.
@pytest.mark.asyncio
async def test_tasks_create_rate_limited_returns_envelope() -> None:
    from session_buddy.mcp.tools import tasks_tools

    # 1-request limiter so the second call blows past quota.
    tasks_tools._create_rate_limiter = RateLimiter(limit=1, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=AsyncMock(return_value=True)),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
    ):
        first = await tasks_tools.tasks_create(
            ctx,
            content="first",
            tags=["task"],
        )
        assert isinstance(first, Task), f"first call should succeed; got {first!r}"

        second = await tasks_tools.tasks_create(
            ctx,
            content="second",
            tags=["task"],
        )

    # Rate-limited response is the canonical error envelope, NOT a Task.
    assert isinstance(second, dict), f"Expected error envelope dict, got {type(second).__name__}"
    assert second.get("status") == "error"
    assert second.get("error_code") == "rate_limited"
    assert "message" in second
    details = second.get("details", {})
    assert details.get("caller") == "user:les@example.com"


# Per brief: store_reflection called with content, metadata={kind=task, ...}, tags.
@pytest.mark.asyncio
async def test_tasks_create_persists_via_store_reflection() -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    store_mock = AsyncMock(return_value=True)
    with (
        patch.object(tasks_tools, "store_reflection", new=store_mock),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
    ):
        await tasks_tools.tasks_create(
            ctx,
            content="Refactor the auth handler",
            tags=["task", "refactor"],
        )

    store_mock.assert_awaited_once()
    _args, kwargs = store_mock.await_args
    # Signature: store_reflection(content, metadata=..., tags=...)
    assert kwargs["content"] == "Refactor the auth handler"
    assert kwargs["tags"] == ["task", "refactor"]
    meta = kwargs["metadata"]
    assert meta["kind"] == "task"
    assert meta["owner"] == "user:les@example.com"
    # uuid_alias is the compact 12-hex display form (task.id[2:14]).
    assert len(meta["uuid_alias"]) == 12
    assert meta["priority"] == "normal"
    assert meta["effort"] is None
    assert meta["due_at"] is None
    assert meta["parent_task_id"] is None
    assert meta["workflow_id"] is None


# Defensive: limiter is module-scoped and persists across calls; we reset
# it in every test above. This test pins the reset behavior so a future
# refactor doesn't accidentally introduce cross-test contamination.
def test_module_rate_limiter_is_singleton() -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=42, window_seconds=42)
    a = tasks_tools._get_create_limiter()
    b = tasks_tools._get_create_limiter()
    assert a is b
    assert a.limit == 42
    assert a.window_seconds == 42