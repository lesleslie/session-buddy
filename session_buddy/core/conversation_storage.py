"""Conversation storage utilities for Session Buddy.

This module provides utilities for capturing and storing conversation context
during checkpoints and session end operations.
"""

from __future__ import annotations

import logging
import typing as t
from datetime import datetime

from session_buddy.core.session_manager import SessionLifecycleManager


def get_conversation_logger() -> logging.Logger:
    """Get the conversation storage logger instance.

    This function is used in tests for mocking purposes.
    """
    return logging.getLogger(__name__)


async def capture_conversation_context(
    manager: SessionLifecycleManager,
    checkpoint_type: str = "checkpoint",
    quality_score: int | None = None,
    metadata: dict[str, t.Any] | None = None,
) -> str:
    """Capture conversation context from the current session.

    This function captures comprehensive conversation context including:
    1. Session context (if available)
    2. Quality scores and history
    3. Project information
    4. Session metadata
    5. Timestamp and checkpoint type

    Args:
        manager: SessionLifecycleManager instance
        checkpoint_type: Type of checkpoint (checkpoint, session_end, manual)
        quality_score: Current quality score (optional)
        metadata: Additional metadata to include (optional)

    Returns:
        Formatted conversation text for storage

    Example:
        >>> manager = SessionLifecycleManager()
        >>> context = await capture_conversation_context(
        ...     manager,
        ...     checkpoint_type="checkpoint",
        ...     quality_score=85
        ... )
    """
    get_conversation_logger()
    lines: list[str] = []

    # Header
    lines.append(f"# Conversation Context: {checkpoint_type.upper()}")
    lines.append(f"Project: {manager.current_project or 'Unknown'}")
    lines.append(f"Timestamp: {datetime.now().isoformat()}")

    if quality_score is not None:
        lines.append(f"Quality Score: {quality_score}/100")

    lines.append("")

    # Quality history if available
    if manager.current_project and manager._quality_history.get(
        manager.current_project
    ):
        scores = manager._quality_history[manager.current_project]
        if scores:
            lines.append("## Quality History")
            lines.append(f"Recent scores: {', '.join(map(str, scores[-5:]))}")
            if len(scores) > 1:
                trend = "improving" if scores[-1] > scores[0] else "stable"
                lines.append(f"Trend: {trend}")
            lines.append("")

    # Session context if available
    if manager.session_context:
        lines.append("## Session Context")
        for key, value in manager.session_context.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"{key}: {value}")
            elif isinstance(value, list):
                lines.append(f"{key}: {len(value)} items")
            elif isinstance(value, dict):
                lines.append(f"{key}: {len(value)} keys")
        lines.append("")

    # Additional metadata
    if metadata:
        lines.append("## Metadata")
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"{key}: {value}")
        lines.append("")

    return "\n".join(lines)


async def store_conversation_checkpoint(
    manager: SessionLifecycleManager,
    checkpoint_type: str = "checkpoint",
    quality_score: int | None = None,
    is_manual: bool = False,
) -> dict[str, t.Any]:
    """Store conversation checkpoint to the reflection database.

    This function captures the current conversation context and stores it
    in the reflection database with full embedding support for semantic search.

    Args:
        manager: SessionLifecycleManager instance
        checkpoint_type: Type of checkpoint (checkpoint, session_end, manual)
        quality_score: Current quality score (optional)
        is_manual: Whether this was a manually-triggered checkpoint

    Returns:
        Dictionary with storage result:
        - success: bool
        - conversation_id: str | None
        - error: str | None

    Example:
        >>> result = await store_conversation_checkpoint(
        ...     manager,
        ...     checkpoint_type="checkpoint",
        ...     quality_score=85,
        ...     is_manual=True
        ... )
        >>> if result["success"]:
        ...     print(f"Stored: {result['conversation_id']}")
    """
    logger = get_conversation_logger()
    result: dict[str, t.Any] = {
        "success": False,
        "conversation_id": None,
        "error": None,
    }

    try:
        from session_buddy.reflection.database import ReflectionDatabase
        from session_buddy.settings import get_settings

        # Check if conversation storage is enabled
        settings = get_settings()

        # Check for conversation storage settings
        enable_storage = getattr(settings, "enable_conversation_storage", True)

        if not enable_storage:
            logger.debug("Conversation storage disabled in settings")
            result["error"] = "Conversation storage disabled"
            return result

        # Capture conversation context
        conversation_text = await capture_conversation_context(
            manager,
            checkpoint_type=checkpoint_type,
            quality_score=quality_score,
            metadata={"is_manual": is_manual},
        )

        # Build metadata for storage
        conversation_metadata: dict[str, t.Any] = {
            "project": manager.current_project or "unknown",
            "checkpoint_type": checkpoint_type,
            "is_manual": is_manual,
            "quality_score": quality_score,
            "timestamp": datetime.now().isoformat(),
        }

        # Check minimum length requirement
        min_length = getattr(settings, "conversation_storage_min_length", 100)
        if len(conversation_text) < min_length:
            logger.debug(
                "Conversation text too short (%d < %d), skipping storage",
                len(conversation_text),
                min_length,
            )
            result["error"] = f"Conversation text too short (min {min_length} chars)"
            return result

        # Check maximum length requirement (chunking)
        max_length = getattr(settings, "conversation_storage_max_length", 50000)
        if len(conversation_text) > max_length:
            logger.info(
                "Conversation text too long (%d > %d), truncating",
                len(conversation_text),
                max_length,
            )
            conversation_text = conversation_text[:max_length] + "\n... [truncated]"

        # Store conversation to database
        db = ReflectionDatabase()
        await db.initialize()

        try:
            conversation_id = await db.store_conversation(
                content=conversation_text,
                metadata=conversation_metadata,
            )

            result["success"] = True
            result["conversation_id"] = conversation_id

            logger.info(
                "Stored conversation checkpoint, project=%s, checkpoint_type=%s, quality_score=%s, conversation_id=%s",
                manager.current_project,
                checkpoint_type,
                quality_score,
                conversation_id,
            )
        finally:
            db.close()

    except Exception as e:
        logger.warning(
            "Failed to store conversation checkpoint, project=%s, error=%s",
            manager.current_project,
            str(e),
        )
        result["error"] = str(e)

    return result


async def get_conversation_stats() -> dict[str, t.Any]:
    """Get statistics about stored conversations.

    Returns:
        Dictionary with conversation statistics:
        - total_conversations: int
        - with_embeddings: int
        - embedding_coverage: float
        - recent_conversations: int
        - projects: list[str]

    Example:
        >>> stats = await get_conversation_stats()
        >>> print(f"Total: {stats['total_conversations']}")
    """
    logger = get_conversation_logger()
    stats: dict[str, t.Any] = {
        "total_conversations": 0,
        "with_embeddings": 0,
        "embedding_coverage": 0.0,
        "recent_conversations": 0,
        "projects": [],
        "error": None,
    }

    try:
        from session_buddy.reflection.database import ReflectionDatabase

        db = ReflectionDatabase()
        await db.initialize()

        try:
            # Get total count
            stats["total_conversations"] = await db._get_conversation_count()

            if stats["total_conversations"] > 0:
                # Get embedding coverage
                if db.is_temp_db:
                    with db.lock:
                        result = (
                            db._get_conn()
                            .execute(
                                "SELECT COUNT(*) FROM conversations WHERE embedding IS NOT NULL"
                            )
                            .fetchone()
                        )
                        stats["with_embeddings"] = result[0] if result else 0
                else:
                    import asyncio

                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: (
                            db._get_conn()
                            .execute(
                                "SELECT COUNT(*) FROM conversations WHERE embedding IS NOT NULL"
                            )
                            .fetchone()
                        ),
                    )
                    stats["with_embeddings"] = result[0] if result else 0

                # Calculate coverage
                stats["embedding_coverage"] = (
                    (stats["with_embeddings"] / stats["total_conversations"] * 100)
                    if stats["total_conversations"] > 0
                    else 0.0
                )

                # Get recent conversations (last 7 days)
                if db.is_temp_db:
                    with db.lock:
                        result = (
                            db._get_conn()
                            .execute(
                                """SELECT COUNT(*) FROM conversations
                            WHERE timestamp > NOW() - INTERVAL '7 days'"""
                            )
                            .fetchone()
                        )
                        stats["recent_conversations"] = result[0] if result else 0
                else:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: (
                            db._get_conn()
                            .execute(
                                """SELECT COUNT(*) FROM conversations
                            WHERE timestamp > NOW() - INTERVAL '7 days'"""
                            )
                            .fetchone()
                        ),
                    )
                    stats["recent_conversations"] = result[0] if result else 0

                # Get unique projects
                projects_result = await db._execute_query(
                    "SELECT DISTINCT project FROM conversations WHERE project IS NOT NULL"
                )
                stats["projects"] = [
                    row[0] for row in projects_result if row and row[0]
                ]

        finally:
            db.close()

    except Exception as e:
        logger.warning("Failed to get conversation stats: %s", str(e))
        stats["error"] = str(e)

    return stats
