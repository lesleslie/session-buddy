"""Tests for ``ecosystem_run_history`` MCP tool (Phase 1 of v2 plan)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from session_buddy.mcp.tools.ecosystem_run_history import (
    BODAI_COMPONENT_KEYS,
    SUBSTRATE_CAP_KEY_FMT,
    SUBSTRATE_RUN_KEY_FMT,
    EcosystemRunHistoryRequest,
    aggregate_run_history,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyFastMCP:
    """Minimal FastMCP stand-in recording tool() registrations."""

    def __init__(self) -> None:
        self.registered: dict[str, Callable[..., Any]] = {}

    def tool(self, *_args: Any, **_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self.registered[fn.__name__] = fn
            return fn

        return decorator


def _registered_app() -> _DummyFastMCP:
    from session_buddy.mcp.tools.ecosystem_run_history import (
        register_ecosystem_run_history_tools,
    )

    app = _DummyFastMCP()
    register_ecosystem_run_history_tools(app)  # type: ignore[arg-type]
    return app


# ---------------------------------------------------------------------------
# Substrate key formats
# ---------------------------------------------------------------------------


class TestSubstrateKeyFormats:
    def test_run_key_shape(self) -> None:
        wid = "10633f68-279a-4bcc-8c7b-634d870f71c8"
        assert SUBSTRATE_RUN_KEY_FMT.format(workflow_id=wid) == (
            f"session-buddy://runs/{wid}.json"
        )

    def test_capability_key_shape(self) -> None:
        key = SUBSTRATE_CAP_KEY_FMT.format(
            repo="mahavishnu",
            kind="tool",
            name="pool_route_execute",
        )
        assert key == "akosha://capabilities/mahavishnu/tool/pool_route_execute.json"


# ---------------------------------------------------------------------------
# Pydantic request validation
# ---------------------------------------------------------------------------


class TestRequestValidation:
    def test_minimal_valid(self) -> None:
        r = EcosystemRunHistoryRequest(workflow_id="abc-123")
        assert r.workflow_id == "abc-123"
        assert r.scope is None
        assert r.include_steps is False

    def test_workflow_id_required(self) -> None:
        with pytest.raises(Exception):
            EcosystemRunHistoryRequest()  # type: ignore[call-arg]

    def test_empty_workflow_id_rejected(self) -> None:
        with pytest.raises(Exception):
            EcosystemRunHistoryRequest(workflow_id="")

    def test_workflow_id_invalid_chars_rejected(self) -> None:
        with pytest.raises(Exception):
            EcosystemRunHistoryRequest(workflow_id="bad;rm -rf /")

    def test_scope_all_allowed(self) -> None:
        r = EcosystemRunHistoryRequest(workflow_id="abc", scope="all")
        assert r.scope == "all"

    def test_scope_known_component_allowed(self) -> None:
        r = EcosystemRunHistoryRequest(workflow_id="abc", scope="mahavishnu")
        assert r.scope == "mahavishnu"

    def test_scope_unknown_component_rejected(self) -> None:
        with pytest.raises(Exception):
            EcosystemRunHistoryRequest(workflow_id="abc", scope="bogus")


# ---------------------------------------------------------------------------
# ``aggregate_run_history`` (sync aggregator)
# ---------------------------------------------------------------------------


class TestAggregateRunHistory:
    def test_default_scope_includes_all_components(self) -> None:
        result = aggregate_run_history("wid-1")
        assert result["workflow_id"] == "wid-1"
        assert result["mode"] == "phase1_stub"
        assert len(result["components"]) == len(BODAI_COMPONENT_KEYS)
        assert result["summary"]["component_count"] == len(BODAI_COMPONENT_KEYS)
        assert result["summary"]["repos_seen"] == sorted(BODAI_COMPONENT_KEYS)

    def test_scope_filters_to_one_component(self) -> None:
        result = aggregate_run_history("wid-2", scope="mahavishnu")
        assert len(result["components"]) == 1
        assert result["components"][0]["repo"] == "mahavishnu"

    def test_summary_spans_3_components_for_default_query(self) -> None:
        """Plan exit-criteria gate: result must span 3+ components for default query."""
        result = aggregate_run_history("wid-3")
        assert result["summary"]["spans_3_components"] is True
        assert result["summary"]["component_count"] >= 3

    def test_entries_have_required_fields(self) -> None:
        result = aggregate_run_history("wid-4")
        for entry in result["components"]:
            assert {"repo", "workflow_id", "status", "source"} <= set(entry)
            assert entry["workflow_id"] == "wid-4"

    def test_include_steps_adds_steps_field(self) -> None:
        result = aggregate_run_history("wid-5", include_steps=True)
        for entry in result["components"]:
            assert "steps" in entry
            assert entry["steps"] == []

    def test_no_include_steps_omits_steps_field(self) -> None:
        result = aggregate_run_history("wid-6", include_steps=False)
        for entry in result["components"]:
            assert "steps" not in entry

    def test_fetcher_injection(self) -> None:
        def fake_fetcher(repo: str, workflow_id: str) -> dict[str, Any]:
            return {
                "repo": repo,
                "workflow_id": workflow_id,
                "status": "succeeded",
                "started_at": "2026-08-29T00:00:00Z",
                "finished_at": "2026-08-29T00:01:00Z",
                "duration_ms": 60000,
                "source": "live_fetcher",
            }

        result = aggregate_run_history("wid-7", scope="akosha", fetcher=fake_fetcher)
        assert result["mode"] == "live"
        entry = result["components"][0]
        assert entry["status"] == "succeeded"
        assert entry["source"] == "live_fetcher"

    def test_fetcher_failure_is_captured(self) -> None:
        def failing_fetcher(repo: str, workflow_id: str) -> dict[str, Any]:
            raise RuntimeError("network down")

        result = aggregate_run_history("wid-8", scope="akosha", fetcher=failing_fetcher)
        entry = result["components"][0]
        assert entry["status"] == "error"
        assert entry["error"] == "network down"


# ---------------------------------------------------------------------------
# Tool registration + invocation
# ---------------------------------------------------------------------------


class TestRegisterEcosystemRunHistoryTools:
    def test_tool_registered(self) -> None:
        app = _registered_app()
        assert "ecosystem_run_history" in app.registered

    def test_tool_is_coroutine(self) -> None:
        app = _registered_app()
        import inspect

        assert inspect.iscoroutinefunction(app.registered["ecosystem_run_history"])


class TestToolInvocation:
    @pytest.mark.asyncio
    async def test_basic_invocation_returns_json(self) -> None:
        app = _registered_app()
        fn = app.registered["ecosystem_run_history"]
        out = await fn(workflow_id="10633f68-279a-4bcc-8c7b-634d870f71c8")
        payload = json.loads(out)
        assert payload["workflow_id"] == "10633f68-279a-4bcc-8c7b-634d870f71c8"
        assert "summary" in payload
        assert "components" in payload
        assert payload["summary"]["spans_3_components"] is True

    @pytest.mark.asyncio
    async def test_invalid_workflow_id_returns_error_envelope(self) -> None:
        app = _registered_app()
        fn = app.registered["ecosystem_run_history"]
        out = await fn(workflow_id="bad;injection")
        payload = json.loads(out)
        assert payload["success"] is False
        assert payload["error_code"] == "invalid_input"

    @pytest.mark.asyncio
    async def test_invalid_scope_returns_error_envelope(self) -> None:
        app = _registered_app()
        fn = app.registered["ecosystem_run_history"]
        out = await fn(workflow_id="abc-123", scope="bogus")
        payload = json.loads(out)
        assert payload["success"] is False
        assert payload["error_code"] == "invalid_input"

    @pytest.mark.asyncio
    async def test_scope_filter_applied(self) -> None:
        app = _registered_app()
        fn = app.registered["ecosystem_run_history"]
        out = await fn(workflow_id="abc-123", scope="akosha")
        payload = json.loads(out)
        assert len(payload["components"]) == 1
        assert payload["components"][0]["repo"] == "akosha"

    @pytest.mark.asyncio
    async def test_include_steps_returns_step_entries(self) -> None:
        app = _registered_app()
        fn = app.registered["ecosystem_run_history"]
        out = await fn(workflow_id="abc-123", scope="akosha", include_steps=True)
        payload = json.loads(out)
        entry = payload["components"][0]
        assert "steps" in entry


# ---------------------------------------------------------------------------
# Profile wiring
# ---------------------------------------------------------------------------


class TestProfileWiring:
    def test_registration_map_includes_run_history(self) -> None:
        from session_buddy.mcp.tools.profiles import REGISTRATION_MAP

        assert "register_ecosystem_run_history_tools" in REGISTRATION_MAP

    def test_init_exports(self) -> None:
        from session_buddy.mcp.tools import register_ecosystem_run_history_tools

        assert callable(register_ecosystem_run_history_tools)
