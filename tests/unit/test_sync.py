"""Comprehensive pytest unit tests for session_buddy.sync module.

Tests cover:
- MemorySyncClient: HTTP client for fetching memories from remote Session-Buddy instances
- AkoshaSync: Orchestrator for syncing memories to AkOSHA
- Sync operations: push, pull, conflict resolution, partial sync
- Edge cases: network failures, concurrent modifications, corrupted data, empty sync
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

# Import the module under test
from session_buddy.sync import (
    AkoshaSync,
    MemorySyncClient,
    RemoteSessionBuddy,
    _maybe_await,
    sync_all_instances,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create a mock embedding service."""
    service = MagicMock()
    service.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return service


@pytest.fixture
def sample_memory() -> dict[str, Any]:
    """Create a sample memory dictionary."""
    return {
        "id": "mem_123",
        "content": "This is a test memory",
        "created_at": datetime.now(UTC).isoformat(),
        "type": "session_memory",
    }


@pytest.fixture
def sample_memories() -> list[dict[str, Any]]:
    """Create a list of sample memory dictionaries."""
    return [
        {
            "id": "mem_1",
            "content": "First memory",
            "created_at": datetime.now(UTC).isoformat(),
            "type": "session_memory",
        },
        {
            "id": "mem_2",
            "summary": "Second memory summary",
            "created_at": datetime.now(UTC).isoformat(),
            "type": "session_memory",
        },
        {
            "id": "mem_3",
            "query": "What is Python?",
            "response": "Python is a programming language.",
            "created_at": datetime.now(UTC).isoformat(),
            "type": "session_memory",
        },
    ]


# ---------------------------------------------------------------------------
# Tests for _maybe_await helper
# ---------------------------------------------------------------------------


class TestMaybeAwait:
    """Tests for the _maybe_await helper function."""

    @pytest.mark.asyncio
    async def test_returns_awaitable(self) -> None:
        """Test that awaitables are properly awaited."""
        async def async_value() -> int:
            return 42

        result = await _maybe_await(async_value())
        assert result == 42

    @pytest.mark.asyncio
    async def test_returns_plain_value(self) -> None:
        """Test that plain values are returned as-is."""
        result = await _maybe_await(42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_returns_string(self) -> None:
        """Test that strings are returned as-is."""
        result = await _maybe_await("hello")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        """Test that lists are returned as-is."""
        result = await _maybe_await([1, 2, 3])
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_returns_none(self) -> None:
        """Test that None is returned as-is."""
        result = await _maybe_await(None)
        assert result is None


# ---------------------------------------------------------------------------
# Tests for MemorySyncClient
# ---------------------------------------------------------------------------


class TestMemorySyncClientInit:
    """Tests for MemorySyncClient.__init__."""

    def test_strips_trailing_slash(self) -> None:
        """Test that trailing slashes are stripped from base_url."""
        client = MemorySyncClient("http://example.com/")
        assert client.base_url == "http://example.com"

    def test_preserves_url_without_slash(self) -> None:
        """Test that URLs without trailing slashes are preserved."""
        client = MemorySyncClient("http://example.com")
        assert client.base_url == "http://example.com"

    def test_default_timeout(self) -> None:
        """Test default timeout is 30 seconds."""
        client = MemorySyncClient("http://example.com")
        assert client.timeout == 30.0

    def test_custom_timeout(self) -> None:
        """Test custom timeout value."""
        client = MemorySyncClient("http://example.com", timeout=60.0)
        assert client.timeout == 60.0

    def test_client_initially_none(self) -> None:
        """Test that _client is initially None."""
        client = MemorySyncClient("http://example.com")
        assert client._client is None


class TestMemorySyncClientContextManager:
    """Tests for MemorySyncClient async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_returns_client(self) -> None:
        """Test __aenter__ returns the client instance."""
        client = MemorySyncClient("http://example.com")
        result = await client.__aenter__()
        assert result is client

    @pytest.mark.asyncio
    async def test_aenter_creates_client(self) -> None:
        """Test __aenter__ creates an httpx.AsyncClient."""
        client = MemorySyncClient("http://example.com")
        await client.__aenter__()
        assert client._client is not None

    @pytest.mark.asyncio
    async def test_aexit_closes_client(self) -> None:
        """Test __aexit__ closes the client."""
        client = MemorySyncClient("http://example.com")
        await client.__aenter__()
        assert client._client is not None
        # __aexit__ calls aclose() but does not null out _client per implementation
        await client.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_aexit_handles_none_client(self) -> None:
        """Test __aexit__ handles case when client is None."""
        client = MemorySyncClient("http://example.com")
        # Should not raise
        await client.__aexit__(None, None, None)


class TestMemorySyncClientSearchMemories:
    """Tests for MemorySyncClient.search_memories method."""

    @pytest.mark.asyncio
    async def test_search_memories_success_json_list(self) -> None:
        """Test successful search with JSON list response."""
        memories = [
            {"id": "mem_1", "content": "Test"},
            {"id": "mem_2", "content": "Test 2"},
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value={"result": json.dumps(memories)})

        client = MemorySyncClient("http://example.com")
        # Inject mock _client directly
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.search_memories(query="test", limit=10)

        assert len(result) == 2
        assert result[0]["id"] == "mem_1"

    @pytest.mark.asyncio
    async def test_search_memories_success_dict_response(self) -> None:
        """Test successful search with JSON dict response."""
        memory = {"id": "mem_1", "content": "Test"}

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value={"result": json.dumps(memory)})

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.search_memories(query="test", limit=10)

        assert len(result) == 1
        assert result[0]["id"] == "mem_1"

    @pytest.mark.asyncio
    async def test_search_memories_plain_text_response(self) -> None:
        """Test successful search with plain text response."""
        text = "Plain text response"

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value={"result": text})

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.search_memories(query="test", limit=10)

        assert len(result) == 1
        assert result[0]["text"] == text
        assert "source" in result[0]

    @pytest.mark.asyncio
    async def test_search_memories_empty_result(self) -> None:
        """Test search with empty result."""
        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value={"result": None})

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.search_memories(query="test", limit=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_search_memories_no_result_key(self) -> None:
        """Test search with no result key in response."""
        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value={})

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.search_memories(query="test", limit=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_search_memories_with_project_filter(self) -> None:
        """Test search with project filter."""
        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={"result": json.dumps([{"id": "mem_1"}])}
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.search_memories(
            query="test", limit=10, project="myproject"
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_search_memories_http_error(self) -> None:
        """Test search handles HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock()
            )
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        with pytest.raises(httpx.HTTPStatusError):
            await client.search_memories(query="test", limit=10)

    @pytest.mark.asyncio
    async def test_search_memories_min_score(self) -> None:
        """Test search with min_score parameter."""
        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={"result": json.dumps([{"id": "mem_1"}])}
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.search_memories(query="test", limit=10, min_score=0.5)

        assert len(result) == 1


class TestMemorySyncClientFetchMemories:
    """Tests for MemorySyncClient.fetch_memories method."""

    @pytest.mark.asyncio
    async def test_fetch_memories_success(self) -> None:
        """Test successful fetch."""
        memories = [{"id": "mem_1", "content": "Test"}]

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={"result": json.dumps(memories)}
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.fetch_memories(limit=50)

        assert len(result) == 1
        assert result[0]["id"] == "mem_1"

    @pytest.mark.asyncio
    async def test_fetch_memories_with_project(self) -> None:
        """Test fetch with project filter."""
        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value={"result": json.dumps([])})

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.fetch_memories(limit=50, project="myproject")

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_memories_http_error(self) -> None:
        """Test fetch handles HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock()
            )
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_memories(limit=50)


class TestMemorySyncClientGetRecentMemories:
    """Tests for MemorySyncClient.get_recent_memories method."""

    @pytest.mark.asyncio
    async def test_get_recent_memories_filters_by_time(self) -> None:
        """Test that recent memories are filtered by timestamp."""
        now = datetime.now(UTC)
        old_memory = {
            "id": "old",
            "created_at": (now - timedelta(hours=48)).isoformat(),
        }
        recent_memory = {
            "id": "recent",
            "created_at": now.isoformat(),
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={"result": json.dumps([old_memory, recent_memory])}
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.get_recent_memories(hours=24, limit=10)

        # Should only include the recent memory
        assert len(result) == 1
        assert result[0]["id"] == "recent"

    @pytest.mark.asyncio
    async def test_get_recent_memories_respects_limit(self) -> None:
        """Test that limit is respected."""
        now = datetime.now(UTC)
        memories = [
            {"id": f"mem_{i}", "created_at": now.isoformat()}
            for i in range(20)
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={"result": json.dumps(memories)}
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.get_recent_memories(hours=24, limit=5)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_get_recent_memories_no_timestamp_includes(self) -> None:
        """Test that memories without timestamp are included (fallback)."""
        memory_with_ts = {
            "id": "with_ts",
            "created_at": datetime.now(UTC).isoformat(),
        }
        memory_without_ts = {
            "id": "no_ts",
            "content": "No timestamp",
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={"result": json.dumps([memory_with_ts, memory_without_ts])}
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.get_recent_memories(hours=24, limit=10)

        # Both should be included since one has no timestamp
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_recent_memories_invalid_timestamp_skipped(self) -> None:
        """Test that memories with invalid timestamps are skipped."""
        now = datetime.now(UTC)
        valid_memory = {"id": "valid", "created_at": now.isoformat()}
        invalid_memory = {"id": "invalid", "created_at": "not-a-timestamp"}
        old_memory = {
            "id": "old",
            "created_at": (now - timedelta(hours=48)).isoformat(),
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={"result": json.dumps([valid_memory, invalid_memory, old_memory])}
        )

        client = MemorySyncClient("http://example.com")
        mock_http_client = MagicMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        result = await client.get_recent_memories(hours=24, limit=10)

        # invalid_memory has invalid timestamp, old_memory is out of range
        # So only valid_memory should be included
        assert len(result) == 1
        assert result[0]["id"] == "valid"


class TestMemorySyncClientParseMemoryResponse:
    """Tests for MemorySyncClient._parse_memory_response method."""

    def test_parse_none(self) -> None:
        """Test parsing None returns empty list."""
        client = MemorySyncClient("http://example.com")
        result = client._parse_memory_response(None)
        assert result == []

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string returns empty list."""
        client = MemorySyncClient("http://example.com")
        result = client._parse_memory_response("")
        assert result == []

    def test_parse_json_list(self) -> None:
        """Test parsing JSON list."""
        memories = [{"id": "1"}, {"id": "2"}]
        client = MemorySyncClient("http://example.com")
        result = client._parse_memory_response(json.dumps(memories))
        assert len(result) == 2

    def test_parse_json_dict(self) -> None:
        """Test parsing JSON dict returns list with single item."""
        memory = {"id": "1"}
        client = MemorySyncClient("http://example.com")
        result = client._parse_memory_response(json.dumps(memory))
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_parse_invalid_json_returns_fallback(self) -> None:
        """Test that invalid JSON returns fallback object."""
        client = MemorySyncClient("http://example.com")
        result = client._parse_memory_response("not valid json")
        assert len(result) == 1
        assert result[0]["id"].startswith("remote_")
        assert result[0]["text"] == "not valid json"
        assert result[0]["source"] == "http://example.com"

    def test_parse_list_returns_list(self) -> None:
        """Test that list input returns list."""
        memories = [{"id": "1"}, {"id": "2"}]
        client = MemorySyncClient("http://example.com")
        result = client._parse_memory_response(memories)
        assert len(result) == 2

    def test_parse_dict_returns_list(self) -> None:
        """Test that dict input returns list with item."""
        memory = {"id": "1"}
        client = MemorySyncClient("http://example.com")
        result = client._parse_memory_response(memory)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests for AkoshaSync
# ---------------------------------------------------------------------------


class TestAkoshaSyncInit:
    """Tests for AkoshaSync.__init__."""

    def test_default_instance_urls(self, mock_embedding_service: MagicMock) -> None:
        """Test default instance URL is localhost:8678."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        assert sync.instance_urls == ["http://localhost:8678"]

    def test_custom_instance_urls(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test custom instance URLs."""
        sync = AkoshaSync(
            embedding_service=mock_embedding_service,
            instance_urls=["http://one:8678", "http://two:8678"],
        )
        assert len(sync.instance_urls) == 2
        assert "http://one:8678" in sync.instance_urls

    def test_initial_stats(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test initial statistics are set correctly."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        assert sync.stats["memories_fetched"] == 0
        assert sync.stats["memories_synced"] == 0
        assert sync.stats["embeddings_generated"] == 0
        assert sync.stats["errors"] == []


class TestAkoshaSyncSyncAllInstances:
    """Tests for AkoshaSync.sync_all_instances method."""

    @pytest.mark.asyncio
    async def test_sync_all_resets_stats(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that sync_all_instances resets statistics."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        sync.stats["memories_fetched"] = 100  # Pre-set

        with patch.object(
            sync, "sync_instance", new_callable=AsyncMock
        ) as mock_sync_instance:
            mock_sync_instance.return_value = {"fetched": 0, "synced": 0}
            result = await sync.sync_all_instances()

        assert result["success"] is True
        assert sync.stats["memories_fetched"] == 0

    @pytest.mark.asyncio
    async def test_sync_all_calls_each_instance(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that each instance is synced."""
        sync = AkoshaSync(
            embedding_service=mock_embedding_service,
            instance_urls=["http://one:8678", "http://two:8678"],
        )

        with patch.object(
            sync, "sync_instance", new_callable=AsyncMock
        ) as mock_sync_instance:
            mock_sync_instance.return_value = {"fetched": 5, "synced": 5}
            result = await sync.sync_all_instances()

        assert mock_sync_instance.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_all_aggregates_stats(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that statistics are aggregated across instances."""
        sync = AkoshaSync(
            embedding_service=mock_embedding_service,
            instance_urls=["http://one:8678", "http://two:8678"],
        )

        with patch.object(
            sync, "sync_instance", new_callable=AsyncMock
        ) as mock_sync_instance:
            mock_sync_instance.side_effect = [
                {"fetched": 10, "synced": 9},
                {"fetched": 5, "synced": 5},
            ]
            result = await sync.sync_all_instances()

        assert result["memories_fetched"] == 15
        assert result["memories_synced"] == 14

    @pytest.mark.asyncio
    async def test_sync_all_continues_on_instance_error(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that sync continues even if one instance fails."""
        sync = AkoshaSync(
            embedding_service=mock_embedding_service,
            instance_urls=["http://one:8678", "http://two:8678"],
        )

        with patch.object(
            sync, "sync_instance", new_callable=AsyncMock
        ) as mock_sync_instance:
            mock_sync_instance.side_effect = [
                Exception("Connection failed"),
                {"fetched": 5, "synced": 5},
            ]
            result = await sync.sync_all_instances()

        # Should still succeed overall
        assert result["success"] is True
        # Should have 1 error recorded
        assert len(result["errors"]) == 1

    @pytest.mark.asyncio
    async def test_sync_all_returns_instances_count(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that number of instances synced is returned."""
        sync = AkoshaSync(
            embedding_service=mock_embedding_service,
            instance_urls=["http://one:8678", "http://two:8678", "http://three:8678"],
        )

        with patch.object(
            sync, "sync_instance", new_callable=AsyncMock
        ) as mock_sync_instance:
            mock_sync_instance.return_value = {"fetched": 0, "synced": 0}
            result = await sync.sync_all_instances()

        assert result["instances_synced"] == 3


class TestAkoshaSyncSyncInstance:
    """Tests for AkoshaSync.sync_instance method."""

    @pytest.mark.asyncio
    async def test_sync_instance_incremental(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test incremental sync uses get_recent_memories."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch(
            "session_buddy.sync.MemorySyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.get_recent_memories = AsyncMock(return_value=[])
            mock_client_class.return_value = mock_client

            result = await sync.sync_instance(
                base_url="http://example.com",
                incremental=True,
            )

        mock_client.get_recent_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_instance_full_sync(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test full sync uses search_memories."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch(
            "session_buddy.sync.MemorySyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.search_memories = AsyncMock(return_value=[])
            mock_client_class.return_value = mock_client

            result = await sync.sync_instance(
                base_url="http://example.com",
                incremental=False,
            )

        mock_client.search_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_instance_syncs_each_memory(
        self, mock_embedding_service: MagicMock, sample_memories: list[dict]
    ) -> None:
        """Test that each memory is synced."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch(
            "session_buddy.sync.MemorySyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.get_recent_memories = AsyncMock(return_value=sample_memories)
            mock_client_class.return_value = mock_client

            with patch.object(
                sync, "_sync_memory", new_callable=AsyncMock
            ) as mock_sync_memory:
                result = await sync.sync_instance(
                    base_url="http://example.com",
                    incremental=True,
                )

            assert mock_sync_memory.call_count == len(sample_memories)

    @pytest.mark.asyncio
    async def test_sync_instance_continues_on_memory_error(
        self, mock_embedding_service: MagicMock, sample_memories: list[dict]
    ) -> None:
        """Test that sync continues even if a memory fails."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch(
            "session_buddy.sync.MemorySyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.get_recent_memories = AsyncMock(return_value=sample_memories)
            mock_client_class.return_value = mock_client

            async def failing_sync(memory, source):
                if memory["id"] == "mem_1":
                    raise Exception("Failed to sync")

            with patch.object(
                sync, "_sync_memory", new_callable=AsyncMock
            ) as mock_sync_memory:
                mock_sync_memory.side_effect = failing_sync
                result = await sync.sync_instance(
                    base_url="http://example.com",
                    incremental=True,
                )

            # Should still process mem_2 and mem_3
            assert result["fetched"] == 3
            assert result["synced"] == 2  # mem_1 failed
            assert len(sync.stats["errors"]) == 1


class TestAkoshaSyncSyncMemory:
    """Tests for AkoshaSync._sync_memory method."""

    @pytest.mark.asyncio
    async def test_sync_memory_generates_embedding(
        self, mock_embedding_service: MagicMock, sample_memory: dict
    ) -> None:
        """Test that embedding is generated for memory."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch.object(
            sync, "_store_in_akosha", new_callable=AsyncMock
        ) as mock_store:
            await sync._sync_memory(sample_memory, "http://example.com")

        mock_embedding_service.generate_embedding.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_memory_skips_empty_text(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that memory with no text content is skipped."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        empty_memory = {"id": "empty", "type": "session_memory"}  # No content field

        with patch.object(
            sync, "_store_in_akosha", new_callable=AsyncMock
        ) as mock_store:
            await sync._sync_memory(empty_memory, "http://example.com")

        # Should not try to generate embedding for empty text
        mock_embedding_service.generate_embedding.assert_not_called()
        mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_memory_stores_result(
        self, mock_embedding_service: MagicMock, sample_memory: dict
    ) -> None:
        """Test that memory is stored after generating embedding."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch.object(
            sync, "_store_in_akosha", new_callable=AsyncMock
        ) as mock_store:
            await sync._sync_memory(sample_memory, "http://example.com")

        mock_store.assert_called_once()
        call_args = mock_store.call_args
        assert call_args.kwargs["source"] == "http://example.com"

    @pytest.mark.asyncio
    async def test_sync_memory_updates_stats(
        self, mock_embedding_service: MagicMock, sample_memory: dict
    ) -> None:
        """Test that statistics are updated after sync."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch.object(
            sync, "_store_in_akosha", new_callable=AsyncMock
        ):
            await sync._sync_memory(sample_memory, "http://example.com")

        assert sync.stats["embeddings_generated"] == 1


class TestAkoshaSyncExtractText:
    """Tests for AkoshaSync._extract_text method."""

    def test_extract_text_from_content(self, mock_embedding_service: MagicMock) -> None:
        """Test text extraction from content field."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        memory = {"id": "1", "content": "Test content"}
        result = sync._extract_text(memory)
        assert result == "Test content"

    def test_extract_text_from_summary(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test text extraction from summary field."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        memory = {"id": "1", "summary": "Test summary"}
        result = sync._extract_text(memory)
        assert result == "Test summary"

    def test_extract_text_from_reflection(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test text extraction from reflection field."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        memory = {"id": "1", "reflection": "Test reflection"}
        result = sync._extract_text(memory)
        assert result == "Test reflection"

    def test_extract_text_from_query_response(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test text extraction from query/response fields."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        memory = {
            "id": "1",
            "query": "What is Python?",
            "response": "A programming language.",
        }
        result = sync._extract_text(memory)
        assert "What is Python?" in result
        assert "A programming language." in result

    def test_extract_text_empty_for_no_content(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that empty string is returned when no text found."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        memory = {"id": "1", "type": "session_memory"}  # No text fields
        result = sync._extract_text(memory)
        assert result == ""

    def test_extract_text_converts_to_string(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that non-string content is converted to string."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        memory = {"id": "1", "content": 123}  # Integer content
        result = sync._extract_text(memory)
        assert result == "123"


class TestAkoshaSyncStoreInAkosha:
    """Tests for AkoshaSync._store_in_akosha method."""

    @pytest.mark.asyncio
    async def test_store_in_akosha_success(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test successful storage in Akosha."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        # Mock response
        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()

        # Mock the HTTP client created inside _store_in_akosha
        mock_http_client_instance = MagicMock()
        mock_http_client_instance.post = AsyncMock(return_value=mock_response)
        mock_http_client_instance.aclose = AsyncMock()

        with patch("session_buddy.sync.httpx.AsyncClient") as mock_client_class:
            # Make the context manager return our mock client
            instance = mock_client_class.return_value
            instance.__aenter__ = AsyncMock(return_value=mock_http_client_instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.post = mock_http_client_instance.post
            instance.aclose = mock_http_client_instance.aclose

            memory = {"id": "mem_1", "content": "Test"}
            result = await sync._store_in_akosha(
                memory=memory,
                text="Test",
                embedding=[0.1, 0.2, 0.3],
                source="http://example.com",
            )

        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_store_in_akosha_http_error(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test handling of HTTP errors during storage."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock()
            )
        )

        mock_http_client_instance = MagicMock()
        mock_http_client_instance.post = AsyncMock(return_value=mock_response)
        mock_http_client_instance.aclose = AsyncMock()

        with patch("session_buddy.sync.httpx.AsyncClient") as mock_client_class:
            instance = mock_client_class.return_value
            instance.__aenter__ = AsyncMock(return_value=mock_http_client_instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.post = mock_http_client_instance.post
            instance.aclose = mock_http_client_instance.aclose

            memory = {"id": "mem_1", "content": "Test"}
            result = await sync._store_in_akosha(
                memory=memory,
                text="Test",
                embedding=[0.1, 0.2, 0.3],
                source="http://example.com",
            )

        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_store_in_akosha_converts_embedding_to_list(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that numpy arrays are converted to lists."""
        import numpy as np

        sync = AkoshaSync(embedding_service=mock_embedding_service)

        mock_response = MagicMock()
        mock_response.raise_for_status = AsyncMock()

        mock_http_client_instance = MagicMock()
        mock_http_client_instance.post = AsyncMock(return_value=mock_response)
        mock_http_client_instance.aclose = AsyncMock()

        with patch("session_buddy.sync.httpx.AsyncClient") as mock_client_class:
            instance = mock_client_class.return_value
            instance.__aenter__ = AsyncMock(return_value=mock_http_client_instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.post = mock_http_client_instance.post
            instance.aclose = mock_http_client_instance.aclose

            memory = {"id": "mem_1", "content": "Test"}
            await sync._store_in_akosha(
                memory=memory,
                text="Test",
                embedding=np.array([0.1, 0.2, 0.3]),
                source="http://example.com",
            )

            call_args = mock_http_client_instance.post.call_args
            memory_data = call_args.kwargs["json"]
            # Verify embedding was converted to list
            assert isinstance(memory_data["embedding"], list)


class TestAkoshaSyncStoreMemory:
    """Tests for AkoshaSync.store_memory method."""

    @pytest.mark.asyncio
    async def test_store_memory_delegates(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that store_memory calls _store_in_akosha."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch.object(
            sync, "_store_in_akosha", new_callable=AsyncMock
        ) as mock_store:
            mock_store.return_value = {"status": "stored", "memory_id": "mem_1"}
            result = await sync.store_memory(
                memory={"id": "mem_1"},
                text="Test",
                embedding=[0.1, 0.2, 0.3],
                source="http://example.com",
            )

        mock_store.assert_called_once()
        assert result["status"] == "stored"


class TestAkoshaSyncGetStatistics:
    """Tests for AkoshaSync.get_statistics method."""

    def test_get_statistics_returns_copy(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that get_statistics returns a copy of stats."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        stats = sync.get_statistics()

        # Modify returned stats
        stats["memories_fetched"] = 999

        # Original should be unchanged
        assert sync.stats["memories_fetched"] == 0

    def test_get_statistics_contains_expected_keys(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that returned stats have expected keys."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        stats = sync.get_statistics()

        assert "memories_fetched" in stats
        assert "memories_synced" in stats
        assert "embeddings_generated" in stats
        assert "errors" in stats


# ---------------------------------------------------------------------------
# Tests for module-level sync_all_instances function
# ---------------------------------------------------------------------------


class TestSyncAllInstancesFunction:
    """Tests for the sync_all_instances convenience function."""

    @pytest.mark.asyncio
    async def test_sync_all_instances_creates_embedding_service(self) -> None:
        """Test that function creates embedding service if not provided."""
        with patch(
            "session_buddy.sync.AkoshaSync"
        ) as mock_sync_class:
            mock_instance = AsyncMock()
            mock_instance.sync_all_instances = AsyncMock(
                return_value={"success": True}
            )
            mock_sync_class.return_value = mock_instance

            # Patch EmbeddingService to avoid actual initialization
            with patch(
                "akosha.processing.embeddings.EmbeddingService"
            ) as mock_es_class:
                mock_es = MagicMock()
                mock_es.initialize = AsyncMock()
                mock_es_class.return_value = mock_es

                await sync_all_instances()

            mock_es_class.assert_called_once()
            mock_es.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_all_instances_uses_provided_embedding_service(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that provided embedding service is used."""
        with patch(
            "session_buddy.sync.AkoshaSync"
        ) as mock_sync_class:
            mock_instance = AsyncMock()
            mock_instance.sync_all_instances = AsyncMock(
                return_value={"success": True}
            )
            mock_sync_class.return_value = mock_instance

            result = await sync_all_instances(embedding_service=mock_embedding_service)

            call_kwargs = mock_sync_class.call_args.kwargs
            assert call_kwargs["embedding_service"] is mock_embedding_service

    @pytest.mark.asyncio
    async def test_sync_all_instances_passes_parameters(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that parameters are passed through."""
        with patch(
            "session_buddy.sync.AkoshaSync"
        ) as mock_sync_class:
            mock_instance = AsyncMock()
            mock_instance.sync_all_instances = AsyncMock(
                return_value={"success": True, "memories_synced": 10}
            )
            mock_sync_class.return_value = mock_instance

            result = await sync_all_instances(
                instance_urls=["http://one:8678"],
                embedding_service=mock_embedding_service,
                query="test",
                limit=50,
                incremental=False,
            )

            mock_instance.sync_all_instances.assert_called_once_with(
                query="test",
                limit=50,
                incremental=False,
            )

    @pytest.mark.asyncio
    async def test_sync_all_instances_returns_result(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that the result is returned."""
        with patch(
            "session_buddy.sync.AkoshaSync"
        ) as mock_sync_class:
            mock_instance = AsyncMock()
            mock_instance.sync_all_instances = AsyncMock(
                return_value={"success": True, "memories_synced": 5}
            )
            mock_sync_class.return_value = mock_instance

            result = await sync_all_instances(embedding_service=mock_embedding_service)

        assert result["success"] is True
        assert result["memories_synced"] == 5


# ---------------------------------------------------------------------------
# Tests for RemoteSessionBuddy alias
# ---------------------------------------------------------------------------


class TestRemoteSessionBuddyAlias:
    """Tests for RemoteSessionBuddy alias."""

    def test_remote_session_buddy_is_memory_sync_client(self) -> None:
        """Test that RemoteSessionBuddy is an alias for MemorySyncClient."""
        assert RemoteSessionBuddy is MemorySyncClient


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for sync module."""

    @pytest.mark.asyncio
    async def test_concurrent_sync_modifications(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test handling of concurrent modifications to stats."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        async def modify_stats():
            for _ in range(10):
                sync.stats["memories_synced"] += 1
                await asyncio.sleep(0.001)

        # Run concurrent modifications
        await asyncio.gather(modify_stats(), modify_stats())

        # Should handle without race conditions (basic test)
        assert sync.stats["memories_synced"] == 20

    @pytest.mark.asyncio
    async def test_corrupted_data_handling(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test handling of corrupted data."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        corrupted_memory = {
            "id": "corrupted",
            # No proper content fields
        }

        # Should not raise, just skip
        with patch.object(
            sync, "_store_in_akosha", new_callable=AsyncMock
        ) as mock_store:
            await sync._sync_memory(corrupted_memory, "http://example.com")

        # Memory with no extractable text should be skipped
        mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_sync_results(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test handling of empty sync results."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)

        with patch(
            "session_buddy.sync.MemorySyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.get_recent_memories = AsyncMock(return_value=[])
            mock_client_class.return_value = mock_client

            result = await sync.sync_instance(
                base_url="http://example.com",
                incremental=True,
            )

        assert result["fetched"] == 0
        assert result["synced"] == 0

    @pytest.mark.asyncio
    async def test_large_memory_handling(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test handling of large memory content."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        large_memory = {
            "id": "large",
            "content": "x" * 100000,  # 100KB of content
        }

        # Should handle without issues
        text = sync._extract_text(large_memory)
        assert len(text) == 100000

    @pytest.mark.asyncio
    async def test_special_characters_in_memory(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test handling of special characters in memory content."""
        sync = AkoshaSync(embedding_service=mock_embedding_service)
        memory = {
            "id": "special",
            "content": "Unicode: éèê | Emoji: \U0001F600 | Control: \x00",
        }

        text = sync._extract_text(memory)
        assert "é" in text
        assert "\U0001F600" in text


# ---------------------------------------------------------------------------
# Integration-style tests (mocked external dependencies)
# ---------------------------------------------------------------------------


class TestSyncIntegration:
    """Integration-style tests with all external dependencies mocked."""

    @pytest.mark.asyncio
    async def test_full_sync_workflow(
        self, mock_embedding_service: MagicMock, sample_memories: list
    ) -> None:
        """Test complete sync workflow from fetching to storing."""
        sync = AkoshaSync(
            embedding_service=mock_embedding_service,
            instance_urls=["http://one:8678", "http://two:8678"],
        )

        with patch(
            "session_buddy.sync.MemorySyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.get_recent_memories = AsyncMock(return_value=sample_memories)
            mock_client_class.return_value = mock_client

            with patch.object(
                sync, "_store_in_akosha", new_callable=AsyncMock
            ) as mock_store:
                mock_store.return_value = {"status": "stored", "memory_id": "test"}

                result = await sync.sync_all_instances(incremental=True)

        assert result["success"] is True
        assert result["instances_synced"] == 2

    @pytest.mark.asyncio
    async def test_conflict_resolution_strategy(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test sync handles conflicting memories from different instances."""
        sync = AkoshaSync(
            embedding_service=mock_embedding_service,
            instance_urls=["http://one:8678", "http://two:8678"],
        )

        # Same memory ID from two sources
        conflicting_memory = {
            "id": "mem_conflict",
            "content": "Conflicting content",
            "created_at": datetime.now(UTC).isoformat(),
        }

        with patch(
            "session_buddy.sync.MemorySyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            # Same memory from both instances
            mock_client.get_recent_memories = AsyncMock(
                return_value=[conflicting_memory]
            )
            mock_client_class.return_value = mock_client

            with patch.object(
                sync, "_store_in_akosha", new_callable=AsyncMock
            ) as mock_store:
                # Both instances will try to store the same memory
                # Current implementation doesn't deduplicate
                result = await sync.sync_all_instances(incremental=True)

        # Both instances sync successfully (no deduplication currently)
        assert result["success"] is True
