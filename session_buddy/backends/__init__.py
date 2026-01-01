"""Storage backends for serverless session management.

This package provides various storage backend implementations for session state:
- RedisStorage: Redis-based storage with TTL support (deprecated)
- S3Storage: S3-compatible object storage (deprecated)
- LocalFileStorage: Local file system storage (development/testing, deprecated)

All backends implement the SessionStorage abstract interface.
"""

from session_buddy.backends.base import SessionState, SessionStorage
from session_buddy.backends.local_backend import LocalFileStorage
from session_buddy.backends.redis_backend import RedisStorage
from session_buddy.backends.s3_backend import S3Storage

__all__ = [
    "LocalFileStorage",
    "RedisStorage",
    "S3Storage",
    "SessionState",
    "SessionStorage",
]
