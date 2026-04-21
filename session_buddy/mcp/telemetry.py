"""OpenTelemetry bootstrap helpers for Session-Buddy's FastMCP server."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from mcp_common.server.telemetry import FastMCPOpenTelemetryMiddleware

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as OTLPGrpcSpanExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as OTLPHTTPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional runtime dependency
    trace = None  # type: ignore[assignment]
    OTLPGrpcSpanExporter = None  # type: ignore[assignment]
    OTLPHTTPSpanExporter = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)
_TRACING_CONFIGURED = False


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
    global _TRACING_CONFIGURED
    if _TRACING_CONFIGURED:
        return True

    if not _OTEL_AVAILABLE:
        logger.debug("OpenTelemetry SDK not available; skipping tracing setup")
        return False

    otel_protocol = (
        protocol or os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") or "grpc"
    ).lower()
    otel_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otel_endpoint:
        otel_endpoint = (
            "http://localhost:4318"
            if otel_protocol.startswith("http")
            else "http://localhost:4317"
        )

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
        exporter = OTLPHTTPSpanExporter(endpoint=otel_endpoint)
    else:
        exporter = OTLPGrpcSpanExporter(endpoint=otel_endpoint, insecure=True)

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
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


__all__ = [
    "attach_otel_middleware",
    "configure_otel_tracing",
]
