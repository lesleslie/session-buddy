"""Unit test: ``session_lifecycle`` populates the ``bodai_events`` feed at boot.

The ``bodai_events`` feed is *publisher*-shaped — ``entities_count`` counts
successful enqueues, not records read. A publisher that has published
nothing is idle rather than broken, but the feed model has no way to
express "idle": an empty feed with a running ingester reads
``warming_up`` (``mcp_common/health/feed.py``), and the counter resets to
zero on every restart. So the feed went amber after each boot and only
turned green once the first task event happened to be published.

``session_lifecycle`` therefore publishes a liveness marker right after
installing the publisher. This test pins that contract end to end: the
lifespan must leave the feed populated, and the health snapshot built
from it must read ``healthy`` — not ``warming_up``.

The Redis transport is stubbed at the adapter boundary, so no Redis
round trip happens; everything above the transport is the real code.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from oneiric.adapters.queue.redis_streams import RedisStreamsQueueAdapter

from session_buddy import server_optimized
from session_buddy.mcp.tools import tasks_events


@pytest.fixture
def stubbed_lifespan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Drive ``session_lifecycle`` with every side effect stubbed out.

    Yields the list of XADD payloads the publisher wrote.
    """
    monkeypatch.chdir(tmp_path)

    written: list[dict] = []

    async def _fake_init(self) -> None:
        """Stand in for the Redis handshake — no server required."""

    async def _fake_enqueue(self, data) -> str:
        written.append(dict(data))
        return "1-0"

    monkeypatch.setattr(RedisStreamsQueueAdapter, "init", _fake_init)
    monkeypatch.setattr(RedisStreamsQueueAdapter, "enqueue", _fake_enqueue)

    # The signer feed is NOT stubbed: the aggregate verdict
    # (``data_feeds_ok``) spans both feeds, so the signer feed has to be
    # genuinely healthy for that assertion to mean anything.
    monkeypatch.setattr(
        server_optimized,
        "lifecycle_manager",
        MagicMock(
            drain_pending_markers=AsyncMock(),
            end_session=AsyncMock(return_value={"success": True}),
        ),
    )
    monkeypatch.setattr(server_optimized, "is_git_repository", lambda _path: False)

    monkeypatch.setattr(server_optimized, "_delayed_session_init", AsyncMock())
    monkeypatch.setattr(server_optimized, "_report_runtime_to_oneiric", AsyncMock())

    # No autocheckpoint loop: this test is about the publisher.
    async def _no_loop(_settings):
        return None

    monkeypatch.setattr(
        "session_buddy.mcp.autocheckpoint_lifespan.start_autocheckpoint_loop",
        _no_loop,
    )

    # Settings: the publisher must be enabled for the heartbeat to run.
    from session_buddy import settings as _settings_mod

    class _StubBodaiEvents:
        stream = "bodai:events"
        consumer_group = "bodai-default"
        enabled = True

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

    # The lifespan installs the publisher into a module-level slot; put
    # the original back so this test cannot leak into the next one.
    original = tasks_events._publisher
    try:
        yield written
    finally:
        tasks_events._publisher = original


@pytest.mark.unit
async def test_lifespan_publishes_the_liveness_marker(stubbed_lifespan) -> None:
    """The lifespan must publish exactly one heartbeat, on the liveness channel."""
    from session_buddy.mcp.events.bodai_events_publisher import HEARTBEAT_CHANNEL

    cm = server_optimized.session_lifecycle(MagicMock())
    async with cm:
        pass

    channels = [payload["channel"] for payload in stubbed_lifespan]
    assert channels == [HEARTBEAT_CHANNEL], (
        f"expected one heartbeat on {HEARTBEAT_CHANNEL!r}; got {channels}"
    )


@pytest.mark.unit
async def test_lifespan_leaves_the_feed_populated(stubbed_lifespan) -> None:
    """After the lifespan runs, the publisher's feed counters are non-zero.

    This is the property the heartbeat exists for: the counter must not
    read zero at boot, or the feed reads ``warming_up``.
    """
    cm = server_optimized.session_lifecycle(MagicMock())
    async with cm:
        pass

    publisher = tasks_events._publisher
    assert publisher is not None
    assert publisher.entities_count == 1
    assert publisher.cycles_total >= 1
    assert publisher.errors_total == 0
    assert publisher.last_updated_timestamp > 0


@pytest.mark.unit
async def test_health_snapshot_reads_healthy_after_the_lifespan(
    stubbed_lifespan,
) -> None:
    """The health snapshot must read ``healthy`` — not ``warming_up``.

    ``_build_health_snapshot`` is the single source of truth for the
    ``/health`` body (both the HTTP route and the ``get_health`` tool
    route through it), so asserting on it proves what an operator and
    the launchd healthcheck will see.
    """
    cm = server_optimized.session_lifecycle(MagicMock())
    async with cm:
        pass

    body = server_optimized._build_health_snapshot()
    checks = body["checks"]
    bodai = checks["bodai_events"]

    assert bodai["status"] == "healthy", (
        f"expected a healthy bodai_events feed; got {bodai}"
    )
    assert bodai["ok"] is True
    assert bodai["entities_count"] == 1
    assert checks["_aggregate"]["data_feeds_ok"] is True
