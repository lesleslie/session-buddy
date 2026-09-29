"""Integration tests for task-system authz isolation between MCP callers.

Pins the security-critical invariants called out in spec §Authz Model:

- Caller-supplied ``owner`` is silently overwritten with the server-derived
  caller identity (the server-derives-owner contract).
- ``tasks_list`` does NOT include another user's private tasks.
- ``tasks_get`` returns 404 (NOT 403) on cross-user access to avoid
  leaking existence.
- ``tasks_update`` returns 404 (NOT 403) on cross-user access.
- ``tasks_complete`` returns 404 (NOT 403) on cross-user access.
"""

from __future__ import annotations

import sys
import types

# Module-level preload: stub out a transitive dependency that the
# ``session_buddy.mcp.tools`` package __init__ pulls in, so this test
# file can import ``tasks_tools`` without the parent __init__ failing
# first. The stub is a no-op module attribute that's only referenced
# from the broken parent __init__; nothing here invokes it.
if "session_buddy.mcp.tools.infrastructure.pools" not in sys.modules:
    _pools_stub = types.ModuleType(
        "session_buddy.mcp.tools.infrastructure.pools",
    )

    # The stub is invoked from ``session_buddy.server_optimized`` at
    # module load: it calls ``register_pool_tools(mcp)``. Provide a
    # no-op callable so the chain completes without invoking the
    # real (broken) registration function.
    def _noop_register_pool_tools(_mcp: object) -> None:
        return None

    _pools_stub.register_pool_tools = _noop_register_pool_tools  # type: ignore[attr-defined]
    sys.modules["session_buddy.mcp.tools.infrastructure.pools"] = _pools_stub

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools import tasks_storage, tasks_tools
from session_buddy.mcp.tools.tasks_models import Task, UpdateTaskRequest
from session_buddy.mcp.tools.tasks_security import RateLimiter
from session_buddy.mcp.tools.tasks_tools import (
    tasks_complete,
    tasks_create,
    tasks_get,
    tasks_list,
    tasks_update,
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


def _fake_store_reflection(content: str, tags=None, metadata=None) -> str:
    """Sync inner helper that the AsyncMock below wraps."""
    reflection_id = f"ref-{uuid.uuid4().hex[:12]}"
    if metadata is not None:
        tasks_storage.persist_task_metadata(
            tasks_storage.get_engine(),
            reflection_id,
            dict(metadata),
        )
    return reflection_id


def _store_reflection_mock() -> Any:
    """Build an AsyncMock whose side_effect is the sync fake above."""
    return AsyncMock(side_effect=_fake_store_reflection)


def _reflection_for(
    reflection_id: str,
    content: str = "task body",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Build a reflection dict matching the adapter's shape."""
    from datetime import UTC, datetime

    return {
        "id": reflection_id,
        "content": content,
        "tags": list(tags) if tags is not None else ["task"],
        "project": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _reset_limiters() -> None:
    """Reset module-level rate limiters so cross-test state doesn't leak."""
    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_user_a_cannot_read_user_b_private_tasks() -> None:
    """Two parallel MCP caller identities; verify isolation.

    Spec §Authz Model + §Error Handling Matrix: cross-user access
    returns 404 envelopes (NOT 403) so an attacker cannot probe for
    task existence by status code.
    """
    _reset_limiters()

    engine = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(engine)
    try:
        ctx_a = _make_ctx({"user_email": "alice@example.com"})
        ctx_b = _make_ctx({"user_email": "bob@example.com"})

        with (
            patch.object(
                tasks_tools,
                "store_reflection",
                new=_store_reflection_mock(),
            ),
            patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
            patch.object(
                tasks_tools,
                "_read_reflection",
                new=AsyncMock(
                    side_effect=lambda rid: _reflection_for(
                        rid,
                        tags=["task"],
                    ),
                ),
            ),
        ):
            # User A creates a task. The caller-supplied ``owner`` MUST be
            # silently overwritten by the server-derived caller identity
            # (this is the load-bearing security invariant — see the
            # server-derives-owner spec contract).
            task_a = await tasks_create(
                ctx_a,
                content="alice-secret-content",
                tags=["task", "private"],
                owner="user:attacker@example.com",
            )
            assert isinstance(task_a, Task)
            assert task_a.owner == "user:alice@example.com", (
                f"owner must be server-derived; got {task_a.owner!r}"
            )

            # User B lists — must NOT contain User A's task.
            listed = await tasks_list(ctx_b, include_legacy=False)
            listed_ids = [t.id for t in listed.items]
            assert task_a.id not in listed_ids, (
                f"User B sees User A's task; listed_ids={listed_ids!r}"
            )

            # User B calls tasks_get(task_A_id) — must return 404 envelope.
            get_result = await tasks_get(ctx_b, task_id=task_a.id)
            assert isinstance(get_result, dict), (
                f"Expected error envelope dict, got {type(get_result).__name__}"
            )
            assert get_result["status"] == "error"
            assert get_result["error_code"] == "not_found"

            # User B calls tasks_update(task_A_id, ...) — must be rejected.
            update_result = await tasks_update(
                ctx_b,
                task_id=task_a.id,
                request=UpdateTaskRequest(priority="high"),
            )
            assert isinstance(update_result, dict)
            assert update_result["status"] == "error"
            assert update_result["error_code"] == "not_found"

            # User B calls tasks_complete(task_A_id) — must be rejected.
            complete_result = await tasks_complete(ctx_b, task_id=task_a.id)
            assert isinstance(complete_result, dict)
            assert complete_result["status"] == "error"
            assert complete_result["error_code"] == "not_found"
    finally:
        tasks_storage.set_engine(None)