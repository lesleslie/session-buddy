"""End-to-end /health aggregator contract for Session-Buddy.

Implements plan §5 Phase 4 task 1 — the per-repo integration test that
pins the contract between ``mcp_common.health.aggregator.aggregate_feed_states``
and the Session-Buddy ``/health`` HTTP route.

Session-Buddy ships exactly one data feed (``skills_signer``), so the
aggregator's worst-case verdict is just that feed's status. The tests
here exercise:

* Healthy: signer loaded with manifest entries → status="healthy", 200.
* Warming-up: signer loaded but manifest is empty → status="warming_up",
  200 (the launchd wrapper relies on 200 during normal startup).
* Failed: signer singleton is None (lifespan hasn't run yet) →
  status="failed", 503 with explicit ``error`` field.
* Reason codes populate: each non-healthy verdict carries at least one
  :class:`mcp_common.health.feed.ReasonCode` enum string.

These tests bypass the disk-loading :func:`init_signer_feed_state`
helper (which writes a keypair to disk as a side effect) and install
a synthetic :class:`SignerFeedState` directly via the module
singleton. That's appropriate because the ``/health`` route reads
through ``get_signer_feed_state()`` — the integration surface under
test is the route, not the disk-loading helper.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from mcp_common.health.feed import ReasonCode

import session_buddy.mcp.signer_feed as signer_feed_mod
import session_buddy.mcp.tools.tasks_events as tasks_events_mod
from session_buddy import server_optimized as so
from session_buddy.mcp.signer_feed import (
    SignerFeedState,
    reset_signer_feed_state,
)
from session_buddy.skills_signer import (
    PubkeyManifest,
    SkillsSigner,
    build_pubkey_manifest,
    generate_keypair,
)


def _json_body(response: object) -> dict[str, object]:
    """Decode a Starlette ``JSONResponse.body`` into a dict."""
    return json.loads(response.body)  # type: ignore[attr-defined]


def _install_signer(manifest: PubkeyManifest) -> SignerFeedState:
    """Build a ``SignerFeedState`` and install it as the singleton.

    Bypasses :func:`init_signer_feed_state` (which writes to disk) and
    uses ``generate_keypair`` directly so tests stay hermetic.
    """
    keypair = generate_keypair()
    signer = SkillsSigner.from_keypair(keypair)
    state = SignerFeedState(manifest=manifest, signer=signer)
    signer_feed_mod._signer_feed_state = state
    return state


def _install_healthy_publisher() -> MagicMock:
    """Install a healthy BodaiEventsPublisher-shaped mock on tasks_events._publisher.

    Task 4 made the bodai_events publisher a second data feed in the
    /health aggregator. The pre-Task-4 tests in this module focus on
    the skills_signer feed; to keep those tests isolated from the new
    feed we install a healthy publisher in their setup so the aggregate
    stays healthy / warming_up / failed for the signer-side reasons,
    not for bodai_events reasons.
    """
    from session_buddy.mcp.events.bodai_events_publisher import (
        BodaiEventsPublisher,
    )

    publisher = MagicMock(spec=BodaiEventsPublisher)
    publisher.entities_count = 1
    publisher.cycles_total = 1
    publisher.errors_total = 0
    publisher.last_updated_timestamp = 1_000_000.0
    publisher.enabled = True
    publisher._init_ok = True
    tasks_events_mod._publisher = publisher
    return publisher


def _clear_publisher() -> None:
    """Reset the bodai_events publisher slot (test cleanup)."""
    tasks_events_mod._publisher = None


class TestHealthAggregatorHealthy:
    """Signer loaded with manifest entries → healthy → 200."""

    def setup_method(self) -> None:
        # Synthetic manifest with one entry — exercises the canonical
        # "loaded, populated" path.
        self.state = _install_signer(build_pubkey_manifest(generate_keypair()))
        # Task 4: keep the bodai_events feed healthy so the aggregate
        # verdict reflects the signer feed only.
        _install_healthy_publisher()

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        _clear_publisher()

    async def test_health_returns_200_when_signer_loaded(self) -> None:
        response = await so.health_check(None)
        body = _json_body(response)
        assert response.status_code == 200  # type: ignore[attr-defined]
        # Body status mirrors the aggregator's verdict enum.
        assert body["status"] == "healthy"
        feed = body["checks"]["skills_signer"]
        assert feed["ok"] is True
        assert feed["status"] == "healthy"
        assert feed["reason_codes"] == []
        # Aggregator block surfaces the verdict so operators see WHY at
        # the top level.
        aggregate = body["checks"]["_aggregate"]
        assert aggregate["status"] == "healthy"
        assert aggregate["data_feeds_ok"] is True
        # Legacy manifest fields preserved for the Phase 2/6 installer.
        assert "key_count" in feed
        assert "pubkeys" in feed
        assert feed["generation"] >= 0

    async def test_health_includes_four_mandatory_wire_fields(self) -> None:
        """Per mcp-backend-wiring-discipline.md: every feed must expose
        ``feed_entities_count``, ``feed_last_updated_timestamp``,
        ``cycles_total``, ``errors_total``."""
        response = await so.health_check(None)
        body = _json_body(response)
        feed = body["checks"]["skills_signer"]
        assert "feed_entities_count" in feed
        assert "feed_last_updated_timestamp" in feed
        assert "cycles_total" in feed
        assert "errors_total" in feed


class TestHealthAggregatorFailed:
    """Signer singleton is None → failed → 503.

    The lifespan is responsible for calling ``init_signer_feed_state``
    during startup. If ``/health`` is hit BEFORE the lifespan runs
    (e.g. during the brief warm-up window), the singleton is None and
    the aggregator correctly reports FAILED.
    """

    def setup_method(self) -> None:
        reset_signer_feed_state()
        # Task 4: keep the bodai_events feed healthy so the aggregate
        # failure is localize-able to skills_signer.
        _install_healthy_publisher()

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        _clear_publisher()

    async def test_health_returns_503_when_signer_not_initialized(self) -> None:
        response = await so.health_check(None)
        body = _json_body(response)
        assert response.status_code == 503  # type: ignore[attr-defined]
        # Body status reflects the aggregator's failed verdict.
        assert body["status"] == "failed"
        feed = body["checks"]["skills_signer"]
        assert feed["ok"] is False
        assert feed["status"] == "failed"
        # The aggregator surfaces feed_never_populated + ingester_not_running
        # for the never-initialized case.
        assert ReasonCode.FEED_NEVER_POPULATED.value in feed["reason_codes"]
        assert ReasonCode.INGESTER_NOT_RUNNING.value in feed["reason_codes"]
        # The legacy error string is preserved for the Phase 1.5 surface.
        assert "not initialized" in feed["error"]
        # Top-level aggregate verdict matches.
        aggregate = body["checks"]["_aggregate"]
        assert aggregate["status"] == "failed"


class TestHealthAggregatorWarmingUp:
    """Signer loaded with empty manifest → warming_up → 200.

    HNSW hardening would normally flag ``ingester_running=True`` +
    ``cycles_total == 0`` as DEGRADED. Session-Buddy's signer is a
    pure data-feed with no producer loop — it has ``cycles_total = 0``
    at construction time but the manifest is loaded synchronously.
    When the manifest is non-empty but the signer hasn't run any
    update cycle yet, the aggregator reports WARMING_UP (not DEGRADED)
    because ``entities_count > 0``.

    Here we test the empty-manifest case: ``ingester_running=True`` +
    ``entities_count == 0`` + ``cycles_total == 0`` triggers the
    warming_up branch in ``is_healthy`` (branch 2c: empty + alive +
    at_least_one_cycle), but Session-Buddy's signer has ``cycles_total
    = 0`` from construction. The aggregator correctly reports
    WARMING_UP because the ingester is alive (the singleton is set).
    """

    def setup_method(self) -> None:
        # Install a signer with an EMPTY manifest — ingester_running=True
        # but entities_count == 0. Bump cycles_total so the aggregator
        # sees an "alive + cycled + empty" surface (= WARMING_UP), not
        # the "alive + never-cycled" surface (= DEGRADED via HNSW
        # hardening with FEED_NEVER_POPULATED).
        self.state = _install_signer(PubkeyManifest())  # empty
        self.state.record_cycle()  # cycles_total: 0 → 1
        # Task 4: keep the bodai_events feed healthy so the aggregate
        # verdict reflects the signer feed only.
        _install_healthy_publisher()

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        _clear_publisher()

    async def test_health_returns_200_when_signer_alive_but_empty(self) -> None:
        response = await so.health_check(None)
        body = _json_body(response)
        assert response.status_code == 200  # type: ignore[attr-defined]
        # Body status mirrors the aggregator's warming_up verdict.
        assert body["status"] == "warming_up"
        feed = body["checks"]["skills_signer"]
        assert feed["ok"] is False  # warming_up is not healthy
        assert feed["status"] == "warming_up"
        # The aggregator's reason code surfaces the empty-feed state.
        assert ReasonCode.WARMING_UP_EMPTY_FEED.value in feed["reason_codes"]
        # Empty manifest → 0 entities, but ingester_running=True.
        assert feed["feed_entities_count"] == 0
        aggregate = body["checks"]["_aggregate"]
        assert aggregate["status"] == "warming_up"


class TestHealthAggregatorBodaiEventsDegraded:
    """Task 4: when the BodaiEventsPublisher is degraded, /health must
    return 503 and the bodai_events feed must surface the failure.

    ``BodaiEventsPublisher.health()`` returns False when ``enabled=True``
    AND the transport never came up (``_init_ok == False``). This pins
    the contract that the lifespan-installed publisher participates in the
    per-feed aggregator (skills_signer + bodai_events) so operators see
    a Redis outage via the standard /health surface.

    The signer feed is healthy so the failure must localize to the
    bodai_events feed — the aggregate status is ``failed`` because the
    worst feed is failed, but ``checks.skills_signer.ok`` stays True.
    """

    def setup_method(self) -> None:
        # Signer healthy so the aggregate failure must come from bodai_events.
        _install_signer(build_pubkey_manifest(generate_keypair()))

        # Synthesize a BodaiEventsPublisher-shaped object with the
        # exact attributes /health reads. We do not need a real
        # publisher — MagicMock-with-spec enforces the attribute names
        # the /health handler accesses.
        from session_buddy.mcp.events.bodai_events_publisher import (
            BodaiEventsPublisher,
        )

        degraded_publisher = MagicMock(spec=BodaiEventsPublisher)
        degraded_publisher.entities_count = 0
        degraded_publisher.cycles_total = 0
        degraded_publisher.errors_total = 5
        degraded_publisher.last_updated_timestamp = 0.0
        # The two attributes /health reads directly: enabled + _init_ok.
        degraded_publisher.enabled = True
        degraded_publisher._init_ok = False  # transport never came up

        tasks_events_mod._publisher = degraded_publisher

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        tasks_events_mod._publisher = None

    async def test_health_returns_503_when_bodai_publisher_degraded(self) -> None:
        response = await so.health_check(None)
        body = _json_body(response)

        # HTTP 503 — the aggregator's worst status is failed.
        assert response.status_code == 503  # type: ignore[attr-defined]
        assert body["status"] == "failed"

        # Localize the failure: signer feed is healthy, bodai_events is not.
        signer_feed = body["checks"]["skills_signer"]
        assert signer_feed["ok"] is True
        assert signer_feed["status"] == "healthy"

        bodai_feed = body["checks"]["bodai_events"]
        assert bodai_feed["ok"] is False
        assert bodai_feed["status"] == "failed"
        # The four-feed data the wire carries so operators can investigate.
        assert "feed_entities_count" in bodai_feed
        assert "feed_last_updated_timestamp" in bodai_feed
        assert "cycles_total" in bodai_feed
        assert "errors_total" in bodai_feed
        assert bodai_feed["errors_total"] == 5

        # Aggregate: data_feeds_ok reflects the AND across feeds.
        aggregate = body["checks"]["_aggregate"]
        assert aggregate["status"] == "failed"
        assert aggregate["data_feeds_ok"] is False


class TestHealthAggregatorBodaiEventsHealthy:
    """When the publisher is enabled AND transport init succeeded, the
    bodai_events feed must report healthy in the aggregator.

    This pins the positive path: a publisher with ``enabled=True``,
    ``_init_ok=True`` and ``errors_total=0`` must NOT cause /health to
    return 503. Without this positive control the degraded test could
    pass vacuously if the /health code stopped reading the publisher.
    """

    def setup_method(self) -> None:
        _install_signer(build_pubkey_manifest(generate_keypair()))

        from session_buddy.mcp.events.bodai_events_publisher import (
            BodaiEventsPublisher,
        )

        healthy_publisher = MagicMock(spec=BodaiEventsPublisher)
        healthy_publisher.entities_count = 3
        healthy_publisher.cycles_total = 1
        healthy_publisher.errors_total = 0
        healthy_publisher.last_updated_timestamp = 1_000_000.0
        healthy_publisher.enabled = True
        healthy_publisher._init_ok = True

        tasks_events_mod._publisher = healthy_publisher

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        tasks_events_mod._publisher = None

    async def test_health_returns_200_when_bodai_publisher_healthy(self) -> None:
        response = await so.health_check(None)
        body = _json_body(response)

        # Healthy publisher + healthy signer → 200 OK.
        assert response.status_code == 200  # type: ignore[attr-defined]
        assert body["status"] == "healthy"

        bodai_feed = body["checks"]["bodai_events"]
        assert bodai_feed["ok"] is True
        assert bodai_feed["status"] == "healthy"
        assert bodai_feed["feed_entities_count"] == 3
        assert bodai_feed["cycles_total"] == 1


class TestHealthAggregatorBodaiEventsAbsent:
    """When the lifespan hasn't installed the publisher yet, the
    bodai_events feed must surface as failed (no ingester alive).

    This mirrors the skills_singer-not-initialized pattern: the slot
    is None → empty HealthFeedState → aggregator reports failed. Pinned
    so a regression that treats None as healthy cannot pass.
    """

    def setup_method(self) -> None:
        # Healthy signer so the failure must come from bodai_events.
        _install_signer(build_pubkey_manifest(generate_keypair()))
        # Explicitly clear — task_data could have leaked from a previous test.
        tasks_events_mod._publisher = None

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        tasks_events_mod._publisher = None

    async def test_health_returns_503_when_publisher_slot_empty(self) -> None:
        response = await so.health_check(None)
        body = _json_body(response)

        # No publisher → failed feed → 503.
        assert response.status_code == 503  # type: ignore[attr-defined]
        bodai_feed = body["checks"]["bodai_events"]
        assert bodai_feed["ok"] is False
        assert bodai_feed["status"] == "failed"
        assert bodai_feed["feed_entities_count"] == 0
