from __future__ import annotations

import asyncio
import types
from datetime import UTC, datetime

from session_buddy.health_checks import ComponentHealth, HealthStatus


def test_get_health_status_liveness(monkeypatch) -> None:
    from session_buddy import health_checks
    import session_buddy
    from session_buddy.tools import health_tools

    monkeypatch.setattr(
        health_checks, "get_all_health_checks",
        lambda: asyncio.sleep(0, result=[
            {"name": "database", "status": HealthStatus.HEALTHY, "message": "ok"},
            ComponentHealth(
                name="filesystem",
                status=HealthStatus.DEGRADED,
                message="slow",
                latency_ms=12.3,
                metadata={"note": "patched"},
            ),
        ]),
    )
    monkeypatch.setattr(health_tools, "_SERVER_START_TIME", 1000.0)
    monkeypatch.setattr(
        health_tools,
        "datetime",
        types.SimpleNamespace(now=lambda tz=None: datetime(2026, 5, 24, 12, 0, tzinfo=UTC)),
    )

    result = asyncio.run(health_tools.get_health_status())

    assert result["status"] == "healthy"
    assert result["alive"] is True
    assert result["metadata"]["check_type"] == "liveness"
    assert result["version"] == session_buddy.__version__
    assert result["components"][1]["note"] == "patched"


def test_get_health_status_readiness_and_version_fallback(monkeypatch) -> None:
    from session_buddy import health_checks
    import session_buddy
    from session_buddy.tools import health_tools

    async def fake_checks() -> list[dict[str, object]]:
        return [
            {"name": "database", "status": HealthStatus.DEGRADED, "message": "warn"}
        ]

    monkeypatch.setattr(health_checks, "get_all_health_checks", fake_checks)
    monkeypatch.setattr(health_tools, "_SERVER_START_TIME", 100.0)
    monkeypatch.setattr(
        health_tools,
        "datetime",
        types.SimpleNamespace(now=lambda tz=None: datetime(2026, 5, 24, 12, 0, tzinfo=UTC)),
    )
    monkeypatch.delattr(session_buddy, "__version__", raising=False)

    result = asyncio.run(health_tools.get_health_status(ready=True))

    assert result["status"] == "unhealthy"
    assert result["ready"] is False
    assert result["version"] == "unknown"
    assert result["metadata"]["check_type"] == "readiness"
