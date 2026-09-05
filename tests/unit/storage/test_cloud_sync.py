"""Tests for session_buddy.storage.cloud_sync.

Covers ``CloudSyncMethod``:
- ``__init__`` validation (valid config, missing system_id)
- ``is_available`` (no bucket, with bucket, with bucket but no oneiric)
- ``get_method_name`` ("cloud")
- ``_generate_upload_id`` format
- ``_get_cloud_path`` formatting
- ``_read_database`` (raw vs gzip)
- ``_compute_sha256`` matches hashlib directly
- ``_file_exists_with_checksum`` returns False (placeholder)
- ``_upload_to_s3`` async + sync fallback path
- ``_upload_with_retry`` success / retry exhaustion
- ``_upload_database`` dedup-skip path + upload path
- ``_upload_manifest`` builds correct JSON
- ``sync`` happy path / no DBs / missing oneiric / CloudUploadError

The S3 adapter is injected as ``self._s3_adapter`` so no real cloud
connection is made. ``Path.home()`` is monkeypatched to redirect DB
paths to tmp_path. The async sleep between retries is patched out.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.storage import cloud_sync
from session_buddy.storage.akosha_config import AkoshaSyncConfig
from session_buddy.storage.cloud_sync import CloudSyncMethod
from session_buddy.storage.sync_protocol import CloudUploadError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> AkoshaSyncConfig:
    """Build a config that passes validation."""
    base = dict(
        cloud_bucket="my-bucket",
        cloud_endpoint="https://s3.example.com",
        cloud_region="us-east-1",
        system_id="test-system",
        upload_timeout_seconds=10,
        max_retries=3,
        retry_backoff_seconds=0.1,
        enable_compression=True,
        enable_deduplication=True,
    )
    base.update(overrides)
    return AkoshaSyncConfig(**base)


@pytest.fixture
def cloud_sync_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> CloudSyncMethod:
    """Build a CloudSyncMethod with DB paths redirected to tmp_path."""
    monkeypatch.setattr(cloud_sync.Path, "home", lambda: tmp_path)
    instance = CloudSyncMethod(_make_config())
    instance.reflection_db_path = tmp_path / "reflection.duckdb"
    instance.knowledge_graph_db_path = tmp_path / "knowledge_graph.duckdb"
    return instance


def _make_s3_adapter() -> MagicMock:
    """Build a mock S3 adapter with an async upload method."""
    adapter = MagicMock()
    adapter.upload = AsyncMock()
    return adapter


def _seed_db(path: Path, content: bytes = b"hello duckdb") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_valid_config_succeeds(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(cloud_sync.Path, "home", lambda: tmp_path)
        instance = CloudSyncMethod(_make_config())
        assert instance._s3_adapter is None
        assert instance.config.cloud_bucket == "my-bucket"

    def test_invalid_config_raises_value_error(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(cloud_sync.Path, "home", lambda: tmp_path)
        # system_id required when cloud_bucket is set; pass empty bucket
        # to keep validation focused. Invalid endpoint URL forces failure.
        bad_config = AkoshaSyncConfig(
            cloud_bucket="my-bucket",
            cloud_endpoint="not a url",
            system_id="x",
        )
        with pytest.raises(ValueError, match="Invalid Akosha configuration"):
            CloudSyncMethod(bad_config)


# ---------------------------------------------------------------------------
# is_available / get_method_name
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_false_when_cloud_not_configured(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(cloud_sync.Path, "home", lambda: tmp_path)
        config = AkoshaSyncConfig(cloud_bucket="", system_id="x")
        instance = CloudSyncMethod(config)
        assert instance.is_available() is False

    def test_true_when_bucket_configured_and_oneiric_available(
        self, cloud_sync_instance, monkeypatch
    ) -> None:
        # _get_s3_adapter_class returns successfully (default test env).
        assert cloud_sync_instance.is_available() is True

    def test_false_when_oneiric_import_fails(
        self, cloud_sync_instance, monkeypatch
    ) -> None:
        # Force _get_s3_adapter_class to raise ImportError.
        def boom():
            raise ImportError("oneiric missing")

        monkeypatch.setattr(cloud_sync, "_get_s3_adapter_class", boom)
        assert cloud_sync_instance.is_available() is False


class TestGetMethodName:
    def test_returns_cloud(self, cloud_sync_instance: CloudSyncMethod) -> None:
        assert cloud_sync_instance.get_method_name() == "cloud"


# ---------------------------------------------------------------------------
# Pure-Python helpers
# ---------------------------------------------------------------------------


class TestGenerateUploadId:
    def test_format_matches_pattern(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        upload_id = cloud_sync_instance._generate_upload_id()
        # YYYYMMDD_HHMMSS_system-id
        parts = upload_id.split("_", 2)
        assert len(parts) == 3
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[1]) == 6  # HHMMSS
        assert parts[2] == "test-system"


class TestGetCloudPath:
    def test_format(self, cloud_sync_instance: CloudSyncMethod) -> None:
        path = cloud_sync_instance._get_cloud_path("reflection.duckdb", "upl_1")
        assert path == "systems/test-system/uploads/upl_1/reflection.duckdb"


class TestFileExistsWithChecksum:
    @pytest.mark.asyncio
    async def test_returns_false_placeholder(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        # Current implementation is a TODO stub that returns False.
        # It's declared async but returns immediately — callers must
        # await it.
        result = await cloud_sync_instance._file_exists_with_checksum(
            "any/path", "abc123"
        )
        assert result is False


# ---------------------------------------------------------------------------
# _read_database
# ---------------------------------------------------------------------------


class TestReadDatabase:
    @pytest.mark.asyncio
    async def test_returns_raw_bytes_when_compression_disabled(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(cloud_sync.Path, "home", lambda: tmp_path)
        config = _make_config(enable_compression=False)
        instance = CloudSyncMethod(config)
        instance.reflection_db_path = tmp_path / "reflection.duckdb"
        instance.knowledge_graph_db_path = tmp_path / "knowledge_graph.duckdb"
        _seed_db(instance.reflection_db_path, b"raw content")

        result = await instance._read_database(instance.reflection_db_path)
        assert result == b"raw content"

    @pytest.mark.asyncio
    async def test_returns_compressed_bytes_when_compression_enabled(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        _seed_db(cloud_sync_instance.reflection_db_path, b"raw content")
        result = await cloud_sync_instance._read_database(
            cloud_sync_instance.reflection_db_path
        )
        # gzip magic bytes (0x1f, 0x8b) confirm compression.
        assert result[:2] == b"\x1f\x8b"
        # Decompresses back to original.
        assert gzip.decompress(result) == b"raw content"


# ---------------------------------------------------------------------------
# _compute_sha256
# ---------------------------------------------------------------------------


class TestComputeSha256:
    @pytest.mark.asyncio
    async def test_matches_hashlib_directly(
        self, cloud_sync_instance: CloudSyncMethod, tmp_path: Path
    ) -> None:
        target = tmp_path / "sample.bin"
        target.write_bytes(b"checksum test data")

        result = await cloud_sync_instance._compute_sha256(target)

        expected = hashlib.sha256(b"checksum test data").hexdigest()
        assert result == expected

    @pytest.mark.asyncio
    async def test_handles_large_file_in_chunks(
        self, cloud_sync_instance: CloudSyncMethod, tmp_path: Path
    ) -> None:
        target = tmp_path / "large.bin"
        # Write 20KB to exercise multiple chunks (chunk size = 8192).
        target.write_bytes(b"x" * 20_000)

        result = await cloud_sync_instance._compute_sha256(target)

        expected = hashlib.sha256(b"x" * 20_000).hexdigest()
        assert result == expected


# ---------------------------------------------------------------------------
# _upload_to_s3
# ---------------------------------------------------------------------------


class TestUploadToS3:
    @pytest.mark.asyncio
    async def test_calls_adapter_upload(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter
        await cloud_sync_instance._upload_to_s3("path/to/file", b"data")
        adapter.upload.assert_awaited_once_with(path="path/to/file", data=b"data")

    @pytest.mark.asyncio
    async def test_raises_when_adapter_uninitialized(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        cloud_sync_instance._s3_adapter = None
        with pytest.raises(RuntimeError, match="S3 adapter not initialized"):
            await cloud_sync_instance._upload_to_s3("path", b"data")

    @pytest.mark.asyncio
    async def test_propagates_adapter_error(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        adapter = _make_s3_adapter()
        adapter.upload.side_effect = RuntimeError("S3 unavailable")
        cloud_sync_instance._s3_adapter = adapter
        with pytest.raises(RuntimeError, match="S3 unavailable"):
            await cloud_sync_instance._upload_to_s3("path", b"data")


# ---------------------------------------------------------------------------
# _upload_with_retry
# ---------------------------------------------------------------------------


class TestUploadWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_attempt(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        result = await cloud_sync_instance._upload_with_retry(
            data=b"data", db_name="x.duckdb", upload_id="upl_1"
        )
        assert result == "systems/test-system/uploads/upl_1/x.duckdb"
        adapter.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_until_success(
        self, cloud_sync_instance: CloudSyncMethod, monkeypatch
    ) -> None:
        # Patch sleep to skip backoff.
        async def fast_sleep(seconds):
            return None

        monkeypatch.setattr(cloud_sync.asyncio, "sleep", fast_sleep)

        adapter = _make_s3_adapter()
        # Fail twice, succeed on third attempt.
        adapter.upload.side_effect = [
            RuntimeError("transient 1"),
            RuntimeError("transient 2"),
            None,
        ]
        cloud_sync_instance._s3_adapter = adapter

        result = await cloud_sync_instance._upload_with_retry(
            data=b"data", db_name="x.duckdb", upload_id="upl_1"
        )
        assert result == "systems/test-system/uploads/upl_1/x.duckdb"
        assert adapter.upload.await_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_all_retries(
        self, cloud_sync_instance: CloudSyncMethod, monkeypatch
    ) -> None:
        async def fast_sleep(seconds):
            return None

        monkeypatch.setattr(cloud_sync.asyncio, "sleep", fast_sleep)

        adapter = _make_s3_adapter()
        adapter.upload.side_effect = RuntimeError("permanent failure")
        cloud_sync_instance._s3_adapter = adapter

        with pytest.raises(CloudUploadError) as exc_info:
            await cloud_sync_instance._upload_with_retry(
                data=b"data", db_name="x.duckdb", upload_id="upl_1"
            )
        assert "Upload failed after 3 attempts" in str(exc_info.value)
        # All retries were attempted.
        assert adapter.upload.await_count == 3


# ---------------------------------------------------------------------------
# _upload_database
# ---------------------------------------------------------------------------


class TestUploadDatabase:
    @pytest.mark.asyncio
    async def test_uploads_when_no_existing(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        _seed_db(cloud_sync_instance.reflection_db_path)
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        result = await cloud_sync_instance._upload_database(
            db_path=cloud_sync_instance.reflection_db_path,
            db_name=cloud_sync_instance.REFLECTION_DB_NAME,
            upload_id="upl_1",
        )
        # Cloud path is returned.
        assert "reflection.duckdb" in result
        adapter.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_upload_when_dedup_matches(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        _seed_db(cloud_sync_instance.reflection_db_path)
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        # Force _file_exists_with_checksum to return True.
        async def always_exists(*args, **kwargs):
            return True

        cloud_sync_instance._file_exists_with_checksum = always_exists  # type: ignore[method-assign]

        result = await cloud_sync_instance._upload_database(
            db_path=cloud_sync_instance.reflection_db_path,
            db_name=cloud_sync_instance.REFLECTION_DB_NAME,
            upload_id="upl_1",
        )
        assert "reflection.duckdb" in result
        # Adapter was NOT called — dedup short-circuited the upload.
        adapter.upload.assert_not_awaited()


# ---------------------------------------------------------------------------
# _upload_manifest
# ---------------------------------------------------------------------------


class TestUploadManifest:
    @pytest.mark.asyncio
    async def test_uploads_manifest_json(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        # Capture the data passed to upload so we can decode the JSON.
        captured_data: dict[str, bytes] = {}

        async def capture(path, data):
            captured_data["path"] = path
            captured_data["data"] = data

        adapter.upload.side_effect = capture

        result = await cloud_sync_instance._upload_manifest(
            upload_id="upl_1",
            files_uploaded=[
                "systems/test-system/uploads/upl_1/reflection.duckdb",
                "systems/test-system/uploads/upl_1/knowledge_graph.duckdb",
            ],
        )

        # Manifest cloud path.
        assert result == "systems/test-system/uploads/upl_1/manifest.json"

        # Decode and validate the JSON.
        manifest = json.loads(captured_data["data"].decode("utf-8"))
        assert manifest["upload_id"] == "upl_1"
        assert manifest["system_id"] == "test-system"
        assert "timestamp" in manifest
        assert len(manifest["files"]) == 2
        assert manifest["files"][0]["name"] == "reflection.duckdb"
        assert manifest["files"][1]["name"] == "knowledge_graph.duckdb"
        assert manifest["metadata"]["uploader"] == "session-buddy"

    @pytest.mark.asyncio
    async def test_compression_flag_reflects_config(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        # Test with compression disabled.
        cloud_sync_instance.config = _make_config(enable_compression=False)
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        captured: dict[str, bytes] = {}

        async def capture(path, data):
            captured["data"] = data

        adapter.upload.side_effect = capture

        await cloud_sync_instance._upload_manifest(
            upload_id="upl_1",
            files_uploaded=["systems/test-system/uploads/upl_1/x.duckdb"],
        )
        manifest = json.loads(captured["data"].decode("utf-8"))
        assert manifest["files"][0]["compression"] == "none"


# ---------------------------------------------------------------------------
# sync (public)
# ---------------------------------------------------------------------------


class TestSync:
    @pytest.mark.asyncio
    async def test_no_dbs_returns_empty_files(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        # No DBs on disk → no uploads.
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        result = await cloud_sync_instance.sync(
            upload_reflections=True, upload_knowledge_graph=True
        )
        assert result["method"] == "cloud"
        assert result["success"] is True
        assert result["files_uploaded"] == []
        assert result["bytes_transferred"] == 0
        assert result["upload_id"]  # non-empty
        adapter.upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uploads_both_dbs(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        _seed_db(cloud_sync_instance.reflection_db_path, b"reflection content")
        _seed_db(
            cloud_sync_instance.knowledge_graph_db_path, b"kg content"
        )
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        result = await cloud_sync_instance.sync()
        assert result["success"] is True
        # 2 DBs + 1 manifest = 3 uploads.
        assert len(result["files_uploaded"]) == 3
        assert adapter.upload.await_count == 3
        # Bytes is sum of local file sizes (pre-compression).
        assert result["bytes_transferred"] == len(b"reflection content") + len(b"kg content")

    @pytest.mark.asyncio
    async def test_only_reflections(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        _seed_db(cloud_sync_instance.reflection_db_path)
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        result = await cloud_sync_instance.sync(
            upload_reflections=True, upload_knowledge_graph=False
        )
        # 1 DB + 1 manifest = 2 uploads.
        assert len(result["files_uploaded"]) == 2
        assert any("reflection.duckdb" in f for f in result["files_uploaded"])

    @pytest.mark.asyncio
    async def test_only_knowledge_graph(
        self, cloud_sync_instance: CloudSyncMethod
    ) -> None:
        _seed_db(cloud_sync_instance.knowledge_graph_db_path)
        adapter = _make_s3_adapter()
        cloud_sync_instance._s3_adapter = adapter

        result = await cloud_sync_instance.sync(
            upload_reflections=False, upload_knowledge_graph=True
        )
        assert len(result["files_uploaded"]) == 2
        assert any("knowledge_graph.duckdb" in f for f in result["files_uploaded"])

    @pytest.mark.asyncio
    async def test_lazy_creates_adapter(
        self, cloud_sync_instance: CloudSyncMethod, monkeypatch
    ) -> None:
        # Patch _create_s3_adapter to verify it's called lazily.
        create_called = {"n": 0}

        async def fake_create(self):
            create_called["n"] += 1
            return _make_s3_adapter()

        monkeypatch.setattr(CloudSyncMethod, "_create_s3_adapter", fake_create)
        # _s3_adapter is initially None.
        assert cloud_sync_instance._s3_adapter is None
        await cloud_sync_instance.sync()
        assert create_called["n"] == 1
        # Second sync call should NOT recreate (lazy: only once).
        await cloud_sync_instance.sync()
        assert create_called["n"] == 1

    @pytest.mark.asyncio
    async def test_raises_clouduploaderror_on_failure(
        self, cloud_sync_instance: CloudSyncMethod, monkeypatch
    ) -> None:
        _seed_db(cloud_sync_instance.reflection_db_path)
        cloud_sync_instance._s3_adapter = _make_s3_adapter()

        async def fast_sleep(seconds):
            return None

        monkeypatch.setattr(cloud_sync.asyncio, "sleep", fast_sleep)

        # All retries fail.
        cloud_sync_instance._s3_adapter.upload.side_effect = RuntimeError(
            "bucket unreachable"
        )
        with pytest.raises(CloudUploadError, match="Cloud upload failed"):
            await cloud_sync_instance.sync()

    @pytest.mark.asyncio
    async def test_raises_when_oneiric_adapter_init_fails(
        self, cloud_sync_instance: CloudSyncMethod, monkeypatch
    ) -> None:
        # Force _create_s3_adapter to raise.
        async def boom_create(self):
            raise RuntimeError("adapter init failed")

        monkeypatch.setattr(CloudSyncMethod, "_create_s3_adapter", boom_create)
        with pytest.raises(CloudUploadError, match="Cloud upload failed"):
            await cloud_sync_instance.sync()
