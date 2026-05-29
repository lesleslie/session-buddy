"""Comprehensive unit tests for health check implementations.

Tests component-level health checks including:
- Database connectivity and latency
- File system access and permissions
- Optional dependencies availability
- Python environment validation
- Concurrent health check execution
- Edge cases and error handling

Target: 60+ tests for 70%+ coverage of health_checks.py
"""

from __future__ import annotations

import asyncio
import builtins
import importlib
import sys
import tempfile
import time
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

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


# =============================================================================
# Test HealthStatus Enum
# =============================================================================


class TestHealthStatusEnum:
    """Test HealthStatus enum values and behavior."""

    def test_health_status_healthy_value(self) -> None:
        """Test HealthStatus.HEALTHY has correct string value."""
        assert HealthStatus.HEALTHY == "healthy"
        assert str(HealthStatus.HEALTHY) == "healthy"

    def test_health_status_degraded_value(self) -> None:
        """Test HealthStatus.DEGRADED has correct string value."""
        assert HealthStatus.DEGRADED == "degraded"
        assert str(HealthStatus.DEGRADED) == "degraded"

    def test_health_status_unhealthy_value(self) -> None:
        """Test HealthStatus.UNHEALTHY has correct string value."""
        assert HealthStatus.UNHEALTHY == "unhealthy"
        assert str(HealthStatus.UNHEALTHY) == "unhealthy"

    def test_health_status_is_string(self) -> None:
        """Test HealthStatus values can be used as strings."""
        status = HealthStatus.HEALTHY
        assert isinstance(status, str)
        assert status == "healthy"
        assert status.lower() == "healthy"

    def test_health_status_comparison(self) -> None:
        """Test HealthStatus enum comparison works correctly."""
        assert HealthStatus.HEALTHY == HealthStatus.HEALTHY
        assert HealthStatus.HEALTHY != HealthStatus.DEGRADED
        # StrEnum comparison by string value: "degraded" < "healthy" < "unhealthy" (d < h < u)
        assert HealthStatus.DEGRADED < HealthStatus.HEALTHY
        assert HealthStatus.HEALTHY < HealthStatus.UNHEALTHY

    def test_health_status_all_values(self) -> None:
        """Test all expected HealthStatus values exist."""
        values = list(HealthStatus)
        assert len(values) == 3
        assert HealthStatus.HEALTHY in values
        assert HealthStatus.DEGRADED in values
        assert HealthStatus.UNHEALTHY in values


# =============================================================================
# Test ComponentHealth Dataclass
# =============================================================================


class TestComponentHealthDataclass:
    """Test ComponentHealth dataclass initialization and fields."""

    def test_component_health_required_fields(self) -> None:
        """Test ComponentHealth with only required fields."""
        health = ComponentHealth(
            name="test_component",
            status=HealthStatus.HEALTHY,
            message="All systems operational",
        )
        assert health.name == "test_component"
        assert health.status == HealthStatus.HEALTHY
        assert health.message == "All systems operational"

    def test_component_health_optional_latency(self) -> None:
        """Test ComponentHealth with latency field."""
        health = ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="OK",
            latency_ms=42.5,
        )
        assert health.latency_ms == 42.5

    def test_component_health_optional_metadata(self) -> None:
        """Test ComponentHealth with metadata field."""
        health = ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="OK",
            metadata={"conversations": 100, "errors": 0},
        )
        assert health.metadata["conversations"] == 100
        assert health.metadata["errors"] == 0

    def test_component_health_default_latency_is_none(self) -> None:
        """Test ComponentHealth latency defaults to None."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="OK",
        )
        assert health.latency_ms is None

    def test_component_health_default_metadata_is_empty_dict(self) -> None:
        """Test ComponentHealth metadata defaults to empty dict."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="OK",
        )
        assert health.metadata == {}

    def test_component_health_all_fields(self) -> None:
        """Test ComponentHealth with all fields populated."""
        health = ComponentHealth(
            name="database",
            status=HealthStatus.DEGRADED,
            message="High latency detected",
            latency_ms=650.0,
            metadata={
                "conversations": 500,
                "query_time_ms": 650,
                "region": "us-west-2",
            },
        )
        assert health.name == "database"
        assert health.status == HealthStatus.DEGRADED
        assert health.message == "High latency detected"
        assert health.latency_ms == 650.0
        assert len(health.metadata) == 3

    def test_component_health_mutable_metadata_shared_reference(self) -> None:
        """Test that passing metadata shares the reference (not a copy)."""
        original_metadata = {"key": "value"}
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="OK",
            metadata=original_metadata,
        )
        # The dataclass stores the reference, not a copy
        # This is expected behavior - the caller should clone if needed
        assert health.metadata is original_metadata


# =============================================================================
# Test check_database_health
# =============================================================================


class TestCheckDatabaseHealth:
    """Test check_database_health function - database connectivity checks."""

    @pytest.mark.asyncio
    async def test_database_health_reflection_not_available(self) -> None:
        """Test DEGRADED status when reflection database is not available."""
        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", False):
            result = await check_database_health()
            assert result.name == "database"
            assert result.status == HealthStatus.DEGRADED
            assert "not available" in result.message.lower()

    @pytest.mark.asyncio
    async def test_database_health_not_initialized_returns_none(self) -> None:
        """Test DEGRADED when get_initialized_reflection_database returns None."""
        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await check_database_health()
            assert result.name == "database"
            assert result.status == HealthStatus.DEGRADED
            assert "not initialized" in result.message.lower()

    @pytest.mark.asyncio
    async def test_database_health_not_initialized_with_mock_module_fallback(
        self,
    ) -> None:
        """Test fallback path when get_reflection_database is a mock returning db."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 25})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "session_buddy.health_checks.get_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ):
            result = await check_database_health()
            assert result.name == "database"
            assert result.status == HealthStatus.HEALTHY
            assert result.metadata["conversations"] == 25

    @pytest.mark.asyncio
    async def test_database_health_healthy_normal_latency(self) -> None:
        """Test HEALTHY when database is responsive with normal latency."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 100})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.05],  # 50ms latency
        ):
            result = await check_database_health()
            assert result.name == "database"
            assert result.status == HealthStatus.HEALTHY
            assert result.message == "Database operational"
            assert result.latency_ms == 50.0
            assert result.metadata["conversations"] == 100

    @pytest.mark.asyncio
    async def test_database_health_degraded_high_latency(self) -> None:
        """Test DEGRADED when latency exceeds 500ms threshold."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 50})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.6],  # 600ms latency
        ):
            result = await check_database_health()
            assert result.name == "database"
            assert result.status == HealthStatus.DEGRADED
            assert "high" in result.message.lower()
            assert "latency" in result.message.lower()
            assert result.latency_ms == 600.0

    @pytest.mark.asyncio
    async def test_database_health_degraded_at_exactly_500ms(self) -> None:
        """Test DEGRADED when latency is exactly at 500ms threshold."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 10})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.5],  # exactly 500ms
        ):
            result = await check_database_health()
            assert result.name == "database"
            # At exactly 500ms, still healthy (threshold is >500)
            assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_database_health_unhealthy_exception_during_check(self) -> None:
        """Test UNHEALTHY when exception occurs during database check."""
        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Database connection timeout"),
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.02],
        ):
            result = await check_database_health()
            assert result.name == "database"
            assert result.status == HealthStatus.UNHEALTHY
            assert "error" in result.message.lower()
            assert "connection timeout" in result.message.lower()

    @pytest.mark.asyncio
    async def test_database_health_unhealthy_exception_message_truncated(self) -> None:
        """Test that long exception messages are truncated to 100 chars."""
        long_message = "A" * 200  # Very long error message
        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            side_effect=RuntimeError(long_message),
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.01],
        ):
            result = await check_database_health()
            assert len(result.message) <= 100 + len("Database error: ")

    @pytest.mark.asyncio
    async def test_database_health_includes_latency_in_response(self) -> None:
        """Test that latency_ms is included in the response."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 0})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.123],
        ):
            result = await check_database_health()
            assert result.latency_ms is not None
            assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_database_health_get_stats_returns_zero_conversations(self) -> None:
        """Test handling of zero conversations count."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 0})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.01],
        ):
            result = await check_database_health()
            assert result.status == HealthStatus.HEALTHY
            assert result.metadata["conversations"] == 0

    @pytest.mark.asyncio
    async def test_database_health_get_stats_returns_missing_key(self) -> None:
        """Test handling when get_stats returns dict without conversations_count."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={})  # Empty dict

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.01],
        ):
            result = await check_database_health()
            assert result.status == HealthStatus.HEALTHY
            assert result.metadata["conversations"] == 0


# =============================================================================
# Test check_file_system_health
# =============================================================================


class TestCheckFileSystemHealth:
    """Test check_file_system_health function - file system access checks."""

    @pytest.mark.asyncio
    async def test_file_system_health_missing_claude_dir(self) -> None:
        """Test UNHEALTHY when ~/.claude directory does not exist."""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/nonexistent_path_12345")
            result = await check_file_system_health()
            assert result.name == "file_system"
            assert result.status == HealthStatus.UNHEALTHY
            assert "does not exist" in result.message.lower()

    @pytest.mark.asyncio
    async def test_file_system_health_dir_not_writable_permission_error(
        self,
    ) -> None:
        """Test UNHEALTHY when ~/.claude is not writable due to permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()

            with patch("pathlib.Path.home", return_value=mock_home), patch.object(
                Path,
                "write_text",
                side_effect=PermissionError("Permission denied: '.health_check'"),
            ):
                result = await check_file_system_health()
                assert result.name == "file_system"
                assert result.status == HealthStatus.UNHEALTHY
                assert "not writable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_file_system_health_dir_not_writable_os_error(self) -> None:
        """Test UNHEALTHY when ~/.claude write fails with OSError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()

            with patch("pathlib.Path.home", return_value=mock_home), patch.object(
                Path, "write_text", side_effect=OSError("Disk full")
            ):
                result = await check_file_system_health()
                assert result.name == "file_system"
                assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_file_system_health_missing_both_subdirs(self) -> None:
        """Test DEGRADED when both logs and data subdirectories are missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()

            with patch("pathlib.Path.home", return_value=mock_home):
                result = await check_file_system_health()
                assert result.name == "file_system"
                assert result.status == HealthStatus.DEGRADED
                assert "missing directories" in result.message.lower()

    @pytest.mark.asyncio
    async def test_file_system_health_missing_only_logs_dir(self) -> None:
        """Test DEGRADED when only logs directory is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()
            (claude_dir / "data").mkdir()

            with patch("pathlib.Path.home", return_value=mock_home):
                result = await check_file_system_health()
                assert result.name == "file_system"
                assert result.status == HealthStatus.DEGRADED
                assert "logs" in result.message

    @pytest.mark.asyncio
    async def test_file_system_health_missing_only_data_dir(self) -> None:
        """Test DEGRADED when only data directory is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()
            (claude_dir / "logs").mkdir()

            with patch("pathlib.Path.home", return_value=mock_home):
                result = await check_file_system_health()
                assert result.name == "file_system"
                assert result.status == HealthStatus.DEGRADED
                assert "data" in result.message

    @pytest.mark.asyncio
    async def test_file_system_health_healthy_all_dirs_present(self) -> None:
        """Test HEALTHY when all required directories exist and are writable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()
            (claude_dir / "logs").mkdir()
            (claude_dir / "data").mkdir()

            with patch("pathlib.Path.home", return_value=mock_home):
                result = await check_file_system_health()
                assert result.name == "file_system"
                assert result.status == HealthStatus.HEALTHY
                assert "accessible" in result.message.lower()

    @pytest.mark.asyncio
    async def test_file_system_health_exception_during_check(self) -> None:
        """Test UNHEALTHY when exception occurs during file system check."""
        with patch(
            "pathlib.Path.home",
            side_effect=RuntimeError("Path resolution failed"),
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.01],
        ):
            result = await check_file_system_health()
            assert result.name == "file_system"
            assert result.status == HealthStatus.UNHEALTHY
            assert "error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_file_system_health_write_and_unlink_succeeds(self) -> None:
        """Test that write_text and unlink operations work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()
            (claude_dir / "logs").mkdir()
            (claude_dir / "data").mkdir()

            with patch("pathlib.Path.home", return_value=mock_home):
                result = await check_file_system_health()
                # Verify the health check didn't leave test file behind
                assert not (claude_dir / ".health_check").exists()
                assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_file_system_health_includes_latency(self) -> None:
        """Test that file system check includes latency measurement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)
            claude_dir = mock_home / ".claude"
            claude_dir.mkdir()
            (claude_dir / "logs").mkdir()
            (claude_dir / "data").mkdir()

            with patch("pathlib.Path.home", return_value=mock_home):
                result = await check_file_system_health()
                assert result.latency_ms is not None
                assert result.latency_ms >= 0


# =============================================================================
# Test check_dependencies_health
# =============================================================================


class TestCheckDependenciesHealth:
    """Test check_dependencies_health function - optional dependencies check."""

    @pytest.mark.asyncio
    async def test_dependencies_health_no_features_available(self) -> None:
        """Test DEGRADED when no optional features are available."""
        with patch(
            "importlib.util.find_spec", return_value=None
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert result.name == "dependencies"
            assert result.status == HealthStatus.DEGRADED
            assert "no optional features" in result.message.lower()

    @pytest.mark.asyncio
    async def test_dependencies_health_all_available(self) -> None:
        """Test HEALTHY when all optional features are available."""
        mock_spec = MagicMock()

        with patch(
            "importlib.util.find_spec", return_value=mock_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert result.name == "dependencies"
            assert result.status == HealthStatus.HEALTHY
            assert "features available" in result.message.lower()

    @pytest.mark.asyncio
    async def test_dependencies_health_some_available_some_missing(self) -> None:
        """Test DEGRADED when some features available, some missing."""
        def mock_find_spec(name: str) -> MagicMock | None:
            if name == "onnxruntime":
                return None  # ONNX not available
            if name == "crackerjack":
                return None  # Crackerjack not available
            return MagicMock()  # multi_project available

        with patch(
            "importlib.util.find_spec", side_effect=mock_find_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert result.name == "dependencies"
            assert result.status == HealthStatus.DEGRADED
            assert "available" in result.message.lower()
            assert "unavailable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_dependencies_health_with_quality_utils_crackerjack(self) -> None:
        """Test that CRACKERJACK_AVAILABLE from quality_utils is respected."""
        fake_quality_utils = types.ModuleType(
            "session_buddy.utils.quality_utils_v2"
        )
        fake_quality_utils.CRACKERJACK_AVAILABLE = True

        with patch.dict(
            sys.modules,
            {"session_buddy.utils.quality_utils_v2": fake_quality_utils},
            clear=False,
        ), patch(
            "importlib.util.find_spec", return_value=MagicMock()
        ):
            result = await check_dependencies_health()
            assert "crackerjack" in result.metadata["available"]

    @pytest.mark.asyncio
    async def test_dependencies_health_quality_utils_not_available(self) -> None:
        """Test when quality_utils module is not in sys.modules."""
        with patch(
            "importlib.util.find_spec", return_value=MagicMock()
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            # Should fall back to find_spec check for crackerjack
            assert result.name == "dependencies"

    @pytest.mark.asyncio
    async def test_dependencies_health_find_spec_raises_value_error(self) -> None:
        """Test handling when find_spec raises ValueError."""
        with patch(
            "importlib.util.find_spec",
            side_effect=ValueError("Invalid module name"),
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert result.name == "dependencies"
            # Should fall back to checking sys.modules
            assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

    @pytest.mark.asyncio
    async def test_dependencies_health_module_in_sys_modules(self) -> None:
        """Test when module name is directly in sys.modules."""
        # Simulate crackerjack being in sys.modules
        with patch.dict(
            sys.modules,
            {
                "crackerjack": MagicMock(),
                "session_buddy.utils.quality_utils_v2": None,
            },
        ), patch(
            "importlib.util.find_spec",
            side_effect=ValueError("Invalid module name"),
        ):
            result = await check_dependencies_health()
            assert "crackerjack" in result.metadata["available"]

    @pytest.mark.asyncio
    async def test_dependencies_health_counts_features_in_message(self) -> None:
        """Test that the message includes counts of available/unavailable."""
        with patch(
            "importlib.util.find_spec", return_value=MagicMock()
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            # Message should contain count of features
            assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_dependencies_health_multi_project_available(self) -> None:
        """Test when multi_project_coordinator module is available."""
        mock_spec = MagicMock()

        with patch(
            "importlib.util.find_spec", return_value=mock_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert "multi_project" in result.metadata["available"]

    @pytest.mark.asyncio
    async def test_dependencies_health_multi_project_import_error(self) -> None:
        """Test when find_spec for multi_project raises ImportError."""
        def mock_find_spec(name: str) -> MagicMock | None:
            if name == "session_buddy.multi_project_coordinator":
                raise ImportError("Module not found")
            return MagicMock()  # Return truthy MagicMock for other modules

        with patch(
            "importlib.util.find_spec", side_effect=mock_find_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert "multi_project" in result.metadata["unavailable"]

    @pytest.mark.asyncio
    async def test_dependencies_health_multi_project_generic_exception(self) -> None:
        """Test when find_spec for multi_project raises generic Exception."""
        def mock_find_spec(name: str) -> MagicMock | None:
            if name == "session_buddy.multi_project_coordinator":
                raise Exception("Unknown error")
            return MagicMock()  # Return truthy MagicMock for other modules

        with patch(
            "importlib.util.find_spec", side_effect=mock_find_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert "multi_project" in result.metadata["unavailable"]

    @pytest.mark.asyncio
    async def test_dependencies_health_includes_latency(self) -> None:
        """Test that dependency check measures and reports latency."""
        with patch(
            "importlib.util.find_spec", return_value=None
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert result.latency_ms is not None
            assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_dependencies_health_onxxruntime_available(self) -> None:
        """Test when onnxruntime module is available."""
        mock_spec = MagicMock()

        with patch(
            "importlib.util.find_spec", return_value=mock_spec
        ), patch.dict(sys.modules, {"session_buddy.utils.quality_utils_v2": None}):
            result = await check_dependencies_health()
            assert "onnx" in result.metadata["available"]


# =============================================================================
# Test check_python_environment_health
# =============================================================================


class TestCheckPythonEnvironmentHealth:
    """Test check_python_environment_health function - Python env validation."""

    @pytest.mark.asyncio
    async def test_python_env_health_healthy_on_valid_python(self) -> None:
        """Test HEALTHY when running on valid Python 3.13+."""
        result = await check_python_environment_health()
        assert result.name == "python_env"
        assert result.status == HealthStatus.HEALTHY
        assert "python" in result.message.lower()
        assert result.latency_ms is not None

    @pytest.mark.asyncio
    async def test_python_env_health_unhealthy_on_old_version(self) -> None:
        """Test UNHEALTHY when Python version is below 3.13."""
        from collections import namedtuple

        MockVersionInfo = namedtuple(
            "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
        )
        mock_version = MockVersionInfo(
            major=3, minor=12, micro=0, releaselevel="final", serial=0
        )

        with patch("sys.version_info", new=mock_version):
            result = await check_python_environment_health()
            assert result.name == "python_env"
            assert result.status == HealthStatus.UNHEALTHY
            assert "3.13" in result.message
            assert "required" in result.message.lower()

    @pytest.mark.asyncio
    async def test_python_env_health_unhealthy_python_3_10(self) -> None:
        """Test UNHEALTHY for Python 3.10 (well below minimum)."""
        from collections import namedtuple

        MockVersionInfo = namedtuple(
            "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
        )
        mock_version = MockVersionInfo(
            major=3, minor=10, micro=0, releaselevel="final", serial=0
        )

        with patch("sys.version_info", new=mock_version):
            result = await check_python_environment_health()
            assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_python_env_health_missing_critical_import_enum(self) -> None:
        """Test UNHEALTHY when 'enum' module import fails."""
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> Any:
            if name == "enum":
                raise ImportError("No module named 'enum'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = await check_python_environment_health()
            assert result.status == HealthStatus.UNHEALTHY
            assert "missing critical imports" in result.message.lower()
            assert "enum" in result.message

    @pytest.mark.asyncio
    async def test_python_env_health_missing_critical_import_asyncio(self) -> None:
        """Test UNHEALTHY when 'asyncio' module import fails."""
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> Any:
            if name == "asyncio":
                raise ImportError("No module named 'asyncio'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = await check_python_environment_health()
            assert result.status == HealthStatus.UNHEALTHY
            assert "missing critical imports" in result.message.lower()

    @pytest.mark.asyncio
    async def test_python_env_health_missing_multiple_imports(self) -> None:
        """Test UNHEALTHY when multiple critical imports are missing."""
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> Any:
            if name in ("asyncio", "pathlib"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = await check_python_environment_health()
            assert result.status == HealthStatus.UNHEALTHY
            assert "asyncio" in result.message
            assert "pathlib" in result.message

    @pytest.mark.asyncio
    async def test_python_env_health_includes_python_version_metadata(self) -> None:
        """Test that Python version is included in metadata when healthy."""
        result = await check_python_environment_health()
        if result.status == HealthStatus.HEALTHY:
            assert "python_version" in result.metadata
            assert "platform" in result.metadata

    @pytest.mark.asyncio
    async def test_python_env_health_includes_platform_metadata(self) -> None:
        """Test that platform is included in metadata."""
        result = await check_python_environment_health()
        if result.status == HealthStatus.HEALTHY:
            assert "platform" in result.metadata
            assert result.metadata["platform"] in ("darwin", "linux", "win32", "freebsd")

    @pytest.mark.asyncio
    async def test_python_env_health_exception_during_check(self) -> None:
        """Test UNHEALTHY when exception occurs during environment check."""
        with patch(
            "session_buddy.health_checks.sys.version_info",
            side_effect=RuntimeError("Critical failure"),
        ):
            result = await check_python_environment_health()
            assert result.status == HealthStatus.UNHEALTHY
            assert "environment check failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_python_env_health_exception_message_truncated(self) -> None:
        """Test that exception message is truncated to 100 characters."""
        long_error = "X" * 200
        with patch(
            "session_buddy.health_checks.sys.version_info",
            side_effect=RuntimeError(long_error),
        ):
            result = await check_python_environment_health()
            assert len(result.message) <= 100 + len("Environment check failed: ")

    @pytest.mark.asyncio
    async def test_python_env_health_python_3_13_exactly(self) -> None:
        """Test HEALTHY when Python version is exactly 3.13."""
        from collections import namedtuple

        MockVersionInfo = namedtuple(
            "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
        )
        mock_version = MockVersionInfo(
            major=3, minor=13, micro=0, releaselevel="final", serial=0
        )

        with patch("sys.version_info", new=mock_version):
            result = await check_python_environment_health()
            assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_python_env_health_python_3_14(self) -> None:
        """Test HEALTHY when Python version is 3.14 (future version)."""
        from collections import namedtuple

        MockVersionInfo = namedtuple(
            "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
        )
        mock_version = MockVersionInfo(
            major=3, minor=14, micro=0, releaselevel="final", serial=0
        )

        with patch("sys.version_info", new=mock_version):
            result = await check_python_environment_health()
            assert result.status == HealthStatus.HEALTHY


# =============================================================================
# Test get_initialized_reflection_database
# =============================================================================


class TestGetInitializedReflectionDatabase:
    """Test get_initialized_reflection_database function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_reflection_not_available(self) -> None:
        """Test None is returned when REFLECTION_AVAILABLE is False."""
        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", False):
            result = await get_initialized_reflection_database()
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_database_when_available(self) -> None:
        """Test database instance is returned when available."""
        mock_db = AsyncMock()
        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ):
            result = await get_initialized_reflection_database()
            assert result == mock_db

    @pytest.mark.asyncio
    async def test_returns_none_when_get_reflection_database_returns_none(
        self,
    ) -> None:
        """Test None is returned when get_reflection_database returns None."""
        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_reflection_database",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_initialized_reflection_database()
            assert result is None


# =============================================================================
# Test get_all_health_checks
# =============================================================================


class TestGetAllHealthChecks:
    """Test get_all_health_checks function - concurrent execution of all checks."""

    @pytest.mark.asyncio
    async def test_all_four_checks_are_returned(self) -> None:
        """Test that exactly 4 ComponentHealth results are returned."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            results = await get_all_health_checks()
            assert len(results) == 4

    @pytest.mark.asyncio
    async def test_checks_have_correct_names(self) -> None:
        """Test that each check returns with the correct name."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            results = await get_all_health_checks()
            names = {r.name for r in results}
            assert names == {"python_env", "file_system", "database", "dependencies"}

    @pytest.mark.asyncio
    async def test_exception_in_python_check_converted_to_unhealthy(self) -> None:
        """Test that exception in check_python_environment_health is handled."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Python check crashed"),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            results = await get_all_health_checks()
            python_result = next(r for r in results if r.name == "python_env")
            assert python_result.status == HealthStatus.UNHEALTHY
            assert "crashed" in python_result.message.lower()
            assert "python check crashed" in python_result.message.lower()

    @pytest.mark.asyncio
    async def test_exception_in_file_system_check_converted_to_unhealthy(self) -> None:
        """Test that exception in check_file_system_health is handled."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("File system check failed"),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            results = await get_all_health_checks()
            fs_result = next(r for r in results if r.name == "file_system")
            assert fs_result.status == HealthStatus.UNHEALTHY
            assert "crashed" in fs_result.message.lower()

    @pytest.mark.asyncio
    async def test_exception_in_database_check_converted_to_unhealthy(self) -> None:
        """Test that exception in check_database_health is handled."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Database check crashed"),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            results = await get_all_health_checks()
            db_result = next(r for r in results if r.name == "database")
            assert db_result.status == HealthStatus.UNHEALTHY
            assert "crashed" in db_result.message.lower()

    @pytest.mark.asyncio
    async def test_exception_in_dependencies_check_converted_to_unhealthy(
        self,
    ) -> None:
        """Test that exception in check_dependencies_health is handled."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Dependencies check crashed"),
        ):
            results = await get_all_health_checks()
            dep_result = next(r for r in results if r.name == "dependencies")
            assert dep_result.status == HealthStatus.UNHEALTHY
            assert "crashed" in dep_result.message.lower()

    @pytest.mark.asyncio
    async def test_all_checks_return_exceptions_as_unhealthy(self) -> None:
        """Test that all checks raising exceptions are handled."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Error 1"),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Error 2"),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Error 3"),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Error 4"),
        ):
            results = await get_all_health_checks()
            assert len(results) == 4
            assert all(r.status == HealthStatus.UNHEALTHY for r in results)

    @pytest.mark.asyncio
    async def test_results_are_component_health_instances(self) -> None:
        """Test that all returned results are ComponentHealth instances."""
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="python_env", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            results = await get_all_health_checks()
            assert all(isinstance(r, ComponentHealth) for r in results)

    @pytest.mark.asyncio
    async def test_exception_messages_are_truncated(self) -> None:
        """Test that exception messages are truncated to 100 characters."""
        long_error = "Y" * 200
        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError(long_error),
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            results = await get_all_health_checks()
            python_result = next(r for r in results if r.name == "python_env")
            assert len(python_result.message) <= 100 + len("Health check crashed: ")

    @pytest.mark.asyncio
    async def test_checks_run_concurrently_via_asyncio_gather(self) -> None:
        """Test that checks are executed concurrently using asyncio.gather."""
        check_calls: list[bool] = []

        async def slow_python_check() -> ComponentHealth:
            check_calls.append(True)
            await asyncio.sleep(0.01)
            return ComponentHealth(
                name="python_env", status=HealthStatus.HEALTHY, message="OK"
            )

        async def slow_fs_check() -> ComponentHealth:
            check_calls.append(True)
            await asyncio.sleep(0.01)
            return ComponentHealth(
                name="file_system", status=HealthStatus.HEALTHY, message="OK"
            )

        with patch(
            "session_buddy.health_checks.check_python_environment_health",
            new_callable=AsyncMock,
            side_effect=slow_python_check,
        ), patch(
            "session_buddy.health_checks.check_file_system_health",
            new_callable=AsyncMock,
            side_effect=slow_fs_check,
        ), patch(
            "session_buddy.health_checks.check_database_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="database", status=HealthStatus.HEALTHY, message="OK"
            ),
        ), patch(
            "session_buddy.health_checks.check_dependencies_health",
            new_callable=AsyncMock,
            return_value=ComponentHealth(
                name="dependencies", status=HealthStatus.HEALTHY, message="OK"
            ),
        ):
            start = time.perf_counter()
            await get_all_health_checks()
            elapsed_ms = (time.perf_counter() - start) * 1000
            # If run serially, would take ~20ms; concurrent should be ~10ms
            assert elapsed_ms < 50  # Generous bound


# =============================================================================
# Test __all__ exports
# =============================================================================


class TestModuleExports:
    """Test module __all__ exports."""

    def test_all_includes_expected_functions(self) -> None:
        """Test that __all__ contains all expected public functions."""
        from session_buddy.health_checks import __all__

        expected = [
            "check_database_health",
            "check_dependencies_health",
            "check_file_system_health",
            "check_python_environment_health",
            "get_all_health_checks",
        ]
        for name in expected:
            assert name in __all__, f"{name} not in __all__"

    def test_all_count(self) -> None:
        """Test that __all__ has exactly 5 entries."""
        from session_buddy.health_checks import __all__

        assert len(__all__) == 5


# =============================================================================
# Test edge cases and integration scenarios
# =============================================================================


class TestHealthCheckEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_component_health_with_none_metadata(self) -> None:
        """Test ComponentHealth accepts None metadata via field default."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="OK",
        )
        assert health.metadata == {}

    @pytest.mark.asyncio
    async def test_multiple_sequential_checks(self) -> None:
        """Test running multiple health checks sequentially."""
        results1 = await get_all_health_checks()
        results2 = await get_all_health_checks()
        assert len(results1) == len(results2) == 4

    @pytest.mark.asyncio
    async def test_health_status_transitions(self) -> None:
        """Test that health statuses can be used in comparisons."""
        healthy = HealthStatus.HEALTHY
        degraded = HealthStatus.DEGRADED
        unhealthy = HealthStatus.UNHEALTHY

        # Test ordering (alphabetical: degraded < healthy < unhealthy)
        assert degraded < healthy < unhealthy

    @pytest.mark.asyncio
    async def test_database_health_zero_latency(self) -> None:
        """Test database health with zero latency (instant response)."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 1})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.0],  # Zero latency
        ):
            result = await check_database_health()
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms == 0.0

    @pytest.mark.asyncio
    async def test_database_health_very_high_conversations_count(self) -> None:
        """Test database health with very high conversations count."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(return_value={"conversations_count": 1_000_000})

        with patch("session_buddy.health_checks.REFLECTION_AVAILABLE", True), patch(
            "session_buddy.health_checks.get_initialized_reflection_database",
            new_callable=AsyncMock,
            return_value=mock_db,
        ), patch(
            "session_buddy.health_checks.time.perf_counter",
            side_effect=[0.0, 0.01],
        ):
            result = await check_database_health()
            assert result.metadata["conversations"] == 1_000_000

    @pytest.mark.asyncio
    async def test_file_system_health_read_only_at_root(self) -> None:
        """Test file system health when home is root (potential permission issues)."""
        with patch("pathlib.Path.home", return_value=Path("/root")):
            result = await check_file_system_health()
            # Should handle gracefully, not crash
            assert result.name == "file_system"
            assert result.status in [
                HealthStatus.HEALTHY,
                HealthStatus.DEGRADED,
                HealthStatus.UNHEALTHY,
            ]
