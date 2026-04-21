from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mcp_common.server.telemetry import FastMCPOpenTelemetryMiddleware

from session_buddy.mcp.telemetry import attach_otel_middleware, configure_otel_tracing


def test_configure_otel_tracing_sets_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    provider = MagicMock()
    exporter = MagicMock()
    monkeypatch.setattr("session_buddy.mcp.telemetry.TracerProvider", lambda resource=None: provider)
    monkeypatch.setattr("session_buddy.mcp.telemetry.BatchSpanProcessor", lambda exp: ("processor", exp))
    monkeypatch.setattr("session_buddy.mcp.telemetry.Resource", SimpleNamespace(create=lambda data: data))
    monkeypatch.setattr("session_buddy.mcp.telemetry.trace.set_tracer_provider", MagicMock())
    monkeypatch.setattr("session_buddy.mcp.telemetry.OTLPGrpcSpanExporter", lambda endpoint, insecure=True: exporter)
    monkeypatch.setattr("session_buddy.mcp.telemetry.OTLPHTTPSpanExporter", lambda endpoint: exporter)

    assert configure_otel_tracing(
        service_name="session-buddy",
        environment="test",
        endpoint="http://localhost:4317",
        protocol="grpc",
    )
    assert provider.add_span_processor.called


def test_attach_otel_middleware_adds_middleware() -> None:
    captured = []

    class DummyMCP:
        def add_middleware(self, middleware):
            captured.append(middleware)

    mcp = DummyMCP()

    assert attach_otel_middleware(mcp, service_name="session-buddy")
    assert captured and captured[0].service_name == "session-buddy"


def test_server_registers_shared_otel_middleware() -> None:
    from session_buddy.server_optimized import mcp

    assert hasattr(mcp, "middleware")
    assert any(isinstance(middleware, FastMCPOpenTelemetryMiddleware) for middleware in mcp.middleware)
