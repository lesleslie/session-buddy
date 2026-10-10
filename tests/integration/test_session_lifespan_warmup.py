"""Regression test for the launchd-restart loop observed 2026-10-10.

Session-Buddy's ``/health`` endpoint aggregates two data feeds via
``mcp_common.health.aggregator.aggregate_feed_states``:

1. ``skills_signer`` — initialized by ``init_signer_feed_state()``
   inside ``session_lifecycle`` before the ``yield``.
2. ``bodai_events`` — the ``BodaiEventsPublisher`` singleton at
   ``tasks_events._publisher``.

When either feed reports ``ingester_running=False`` with
``cycles_total == 0``, the aggregator evaluates the
``FEED_NEVER_POPULATED + INGESTER_NOT_RUNNING`` branch and returns
``StatusValue.FAILED`` (see ``mcp-common/health/feed.py:213``). The
HTTP route at ``session_buddy/server_optimized.py:530`` then
translates that to **503**.

``launch_with_healthcheck.sh`` interprets a 60-second window of
503 as "did not become healthy" → SIGTERM → exit 1 →
``launchctl``'s ``KeepAlive.Crashed=true`` restarts the process
every 5 seconds. The result is a 23 MB error log full of repeated
startup banners and a perpetually-refused MCP connection from
Claude Code (``ECONNREFUSED`` at ``http://localhost:8678/mcp``).

This test pins the contract: after ``session_lifecycle`` runs to
its first ``yield``, BOTH data-feed singletons must be populated
so the aggregator sees ``ingester_running=True`` for both feeds.

The regression surfaced because the lifespan in
``server_optimized.py:228-284`` initialises the skills_signer feed
but never installs the bodai_events publisher — that install lives
in a *different* lifespan at ``session_buddy/mcp/server.py:436``
that is not wired into the running ``mcp`` instance (see the
``fastmcp.FastMCP(..., lifespan=session_lifecycle)`` call at
``server_optimized.py:287``).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import session_buddy.mcp.tools.tasks_events as tasks_events_mod
from session_buddy import server_optimized as so
from session_buddy.mcp.signer_feed import (
    SignerFeedState,
    reset_signer_feed_state,
)
from session_buddy.skills_signer import (
    SkillsSigner,
    build_pubkey_manifest,
    generate_keypair,
)


def _install_synthetic_signer() -> SignerFeedState:
    """Hermetic signer singleton without PEM disk I/O."""
    from session_buddy.mcp import signer_feed as signer_feed_mod

    keypair = generate_keypair()
    manifest = build_pubkey_manifest(keypair)
    signer = SkillsSigner.from_keypair(keypair)
    state = SignerFeedState(manifest=manifest, signer=signer)
    signer_feed_mod._signer_feed_state = state
    return state


def _clear_publisher() -> None:
    """Reset the bodai_events publisher singleton (test cleanup)."""
    tasks_events_mod._publisher = None


@asynccontextmanager
async def _drive_session_lifecycle(app: Any) -> AsyncGenerator[None]:
    """Drive ``session_lifecycle`` end-to-end with hermetic stubs.

    The post-yield block schedules three background tasks
    (Dhara registration, delayed session init, lifecycle_manager
    end-of-session). Without mocks those touch real network and
    git state. Each is replaced with an ``AsyncMock`` that returns
    immediately so the async-with exit cleans up cleanly.
    """
    with (
        patch.object(
            so.lifecycle_manager,
            "drain_pending_markers",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            so,
            "_delayed_session_init",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            so,
            "_register_component_to_dhara",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            so.lifecycle_manager,
            "end_session",
            new=AsyncMock(return_value={"success": True}),
        ),
    ):
        async with so.session_lifecycle(app):
            yield


@pytest.mark.integration
async def test_session_lifespan_installs_bodai_events_publisher() -> None:
    """After ``session_lifecycle`` reaches its first ``yield``, the
    ``bodai_events`` publisher singleton must be populated.

    Without this, ``_build_health_snapshot`` at
    ``session_buddy/server_optimized.py:411-418`` builds a
    ``HealthFeedState(entities_count=0, cycles_total=0,
    ingester_running=False)``. The aggregator branch 2b at
    ``mcp_common/health/feed.py:213`` returns
    ``StatusValue.FAILED`` and ``/health`` answers 503 —
    reproducibly causing the launchd keepalive restart loop
    observed 2026-10-10.
    """
    _install_synthetic_signer()
    _clear_publisher()

    from session_buddy.mcp.events.bodai_events_publisher import (
        BodaiEventsPublisher,
    )

    def _make_fake_publisher(*_args: Any, **_kwargs: Any) -> MagicMock:
        publisher = MagicMock(spec=BodaiEventsPublisher)
        publisher.entities_count = 0
        publisher.cycles_total = 0
        publisher.errors_total = 0
        publisher.last_updated_timestamp = None
        publisher.enabled = True
        publisher._init_ok = True
        publisher.init = AsyncMock(return_value=None)  # type: ignore[method-assign]
        return publisher

    publisher_factory_patch = MagicMock(
        side_effect=_make_fake_publisher,
    )

    with patch(
        "session_buddy.mcp.events.bodai_events_publisher.BodaiEventsPublisher",
        new=publisher_factory_patch,
    ):
        async with _drive_session_lifecycle(app=None):
            assert tasks_events_mod._publisher is not None, (
                "Regression 2026-10-10: session_lifecycle reached "
                "yield with tasks_events._publisher still None. "
                "_build_health_snapshot then reports "
                "ingester_running=False for bodai_events → "
                "aggregate returns FAILED → /health=503 → "
                "launch_with_healthcheck.sh kills the process → "
                "KeepAlive restart loop → ECONNREFUSED."
            )

    _clear_publisher()
    reset_signer_feed_state()
