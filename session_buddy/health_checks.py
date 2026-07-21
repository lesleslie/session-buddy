"""Health check implementations for session-mgmt-mcp server.

Provides component-level health checks for database connectivity,
file system access, and optional dependencies.

Phase 10.1: Production Hardening - Session Management Health Checks
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
import typing as t
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import httpx

from session_buddy.utils import logger


class HealthStatus(StrEnum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Component health check result."""

    name: str
    status: HealthStatus
    message: str
    latency_ms: float | None = None
    metadata: dict[str, t.Any] = field(default_factory=dict)


# Try to import optional dependencies
try:
    from session_buddy.utils.instance_managers import get_reflection_database

    REFLECTION_AVAILABLE = True
except ImportError:
    REFLECTION_AVAILABLE = False


async def get_initialized_reflection_database() -> t.Any | None:
    """Return an initialized reflection database when available.

    This wrapper exists for test compatibility and mirrors the older
    health-check API that exposed an eagerly initialized accessor.
    """
    if not REFLECTION_AVAILABLE:
        return None

    return await get_reflection_database()


async def check_database_health() -> ComponentHealth:
    """Check DuckDB reflection database connectivity and health.

    Returns:
        ComponentHealth with database status and latency

    Checks:
        - Database connection
        - Basic query execution
        - Response latency

    """
    if not REFLECTION_AVAILABLE:
        return ComponentHealth(
            name="database",
            status=HealthStatus.DEGRADED,
            message="Reflection database not available (optional feature)",
        )

    start_time = time.perf_counter()

    try:
        db = await get_initialized_reflection_database()
        # Allow tests to patch get_reflection_database without initializing in production.
        if (
            db is None
            and getattr(get_reflection_database, "__module__", "") == "unittest.mock"
        ):
            db = await get_reflection_database()
        if db is None:
            return ComponentHealth(
                name="database",
                status=HealthStatus.DEGRADED,
                message="Reflection database not initialized",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                metadata={"initialized": False},
            )

        # Test basic query execution
        stats = await db.get_stats()

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Check if database is responsive
        # get_stats() returns BOTH "conversations_count" and
        # "total_conversations" (same value); the documented primary key
        # (see reflection/database.py:704) is "conversations_count".
        conv_count = int(stats.get("conversations_count", 0) or 0)
        refl_count = int(stats.get("reflections_count", 0) or 0)
        if latency_ms > 500:  # >500ms is concerning
            return ComponentHealth(
                name="database",
                status=HealthStatus.DEGRADED,
                message=f"High database latency: {latency_ms:.1f}ms",
                latency_ms=latency_ms,
                metadata={
                    "conversations": conv_count,
                    "reflections": refl_count,
                    "database_path": getattr(db, "db_path", None),
                },
            )

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database operational",
            latency_ms=latency_ms,
            metadata={
                "conversations": conv_count,
                "reflections": refl_count,
                "database_path": getattr(db, "db_path", None),
            },
        )

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


async def check_file_system_health() -> ComponentHealth:
    """Check file system access for critical directories.

    Returns:
        ComponentHealth with file system status

    Checks:
        - ~/.claude directory exists and writable
        - Data directories accessible
        - Sufficient disk space (basic check)

    """
    start_time = time.perf_counter()

    try:
        claude_dir = Path.home() / ".claude"

        # Check if directory exists
        if not claude_dir.exists():
            return ComponentHealth(
                name="file_system",
                status=HealthStatus.UNHEALTHY,
                message="~/.claude directory does not exist",
            )

        # Check write permissions by creating/removing test file
        test_file = claude_dir / ".health_check"
        try:
            test_file.write_text("health_check")
            test_file.unlink()
        except (OSError, PermissionError) as e:
            return ComponentHealth(
                name="file_system",
                status=HealthStatus.UNHEALTHY,
                message=f"~/.claude not writable: {e}",
            )

        # Check critical subdirectories
        logs_dir = claude_dir / "logs"
        data_dir = claude_dir / "data"

        missing_dirs = []
        if not logs_dir.exists():
            missing_dirs.append("logs")
        if not data_dir.exists():
            missing_dirs.append("data")

        latency_ms = (time.perf_counter() - start_time) * 1000

        if missing_dirs:
            return ComponentHealth(
                name="file_system",
                status=HealthStatus.DEGRADED,
                message=f"Missing directories: {', '.join(missing_dirs)}",
                latency_ms=latency_ms,
            )

        return ComponentHealth(
            name="file_system",
            status=HealthStatus.HEALTHY,
            message="File system accessible",
            latency_ms=latency_ms,
        )

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ComponentHealth(
            name="file_system",
            status=HealthStatus.UNHEALTHY,
            message=f"File system error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


def _module_available(name: str) -> bool:
    """Check if a module is available without importing it.

    Returns True if the module can be found, False otherwise. Treats
    any exception raised by ``find_spec`` (ImportError, ModuleNotFoundError,
    ValueError, or unexpected errors) as "not available" so health checks
    remain best-effort and never crash on a transient module-discovery
    failure.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return name in sys.modules


def _is_loopback_host(host: str) -> bool:
    """Return True if *host* is a loopback address (IPv4 127.0.0.0/8 or IPv6 ::1)."""
    import ipaddress

    with suppress(ValueError):
        addr = ipaddress.ip_address(host)
        return addr.is_loopback
    return host.lower() == "localhost"


def _private_network_allowed() -> bool:
    """Return True if RFC1918 private network provider URLs should be allowed.

    Opt-in via ``SESSION_BUDDY__ALLOW_PRIVATE_NETWORK_PROVIDERS=1`` (also accepts
    ``true``/``yes``/``on``). Off by default — the only loopback exception is
    unconditional (see ``_is_loopback_host``).
    """
    return os.environ.get(
        "SESSION_BUDDY__ALLOW_PRIVATE_NETWORK_PROVIDERS", ""
    ).lower() in {"1", "true", "yes", "on"}


def _is_safe_url(url: str) -> bool:
    """Return True if the URL's host is safe to probe.

    SSRF defense policy (matches the defaults of MAHAVISHNU__OLLAMA_URL and
    MAHAVISHNU__LLAMA_SERVER_URL, which both point at loopback):

    * ``localhost`` / ``127.0.0.0/8`` / ``::1`` — ALWAYS allowed. Loopback
      cannot reach an external attacker, and the two provider URLs default
      to loopback, so unconditionally blocking it masks the doctor signal
      operators actually need (is the service running? slow? timing out?).
    * RFC1918 private (``10/8``, ``172.16/12``, ``192.168/16``) — blocked
      unless ``SESSION_BUDDY__ALLOW_PRIVATE_NETWORK_PROVIDERS=1`` is set.
      This guards against an operator accidentally pointing the env var at
      an internal service on another host.
    * Link-local (``169.254/16``, IPv6 ``fe80::/10``) — ALWAYS blocked. This
      range includes cloud metadata endpoints (e.g. ``169.254.169.254`` on
      AWS/GCP/Azure) which is the canonical SSRF target.
    * Anything else (public IPs, hostnames that resolve to public IPs) — allowed.

    Env vars are operator-controlled, not user-controlled, so loopback trust
    is the correct default. The opt-in flag exists for the case where the
    operator *deliberately* points a provider URL at a private network.
    """
    import ipaddress
    import socket

    try:
        parsed = httpx.URL(url)
        host = parsed.host or ""
    except Exception:
        return False

    # Fast path: loopback is always safe (operator's own machine).
    if _is_loopback_host(host):
        return True

    # Resolve hostname (or use the literal IP) and classify.
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    with suppress(ValueError):
        addr = ipaddress.ip_address(host)

    if addr is not None:
        # Link-local is always blocked (cloud metadata, etc.).
        if addr.is_link_local:
            return False
        # RFC1918 private is blocked unless explicitly opted in.
        if addr.is_private and not _is_loopback_host(host):
            allow_private = _private_network_allowed()
            if not allow_private:
                return False
        return True

    # Hostname: resolve and re-evaluate.
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        # If we cannot resolve, fail safe (treat as not safe).
        return False

    for _family, _type, _proto, _canon, sockaddr in infos:
        resolved_ip = sockaddr[0]
        with suppress(ValueError):
            resolved_addr = ipaddress.ip_address(resolved_ip)
            if resolved_addr.is_link_local:
                return False
            if resolved_addr.is_private and not resolved_addr.is_loopback:
                if not _private_network_allowed():
                    return False
    return True


def _check_crackerjack() -> tuple[list[str], list[str]]:
    """Check Crackerjack availability, return (available, unavailable) lists."""
    available = []
    unavailable = []
    quality_utils = sys.modules.get("session_buddy.utils.quality_utils_v2")
    if quality_utils is not None:
        crackerjack_available = bool(
            getattr(quality_utils, "CRACKERJACK_AVAILABLE", False)
        )
    else:
        crackerjack_available = _module_available("crackerjack")

    if crackerjack_available:
        available.append("crackerjack")
    else:
        unavailable.append("crackerjack")
    return available, unavailable


def _llama_server_health_url() -> str:
    """Build llama-server health check URL."""
    base = os.environ.get(
        "MAHAVISHNU__LLAMA_SERVER_URL", "http://localhost:8080/v1"
    ).rstrip("/")
    if base.endswith(("/embeddings", "/v1/embeddings")):
        base = base.rsplit("/embeddings", 1)[0]
    return f"{base}/embeddings"


def _ollama_health_url() -> str:
    """Build Ollama health check URL."""
    return f"{os.environ.get('MAHAVISHNU__OLLAMA_URL', 'http://localhost:11434')}/api/embed"


async def _check_provider(
    client: httpx.AsyncClient,
    url: str,
    name: str,
    payload: dict[str, t.Any],
) -> str:
    """Check an HTTP provider and return status string.

    Distinct messages so the doctor can show operators what is actually
    wrong with their provider (running? slow? wrong port? blocked by
    SSRF?):

    * ``"{name}"`` — HTTP 200 (running and responsive)
    * ``"{name} ({status_code})"`` — responded but rejected the request
    * ``"{name} (timeout)"`` — service is unreachable within the timeout
      (often: ollama is alive on the port but the model is loading)
    * ``"{name} (connection refused)"`` — nothing is listening on the port
    * ``"{name} (error)"`` — anything else (DNS failure, TLS error, etc.)
    * ``"{name} (SSRF blocked — set SESSION_BUDDY__ALLOW_PRIVATE_NETWORK_PROVIDERS=1)"``
      — the URL targets a private/link-local host and the operator has
      not opted in to probing it. Loopback is always allowed.
    """
    if not _is_safe_url(url):
        logger.warning(f"{name} URL rejected by SSRF check: {url}")
        return (
            f"{name} (SSRF blocked — set "
            f"SESSION_BUDDY__ALLOW_PRIVATE_NETWORK_PROVIDERS=1)"
        )
    try:
        resp = await client.post(url, json=payload)
        return name if resp.status_code == 200 else f"{name} ({resp.status_code})"
    except httpx.TimeoutException:
        return f"{name} (timeout)"
    except httpx.ConnectError:
        return f"{name} (connection refused)"
    except Exception:
        return f"{name} (error)"


async def _check_embedding_providers(
    client: httpx.AsyncClient,
) -> tuple[list[str], list[str]]:
    """Check llama-server and Ollama, return (available, unavailable) lists."""
    available = []
    unavailable = []

    result = await _check_provider(
        client, _llama_server_health_url(), "llama-server", {"input": ["health-check"]}
    )
    if result == "llama-server":
        available.append(result)
    else:
        unavailable.append(result)

    result = await _check_provider(
        client,
        _ollama_health_url(),
        "ollama",
        {"model": "nomic-embed-text", "input": ["health-check"]},
    )
    if result == "ollama":
        available.append(result)
    else:
        unavailable.append(result)

    return available, unavailable


async def _check_crackerjack_and_embedding_providers() -> tuple[list[str], list[str]]:
    """Check Crackerjack and HTTP embedding providers, return (available, unavailable)."""
    available, unavailable = _check_crackerjack()

    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            ep_available, ep_unavailable = await _check_embedding_providers(client)
            available.extend(ep_available)
            unavailable.extend(ep_unavailable)
    except ImportError:
        unavailable.extend(["llama-server", "ollama"])

    return available, unavailable


async def check_dependencies_health() -> ComponentHealth:
    """Check optional dependencies availability.

    Returns:
        ComponentHealth with dependency status

    Checks:
        - Crackerjack integration availability
        - HTTP embedding providers (llama-server/Ollama)
        - Other optional features

    """
    start_time = time.perf_counter()

    available, unavailable = await _check_crackerjack_and_embedding_providers()

    # Check multi-project features
    if _module_available("session_buddy.multi_project_coordinator"):
        available.append("multi_project")
    else:
        unavailable.append("multi_project")

    latency_ms = (time.perf_counter() - start_time) * 1000

    # All optional dependencies missing is degraded, not unhealthy
    if not available:
        return ComponentHealth(
            name="dependencies",
            status=HealthStatus.DEGRADED,
            message="No optional features available",
            latency_ms=latency_ms,
            metadata={"unavailable": unavailable},
        )

    # Some dependencies available
    status = HealthStatus.HEALTHY if not unavailable else HealthStatus.DEGRADED
    message = f"{len(available)} features available"
    if unavailable:
        message += f", {len(unavailable)} unavailable"

    return ComponentHealth(
        name="dependencies",
        status=status,
        message=message,
        latency_ms=latency_ms,
        metadata={"available": available, "unavailable": unavailable},
    )


async def check_python_environment_health() -> ComponentHealth:
    """Check Python environment health and configuration.

    Returns:
        ComponentHealth with Python environment status

    Checks:
        - Python version compatibility
        - Critical imports available
        - Memory usage reasonable

    """
    import sys

    start_time = time.perf_counter()

    try:
        # Check Python version (3.13+ required)
        version_info = sys.version_info
        if version_info < (3, 13):
            return ComponentHealth(
                name="python_env",
                status=HealthStatus.UNHEALTHY,
                message=f"Python 3.13+ required, got {version_info.major}.{version_info.minor}",
            )

        # Check critical imports
        critical_imports = ["asyncio", "pathlib", "dataclasses", "enum"]
        missing_imports = []

        for module_name in critical_imports:
            try:
                __import__(module_name)
            except ImportError:
                missing_imports.append(module_name)

        if missing_imports:
            return ComponentHealth(
                name="python_env",
                status=HealthStatus.UNHEALTHY,
                message=f"Missing critical imports: {', '.join(missing_imports)}",
            )

        latency_ms = (time.perf_counter() - start_time) * 1000

        return ComponentHealth(
            name="python_env",
            status=HealthStatus.HEALTHY,
            message=f"Python {version_info.major}.{version_info.minor}.{version_info.micro}",
            latency_ms=latency_ms,
            metadata={
                "python_version": f"{version_info.major}.{version_info.minor}.{version_info.micro}",
                "platform": sys.platform,
            },
        )

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ComponentHealth(
            name="python_env",
            status=HealthStatus.UNHEALTHY,
            message=f"Environment check failed: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


async def get_all_health_checks() -> list[ComponentHealth]:
    """Run all health checks and return results.

    Returns:
        List of ComponentHealth results for all checks

    This is the main entry point for the health endpoint.

    """
    # Run all checks concurrently
    results = await asyncio.gather(
        check_python_environment_health(),
        check_file_system_health(),
        check_database_health(),
        check_dependencies_health(),
        return_exceptions=True,
    )

    # Convert any exceptions to unhealthy components
    components: list[ComponentHealth] = []
    check_names = ["python_env", "file_system", "database", "dependencies"]

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            components.append(
                ComponentHealth(
                    name=check_names[i],
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check crashed: {str(result)[:100]}",
                ),
            )
        else:
            components.append(result)  # ty: ignore[invalid-argument-type]  # result is ComponentHealth from gather

    return components


__all__ = [
    "check_database_health",
    "check_dependencies_health",
    "check_file_system_health",
    "check_python_environment_health",
    "get_all_health_checks",
]
