"""S3-compatible session storage backend.

**DEPRECATED**: This module is deprecated and will be removed in v1.0.
Use ServerlessStorageAdapter with backend="s3" instead, which uses ACB's
native S3 storage adapter for better performance and features.

Migration:
    Old: S3Storage(config)
    New: ServerlessStorageAdapter(config, backend="s3")

This module provides an S3-compatible implementation of the SessionStorage interface
for storing and retrieving session state in S3-compatible object storage.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import warnings
from datetime import UTC, datetime, timedelta
from typing import Any

from session_buddy.backends.base import SessionState, SessionStorage


class S3Storage(SessionStorage):
    """S3-based session storage.

    .. deprecated:: 0.9.3
        S3Storage is deprecated. Use ``ServerlessStorageAdapter(backend="s3")``
        which provides better performance, connection pooling, and streaming support
        via ACB's native S3 storage adapter.

    """

    def __init__(self, config: dict[str, Any]) -> None:
        warnings.warn(
            "S3Storage is deprecated and will be removed in v1.0. "
            "Use ServerlessStorageAdapter(backend='s3') instead for better "
            "performance and ACB integration.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(config)
        self.bucket_name = config.get("bucket_name", "session-mgmt-mcp")
        self.region = config.get("region", "us-east-1")
        self.key_prefix = config.get("key_prefix", "sessions/")
        self.access_key_id = config.get("access_key_id")
        self.secret_access_key = config.get("secret_access_key")
        self._s3_client = None

    async def _get_s3_client(self) -> Any:
        """Get or create S3 client."""
        if self._s3_client is None:
            try:
                import boto3
                from botocore.client import Config

                session = boto3.Session(
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name=self.region,
                )

                self._s3_client = session.client(
                    "s3",
                    config=Config(retries={"max_attempts": 3}, max_pool_connections=50),
                )
            except ImportError:
                msg = "Boto3 package not installed. Install with: pip install boto3"
                raise ImportError(
                    msg,
                )

        return self._s3_client

    def _get_key(self, session_id: str) -> str:
        """Get S3 key for session."""
        return f"{self.key_prefix}{session_id}.json.gz"

    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session in S3."""
        try:
            s3_client = await self._get_s3_client()

            # Serialize and compress session state
            serialized = json.dumps(session_state.to_dict())
            compressed = gzip.compress(serialized.encode("utf-8"))

            # Prepare S3 object metadata
            metadata = {
                "user_id": session_state.user_id,
                "project_id": session_state.project_id,
                "created_at": session_state.created_at,
                "last_activity": session_state.last_activity,
            }

            # Set expiration if TTL specified
            expires = None
            if ttl_seconds:
                expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

            # Upload to S3
            key = self._get_key(session_state.session_id)

            put_args = {
                "Bucket": self.bucket_name,
                "Key": key,
                "Body": compressed,
                "ContentType": "application/json",
                "ContentEncoding": "gzip",
                "Metadata": metadata,
            }

            if expires:
                put_args["Expires"] = expires

            # Execute in thread pool since boto3 is synchronous
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: s3_client.put_object(**put_args))

            return True

        except Exception as e:
            self.logger.exception(
                f"Failed to store session {session_state.session_id}: {e}",
            )
            return False

    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session from S3."""
        try:
            s3_client = await self._get_s3_client()
            key = self._get_key(session_id)

            # Download from S3
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: s3_client.get_object(Bucket=self.bucket_name, Key=key),
            )

            # Decompress and deserialize
            compressed_data = response["Body"].read()
            serialized = gzip.decompress(compressed_data).decode("utf-8")
            session_data = json.loads(serialized)

            return SessionState.from_dict(session_data)

        except Exception as e:
            self.logger.exception(f"Failed to retrieve session {session_id}: {e}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete session from S3."""
        try:
            s3_client = await self._get_s3_client()
            key = self._get_key(session_id)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: s3_client.delete_object(Bucket=self.bucket_name, Key=key),
            )

            return True

        except Exception as e:
            self.logger.exception(f"Failed to delete session {session_id}: {e}")
            return False

    async def list_sessions(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        """List sessions in S3."""
        try:
            s3_client = await self._get_s3_client()
            s3_objects = await self._get_s3_objects(s3_client)

            session_ids = []
            for obj in s3_objects:
                key = obj["Key"]
                session_id = self._extract_session_id_from_key(key)

                if await self._should_include_s3_session(
                    s3_client,
                    key,
                    user_id,
                    project_id,
                ):
                    session_ids.append(session_id)

            return session_ids

        except Exception as e:
            self.logger.exception(f"Failed to list sessions: {e}")
            return []

    async def _get_s3_objects(self, s3_client: Any) -> list[dict[str, Any]]:
        """Get S3 objects with the configured prefix."""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.key_prefix,
            ),
        )
        contents = response.get("Contents", [])
        return list(contents) if contents else []

    def _extract_session_id_from_key(self, key: str) -> str:
        """Extract session ID from S3 object key."""
        return key.replace(self.key_prefix, "").replace(".json.gz", "")

    async def _should_include_s3_session(
        self,
        s3_client: Any,
        key: str,
        user_id: str | None,
        project_id: str | None,
    ) -> bool:
        """Check if S3 session should be included based on filters."""
        if not user_id and not project_id:
            return True

        metadata = await self._get_s3_object_metadata(s3_client, key)

        if user_id and metadata.get("user_id") != user_id:
            return False
        return not (project_id and metadata.get("project_id") != project_id)

    async def _get_s3_object_metadata(self, s3_client: Any, key: str) -> dict[str, Any]:
        """Get metadata for an S3 object."""
        loop = asyncio.get_event_loop()
        head_response = await loop.run_in_executor(
            None,
            lambda: s3_client.head_object(Bucket=self.bucket_name, Key=key),
        )
        metadata = head_response.get("Metadata", {})
        return dict(metadata) if metadata else {}

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions from S3."""
        try:
            s3_client = await self._get_s3_client()

            # S3 lifecycle policies handle expiration automatically
            # This could implement custom logic for old sessions

            now = datetime.now(UTC)
            cleaned = 0

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=self.key_prefix,
                ),
            )

            for obj in response.get("Contents", []):
                # Check if object is expired (custom logic)
                last_modified = obj["LastModified"].replace(tzinfo=None)
                age_days = (now - last_modified).days

                if age_days > 30:  # Cleanup sessions older than 30 days
                    await loop.run_in_executor(
                        None,
                        lambda: s3_client.delete_object(
                            Bucket=self.bucket_name,
                            Key=obj["Key"],
                        ),
                    )
                    cleaned += 1

            return cleaned

        except Exception as e:
            self.logger.exception(f"Failed to cleanup expired sessions: {e}")
            return 0

    async def is_available(self) -> bool:
        """Check if S3 is available."""
        try:
            s3_client = await self._get_s3_client()

            # Test bucket access
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: s3_client.head_bucket(Bucket=self.bucket_name),
            )

            return True
        except Exception:
            return False
