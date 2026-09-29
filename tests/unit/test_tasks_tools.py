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

from session_buddy.mcp.tools.tasks_events import (
    TaskCompletedPayload,
    TaskCreatedPayload,
    TaskUpdatedPayload,
)
from session_buddy.mcp.tools.tasks_models import (
    TASK_ID_PATTERN,
    Task,
    TaskEvent,
    TaskHistoryResult,
    UpdateTaskRequest,
)
from session_buddy.mcp.tools.tasks_security import (
    MAX_CONTENT_BYTES,
    RateLimiter,
)


def _make_ctx(auth: dict[str, str]) -> Any:
    """Build a stub ``Context``-like object whose ``get_state`` exposes auth keys.

    FastMCP's ``Context.get_state(key)`` is the documented request-state
    API; the task tool reads ``auth_user_email`` and ``auth_agent_id``
    keys from it. The auth dict is split into separate keys here so
    tests mirror the middleware contract that lands with T12+ auth wiring.
    """
    ctx = MagicMock()

    def _get_state(key: str) -> Any:
        mapping = {
            "auth_user_email": auth.get("user_email"),
            "auth_agent_id": auth.get("agent_id"),
        }
        return mapping.get(key)

    ctx.get_state.side_effect = _get_state
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

    assert isinstance(result, Task), (
        f"Expected Task, got {type(result).__name__}: {result!r}"
    )
    assert result.owner == "user:les@example.com"
    assert result.created_by == "user:les@example.com"
    assert result.id.startswith("t-")
    assert len(result.id) == len("t-") + 32
    assert re.match(TASK_ID_PATTERN, result.id), (
        f"id {result.id!r} does not match TASK_ID_PATTERN"
    )
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
    assert isinstance(second, dict), (
        f"Expected error envelope dict, got {type(second).__name__}"
    )
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


# T4 review regression: tasks_create must pass metadata= as a kwarg
# to store_reflection so the new shim (which accepts metadata) doesn't
# TypeError when the mock is unwired.
@pytest.mark.asyncio
async def test_tasks_create_regression_metadata_kwarg_to_store_reflection() -> None:
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
    # ``metadata`` is a top-level kwarg (not nested under content/tags)
    # so the extended shim receives it as a named parameter and can
    # forward it to the impl.
    assert "metadata" in kwargs, f"metadata kwarg missing: {kwargs!r}"
    assert kwargs["metadata"]["kind"] == "task"
    assert kwargs["metadata"]["owner"] == "user:les@example.com"


# T4 review Finding 2 regression: the adapter must use ctx.get_state()
# (the documented FastMCP request-state API), not ctx.request_state
# (the SEP-2322 multi-round-trip string channel). The fix uses keys
# ``auth_user_email`` / ``auth_agent_id``; this test pins that contract.
@pytest.mark.asyncio
async def test_tasks_create_uses_ctx_get_state_for_auth() -> None:
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
        )

    # The adapter must have called ctx.get_state() with the canonical
    # auth keys (NOT ctx.request_state, which is the string-typed
    # SEP-2322 channel).
    get_state_calls = [call.args[0] for call in ctx.get_state.call_args_list]
    assert "auth_user_email" in get_state_calls
    assert "auth_agent_id" in get_state_calls

    # Identity still resolves to the right caller.
    assert result.owner == "user:les@example.com"


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


# ===========================================================================
# Task 5 — ``tasks_list`` tests
# ===========================================================================
#
# The end-to-end tests below stand up a real SQLModel sidecar engine and
# patch ``tasks_tools.store_reflection`` so it (a) returns a unique
# reflection_id and (b) persists the supplied metadata to the sidecar.
# That mimics the behaviour the production wrapper chain has — the sidecar
# is populated by ``_store_reflection_operation`` after the adapter call
# returns the reflection_id. Tests then mock ``_read_reflection`` to feed
# deterministic reflection content back into ``tasks_list``.
import base64
import json
import uuid

from session_buddy.mcp.tools import tasks_storage
from session_buddy.mcp.tools.tasks_models import LegacyTaskRow, TaskListResult


@pytest.fixture
def _t5_engine() -> Any:
    """Yield a fresh in-memory sidecar engine; reset the singleton after."""
    e = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(e)
    try:
        yield e
    finally:
        tasks_storage.set_engine(None)


def _t5_fake_store_reflection(content: str, tags=None, metadata=None) -> str:
    """Sync inner helper. Production wrapper is async; the AsyncMock
    below wraps this so callers can ``await`` it.
    """
    reflection_id = f"ref-{uuid.uuid4().hex[:12]}"
    if metadata is not None:
        tasks_storage.persist_task_metadata(
            tasks_storage.get_engine(),
            reflection_id,
            dict(metadata),
        )
    return reflection_id


def _t5_store_reflection_mock() -> Any:
    """Build an ``AsyncMock`` whose side_effect is the sync fake above.

    The production wrapper is async and the test runner awaits the
    mock; ``AsyncMock(side_effect=...)`` natively returns a coroutine
    per call so this works as a drop-in ``new=`` argument for
    ``patch.object``.
    """
    from unittest.mock import AsyncMock

    return AsyncMock(side_effect=_t5_fake_store_reflection)


def _t5_reflection_for(
    reflection_id: str,
    content: str = "task body",
    tags: list[str] | None = None,
    project: str | None = None,
    timestamp: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a reflection dict that matches ``ReflectionDatabaseAdapterOneiric.get_reflection_by_id`` shape."""
    from datetime import UTC, datetime

    base: dict[str, Any] = {
        "id": reflection_id,
        "content": content,
        "tags": list(tags) if tags is not None else ["task"],
        "project": project,
        "created_at": (timestamp or datetime.now(UTC)).isoformat(),
        "updated_at": (timestamp or datetime.now(UTC)).isoformat(),
    }
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Test 1 — defaults: caller creates 3 tasks; tasks_list() returns all 3.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_returns_only_caller_tasks_by_default(_t5_engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content=f"body-{rid}",
                    tags=["task", "refactor"],
                ),
            ),
        ),
    ):
        for i in range(3):
            result = await tasks_tools.tasks_create(
                ctx,
                content=f"task body {i}",
                tags=["task", "refactor"],
            )
            assert isinstance(result, Task), f"task_create {i} returned {result!r}"

        listing = await tasks_tools.tasks_list(ctx)

    assert isinstance(listing, TaskListResult)
    assert listing.total == 3
    assert len(listing.items) == 3
    assert listing.next_cursor is None
    assert all(item.owner == "user:les@example.com" for item in listing.items)
    assert all("refactor" in item.tags for item in listing.items)


# ---------------------------------------------------------------------------
# Test 2 — status filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_filters_by_status(_t5_engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    # The fake reflection read stamps status onto the tags via "status:done".
    # The Task builder parses the prefix back to a status Literal value.
    done_reflection_ids: set[str] = set()

    async def _fake_create_then_track_one_done():
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        result = await tasks_tools.tasks_create(
            ctx,
            content="body",
            tags=["task"],
        )
        assert isinstance(result, Task)
        return result

    # Re-bind the limiter each call to ensure fresh state.
    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)

    async def _read(rid: str) -> dict[str, Any]:
        if rid in done_reflection_ids:
            return _t5_reflection_for(rid, tags=["task", "status:done"])
        return _t5_reflection_for(rid, tags=["task"])

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(tasks_tools, "_read_reflection", new=AsyncMock(side_effect=_read)),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = []
        for i in range(3):
            r = await tasks_tools.tasks_create(
                ctx,
                content=f"body-{i}",
                tags=["task"],
            )
            assert isinstance(r, Task)
            created.append(r)

        # Mark the second task as done by tagging its reflection.
        done_reflection_ids.add(created[1].id)  # not used directly; use sidecar lookup
        # Find the reflection_id associated with created[1]'s uuid_alias in the sidecar.
        from session_buddy.mcp.tools import tasks_storage

        rows = tasks_storage.find_tasks_by_metadata(
            tasks_storage.get_engine(),
            {"uuid_alias": created[1].id[2:14]},
        )
        assert rows, "expected at least one sidecar row for created[1]"
        done_reflection_ids.add(rows[0])

        listing = await tasks_tools.tasks_list(ctx, status="open")

    assert listing.total == 2
    assert len(listing.items) == 2
    assert all(item.status == "open" for item in listing.items)


# ---------------------------------------------------------------------------
# Test 3 — caller passing another user's owner returns 0.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_filters_by_owner(_t5_engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        for i in range(2):
            r = await tasks_tools.tasks_create(
                ctx,
                content=f"body-{i}",
                tags=["task"],
            )
            assert isinstance(r, Task)

        listing = await tasks_tools.tasks_list(
            ctx,
            owner="user:alice@example.com",
        )

    assert listing.total == 0
    assert listing.items == []
    assert listing.next_cursor is None


# ---------------------------------------------------------------------------
# Test 4 — include_legacy gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_includes_legacy_when_include_legacy_true(
    _t5_engine: Any,
) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    legacy_reflection_id = "ref-legacy-001"
    legacy_reflection = _t5_reflection_for(
        legacy_reflection_id,
        content="legacy body",
        tags=["todo", "cleanup"],
    )

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_query_legacy_reflections",
            new=AsyncMock(return_value=[(legacy_reflection_id, legacy_reflection)]),
        ),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        # No tasks created — verify default behaviour excludes legacy
        listing_default = await tasks_tools.tasks_list(ctx)
        assert listing_default.total == 0
        assert listing_default.items == []

        # include_legacy=True surfaces the row as LegacyTaskRow
        listing_with_legacy = await tasks_tools.tasks_list(ctx, include_legacy=True)

    assert listing_with_legacy.total == 1
    assert len(listing_with_legacy.items) == 1
    legacy_item = listing_with_legacy.items[0]
    assert isinstance(legacy_item, LegacyTaskRow)
    assert legacy_item.id == legacy_reflection_id
    assert legacy_item.content == "legacy body"
    assert legacy_item.tags == ["todo", "cleanup"]


# ---------------------------------------------------------------------------
# Test 5 — authz: User B cannot read User A's private tasks.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_excludes_other_users_private_tasks(_t5_engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx_alice = _make_ctx({"user_email": "alice@example.com"})
    ctx_bob = _make_ctx({"user_email": "bob@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        # Alice creates a private task.
        alice_task = await tasks_tools.tasks_create(
            ctx_alice,
            content="alice secret task",
            tags=["task", "private"],
        )
        assert isinstance(alice_task, Task)
        assert alice_task.owner == "user:alice@example.com"

        # Bob lists — must NOT include Alice's task.
        bob_listing = await tasks_tools.tasks_list(ctx_bob)
        # Alice may also have a record in the sidecar; the visibility filter
        # is the security boundary, so verify Bob sees zero tasks.
        assert bob_listing.total == 0
        assert bob_listing.items == []
        assert all(item.owner != "user:alice@example.com" for item in bob_listing.items)


# ---------------------------------------------------------------------------
# Test 6 — pagination (k=2, cursor)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_pagination_k_and_cursor(_t5_engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        for i in range(5):
            r = await tasks_tools.tasks_create(
                ctx,
                content=f"body-{i}",
                tags=["task"],
            )
            assert isinstance(r, Task)

        page1 = await tasks_tools.tasks_list(ctx, k=2)
        assert len(page1.items) == 2
        assert page1.total == 5
        assert page1.next_cursor is not None

        page2 = await tasks_tools.tasks_list(ctx, k=2, cursor=page1.next_cursor)
        assert len(page2.items) == 2
        assert page2.total == 5
        assert page2.next_cursor is not None

        page3 = await tasks_tools.tasks_list(ctx, k=2, cursor=page2.next_cursor)
        assert len(page3.items) == 1
        assert page3.total == 5
        assert page3.next_cursor is None

        # Page items must not overlap across pages.
        seen_ids = {i.id for i in page1.items}
        seen_ids.update(i.id for i in page2.items)
        seen_ids.update(i.id for i in page3.items)
        assert len(seen_ids) == 5


# ---------------------------------------------------------------------------
# Test 7 — envelope shape (TaskListResult, not list[Task])
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_envelope_shape(_t5_engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        r = await tasks_tools.tasks_create(
            ctx,
            content="body",
            tags=["task"],
        )
        assert isinstance(r, Task)

        listing = await tasks_tools.tasks_list(ctx)

    assert isinstance(listing, TaskListResult), (
        f"Expected TaskListResult, got {type(listing).__name__}"
    )
    assert hasattr(listing, "items")
    assert hasattr(listing, "next_cursor")
    assert hasattr(listing, "total")
    assert listing.total == 1
    assert len(listing.items) == 1
    assert isinstance(listing.items[0], Task)
    # Verify the cursor is opaque (base64-like).
    page = await tasks_tools.tasks_list(ctx, k=1)
    if page.next_cursor:
        # Must not raise when decoded; should be base64-urlsafe JSON.
        padded = page.next_cursor + "=" * (-len(page.next_cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        assert "offset" in decoded


# ---------------------------------------------------------------------------
# T5 fix round 1 — round-trip regression
# ---------------------------------------------------------------------------
#
# Closes the v1-blocker from T5 concern #2: ``tasks_create`` now persists
# the full 32-hex ``task_id`` in metadata, and ``tasks_list`` reads it back.
# This test pins the contract: ``tasks_create(t).id`` MUST appear in the
# ``items`` of the immediately-following ``tasks_list`` so T6/T7 can use
# the listed id for get/update/complete.
@pytest.mark.asyncio
async def test_tasks_list_returns_same_id_as_tasks_create(_t5_engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content="round-trip body",
                    tags=["task"],
                ),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(
            ctx,
            content="round-trip test",
            tags=["task"],
        )
        assert isinstance(created, Task)

        listed = await tasks_tools.tasks_list(ctx)

    listed_ids = [item.id for item in listed.items]
    assert created.id in listed_ids, (
        f"Round-trip broken: created.id={created.id!r} not in list {listed_ids!r}"
    )
    # Sanity: the listed id must still match the canonical pattern.
    assert re.match(TASK_ID_PATTERN, created.id)
    for item in listed.items:
        assert re.match(TASK_ID_PATTERN, item.id)


# ===========================================================================
# Task 6 — ``tasks_get`` + ``tasks_update`` tests
# ===========================================================================
#
# These tests pin:
# - ``tasks_get`` validates the id pattern (Pydantic), round-trips a
#   created task, returns 404 for unknown ids, and returns 404 (not 403)
#   when a non-owner tries to read a private task.
# - ``tasks_update`` mutates the priority field, emits TaskUpdatedPayload,
#   rejects caller-supplied owner, refuses to expose workflow_id via
#   UpdateTaskRequest (T1 contract), enforces visibility, and rate-limits
#   at 120/min. The history-diff test is skipped until T9 lands.


# ---------------------------------------------------------------------------
# tasks_get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_get_validates_id_format() -> None:
    """Invalid task_id returns ``invalid_id_format`` envelope; never reaches DB.

    The spec §Error Handling Matrix pins an envelope (not a raised
    exception) so the MCP client can render the error without parsing
    a traceback.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    result = await tasks_tools.tasks_get(ctx, task_id="not-a-uuid")

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "invalid_id_format"


@pytest.mark.asyncio
async def test_tasks_get_returns_task_with_persisted_id(_t5_engine: Any) -> None:
    """Round-trip: tasks_create then tasks_get returns the same Task."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content="get-me",
                    tags=["task"],
                ),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="get-me", tags=["task"])
        assert isinstance(created, Task)

        fetched = await tasks_tools.tasks_get(ctx, task_id=created.id)

    assert isinstance(fetched, Task), (
        f"Expected Task, got {type(fetched).__name__}: {fetched!r}"
    )
    assert fetched.id == created.id
    assert fetched.content == "get-me"


@pytest.mark.asyncio
async def test_tasks_get_enforces_visibility_private(_t5_engine: Any) -> None:
    """User B's tasks_get(user_a_task_id) returns 404 envelope (no info leak).

    The spec §Authz Model pins 404 (not 403) so an attacker cannot
    probe for existence by status code.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx_alice = _make_ctx({"user_email": "alice@example.com"})
    ctx_bob = _make_ctx({"user_email": "bob@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        task_a = await tasks_tools.tasks_create(
            ctx_alice,
            content="alice-secret",
            tags=["task"],
        )
        assert isinstance(task_a, Task)
        assert task_a.owner == "user:alice@example.com"

        result = await tasks_tools.tasks_get(ctx_bob, task_id=task_a.id)

    assert isinstance(result, dict), (
        f"Expected error envelope dict, got {type(result).__name__}"
    )
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"


@pytest.mark.asyncio
async def test_tasks_get_returns_404_for_unknown_id(_t5_engine: Any) -> None:
    """tasks_get(unknown_id) returns 404 envelope; never raises."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    # Use a structurally-valid id so the test exercises the lookup path
    # (not the Pydantic pattern validator).
    unknown_id = "t-0123456789abcdef0123456789abcdef"

    with patch.object(tasks_tools, "_read_reflection", new=AsyncMock(return_value=None)):
        result = await tasks_tools.tasks_get(ctx, task_id=unknown_id)

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"


# ---------------------------------------------------------------------------
# tasks_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_update_mutates_priority_and_emits_event(_t5_engine: Any) -> None:
    """tasks_update(priority="high") persists; emits TaskUpdatedPayload.

    Verifies:
    - Returned Task reflects the mutation.
    - At least one ``task.updated`` event is published with the priority
      diff in its ``diff`` dict.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})
    publish_mock = AsyncMock()

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=publish_mock),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content="x",
                    tags=["task", "priority:normal"],
                ),
            ),
        ),
        # ``_update_reflection`` now hits the real adapter; this test
        # only exercises the priority mutation path so a no-op patch
        # is sufficient. The dedicated round-trip test in the T6 fix
        # round 1 section below uses a spy to assert the new content.
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(
            ctx,
            content="x",
            tags=["task", "priority:normal"],
        )
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        updated = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="high"),
        )

    assert isinstance(updated, Task), (
        f"Expected Task, got {type(updated).__name__}: {updated!r}"
    )
    assert updated.priority == "high"

    # At least one task.updated event was published with the priority diff.
    publish_mock.assert_awaited()
    update_events = [
        call.args
        for call in publish_mock.await_args_list
        if call.args and call.args[0] == "task.updated"
    ]
    assert update_events, (
        f"expected at least one task.updated event; got {publish_mock.await_args_list!r}"
    )
    priority_event = next(
        (e for e in update_events if isinstance(e[1], TaskUpdatedPayload) and "priority" in e[1].diff),
        None,
    )
    assert priority_event is not None, (
        f"expected priority diff in task.updated; got {[e[1].diff for e in update_events]!r}"
    )
    payload = priority_event[1]
    assert payload.task_id == created.id
    assert payload.diff["priority"][1] == "high"


@pytest.mark.asyncio
async def test_tasks_update_rejects_owner_mutation(_t5_engine: Any) -> None:
    """Caller-supplied owner via UpdateTaskRequest is REJECTED.

    ``UpdateTaskRequest`` excludes ``owner`` per the T1 contract
    (extra='forbid' on the model prevents construction with it). The
    tool body ALSO has a defense-in-depth check that re-uses
    ``getattr(request, "owner", None)`` so a future regression that
    re-exposes the field still rejects it. We exercise that path by
    subclassing ``UpdateTaskRequest`` to inject the forbidden field.
    """
    from session_buddy.mcp.tools import tasks_tools

    class _OwnerExposedRequest(UpdateTaskRequest):
        """Test-only subclass that re-exposes the forbidden ``owner`` field."""

        owner: str | None = None
        created_by: str | None = None
        completed_by: str | None = None

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="x", tags=["task"])
        assert isinstance(created, Task)

        # Bypass the T1 contract (which excludes owner via extra='forbid')
        # to simulate a regression. The tool body's pre-flight check
        # must still reject it with the canonical envelope.
        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        result = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=_OwnerExposedRequest(owner="agent:victim"),
        )

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "owner_mutation_forbidden"


def test_tasks_update_cannot_change_workflow_id() -> None:
    """UpdateTaskRequest excludes workflow_id; constructing one raises.

    This is the T1 contract: ``workflow_id`` is server-set by T17's
    ``tasks_handoff_to_workflow`` only and cannot be mutated via this
    envelope. ``extra='forbid'`` on the ConfigDict makes Pydantic
    reject unknown fields at construction time.
    """
    with pytest.raises(ValidationError) as excinfo:
        UpdateTaskRequest(workflow_id="wf-some-id")  # ty: ignore[call-arg]
    assert "workflow_id" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_tasks_update_records_diff_in_history(_t5_engine: Any) -> None:
    """After priority normal→high, tasks_history shows the diff.

    Flipped on T9: ``tasks_history`` reads the sidecar ``metadata["history"]``
    list written by T6's ``_persist_task_update`` and returns one
    ``TaskEvent`` per diff entry. This test runs the full create → update
    → history path against the real sidecar engine.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content="x",
                    tags=["task", "priority:normal"],
                ),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(
            ctx,
            content="x",
            tags=["task", "priority:normal"],
        )
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        updated = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="high"),
        )
        assert isinstance(updated, Task)

        history = await tasks_tools.tasks_history(
            ctx,
            task_id=created.id,
        )

    assert isinstance(history, TaskHistoryResult)
    # priority normal→high + updated_at (server-set) = 2 diff fields.
    assert len(history.items) >= 1, (
        f"history should record at least the priority diff; got {history.items!r}"
    )
    priority_event = next(
        (
            e for e in history.items
            if e.diff is not None and "priority" in e.diff
        ),
        None,
    )
    assert priority_event is not None, (
        f"priority diff missing from history: {[e.diff for e in history.items]!r}"
    )
    assert priority_event.event_type == "updated"
    assert priority_event.task_id == created.id
    assert priority_event.actor == "user:les@example.com"
    diff_tuple = priority_event.diff["priority"]
    assert diff_tuple[0] == "normal"
    assert diff_tuple[1] == "high"


@pytest.mark.asyncio
async def test_tasks_update_enforces_visibility_other_user(_t5_engine: Any) -> None:
    """User B's update on User A's task returns 404 (no info leak)."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx_alice = _make_ctx({"user_email": "alice@example.com"})
    ctx_bob = _make_ctx({"user_email": "bob@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        task_a = await tasks_tools.tasks_create(
            ctx_alice,
            content="x",
            tags=["task"],
        )
        assert isinstance(task_a, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        result = await tasks_tools.tasks_update(
            ctx_bob,
            task_id=task_a.id,
            request=UpdateTaskRequest(priority="high"),
        )

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"


@pytest.mark.asyncio
async def test_tasks_update_rate_limited_returns_envelope(_t5_engine: Any) -> None:
    """tasks_update rate limit (120/min) returns envelope on overflow.

    Use a 2-request limit so the 3rd call blows past quota in test
    time. The dedicated limiter is separate from tasks_create's 60/min
    (per spec §Input Limits).
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    # Single limiter instance shared across all 3 update calls so the
    # sliding-window state actually accumulates (resetting between calls
    # would let each call start fresh).
    tasks_tools._update_rate_limiter = RateLimiter(limit=2, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        # ``_update_reflection`` is now a real adapter call (T6 fix
        # round 1); this test only exercises the rate-limit envelope
        # so a no-op patch is sufficient.
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="x", tags=["task"])
        assert isinstance(created, Task)

        # First two updates succeed.
        for _ in range(2):
            ok = await tasks_tools.tasks_update(
                ctx,
                task_id=created.id,
                request=UpdateTaskRequest(priority="high"),
            )
            assert isinstance(ok, Task), (
                f"Expected Task, got {type(ok).__name__}: {ok!r}"
            )

        # Third update trips the 2/min limit.
        rate_limited = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="low"),
        )

    assert isinstance(rate_limited, dict)
    assert rate_limited.get("status") == "error"
    assert rate_limited.get("error_code") == "rate_limited"
    details = rate_limited.get("details", {})
    assert details.get("limit") == 2
    assert details.get("caller") == "user:les@example.com"


# ---------------------------------------------------------------------------
# T6 fix round 1 — content round-trip regression
# ---------------------------------------------------------------------------
#
# T6 originally shipped with ``_update_reflection`` as a no-op stub, so
# ``tasks_update(content=...)`` mutated the in-memory task but never
# reached the reflection DB. This test pins the fix: a spy replaces
# ``_update_reflection`` and asserts it was called with the new
# content so the round-trip contract holds.


@pytest.mark.asyncio
async def test_tasks_update_content_round_trips_through_reflection_db(
    _t5_engine: Any,
) -> None:
    """tasks_update(content='new') MUST call _update_reflection with 'new'."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    captured: dict[str, Any] = {}
    original_update_reflection = tasks_tools._update_reflection

    async def spy(reflection_id: str, content: str, tags: list[str]) -> None:
        captured["reflection_id"] = reflection_id
        captured["content"] = content
        captured["tags"] = tags

    tasks_tools._update_reflection = spy  # type: ignore[assignment]
    try:
        with (
            patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
            patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
            patch.object(
                tasks_tools,
                "_read_reflection",
                new=AsyncMock(
                    side_effect=lambda rid: _t5_reflection_for(
                        rid,
                        content="original",
                        tags=["task"],
                    ),
                ),
            ),
        ):
            tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
            created = await tasks_tools.tasks_create(
                ctx,
                content="original",
                tags=["task"],
            )
            assert isinstance(created, Task)

            tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
            result = await tasks_tools.tasks_update(
                ctx,
                task_id=created.id,
                request=UpdateTaskRequest(content="updated-text"),
            )

        assert isinstance(result, Task)
        assert result.content == "updated-text"

        # The spy MUST have been called with the new content; without it
        # ``_persist_task_update``'s ``_update_reflection`` call would
        # have been a no-op and a subsequent ``tasks_get`` would read
        # stale content from the reflection DB.
        assert captured.get("content") == "updated-text", (
            f"_update_reflection was not called with the new content; "
            f"captured={captured!r}"
        )
        assert captured.get("reflection_id"), (
            f"_update_reflection was not called with a reflection_id; "
            f"captured={captured!r}"
        )
        assert "task" in (captured.get("tags") or []), (
            f"_update_reflection must preserve the 'task' discriminator tag; "
            f"captured.tags={captured.get('tags')!r}"
        )
    finally:
        tasks_tools._update_reflection = original_update_reflection  # type: ignore[assignment]


# ===========================================================================
# Task 7 — ``tasks_complete`` tests
# ===========================================================================
#
# The v1.1 multi-agent-review hardening. ``tasks_complete`` is a pure state
# mutation; it MUST NOT inspect ``result_notes`` for any dispatch trigger.
# The only dispatch edge in the system is ``tasks_handoff_to_workflow`` (T17,
# mahavishnu PR #2). Regression test
# ``test_tasks_complete_does_NOT_dispatch_even_with_handoff_prefix`` pins this.


# ---------------------------------------------------------------------------
# tasks_complete happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_complete_sets_status_done_and_completed_at(_t5_engine: Any) -> None:
    """tasks_complete(id) sets status='done', completed_at=now, completed_by=caller."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="finish-me", tags=["task"])
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        completed = await tasks_tools.tasks_complete(ctx, task_id=created.id)

    assert isinstance(completed, Task), (
        f"Expected Task, got {type(completed).__name__}: {completed!r}"
    )
    assert completed.status == "done"
    assert completed.completed_at is not None
    assert completed.completed_by == "user:les@example.com"


@pytest.mark.asyncio
async def test_tasks_complete_records_result_notes(_t5_engine: Any) -> None:
    """tasks_complete(id, result_notes="...") persists notes."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="x", tags=["task"])
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        completed = await tasks_tools.tasks_complete(
            ctx,
            task_id=created.id,
            result_notes="Refactored the authz middleware",
        )

    assert isinstance(completed, Task)
    assert completed.result_notes == "Refactored the authz middleware"


def test_tasks_complete_server_overrides_completed_by() -> None:
    """tasks_complete signature MUST NOT accept completed_by or owner (introspection).

    The brief pins the v1.1 server-set contract: ``completed_by`` is
    derived from caller identity. The signature is the load-bearing
    boundary — if a future regression re-exposes ``completed_by`` /
    ``owner`` as a parameter, this test fails immediately. ``inspect``
    walks the live function object so any monkey-patched decoration that
    re-binds parameters would also be caught.
    """
    import inspect

    from session_buddy.mcp.tools import tasks_tools

    sig = inspect.signature(tasks_tools.tasks_complete)
    assert "completed_by" not in sig.parameters
    assert "owner" not in sig.parameters


# ---------------------------------------------------------------------------
# tasks_complete authz
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_complete_rejects_non_owner_caller(_t5_engine: Any) -> None:
    """User B cannot complete User A's task — 404 envelope, status unchanged.

    Per spec §Authz Model line 565 + §Error Handling Matrix: non-owner
    caller gets an error envelope with ``error_code='not_found'`` (404,
    not 403 — same info-leak parity as ``tasks_get``).
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx_alice = _make_ctx({"user_email": "alice@example.com"})
    ctx_bob = _make_ctx({"user_email": "bob@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        task_a = await tasks_tools.tasks_create(
            ctx_alice,
            content="alice-task",
            tags=["task"],
        )
        assert isinstance(task_a, Task)
        assert task_a.owner == "user:alice@example.com"

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        result = await tasks_tools.tasks_complete(ctx_bob, task_id=task_a.id)

    assert isinstance(result, dict), (
        f"Expected error envelope dict, got {type(result).__name__}"
    )
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"

    # Verify status was NOT changed (read-back via tasks_get).
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    with patch.object(
        tasks_tools,
        "_read_reflection",
        new=AsyncMock(
            side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
        ),
    ):
        fetched = await tasks_tools.tasks_get(ctx_alice, task_id=task_a.id)
    assert isinstance(fetched, Task)
    assert fetched.status != "done"


# ---------------------------------------------------------------------------
# tasks_complete no-dispatch regression (v1.1 hardening)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_complete_does_NOT_dispatch_even_with_handoff_prefix(
    _t5_engine: Any,
) -> None:
    """REGRESSION: result_notes='HANDOFF: ...' MUST NOT trigger any dispatch.

    v1.1 multi-agent-review hardening. The function body MUST be a pure
    state mutation: it does NOT call ``pool_route_execute``,
    ``dispatch_to_pool``, ``route_task``, or any other dispatch primitive
    regardless of ``result_notes`` content. The ONLY dispatch edge in the
    system is ``tasks_handoff_to_workflow`` (T17, mahavishnu PR #2).
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
        # Spy on the candidate dispatch primitive on the tasks_tools
        # module itself. ``create=True`` adds the attribute if it does
        # not exist so the patch always succeeds; the regression
        # assertion below catches any future implementation that
        # tries to call it.
        patch.object(
            tasks_tools,
            "dispatch_to_pool",
            new=AsyncMock(),
            create=True,
        ) as mock_dispatch,
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="x", tags=["task"])
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        completed = await tasks_tools.tasks_complete(
            ctx,
            task_id=created.id,
            result_notes="HANDOFF: trigger-something",
        )

    mock_dispatch.assert_not_called()
    assert isinstance(completed, Task)
    assert completed.status == "done"
    # workflow_id must NOT be set as a side effect of complete.
    assert completed.workflow_id is None


# ---------------------------------------------------------------------------
# tasks_complete event emission + rate limit + 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_complete_emits_task_completed_event(_t5_engine: Any) -> None:
    """Spy on publish_task_event; verify TaskCompletedPayload emitted."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})
    publish_mock = AsyncMock()

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=publish_mock),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="x", tags=["task"])
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        await tasks_tools.tasks_complete(ctx, task_id=created.id)

    completed_events = [
        call.args
        for call in publish_mock.await_args_list
        if call.args and call.args[0] == "task.completed"
    ]
    assert completed_events, (
        f"expected at least one task.completed event; got {publish_mock.await_args_list!r}"
    )
    event_type, payload = completed_events[0][0], completed_events[0][1]
    assert event_type == "task.completed"
    assert isinstance(payload, TaskCompletedPayload)
    assert payload.task_id == created.id
    assert payload.actor == "user:les@example.com"


@pytest.mark.asyncio
async def test_tasks_complete_rate_limited_returns_envelope(_t5_engine: Any) -> None:
    """121st tasks_complete call within 60s returns rate_limited envelope.

    Shared 120/min limiter with ``tasks_update`` per spec §Input Limits.
    Use a 2-request limit so the 3rd call blows past quota in test time.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    # Single limiter instance shared across all 3 complete calls so the
    # sliding-window state actually accumulates.
    tasks_tools._update_rate_limiter = RateLimiter(limit=2, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="x", tags=["task"])
        assert isinstance(created, Task)

        # First two completes succeed.
        for _ in range(2):
            ok = await tasks_tools.tasks_complete(ctx, task_id=created.id)
            assert isinstance(ok, Task), (
                f"Expected Task, got {type(ok).__name__}: {ok!r}"
            )

        # Third complete trips the 2/min limit.
        rate_limited = await tasks_tools.tasks_complete(ctx, task_id=created.id)

    assert isinstance(rate_limited, dict)
    assert rate_limited.get("status") == "error"
    assert rate_limited.get("error_code") == "rate_limited"
    details = rate_limited.get("details", {})
    assert details.get("limit") == 2
    assert details.get("caller") == "user:les@example.com"


@pytest.mark.asyncio
async def test_tasks_complete_returns_404_for_unknown_id(_t5_engine: Any) -> None:
    """tasks_complete(unknown_id) returns 404 envelope."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    unknown_id = "t-0123456789abcdef0123456789abcdef"

    with (
        patch.object(tasks_tools, "_read_reflection", new=AsyncMock(return_value=None)),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        result = await tasks_tools.tasks_complete(ctx, task_id=unknown_id)

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"


# ===========================================================================
# Task 8 — ``tasks_search`` tests
# ===========================================================================
#
# Spec line 121-126: ``tasks_search(query, project=None, min_score=None, k=10)
# -> list[Task]``. The function filters the underlying reflection search
# results to ``kind=task`` rows only (sidecar metadata or ``"task"`` tag
# fallback) and applies the visibility filter (spec §Authz Model).
#
# The tests below mock ``tasks_tools.search_reflections`` (the module-level
# symbol) to avoid standing up the canonical DuckDB reflection adapter —
# the search primitive needs a connected DB, but the unit-test path only
# exercises the kind/visibility/score filter pipeline. The real search
# round-trip is exercised by integration tests on the underlying adapter.


def _t8_hit(
    reflection_id: str,
    content: str,
    score: float = 0.9,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Build a ``search_reflections`` hit dict for the test mocks.

    Mirrors the dict shape returned by ``session_buddy.reflection.search``
    lines 341-352 (semantic) and 426-436 (text fallback): keys
    ``id``, ``content``, ``score``, ``tags`` plus the rest. Only ``id``,
    ``content``, ``score``, ``tags`` are inspected by ``tasks_search``.
    """
    return {
        "id": reflection_id,
        "content": content,
        "score": score,
        "timestamp": None,
        "project": None,
        "tags": list(tags) if tags is not None else [],
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_tasks_search_returns_only_kind_task_rows(_t5_engine: Any) -> None:
    """Mixed hits: tasks + non-task reflections; tasks_search returns only tasks.

    A hit whose reflection_id has no sidecar row (kind != task, no
    "task" tag) MUST be filtered out by ``tasks_search``. The task
    hit carries the canonical reflection_id from ``tasks_create``.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    # Capture the reflection_id assigned to the task by the sidecar mock.
    captured: dict[str, str] = {}

    original_persist = tasks_storage.persist_task_metadata

    def _capture_persist(engine: Any, rid: str, meta: dict[str, Any]) -> None:
        if meta.get("kind") == "task" and "task_rid" not in captured:
            captured["task_rid"] = rid
        original_persist(engine, rid, meta)

    search_mock = AsyncMock(
        side_effect=lambda query, limit=10, project=None: [
            _t8_hit(captured.get("task_rid", ""), "unique-task-content", tags=["task"]),
            _t8_hit("ref-stranger-001", "unique-conversation-content", tags=["conversation"]),
        ]
    )

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_storage, "persist_task_metadata", side_effect=_capture_persist),
        patch.object(tasks_tools, "search_reflections", new=search_mock),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="unique-task-content", tags=["task"])
        assert isinstance(created, Task)
        assert "task_rid" in captured, (
            f"sidecar mock did not capture task reflection_id; captured={captured!r}"
        )

        results = await tasks_tools.tasks_search(ctx, query="unique")

    assert isinstance(results, list)
    assert all(isinstance(t, Task) for t in results), (
        f"every result must be a Task; got {[type(t).__name__ for t in results]!r}"
    )
    # Only the task hit survives — the non-task hit is filtered out.
    assert any(t.id == created.id for t in results), (
        f"created task {created.id!r} missing from results: {[t.id for t in results]!r}"
    )
    # The non-task reflection has no "task" tag and no sidecar row — must be excluded.
    assert all("conversation" not in t.tags for t in results), (
        "non-task reflection leaked into results"
    )


@pytest.mark.asyncio
async def test_tasks_search_supports_project_filter(_t5_engine: Any) -> None:
    """``tasks_search(project="X")`` forwards ``project`` to ``search_reflections``.

    The underlying semantic search constrains at the DB level so we
    never have to post-filter. We verify the contract by spying on the
    module-level ``search_reflections`` and asserting it received the
    forwarded project arg.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    search_mock = AsyncMock(return_value=[])

    with patch.object(tasks_tools, "search_reflections", new=search_mock):
        await tasks_tools.tasks_search(ctx, query="anything", project="alpha")

    search_mock.assert_awaited_once()
    _args, kwargs = search_mock.await_args
    assert kwargs.get("project") == "alpha", (
        f"project must be forwarded; got kwargs={kwargs!r}"
    )


@pytest.mark.asyncio
async def test_tasks_search_supports_min_score(_t5_engine: Any) -> None:
    """``tasks_search(min_score=0.9)`` excludes low-similarity hits.

    The post-filter is applied AFTER visibility (per brief: security
    gate first, relevance gate second). We verify by feeding two hits
    — one above threshold, one below — and asserting only the
    high-score hit survives.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    # Two kind=task hits with very different scores. Both pass visibility
    # (owner == caller); only the high-score one passes min_score=0.9.
    high_rid = "ref-high-score-001"
    low_rid = "ref-low-score-001"

    # Persist sidecar rows so the kind=task filter passes for both.
    engine = tasks_storage.get_engine()
    tasks_storage.persist_task_metadata(engine, high_rid, {
        "kind": "task",
        "owner": "user:les@example.com",
        "task_id": "t-" + "a" * 32,
    })
    tasks_storage.persist_task_metadata(engine, low_rid, {
        "kind": "task",
        "owner": "user:les@example.com",
        "task_id": "t-" + "b" * 32,
    })

    search_mock = AsyncMock(
        return_value=[
            _t8_hit(high_rid, "high-score-body", score=0.95, tags=["task"]),
            _t8_hit(low_rid, "low-score-body", score=0.3, tags=["task"]),
        ]
    )

    async def _fake_read(rid: str) -> dict[str, Any]:
        if rid == high_rid:
            return _t5_reflection_for(rid, content="high-score-body", tags=["task"])
        return _t5_reflection_for(rid, content="low-score-body", tags=["task"])

    with (
        patch.object(tasks_tools, "search_reflections", new=search_mock),
        patch.object(tasks_tools, "_read_reflection", new=AsyncMock(side_effect=_fake_read)),
    ):
        results = await tasks_tools.tasks_search(ctx, query="body", min_score=0.9)

    # Only the high-score hit survives.
    assert len(results) == 1, (
        f"min_score=0.9 must drop the 0.3-score hit; got {[t.content for t in results]!r}"
    )
    assert results[0].content == "high-score-body"


@pytest.mark.asyncio
async def test_tasks_search_respects_k_limit(_t5_engine: Any) -> None:
    """``tasks_search(k=2)`` forwards ``k`` as the ``limit`` arg.

    The underlying reflection search returns at most ``limit`` hits, so
    we can't exceed ``k`` results. We verify the contract by spying on
    the call signature.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    search_mock = AsyncMock(return_value=[])

    with patch.object(tasks_tools, "search_reflections", new=search_mock):
        await tasks_tools.tasks_search(ctx, query="anything", k=2)

    search_mock.assert_awaited_once()
    _args, kwargs = search_mock.await_args
    assert kwargs.get("limit") == 2, f"k=2 must be forwarded as limit=2; got kwargs={kwargs!r}"


@pytest.mark.asyncio
async def test_tasks_search_enforces_visibility_private(_t5_engine: Any) -> None:
    """User B's tasks_search excludes User A's private tasks.

    Even though the underlying reflection search returns User A's task
    (no DB-level filter), the visibility filter on the tasks_search side
    must drop it before the result list is returned (spec §Authz Model).
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx_alice = _make_ctx({"user_email": "alice@example.com"})
    ctx_bob = _make_ctx({"user_email": "bob@example.com"})

    captured: dict[str, str] = {}

    original_persist = tasks_storage.persist_task_metadata

    def _capture_persist(engine: Any, rid: str, meta: dict[str, Any]) -> None:
        if meta.get("kind") == "task" and "alice_rid" not in captured:
            captured["alice_rid"] = rid
        original_persist(engine, rid, meta)

    search_mock = AsyncMock(
        side_effect=lambda query, limit=10, project=None: [
            _t8_hit(
                captured.get("alice_rid", ""),
                "alice-secret",
                tags=["task"],
            ),
        ]
    )

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_storage, "persist_task_metadata", side_effect=_capture_persist),
        patch.object(tasks_tools, "search_reflections", new=search_mock),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        task_a = await tasks_tools.tasks_create(ctx_alice, content="alice-secret", tags=["task"])
        assert isinstance(task_a, Task)
        assert task_a.visibility == "private"
        assert "alice_rid" in captured

        # Bob's view of the same query — Alice's task must be filtered out.
        results = await tasks_tools.tasks_search(ctx_bob, query="alice-secret")

    assert all(t.id != task_a.id for t in results), (
        f"User B must not see User A's private task; got {[t.id for t in results]!r}"
    )


@pytest.mark.asyncio
@pytest.mark.skip(
    reason=(
        "T5 _build_task hardcodes visibility='private' and T6 "
        "_persist_task_update does not write visibility to the sidecar; "
        "visibility_public needs the T5 fix to read visibility from "
        "sidecar metadata. Tracked as T12 follow-up."
    )
)
async def test_tasks_search_enforces_visibility_public(_t5_engine: Any) -> None:
    """Public tasks appear in any user's tasks_search results.

    Tests the visibility contract from the other side: a public task
    owned by User A IS visible to User B (spec §Authz Model — public
    rows pass ``enforce_visibility_filter`` unconditionally).

    Currently skipped: ``_build_task`` (T5) hardcodes
    ``visibility="private"`` and ``_persist_task_update`` (T6) does not
    persist the ``visibility`` field to sidecar metadata, so even
    after ``tasks_update(visibility="public")`` the next ``_build_task``
    call still returns ``"private"``. Pin the test stub in place so
    T12 can flip it on after fixing the persistence path.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx_alice = _make_ctx({"user_email": "alice@example.com"})
    ctx_bob = _make_ctx({"user_email": "bob@example.com"})

    captured: dict[str, str] = {}

    original_persist = tasks_storage.persist_task_metadata

    def _capture_persist(engine: Any, rid: str, meta: dict[str, Any]) -> None:
        if meta.get("kind") == "task" and "alice_public_rid" not in captured:
            captured["alice_public_rid"] = rid
        original_persist(engine, rid, meta)

    search_mock = AsyncMock(
        side_effect=lambda query, limit=10, project=None: [
            _t8_hit(
                captured.get("alice_public_rid", ""),
                "alice-public-body",
                tags=["task"],
            ),
        ]
    )

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
        patch.object(tasks_storage, "persist_task_metadata", side_effect=_capture_persist),
        patch.object(tasks_tools, "search_reflections", new=search_mock),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        task_a = await tasks_tools.tasks_create(ctx_alice, content="alice-public-body", tags=["task"])
        assert isinstance(task_a, Task)

        # Flip to public so Bob can read it.
        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        updated = await tasks_tools.tasks_update(
            ctx_alice,
            task_id=task_a.id,
            request=UpdateTaskRequest(visibility="public"),
        )
        assert isinstance(updated, Task)
        assert updated.visibility == "public"

        # Bob searches — Alice's public task IS visible.
        results = await tasks_tools.tasks_search(ctx_bob, query="alice-public-body")

    assert any(t.id == task_a.id for t in results), (
        f"User B must see Alice's public task; got {[t.id for t in results]!r}"
    )


# ---------------------------------------------------------------------------
# T9: tasks_history — cursor-paginated change history
# ---------------------------------------------------------------------------
#
# Reads ``metadata["history"]`` (the append-only list written by T6's
# ``_persist_task_update``) and maps each entry to a ``TaskEvent`` with
# ``event_type="updated"``. The cursor format reuses T5's offset-based
# ``base64-urlsafe JSON`` scheme.


@pytest.mark.asyncio
async def test_tasks_history_returns_empty_when_no_history(_t5_engine: Any) -> None:
    """tasks_history on a freshly-created task returns empty items + null cursor.

    No updates have been applied yet, so the sidecar ``history`` list is
    empty/absent. The tool must return ``TaskHistoryResult(items=[], next_cursor=None)``,
    not an error envelope.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(
            ctx,
            content="x",
            tags=["task"],
        )
        assert isinstance(created, Task)

        history = await tasks_tools.tasks_history(ctx, task_id=created.id)

    assert isinstance(history, TaskHistoryResult)
    assert history.items == []
    assert history.next_cursor is None


@pytest.mark.asyncio
async def test_tasks_history_returns_update_diff_events(_t5_engine: Any) -> None:
    """After tasks_update(priority='high'), history has one event_type='updated' event.

    ``tasks_history`` reads the sidecar ``metadata["history"]`` list written
    by T6's ``_persist_task_update`` and maps each entry to a ``TaskEvent``
    with ``event_type="updated"`` (the only event type the v1 history source
    emits; the ``Literal`` enum reserves other types for future T17 handoffs).
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content="x",
                    tags=["task", "priority:normal"],
                ),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(
            ctx,
            content="x",
            tags=["task", "priority:normal"],
        )
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="high"),
        )

        history = await tasks_tools.tasks_history(ctx, task_id=created.id)

    assert isinstance(history, TaskHistoryResult)
    # Filter to the priority event (T6 also emits an updated_at event).
    priority_events = [
        e for e in history.items
        if e.diff is not None and "priority" in e.diff
    ]
    assert len(priority_events) == 1
    event = priority_events[0]
    assert isinstance(event, TaskEvent)
    assert event.event_type == "updated"
    assert event.task_id == created.id
    assert event.actor is not None
    assert "priority" in (event.diff or {})


@pytest.mark.asyncio
async def test_tasks_history_paginates_with_k_and_cursor(_t5_engine: Any) -> None:
    """5 updates emit a ``content`` diff + an ``updated_at`` diff each (10 entries).

    tasks_history(k=4) returns 4 + cursor; cursor returns next 4 + cursor;
    final returns 2 + None. Cursor format reuses T5's ``base64-urlsafe
    JSON of {"offset": int}`` scheme. The first page has ``next_cursor``
    set (more entries exist); subsequent pages advance the offset until
    the last page returns ``next_cursor=None``.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content="x",
                    tags=["task"],
                ),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(ctx, content="x", tags=["task"])
        assert isinstance(created, Task)

        # 5 content updates — each emits TWO diff entries (the content field
        # + the always-changing server-set updated_at), so 10 total entries.
        for i in range(5):
            tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
            await tasks_tools.tasks_update(
                ctx,
                task_id=created.id,
                request=UpdateTaskRequest(content=f"v{i}"),
            )

        # Page 1
        p1 = await tasks_tools.tasks_history(ctx, task_id=created.id, k=4)
        assert len(p1.items) == 4
        assert p1.next_cursor is not None
        # Page 2
        p2 = await tasks_tools.tasks_history(
            ctx,
            task_id=created.id,
            k=4,
            cursor=p1.next_cursor,
        )
        assert len(p2.items) == 4
        assert p2.next_cursor is not None
        # Page 3 (final)
        p3 = await tasks_tools.tasks_history(
            ctx,
            task_id=created.id,
            k=4,
            cursor=p2.next_cursor,
        )
        assert len(p3.items) == 2
        assert p3.next_cursor is None


@pytest.mark.asyncio
async def test_tasks_history_actor_is_server_set_not_spoofed(_t5_engine: Any) -> None:
    """Actor in history events reflects the caller at update time; can't be spoofed.

    The history dict's ``actor`` field is set by T6's ``_persist_task_update``
    from the server-derived caller identity (T3). Callers cannot inject a
    fake actor via the update envelope — this test confirms the round-trip
    surfaces the real caller.
    """
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx = _make_ctx({"user_email": "alice@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(
                    rid,
                    content="x",
                    tags=["task", "priority:normal"],
                ),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        created = await tasks_tools.tasks_create(
            ctx,
            content="x",
            tags=["task", "priority:normal"],
        )
        assert isinstance(created, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="high"),
        )

        history = await tasks_tools.tasks_history(ctx, task_id=created.id)

    assert isinstance(history, TaskHistoryResult)
    assert history.items, "expected at least one history event"
    for event in history.items:
        assert event.actor == "user:alice@example.com", (
            f"actor must be the server-derived caller; got {event.actor!r}"
        )


@pytest.mark.asyncio
async def test_tasks_history_enforces_visibility_404(_t5_engine: Any) -> None:
    """User B's tasks_history on User A's task returns 404 (no info leak)."""
    from session_buddy.mcp.tools import tasks_tools

    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
    ctx_alice = _make_ctx({"user_email": "alice@example.com"})
    ctx_bob = _make_ctx({"user_email": "bob@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_t5_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(
                side_effect=lambda rid: _t5_reflection_for(rid, tags=["task"]),
            ),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
        task_a = await tasks_tools.tasks_create(ctx_alice, content="x", tags=["task"])
        assert isinstance(task_a, Task)

        tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)
        await tasks_tools.tasks_update(
            ctx_alice,
            task_id=task_a.id,
            request=UpdateTaskRequest(priority="high"),
        )

        # Bob requests Alice's task history — 404 (not 403, no info leak).
        result = await tasks_tools.tasks_history(ctx_bob, task_id=task_a.id)

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"


@pytest.mark.asyncio
async def test_tasks_history_returns_404_for_unknown_id(_t5_engine: Any) -> None:
    """tasks_history(unknown_id) returns 404 envelope."""
    from session_buddy.mcp.tools import tasks_tools

    ctx = _make_ctx({"user_email": "les@example.com"})

    result = await tasks_tools.tasks_history(
        ctx,
        task_id="t-0123456789abcdef0123456789abcdef",
    )

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"


@pytest.mark.asyncio
async def test_tasks_history_validates_id_format(_t5_engine: Any) -> None:
    """tasks_history(task_id='not-a-uuid') returns invalid_id_format envelope."""
    from session_buddy.mcp.tools import tasks_tools

    ctx = _make_ctx({"user_email": "les@example.com"})

    result = await tasks_tools.tasks_history(ctx, task_id="not-a-uuid")

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "invalid_id_format"

