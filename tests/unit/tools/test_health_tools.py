#!/usr/bin/env python3
"""Test suite for session_buddy.tools.health_tools.

Covers :func:`get_health_status` for both liveness (``ready=False``) and
readiness (``ready=True``) probes, plus the defensive-fallback branch
where a component is a plain dict rather than a :class:`ComponentHealth`
dataclass. The module is the new entry-point added during the
``2026-08-21-mcp-tool-registration-dual-track-drift`` cleanup, so we
also assert the public surface still matches the consumer in
``session_buddy.cli.base`` (``get_health_status`` importable, async,
``ready=False`` default).
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

import session_buddy.health_checks as health_checks_mod
import session_buddy.tools.health_tools as health_tools_mod
from session_buddy.health_checks import ComponentHealth, HealthStatus


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exposes_get_health_status() -> None:
    """``get_health_status`` is the only public name from this module.

    The :data:`__all__` list pins the public surface — operators and the
    OneiricCLIBase hook in ``session_buddy.cli.base`` import
    ``get_health_status`` directly, so the symbol must stay importable.
    """
    assert "get_health_status" in health_tools_mod.__all__
    assert health_tools_mod.get_health_status is not None


def test_get_health_status_is_coroutine_function() -> None:
    """get_health_status must be ``async def`` — callers ``await`` it.

    ``OneiricCLIBase._health_probe`` does
    ``asyncio.run(get_health_status(ready=False))``, which only works
    when the callable returns a coroutine. A regression that turns it
    into a sync function would break every consumer.
    """
    assert asyncio.iscoroutinefunction(health_tools_mod.get_health_status)


# ---------------------------------------------------------------------------
# Helpers — small factories so individual tests stay focused.
# ---------------------------------------------------------------------------


def _healthy(name: str, **metadata: object) -> ComponentHealth:
    return ComponentHealth(
        name=name,
        status=HealthStatus.HEALTHY,
        message=f"{name}-ok",
        latency_ms=1.0,
        metadata=metadata,
    )


def _unhealthy(name: str, message: str = "down") -> ComponentHealth:
    return ComponentHealth(
        name=name,
        status=HealthStatus.UNHEALTHY,
        message=message,
        latency_ms=10.0,
        metadata={"err": "boom"},
    )


def _degraded(name: str, message: str = "slow") -> ComponentHealth:
    return ComponentHealth(
        name=name,
        status=HealthStatus.DEGRADED,
        message=message,
        latency_ms=250.0,
        metadata={},
    )


def _patch_components(
    monkeypatch: pytest.MonkeyPatch,
    components: list[object],
) -> None:
    """Stub ``get_all_health_checks`` to return ``components`` verbatim."""
    async def _fake() -> list[object]:
        return list(components)

    monkeypatch.setattr(
        health_tools_mod.health_checks,
        "get_all_health_checks",
        _fake,
    )


# ---------------------------------------------------------------------------
# Liveness path (ready=False)
# ---------------------------------------------------------------------------


async def test_liveness_all_healthy_is_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Liveness check: all HEALTHY → status healthy, alive=True."""
    _patch_components(monkeypatch, [_healthy("python_env"), _healthy("file_system")])

    result = await health_tools_mod.get_health_status(ready=False)

    assert result["status"] == "healthy"
    assert result["alive"] is True
    assert "ready" not in result
    assert result["metadata"]["check_type"] == "liveness"


async def test_liveness_degraded_still_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Liveness check: DEGRADED components do NOT fail liveness.

    Loose definition per the docstring: "only UNHEALTHY components
    fail" — DEGRADED is operating, just slow.
    """
    _patch_components(monkeypatch, [_healthy("python_env"), _degraded("database")])

    result = await health_tools_mod.get_health_status(ready=False)

    assert result["alive"] is True
    assert result["status"] == "healthy"


async def test_liveness_unhealthy_kills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Liveness check: at least one UNHEALTHY → alive=False, status unhealthy."""
    _patch_components(
        monkeypatch,
        [_healthy("python_env"), _unhealthy("file_system", "disk full")],
    )

    result = await health_tools_mod.get_health_status(ready=False)

    assert result["alive"] is False
    assert result["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# Readiness path (ready=True) — strict: only fully healthy passes.
# ---------------------------------------------------------------------------


async def test_readiness_all_healthy_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness check: all HEALTHY → status healthy, ready=True."""
    _patch_components(monkeypatch, [_healthy("python_env")])

    result = await health_tools_mod.get_health_status(ready=True)

    assert result["status"] == "healthy"
    assert result["ready"] is True
    assert "alive" not in result
    assert result["metadata"]["check_type"] == "readiness"


async def test_readiness_degraded_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness check: DEGRADED → ready=False (strict definition)."""
    _patch_components(monkeypatch, [_healthy("python_env"), _degraded("database")])

    result = await health_tools_mod.get_health_status(ready=True)

    assert result["ready"] is False
    assert result["status"] == "unhealthy"


async def test_readiness_unhealthy_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness check: any UNHEALTHY → ready=False."""
    _patch_components(monkeypatch, [_unhealthy("database")])

    result = await health_tools_mod.get_health_status(ready=True)

    assert result["ready"] is False
    assert result["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# Empty-component edge case
# ---------------------------------------------------------------------------


async def test_empty_components_is_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No components reported: status is healthy (vacuously).

    Both ``all([])`` and ``not any([])`` are True, so liveness and
    readiness both pass on an empty list.
    """
    _patch_components(monkeypatch, [])

    liveness = await health_tools_mod.get_health_status(ready=False)
    readiness = await health_tools_mod.get_health_status(ready=True)

    assert liveness["status"] == "healthy"
    assert liveness["alive"] is True
    assert readiness["status"] == "healthy"
    assert readiness["ready"] is True


# ---------------------------------------------------------------------------
# Defensive fallback branch (component is dict, not ComponentHealth)
# ---------------------------------------------------------------------------


async def test_dict_component_uses_fallback_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-ComponentHealth component falls back to ``dict(comp)``.

    The producer of ``get_all_health_checks`` is documented to return
    :class:`ComponentHealth` instances, but the consumer here guards
    against anything dict-like so a future migration does not crash
    the health endpoint.
    """
    raw_dict = {
        "name": "custom",
        "status": "healthy",
        "message": "ok",
        "latency_ms": 0.5,
        "extra": "preserved",
    }
    _patch_components(monkeypatch, [raw_dict])

    result = await health_tools_mod.get_health_status(ready=False)

    assert result["components"][0]["name"] == "custom"
    assert result["components"][0]["status"] == "healthy"
    assert result["components"][0]["extra"] == "preserved"
    assert result["alive"] is True


async def test_dict_component_without_status_field_defaults_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ``status`` key on a component → 'healthy' default.

    The comprehension ``[c.get('status', 'healthy') for c in serialised]``
    only applies to dict-shaped components. A missing status means the
    component is treated as healthy.
    """
    raw_dict = {"name": "no-status"}
    _patch_components(monkeypatch, [raw_dict])

    result = await health_tools_mod.get_health_status(ready=True)

    assert result["ready"] is True


# ---------------------------------------------------------------------------
# ComponentHealth metadata merge
# ---------------------------------------------------------------------------


async def test_component_health_metadata_merged_into_serialised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The :class:`ComponentHealth.metadata` dict is spread into the serialised row.

    Plus the four core fields (name/status/message/latency_ms). Together
    they produce the dict the orchestration probes consume.
    """
    comp = ComponentHealth(
        name="python_env",
        status=HealthStatus.HEALTHY,
        message="py3.14",
        latency_ms=2.5,
        metadata={"python_version": "3.14.7", "platform": "darwin"},
    )
    _patch_components(monkeypatch, [comp])

    result = await health_tools_mod.get_health_status(ready=False)

    row = result["components"][0]
    assert row["name"] == "python_env"
    assert row["status"] == "healthy"
    assert row["message"] == "py3.14"
    assert row["latency_ms"] == 2.5
    assert row["python_version"] == "3.14.7"
    assert row["platform"] == "darwin"


# ---------------------------------------------------------------------------
# Version handling
# ---------------------------------------------------------------------------


async def test_version_import_error_falls_back_to_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``session_buddy.__version__`` is unimportable, return 'unknown'.

    The wrapper has an ``except (ImportError, AttributeError)`` guard so a
    missing __version__ does not blow up the health endpoint.
    """
    _patch_components(monkeypatch, [_healthy("python_env")])

    # Patch the inner ``from session_buddy import __version__`` import to
    # raise ImportError. We avoid deleting ``session_buddy.__version__``
    # so subsequent tests still see a normal package.
    import builtins

    real_import = builtins.__import__

    def _failing_import(name: str, *args: object, **kwargs: object) -> object:
        # ``from session_buddy import __version__`` reaches __import__ with
        # fromlist=("__version__",). Raise to simulate a missing __version__.
        fromlist = args[2] if len(args) >= 3 else kwargs.get("fromlist")
        if name == "session_buddy" and fromlist and "__version__" in fromlist:
            raise ImportError("simulated missing __version__")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _failing_import)

    result = await health_tools_mod.get_health_status(ready=False)

    assert result["version"] == "unknown"


async def test_version_imported_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``__version__`` is importable, it surfaces in the result."""
    _patch_components(monkeypatch, [_healthy("python_env")])

    import session_buddy

    expected = getattr(session_buddy, "__version__", None)

    result = await health_tools_mod.get_health_status(ready=False)

    assert result["version"] == expected


# ---------------------------------------------------------------------------
# Result shape contract
# ---------------------------------------------------------------------------


async def test_result_has_required_top_level_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The result dict must include status, timestamp, version, uptime, components, metadata.

    Orchestration probes (Docker / Kubernetes) parse these keys
    positionally — drift breaks liveness/readiness semantics.
    """
    _patch_components(monkeypatch, [_healthy("python_env")])

    result = await health_tools_mod.get_health_status(ready=False)

    for key in ("status", "timestamp", "version", "uptime_seconds", "components", "metadata"):
        assert key in result, f"Missing required key: {key}"


async def test_timestamp_is_iso8601_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timestamp is an ISO-8601 string with a UTC offset.

    The producer uses ``datetime.now(tz=UTC).isoformat()`` so a `+00:00`
    suffix is part of the contract (downstream parsers rely on it).
    """
    _patch_components(monkeypatch, [_healthy("python_env")])

    result = await health_tools_mod.get_health_status(ready=False)

    assert result["timestamp"].endswith("+00:00")


async def test_uptime_seconds_is_positive_float(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uptime is a non-negative float, rounded to milliseconds."""
    _patch_components(monkeypatch, [_healthy("python_env")])

    result = await health_tools_mod.get_health_status(ready=False)

    assert isinstance(result["uptime_seconds"], float)
    assert result["uptime_seconds"] >= 0.0


async def test_default_ready_arg_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default behaviour is liveness (ready=False).

    ``session_buddy.cli.base`` and the docs both say
    ``session-buddy health`` does a liveness probe. The default must
    stay False so callers that omit ``ready`` get liveness.
    """
    _patch_components(monkeypatch, [_healthy("python_env")])

    result = await health_tools_mod.get_health_status()

    assert "alive" in result
    assert "ready" not in result
    assert result["metadata"]["check_type"] == "liveness"
