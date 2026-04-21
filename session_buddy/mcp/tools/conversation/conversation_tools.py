from typing import Any


@mcp_server.tool()
async def _store_conversation_impl(
    content: str,
    project: str | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    _get_logger=None,
    ReflectionDatabase=None,
) -> str:
    """Manually store a conversation with embedding support."""
    logger = _get_logger()
    try:
        from pathlib import Path

        from session_buddy.reflection.database import ReflectionDatabase

        if not project:
            project = Path.cwd().name
        conversation_metadata: dict[str, Any] = {
            "project": project,
            "source": "manual_storage",
            "timestamp": None,
        }
        if metadata:
            conversation_metadata.update(metadata)
        if len(content) < 10:
            return "❌ Content too short (minimum 10 characters)"
        async with ReflectionDatabase() as db:
            conversation_id = await db.store_conversation(
                content=content, metadata=conversation_metadata
            )
            logger.info(
                "Manually stored conversation, project=%s, conversation_id=%s, length=%d",
                project,
                conversation_id,
                len(content),
            )
            return f"✅ Conversation stored successfully!\n\n📝 Conversation ID: {conversation_id}\n📁 Project: {project}\n📏 Content length: {len(content)} characters\n🔍 Searchable: Yes (with embeddings)\n\nThe conversation is now available for semantic search."
    except Exception as e:
        logger.exception("Failed to store conversation")
        return f"❌ Failed to store conversation: {e}"


@mcp_server.tool()
async def _store_conversation_checkpoint_impl(
    checkpoint_type: str = "manual",
    quality_score: int | None = None,
    *,
    SessionLifecycleManager=None,
    _get_logger=None,
    store_conversation_checkpoint_helper=None,
    get_sync_typed=None,
) -> str:
    """Store a conversation checkpoint from current session context."""
    logger = _get_logger()
    try:
        from session_buddy.core.session_manager import SessionLifecycleManager

        manager = get_sync_typed(SessionLifecycleManager)
        result = await store_conversation_checkpoint_helper(
            manager=manager,
            checkpoint_type=checkpoint_type,
            quality_score=quality_score,
            is_manual=True,
        )
        if result["success"]:
            return f"✅ Conversation checkpoint stored successfully!\n\n📝 Conversation ID: {result['conversation_id']}\n📁 Project: {manager.current_project or 'Unknown'}\n🏷️  Checkpoint type: {checkpoint_type}\n📊 Quality score: {quality_score or 'N/A'}\n\nThe conversation checkpoint is now available for semantic search."
        else:
            error = result.get("error", "Unknown error")
            return f"❌ Failed to store conversation checkpoint: {error}"
    except Exception as e:
        logger.exception("Failed to store conversation checkpoint")
        return f"❌ Failed to store conversation checkpoint: {e}"


@mcp_server.tool()
async def _get_conversation_statistics_impl(
    *, sorted=None, _get_logger=None, get_conversation_stats=None
) -> str:
    """Get statistics about stored conversations."""
    logger = _get_logger()
    try:
        stats = await get_conversation_stats()
        if stats.get("error"):
            return f"❌ Failed to get statistics: {stats['error']}"
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
            lines.extend(("", "📁 Projects with conversations:"))
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
async def _search_conversations_impl(
    query: str,
    limit: int = 10,
    min_score: float = 0.7,
    project: str | None = None,
    *,
    _get_logger=None,
    ReflectionDatabase=None,
) -> str:
    """Search conversations by semantic similarity."""
    logger = _get_logger()
    try:
        from session_buddy.reflection.database import ReflectionDatabase

        if not query.strip():
            return "❌ Query cannot be empty"
        if limit < 1 or limit > 100:
            return "❌ Limit must be between 1 and 100"
        if min_score < 0 or min_score > 1:
            return "❌ Minimum score must be between 0 and 1"
        async with ReflectionDatabase() as db:
            results = await db.search_conversations(
                query=query, limit=limit, min_score=min_score, project=project
            )
        if not results:
            return f'🔍 No conversations found matching: "{query}"\n\n💡 Tips:\n   - Try a different search query\n   - Lower the minimum score (current: {min_score})\n   - Remove project filter if set\n   - Store more conversations using `/checkpoint`'
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
            content = result.get("content", "")
            preview = content[:200] + "..." if len(content) > 200 else content
            lines.append(f"   📝 {preview}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Failed to search conversations")
        return f"❌ Search failed: {e}"


def _register_conversation_tools_impl(mcp_server: FastMCP) -> None:
    """Register all conversation storage tools with the MCP server."""

    @mcp_server.tool()
    @mcp_server.tool()
    async def store_conversation(
        content: str, project: str | None = None, metadata: dict[str, Any] | None = None
    ) -> str:
        return await _store_conversation_impl(
            content,
            project,
            metadata,
            _get_logger=_get_logger,
            ReflectionDatabase=ReflectionDatabase,
        )

    @mcp_server.tool()
    @mcp_server.tool()
    async def store_conversation_checkpoint(
        checkpoint_type: str = "manual", quality_score: int | None = None
    ) -> str:
        return await _store_conversation_checkpoint_impl(
            checkpoint_type,
            quality_score,
            SessionLifecycleManager=SessionLifecycleManager,
            _get_logger=_get_logger,
            store_conversation_checkpoint_helper=store_conversation_checkpoint_helper,
            get_sync_typed=get_sync_typed,
        )

    @mcp_server.tool()
    @mcp_server.tool()
    async def get_conversation_statistics() -> str:
        return await _get_conversation_statistics_impl(
            sorted=sorted,
            _get_logger=_get_logger,
            get_conversation_stats=get_conversation_stats,
        )

    @mcp_server.tool()
    @mcp_server.tool()
    async def search_conversations(
        query: str, limit: int = 10, min_score: float = 0.7, project: str | None = None
    ) -> str:
        return await _search_conversations_impl(
            query,
            limit,
            min_score,
            project,
            _get_logger=_get_logger,
            ReflectionDatabase=ReflectionDatabase,
        )
