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

from mcp_common.health.feed import ReasonCode

import session_buddy.mcp.signer_feed as signer_feed_mod
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
    signer_feed_mod._signer_feed_state = state  # noqa: SLF001 — test bypass
    return state


class TestHealthAggregatorHealthy:
    """Signer loaded with manifest entries → healthy → 200."""

    def setup_method(self) -> None:
        # Synthetic manifest with one entry — exercises the canonical
        # "loaded, populated" path.
        self.state = _install_signer(build_pubkey_manifest(generate_keypair()))

    def teardown_method(self) -> None:
        reset_signer_feed_state()

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

    def teardown_method(self) -> None:
        reset_signer_feed_state()

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
        # but entities_count == 0. This is the warming_up surface: the
        # signer is loaded, the ingester is alive, but no manifest
        # entries exist yet.
        self.state = _install_signer(PubkeyManifest())  # empty

    def teardown_method(self) -> None:
        reset_signer_feed_state()

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
