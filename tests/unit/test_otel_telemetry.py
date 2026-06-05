from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mcp_common.server.telemetry import FastMCPOpenTelemetryMiddleware

from session_buddy.mcp import telemetry
from session_buddy.mcp.telemetry import attach_otel_middleware, configure_otel_tracing


def test_configure_otel_tracing_sets_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    provider = MagicMock()
    exporter = MagicMock()
    monkeypatch.setattr(telemetry, "TracerProvider", lambda resource=None: provider)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exp: ("processor", exp))
    monkeypatch.setattr(telemetry, "Resource", SimpleNamespace(create=lambda data: data))
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(set_tracer_provider=MagicMock()))
    monkeypatch.setattr(telemetry, "OTLPGrpcSpanExporter", lambda endpoint, insecure=True: exporter)
    monkeypatch.setattr(telemetry, "OTLPHTTPSpanExporter", lambda endpoint: exporter)

    assert configure_otel_tracing(
        service_name="session-buddy",
        environment="test",
        endpoint="http://localhost:4317",
        protocol="grpc",
    )
    assert provider.add_span_processor.called


def test_configure_otel_tracing_second_call_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", True)
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(set_tracer_provider=MagicMock()))

    assert (
        configure_otel_tracing(
            service_name="session-buddy",
            environment="test",
            endpoint="http://localhost:4317",
            protocol="grpc",
        )
        is True
    )


def test_configure_otel_tracing_no_endpoint_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(set_tracer_provider=MagicMock()))

    assert (
        configure_otel_tracing(
            service_name="session-buddy",
            environment="test",
            endpoint=None,
            protocol="grpc",
        )
        is False
    )


def test_configure_otel_tracing_missing_sdk_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", False)

    assert (
        configure_otel_tracing(
            service_name="session-buddy",
            environment="test",
            endpoint="http://localhost:4317",
            protocol="grpc",
        )
        is False
    )


def test_configure_otel_tracing_missing_endpoint_outside_pytest_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert (
        configure_otel_tracing(
            service_name="session-buddy",
            environment="test",
            endpoint=None,
            protocol="grpc",
        )
        is False
    )


def test_configure_otel_tracing_http_protocol_and_resource_attrs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    provider = MagicMock()
    exporter = MagicMock()
    resource_data = {}

    monkeypatch.setattr(telemetry, "TracerProvider", lambda resource=None: provider)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exp: ("processor", exp))
    monkeypatch.setattr(telemetry, "Resource", SimpleNamespace(create=lambda data: resource_data.update(data) or data))
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(set_tracer_provider=MagicMock()))
    monkeypatch.setattr(telemetry, "OTLPGrpcSpanExporter", lambda endpoint, insecure=True: exporter)
    monkeypatch.setattr(telemetry, "OTLPHTTPSpanExporter", lambda endpoint: exporter)

    assert configure_otel_tracing(
        service_name="session-buddy",
        environment="test",
        endpoint="http://localhost:4318",
        protocol="http/protobuf",
        resource_attributes={"custom.attr": "value"},
    )
    assert provider.add_span_processor.called
    assert resource_data["custom.attr"] == "value"
    assert resource_data["service.name"] == "session-buddy"


def test_configure_otel_tracing_does_not_reregister_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", True)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    provider = MagicMock()
    monkeypatch.setattr(telemetry, "TracerProvider", lambda resource=None: provider)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exp: ("processor", exp))
    monkeypatch.setattr(telemetry, "Resource", SimpleNamespace(create=lambda data: data))
    register_mock = MagicMock()
    monkeypatch.setattr("session_buddy.mcp.telemetry.atexit.register", register_mock)
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(set_tracer_provider=MagicMock()))
    monkeypatch.setattr(telemetry, "OTLPGrpcSpanExporter", lambda endpoint, insecure=True: MagicMock())
    monkeypatch.setattr(telemetry, "OTLPHTTPSpanExporter", lambda endpoint: MagicMock())

    assert configure_otel_tracing(
        service_name="session-buddy",
        environment="test",
        endpoint="http://localhost:4317",
        protocol="grpc",
    )
    register_mock.assert_not_called()


def test_shutdown_otel_tracing_shuts_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_buddy.mcp import telemetry

    provider = MagicMock()
    monkeypatch.setattr(telemetry, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(telemetry, "_TRACING_CONFIGURED", True)

    assert telemetry.shutdown_otel_tracing() is True
    provider.shutdown.assert_called_once()
    assert telemetry._TRACER_PROVIDER is None
    assert telemetry._TRACING_CONFIGURED is False


def test_shutdown_otel_tracing_no_provider_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp import telemetry

    monkeypatch.setattr(telemetry, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(telemetry, "_TRACING_CONFIGURED", True)

    assert telemetry.shutdown_otel_tracing() is False
    assert telemetry._TRACING_CONFIGURED is False


def test_shutdown_otel_tracing_without_shutdown_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp import telemetry

    provider = object()
    monkeypatch.setattr(telemetry, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(telemetry, "_TRACING_CONFIGURED", True)

    assert telemetry.shutdown_otel_tracing() is False


def test_attach_otel_middleware_adds_middleware() -> None:
    captured = []

    class DummyMCP:
        def add_middleware(self, middleware):
            captured.append(middleware)

    mcp = DummyMCP()

    assert attach_otel_middleware(mcp, service_name="session-buddy")
    assert captured and captured[0].service_name == "session-buddy"


def test_attach_otel_middleware_missing_method_returns_false() -> None:
    assert attach_otel_middleware(object(), service_name="session-buddy") is False


def test_server_registers_shared_otel_middleware() -> None:
    from session_buddy.server_optimized import mcp

    assert hasattr(mcp, "middleware")
    assert any(isinstance(middleware, FastMCPOpenTelemetryMiddleware) for middleware in mcp.middleware)
