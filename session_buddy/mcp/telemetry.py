"""OpenTelemetry bootstrap helpers for Session-Buddy's FastMCP server."""

from __future__ import annotations

import atexit
import logging
import os
import sys
from collections.abc import Mapping
from typing import Any

from mcp_common.server.telemetry import FastMCPOpenTelemetryMiddleware

try:
    from opentelemetry import trace  # ty: ignore[unresolved-import]
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # ty: ignore[unresolved-import]
        OTLPSpanExporter as OTLPGrpcSpanExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # ty: ignore[unresolved-import]
        OTLPSpanExporter as OTLPHTTPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource  # ty: ignore[unresolved-import]
    from opentelemetry.sdk.trace import TracerProvider  # ty: ignore[unresolved-import]
    from opentelemetry.sdk.trace.export import (  # ty: ignore[unresolved-import]
        BatchSpanProcessor,
    )

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional runtime dependency
    trace: Any = None
    OTLPGrpcSpanExporter: Any = None
    OTLPHTTPSpanExporter: Any = None
    Resource: Any = None
    TracerProvider: Any = None
    BatchSpanProcessor: Any = None
    _OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)
_TRACING_CONFIGURED = False
_TRACER_PROVIDER: TracerProvider | None = None
_SHUTDOWN_REGISTERED = False


def attach_otel_middleware(
    mcp: Any,
    *,
    service_name: str,
    environment: str = "production",
    service_namespace: str = "session-buddy",
) -> bool:
    """Attach shared MCP OpenTelemetry middleware to a FastMCP server."""
    if not hasattr(mcp, "add_middleware"):
        return False

    middleware = FastMCPOpenTelemetryMiddleware(
        service_name=service_name,
        environment=environment,
        service_namespace=service_namespace,
    )
    mcp.add_middleware(middleware)
    logger.info(
        "Registered Session-Buddy FastMCP OpenTelemetry middleware",
        extra={
            "service_name": service_name,
            "environment": environment,
            "service_namespace": service_namespace,
        },
    )
    return True


def configure_otel_tracing(
    *,
    service_name: str,
    environment: str = "production",
    service_namespace: str = "session-buddy",
    endpoint: str | None = None,
    protocol: str | None = None,
    resource_attributes: Mapping[str, str] | None = None,
) -> bool:
    """Configure the OpenTelemetry tracer provider for Session-Buddy."""
    global _TRACING_CONFIGURED, _TRACER_PROVIDER, _SHUTDOWN_REGISTERED
    if _TRACING_CONFIGURED:
        return True

    if not _OTEL_AVAILABLE:
        logger.debug("OpenTelemetry SDK not available; skipping tracing setup")
        return False

    if endpoint is None and "pytest" in sys.modules:
        logger.debug("Pytest detected without explicit OTEL endpoint; skipping")
        return False

    otel_protocol = (
        protocol or os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") or "grpc"
    ).lower()
    otel_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otel_endpoint:
        logger.debug(
            "OpenTelemetry endpoint not configured; skipping tracing setup",
        )
        return False

    resource_data: dict[str, str] = {
        "service.name": service_name,
        "service.namespace": service_namespace,
        "deployment.environment": environment,
        "telemetry.source": "session-buddy",
        "telemetry.source.type": "mcp_server",
    }
    if resource_attributes:
        resource_data.update(resource_attributes)

    resource = Resource.create(resource_data)
    provider = TracerProvider(resource=resource)

    if otel_protocol.startswith("http"):
        exporter: Any = OTLPHTTPSpanExporter(endpoint=otel_endpoint)
    else:
        exporter = OTLPGrpcSpanExporter(endpoint=otel_endpoint, insecure=True)

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER_PROVIDER = provider
    if not _SHUTDOWN_REGISTERED:
        atexit.register(shutdown_otel_tracing)
        _SHUTDOWN_REGISTERED = True
    logger.info(
        "Configured Session-Buddy OpenTelemetry tracing",
        extra={
            "service_name": service_name,
            "service_namespace": service_namespace,
            "environment": environment,
            "endpoint": otel_endpoint,
            "protocol": otel_protocol,
        },
    )
    _TRACING_CONFIGURED = True
    return True


def shutdown_otel_tracing() -> bool:
    """Shut down the configured OpenTelemetry tracer provider if present."""
    global _TRACING_CONFIGURED, _TRACER_PROVIDER
    provider = _TRACER_PROVIDER
    _TRACER_PROVIDER = None
    _TRACING_CONFIGURED = False

    if provider is None:
        return False

    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        shutdown()
        return True
    return False


__all__ = [
    "attach_otel_middleware",
    "configure_otel_tracing",
    "shutdown_otel_tracing",
]
