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

from session_buddy.mcp.tools.tasks_events import TaskCreatedPayload, TaskUpdatedPayload
from session_buddy.mcp.tools.tasks_models import (
    TASK_ID_PATTERN,
    Task,
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


@pytest.mark.skip(reason="T9 dependency — tasks_history lands in T9")
@pytest.mark.asyncio
async def test_tasks_update_records_diff_in_history(_t5_engine: Any) -> None:
    """After priority normal→high, tasks_history shows the diff.

    Skipped until T9's ``tasks_history`` tool lands. For T6 the
    ``_persist_task_update`` writes the history list into the sidecar
    metadata under the ``history`` key — verified by sidecar inspection
    in the integration test path that T12 wires.
    """


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
