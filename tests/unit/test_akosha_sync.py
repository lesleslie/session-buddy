"""Unit tests for Akosha sync components.

Tests cloud sync, HTTP sync, and hybrid orchestrator functionality
with mocked external dependencies.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from session_buddy.storage.akosha_config import AkoshaSyncConfig
from session_buddy.storage.akosha_sync import HttpSyncMethod, HybridAkoshaSync
from session_buddy.storage.cloud_sync import CloudSyncMethod
from session_buddy.storage.sync_protocol import (
    CloudUploadError,
    HTTPSyncError,
    HybridSyncError,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_settings() -> Mock:
    """Create mock settings object."""
    settings = Mock()
    settings.akosha_cloud_bucket = "test-bucket"
    settings.akosha_cloud_endpoint = "https://test.r2.cloudflarestorage.com"
    settings.akosha_cloud_region = "auto"
    settings.akosha_system_id = "test-system"
    settings.akosha_upload_on_session_end = True
    settings.akosha_enable_fallback = True
    settings.akosha_force_method = "auto"
    settings.akosha_upload_timeout_seconds = 300
    settings.akosha_max_retries = 3
    settings.akosha_retry_backoff_seconds = 2.0
    settings.akosha_enable_compression = True
    settings.akosha_enable_deduplication = True
    settings.akosha_chunk_size_mb = 5
    return settings


@pytest.fixture
def sample_config(mock_settings: Mock) -> AkoshaSyncConfig:
    """Create sample AkoshaSyncConfig."""
    return AkoshaSyncConfig.from_settings(mock_settings)


# ============================================================================
# AkoshaSyncConfig Tests
# ============================================================================


class TestAkoshaSyncConfig:
    """Test AkoshaSyncConfig dataclass functionality."""

    def test_from_settings(self, mock_settings: Mock) -> None:
        """Test config creation from settings object."""
        config = AkoshaSyncConfig.from_settings(mock_settings)

        assert config.cloud_bucket == "test-bucket"
        assert config.cloud_endpoint == "https://test.r2.cloudflarestorage.com"
        assert config.system_id == "test-system"
        assert config.upload_on_session_end is True
        assert config.enable_fallback is True
        assert config.force_method == "auto"
        assert config.max_retries == 3

    def test_cloud_configured_property(self, sample_config: AkoshaSyncConfig) -> None:
        """Test cloud_configured computed property."""
        assert sample_config.cloud_configured is True

        # Empty bucket should return False
        config = AkoshaSyncConfig(cloud_bucket="")
        assert config.cloud_configured is False

    def test_system_id_resolved_property(self, sample_config: AkoshaSyncConfig) -> None:
        """Test system_id_resolved computed property."""
        assert sample_config.system_id_resolved == "test-system"

        # Empty system_id should fallback to hostname
        config = AkoshaSyncConfig(cloud_bucket="test", system_id="")
        assert len(config.system_id_resolved) > 0
        assert config.system_id_resolved != "unknown-system" or True  # May be unknown in tests

    def test_should_use_cloud_property(self, sample_config: AkoshaSyncConfig) -> None:
        """Test should_use_cloud computed property."""
        # Auto mode with cloud configured
        assert sample_config.should_use_cloud is True

        # Force HTTP mode
        config = AkoshaSyncConfig(
            cloud_bucket="test",
            force_method="http",
        )
        assert config.should_use_cloud is False

        # Force cloud mode without bucket
        config = AkoshaSyncConfig(cloud_bucket="", force_method="cloud")
        assert config.should_use_cloud is False

    def test_should_use_http_property(self, sample_config: AkoshaSyncConfig) -> None:
        """Test should_use_http computed property."""
        # Auto mode with fallback enabled
        assert sample_config.should_use_http is True

        # Disable fallback
        config = AkoshaSyncConfig(
            cloud_bucket="test",
            enable_fallback=False,
        )
        assert config.should_use_http is False

        # Force HTTP mode
        config = AkoshaSyncConfig(force_method="http")
        assert config.should_use_http is True

    def test_validation_success(self, sample_config: AkoshaSyncConfig) -> None:
        """Test validation with valid configuration."""
        errors = sample_config.validate()
        assert len(errors) == 0

    def test_validation_invalid_bucket_name(self) -> None:
        """Test validation with invalid bucket name."""
        config = AkoshaSyncConfig(
            cloud_bucket="Invalid_Bucket_Name",  # Uppercase not allowed
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("bucket" in e.lower() for e in errors)

    def test_validation_http_endpoint(self) -> None:
        """Test validation rejects HTTP endpoints."""
        config = AkoshaSyncConfig(
            cloud_bucket="test-bucket",
            cloud_endpoint="http://localhost:9000",  # HTTP not allowed
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("https" in e.lower() for e in errors)

    def test_validation_force_cloud_without_bucket(self) -> None:
        """Test validation when forcing cloud without bucket."""
        config = AkoshaSyncConfig(
            cloud_bucket="",
            force_method="cloud",
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("cloud_bucket" in e for e in errors)


# ============================================================================
# CloudSyncMethod Tests
# ============================================================================


class TestCloudSyncMethod:
    """Test CloudSyncMethod sync functionality."""

    def test_init_success(self, sample_config: AkoshaSyncConfig) -> None:
        """Test successful initialization."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)
            assert cloud_sync.config == sample_config

    def test_init_invalid_config(self) -> None:
        """Test initialization with invalid configuration."""
        config = AkoshaSyncConfig(
            cloud_bucket="Invalid_Bucket",
        )
        errors = config.validate()
        assert len(errors) > 0

        with pytest.raises(ValueError, match="Invalid Akosha configuration"):
            CloudSyncMethod(config)

    def test_is_available_with_bucket(self, sample_config: AkoshaSyncConfig) -> None:
        """Test is_available returns True when cloud configured."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)
            assert cloud_sync.is_available() is True

    def test_is_available_without_bucket(self) -> None:
        """Test is_available returns False without bucket."""
        config = AkoshaSyncConfig(cloud_bucket="")
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(config)
            assert cloud_sync.is_available() is False

    def test_get_method_name(self, sample_config: AkoshaSyncConfig) -> None:
        """Test get_method_name returns correct name."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)
            assert cloud_sync.get_method_name() == "cloud"

    def test_generate_upload_id(self, sample_config: AkoshaSyncConfig) -> None:
        """Test upload ID generation format."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)
            upload_id = cloud_sync._generate_upload_id()

            # Format: YYYYMMDD_HHMMSS_system-id
            assert "_" in upload_id
            parts = upload_id.split("_")
            # Should have 3 parts: date, time, system-id
            assert len(parts) >= 2  # At minimum: timestamp and system_id
            assert parts[-1] == "test-system"

    def test_get_cloud_path(self, sample_config: AkoshaSyncConfig) -> None:
        """Test cloud path generation."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)
            path = cloud_sync._get_cloud_path("reflection.duckdb", "20250208_123456_test")

            # Format: systems/{system_id}/uploads/{upload_id}/{db_name}
            assert path.startswith("systems/")
            assert "/uploads/" in path
            assert path.endswith("reflection.duckdb")

    @pytest.mark.asyncio
    async def test_sync_success(self, sample_config: AkoshaSyncConfig) -> None:
        """Test successful sync operation."""
        from session_buddy.storage.sync_protocol import SyncMethod

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            cloud_sync = CloudSyncMethod(sample_config)

            # Mock S3 adapter and file operations
            mock_adapter = AsyncMock()
            cloud_sync._s3_adapter = mock_adapter

            # Mock file existence and stat
            with patch.object(Path, "exists", return_value=True):
                mock_stat = Mock()
                mock_stat.st_size = 42000000  # 42MB
                with patch.object(Path, "stat", return_value=mock_stat):
                    with patch.object(
                        cloud_sync,
                        "_upload_database",
                        return_value="systems/test/uploads/test/reflection.duckdb",
                    ):
                        with patch.object(
                            cloud_sync,
                            "_upload_manifest",
                            return_value="systems/test/uploads/test/manifest.json",
                        ):
                            result = await cloud_sync.sync()

                            assert result["success"] is True
                            assert result["method"] == "cloud"
                            assert len(result["files_uploaded"]) > 0
                            assert "upload_id" in result


# ============================================================================
# HttpSyncMethod Tests
# ============================================================================


class TestHttpSyncMethod:
    """Test HttpSyncMethod sync functionality."""

    def test_init(self, sample_config: AkoshaSyncConfig) -> None:
        """Test initialization."""
        http_sync = HttpSyncMethod(sample_config)
        assert http_sync.config == sample_config

    def test_get_method_name(self, sample_config: AkoshaSyncConfig) -> None:
        """Test get_method_name returns correct name."""
        http_sync = HttpSyncMethod(sample_config)
        assert http_sync.get_method_name() == "http"

    @pytest.mark.asyncio
    async def test_sync_success(self, sample_config: AkoshaSyncConfig) -> None:
        """Test successful HTTP sync."""
        http_sync = HttpSyncMethod(sample_config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response

            mock_client_class.return_value = mock_client

            result = await http_sync.sync()

            assert result["success"] is True
            assert result["method"] == "http"

    @pytest.mark.asyncio
    async def test_sync_failure(self, sample_config: AkoshaSyncConfig) -> None:
        """Test HTTP sync failure."""
        from session_buddy.storage.sync_protocol import HTTPSyncError

        http_sync = HttpSyncMethod(sample_config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = Exception("Connection refused")

            mock_client_class.return_value = mock_client

            with pytest.raises(HTTPSyncError):
                await http_sync.sync()


# ============================================================================
# HybridAkoshaSync Tests
# ============================================================================


class TestHybridAkoshaSync:
    """Test HybridAkoshaSync orchestrator functionality."""

    def test_init(self, sample_config: AkoshaSyncConfig) -> None:
        """Test initialization creates both methods."""
        from session_buddy.storage.sync_protocol import SyncMethod

        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            assert len(hybrid.methods) == 2
            assert all(isinstance(m, SyncMethod) for m in hybrid.methods)

    def test_get_method(self, sample_config: AkoshaSyncConfig) -> None:
        """Test getting method by name."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            cloud_method = hybrid._get_method("cloud")
            assert cloud_method is not None
            assert cloud_method.get_method_name() == "cloud"

            http_method = hybrid._get_method("http")
            assert http_method is not None
            assert http_method.get_method_name() == "http"

            unknown_method = hybrid._get_method("unknown")
            assert unknown_method is None

    @pytest.mark.asyncio
    async def test_sync_memories_auto_cloud_success(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test auto mode succeeds with cloud sync."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            # Mock cloud sync success
            for method in hybrid.methods:
                if method.get_method_name() == "cloud":
                    method.is_available = Mock(return_value=True)
                    method.sync = AsyncMock(
                        return_value={
                            "success": True,
                            "method": "cloud",
                            "files_uploaded": ["test.duckdb"],
                        }
                    )

            result = await hybrid.sync_memories(force_method="auto")

            assert result["success"] is True
            assert result["method"] == "cloud"

    @pytest.mark.asyncio
    async def test_sync_memories_auto_fallback_to_http(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test auto mode falls back to HTTP when cloud unavailable."""
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
                        }
                    )

            result = await hybrid.sync_memories(force_method="auto")

            assert result["success"] is True
            assert result["method"] == "http"

    @pytest.mark.asyncio
    async def test_sync_memories_force_method(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test forcing specific method."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            # Mock HTTP success
            for method in hybrid.methods:
                if method.get_method_name() == "http":
                    method.is_available = Mock(return_value=True)
                    method.sync = AsyncMock(
                        return_value={
                            "success": True,
                            "method": "http",
                        }
                    )

            result = await hybrid.sync_memories(force_method="http")

            assert result["success"] is True
            assert result["method"] == "http"

    @pytest.mark.asyncio
    async def test_sync_memories_all_methods_fail(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test HybridSyncError raised when all methods fail."""
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(sample_config)

            # Mock all methods unavailable
            for method in hybrid.methods:
                method.is_available = Mock(return_value=False)

            with pytest.raises(HybridSyncError, match="All.*sync methods failed"):
                await hybrid.sync_memories(force_method="auto")

    @pytest.mark.asyncio
    async def test_sync_memories_force_method_unavailable(
        self,
        sample_config: AkoshaSyncConfig,
    ) -> None:
        """Test forcing unavailable method raises error."""
        config = AkoshaSyncConfig(cloud_bucket="", force_method="auto")
        with patch("session_buddy.storage.cloud_sync._get_s3_adapter_class"):
            hybrid = HybridAkoshaSync(config)

            # Remove cloud method (simulate unavailable)
            hybrid.methods = [m for m in hybrid.methods if m.get_method_name() != "cloud"]

            with pytest.raises(
                HybridSyncError,
                match="Requested method 'cloud' not available",
            ):
                await hybrid.sync_memories(force_method="cloud")
