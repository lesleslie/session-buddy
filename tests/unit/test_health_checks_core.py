"""Unit tests for health check implementations.

Tests component-level health checks including:
- Database connectivity and latency
- File system access and permissions
- Optional dependencies availability
- Python environment validation
- Concurrent health check execution
"""

from __future__ import annotations

import builtins
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.health_checks import (
    ComponentHealth,
    HealthStatus,
    check_database_health,
    check_dependencies_health,
    check_file_system_health,
    check_python_environment_health,
    get_all_health_checks,
    get_initialized_reflection_database,
)


class TestHealthStatus:
    """Test HealthStatus enum."""

    def test_health_status_values(self) -> None:
        """Test that HealthStatus has required values."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"

    def test_health_status_is_strenum(self) -> None:
        """Test that HealthStatus can be used as string."""
        status = HealthStatus.HEALTHY
        assert isinstance(status, str)
        assert str(status) == "healthy"


class TestComponentHealth:
    """Test ComponentHealth dataclass."""

    def test_component_health_basic(self) -> None:
        """Test creating basic ComponentHealth instance."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="All good",
        )
        assert health.name == "test"
        assert health.status == HealthStatus.HEALTHY
        assert health.message == "All good"
        assert health.latency_ms is None
        assert health.metadata == {}

    def test_component_health_with_latency(self) -> None:
        """Test ComponentHealth with latency."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.DEGRADED,
            message="Slow response",
            latency_ms=250.5,
        )
        assert health.latency_ms == 250.5

    def test_component_health_with_metadata(self) -> None:
        """Test ComponentHealth with metadata."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="Good",
            metadata={"version": "1.0", "count": 42},
        )
        assert health.metadata["version"] == "1.0"
        assert health.metadata["count"] == 42

    def test_component_health_all_fields(self) -> None:
        """Test ComponentHealth with all fields populated."""
        health = ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Operational",
            latency_ms=150.0,
            metadata={"queries": 100, "active": True},
        )
        assert health.name == "database"
        assert health.latency_ms == 150.0
        assert len(health.metadata) == 2


class TestCheckDatabaseHealth:
    """Test check_database_health function."""

    @pytest.mark.asyncio
    async def test_database_health_unavailable(self) -> None:
        """Test database health when reflection database is unavailable."""
        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", False
        ):
            health = await check_database_health()
            assert health.name == "database"
            assert health.status == HealthStatus.DEGRADED
            assert "not available" in health.message

    @pytest.mark.asyncio
    async def test_database_health_not_initialized(self) -> None:
        """Test database health when not initialized."""
        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", True
        ), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=None,
        ):
            health = await check_database_health()
            assert health.name == "database"
            assert health.status == HealthStatus.DEGRADED
            assert "not initialized" in health.message

    @pytest.mark.asyncio
    async def test_database_health_high_latency(self) -> None:
        """Test database health with high latency (>500ms)."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(
            return_value={"conversations_count": 10}
        )

        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", True
        ), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.6],  # 600ms latency
        ):
            health = await check_database_health()
            assert health.name == "database"
            assert health.status == HealthStatus.DEGRADED
            assert "latency" in health.message.lower()

    @pytest.mark.asyncio
    async def test_database_health_healthy(self) -> None:
        """Test database health when healthy."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(
            return_value={"conversations_count": 50}
        )

        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", True
        ), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.1],  # 100ms latency
        ):
            health = await check_database_health()
            assert health.name == "database"
            assert health.status == HealthStatus.HEALTHY
            assert "operational" in health.message.lower()
            assert health.metadata["conversations"] == 50

    @pytest.mark.asyncio
    async def test_database_health_exception(self) -> None:
        """Test database health when exception occurs."""
        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", True
        ), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection failed"),
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.05],
        ):
            health = await check_database_health()
            assert health.name == "database"
            assert health.status == HealthStatus.UNHEALTHY
            assert "error" in health.message.lower()

    @pytest.mark.asyncio
    async def test_database_health_uses_mocked_accessor_fallback(self) -> None:
        """Test fallback path when the initialized accessor returns None."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 7})

        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", True
        ), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "session_buddy.health_checks.get_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ):
            health = await check_database_health()

            assert health.name == "database"
            assert health.status == HealthStatus.HEALTHY
            assert health.metadata["conversations"] == 7


class TestCheckFileSystemHealth:
    """Test check_file_system_health function."""

    @pytest.mark.asyncio
    async def test_file_system_health_missing_claude_dir(self) -> None:
        """Test when ~/.claude directory doesn't exist."""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/nonexistent")
            with patch.object(
                Path, "exists", return_value=False
            ):
                health = await check_file_system_health()
                assert health.name == "file_system"
                assert health.status == HealthStatus.UNHEALTHY
                assert "does not exist" in health.message

    @pytest.mark.asyncio
    async def test_file_system_health_not_writable(self) -> None:
        """Test when ~/.claude is not writable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()

            with patch(
                "pathlib.Path.home", return_value=mock_home
            ), patch.object(
                Path, "write_text", side_effect=PermissionError("Permission denied")
            ):
                health = await check_file_system_health()
                assert health.name == "file_system"
                assert health.status == HealthStatus.UNHEALTHY
                assert "not writable" in health.message

    @pytest.mark.asyncio
    async def test_file_system_health_missing_subdirectories(self) -> None:
        """Test when required subdirectories are missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()
            # Create only logs dir, not data dir

            with patch("pathlib.Path.home", return_value=mock_home):
                (claude_dir / "logs").mkdir()
                health = await check_file_system_health()
                assert health.name == "file_system"
                assert health.status == HealthStatus.DEGRADED
                assert "missing" in health.message.lower()

    @pytest.mark.asyncio
    async def test_file_system_health_healthy(self) -> None:
        """Test file system health when all directories exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()
            (claude_dir / "logs").mkdir()
            (claude_dir / "data").mkdir()

            with patch("pathlib.Path.home", return_value=mock_home):
                health = await check_file_system_health()
                assert health.name == "file_system"
                assert health.status == HealthStatus.HEALTHY
                assert "accessible" in health.message.lower()

    @pytest.mark.asyncio
    async def test_file_system_health_exception(self) -> None:
        """Test file system health when exception occurs."""
        with patch(
            "pathlib.Path.home", side_effect=RuntimeError("OS error")
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.05],
        ):
            health = await check_file_system_health()
            assert health.name == "file_system"
            assert health.status == HealthStatus.UNHEALTHY
            assert "error" in health.message.lower()


class TestCheckDependenciesHealth:
    """Test check_dependencies_health function."""

    @pytest.mark.asyncio
    async def test_dependencies_health_none_available(self) -> None:
        """Test when no optional dependencies are available.

        The exact ``message`` string is not asserted because the embedding
        provider check pings live HTTP endpoints (ollama/llama-server);
        on developer machines one of them may actually be running. The
        contract is: when no optional Python deps are importable, the
        status is DEGRADED and every Crackerjack/multi_project flag is
        in the ``unavailable`` metadata list.
        """
        with patch(
            "importlib.util.find_spec", return_value=None
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            health = await check_dependencies_health()
            assert health.name == "dependencies"
            assert health.status == HealthStatus.DEGRADED
            # All three importable-but-mocked deps must be marked unavailable.
            unavailable = health.metadata.get("unavailable", [])
            assert "crackerjack" in unavailable
            assert "multi_project" in unavailable

    @pytest.mark.asyncio
    async def test_dependencies_health_all_available(self) -> None:
        """Test when all optional dependencies are available."""
        mock_spec = MagicMock()

        async def fake_check_embedding_providers(client):
            return (["llama-server", "ollama"], [])

        with patch(
            "importlib.util.find_spec", return_value=mock_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}), patch(
            "session_buddy.health_checks._check_embedding_providers",
            side_effect=fake_check_embedding_providers,
        ):
            health = await check_dependencies_health()
            assert health.name == "dependencies"
            assert health.status == HealthStatus.HEALTHY
            assert "features available" in health.message.lower()

    @pytest.mark.asyncio
    async def test_dependencies_health_partial(self) -> None:
        """Test when some dependencies are available."""
        # Crackerjack available, ONNX not available
        def mock_find_spec(name: str) -> MagicMock | None:
            if name == "onnxruntime":
                return None
            return MagicMock()

        with patch(
            "importlib.util.find_spec", side_effect=mock_find_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            health = await check_dependencies_health()
            assert health.name == "dependencies"
            assert health.status == HealthStatus.DEGRADED
            assert "available" in health.message.lower()
            assert "unavailable" in health.message.lower()

    @pytest.mark.asyncio
    async def test_dependencies_health_crackerjack_check(self) -> None:
        """Test Crackerjack dependency checking."""
        with patch(
            "importlib.util.find_spec", return_value=MagicMock()
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            health = await check_dependencies_health()
            assert "crackerjack" in str(health.metadata)

    @pytest.mark.asyncio
    async def test_dependencies_health_uses_loaded_quality_utils_module(self) -> None:
        """Test dependency detection when the compatibility shim is already loaded."""
        fake_quality_utils = types.ModuleType("session_buddy.utils.quality_utils_v2")
        fake_quality_utils.CRACKERJACK_AVAILABLE = True

        async def fake_check_embedding_providers(client):
            return (["llama-server", "ollama"], [])

        with patch.dict(
            sys.modules,
            {"session_buddy.utils.quality_utils_v2": fake_quality_utils},
            clear=False,
        ), patch("importlib.util.find_spec", return_value=MagicMock()), patch(
            "session_buddy.health_checks._check_embedding_providers",
            side_effect=fake_check_embedding_providers,
        ):
            health = await check_dependencies_health()

            assert health.name == "dependencies"
            assert health.status == HealthStatus.HEALTHY
            assert "crackerjack" in health.metadata["available"]
            assert "multi_project" in health.metadata["available"]


class TestCheckPythonEnvironmentHealth:
    """Test check_python_environment_health function."""

    @pytest.mark.asyncio
    async def test_python_env_health_returns_component(self) -> None:
        """Test that Python environment check returns ComponentHealth."""
        health = await check_python_environment_health()
        assert health.name == "python_env"
        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert isinstance(health.message, str)
        assert health.message  # Non-empty message

    @pytest.mark.asyncio
    async def test_python_env_health_has_latency(self) -> None:
        """Test that Python environment check measures latency."""
        health = await check_python_environment_health()
        assert health.name == "python_env"
        assert health.latency_ms is not None
        assert health.latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_python_env_health_has_metadata(self) -> None:
        """Test that Python environment check includes metadata."""
        health = await check_python_environment_health()
        assert health.name == "python_env"
        if health.status == HealthStatus.HEALTHY:
            # When healthy, should have Python version in metadata
            assert "python_version" in health.metadata
            assert "platform" in health.metadata

    @pytest.mark.asyncio
    async def test_python_env_health_runs_without_error(self) -> None:
        """Test Python environment check runs and completes."""
        health = await check_python_environment_health()
        assert isinstance(health, ComponentHealth)

    @pytest.mark.asyncio
    async def test_python_env_health_rejects_old_version(self) -> None:
        """Test that Python versions below 3.13 are rejected."""

        class FakeVersionInfo:
            major = 3
            minor = 12
            micro = 4

            def __lt__(self, other: tuple[int, int]) -> bool:
                return (self.major, self.minor) < other

        with patch(
            "session_buddy.health_checks.sys.version_info",
            FakeVersionInfo(),
        ):
            health = await check_python_environment_health()

            assert health.name == "python_env"
            assert health.status == HealthStatus.UNHEALTHY
            assert "3.13+" in health.message

    @pytest.mark.asyncio
    async def test_python_env_health_reports_missing_import(self) -> None:
        """Test that missing critical imports are reported."""
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object):
            if name == "enum":
                raise ImportError("missing enum")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            health = await check_python_environment_health()

        assert health.name == "python_env"
        assert health.status == HealthStatus.UNHEALTHY
        assert "missing critical imports" in health.message.lower()
        assert "enum" in health.message


class TestGetInitializedReflectionDatabase:
    """Test get_initialized_reflection_database function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_unavailable(self) -> None:
        """Test that None is returned when reflection database is unavailable."""
        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", False
        ):
            result = await get_initialized_reflection_database()
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_database_when_available(self) -> None:
        """Test that database is returned when available."""
        mock_db = AsyncMock()
        with patch(
            "session_buddy.health_checks.REFLECTION_AVAILABLE", True
        ), patch(
            "session_buddy.health_checks.get_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ):
            result = await get_initialized_reflection_database()
            assert result == mock_db


class TestGetAllHealthChecks:
    """Test get_all_health_checks function."""

    @pytest.mark.asyncio
    async def test_returns_all_check_results(self) -> None:
        """Test that all health checks are executed."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ):
            results = await get_all_health_checks()
            assert len(results) == 4
            assert all(
                isinstance(r, ComponentHealth) for r in results
            )

    @pytest.mark.asyncio
    async def test_handles_exceptions_in_checks(self) -> None:
        """Test that exceptions in health checks are converted to unhealthy."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("File system error"),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ):
            results = await get_all_health_checks()
            assert len(results) == 4
            # Second one should be unhealthy due to exception
            assert results[1].status == HealthStatus.UNHEALTHY
            assert "crashed" in results[1].message.lower()

    @pytest.mark.asyncio
    async def test_concurrent_execution(self) -> None:
        """Test that all checks run concurrently."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies",
                status=HealthStatus.HEALTHY,
                message="OK",
            ),
        ):
            results = await get_all_health_checks()
            assert len(results) == 4
            # All should have results (not be exceptions)
            for result in results:
                if isinstance(result, ComponentHealth):
                    assert result.name in [
                        "python_env",
                        "file_system",
                        "database",
                        "dependencies",
                    ]
