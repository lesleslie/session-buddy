"""Bodai task events publisher — owns the oneiric Redis Streams adapter."""

from __future__ import annotations

import logging
import time

from oneiric.adapters.queue.redis_streams import (
    RedisStreamsQueueAdapter,
    RedisStreamsQueueSettings,
)
from opentelemetry import trace
from pydantic import BaseModel

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


class BodaiEventsPublisher:
    """Owns the oneiric Redis Streams adapter for the ``bodai:events`` stream.

    Singleton on the FastMCP server (one per process).

    Lifecycle: ``init()`` on FastMCP startup, ``cleanup()`` on shutdown,
    ``health()`` called by ``/health``.

    Failure semantics: ``_init_transport()`` exceptions are LOGGED + SWALLOWED.
    Server starts anyway and ``publish`` no-ops. Mutation path MUST NOT block
    on Redis.

    Writes flat fields via ``adapter.enqueue()`` — ``channel`` is the event
    type, rest of payload is XADD'd as top-level fields. Consumers filter on
    ``channel`` (in entry["payload"]) without JSON-deserializing.

    §3 counters (per mcp-backend-wiring-discipline.md):
      - cycles_total: every publish() call attempt.
      - errors_total: caught exceptions.
      - entities_count: successful enqueue.
      - last_updated_timestamp: most recent successful enqueue.

    OTel span (per mcp-backend-wiring-discipline.md §4):
      - bodai_events.publish: attributes event_type, task_id, outcome
        ∈ {success, failure, disabled}.
    """

    def __init__(
        self,
        *,
        stream: str = "bodai:events",
        consumer_group: str = "bodai-default",
        enabled: bool = True,
    ) -> None:
        self._settings = RedisStreamsQueueSettings(
            stream=stream,
            group=consumer_group,
        )
        self._adapter = RedisStreamsQueueAdapter(settings=self._settings)
        self.enabled = enabled
        self.entities_count = 0
        self.cycles_total = 0
        self.errors_total = 0
        self.last_updated_timestamp: float = 0.0
        # Tracks whether _init_transport() completed at least once; used by
        # health() to report degraded when the transport never came up.
        self._init_ok: bool = False

    async def _init_transport(self) -> None:
        await self._adapter.init()

    async def init(self) -> None:
        if not self.enabled:
            return
        try:
            await self._init_transport()
            self._init_ok = True
        except Exception as exc:  # noqa: BLE001 — degraded-to-noop by design
            logger.warning(
                "bodai_events: publisher init failed (degraded to no-op): %s",
                exc,
            )

    async def cleanup(self) -> None:
        try:
            await self._adapter.cleanup()
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.warning("bodai_events: cleanup failed: %s", exc)

    async def health(self) -> bool:
        if not self.enabled:
            return True
        if not self._init_ok:
            return False
        return self.errors_total == 0 or self.entities_count > 0

    async def publish(
        self,
        event_type: str,
        payload: BaseModel,
    ) -> str | None:
        task_id = getattr(payload, "task_id", None) or "unknown"
        with _tracer.start_as_current_span("bodai_events.publish") as span:
            span.set_attribute("event_type", event_type)
            span.set_attribute("task_id", str(task_id))
            if not self.enabled:
                span.set_attribute("outcome", "disabled")
                return None
            self.cycles_total += 1
            try:
                data = {"channel": event_type} | payload.model_dump(mode="json")
                message_id = await self._adapter.enqueue(data)
            except Exception as exc:  # noqa: BLE001 — degrade gracefully per spec
                self.errors_total += 1
                span.set_attribute("outcome", "failure")
                logger.warning("bodai_events: enqueue %s failed: %s", event_type, exc)
                return None
            span.set_attribute("outcome", "success")
            self.entities_count += 1
            self.last_updated_timestamp = time.time()
            return message_id
