"""Unit tests for ``tasks_link_workflow`` — the task→workflow back-link.

``Task.workflow_id`` is the one field in the task model that is
**server-set**: the caller cannot set it, and the caller-supplied
``metadata`` bag on ``tasks_update`` must never become its source. The
contract that settles how the link is written lives in the mahavishnu
repo at ``docs/specs/2026-10-30-task-workflow-backlink-design.md``.

These tests pin the four properties the contract promises:

- **C1 — one writer.** Only ``tasks_link_workflow`` sets the field; the
  generic metadata bag cannot reach it.
- **C2 — owner-scoped.** A caller that cannot see the task gets the
  404-shaped ``not_found`` envelope, not a leak of the link's existence.
- **C3 — link-once.** The first link wins; re-linking to the same id is
  an idempotent no-op (the orphan sweeper retries a link after a step-3
  failure, and a retry must not be an error); re-linking to a different
  id is refused.
- **C4 — provenance.** The link records who made it and when, and those
  fields survive the sidecar round trip.

They also pin **C5**, the workflow-id pattern, including the trailing
newline that ``re.match`` would have let through.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools import tasks_storage, tasks_tools
from session_buddy.mcp.tools.tasks_events import TaskUpdatedPayload
from session_buddy.mcp.tools.tasks_models import Task, UpdateTaskRequest
from session_buddy.mcp.tools.tasks_security import RateLimiter

_WORKFLOW_ID = "wf_1a2b3c4d_code_review"
_NOW = datetime(2026, 10, 30, 7, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _make_ctx(auth: dict[str, str]) -> Any:
    """Build a stub ``Context`` whose ``get_state`` exposes auth keys.

    FastMCP 4.x's ``Context.get_state`` is a coroutine function, so the
    stub is async too — the task tools await it.
    """
    ctx = MagicMock()

    async def _get_state(key: str) -> Any:
        mapping = {
            "auth_user_email": auth.get("user_email"),
            "auth_agent_id": auth.get("agent_id"),
        }
        return mapping.get(key)

    ctx.get_state.side_effect = _get_state
    return ctx


@pytest.fixture
def engine() -> Any:
    """Yield a fresh in-memory sidecar engine; reset the singleton after."""
    e = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(e)
    try:
        yield e
    finally:
        tasks_storage.set_engine(None)


#: In-memory stand-in for the reflection rows' ``metadata`` document.
_FAKE_REFLECTIONS: dict[str, dict[str, Any]] = {}


def _fake_store_reflection(
    content: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Stand in for ``store_reflection``: mint an id and write BOTH stores.

    The production path persists the caller's metadata into the task
    metadata sidecar keyed by the returned reflection id — that is the
    row ``_find_reflection_id_by_task_id`` searches — AND into the
    reflection row's own ``metadata`` document, which is the document
    the read path prefers.

    The fake reflection store below is what makes the second store
    visible to these tests. Before it existed, ``_reflection_for``
    returned a row with no ``metadata`` key at all, so the merge always
    fell back to the sidecar and the tests could not express the
    production state (a reflection document carrying a stale
    ``workflow_id: None``).
    """
    reflection_id = f"ref-{uuid.uuid4().hex[:12]}"
    if metadata is not None:
        tasks_storage.persist_task_metadata(
            tasks_storage.get_engine(),
            reflection_id,
            dict(metadata),
        )
    _FAKE_REFLECTIONS[reflection_id] = {
        "id": reflection_id,
        "content": content,
        "tags": list(tags) if tags is not None else ["task"],
        "metadata": dict(metadata) if metadata is not None else {},
    }
    return reflection_id


async def _fake_update_reflection(
    reflection_id: str,
    content: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Stand in for ``tasks_tools._update_reflection``.

    Writes back into the fake reflection store so a test can assert what
    the reflection row holds after a mutation.
    """
    row = _FAKE_REFLECTIONS.setdefault(
        reflection_id,
        {"id": reflection_id, "content": "", "tags": ["task"], "metadata": {}},
    )
    if content is not None:
        row["content"] = content
    if tags is not None:
        row["tags"] = list(tags)
    if metadata is not None:
        row["metadata"] = dict(metadata)


def _store_reflection_mock() -> Any:
    return AsyncMock(side_effect=_fake_store_reflection)


def _reflection_for(reflection_id: str, content: str = "task body") -> dict[str, Any]:
    row = _FAKE_REFLECTIONS.get(reflection_id)
    if row is None:
        return {
            "id": reflection_id,
            "content": content,
            "tags": ["task"],
            "metadata": {},
        }
    return {
        "id": row["id"],
        "content": row["content"],
        "tags": list(row["tags"]),
        "metadata": dict(row["metadata"]),
    }


@pytest.fixture(autouse=True)
def _isolate_reflection_writes() -> Any:
    """Keep every reflection-store write inside the fake store.

    The link path mirrors the workflow id into the reflection row's
    ``metadata`` document. Without this, ``_update_reflection`` would
    reach the REAL adapter — and the live DuckDB — for the rows the fake
    store invented.
    """
    _FAKE_REFLECTIONS.clear()
    with patch.object(
        tasks_tools,
        "_update_reflection",
        new=AsyncMock(side_effect=_fake_update_reflection),
    ):
        yield


async def _create_task(ctx: Any, content: str = "task body") -> Task:
    """Create a task through the real ``tasks_create`` path."""
    created = await tasks_tools.tasks_create(
        ctx,
        content=content,
        tags=["task"],
    )
    assert isinstance(created, Task)
    return created


def _reset_limiters() -> None:
    tasks_tools._create_rate_limiter = RateLimiter(limit=60, window_seconds=60)
    tasks_tools._update_rate_limiter = RateLimiter(limit=120, window_seconds=60)


# ---------------------------------------------------------------------------
# C1 / C4 — the link, its provenance, and the round trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_tasks_link_workflow_sets_the_link_and_its_provenance(
    engine: Any,
) -> None:
    """Linking populates ``workflow_id`` plus who/when, and it persists."""
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        linked = await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )

    assert isinstance(linked, Task)
    assert linked.workflow_id == _WORKFLOW_ID
    assert linked.workflow_linked_by == "user:les@example.com"
    assert linked.workflow_linked_at is not None

    # The link survives the sidecar round trip: read it back the way
    # ``tasks_get`` does.
    with patch.object(
        tasks_tools,
        "_read_reflection",
        new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
    ):
        fetched = await tasks_tools.tasks_get(ctx, task_id=created.id)

    assert isinstance(fetched, Task)
    assert fetched.workflow_id == _WORKFLOW_ID
    assert fetched.workflow_linked_by == "user:les@example.com"
    assert fetched.workflow_linked_at is not None


@pytest.mark.unit
async def test_the_link_is_recorded_in_the_task_history(engine: Any) -> None:
    """The link shows up in the history timeline ``tasks_history`` renders."""
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )

    reflection_id = tasks_tools._find_reflection_id_by_task_id(
        engine=engine,
        task_id=created.id,
    )
    assert reflection_id is not None
    blob = tasks_storage.read_task_metadata(engine=engine, reflection_id=reflection_id)
    assert blob is not None
    history = blob.get("history") or []
    assert history, "the link must be recorded in the history timeline"
    # ``_compute_diff`` emits one entry per changed field, alphabetically:
    # updated_at, workflow_id, workflow_linked_at, workflow_linked_by.
    link_entries = [h for h in history if h["field"] == "workflow_id"]
    assert link_entries, (
        f"expected a workflow_id history entry; got {[h['field'] for h in history]!r}"
    )
    assert link_entries[-1]["before"] is None
    assert link_entries[-1]["after"] == _WORKFLOW_ID
    assert link_entries[-1]["actor"] == "user:les@example.com"


@pytest.mark.unit
async def test_linking_emits_a_task_updated_event_with_the_workflow_id(
    engine: Any,
) -> None:
    """The link is observable on the event stream, not only in the row."""
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})
    publish_mock = AsyncMock()

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=publish_mock),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )

    update_events = [
        call.args
        for call in publish_mock.await_args_list
        if call.args and call.args[0] == "task.updated"
    ]
    assert update_events, "expected at least one task.updated event"
    workflow_event = next(
        (
            e
            for e in update_events
            if isinstance(e[1], TaskUpdatedPayload) and "workflow_id" in e[1].diff
        ),
        None,
    )
    assert workflow_event is not None, (
        f"expected a workflow_id diff; got {[e[1].diff for e in update_events]!r}"
    )
    assert workflow_event[1].diff["workflow_id"][1] == _WORKFLOW_ID


# ---------------------------------------------------------------------------
# C3 — link-once
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_relinking_to_a_different_workflow_is_refused(engine: Any) -> None:
    """The first link wins: a task binds to exactly one workflow."""
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )
        second = await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id="wf_99999999_something_else",
        )

    assert isinstance(second, dict)
    assert second.get("status") == "error"
    assert second.get("error_code") == "workflow_already_linked"
    # The existing binding is NOT echoed back: the envelope says only
    # that the task is already bound elsewhere. The first link stands.
    assert "linked_workflow_id" not in second.get("details", {})
    assert "linked_workflow_id" not in second.get("message", "")

    # The first binding is untouched.
    with patch.object(
        tasks_tools,
        "_read_reflection",
        new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
    ):
        fetched = await tasks_tools.tasks_get(ctx, task_id=created.id)
    assert isinstance(fetched, Task)
    assert fetched.workflow_id == _WORKFLOW_ID


@pytest.mark.unit
async def test_relinking_to_the_same_workflow_is_idempotent(engine: Any) -> None:
    """The sweeper retries a link after a step-3 failure — that must not error.

    The retry is a no-op: no second write, no second event.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})
    publish_mock = AsyncMock()
    writes: list[dict[str, Any]] = []
    real_persist = tasks_storage.persist_task_metadata

    def _capture(engine, reflection_id, metadata):
        """Record the write, then let the real persistence happen.

        A spy that REPLACED the real call would stop the sidecar row
        from ever being written, and the second link would then fail to
        find the task at all — testing the harness, not the link.
        """
        writes.append(dict(metadata))
        return real_persist(engine, reflection_id, metadata)

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=publish_mock),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(
            tasks_tools.tasks_storage,
            "persist_task_metadata",
            side_effect=_capture,
        ),
    ):
        created = await _create_task(ctx)
        await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )
        writes_after_first = len(writes)
        events_after_first = publish_mock.await_count

        again = await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )

    assert isinstance(again, Task)
    assert again.workflow_id == _WORKFLOW_ID
    assert len(writes) == writes_after_first, "the retry must not write again"
    assert publish_mock.await_count == events_after_first, (
        "the retry must not emit another event"
    )


# ---------------------------------------------------------------------------
# C2 — owner-scoped
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_caller_who_cannot_see_the_task_gets_not_found(engine: Any) -> None:
    """The 404-shaped envelope hides both the task and the link."""
    _reset_limiters()
    owner_ctx = _make_ctx({"user_email": "les@example.com"})
    other_ctx = _make_ctx({"user_email": "someone-else@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(owner_ctx)
        await tasks_tools.tasks_link_workflow(
            owner_ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )
        result = await tasks_tools.tasks_link_workflow(
            other_ctx,
            task_id=created.id,
            workflow_id="wf_99999999_theirs",
        )

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("error_code") == "not_found"


# ---------------------------------------------------------------------------
# C5 — the workflow-id pattern
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_malformed_workflow_id_is_rejected(engine: Any) -> None:
    """Only conservative identifier shapes are accepted."""
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        for bad in ("wf with spaces", "wf/../etc", "wf\nnewline", "x" * 129):
            result = await tasks_tools.tasks_link_workflow(
                ctx,
                task_id=created.id,
                workflow_id=bad,
            )
            assert isinstance(result, dict), f"{bad!r} should not link"
            assert result.get("error_code") == "invalid_workflow_id", bad


@pytest.mark.unit
async def test_a_workflow_id_with_a_trailing_newline_is_rejected(
    engine: Any,
) -> None:
    """``re.match`` would let this through — ``$`` also matches before ``\\n``.

    The value is spliced into an MCP key path on the mahavishnu side, so
    a trailing newline has to be refused at the boundary.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        result = await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id="wf_abc123\n",
        )

    assert isinstance(result, dict)
    assert result.get("error_code") == "invalid_workflow_id"


@pytest.mark.unit
async def test_a_malformed_task_id_is_rejected(engine: Any) -> None:
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    result = await tasks_tools.tasks_link_workflow(
        ctx,
        task_id="not-a-task-id",
        workflow_id=_WORKFLOW_ID,
    )

    assert isinstance(result, dict)
    assert result.get("error_code") == "invalid_id_format"


# ---------------------------------------------------------------------------
# C1 — the metadata bag cannot reach the field
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_the_metadata_bag_cannot_set_the_workflow_id(engine: Any) -> None:
    """``tasks_update(metadata={"workflow_id": ...})`` must not link a task.

    This is the vector the contract closes: the metadata dict is
    caller-supplied content, whatever key it carries.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        created = await _create_task(ctx)
        updated = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(metadata={"workflow_id": "wf_forged"}),
        )

    assert isinstance(updated, Task)
    assert updated.workflow_id is None, (
        "caller metadata must not populate the server-set workflow_id"
    )
    # The caller's own data is still persisted — under its own key.
    assert updated.metadata == {"workflow_id": "wf_forged"}


@pytest.mark.unit
async def test_a_link_reaches_the_reflection_store_and_survives_an_update(
    engine: Any,
) -> None:
    """The link must live in BOTH stores, and survive an ordinary update.

    Regression: the link was written only to the sidecar while the
    reflection document kept a stale ``workflow_id: None``. The read
    path prefers the reflection document, so the link was invisible to
    every reader — and the next ``tasks_update`` merged that stale
    ``None`` back over the sidecar, destroying the binding permanently.
    The two link tests above could not catch it because their reflection
    fixture carried no ``metadata`` at all, so the merge always fell
    back to the sidecar.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})
    _FAKE_REFLECTIONS.clear()

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(
            tasks_tools,
            "_update_reflection",
            new=AsyncMock(side_effect=_fake_update_reflection),
        ),
    ):
        created = await _create_task(ctx)
        linked = await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )
        assert isinstance(linked, Task)
        assert linked.workflow_id == _WORKFLOW_ID

        reflection_id = tasks_tools._find_reflection_id_by_task_id(
            engine=engine,
            task_id=created.id,
        )
        assert reflection_id is not None

        # The link reached the reflection document, not just the sidecar.
        assert (
            _FAKE_REFLECTIONS[reflection_id]["metadata"]["workflow_id"] == _WORKFLOW_ID
        )

        # A reader that prefers the reflection document sees the link.
        fetched = await tasks_tools.tasks_get(ctx, task_id=created.id)
        assert isinstance(fetched, Task)
        assert fetched.workflow_id == _WORKFLOW_ID

        # An ordinary update must not clear it.
        updated = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="high"),
        )
        assert isinstance(updated, Task)
        assert updated.workflow_id == _WORKFLOW_ID
        assert (
            _FAKE_REFLECTIONS[reflection_id]["metadata"]["workflow_id"] == _WORKFLOW_ID
        )


@pytest.mark.unit
async def test_a_link_keeps_history_that_lives_only_in_the_reflection_row(
    engine: Any,
) -> None:
    """The link must append to the MERGED history, not to the sidecar's.

    The history is append-only, and the reflection document is the
    authoritative copy. A link that rebuilt the list from the sidecar
    alone would drop every entry the sidecar never received — silently,
    because a shorter history still looks like a history.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})
    _FAKE_REFLECTIONS.clear()

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(
            tasks_tools,
            "_update_reflection",
            new=AsyncMock(side_effect=_fake_update_reflection),
        ),
    ):
        created = await _create_task(ctx)
        reflection_id = tasks_tools._find_reflection_id_by_task_id(
            engine=engine,
            task_id=created.id,
        )
        assert reflection_id is not None

        # An entry that lives ONLY in the reflection document — the state
        # a task reaches when the sidecar lags behind the store that is
        # authoritative.
        _FAKE_REFLECTIONS[reflection_id]["metadata"]["history"] = [
            {
                "field": "priority",
                "before": "normal",
                "after": "high",
                "actor": "user:les@example.com",
                "at": "2026-11-07T11:00:00+00:00",
            },
        ]

        linked = await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )
        assert isinstance(linked, Task)

    history = _FAKE_REFLECTIONS[reflection_id]["metadata"]["history"]
    assert len(history) >= 2, (
        f"expected the pre-existing entry plus the link's own entries; got {history!r}"
    )
    assert history[0]["field"] == "priority", (
        f"the pre-existing history entry was dropped; got {history!r}"
    )
    assert history[0]["before"] == "normal"
    assert history[0]["after"] == "high"


@pytest.mark.unit
async def test_a_link_mirrors_the_merged_document_not_a_row_subset(
    engine: Any,
) -> None:
    """The mirror must carry the IDENTITY fields forward, not drop them.

    The mirror is written into the authoritative store. If it is built
    from the reflection row's own document and that document is partial
    (no ``owner`` / ``visibility`` / ``task_id``), the mirror persists a
    document WITHOUT them — and the backfill skips any row whose
    document is non-empty, so the row is never completed. When the
    sidecar is retired, that task loses its authorization metadata.

    The mirror is therefore built from the MERGED document, which holds
    the identity fields whichever store supplied them.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})
    _FAKE_REFLECTIONS.clear()

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(
            tasks_tools,
            "_update_reflection",
            new=AsyncMock(side_effect=_fake_update_reflection),
        ),
    ):
        created = await _create_task(ctx)
        reflection_id = tasks_tools._find_reflection_id_by_task_id(
            engine=engine,
            task_id=created.id,
        )
        assert reflection_id is not None

        # A partial reflection document: the link fields only. The
        # sidecar still holds the identity fields.
        _FAKE_REFLECTIONS[reflection_id]["metadata"] = {"workflow_id": None}

        linked = await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )
        assert isinstance(linked, Task)

    mirrored = _FAKE_REFLECTIONS[reflection_id]["metadata"]
    assert mirrored.get("owner") == "user:les@example.com", (
        f"the mirror dropped the owner; got {mirrored!r}"
    )
    assert mirrored.get("task_id") == created.id, (
        f"the mirror dropped the task id; got {mirrored!r}"
    )
    assert mirrored.get("kind") == "task", (
        f"the mirror dropped the task discriminator; got {mirrored!r}"
    )
    # ``visibility`` is not asserted: a task that has never been updated
    # carries no visibility key in its document at all (the model's
    # default is "private"), and the update path writes one. The
    # identity fields above are the ones that must survive the mirror.


@pytest.mark.unit
async def test_an_ordinary_update_does_not_clear_an_existing_link(
    engine: Any,
) -> None:
    """Once linked, the link survives ordinary task updates."""
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        created = await _create_task(ctx)
        await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )
        updated = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="high"),
        )

    assert isinstance(updated, Task)
    assert updated.workflow_id == _WORKFLOW_ID
    assert updated.workflow_linked_by == "user:les@example.com"


@pytest.mark.unit
async def test_a_stale_update_does_not_clobber_a_link(engine: Any) -> None:
    """A link written while an update was in flight must survive the update.

    The update path re-reads the sidecar row immediately before writing
    and merges onto it. Without that, the update would write back the
    stale snapshot it read at the top of its body — and silently erase a
    workflow link written in between.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        await tasks_tools.tasks_link_workflow(
            ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )

    reflection_id = tasks_tools._find_reflection_id_by_task_id(
        engine=engine,
        task_id=created.id,
    )
    assert reflection_id is not None
    current = tasks_storage.read_task_metadata(
        engine=engine,
        reflection_id=reflection_id,
    )
    assert current is not None
    assert current["workflow_id"] == _WORKFLOW_ID

    # The snapshot an update would have read at the top of its body: the
    # task as it was BEFORE the link existed.
    stale = {
        key: value
        for key, value in current.items()
        if key not in ("workflow_id", "workflow_linked_at", "workflow_linked_by")
    }

    reads = {"n": 0}

    def _stale_then_current(engine, reflection_id):
        del engine, reflection_id
        reads["n"] += 1
        return dict(stale) if reads["n"] == 1 else dict(current)

    with (
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(
            tasks_tools.tasks_storage,
            "read_task_metadata",
            side_effect=_stale_then_current,
        ),
    ):
        updated = await tasks_tools.tasks_update(
            ctx,
            task_id=created.id,
            request=UpdateTaskRequest(priority="high"),
        )

    assert isinstance(updated, Task)
    assert updated.priority == "high"
    assert reads["n"] >= 2, "the persist path must re-read the current blob"

    after = tasks_storage.read_task_metadata(
        engine=engine,
        reflection_id=reflection_id,
    )
    assert after is not None
    assert after["workflow_id"] == _WORKFLOW_ID, (
        "an update must not erase a workflow link it did not write"
    )


# ---------------------------------------------------------------------------
# Authorization — the owner-scoped gate
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_non_owner_cannot_link_someone_elses_public_task(
    engine: Any,
) -> None:
    """A PUBLIC task is still owner-scoped for linking.

    The visibility filter lets anyone READ a public task — and write it,
    via ``tasks_update``. But ``workflow_id`` is a server-set field: a
    link asserts "this task is running under that workflow". Letting any
    caller bind a public task to a workflow it never dispatched would
    forge that assertion, and the orphan sweeper trusts it.
    """
    _reset_limiters()
    owner_ctx = _make_ctx({"user_email": "les@example.com"})
    other_ctx = _make_ctx({"user_email": "stranger@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(tasks_tools, "_update_reflection", new=AsyncMock()),
    ):
        created = await _create_task(owner_ctx)
        # Make the task public so the visibility filter passes for a
        # stranger — the owner check is then the only thing standing.
        await tasks_tools.tasks_update(
            owner_ctx,
            task_id=created.id,
            request=UpdateTaskRequest(visibility="public"),
        )
        result = await tasks_tools.tasks_link_workflow(
            other_ctx,
            task_id=created.id,
            workflow_id="wf_99999999_forged",
        )

    assert isinstance(result, dict)
    assert result.get("error_code") == "not_found", (
        "a non-owner must not be able to link a public task"
    )

    with patch.object(
        tasks_tools,
        "_read_reflection",
        new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
    ):
        fetched = await tasks_tools.tasks_get(owner_ctx, task_id=created.id)
    assert isinstance(fetched, Task)
    assert fetched.workflow_id is None


@pytest.mark.unit
async def test_a_configured_service_principal_may_link(engine: Any) -> None:
    """An allow-listed service principal may link a task it does not own.

    That is how mahavishnu's orphan sweeper recovers a task on behalf of
    the dispatch edge without opening the channel to every caller.
    """
    _reset_limiters()
    owner_ctx = _make_ctx({"user_email": "les@example.com"})
    sweeper_ctx = _make_ctx({"agent_id": "mahavishnu-orphan-sweeper"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
        patch.object(
            tasks_tools,
            "_may_link",
            new=lambda caller, _task: caller == "agent:mahavishnu-orphan-sweeper",
        ),
    ):
        created = await _create_task(owner_ctx)
        result = await tasks_tools.tasks_link_workflow(
            sweeper_ctx,
            task_id=created.id,
            workflow_id=_WORKFLOW_ID,
        )

    assert isinstance(result, Task)
    assert result.workflow_id == _WORKFLOW_ID
    assert result.workflow_linked_by == "agent:mahavishnu-orphan-sweeper"


@pytest.mark.unit
async def test_may_link_is_closed_by_default(engine: Any) -> None:
    """With no allow-list configured, only the owner may link."""
    from session_buddy.mcp.tools.tasks_models import Task as TaskModel

    task = TaskModel(
        id="t-" + "0" * 32,
        content="a task",
        owner="user:les@example.com",
        tags=["task"],
        created_at=_NOW,
        updated_at=_NOW,
    )
    assert tasks_tools._may_link("user:les@example.com", task) is True
    assert tasks_tools._may_link("agent:someone-else", task) is False


# ---------------------------------------------------------------------------
# Atomicity — the link-once invariant
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_conflicting_link_is_refused_atomically(engine: Any) -> None:
    """Two different workflows cannot both win the link.

    The decision is made by a conditional UPDATE in the storage layer,
    so the second writer matches zero rows and is refused — rather than
    overwriting the first binding.
    """
    from session_buddy.mcp.tools import tasks_link_storage

    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        reflection_id = tasks_tools._find_reflection_id_by_task_id(
            engine=engine,
            task_id=created.id,
        )
        assert reflection_id is not None

        first = tasks_link_storage.link_task_workflow(
            engine,
            reflection_id,
            "wf_first",
            linked_at="2026-10-30T00:00:00+00:00",
            linked_by="user:les@example.com",
            updated_at="2026-10-30T00:00:00+00:00",
            history=[],
        )
        second = tasks_link_storage.link_task_workflow(
            engine,
            reflection_id,
            "wf_second",
            linked_at="2026-10-30T00:00:01+00:00",
            linked_by="user:les@example.com",
            updated_at="2026-10-30T00:00:01+00:00",
            history=[],
        )
        # A re-link to the SAME id is idempotent, not a conflict.
        same = tasks_link_storage.link_task_workflow(
            engine,
            reflection_id,
            "wf_first",
            linked_at="2026-10-30T00:00:02+00:00",
            linked_by="user:les@example.com",
            updated_at="2026-10-30T00:00:02+00:00",
            history=[],
        )

    assert first == tasks_link_storage.LINK_OUTCOME_LINKED
    assert second == tasks_link_storage.LINK_OUTCOME_ALREADY_LINKED
    assert same == tasks_link_storage.LINK_OUTCOME_LINKED

    blob = tasks_storage.read_task_metadata(engine=engine, reflection_id=reflection_id)
    assert blob is not None
    assert blob["workflow_id"] == "wf_first", "the first link must stand"


@pytest.mark.unit
async def test_linking_a_missing_task_reports_not_found(engine: Any) -> None:
    from session_buddy.mcp.tools import tasks_link_storage

    outcome = tasks_link_storage.link_task_workflow(
        engine,
        "no-such-reflection",
        "wf_x",
        linked_at="2026-10-30T00:00:00+00:00",
        linked_by="user:les@example.com",
        updated_at="2026-10-30T00:00:00+00:00",
        history=[],
    )
    assert outcome == tasks_link_storage.LINK_OUTCOME_NOT_FOUND


# ---------------------------------------------------------------------------
# C5 — path-safety of the workflow id
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_dot_segments_are_rejected(engine: Any) -> None:
    """".", ".." and friends are path-traversal segments.

    The workflow id is spliced into a substrate key path on the
    mahavishnu side (``workflow-results/{workflow_id}/``). They match the
    character class, so they need their own rule.
    """
    _reset_limiters()
    ctx = _make_ctx({"user_email": "les@example.com"})

    with (
        patch.object(tasks_tools, "store_reflection", new=_store_reflection_mock()),
        patch.object(tasks_tools, "publish_task_event", new=AsyncMock()),
        patch.object(
            tasks_tools,
            "_read_reflection",
            new=AsyncMock(side_effect=lambda rid: _reflection_for(rid)),
        ),
    ):
        created = await _create_task(ctx)
        for bad in (".", ".."):
            result = await tasks_tools.tasks_link_workflow(
                ctx,
                task_id=created.id,
                workflow_id=bad,
            )
            assert isinstance(result, dict), f"{bad!r} should not link"
            assert result.get("error_code") == "invalid_workflow_id", bad


@pytest.mark.unit
async def test_the_model_rejects_a_malformed_workflow_id(engine: Any) -> None:
    """``Task.workflow_id`` is validated on read-back, not only on write.

    A value that reached the row by any other route cannot be served as
    a valid task.
    """
    from pydantic import ValidationError

    from session_buddy.mcp.tools.tasks_models import Task as TaskModel

    with pytest.raises(ValidationError):
        TaskModel(
            id="t-" + "0" * 32,
            content="a task",
            owner="user:les@example.com",
            tags=["task"],
            workflow_id="not a valid id",
            created_at=_NOW,
            updated_at=_NOW,
        )
