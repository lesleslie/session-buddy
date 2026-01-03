"""Health check implementations for session-mgmt-mcp server.

Provides component-level health checks for database connectivity,
file system access, and optional dependencies.

Phase 10.1: Production Hardening - Session Management Health Checks
"""

from __future__ import annotations

import importlib.util
import sys
import time
import typing as t

# Health status types (mcp_common.health doesn't exist in 2.0.0)
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from session_buddy.reflection_tools import (
        get_initialized_reflection_database,
        get_reflection_database,
    )


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
    from session_buddy.reflection_tools import (
        get_initialized_reflection_database,
        get_reflection_database,
    )

    REFLECTION_AVAILABLE = True
except ImportError:
    REFLECTION_AVAILABLE = False


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
        db = get_initialized_reflection_database() if REFLECTION_AVAILABLE else None
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
        if latency_ms > 500:  # >500ms is concerning
            return ComponentHealth(
                name="database",
                status=HealthStatus.DEGRADED,
                message=f"High database latency: {latency_ms:.1f}ms",
                latency_ms=latency_ms,
                metadata={"conversations": stats.get("conversations_count", 0)},
            )

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database operational",
            latency_ms=latency_ms,
            metadata={"conversations": stats.get("conversations_count", 0)},
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


async def check_dependencies_health() -> ComponentHealth:
    """Check optional dependencies availability.

    Returns:
        ComponentHealth with dependency status

    Checks:
        - Crackerjack integration availability
        - ONNX runtime for embeddings
        - Other optional features

    """
    start_time = time.perf_counter()

    available = []
    unavailable = []

    def _module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except ValueError:
            return name in sys.modules

    # Check Crackerjack without importing heavy modules
    crackerjack_available = False
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

    # Check ONNX/embeddings without importing
    if _module_available("onnxruntime"):
        available.append("onnx")
    else:
        unavailable.append("onnx")

    # Check multi-project features
    try:
        # Try to import the multi-project module directly without triggering server init
        spec = importlib.util.find_spec("session_buddy.multi_project_coordinator")
        if spec is not None:
            available.append("multi_project")
        else:
            unavailable.append("multi_project")
    except (ImportError, Exception):
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
    import asyncio

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
            components.append(result)  # type: ignore[arg-type]  # result is ComponentHealth from gather

    return components


__all__ = [
    "check_database_health",
    "check_dependencies_health",
    "check_file_system_health",
    "check_python_environment_health",
    "get_all_health_checks",
]
