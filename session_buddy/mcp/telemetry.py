"""OpenTelemetry bootstrap helpers for Session-Buddy's FastMCP server."""

from __future__ import annotations

import atexit
import logging
import os
import sys
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from mcp_common.server.producer_telemetry import configure_producer_tracing
from mcp_common.server.telemetry import FastMCPOpenTelemetryMiddleware

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

try:
    from opentelemetry import trace

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional runtime dependency
    trace: Any = None
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
    service_namespace: str = "bodai",
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
    service_namespace: str = "bodai",
    endpoint: str | None = None,
    protocol: str | None = None,
    resource_attributes: Mapping[str, str] | None = None,
) -> bool:
    """Configure the OpenTelemetry tracer provider for Session-Buddy.

    The provider itself is built by mcp-common's shared producer
    telemetry helper, so Session-Buddy's exporter resolves the collector
    the same way every other core service's does.

    That resolution used to be done here, and it was wrong in a way that
    looked healthy: the endpoint was handed to the exporter verbatim,
    but the exporter treats an explicit endpoint as the COMPLETE URL
    including the signal path. Pointing it at ``http://127.0.0.1:4318``
    therefore posted to the port's root rather than to
    ``/v1/traces``, and every batch came back ``404 Not Found``. The
    receiver never saw the spans, and no metric showed it -- a rejected
    request and a request that was never made look the same from here.

    The namespace default was wrong too, in the quieter way. The
    receiver's allowlist is a fixed set of NAMESPACES (``bodai``,
    ``cli-tools``), and ``session-buddy`` is a service NAME. A span
    carrying it would have been quarantined as namespace drift even
    once the path was right.
    """
    global _TRACING_CONFIGURED, _TRACER_PROVIDER, _SHUTDOWN_REGISTERED
    if _TRACING_CONFIGURED:
        return True

    if not _OTEL_AVAILABLE:
        logger.debug("OpenTelemetry SDK not available; skipping tracing setup")
        return False

    if endpoint is None and "pytest" in sys.modules:
        logger.debug("Pytest detected without explicit OTEL endpoint; skipping")
        return False

    extra_attributes: dict[str, str] = {
        "telemetry.source": "session-buddy",
        "telemetry.source.type": "mcp_server",
    }
    if resource_attributes:
        extra_attributes.update(resource_attributes)

    configured = configure_producer_tracing(
        service_name,
        service_namespace=service_namespace,
        environment=environment,
        endpoint=endpoint,
        protocol=protocol,
        resource_attributes=extra_attributes,
    )
    if not configured:
        logger.debug(
            "OpenTelemetry endpoint not configured; skipping tracing setup",
        )
        return False

    _TRACER_PROVIDER = trace.get_tracer_provider()
    if not _SHUTDOWN_REGISTERED:
        atexit.register(shutdown_otel_tracing)
        _SHUTDOWN_REGISTERED = True
    logger.info(
        "Configured Session-Buddy OpenTelemetry tracing",
        extra={
            "service_name": service_name,
            "service_namespace": service_namespace,
            "environment": environment,
            "endpoint": endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            "protocol": protocol or os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL"),
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
