"""Unit tests for session_buddy.core.causal_chains."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.causal_chains import (
    CausalChain,
    CausalChainTracker,
    ErrorEvent,
    FixAttempt,
)


class TestErrorEvent:
    """Tests for ErrorEvent dataclass."""

    def test_error_event_creation(self) -> None:
        """Test ErrorEvent can be created with required fields."""
        event = ErrorEvent(
            id="err-12345678",
            error_message="ImportError: module not found",
            error_type="ImportError",
            context={"file": "main.py", "line": 10},
            timestamp=datetime.now(),
            session_id="session-123",
        )

        assert event.id == "err-12345678"
        assert event.error_message == "ImportError: module not found"
        assert event.error_type == "ImportError"
        assert event.context == {"file": "main.py", "line": 10}
        assert event.session_id == "session-123"
        assert event.embedding is None

    def test_error_event_with_embedding(self) -> None:
        """Test ErrorEvent can include embedding vector."""
        embedding = [0.1] * 384
        event = ErrorEvent(
            id="err-abcdefgh",
            error_message="TypeError",
            error_type="TypeError",
            context={},
            timestamp=datetime.now(),
            session_id="s1",
            embedding=embedding,
        )

        assert event.embedding is not None
        assert len(event.embedding) == 384


class TestFixAttempt:
    """Tests for FixAttempt dataclass."""

    def test_fix_attempt_creation(self) -> None:
        """Test FixAttempt can be created with required fields."""
        attempt = FixAttempt(
            id="fix-12345678",
            error_id="err-87654321",
            action_taken="Added missing import",
            code_changes="import os",
            successful=True,
        )

        assert attempt.id == "fix-12345678"
        assert attempt.error_id == "err-87654321"
        assert attempt.action_taken == "Added missing import"
        assert attempt.code_changes == "import os"
        assert attempt.successful is True

    def test_fix_attempt_defaults(self) -> None:
        """Test FixAttempt has sensible defaults."""
        attempt = FixAttempt(
            id="fix-11111111",
            error_id="err-22222222",
            action_taken="Restarted service",
        )

        assert attempt.successful is False
        assert attempt.code_changes is None
        assert isinstance(attempt.timestamp, datetime)


class TestCausalChain:
    """Tests for CausalChain dataclass."""

    def test_causal_chain_creation(self) -> None:
        """Test CausalChain links error to attempts."""
        error_event = ErrorEvent(
            id="err-12345678",
            error_message="Error",
            error_type="Error",
            context={},
            timestamp=datetime.now(),
            session_id="s1",
        )
        fix_attempt = FixAttempt(
            id="fix-87654321",
            error_id="err-12345678",
            action_taken="Applied fix",
            successful=True,
        )

        chain = CausalChain(
            id="chain-abcdefgh",
            error_event=error_event,
            fix_attempts=[fix_attempt],
            successful_fix=fix_attempt,
            resolution_time_minutes=5.5,
        )

        assert chain.id == "chain-abcdefgh"
        assert chain.error_event.id == "err-12345678"
        assert len(chain.fix_attempts) == 1
        assert chain.successful_fix is fix_attempt
        assert chain.resolution_time_minutes == 5.5

    def test_causal_chain_with_no_resolution(self) -> None:
        """Test CausalChain can exist without resolution."""
        error_event = ErrorEvent(
            id="err-11111111",
            error_message="Error",
            error_type="Error",
            context={},
            timestamp=datetime.now(),
            session_id="s1",
        )

        chain = CausalChain(
            id="chain-unresolved",
            error_event=error_event,
            fix_attempts=[],
            successful_fix=None,
            resolution_time_minutes=None,
        )

        assert chain.successful_fix is None
        assert chain.resolution_time_minutes is None


class TestCausalChainTracker:
    """Tests for CausalChainTracker class."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock ReflectionDatabaseAdapterOneiric."""
        mock = MagicMock()
        mock.conn = AsyncMock()
        return mock

    @pytest.fixture
    def tracker(self, mock_db: MagicMock) -> CausalChainTracker:
        """Create a CausalChainTracker with directly injected mock db."""
        tracker = CausalChainTracker()
        tracker.db = mock_db
        return tracker

    @pytest.mark.asyncio
    async def test_record_error_event_generates_id(self, tracker: CausalChainTracker) -> None:
        """Test record_error_event returns properly formatted ID."""
        error_id = await tracker.record_error_event(
            error="Test error",
            context={"file": "test.py"},
            session_id="session-123",
        )

        assert error_id.startswith("err-")
        assert len(error_id) == 12  # "err-" + 8 chars

    @pytest.mark.asyncio
    async def test_record_error_event_calls_db_execute(self, tracker: CausalChainTracker, mock_db: MagicMock) -> None:
        """Test record_error_event stores error in database."""
        await tracker.record_error_event(
            error="ImportError: module not found",
            context={"file": "main.py", "error_type": "ImportError"},
            session_id="session-456",
        )

        mock_db.conn.execute.assert_called_once()
        call_args = mock_db.conn.execute.call_args
        assert "INSERT INTO causal_error_events" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_record_fix_attempt_generates_id(self, tracker: CausalChainTracker) -> None:
        """Test record_fix_attempt returns properly formatted ID."""
        fix_id = await tracker.record_fix_attempt(
            error_id="err-12345678",
            action_taken="Added import",
            successful=False,
        )

        assert fix_id.startswith("fix-")
        assert len(fix_id) == 12

    @pytest.mark.asyncio
    async def test_record_fix_attempt_calls_db_execute(self, tracker: CausalChainTracker, mock_db: MagicMock) -> None:
        """Test record_fix_attempt calls db execute (even with async mock)."""
        # When successful=True, it also calls _create_causal_chain which uses fetchone
        # The key assertion is that execute is called - exact call check depends on async behavior
        await tracker.record_fix_attempt(
            error_id="err-12345678",
            action_taken="Applied workaround",
            code_changes="try-except block",
            successful=False,  # Don't trigger causal chain creation
        )

        assert mock_db.conn.execute.called

    @pytest.mark.asyncio
    async def test_query_similar_failures_validates_limit(self, tracker: CausalChainTracker) -> None:
        """Test query_similar_failures rejects invalid limits."""
        with pytest.raises(ValueError, match="limit must be an integer"):
            await tracker.query_similar_failures("some error", limit=0)

        with pytest.raises(ValueError, match="limit must be an integer"):
            await tracker.query_similar_failures("some error", limit=-1)

        with pytest.raises(ValueError, match="limit must be an integer"):
            await tracker.query_similar_failures("some error", limit=101)

    @pytest.mark.asyncio
    async def test_query_similar_failures_no_db_connection(self, tracker: CausalChainTracker) -> None:
        """Test query_similar_failures returns empty when no DB."""
        tracker.db = None

        result = await tracker.query_similar_failures("some error")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_causal_chain_no_db(self, tracker: CausalChainTracker) -> None:
        """Test get_causal_chain returns None when no DB."""
        tracker.db = None

        result = await tracker.get_causal_chain("chain-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_embedding_cache_avoids_redundant_calls(self, tracker: CausalChainTracker) -> None:
        """Test embedding cache stores and reuses embeddings."""
        test_text = "Test error for caching"

        # Directly test the cache logic by calling _generate_embedding twice
        result1 = await tracker._generate_embedding(test_text)
        assert test_text in tracker._embedding_cache
        result2 = await tracker._generate_embedding(test_text)
        assert result1 == result2

    def test_tracker_initializes_with_logger(self) -> None:
        """Test tracker accepts optional logger."""
        import logging

        custom_logger = logging.getLogger("test")
        tracker = CausalChainTracker(logger=custom_logger)

        assert tracker.logger is custom_logger
