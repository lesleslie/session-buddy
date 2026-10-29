from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mcp_common.server.producer_telemetry import ProducerTracingResult
from mcp_common.server.telemetry import FastMCPOpenTelemetryMiddleware

from session_buddy.mcp import telemetry
from session_buddy.mcp.telemetry import attach_otel_middleware, configure_otel_tracing


def test_configure_otel_tracing_delegates_to_the_shared_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider is built by mcp-common's shared producer telemetry.

    Session-Buddy used to build its own, and got the collector endpoint
    wrong: the exporter treats an explicit endpoint as the COMPLETE URL
    including the signal path, so pointing it at the port's root posted
    to the wrong place and every batch came back 404. The receiver never
    saw the spans, and no metric showed it -- a rejected request and a
    request that was never made look the same from here.
    """
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    helper = MagicMock(return_value=ProducerTracingResult(MagicMock(), True))
    monkeypatch.setattr(telemetry, "configure_producer_tracing", helper)
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(get_tracer_provider=MagicMock()))

    assert configure_otel_tracing(
        service_name="session-buddy",
        environment="test",
        endpoint="http://localhost:4317",
        protocol="grpc",
    )
    helper.assert_called_once()
    assert helper.call_args.args[0] == "session-buddy"


def test_configure_otel_tracing_reports_the_fleet_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The namespace is "bodai", not the service name.

    The receiver's allowlist is a fixed set of NAMESPACES ("bodai",
    "cli-tools"). "session-buddy" is a service NAME, and a span
    carrying it as its namespace would have been quarantined as
    namespace drift even once the endpoint was right.
    """
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    helper = MagicMock(return_value=ProducerTracingResult(MagicMock(), True))
    monkeypatch.setattr(telemetry, "configure_producer_tracing", helper)
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(get_tracer_provider=MagicMock()))

    configure_otel_tracing(
        service_name="session-buddy",
        environment="test",
        endpoint="http://127.0.0.1:4318",
    )

    assert helper.call_args.kwargs["service_namespace"] == "bodai"


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
    monkeypatch.setattr(
        telemetry,
        "configure_producer_tracing",
        MagicMock(return_value=ProducerTracingResult(None, False)),
    )
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(get_tracer_provider=MagicMock()))

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
    helper = MagicMock(return_value=ProducerTracingResult(MagicMock(), True))
    monkeypatch.setattr(telemetry, "configure_producer_tracing", helper)
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(get_tracer_provider=MagicMock()))

    assert configure_otel_tracing(
        service_name="session-buddy",
        environment="test",
        endpoint="http://localhost:4318",
        protocol="http/protobuf",
        resource_attributes={"custom.attr": "value"},
    )
    assert helper.call_args.kwargs["protocol"] == "http/protobuf"
    assert helper.call_args.kwargs["endpoint"] == "http://localhost:4318"
    attributes = helper.call_args.kwargs["resource_attributes"]
    assert attributes["custom.attr"] == "value"
    assert attributes["telemetry.source"] == "session-buddy"


def test_configure_otel_tracing_does_not_reregister_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACING_CONFIGURED", False)
    monkeypatch.setattr("session_buddy.mcp.telemetry._TRACER_PROVIDER", None)
    monkeypatch.setattr("session_buddy.mcp.telemetry._SHUTDOWN_REGISTERED", True)
    monkeypatch.setattr("session_buddy.mcp.telemetry._OTEL_AVAILABLE", True)
    monkeypatch.setattr(
        telemetry,
        "configure_producer_tracing",
        MagicMock(return_value=ProducerTracingResult(MagicMock(), True)),
    )
    register_mock = MagicMock()
    monkeypatch.setattr("session_buddy.mcp.telemetry.atexit.register", register_mock)
    monkeypatch.setattr(telemetry, "trace", SimpleNamespace(get_tracer_provider=MagicMock()))

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


class TestProviderOwnership:
    """Session-Buddy closes only the provider it installed.

    The shared helper reports two separate facts: whether spans will
    export, and whether the provider is OURS. A provider somebody else
    installed still exports spans -- but closing it at exit would be us
    reaching into another component's exporter and flushing its spans
    into the void.
    """

    def _reset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from session_buddy.mcp import telemetry

        monkeypatch.setattr(telemetry, "_TRACING_CONFIGURED", False)
        monkeypatch.setattr(telemetry, "_TRACER_PROVIDER", None)
        monkeypatch.setattr(telemetry, "_SHUTDOWN_REGISTERED", False)
        monkeypatch.setattr(telemetry, "_OTEL_AVAILABLE", True)

    def test_the_provider_we_installed_is_captured_and_shut_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.mcp import telemetry

        self._reset(monkeypatch)

        provider = MagicMock()
        monkeypatch.setattr(
            telemetry,
            "configure_producer_tracing",
            MagicMock(return_value=ProducerTracingResult(provider, True)),
        )
        monkeypatch.setattr(
            telemetry,
            "trace",
            SimpleNamespace(get_tracer_provider=MagicMock(return_value=provider)),
        )
        register_mock = MagicMock()
        monkeypatch.setattr("session_buddy.mcp.telemetry.atexit.register", register_mock)

        assert (
            configure_otel_tracing(
                service_name="session-buddy",
                environment="test",
                endpoint="http://127.0.0.1:4318",
            )
            is True
        )

        assert telemetry._TRACER_PROVIDER is provider
        register_mock.assert_called_once()

        # And it is ours to close.
        assert telemetry.shutdown_otel_tracing() is True
        provider.shutdown.assert_called_once()

    def test_a_provider_installed_by_someone_else_is_never_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.mcp import telemetry

        self._reset(monkeypatch)

        foreign = MagicMock()
        monkeypatch.setattr(
            telemetry,
            "configure_producer_tracing",
            MagicMock(return_value=ProducerTracingResult(None, True)),
        )
        monkeypatch.setattr(
            telemetry,
            "trace",
            SimpleNamespace(get_tracer_provider=MagicMock(return_value=foreign)),
        )
        register_mock = MagicMock()
        monkeypatch.setattr("session_buddy.mcp.telemetry.atexit.register", register_mock)

        # Tracing IS active -- the incumbent's provider exports spans --
        # so this call still reports success.
        assert (
            configure_otel_tracing(
                service_name="session-buddy",
                environment="test",
                endpoint="http://127.0.0.1:4318",
            )
            is True
        )

        # But the incumbent's provider is not captured, and no shutdown
        # is registered for it: it is not ours to close.
        assert telemetry._TRACER_PROVIDER is None
        register_mock.assert_not_called()

        assert telemetry.shutdown_otel_tracing() is False
        foreign.shutdown.assert_not_called()
