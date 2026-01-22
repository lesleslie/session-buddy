"""Query rewriting hooks integration for Session Buddy (Phase 2).

This module integrates the QueryRewriter with the hooks system to automatically
rewrite ambiguous queries before search operations execute.

Integration Flow:
    PRE_SEARCH_QUERY hook → QueryRewriter.rewrite_query() → Modified search context
                                                      ↓
                            Original query expanded with context
                                                      ↓
                           Better search results with resolved pronouns

Usage:
    >>> from session_buddy.rewriting import initialize_query_rewriting_hooks
    >>> hooks_manager = HooksManager()
    >>> await initialize_query_rewriting_hooks(hooks_manager)
    >>> # Now all search queries will be automatically rewritten
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_buddy.core.hooks import Hook, HookContext, HooksManager, HookType
    from session_buddy.rewriting.query_rewriter import QueryRewriter, RewriteContext

logger = logging.getLogger(__name__)


async def initialize_query_rewriting_hooks(
    hooks_manager: HooksManager,
    rewriter: QueryRewriter | None = None,
) -> None:
    """Initialize query rewriting hooks in the hooks manager.

    This function registers hooks that automatically rewrite queries before
    search operations execute, improving search quality by resolving
    ambiguous references (pronouns, demonstratives, temporal references).

    Args:
        hooks_manager: The hooks manager to register hooks with
        rewriter: Optional QueryRewriter instance (creates new one if None)

    The registered hooks:
        - query_rewriting_hook (priority: 100): Rewrites ambiguous queries before search
    """
    if rewriter is None:
        rewriter = QueryRewriter()

    async def _handler_wrapper(ctx: Any) -> Any:
        return await _query_rewriting_handler(ctx, rewriter)

    # Register query rewriting hook
    await hooks_manager.register_hook(
        Hook(
            name="query_rewriting",
            hook_type=HookType.PRE_SEARCH_QUERY,
            priority=100,  # Run before search but after other preprocessing
            handler=_handler_wrapper,
            metadata={"module": "query_rewriting", "version": "1.0"},
        )
    )

    logger.info("Query rewriting hooks registered successfully")


async def _query_rewriting_handler(
    context: HookContext,
    rewriter: QueryRewriter,
) -> Any:
    """Handler for query rewriting hook.

    This handler:
    1. Extracts the original query from context metadata
    2. Detects if the query is ambiguous
    3. Rewrites the query with context if needed
    4. Updates the context with the rewritten query

    Args:
        context: Hook context containing original query in metadata
        rewriter: QueryRewriter instance to use for rewriting

    Returns:
        HookResult with modified_context containing rewritten query
    """
    try:
        # Extract original query from context
        original_query = context.metadata.get("query", "")
        if not original_query:
            # No query to rewrite, skip
            from session_buddy.core.hooks import HookResult

            return HookResult(success=True)

        # Build rewrite context
        rewrite_context = RewriteContext(
            query=original_query,
            recent_conversations=context.metadata.get("recent_conversations", []),
            project=context.metadata.get("project"),
            recent_files=context.metadata.get("recent_files", []),
            session_context=context.metadata,
        )

        # Rewrite query
        rewrite_result = await rewriter.rewrite_query(
            query=original_query,
            context=rewrite_context,
            force_rewrite=False,
        )

        # Update context with rewritten query if it was modified
        if rewrite_result.was_rewritten:
            from session_buddy.core.hooks import HookResult

            logger.info(
                "Query rewritten: '%s' → '%s' (confidence: %.2f, cache_hit: %s)",
                original_query[:50],
                rewrite_result.rewritten_query[:50],
                rewrite_result.confidence,
                rewrite_result.cache_hit,
            )

            return HookResult(
                success=True,
                modified_context={
                    "query": rewrite_result.rewritten_query,
                    "original_query": original_query,
                    "rewrite_confidence": rewrite_result.confidence,
                    "rewrite_cache_hit": rewrite_result.cache_hit,
                },
            )

        else:
            # Query was clear, no rewrite needed
            from session_buddy.core.hooks import HookResult

            return HookResult(success=True)

    except Exception as e:
        logger.error(f"Query rewriting hook failed: {e}", exc_info=True)
        # Don't fail the search if rewriting fails
        from session_buddy.core.hooks import HookResult

        return HookResult(success=True, error=str(e))
