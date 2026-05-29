from __future__ import annotations

import gzip
import sys
import types
from datetime import UTC, datetime, timedelta

import pytest

from session_buddy.backends.base import SessionState


def _state(session_id: str = "session-1") -> SessionState:
    now = datetime.now(UTC).isoformat()
    return SessionState(
        session_id=session_id,
        user_id="user-1",
        project_id="project-1",
        created_at=now,
        last_activity=now,
    )


class _FakeAsyncRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.set_calls: list[tuple[str, bytes, int | None]] = []
        self.expire_calls: list[tuple[str, int]] = []
        self.sadd_calls: list[tuple[str, str]] = []
        self.srem_calls: list[tuple[str, str]] = []
        self.session_keys_value: list[bytes | str] = []
        self.index_keys_value: list[bytes | str] = []
        self.smembers_value: dict[str, set[bytes | str]] = {}
        self.exists_value: dict[str, int] = {}
        self.ping_called = False

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.values[key] = value
        self.set_calls.append((key, value, ex))

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def sadd(self, key: str, value: str) -> None:
        self.sadd_calls.append((key, value))

    async def srem(self, key: str, value: str | bytes) -> None:
        self.srem_calls.append((key, value.decode("utf-8") if isinstance(value, bytes) else value))

    async def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))

    async def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0

    async def smembers(self, key: str) -> set[bytes | str]:
        return self.smembers_value.get(key, set())

    async def keys(self, pattern: str) -> list[bytes | str]:
        if ":index:" in pattern:
            return self.index_keys_value
        return self.session_keys_value

    async def exists(self, key: str) -> int:
        return self.exists_value.get(key, 0)

    async def ping(self) -> bool:
        self.ping_called = True
        return True


class _FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []
        self.get_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []
        self.list_calls: list[tuple[str, str]] = []
        self.head_calls: list[tuple[str, str]] = []
        self.head_bucket_calls: list[str] = []
        self.objects: list[dict[str, object]] = []
        self.metadata: dict[str, dict[str, str]] = {}
        self.body_by_key: dict[str, bytes] = {}

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)
        self.body_by_key[str(kwargs["Key"])] = kwargs["Body"]  # type: ignore[assignment]

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self.get_calls.append((Bucket, Key))
        return {"Body": types.SimpleNamespace(read=lambda: self.body_by_key[Key])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.delete_calls.append((Bucket, Key))

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict[str, object]:
        self.list_calls.append((Bucket, Prefix))
        return {"Contents": self.objects}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self.head_calls.append((Bucket, Key))
        return {"Metadata": self.metadata.get(Key, {})}

    def head_bucket(self, *, Bucket: str) -> None:
        self.head_bucket_calls.append(Bucket)


@pytest.mark.asyncio
async def test_redis_storage_happy_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis_client = _FakeAsyncRedis()
    fake_redis_package = types.ModuleType("redis")
    fake_asyncio_module = types.ModuleType("redis.asyncio")
    fake_asyncio_module.Redis = lambda **kwargs: fake_redis_client  # type: ignore[attr-defined]
    fake_redis_package.asyncio = fake_asyncio_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake_redis_package)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio_module)

    from session_buddy.backends.redis_backend import RedisStorage

    storage = RedisStorage({"key_prefix": "sb:"})
    state = _state("redis-session")

    assert storage._get_key(state.session_id) == "sb:session:redis-session"
    assert storage._get_index_key("user:user-1") == "sb:index:user:user-1"

    assert await storage.is_available() is True

    assert await storage.store_session(state, ttl_seconds=60) is True
    assert fake_redis_client.set_calls[0][0] == "sb:session:redis-session"
    assert fake_redis_client.expire_calls == [
        ("sb:index:user:user-1", 60),
        ("sb:index:project:project-1", 60),
    ]

    retrieved = await storage.retrieve_session(state.session_id)
    assert retrieved == state

    fake_redis_client.smembers_value = {
        "sb:index:user:user-1": {b"redis-session", "other-session"},
        "sb:index:project:project-1": {b"redis-session"},
    }
    fake_redis_client.session_keys_value = [
        b"sb:session:redis-session",
        "sb:session:other",
    ]
    fake_redis_client.index_keys_value = [
        b"sb:index:user:user-1",
        "sb:index:project:project-1",
    ]
    fake_redis_client.exists_value = {
        "sb:session:redis-session": 1,
        "sb:session:other-session": 0,
    }

    assert set(await storage.list_sessions(user_id="user-1")) == {
        "redis-session",
        "other-session",
    }
    assert set(await storage.list_sessions(project_id="project-1")) == {
        "redis-session",
    }
    assert set(await storage.list_sessions()) == {"redis-session", "other"}

    assert await storage._is_orphaned_session(fake_redis_client, b"other-session") is True
    assert await storage._cleanup_index_key(
        fake_redis_client,
        "sb:index:user:user-1",
    ) == 1
    assert await storage._get_index_keys(fake_redis_client) == [
        "sb:index:user:user-1",
        "sb:index:project:project-1",
    ]

    deleted = await storage.delete_session(state.session_id)
    assert deleted is True
    assert await storage.cleanup_expired_sessions() == 1


@pytest.mark.asyncio
async def test_redis_storage_import_error_and_retrieve_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.backends.redis_backend import RedisStorage

    storage = RedisStorage({})

    monkeypatch.setitem(sys.modules, "redis", None)
    monkeypatch.setitem(sys.modules, "redis.asyncio", None)
    with pytest.raises(ImportError, match="Redis package not installed"):
        await storage._get_redis()

    fake_redis_client = _FakeAsyncRedis()
    storage._redis = fake_redis_client
    assert await storage.retrieve_session("missing") is None


@pytest.mark.asyncio
async def test_s3_storage_happy_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_s3_client = _FakeS3Client()
    fake_boto3 = types.ModuleType("boto3")
    fake_botocore = types.ModuleType("botocore")
    fake_botocore_client = types.ModuleType("botocore.client")
    fake_boto3.Session = lambda **kwargs: types.SimpleNamespace(  # type: ignore[attr-defined]
        client=lambda *a, **k: fake_s3_client,
    )
    fake_botocore_client.Config = lambda **kwargs: kwargs  # type: ignore[attr-defined]
    fake_botocore.client = fake_botocore_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.client", fake_botocore_client)

    from session_buddy.backends.s3_backend import S3Storage

    class _NaiveDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return datetime.now()

    monkeypatch.setattr("session_buddy.backends.s3_backend.datetime", _NaiveDateTime)

    storage = S3Storage({"key_prefix": "archive/"})
    state = _state("s3-session")

    assert storage._get_key(state.session_id) == "archive/s3-session.json.gz"

    assert await storage.is_available() is True

    assert await storage.store_session(state, ttl_seconds=30) is True
    assert fake_s3_client.put_calls[0]["Bucket"] == "session-mgmt-mcp"
    assert fake_s3_client.put_calls[0]["Key"] == "archive/s3-session.json.gz"
    assert "Expires" in fake_s3_client.put_calls[0]

    body = fake_s3_client.put_calls[0]["Body"]
    assert isinstance(body, bytes)
    assert gzip.decompress(body).decode("utf-8")

    fake_s3_client.body_by_key["archive/s3-session.json.gz"] = body
    retrieved = await storage.retrieve_session(state.session_id)
    assert retrieved == state

    fake_s3_client.objects = [
        {"Key": "archive/s3-session.json.gz", "LastModified": datetime.now()},
        {
            "Key": "archive/old-session.json.gz",
            "LastModified": datetime.now() - timedelta(days=31),
        },
    ]
    fake_s3_client.metadata = {
        "archive/s3-session.json.gz": {"user_id": "user-1", "project_id": "project-1"},
        "archive/old-session.json.gz": {"user_id": "user-2", "project_id": "project-2"},
    }

    assert await storage._get_s3_objects(fake_s3_client) == fake_s3_client.objects
    assert storage._extract_session_id_from_key("archive/s3-session.json.gz") == "s3-session"
    assert await storage._should_include_s3_session(
        fake_s3_client,
        "archive/s3-session.json.gz",
        user_id="user-1",
        project_id="project-1",
    ) is True
    assert await storage._should_include_s3_session(
        fake_s3_client,
        "archive/s3-session.json.gz",
        user_id="other",
        project_id=None,
    ) is False

    assert set(await storage.list_sessions()) == {"s3-session", "old-session"}
    assert set(await storage.list_sessions(user_id="user-1")) == {"s3-session"}
    assert set(await storage.list_sessions(project_id="project-1")) == {"s3-session"}

    assert await storage.cleanup_expired_sessions() == 1
    assert fake_s3_client.delete_calls[-1] == ("session-mgmt-mcp", "archive/old-session.json.gz")


@pytest.mark.asyncio
async def test_s3_storage_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.backends.s3_backend import S3Storage

    storage = S3Storage({})

    monkeypatch.setitem(sys.modules, "boto3", None)
    monkeypatch.setitem(sys.modules, "botocore", None)
    monkeypatch.setitem(sys.modules, "botocore.client", None)
    with pytest.raises(ImportError, match="Boto3 package not installed"):
        await storage._get_s3_client()
