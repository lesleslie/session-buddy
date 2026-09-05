"""Tests for session_buddy.mcp.tools.monitoring.health_tools.

Covers the health check MCP tool:
- ``_normalize_dict_component``: valid status, invalid status → DEGRADED,
  defaults for missing keys, metadata passthrough
- ``_normalize_object_component``: pre-built ComponentHealth passthrough,
  status coercion from object, status string coerced, invalid status
  → DEGRADED, missing attributes default safely
- ``_normalize_components``: mixed list (ComponentHealth + dict + object),
  empty list, dict passthrough
- ``_prepare_readiness_result``: ``ready`` key reflects is_healthy()
- ``_prepare_liveness_result``: ``alive`` key reflects is_ready()
- ``get_health_status``: happy path liveness, readiness, version fallback
  when ``__version__`` import fails, mixed component types normalized,
  metadata includes check_type
- ``__all__`` exports

Real health checks are patched out via monkeypatch on
``session_buddy.health_checks.get_all_health_checks`` so no filesystem
or network calls happen.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp_common.health import (
    ComponentHealth as MCPComponentHealth,
    HealthCheckResponse,
    HealthStatus,
)

from session_buddy.mcp.tools.monitoring import health_tools
from session_buddy.mcp.tools.monitoring.health_tools import (
    _normalize_components,
    _normalize_dict_component,
    _normalize_object_component,
    _prepare_liveness_result,
    _prepare_readiness_result,
    get_health_status,
)
import session_buddy as _session_buddy_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    *,
    overall: HealthStatus = HealthStatus.HEALTHY,
    components: list[MCPComponentHealth] | None = None,
) -> HealthCheckResponse:
    return HealthCheckResponse.create(
        components=components or [],
        version="1.0.0",
        start_time=0.0,
        metadata={"check_type": "test"},
    )


# ---------------------------------------------------------------------------
# _normalize_dict_component
# ---------------------------------------------------------------------------


class TestNormalizeDictComponent:
    def test_valid_status_preserved(self) -> None:
        comp = _normalize_dict_component(
            {"name": "database", "status": "healthy", "latency_ms": 12.5}
        )
        assert isinstance(comp, MCPComponentHealth)
        assert comp.name == "database"
        assert comp.status == HealthStatus.HEALTHY
        assert comp.latency_ms == 12.5

    def test_invalid_status_defaults_to_degraded(self) -> None:
        # Unknown status string → DEGRADED (graceful coerce).
        comp = _normalize_dict_component({"name": "x", "status": "bogus"})
        assert comp.status == HealthStatus.DEGRADED

    def test_missing_status_defaults_to_degraded(self) -> None:
        # No status field → DEGRADED.
        comp = _normalize_dict_component({"name": "x"})
        assert comp.status == HealthStatus.DEGRADED

    def test_missing_name_defaults_to_unknown(self) -> None:
        comp = _normalize_dict_component({"status": "healthy"})
        assert comp.name == "unknown"

    def test_message_and_metadata_passthrough(self) -> None:
        comp = _normalize_dict_component(
            {
                "name": "x",
                "status": "healthy",
                "message": "all good",
                "metadata": {"k": "v"},
            }
        )
        assert comp.message == "all good"
        assert comp.metadata == {"k": "v"}

    def test_metadata_defaults_to_empty_dict(self) -> None:
        comp = _normalize_dict_component({"name": "x", "status": "healthy"})
        assert comp.metadata == {}

    def test_message_defaults_to_none(self) -> None:
        comp = _normalize_dict_component({"name": "x", "status": "healthy"})
        assert comp.message is None

    def test_latency_ms_defaults_to_none(self) -> None:
        comp = _normalize_dict_component({"name": "x", "status": "healthy"})
        assert comp.latency_ms is None

    def test_unhealthy_status_preserved(self) -> None:
        comp = _normalize_dict_component({"name": "x", "status": "unhealthy"})
        assert comp.status == HealthStatus.UNHEALTHY


# ---------------------------------------------------------------------------
# _normalize_object_component
# ---------------------------------------------------------------------------


class TestNormalizeObjectComponent:
    def test_status_enum_passthrough(self) -> None:
        obj = SimpleNamespace(
            name="database",
            status=HealthStatus.HEALTHY,
            message="ok",
            latency_ms=10.0,
            metadata={"k": "v"},
        )
        comp = _normalize_object_component(obj)
        assert isinstance(comp, MCPComponentHealth)
        assert comp.name == "database"
        assert comp.status == HealthStatus.HEALTHY
        assert comp.message == "ok"
        assert comp.latency_ms == 10.0
        assert comp.metadata == {"k": "v"}

    def test_status_string_coerced(self) -> None:
        # Status comes in as a plain string instead of the enum.
        obj = SimpleNamespace(name="x", status="healthy")
        comp = _normalize_object_component(obj)
        assert comp.status == HealthStatus.HEALTHY

    def test_invalid_status_string_defaults_to_degraded(self) -> None:
        obj = SimpleNamespace(name="x", status="bogus")
        comp = _normalize_object_component(obj)
        assert comp.status == HealthStatus.DEGRADED

    def test_missing_status_defaults_to_degraded(self) -> None:
        # No status attribute → DEGRADED.
        obj = SimpleNamespace(name="x")
        comp = _normalize_object_component(obj)
        assert comp.status == HealthStatus.DEGRADED

    def test_missing_attributes_default_safely(self) -> None:
        # All optional attrs missing → safe defaults.
        obj = SimpleNamespace(name="x")
        comp = _normalize_object_component(obj)
        assert comp.message is None
        assert comp.latency_ms is None
        assert comp.metadata == {}

    def test_missing_name_defaults_to_unknown(self) -> None:
        # No name attribute → "unknown".
        obj = SimpleNamespace(status=HealthStatus.HEALTHY)
        comp = _normalize_object_component(obj)
        assert comp.name == "unknown"

    def test_non_string_non_enum_status_defaults_to_degraded(self) -> None:
        # status is an int → not a HealthStatus enum, str() fails
        # because int('42') raises ValueError → falls to DEGRADED.
        obj = SimpleNamespace(name="x", status=42)
        comp = _normalize_object_component(obj)
        assert comp.status == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# _normalize_components
# ---------------------------------------------------------------------------


class TestNormalizeComponents:
    def test_empty_list(self) -> None:
        assert _normalize_components([]) == []

    def test_component_health_passthrough(self) -> None:
        comp = MCPComponentHealth(
            name="x", status=HealthStatus.HEALTHY
        )
        result = _normalize_components([comp])
        assert result == [comp]

    def test_dict_passthrough(self) -> None:
        result = _normalize_components([{"name": "x", "status": "healthy"}])
        assert len(result) == 1
        assert isinstance(result[0], MCPComponentHealth)
        assert result[0].name == "x"
        assert result[0].status == HealthStatus.HEALTHY

    def test_object_passthrough(self) -> None:
        obj = SimpleNamespace(name="x", status=HealthStatus.HEALTHY)
        result = _normalize_components([obj])
        assert len(result) == 1
        assert result[0].name == "x"
        assert result[0].status == HealthStatus.HEALTHY

    def test_mixed_list(self) -> None:
        # All three shapes in one list — order preserved.
        comp = MCPComponentHealth(name="a", status=HealthStatus.HEALTHY)
        result = _normalize_components(
            [
                comp,
                {"name": "b", "status": "degraded"},
                SimpleNamespace(name="c", status="unhealthy"),
            ]
        )
        assert len(result) == 3
        assert result[0].name == "a"
        assert result[0].status == HealthStatus.HEALTHY
        assert result[1].name == "b"
        assert result[1].status == HealthStatus.DEGRADED
        assert result[2].name == "c"
        assert result[2].status == HealthStatus.UNHEALTHY

    def test_preserves_order(self) -> None:
        # Order of the input list is preserved in the output.
        result = _normalize_components(
            [
                SimpleNamespace(name="first", status=HealthStatus.HEALTHY),
                SimpleNamespace(name="second", status=HealthStatus.HEALTHY),
                SimpleNamespace(name="third", status=HealthStatus.HEALTHY),
            ]
        )
        assert [c.name for c in result] == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# _prepare_readiness_result / _prepare_liveness_result
# ---------------------------------------------------------------------------


class TestPrepareResults:
    def test_readiness_result_has_ready_key(self) -> None:
        response = _make_response()
        result = _prepare_readiness_result(response)
        assert "ready" in result
        # No components → response is healthy → ready True.
        assert result["ready"] is True

    def test_readiness_result_unhealthy_returns_not_ready(self) -> None:
        # An UNHEALTHY component flips ready → False.
        response = HealthCheckResponse.create(
            components=[
                MCPComponentHealth(name="db", status=HealthStatus.UNHEALTHY)
            ],
            version="1.0.0",
            start_time=0.0,
        )
        result = _prepare_readiness_result(response)
        assert result["ready"] is False

    def test_liveness_result_has_alive_key(self) -> None:
        response = _make_response()
        result = _prepare_liveness_result(response)
        assert "alive" in result
        # No components → response is ready → alive True.
        assert result["alive"] is True

    def test_liveness_result_unhealthy_returns_not_alive(self) -> None:
        response = HealthCheckResponse.create(
            components=[
                MCPComponentHealth(name="db", status=HealthStatus.UNHEALTHY)
            ],
            version="1.0.0",
            start_time=0.0,
        )
        result = _prepare_liveness_result(response)
        assert result["alive"] is False

    def test_prepare_includes_response_to_dict(self) -> None:
        response = _make_response()
        result = _prepare_liveness_result(response)
        # The standard response fields are merged in.
        assert "status" in result
        assert "timestamp" in result
        assert "version" in result
        assert "uptime_seconds" in result
        assert "components" in result


# ---------------------------------------------------------------------------
# get_health_status (public)
# ---------------------------------------------------------------------------


class TestGetHealthStatus:
    @pytest.mark.asyncio
    async def test_liveness_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Calling without arguments → liveness semantics."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(return_value=[]),
        )

        result = await get_health_status()

        assert result["alive"] is True
        # Liveness uses is_ready() not is_healthy(), so check_type is liveness.
        assert result["metadata"]["check_type"] == "liveness"

    @pytest.mark.asyncio
    async def test_readiness_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ready=True → readiness semantics."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(return_value=[]),
        )

        result = await get_health_status(ready=True)

        assert result["ready"] is True
        assert result["metadata"]["check_type"] == "readiness"

    @pytest.mark.asyncio
    async def test_empty_components_returns_healthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(return_value=[]),
        )

        result = await get_health_status()

        assert result["status"] == HealthStatus.HEALTHY.value

    @pytest.mark.asyncio
    async def test_normalizes_dict_components(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dict components from real health checks get coerced."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(
                return_value=[
                    {"name": "db", "status": "healthy", "latency_ms": 5.0},
                    {"name": "fs", "status": "degraded"},
                ]
            ),
        )

        result = await get_health_status()

        # Aggregated status: worst is DEGRADED.
        assert result["status"] == HealthStatus.DEGRADED.value
        assert len(result["components"]) == 2
        names = sorted(c["name"] for c in result["components"])
        assert names == ["db", "fs"]

    @pytest.mark.asyncio
    async def test_normalizes_object_components(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plain object components get coerced."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(
                return_value=[
                    SimpleNamespace(
                        name="api", status=HealthStatus.HEALTHY
                    ),
                ]
            ),
        )

        result = await get_health_status()

        assert result["status"] == HealthStatus.HEALTHY.value
        assert result["components"][0]["name"] == "api"

    @pytest.mark.asyncio
    async def test_normalizes_mixed_components(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mixed list of dict, object, and ComponentHealth."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(
                return_value=[
                    MCPComponentHealth(
                        name="a", status=HealthStatus.HEALTHY
                    ),
                    {"name": "b", "status": "healthy"},
                    SimpleNamespace(name="c", status="healthy"),
                ]
            ),
        )

        result = await get_health_status()

        assert result["status"] == HealthStatus.HEALTHY.value
        assert len(result["components"]) == 3

    @pytest.mark.asyncio
    async def test_version_fallback_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``__version__`` cannot be imported, fall back to 'unknown'."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(return_value=[]),
        )
        # Drop __version__ so ``from session_buddy import __version__`` raises.
        monkeypatch.delattr(_session_buddy_module, "__version__", raising=False)

        result = await get_health_status()

        assert result["version"] == "unknown"

    @pytest.mark.asyncio
    async def test_version_uses_package_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``__version__`` exists, use it."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(return_value=[]),
        )
        # Use the module reference (not a dotted string) so pytest doesn't
        # try to look up `__version__` as an attribute on the test module.
        monkeypatch.setattr(
            _session_buddy_module, "__version__", "9.9.9", raising=False
        )

        result = await get_health_status()

        assert result["version"] == "9.9.9"

    @pytest.mark.asyncio
    async def test_uptime_seconds_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(return_value=[]),
        )

        result = await get_health_status()

        # Response.to_dict() includes uptime_seconds.
        assert "uptime_seconds" in result
        assert isinstance(result["uptime_seconds"], (int, float))
        assert result["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_unhealthy_component_makes_not_ready(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An UNHEALTHY component → readiness flips to False."""
        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks",
            AsyncMock(
                return_value=[
                    MCPComponentHealth(
                        name="db", status=HealthStatus.UNHEALTHY
                    )
                ]
            ),
        )

        result = await get_health_status(ready=True)

        assert result["ready"] is False

    @pytest.mark.asyncio
    async def test_propagates_get_all_health_checks_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the underlying health check raises, it propagates out."""
        async def boom():
            raise RuntimeError("disk check failed")

        monkeypatch.setattr(
            "session_buddy.health_checks.get_all_health_checks", boom
        )

        with pytest.raises(RuntimeError, match="disk check failed"):
            await get_health_status()


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


class TestExports:
    def test_all_exports(self) -> None:
        assert "get_health_status" in health_tools.__all__
