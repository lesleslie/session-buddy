"""End-to-end Redis round-trip test for ``BodaiEventsPublisher``.

Proves the publisher's XADD lands in Redis and is XREADGROUP-able by the
same consumer group the publisher auto-creates. Gated by
``requires_network`` so CI runners without a hot Redis skip cleanly; the
unit-test suite already covers the schema/validation contract.

Verification side uses ``redis.asyncio`` (redis-py 8.x — already a direct
session-buddy dep). The publisher under test uses oneiric's
``coredis`` adapter against the same Redis URL; both speak the Redis
protocol so we only need a compatible client on the read side.
"""

from __future__ import annotations

import socket
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_network,
]


REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"


def _redis_reachable(timeout: float = 0.5) -> bool:
    """TCP-probe the local Redis server — no protocol chatter, just socket reach."""
    try:
        with socket.create_connection((REDIS_HOST, REDIS_PORT), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """Yield a redis-py async ``Redis`` client connected to the local Redis instance.

    The publisher under test owns its own coredis client pool; this
    fixture only handles the verification-side connection.
    """
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
        yield client
    finally:
        await client.aclose()


async def test_publisher_xadds_to_bodai_events(redis_client: Redis) -> None:
    """XADD lands in Redis and the same consumer group can XREADGROUP it back."""
    if not _redis_reachable():
        pytest.skip("Redis not reachable on localhost:6379; requires_network env only.")

    from session_buddy.mcp.events.bodai_events_publisher import BodaiEventsPublisher
    from session_buddy.mcp.tools.tasks_events import TaskCreatedPayload

    # Unique stream + consumer group per run to avoid clobbering prod data.
    suffix = uuid.uuid4().hex[:12]
    stream = f"bodai:events:test-{suffix}"
    group = f"test-group-{suffix}"
    consumer = f"test-consumer-{suffix}"

    publisher = BodaiEventsPublisher(stream=stream, consumer_group=group)
    await publisher.init()
    try:
        assert await publisher.health() is True, (
            "publisher health degraded after init; check Redis is up"
        )

        task_id = "t-" + "0" * 32
        payload = TaskCreatedPayload(
            task_id=task_id,
            owner="test-owner",
            actor="test-actor",
            created_at=datetime.now(UTC),
            content_hash="a" * 64,
        )

        msg_id = await publisher.publish("task.created", payload)
        assert msg_id is not None, "publish returned None; Redis unreachable?"

        # XREADGROUP with the special ">" id returns only undelivered ones.
        # block=0 = fire-and-forget (no waiting). We just published so it's there.
        entries = await redis_client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=1,
            block=0,
        )
        assert len(entries) == 1, f"expected 1 stream entry, got {entries}"
        stream_key, msgs = entries[0]
        assert stream_key == stream
        assert msgs[0][1]["channel"] == "task.created"
        assert msgs[0][1]["task_id"] == task_id
    finally:
        await publisher.cleanup()


def test_redis_probe_helper_returns_bool() -> None:
    """Sanity-check the connectivity gate — should never raise."""
    result = _redis_reachable()
    assert isinstance(result, bool)


async def test_publisher_init_failure_does_not_raise() -> None:
    """Init must swallow transport failures (degraded-to-noop by design)."""
    if not _redis_reachable():
        pytest.skip("Redis not reachable on localhost:6379; requires_network env only.")

    from session_buddy.mcp.events.bodai_events_publisher import BodaiEventsPublisher

    # Point at an unused port to force init() to swallow the connection error.
    bad_port_publisher = BodaiEventsPublisher(
        stream="bodai:events:test-unused",
        consumer_group="test-group-unused",
        enabled=True,
    )
    # Override the internal settings url to a dead port before init().
    bad_port_publisher._settings.url = "redis://127.0.0.1:1/0"
    await bad_port_publisher.init()  # must NOT propagate the connection refused error
    assert await bad_port_publisher.health() is False
    # publish against a degraded publisher returns None and increments errors.
    msg_id = await bad_port_publisher.publish("task.created", _DummyPayload())
    assert msg_id is None
    assert bad_port_publisher.errors_total >= 1
    await bad_port_publisher.cleanup()


class _DummyPayload:
    """Minimal payload stub — the bad-port branch never round-trips through schema."""

    task_id = "t-stub"

    def model_dump(self, mode: str = "python") -> dict[str, str]:
        return {"task_id": self.task_id}
