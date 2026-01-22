"""Causal chain tracking for debugging intelligence.

This module implements a sophisticated error tracking system that:
- Records error events with semantic embeddings
- Tracks fix attempts and their outcomes
- Maintains complete error→attempt→solution chains
- Enables semantic search for similar past failures
- Provides debugging intelligence from historical patterns

Architecture:
    ErrorEvent → FixAttempt → CausalChain → CausalChainTracker
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter_oneiric import (
        ReflectionDatabaseAdapterOneiric,
    )


@dataclass
class ErrorEvent:
    """An error that occurred during development.

    Attributes:
        id: Unique error identifier
        error_message: The error message/text
        error_type: Type/category of error (e.g., "TypeError", "ImportError")
        context: Additional context (file, line number, code snippet, etc.)
        timestamp: When the error occurred
        session_id: Session where error occurred
        embedding: Semantic vector for similarity search (384-dim)
    """

    id: str
    error_message: str
    error_type: str
    context: dict[str, Any]
    timestamp: datetime
    session_id: str
    embedding: list[float] | None = None


@dataclass
class FixAttempt:
    """An attempt to fix an error.

    Attributes:
        id: Unique attempt identifier
        error_id: Reference to error being fixed
        action_taken: Description of fix attempt
        code_changes: Optional code changes made
        successful: Whether this attempt resolved the error
        timestamp: When attempt was made
    """

    id: str
    error_id: str
    action_taken: str
    code_changes: str | None = None
    successful: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CausalChain:
    """Complete error→attempts→solution chain.

    Attributes:
        id: Unique chain identifier
        error_event: The original error
        fix_attempts: All fix attempts (including failed ones)
        successful_fix: The fix that worked (if any)
        resolution_time_minutes: Time from error to resolution
    """

    id: str
    error_event: ErrorEvent
    fix_attempts: list[FixAttempt]
    successful_fix: FixAttempt | None = None
    resolution_time_minutes: float | None = None


class CausalChainTracker:
    """Track failure→fix patterns for debugging assistance.

    This tracker provides:
        - Error event recording with semantic embeddings
        - Fix attempt tracking with success/failure
        - Complete causal chain construction
        - Semantic search for similar past errors
        - Debugging intelligence from historical patterns

    Usage:
        >>> tracker = CausalChainTracker()
        >>> await tracker.initialize()
        >>> error_id = await tracker.record_error_event(
        ...     error="ImportError: module not found",
        ...     context={"file": "main.py"},
        ...     session_id="session-123"
        ... )
        >>> fix_id = await tracker.record_fix_attempt(
        ...     error_id=error_id,
        ...     action_taken="Added missing import",
        ...     successful=True
        ... )
        >>> similar = await tracker.query_similar_failures(
        ...     current_error="ImportError in main.py"
        ... )
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize causal chain tracker.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.db: ReflectionDatabaseAdapterOneiric | None = None
        self._embedding_cache: dict[str, list[float]] = {}

    async def initialize(self) -> None:
        """Initialize causal chain storage.

        Creates necessary database tables if they don't exist.
        """
        # Import here to avoid circular dependency
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )
        from session_buddy.di import depends

        self.db = depends.get_sync(ReflectionDatabaseAdapterOneiric)
        await self._ensure_tables()

        self.logger.info("CausalChainTracker initialized")

    async def _ensure_tables(self) -> None:
        """Create causal chain tables.

        Three tables work together:
            1. causal_error_events: Records of errors with embeddings
            2. causal_fix_attempts: Fix attempts linked to errors
            3. causal_chains: Completed chains linking errors to solutions
        """
        if not self.db or not self.db.conn:
            self.logger.warning(
                "No database connection available for causal chain tables"
            )
            return

        # Error events table with vector embeddings
        await self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS causal_error_events (
                id TEXT PRIMARY KEY,
                error_message TEXT,
                error_type TEXT,
                context JSON,
                timestamp TIMESTAMP,
                session_id TEXT,
                embedding FLOAT[384]
            )
        """
        )

        # Fix attempts table
        await self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS causal_fix_attempts (
                id TEXT PRIMARY KEY,
                error_id TEXT,
                action_taken TEXT,
                code_changes TEXT,
                successful BOOLEAN,
                timestamp TIMESTAMP,
                FOREIGN KEY (error_id) REFERENCES causal_error_events(id)
            )
        """
        )

        # Completed causal chains table
        await self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS causal_chains (
                id TEXT PRIMARY KEY,
                error_id TEXT,
                successful_fix_id TEXT,
                resolution_time_minutes FLOAT,
                created_at TIMESTAMP,
                FOREIGN KEY (error_id) REFERENCES causal_error_events(id),
                FOREIGN KEY (successful_fix_id) REFERENCES causal_fix_attempts(id)
            )
        """
        )

        # Index for semantic search
        await self.db.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_causal_error_events_embeddings
            ON causal_error_events USING HNSW (embedding)
            WITH (metric = 'cosine', M = 16, ef_construction = 200)
        """
        )

        self.logger.info("Causal chain tables created")

    async def record_error_event(
        self,
        error: str,
        context: dict[str, Any],
        session_id: str,
    ) -> str:
        """Record an error event.

        Generates semantic embedding for the error message to enable
        similarity search for past debugging patterns.

        Args:
            error: Error message or description
            context: Additional context (file, line, code, etc.)
            session_id: Current session identifier

        Returns:
            Error event ID (format: err-XXXXXXXX)
        """
        error_id = f"err-{uuid.uuid4().hex[:8]}"

        # Generate embedding for semantic search
        embedding = await self._generate_embedding(error)

        # Store in database
        if self.db and self.db.conn:
            await self.db.conn.execute(
                """
                INSERT INTO causal_error_events
                (id, error_message, error_type, context, timestamp, session_id, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    error_id,
                    error,
                    context.get("error_type", "unknown"),
                    json.dumps(context),
                    datetime.now(),
                    session_id,
                    embedding,
                ),
            )

        self.logger.info(
            "Recorded error event: id=%s, error_type=%s, session=%s",
            error_id,
            context.get("error_type", "unknown"),
            session_id,
        )

        return error_id

    async def record_fix_attempt(
        self,
        error_id: str,
        action_taken: str,
        code_changes: str | None = None,
        successful: bool = False,
    ) -> str:
        """Record a fix attempt.

        Args:
            error_id: Error event being fixed
            action_taken: Description of fix attempt
            code_changes: Optional code changes made
            successful: Whether this fix resolved the error

        Returns:
            Fix attempt ID (format: fix-XXXXXXXX)

        Note:
            If successful=True, automatically creates a causal chain
        """
        attempt_id = f"fix-{uuid.uuid4().hex[:8]}"

        # Store in database
        if self.db and self.db.conn:
            await self.db.conn.execute(
                """
                INSERT INTO causal_fix_attempts
                (id, error_id, action_taken, code_changes, successful, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    attempt_id,
                    error_id,
                    action_taken,
                    code_changes,
                    successful,
                    datetime.now(),
                ),
            )

            # If successful, create causal chain
            if successful:
                await self._create_causal_chain(error_id, attempt_id)

        self.logger.info(
            "Recorded fix attempt: id=%s, error_id=%s, successful=%s",
            attempt_id,
            error_id,
            successful,
        )

        return attempt_id

    async def _create_causal_chain(self, error_id: str, successful_fix_id: str) -> str:
        """Create completed causal chain.

        Calculates resolution time from error to successful fix.

        Args:
            error_id: Original error event ID
            successful_fix_id: Successful fix attempt ID

        Returns:
            Causal chain ID (format: chain-XXXXXXXX)
        """
        if not self.db or not self.db.conn:
            return ""

        # Get timestamps to calculate resolution time
        error_result = await self.db.conn.execute(
            """
            SELECT timestamp FROM causal_error_events WHERE id = ?
        """,
            (error_id,),
        ).fetchone()

        fix_result = await self.db.conn.execute(
            """
            SELECT timestamp FROM causal_fix_attempts WHERE id = ?
        """,
            (successful_fix_id,),
        ).fetchone()

        if not error_result or not fix_result:
            self.logger.error(
                "Could not create causal chain: error_id=%s, fix_id=%s",
                error_id,
                successful_fix_id,
            )
            return ""

        error_time, fix_time = error_result[0], fix_result[0]
        resolution_time = (fix_time - error_time).total_seconds() / 60

        # Store causal chain
        chain_id = f"chain-{uuid.uuid4().hex[:8]}"
        await self.db.conn.execute(
            """
            INSERT INTO causal_chains
            (id, error_id, successful_fix_id, resolution_time_minutes, created_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (chain_id, error_id, successful_fix_id, resolution_time, datetime.now()),
        )

        self.logger.info(
            "Created causal chain: id=%s, resolution_time=%.2fmin",
            chain_id,
            resolution_time,
        )

        return chain_id

    async def query_similar_failures(
        self, current_error: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Find past failures similar to current error.

        Uses semantic search on error embeddings to find historically
        similar errors and their successful fixes.

        Args:
            current_error: Current error message
            limit: Maximum number of similar failures to return (1-100)

        Returns:
            List of similar failure chains with context
        """
        # Validate limit to prevent DoS
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")

        if not self.db or not self.db.conn:
            self.logger.warning("No database connection for similarity search")
            return []

        # Generate embedding for current error
        query_embedding = await self._generate_embedding(current_error)

        # Semantic search on past errors
        results = await self.db.conn.execute(
            """
            SELECT
                e.id,
                e.error_message,
                e.context,
                c.successful_fix_id,
                f.action_taken,
                f.code_changes,
                c.resolution_time_minutes,
                array_cosine_similarity(e.embedding, ?::FLOAT[384]) as similarity
            FROM causal_error_events e
            JOIN causal_chains c ON e.id = c.error_id
            JOIN causal_fix_attempts f ON c.successful_fix_id = f.id
            WHERE similarity > 0.7
            ORDER BY similarity DESC, c.resolution_time_minutes ASC
            LIMIT ?
        """,
            (query_embedding, limit),
        ).fetchall()

        similar_failures = [
            {
                "error_id": row[0],
                "error_message": row[1],
                "context": json.loads(row[2]) if row[2] else {},
                "successful_fix": {
                    "action_taken": row[4],
                    "code_changes": row[5],
                },
                "resolution_time_minutes": row[6],
                "similarity": row[7],
            }
            for row in results
        ]

        self.logger.info(
            "Found %d similar failures for error: %s",
            len(similar_failures),
            current_error[:100],
        )

        return similar_failures

    async def get_causal_chain(self, chain_id: str) -> CausalChain | None:
        """Get complete causal chain by ID.

        Args:
            chain_id: Causal chain identifier

        Returns:
            Complete CausalChain with error, attempts, and resolution,
            or None if not found
        """
        if not self.db or not self.db.conn:
            return None

        # Query error event
        error_row = await self.db.conn.execute(
            """
            SELECT id, error_message, error_type, context, timestamp, session_id
            FROM causal_error_events
            WHERE id IN (SELECT error_id FROM causal_chains WHERE id = ?)
        """,
            (chain_id,),
        ).fetchone()

        if not error_row:
            return None

        error_event = ErrorEvent(
            id=error_row[0],
            error_message=error_row[1],
            error_type=error_row[2],
            context=json.loads(error_row[3]) if error_row[3] else {},
            timestamp=error_row[4],
            session_id=error_row[5],
        )

        # Query all fix attempts
        attempts_rows = await self.db.conn.execute(
            """
            SELECT id, error_id, action_taken, code_changes, successful, timestamp
            FROM causal_fix_attempts
            WHERE error_id = ?
            ORDER BY timestamp ASC
        """,
            (error_event.id,),
        ).fetchall()

        fix_attempts = [
            FixAttempt(
                id=row[0],
                error_id=row[1],
                action_taken=row[2],
                code_changes=row[3],
                successful=row[4],
                timestamp=row[5],
            )
            for row in attempts_rows
        ]

        # Find successful fix
        successful_fix = next((a for a in fix_attempts if a.successful), None)

        # Calculate resolution time
        resolution_time = None
        if successful_fix:
            resolution_time = (
                successful_fix.timestamp - error_event.timestamp
            ).total_seconds() / 60

        return CausalChain(
            id=chain_id,
            error_event=error_event,
            fix_attempts=fix_attempts,
            successful_fix=successful_fix,
            resolution_time_minutes=resolution_time,
        )

    async def _generate_embedding(self, text: str) -> list[float]:
        """Generate semantic embedding for text.

        Uses cached embeddings if available to avoid recomputation.
        Delegates to reflection_tools for actual embedding generation.

        Args:
            text: Text to embed

        Returns:
            384-dimensional embedding vector
        """
        # Check cache first
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        # Import here to avoid circular dependency
        from session_buddy.reflection_tools import generate_embedding

        embedding = await generate_embedding(text)

        # Cache for future use
        self._embedding_cache[text] = embedding

        return embedding  # type: ignore[no-any-return]
