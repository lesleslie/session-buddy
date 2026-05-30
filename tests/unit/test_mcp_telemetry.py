"""Unit tests for OTel telemetry module.

Tests:
- attach_otel_middleware function
- configure_otel_tracing function
- shutdown_otel_tracing function
- Module-level state management
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestAttachOtelMiddleware:
    """Tests for attach_otel_middleware function."""

    def test_attach_middleware_success(self) -> None:
        """Test attaching middleware to a valid FastMCP server."""
        from session_buddy.mcp.telemetry import attach_otel_middleware

        mock_mcp = MagicMock()
        mock_mcp.add_middleware = MagicMock()

        result = attach_otel_middleware(
            mock_mcp,
            service_name="test-service",
            environment="test",
            service_namespace="test-namespace",
        )

        assert result is True
        mock_mcp.add_middleware.assert_called_once()

    def test_attach_middleware_no_add_middleware(self) -> None:
        """Test attaching middleware fails gracefully when method missing."""
        from session_buddy.mcp.telemetry import attach_otel_middleware

        mock_mcp = MagicMock(spec=[])  # No add_middleware method

        result = attach_otel_middleware(mock_mcp, service_name="test-service")

        assert result is False


class TestConfigureOtelTracing:
    """Tests for configure_otel_tracing function."""

    def test_configure_returns_false_when_otel_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that tracing setup returns False when OTel is not available."""
        from session_buddy.mcp import telemetry

        # Force OTel as unavailable
        monkeypatch.setattr(telemetry, "_OTEL_AVAILABLE", False)

        result = telemetry.configure_otel_tracing(
            service_name="test-service",
        )

        assert result is False

    def test_configure_returns_false_when_already_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that tracing setup returns True if already configured."""
        from session_buddy.mcp import telemetry

        # Set OTel as available but tracing already configured
        monkeypatch.setattr(telemetry, "_OTEL_AVAILABLE", True)
        monkeypatch.setattr(telemetry, "_TRACING_CONFIGURED", True)

        result = telemetry.configure_otel_tracing(
            service_name="test-service",
        )

        assert result is True

    def test_configure_returns_false_when_no_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that tracing setup returns False when no endpoint is configured."""
        from session_buddy.mcp import telemetry

        # Set OTel as available but no endpoint
        monkeypatch.setattr(telemetry, "_OTEL_AVAILABLE", True)
        monkeypatch.setattr(telemetry, "_TRACING_CONFIGURED", False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

        result = telemetry.configure_otel_tracing(
            service_name="test-service",
        )

        assert result is False

    def test_configure_with_endpoint_http_protocol(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test tracing configuration with HTTP protocol."""
        from session_buddy.mcp import telemetry

        # Reset global state
        monkeypatch.setattr(telemetry, "_TRACING_CONFIGURED", False)
        monkeypatch.setattr(telemetry, "_TRACER_PROVIDER", None)
        monkeypatch.setattr(telemetry, "_SHUTDOWN_REGISTERED", True)
        monkeypatch.setattr(telemetry, "_OTEL_AVAILABLE", True)

        # Mock the OTel classes
        mock_provider = MagicMock()
        mock_resource = MagicMock()
        mock_exporter = MagicMock()
        mock_span_processor = MagicMock()

        class MockResource:
            @staticmethod
            def create(attrs):
                return mock_resource

        class MockTracerProvider:
            def __init__(self, resource):
                pass

            def add_span_processor(self, processor):
                pass

            @property
            def shutdown(self):
                return MagicMock()

        class MockHTTPSpanExporter:
            def __init__(self, endpoint):
                pass

        class MockBatchSpanProcessor:
            def __init__(self, exporter):
                pass

        # Apply patches
        monkeypatch.setattr(telemetry, "Resource", MockResource)
        monkeypatch.setattr(telemetry, "TracerProvider", MockTracerProvider)
        monkeypatch.setattr(telemetry, "OTLPHTTPSpanExporter", MockHTTPSpanExporter)
        monkeypatch.setattr(telemetry, "BatchSpanProcessor", MockBatchSpanProcessor)

        with patch.object(telemetry.trace, "set_tracer_provider"):
            result = telemetry.configure_otel_tracing(
                service_name="test-service",
                environment="test",
                service_namespace="test-ns",
                endpoint="http://localhost:4317",
                protocol="http",
            )

        assert result is True
        assert telemetry._TRACING_CONFIGURED is True


class TestShutdownOtelTracing:
    """Tests for shutdown_otel_tracing function."""

    def test_shutdown_returns_false_when_no_provider(self) -> None:
        """Test shutdown returns False when no provider is set."""
        from session_buddy.mcp import telemetry

        # Reset global state
        original_provider = getattr(telemetry, "_TRACER_PROVIDER", None)
        telemetry._TRACER_PROVIDER = None

        try:
            result = telemetry.shutdown_otel_tracing()

            assert result is False
            assert telemetry._TRACING_CONFIGURED is False
        finally:
            telemetry._TRACER_PROVIDER = original_provider

    def test_shutdown_calls_provider_shutdown(self) -> None:
        """Test shutdown calls the provider's shutdown method."""
        from session_buddy.mcp import telemetry

        # Reset global state
        mock_provider = MagicMock()
        mock_shutdown = MagicMock(return_value=None)
        mock_provider.shutdown = mock_shutdown

        telemetry._TRACER_PROVIDER = mock_provider
        telemetry._TRACING_CONFIGURED = True

        result = telemetry.shutdown_otel_tracing()

        assert result is True
        mock_shutdown.assert_called_once()
        assert telemetry._TRACER_PROVIDER is None
        assert telemetry._TRACING_CONFIGURED is False

    def test_shutdown_returns_false_when_shutdown_not_callable(self) -> None:
        """Test shutdown returns False when provider has no shutdown method."""
        from session_buddy.mcp import telemetry

        # Provider without shutdown method
        mock_provider = MagicMock(spec=["resource"])  # No shutdown attribute

        telemetry._TRACER_PROVIDER = mock_provider
        telemetry._TRACING_CONFIGURED = True

        result = telemetry.shutdown_otel_tracing()

        assert result is False


class TestTelemetryModuleExports:
    """Tests for module-level exports."""

    def test_module_exports_correct_functions(self) -> None:
        """Test that __all__ contains expected functions."""
        from session_buddy.mcp import telemetry

        expected_exports = [
            "attach_otel_middleware",
            "configure_otel_tracing",
            "shutdown_otel_tracing",
        ]

        for export in expected_exports:
            assert export in telemetry.__all__
            assert hasattr(telemetry, export)
