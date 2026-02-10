"""MCP tools for conversation storage and retrieval.

This module provides tools for manually storing conversations and
retrieving conversation statistics from the reflection database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Import conversation storage utilities
from session_buddy.core.conversation_storage import (
    get_conversation_stats,
)
from session_buddy.di import get_sync_typed
from session_buddy.utils.error_management import _get_logger


def register_conversation_tools(mcp_server: FastMCP) -> None:
    """Register all conversation storage tools with the MCP server."""

    @mcp_server.tool()
    async def store_conversation(
        content: str,
        project: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Manually store a conversation with embedding support.

        Args:
            content: Conversation text content to store
            project: Optional project identifier (defaults to current project)
            metadata: Optional metadata dictionary (tags, source, etc.)

        Returns:
            Storage result with conversation ID

        Example:
            >>> result = await store_conversation(
            ...     "Discussion about database architecture",
            ...     project="session-buddy",
            ...     metadata={"topic": "architecture"}
            ... )
        """
        logger = _get_logger()

        try:
            from pathlib import Path

            from session_buddy.reflection.database import ReflectionDatabase

            # Auto-detect project if not provided
            if not project:
                project = Path.cwd().name

            # Build metadata
            conversation_metadata: dict[str, Any] = {
                "project": project,
                "source": "manual_storage",
                "timestamp": None,  # Will be set by database
            }

            if metadata:
                conversation_metadata.update(metadata)

            # Validate content length
            if len(content) < 10:
                return "❌ Content too short (minimum 10 characters)"

            # Store conversation
            async with ReflectionDatabase() as db:
                conversation_id = await db.store_conversation(
                    content=content,
                    metadata=conversation_metadata,
                )

                logger.info(
                    "Manually stored conversation, project=%s, conversation_id=%s, length=%d",
                    project,
                    conversation_id,
                    len(content),
                )

                return f"""✅ Conversation stored successfully!

📝 Conversation ID: {conversation_id}
📁 Project: {project}
📏 Content length: {len(content)} characters
🔍 Searchable: Yes (with embeddings)

The conversation is now available for semantic search."""

        except Exception as e:
            logger.exception("Failed to store conversation")
            return f"❌ Failed to store conversation: {e}"

    @mcp_server.tool()
    async def store_conversation_checkpoint(
        checkpoint_type: str = "manual",
        quality_score: int | None = None,
    ) -> str:
        """Store a conversation checkpoint from current session context.

        This tool captures the current session context and stores it as a
        conversation checkpoint with full embedding support.

        Args:
            checkpoint_type: Type of checkpoint (manual, checkpoint, session_end)
            quality_score: Optional quality score to include

        Returns:
            Storage result with conversation ID

        Example:
            >>> result = await store_conversation_checkpoint(
            ...     checkpoint_type="manual",
            ...     quality_score=85
            ... )
        """
        logger = _get_logger()

        try:
            from session_buddy.core.session_manager import SessionLifecycleManager

            # Get session manager
            manager = get_sync_typed(SessionLifecycleManager)

            # Store conversation checkpoint
            result = await store_conversation_checkpoint(
                manager=manager,
                checkpoint_type=checkpoint_type,
                quality_score=quality_score,
                is_manual=True,
            )

            if result["success"]:
                return f"""✅ Conversation checkpoint stored successfully!

📝 Conversation ID: {result["conversation_id"]}
📁 Project: {manager.current_project or "Unknown"}
🏷️  Checkpoint type: {checkpoint_type}
📊 Quality score: {quality_score or "N/A"}

The conversation checkpoint is now available for semantic search."""
            else:
                error = result.get("error", "Unknown error")
                return f"❌ Failed to store conversation checkpoint: {error}"

        except Exception as e:
            logger.exception("Failed to store conversation checkpoint")
            return f"❌ Failed to store conversation checkpoint: {e}"

    @mcp_server.tool()
    async def get_conversation_statistics() -> str:
        """Get statistics about stored conversations.

        Returns comprehensive statistics including:
        - Total conversations stored
        - Embedding coverage percentage
        - Recent conversations (last 7 days)
        - Projects with conversations

        Returns:
            Formatted statistics report

        Example:
            >>> stats = await get_conversation_statistics()
        """
        logger = _get_logger()

        try:
            # Get statistics
            stats = await get_conversation_stats()

            if stats.get("error"):
                return f"❌ Failed to get statistics: {stats['error']}"

            # Format output
            lines = [
                "📊 Conversation Storage Statistics",
                "=" * 50,
                "",
                f"📝 Total conversations: {stats['total_conversations']:,}",
                f"🤖 With embeddings: {stats['with_embeddings']:,}",
                f"📈 Embedding coverage: {stats['embedding_coverage']:.1f}%",
                f"🕐 Recent (7 days): {stats['recent_conversations']:,}",
            ]

            if stats["projects"]:
                lines.extend(
                    (
                        "",
                        "📁 Projects with conversations:",
                    )
                )
                for project in sorted(stats["projects"]):
                    lines.append(f"   • {project}")

            if stats["total_conversations"] == 0:
                lines.extend(
                    (
                        "",
                        "💡 Tip: Use `/checkpoint` to store conversations automatically",
                        "   or use `store_conversation` to manually store conversations.",
                    )
                )

            return "\n".join(lines)

        except Exception as e:
            logger.exception("Failed to get conversation statistics")
            return f"❌ Failed to get statistics: {e}"

    @mcp_server.tool()
    async def search_conversations(
        query: str,
        limit: int = 10,
        min_score: float = 0.7,
        project: str | None = None,
    ) -> str:
        """Search conversations by semantic similarity.

        Uses vector embeddings to find semantically similar conversations.
        Falls back to text search if embeddings are not available.

        Args:
            query: Search query text
            limit: Maximum number of results (default: 10)
            min_score: Minimum similarity score 0-1 (default: 0.7)
            project: Optional project filter

        Returns:
            Formatted search results

        Example:
            >>> results = await search_conversations(
            ...     "database architecture",
            ...     limit=5,
            ...     project="session-buddy"
            ... )
        """
        logger = _get_logger()

        try:
            from session_buddy.reflection.database import ReflectionDatabase

            # Validate inputs
            if not query.strip():
                return "❌ Query cannot be empty"

            if limit < 1 or limit > 100:
                return "❌ Limit must be between 1 and 100"

            if min_score < 0 or min_score > 1:
                return "❌ Minimum score must be between 0 and 1"

            # Search conversations
            async with ReflectionDatabase() as db:
                results = await db.search_conversations(
                    query=query,
                    limit=limit,
                    min_score=min_score,
                    project=project,
                )

            if not results:
                return f"""🔍 No conversations found matching: "{query}"

💡 Tips:
   - Try a different search query
   - Lower the minimum score (current: {min_score})
   - Remove project filter if set
   - Store more conversations using `/checkpoint`"""

            # Format results
            lines = [
                f"🔍 Search Results for: '{query}'",
                "=" * 50,
                f"Found {len(results)} conversations",
                "",
            ]

            for i, result in enumerate(results, 1):
                score_pct = result.get("score", 0) * 100
                lines.append(f"{i}. Score: {score_pct:.1f}%")

                if project := result.get("project"):
                    lines.append(f"   📁 Project: {project}")

                if timestamp := result.get("timestamp"):
                    lines.append(f"   🕐 {timestamp}")

                # Truncate content for display
                content = result.get("content", "")
                preview = content[:200] + "..." if len(content) > 200 else content
                lines.append(f"   📝 {preview}")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.exception("Failed to search conversations")
            return f"❌ Search failed: {e}"
