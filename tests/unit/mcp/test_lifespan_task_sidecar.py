"""Unit test: ``session_lifecycle`` points the task sidecar at a durable file.

The task sidecar is where task metadata LIVES. The DuckDB reflection row
carries the content and the tags, but the values -- ``owner``,
``created_at``, ``task_id``, the change history -- are in the sidecar,
and ``tasks_list`` / ``tasks_get`` discover tasks through it.

``tasks_storage.get_engine`` defaults to in-memory SQLite, so a server
that never wires a file-backed engine starts every boot with an empty
sidecar: ``tasks_list`` returns nothing, ``tasks_get`` 404s, and every
task created before the restart is gone -- including one a workflow was
dispatched against.

This test pins the wiring that makes the sidecar durable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy import server_optimized
from session_buddy.mcp.tools import tasks_storage


@pytest.fixture
def stubbed_lifespan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Drive ``session_lifecycle`` with every side effect stubbed out.

    Yields the resolved sidecar path.
    """
    monkeypatch.chdir(tmp_path)

    sidecar_path = tmp_path / "data" / "tasks_metadata.sqlite"

    from session_buddy import settings as _settings_mod

    class _StubBodaiEvents:
        stream = "bodai:events"
        consumer_group = "bodai-default"
        enabled = False

    class _StubTaskMetadata:
        enabled = True
        path = sidecar_path

    class _StubSession:
        auto_checkpoint_interval = 0
        midpoint_commit_interval_s = 0
        midpoint_commits_enabled = False
        midpoint_commit_min_quality_delta = 10

    class _StubSettings:
        bodai_events = _StubBodaiEvents()
        task_metadata = _StubTaskMetadata()
        session = _StubSession()

    monkeypatch.setattr(_settings_mod, "get_settings", lambda: _StubSettings())
    monkeypatch.setattr(
        _settings_mod,
        "get_task_metadata_path",
        lambda: sidecar_path,
    )

    # Redis transport: stubbed so no server is required.
    from oneiric.adapters.queue.redis_streams import RedisStreamsQueueAdapter

    async def _fake_init(self) -> None:
        """Stand in for the Redis handshake."""

    async def _fake_enqueue(self, data) -> str:
        return "1-0"

    monkeypatch.setattr(RedisStreamsQueueAdapter, "init", _fake_init)
    monkeypatch.setattr(RedisStreamsQueueAdapter, "enqueue", _fake_enqueue)

    monkeypatch.setattr(
        server_optimized,
        "lifecycle_manager",
        MagicMock(
            drain_pending_markers=AsyncMock(),
            end_session=AsyncMock(return_value={"success": True}),
        ),
    )
    monkeypatch.setattr(server_optimized, "is_git_repository", lambda _path: False)

    async def _noop_dhara_register(*_a, **_kw):
        return None

    monkeypatch.setattr(
        server_optimized,
        "_register_component_to_dhara",
        _noop_dhara_register,
    )
    monkeypatch.setattr(server_optimized, "_delayed_session_init", AsyncMock())
    monkeypatch.setattr(server_optimized, "_report_runtime_to_oneiric", AsyncMock())

    async def _no_loop(_settings):
        return None

    monkeypatch.setattr(
        "session_buddy.mcp.autocheckpoint_lifespan.start_autocheckpoint_loop",
        _no_loop,
    )

    # The lifespan replaces the module-level engine; restore the original
    # so this test cannot leak into the next one.
    original = tasks_storage._engine
    try:
        yield sidecar_path
    finally:
        tasks_storage.set_engine(original)


@pytest.mark.unit
async def test_lifespan_wires_a_file_backed_sidecar(stubbed_lifespan) -> None:
    """After the lifespan runs, the sidecar engine must be file-backed."""
    cm = server_optimized.session_lifecycle(MagicMock())
    async with cm:
        pass

    engine = tasks_storage.get_engine()
    database = engine.url.database
    assert database is not None, "the sidecar engine must not be in-memory"
    assert database == str(stubbed_lifespan), (
        f"expected the sidecar at {stubbed_lifespan}; got {database}"
    )


@pytest.mark.unit
async def test_the_sidecar_file_is_created_on_disk(stubbed_lifespan) -> None:
    """The parent directory is created and the file exists after a write."""
    cm = server_optimized.session_lifecycle(MagicMock())
    async with cm:
        pass

    assert stubbed_lifespan.parent.is_dir(), "the sidecar's parent must exist"

    tasks_storage.persist_task_metadata(
        tasks_storage.get_engine(),
        "reflection-1",
        {"kind": "task", "owner": "user:les"},
    )
    assert stubbed_lifespan.exists(), "the sidecar file must exist on disk"


@pytest.mark.unit
async def test_the_sidecar_file_is_owner_only(stubbed_lifespan) -> None:
    """The sidecar holds task content and the owner's identity.

    It is created with owner-only permissions before SQLite opens it --
    SQLite inherits the mode of an existing file rather than applying its
    own umask, so creating it first is what makes the mode stick.
    """
    cm = server_optimized.session_lifecycle(MagicMock())
    async with cm:
        pass

    assert stubbed_lifespan.exists()
    mode = stubbed_lifespan.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600 on the sidecar; got {mode:o}"


@pytest.mark.unit
async def test_a_disabled_sidecar_leaves_the_default_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """``task_metadata.enabled = false`` keeps the in-memory default.

    The in-memory engine is the pre-existing behaviour, so an operator
    who turns the sidecar off gets exactly that -- no file, no crash.
    """
    monkeypatch.chdir(tmp_path)

    from session_buddy import settings as _settings_mod

    class _StubBodaiEvents:
        stream = "bodai:events"
        consumer_group = "bodai-default"
        enabled = False

    class _StubTaskMetadata:
        enabled = False
        path = tmp_path / "tasks_metadata.sqlite"

    class _StubSession:
        auto_checkpoint_interval = 0
        midpoint_commit_interval_s = 0
        midpoint_commits_enabled = False
        midpoint_commit_min_quality_delta = 10

    class _StubSettings:
        bodai_events = _StubBodaiEvents()
        task_metadata = _StubTaskMetadata()
        session = _StubSession()

    monkeypatch.setattr(_settings_mod, "get_settings", lambda: _StubSettings())

    from oneiric.adapters.queue.redis_streams import RedisStreamsQueueAdapter

    async def _fake_init(self) -> None:
        """Stand in for the Redis handshake."""

    async def _fake_enqueue(self, data) -> str:
        return "1-0"

    monkeypatch.setattr(RedisStreamsQueueAdapter, "init", _fake_init)
    monkeypatch.setattr(RedisStreamsQueueAdapter, "enqueue", _fake_enqueue)

    monkeypatch.setattr(
        server_optimized,
        "lifecycle_manager",
        MagicMock(
            drain_pending_markers=AsyncMock(),
            end_session=AsyncMock(return_value={"success": True}),
        ),
    )
    monkeypatch.setattr(server_optimized, "is_git_repository", lambda _path: False)

    async def _noop_dhara_register(*_a, **_kw):
        return None

    monkeypatch.setattr(
        server_optimized,
        "_register_component_to_dhara",
        _noop_dhara_register,
    )
    monkeypatch.setattr(server_optimized, "_delayed_session_init", AsyncMock())
    monkeypatch.setattr(server_optimized, "_report_runtime_to_oneiric", AsyncMock())

    async def _no_loop(_settings):
        return None

    monkeypatch.setattr(
        "session_buddy.mcp.autocheckpoint_lifespan.start_autocheckpoint_loop",
        _no_loop,
    )

    original = tasks_storage._engine
    try:
        tasks_storage.set_engine(None)
        cm = server_optimized.session_lifecycle(MagicMock())
        async with cm:
            pass

        engine = tasks_storage.get_engine()
        database = engine.url.database
        assert database in (None, ":memory:"), (
            f"a disabled sidecar must stay in-memory; got {database}"
        )
    finally:
        tasks_storage.set_engine(original)
