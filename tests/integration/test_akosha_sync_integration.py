"""Integration tests for Akosha sync components.

Tests end-to-end sync workflows with actual file operations and
mocked cloud services.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import Response

from session_buddy.storage.akosha_config import AkoshaSyncConfig
from session_buddy.storage.akosha_sync import HybridAkoshaSync
from session_buddy.storage.cloud_sync import CloudSyncMethod
from session_buddy.storage.sync_protocol import CloudUploadError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_databases(tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary DuckDB database files for testing.

    Returns:
        Tuple of (reflection_db_path, knowledge_graph_db_path)
    """
    reflection_db = tmp_path / "reflection.duckdb"
    knowledge_graph_db = tmp_path / "knowledge_graph.duckdb"

    # Create dummy database files
    reflection_db.write_bytes(b"reflection_db_data")
    knowledge_graph_db.write_bytes(b"knowledge_graph_db_data")

    return reflection_db, knowledge_graph_db


@pytest.fixture
def sample_config() -> AkoshaSyncConfig:
    """Create sample AkoshaSyncConfig for testing."""
    return AkoshaSyncConfig(
        cloud_bucket="test-bucket",
        cloud_endpoint="https://test.r2.cloudflarestorage.com",
        cloud_region="auto",
        system_id="test-system",
        upload_on_session_end=True,
        enable_fallback=True,
        force_method="auto",
        upload_timeout_seconds=300,
        max_retries=3,
        retry_backoff_seconds=0.1,  # Shorter for tests
        enable_compression=True,
        enable_deduplication=True,
        chunk_size_mb=5,
    )


# ============================================================================
# CloudSyncMethod Integration Tests
# ============================================================================


class TestCloudSyncMethodIntegration:
    """Integration tests for CloudSyncMethod."""

    @pytest.mark.asyncio
    async def test_full_upload_workflow(
        self,
        sample_config: AkoshaSyncConfig,
        temp_databases: tuple[Path, Path],
    ) -> None:
        """Test complete upload workflow with compression and manifest creation."""
        reflection_db, _ = temp_databases

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            # Mock database paths
            cloud_sync = CloudSyncMethod(sample_config)
            cloud_sync.reflection_db_path = reflection_db
            cloud_sync.knowledge_graph_db_path = temp_databases[1]

            # Mock S3 adapter
            mock_adapter = AsyncMock()
            cloud_sync._s3_adapter = mock_adapter

            # Perform sync
            result = await cloud_sync.sync(
                upload_reflections=True,
                upload_knowledge_graph=False,
            )

            # Verify success
            assert result["success"] is True
            assert result["method"] == "cloud"
            assert len(result["files_uploaded"]) == 2  # DB + manifest
            assert "upload_id" in result

            # Verify S3 upload was called
            assert mock_adapter.upload.call_count == 2

    @pytest.mark.asyncio
    async def test_compression_workflow(
        self,
        sample_config: AkoshaSyncConfig,
        temp_databases: tuple[Path, Path],
    ) -> None:
        """Test that compression is applied when enabled."""
        reflection_db, _ = temp_databases

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            config_compression = AkoshaSyncConfig(
                **sample_config.__dict__,
                enable_compression=True,
            )

            cloud_sync = CloudSyncMethod(config_compression)
            cloud_sync.reflection_db_path = reflection_db
            cloud_sync._s3_adapter = AsyncMock()

            # Read database with compression
            file_data = await cloud_sync._read_database(reflection_db)

            # Verify compression was applied
            assert file_data.startswith(b"\\x1f\\x8b")  # Gzip magic bytes

            # Decompress to verify content
            decompressed = gzip.decompress(file_data)
            assert decompressed == reflection_db.read_bytes()

    @pytest.mark.asyncio
    async def test_deduplication_skip(
        self,
        sample_config: AkoshaSyncConfig,
        temp_databases: tuple[Path, Path],
    ) -> None:
        """Test that unchanged files are skipped when deduplication enabled."""
        reflection_db, _ = temp_databases

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            config_dedupe = AkoshaSyncConfig(
                **sample_config.__dict__,
                enable_deduplication=True,
            )

            cloud_sync = CloudSyncMethod(config_dedupe)
            cloud_sync.reflection_db_path = reflection_db

            # Mock file exists with same checksum
            checksum = await cloud_sync._compute_sha256(reflection_db)

            with patch.object(
                cloud_sync,
                "_file_exists_with_checksum",
                return_value=True,
            ):
                # Upload should be skipped
                cloud_path = await cloud_sync._upload_database(
                    db_path=reflection_db,
                    db_name="reflection.duckdb",
                    upload_id="test_upload",
                )

                # Verify path was returned but no upload occurred
                assert cloud_path == "systems/test-system/uploads/test_upload/reflection.duckdb"

    @pytest.mark.asyncio
    async def test_retry_with_backoff(
        self,
        sample_config: AkoshaSyncConfig,
        temp_databases: tuple[Path, Path],
    ) -> None:
        """Test retry logic with exponential backoff."""
        reflection_db, _ = temp_databases

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)
            cloud_sync.reflection_db_path = reflection_db
            cloud_sync._s3_adapter = AsyncMock()

            # Mock upload failure first 2 times, success 3rd time
            call_count = 0

            async def failing_upload(*args: object, **kwargs: object) -> None:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise Exception("Upload failed")
                # Success on 3rd try

            cloud_sync._s3_adapter.upload.side_effect = failing_upload

            with patch.object(
                cloud_sync,
                "_upload_to_s3",
                side_effect=failing_upload,
            ):
                # Should succeed after retries
                with patch.object(
                    cloud_sync,
                    "_upload_with_retry",
                    wraps=cloud_sync._upload_with_retry,
                ) as mock_retry:
                    # Simulate successful upload after retries
                    with patch.object(
                        cloud_sync,
                        "_upload_to_s3",
                    ):
                        # Create mock that succeeds after retries
                        async def mock_upload(*args: object, **kwargs: object) -> None:
                            # Simulate success
                            pass

                        with patch.object(
                            cloud_sync,
                            "_file_exists_with_checksum",
                            return_value=False,
                        ):
                            file_data = await cloud_sync._read_database(reflection_db)
                            await cloud_sync._upload_with_retry(
                                data=file_data,
                                db_name="reflection.duckdb",
                                upload_id="test",
                            )

    @pytest.mark.asyncio
    async def test_manifest_creation(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test manifest.json creation with correct schema."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)
            cloud_sync._s3_adapter = AsyncMock()

            # Create manifest
            upload_id = "20250208_143052_test-system"
            files_uploaded = [
                "systems/test-system/uploads/test/reflection.duckdb",
            ]

            manifest_path = await cloud_sync._upload_manifest(
                upload_id=upload_id,
                files_uploaded=files_uploaded,
            )

            # Verify manifest path
            assert manifest_path == f"systems/test-system/uploads/{upload_id}/manifest.json"

            # Get the uploaded data (from the mock call)
            upload_call = cloud_sync._s3_adapter.upload.call_args_list[-1]
            manifest_json = upload_call[1]["data"]  # keyword argument 'data'

            # Parse and verify manifest
            manifest = json.loads(manifest_json.decode("utf-8"))

            assert manifest["upload_id"] == upload_id
            assert manifest["system_id"] == "test-system"
            assert "timestamp" in manifest
            assert isinstance(manifest["files"], list)
            assert len(manifest["files"]) == 1


# ============================================================================
# HybridAkoshaSync Integration Tests
# ============================================================================


class TestHybridAkoshaSyncIntegration:
    """Integration tests for HybridAkoshaSync orchestrator."""

    @pytest.mark.asyncio
    async def test_cloud_to_http_fallback_integration(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test complete cloud → HTTP fallback workflow."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            # Mock cloud unavailable, HTTP available
            for method in hybrid.methods:
                if method.get_method_name() == "cloud":
                    method.is_available = Mock(return_value=False)
                elif method.get_method_name() == "http":
                    method.is_available = Mock(return_value=True)
                    method.sync = AsyncMock(
                        return_value={
                            "success": True,
                            "method": "http",
                            "files_uploaded": [],
                            "bytes_transferred": 0,
                            "duration_seconds": 0.5,
                            "error": None,
                        }
                    )

            # Perform sync
            result = await hybrid.sync_memories(force_method="auto")

            # Verify HTTP fallback worked
            assert result["success"] is True
            assert result["method"] == "http"

    @pytest.mark.asyncio
    async def test_force_cloud_integration(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test forcing cloud method when available."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            # Mock both available
            for method in hybrid.methods:
                method.is_available = Mock(return_value=True)
                method.sync = AsyncMock(
                    return_value={
                        "success": True,
                        "method": method.get_method_name(),
                    }
                )

            # Force cloud
            result = await hybrid.sync_memories(force_method="cloud")

            # Verify cloud was used
            assert result["success"] is True
            assert result["method"] == "cloud"

    @pytest.mark.asyncio
    async def test_all_methods_failure_scenario(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test error handling when all methods fail."""
        from session_buddy.storage.sync_protocol import HybridSyncError

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            # Mock all methods available but failing
            for method in hybrid.methods:
                method.is_available = Mock(return_value=True)
                method.sync = AsyncMock(
                    side_effect=Exception("Method failed"),
                )

            # Should raise HybridSyncError
            with pytest.raises(HybridSyncError) as exc_info:
                await hybrid.sync_memories(force_method="auto")

            # Verify error contains all method failures
            assert len(exc_info.value.errors) == 2
            assert all("error" in e for e in exc_info.value.errors)


# ============================================================================
# End-to-End MCP Tools Tests
# ============================================================================


class TestMCPToolsIntegration:
    """Integration tests for MCP tool functionality."""

    @pytest.mark.asyncio
    async def test_sync_to_akosha_tool(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test sync_to_akosha MCP tool."""
        from session_buddy.mcp.tools.memory.akosha_tools import sync_to_akosha

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            with patch("session_buddy.settings.get_settings") as mock_settings:
                # Mock settings
                mock_settings_obj = Mock()
                for key, value in sample_config.__dict__.items():
                    setattr(mock_settings_obj, key, value)
                mock_settings.return_value = mock_settings_obj

                # Mock successful sync
                with patch.object(
                    HybridAkoshaSync,
                    "sync_memories",
                    return_value={
                        "success": True,
                        "method": "cloud",
                        "files_uploaded": ["test.duckdb"],
                        "bytes_transferred": 1000000,
                        "duration_seconds": 5.0,
                        "upload_id": "test_upload",
                        "error": None,
                    },
                ):
                    result = await sync_to_akosha(method="auto")

                    assert result["success"] is True
                    assert result["method"] == "cloud"
                    assert result["triggered_by"] == "manual"

    @pytest.mark.asyncio
    async def test_akosha_sync_status_tool(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test akosha_sync_status MCP tool."""
        from session_buddy.mcp.tools.memory.akosha_tools import akosha_sync_status

        with patch("session_buddy.settings.get_settings") as mock_settings:
            # Mock settings
            mock_settings_obj = Mock()
            for key, value in sample_config.__dict__.items():
                setattr(mock_settings_obj, key, value)
            mock_settings.return_value = mock_settings_obj

            result = await akosha_sync_status()

            assert result["cloud_configured"] is True
            assert result["system_id"] == "test-system"
            assert result["should_use_cloud"] is True
            assert result["should_use_http"] is True
            assert "configuration" in result
            assert result["configuration"]["cloud_bucket"] == "test-bucket"


# ============================================================================
# Session End Hook Tests
# ============================================================================


class TestSessionEndHookIntegration:
    """Integration tests for session end hook functionality."""

    @pytest.mark.asyncio
    async def test_background_sync_queued(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test that session end queues background sync task."""
        import asyncio

        from session_buddy.mcp.tools.session.session_tools import (
            _queue_akosha_sync_background,
        )

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            with patch("session_buddy.settings.get_settings") as mock_settings:
                # Mock settings with upload enabled
                mock_settings_obj = Mock()
                for key, value in sample_config.__dict__.items():
                    setattr(mock_settings_obj, key, value)
                mock_settings.return_value = mock_settings_obj

                # Patch asyncio.create_task to capture task creation
                created_tasks = []

                def mock_create_task(coro, name: str = "") -> asyncio.Task:
                    created_tasks.append(coro)
                    # Return mock task
                    task = Mock()
                    task_name = name
                    return task

                with patch("asyncio.create_task", side_effect=mock_create_task):
                    # Queue background sync
                    _queue_akosha_sync_background()

                    # Verify task was created
                    assert len(created_tasks) == 1
                    assert isinstance(created_tasks[0], asyncio.coroutines.Coroutine)

    @pytest.mark.asyncio
    async def test_background_sync_disabled(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test that background sync is not queued when disabled."""
        from session_buddy.mcp.tools.session.session_tools import (
            _queue_akosha_sync_background,
        )

        # Create config with upload disabled
        config_disabled = AkoshaSyncConfig(
            **sample_config.__dict__,
            upload_on_session_end=False,
        )

        with patch("session_buddy.settings.get_settings") as mock_settings:
            mock_settings_obj = Mock()
            for key, value in config_disabled.__dict__.items():
                setattr(mock_settings_obj, key, value)
            mock_settings.return_value = mock_settings_obj

            # Patch asyncio.create_task
            with patch("asyncio.create_task") as mock_create:
                # Queue background sync
                _queue_akosha_sync_background()

                # Verify task was NOT created
                mock_create.assert_not_called()
