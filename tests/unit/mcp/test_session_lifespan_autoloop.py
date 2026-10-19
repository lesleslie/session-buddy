"""Unit test: session_lifecycle wires the AutoCheckpointLoop (plan 4b).

Plan 4 (commit ``c820d210``) deleted the dead
``_lifespan_with_dhara_cleanup`` wrapper. Plan 4b moves the
``AutoCheckpointLoop`` wiring from the wrapper into the canonical
``session_lifecycle`` in ``server_optimized.py``. This test pins the
new contract: ``session_lifecycle`` must invoke
``start_autocheckpoint_loop`` pre-yield and stop the returned loop on
lifespan exit (via the try/finally around the yield).

The test patches the ``start_autocheckpoint_loop`` entry point so we
can record start/stop invocations without spinning a real background
timer. The real loop's tick/stop behavior is exercised by
``tests/unit/core/checkpoint/test_auto_checkpoint_loop.py``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy import server_optimized


class _LoopStub:
    """Stub AutoCheckpointLoop returned by the patched start function."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


@pytest.mark.unit
async def test_session_lifecycle_starts_and_stops_autocheckpoint_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """``session_lifecycle`` must start the loop pre-yield and stop it on exit.

    Patches the entry point to record invocations. All other side
    effects (signer feed init, BodaiEventsPublisher install, lifecycle
    manager, dhara, delayed init, oneiric, end_session, is_git_repository)
    are stubbed so the test runs in a clean environment without real
    settings, Redis, or git repo.
    """
    # Pin cwd to a real directory so any cwd-dependent helper in
    # start_autocheckpoint_loop does not raise OrchestratorCwdInvalid.
    monkeypatch.chdir(tmp_path)

    started_loops: list[_LoopStub] = []

    async def _start_stub(_settings):
        # Mirror the production contract of
        # ``start_autocheckpoint_loop``: construct the loop, start it,
        # and return it. The lifespan is responsible for calling
        # ``stop()`` on the returned loop on exit.
        loop = _LoopStub()
        await loop.start()
        started_loops.append(loop)
        return loop

    # Patch the entry point that session_lifecycle calls inline. The
    # production function is async, so the patch must be async too —
    # otherwise `await start_autocheckpoint_loop(...)` would try to
    # await a non-coroutine.
    monkeypatch.setattr(
        "session_buddy.mcp.autocheckpoint_lifespan.start_autocheckpoint_loop",
        _start_stub,
    )

    # Stub every other side effect the lifespan performs.
    monkeypatch.setattr(
        server_optimized,
        "init_signer_feed_state",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        server_optimized,
        "lifecycle_manager",
        MagicMock(
            drain_pending_markers=AsyncMock(),
            end_session=AsyncMock(return_value={"success": True}),
        ),
    )
    monkeypatch.setattr(
        server_optimized,
        "is_git_repository",
        lambda _path: False,
    )
    # _register_component_to_dhara is invoked via asyncio.create_task
    # post-yield, so the patch must be async (create_task needs a
    # coroutine, not None).
    async def _noop_dhara_register(*_a, **_kw):
        return None

    monkeypatch.setattr(
        server_optimized,
        "_register_component_to_dhara",
        _noop_dhara_register,
    )
    monkeypatch.setattr(
        server_optimized,
        "_delayed_session_init",
        AsyncMock(),
    )
    monkeypatch.setattr(
        server_optimized,
        "_report_runtime_to_oneiric",
        AsyncMock(),
    )

    # Stub settings.get_settings() so the BodaiEventsPublisher install
    # path does not need real settings.
    from session_buddy import settings as _settings_mod

    class _StubBodaiEvents:
        stream = "bodai:events"
        consumer_group = "bodai-default"
        enabled = False

    class _StubSession:
        auto_checkpoint_interval = 0
        midpoint_commit_interval_s = 0
        midpoint_commits_enabled = False
        midpoint_commit_min_quality_delta = 10

    class _StubSettings:
        bodai_events = _StubBodaiEvents()
        session = _StubSession()

    monkeypatch.setattr(_settings_mod, "get_settings", lambda: _StubSettings())

    # BodaiEventsPublisher init must not raise. The lifespan catches
    # its exceptions and continues, so a real BodaiEventsPublisher
    # call would be a no-op even on failure. Stub the class so
    # ``BodaiEventsPublisher(...)`` returns a benign object whose
    # init() is an AsyncMock.
    from session_buddy.mcp.events.bodai_events_publisher import BodaiEventsPublisher

    fake_publisher = MagicMock(spec=BodaiEventsPublisher)
    fake_publisher._init_ok = True
    fake_publisher.cycles_total = 0
    fake_publisher.last_updated_timestamp = 0.0
    fake_publisher.init = AsyncMock()

    with monkeypatch.context() as mp:
        mp.setattr(
            "session_buddy.mcp.events.bodai_events_publisher.BodaiEventsPublisher",
            lambda **kw: fake_publisher,
        )

        # Drive the lifespan. Pre-yield, start_autocheckpoint_loop
        # must have been called and start() invoked on the returned
        # loop. On exit, stop() must have been invoked.
        cm = server_optimized.session_lifecycle(MagicMock())
        async with cm:
            # At this point the lifespan is between setup and yield —
            # the loop has been started. Defensive microtask yield
            # to let any pending start() complete (start is awaited
            # synchronously so this is a no-op in practice).
            await asyncio.sleep(0)

    assert len(started_loops) == 1, (
        f"expected exactly one start_autocheckpoint_loop call; got {len(started_loops)}"
    )
    loop = started_loops[0]
    # start() is called inside start_autocheckpoint_loop before the
    # return — verified by start_calls == 1.
    assert loop.start_calls == 1, (
        f"expected start_autocheckpoint_loop to start the loop; got start_calls={loop.start_calls}"
    )
    # stop() is the lifespan's responsibility — the try/finally around
    # the yield must invoke it once on exit.
    assert loop.stop_calls == 1, (
        f"expected the returned loop's stop() to be called on lifespan exit; "
        f"got {loop.stop_calls}"
    )
