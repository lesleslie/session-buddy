"""Unit tests for ``session_buddy.mcp.events.bodai_events_publisher``.

Per the Task 2 brief, these tests pin:

- Settings mapping: ``consumer_group`` kwarg maps to ``RedisStreamsQueueSettings.group``.
- Lifecycle: ``init()`` swallows transport failures, ``health()`` reports degraded.
- Publish success: returns ``message_id``, increments ``entities_count`` + ``cycles_total``,
  payload is XADD'd with ``channel`` first.
- Publish failure: returns ``None``, increments ``errors_total`` + ``cycles_total``,
  leaves ``entities_count`` at 0.
- Publish disabled: returns ``None`` without ticking counters.
- OTel span ``bodai_events.publish`` carries ``event_type``, ``task_id``, ``outcome``.
- Heartbeat: writes the liveness channel, populates the feed counters, and
  counts (rather than raises) a transport failure.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from session_buddy.mcp.events.bodai_events_publisher import (
    HEARTBEAT_CHANNEL,
    BodaiEventsPublisher,
)
from session_buddy.mcp.tools.tasks_events import TaskCreatedPayload

# Canonical task_id matching tasks_events.TASK_ID_PATTERN = r"^t-[0-9a-f]{32}$".
_VALID_TASK_ID = "t-" + "0" * 32
_NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _payload() -> TaskCreatedPayload:
    """Build a valid TaskCreatedPayload for publish tests."""
    return TaskCreatedPayload(
        task_id=_VALID_TASK_ID,
        owner="alice",
        actor="alice",
        created_at=_NOW,
        content_hash="a" * 64,
    )


def test_consumer_group_maps_to_group_in_settings() -> None:
    """``consumer_group`` kwarg maps to ``RedisStreamsQueueSettings.group``;
    the default ``stream`` flows through as ``bodai:events``."""
    pub = BodaiEventsPublisher(consumer_group="my-group")
    assert pub._settings.group == "my-group"
    assert pub._settings.stream == "bodai:events"


@pytest.mark.asyncio
async def test_publisher_init_failure_is_swallowed(monkeypatch) -> None:
    """``_init_transport`` raising must NOT propagate out of ``init()``;
    a degraded publisher reports ``health() is False``."""
    pub = BodaiEventsPublisher()

    async def boom() -> None:
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(pub._adapter, "init", boom)
    await pub.init()  # must NOT raise
    assert await pub.health() is False


@pytest.mark.asyncio
async def test_publish_with_publisher_enqueues(monkeypatch) -> None:
    """Successful publish returns the message_id, increments
    ``entities_count`` + ``cycles_total``, and stamps ``channel`` first."""
    pub = BodaiEventsPublisher()
    seen: list[dict] = []

    async def fake_enqueue(data: dict) -> str:
        seen.append(data)
        return "1-0"

    monkeypatch.setattr(pub._adapter, "enqueue", fake_enqueue)
    msg_id = await pub.publish("task.created", _payload())
    assert msg_id == "1-0"
    assert seen[0]["channel"] == "task.created"
    assert seen[0]["task_id"] == _VALID_TASK_ID
    assert pub.entities_count == 1
    assert pub.cycles_total == 1


@pytest.mark.asyncio
async def test_publish_failure_increments_errors(monkeypatch) -> None:
    """Caught enqueue exceptions return ``None``, bump ``errors_total`` +
    ``cycles_total``, and leave ``entities_count`` at 0."""
    pub = BodaiEventsPublisher()

    async def boom(data: dict) -> str:
        raise RuntimeError("redis down")

    monkeypatch.setattr(pub._adapter, "enqueue", boom)
    msg_id = await pub.publish("task.created", _payload())
    assert msg_id is None
    assert pub.errors_total == 1
    assert pub.cycles_total == 1
    assert pub.entities_count == 0


@pytest.mark.asyncio
async def test_publish_disabled_returns_none() -> None:
    """Disabled publisher never calls into the transport and never ticks
    ``cycles_total`` (per §3 counter semantics)."""
    pub = BodaiEventsPublisher(enabled=False)
    msg_id = await pub.publish("task.created", _payload())
    assert msg_id is None
    assert pub.cycles_total == 0


@pytest.mark.asyncio
async def test_publish_emits_otel_span_on_success(monkeypatch) -> None:
    """Successful publish emits a ``bodai_events.publish`` OTel span with
    ``event_type``, ``task_id``, and ``outcome == success``."""
    # Force a clean tracer provider so the publisher's tracer captures
    # the span (otherwise OTel returns a NoOp tracer by default).
    previous_provider = trace.get_tracer_provider()
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    try:
        pub = BodaiEventsPublisher()

        async def fake_enqueue(data: dict) -> str:
            return "1-0"

        monkeypatch.setattr(pub._adapter, "enqueue", fake_enqueue)
        await pub.publish("task.created", _payload())
    finally:
        trace.set_tracer_provider(previous_provider)

    spans = exporter.get_finished_spans()
    bodai_spans = [s for s in spans if s.name == "bodai_events.publish"]
    assert bodai_spans, (
        f"expected bodai_events.publish span, got: {[s.name for s in spans]}"
    )
    span = bodai_spans[0]
    assert span.attributes["event_type"] == "task.created"
    assert span.attributes["task_id"] == _VALID_TASK_ID
    assert span.attributes["outcome"] == "success"


@pytest.mark.asyncio
async def test_health_true_when_disabled() -> None:
    """Disabled publisher reports healthy — no-op mode is intentional."""
    pub = BodaiEventsPublisher(enabled=False)
    assert await pub.health() is True


# ---------------------------------------------------------------------------
# Heartbeat — the boot-time liveness marker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_heartbeat_writes_the_liveness_channel(monkeypatch) -> None:
    """The heartbeat is a real enqueue on its own channel.

    It must NOT reuse the ``task.*`` namespace: that namespace is
    reserved for the task system's envelopes, and a consumer keying off
    ``task.*`` must not see a non-task event.
    """
    pub = BodaiEventsPublisher()
    seen: list[dict] = []

    async def fake_enqueue(data: dict) -> str:
        seen.append(data)
        return "42-0"

    monkeypatch.setattr(pub._adapter, "enqueue", fake_enqueue)
    msg_id = await pub.publish_heartbeat(component="session-buddy")

    assert msg_id == "42-0"
    assert seen[0]["channel"] == HEARTBEAT_CHANNEL
    assert not HEARTBEAT_CHANNEL.startswith("task.")
    assert seen[0]["component"] == "session-buddy"
    assert seen[0]["pid"] > 0
    assert seen[0]["hostname"]


@pytest.mark.asyncio
async def test_publish_heartbeat_populates_the_feed_counters(monkeypatch) -> None:
    """The heartbeat is what makes ``entities_count`` non-zero at boot.

    Without it the publisher-shaped feed reads ``warming_up`` — an empty
    feed with a running ingester — until the first task event happens
    to be published, and the counter resets on every restart.
    """
    pub = BodaiEventsPublisher()

    async def fake_enqueue(data: dict) -> str:
        return "1-0"

    monkeypatch.setattr(pub._adapter, "enqueue", fake_enqueue)
    await pub.publish_heartbeat()

    assert pub.entities_count == 1
    assert pub.cycles_total == 1
    assert pub.errors_total == 0
    assert pub.last_updated_timestamp > 0


@pytest.mark.asyncio
async def test_publish_heartbeat_failure_is_counted_not_raised(monkeypatch) -> None:
    """A transport failure must be counted, not raised.

    ``publish()`` swallows the exception and bumps ``errors_total``, which
    makes the feed read ``degraded`` — a publisher that cannot write is
    genuinely degraded, so the failure is deliberately visible.
    """
    pub = BodaiEventsPublisher()

    async def boom(data: dict) -> str:
        raise RuntimeError("redis down")

    monkeypatch.setattr(pub._adapter, "enqueue", boom)
    msg_id = await pub.publish_heartbeat()

    assert msg_id is None
    assert pub.errors_total == 1
    assert pub.entities_count == 0


@pytest.mark.asyncio
async def test_publish_heartbeat_is_a_noop_when_disabled() -> None:
    """A disabled publisher must not tick any counter."""
    pub = BodaiEventsPublisher(enabled=False)
    msg_id = await pub.publish_heartbeat()

    assert msg_id is None
    assert pub.entities_count == 0
    assert pub.cycles_total == 0
    assert pub.errors_total == 0
