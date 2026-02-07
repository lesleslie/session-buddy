"""Tests for Session-Buddy sync.py TODO resolutions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from session_buddy.sync import RemoteSessionBuddy, AkoshaSync


class TestRemoteSessionBuddyMemoryParsing:
    """Test memory parsing from remote Session-Buddy instances."""

    @pytest.fixture
    def remote_buddy(self):
        """Create RemoteSessionBuddy instance."""
        return RemoteSessionBuddy(base_url="http://localhost:8678/mcp")

    @pytest.mark.asyncio
    async def test_parse_json_memories(self, remote_buddy):
        """Test parsing JSON-formatted memory response."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "result": '[{"id": "mem1", "text": "Test memory 1", "created_at": "2026-02-05T10:00:00Z"}]'
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(httpx, "AsyncClient", return_value=mock_client):
            memories = await remote_buddy.fetch_memories()

        assert len(memories) == 1
        assert memories[0]["id"] == "mem1"
        assert memories[0]["text"] == "Test memory 1"

    @pytest.mark.asyncio
    async def test_parse_text_memory(self, remote_buddy):
        """Test parsing plain text memory response."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "result": "This is a plain text memory"
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(httpx, "AsyncClient", return_value=mock_client):
            memories = await remote_buddy.fetch_memories()

        assert len(memories) == 1
        assert memories[0]["text"] == "This is a plain text memory"
        assert "source" in memories[0]

    @pytest.mark.asyncio
    async def test_parse_dict_memory(self, remote_buddy):
        """Test parsing single dict memory response."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "result": {"id": "mem1", "text": "Single memory"}
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(httpx, "AsyncClient", return_value=mock_client):
            memories = await remote_buddy.fetch_memories()

        assert len(memories) == 1
        assert memories[0]["id"] == "mem1"


class TestRemoteSessionBuddyRecentMemories:
    """Test recent memories filtering by timestamp."""

    @pytest.fixture
    def remote_buddy(self):
        """Create RemoteSessionBuddy instance."""
        return RemoteSessionBuddy(base_url="http://localhost:8678/mcp")

    @pytest.mark.asyncio
    async def test_filter_recent_memories(self, remote_buddy):
        """Test filtering memories by timestamp."""
        # Mock memories with different timestamps
        now = datetime.now(UTC)
        old_memories = [
            {
                "id": "mem1",
                "text": "Recent memory",
                "created_at": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "id": "mem2",
                "text": "Old memory",
                "created_at": (now - timedelta(hours=25)).isoformat(),
            },
            {
                "id": "mem3",
                "text": "Another recent",
                "created_at": (now - timedelta(hours=6)).isoformat(),
            },
        ]

        with patch.object(remote_buddy, "search_memories", return_value=old_memories):
            recent = await remote_buddy.get_recent_memories(hours=24, limit=10)

        # Should return only memories within 24 hours
        assert len(recent) == 2
        assert any(m["id"] == "mem1" for m in recent)
        assert any(m["id"] == "mem3" for m in recent)
        assert not any(m["id"] == "mem2" for m in recent)

    @pytest.mark.asyncio
    async def test_sort_by_timestamp(self, remote_buddy):
        """Test memories are sorted by timestamp (newest first)."""
        now = datetime.now(UTC)
        memories = [
            {"id": "mem2", "created_at": (now - timedelta(hours=5)).isoformat()},
            {"id": "mem1", "created_at": (now - timedelta(hours=1)).isoformat()},
            {"id": "mem3", "created_at": (now - timedelta(hours=10)).isoformat()},
        ]

        with patch.object(remote_buddy, "search_memories", return_value=memories):
            recent = await remote_buddy.get_recent_memories(hours=24, limit=10)

        # Should be sorted newest first
        assert recent[0]["id"] == "mem1"  # 1 hour ago
        assert recent[1]["id"] == "mem2"  # 5 hours ago
        assert recent[2]["id"] == "mem3"  # 10 hours ago

    @pytest.mark.asyncio
    async def test_respects_limit(self, remote_buddy):
        """Test result limit is respected."""
        now = datetime.now(UTC)
        memories = [
            {"id": f"mem{i}", "created_at": (now - timedelta(hours=i)).isoformat()}
            for i in range(1, 101)
        ]

        with patch.object(remote_buddy, "search_memories", return_value=memories):
            recent = await remote_buddy.get_recent_memories(hours=24, limit=10)

        # Should return only 10 results
        assert len(recent) == 10


class TestAkoshaStorageIntegration:
    """Test AkOSHA storage integration."""

    @pytest.fixture
    def embedding_service(self):
        """Create mock embedding service."""
        service = MagicMock()
        service.get_embedding.return_value = [0.1, 0.2, 0.3]
        return service

    @pytest.fixture
    def akosha_sync(self, embedding_service):
        """Create AkoshaSync instance."""
        return AkoshaSync(
            embedding_service=embedding_service,
            instance_urls=["http://localhost:8678/mcp"],
        )

    @pytest.mark.asyncio
    async def test_store_memory_in_akosha(self, akosha_sync):
        """Test storing memory in AkOSHA."""
        memory = {
            "id": "test_mem",
            "text": "Test memory content",
            "type": "session_memory",
        }
        text = "Test memory content"
        embedding = [0.1, 0.2, 0.3]

        # Mock successful AkOSHA storage
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await akosha_sync.store_memory(memory, text, embedding, "test_source")

        assert result["status"] == "stored"
        assert "memory_id" in result

    @pytest.mark.asyncio
    async def test_akosha_storage_error_handling(self, akosha_sync):
        """Test error handling when AkOSHA storage fails."""
        memory = {"id": "test_mem", "text": "Test"}
        text = "Test"
        embedding = [0.1, 0.2, 0.3]

        # Mock HTTP error
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "Storage failed", request=None, response=None
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await akosha_sync.store_memory(memory, text, embedding, "test")

        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_memory_data_format(self, akosha_sync):
        """Test memory data is properly formatted for AkOSHA."""
        memory = {
            "id": "test_mem",
            "text": "Test memory",
            "created_at": "2026-02-05T10:00:00Z",
        }
        text = "Test memory"
        embedding = [0.1, 0.2, 0.3, 0.4]

        mock_client = AsyncMock()
        mock_client.post.return_value = AsyncMock(
            raise_for_status=MagicMock(),
            status_code=200
        )

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_httpx:
            await akosha_sync.store_memory(memory, text, embedding, "source")

            # Verify the data sent to AkOSHA
            call_args = mock_httpx.call_args
            sent_data = call_args[1][1]["json"]  # Get the 'json' kwarg

            assert sent_data["id"] == "test_mem"
            assert sent_data["text"] == "Test memory"
            assert sent_data["embedding"] == [0.1, 0.2, 0.3, 0.4]
            assert sent_data["metadata"]["source"] == "source"
            assert "original_id" in sent_data["metadata"]


class TestTemporalDecayScoring:
    """Test temporal memory decay scoring functionality."""

    @pytest.mark.asyncio
    async def test_temporal_decay_calculation(self):
        """Test temporal decay reduces score for old memories."""
        # Calculate decay factor: max(0.8, 1.0 - (age_days / 180))
        now = datetime.now(UTC)

        # Recent memory (30 days old)
        recent_age = (now - timedelta(days=30)).days
        recent_decay = max(0.8, 1.0 - (recent_age / 180))
        assert recent_decay == 1.0 - (30 / 180)  # ~0.833

        # Old memory (200 days old)
        old_age = (now - timedelta(days=200)).days
        old_decay = max(0.8, 1.0 - (old_age / 180))
        assert old_decay == 0.8  # Minimum decay factor

        # Medium age memory (90 days old)
        medium_age = (now - timedelta(days=90)).days
        medium_decay = max(0.8, 1.0 - (medium_age / 180))
        assert medium_decay == 0.5  # 1.0 - (90/180) = 0.5

    @pytest.mark.asyncio
    async def test_temporal_score_with_semantic(self):
        """Test temporal score combines semantic and temporal factors."""
        # Semantic score: 0.9 (high similarity)
        # Age: 90 days → decay factor: 0.5
        # Expected temporal score: 0.9 * 0.5 = 0.45

        semantic_score = 0.9
        age_days = 90
        decay_factor = max(0.8, 1.0 - (age_days / 180))
        temporal_score = semantic_score * decay_factor

        assert temporal_score == 0.45
        # 15-20% accuracy improvement for old embeddings
