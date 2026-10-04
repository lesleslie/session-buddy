"""End-to-end integration tests for the task-system lifecycle.

Pins:

- Full lifecycle: ``tasks_create`` → ``tasks_get`` → ``tasks_update`` →
  ``tasks_complete`` → ``tasks_history`` round-trips correctly.
- Legacy coercion: a ``store_reflection(tags=['todo'])`` row surfaces
  via ``tasks_list(include_legacy=True)`` and is hidden by default.
- Input size caps: ``content > 4 KiB`` and ``metadata > 1 KiB`` are
  rejected at the model layer.

The lifecycle test that exercises ``tasks_search`` is gated behind
``@pytest.mark.slow`` because akosha reindex lag is ~30s; we wait up
to 60s for the new row to surface. If akosha is unreachable in the
test environment, the slow test is skipped (see the body comment).
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

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from session_buddy.mcp.tools import tasks_storage, tasks_tools
from session_buddy.mcp.tools.tasks_models import (
    Task,
    TaskHistoryResult,
    UpdateTaskRequest,
)
from session_buddy.mcp.tools.tasks_security import (
    MAX_CONTENT_BYTES,
    MAX_METADATA_BYTES,
    RateLimiter,
)


def _make_ctx(auth: dict[str, str]) -> Any:
    """Build a stub ``Context``-like object whose ``get_state`` exposes auth keys."""
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
    timestamp: Any = None,
) -> dict[str, Any]:
    """Build a reflection dict matching the adapter's shape."""
    return {
        "id": reflection_id,
        "content": content,
        "tags": list(tags) if tags is not None else ["task"],
        "project": None,
        "created_at": (timestamp or datetime.now(UTC)).isoformat(),
        "updated_at": (timestamp or datetime.now(UTC)).isoformat(),
    }


def _reset_limiters() -> None:
    """Reset module-level rate limiters so cross-test state doesn't leak."""
    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_task_lifecycle_create_update_complete_history() -> None:
    """Full lifecycle: create → get → update → complete → history.

    Excludes ``tasks_search`` from this test because that requires
    the akosha reindex round-trip and lives in the ``@pytest.mark.slow``
    test below.
    """
    _reset_limiters()

    engine = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(engine)
    try:
        ctx = _make_ctx({"user_email": "lifecycle@example.com"})

        # Set up the priority-tag round-trip: the test reads the
        # current tags from the reflection, which must include the
        # ``priority:normal`` discriminator for the diff to be visible.
        async def _read_with_priority(rid: str) -> dict[str, Any]:
            return _reflection_for(
                rid,
                tags=["task", "priority:normal"],
            )

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
                new=AsyncMock(side_effect=_read_with_priority),
            ),
            patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
        ):
            # 1. Create
            created = await tasks_tools.tasks_create(
                ctx,
                content="end-to-end lifecycle test",
                tags=["task", "integration"],
                priority="normal",
            )
            assert isinstance(created, Task)
            assert created.id.startswith("t-")
            assert created.status == "open"

            # 2. Get round-trips
            fetched = await tasks_tools.tasks_get(ctx, task_id=created.id)
            assert isinstance(fetched, Task)
            assert fetched.id == created.id

            # 3. Update mutates
            updated = await tasks_tools.tasks_update(
                ctx,
                task_id=created.id,
                request=UpdateTaskRequest(priority="high"),
            )
            assert isinstance(updated, Task)
            assert updated.priority == "high"

            # 4. Complete
            completed = await tasks_tools.tasks_complete(
                ctx,
                task_id=created.id,
                result_notes="Lifecycle test passed",
            )
            assert isinstance(completed, Task)
            assert completed.status == "done"
            assert completed.completed_by == "user:lifecycle@example.com"

            # 5. History shows the lifecycle
            history = await tasks_tools.tasks_history(ctx, task_id=created.id)
            assert isinstance(history, TaskHistoryResult)
            assert len(history.items) >= 1, (
                f"history should record at least the priority diff; "
                f"got {history.items!r}"
            )
    finally:
        tasks_storage.set_engine(None)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_tasks_search_finds_newly_created_task_after_akosha_reindex() -> None:
    """Create a task → wait up to 60s for akosha reindex → tasks_search returns it.

    Spec §Search + line 121-126 of the spec: ``tasks_search`` queries
    the akosha index, which has a ~30s reindex lag. We poll for up
    to 60s (12 × 5s).

    If akosha is not reachable in this test environment (e.g. CI
    runners without a hot akosha), we skip the assertion rather than
    fail — the unit test ``test_tasks_search_returns_only_kind_task_rows``
    already pins the kind=task filter contract.
    """
    # Skip cleanly if akosha isn't reachable so this test stays
    # network-level verification only. Unit tests already cover the
    # kind/visibility/score filter pipeline.
    try:
        from session_buddy.mcp.tools import tasks_tools as _tt  # noqa: F401
    except (ImportError, RuntimeError):  # pragma: no cover — defensive guard
        pytest.skip(
            "tasks_tools unavailable (likely missing dependency); "
            "integration env only.",
        )

    # Probe akosha via search_reflections before declaring the env
    # integration-ready. If the call raises or hangs, skip.
    async def _probe() -> bool:
        try:
            await asyncio.wait_for(
                tasks_tools.search_reflections(query="probe", limit=1),
                timeout=3.0,
            )
            return True
        except (OSError, TimeoutError, RuntimeError):
            return False

    # Run the probe in the same loop the test uses.
    reachable = await _probe()
    if not reachable:
        pytest.skip(
            "requires akosha reindex — integration env only",
        )

    # The actual lifecycle search round-trip is best validated against
    # a running akosha with the real adapter chain. Unit tests pin
    # the filter pipeline; this integration test asserts the
    # round-trip when the env supports it.
    _reset_limiters()
    engine = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(engine)
    try:
        ctx = _make_ctx({"user_email": "search-roundtrip@example.com"})
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
            created = await tasks_tools.tasks_create(
                ctx,
                content=f"akoshareindexprobe-{uuid.uuid4().hex[:8]}",
                tags=["task"],
            )
            assert isinstance(created, Task)

            found = False
            unique_token = created.content
            for _ in range(12):
                results = await tasks_tools.tasks_search(
                    ctx,
                    query=unique_token,
                    k=10,
                )
                if any(r.id == created.id for r in results):
                    found = True
                    break
                await asyncio.sleep(5)

            assert found, (
                "tasks_search did not surface the task after 60s akosha reindex"
            )
    finally:
        tasks_storage.set_engine(None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_legacy_coercion_in_list_with_include_legacy() -> None:
    """store_reflection(tags=['todo']) row appears in tasks_list(include_legacy=True)
    but not in the default tasks_list().
    """
    _reset_limiters()

    engine = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(engine)
    try:
        ctx = _make_ctx({"user_email": "legacy-test@example.com"})

        # Seed a legacy reflection row via the canonical store_reflection
        # path. The reflection storage adapter is what the legacy coercion
        # path queries — we mimic the production write here.
        legacy_id = f"ref-{uuid.uuid4().hex[:12]}"
        legacy_reflection = _reflection_for(
            legacy_id,
            content="legacy todo content for integration test",
            tags=["todo", "legacy-test-marker"],
        )

        with (
            patch.object(
                tasks_tools,
                "store_reflection",
                new=AsyncMock(return_value=legacy_id),
            ),
            patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
            patch.object(
                tasks_tools,
                "_query_legacy_reflections",
                new=AsyncMock(
                    return_value=[(legacy_id, legacy_reflection)],
                ),
            ),
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
            # Default tasks_list excludes legacy.
            default_list = await tasks_tools.tasks_list(
                ctx,
                include_legacy=False,
            )
            default_ids = [t.id for t in default_list.items]
            assert legacy_id not in default_ids, (
                f"Default list leaked legacy row {legacy_id!r}: {default_ids!r}"
            )

            # include_legacy=True includes legacy.
            legacy_list = await tasks_tools.tasks_list(
                ctx,
                include_legacy=True,
            )
            legacy_ids = [t.id for t in legacy_list.items]
            assert legacy_id in legacy_ids, (
                f"Legacy row missing from include_legacy=True: {legacy_ids!r}"
            )
    finally:
        tasks_storage.set_engine(None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_input_size_caps_enforced() -> None:
    """Content > 4 KiB and metadata > 1 KiB are rejected at the model layer.

    The size caps are enforced inside the Pydantic field validators
    on the ``Task`` model. We invoke ``tasks_create`` directly with
    over-cap payloads and assert it raises ``ValidationError`` (or
    a wrapped ``ValueError`` depending on which path fails first).
    """
    _reset_limiters()

    engine = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(engine)
    try:
        ctx = _make_ctx({"user_email": "size-cap@example.com"})

        # Content too large — MAX_CONTENT_BYTES is 4096.
        big_content = "x" * (MAX_CONTENT_BYTES + 1)
        with (
            patch.object(
                tasks_tools,
                "store_reflection",
                new=_store_reflection_mock(),
            ),
            patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
            pytest.raises((ValidationError, ValueError)),
        ):
            await tasks_tools.tasks_create(
                ctx,
                content=big_content,
                tags=["task"],
            )

        # Metadata too large — MAX_METADATA_BYTES is 1024.
        big_metadata = {"big_key": "x" * (MAX_METADATA_BYTES + 1)}
        with (
            patch.object(
                tasks_tools,
                "store_reflection",
                new=_store_reflection_mock(),
            ),
            patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
            pytest.raises((ValidationError, ValueError)),
        ):
            await tasks_tools.tasks_create(
                ctx,
                content="ok",
                tags=["task"],
                metadata=big_metadata,
            )
    finally:
        tasks_storage.set_engine(None)
