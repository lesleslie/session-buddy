"""Query rewriting system for Session Buddy (Phase 2).

This package provides intelligent query expansion using LLM to resolve
ambiguous queries with pronoun resolution and contextual information.

Components:
    QueryRewriter: LLM-powered query expansion
    AmbiguityDetector: Pattern-based ambiguity detection
    Hooks Integration: Automatic query rewriting before search

Usage:
    >>> from session_buddy.rewriting import QueryRewriter, AmbiguityDetector
    >>> detector = AmbiguityDetector()
    >>> rewriter = QueryRewriter()
    >>> detection = detector.detect_ambiguity("what did I learn?")
    >>> if detection.is_ambiguous:
    ...     result = await rewriter.rewrite_query(query, context)
"""

from __future__ import annotations

from session_buddy.rewriting.hooks_integration import (
    initialize_query_rewriting_hooks,
)
from session_buddy.rewriting.query_rewriter import (
    AmbiguityDetector,
    AmbiguityType,
    QueryRewriter,
    QueryRewriteResult,
    RewriteContext,
)

__all__ = [
    "AmbiguityDetector",
    "AmbiguityType",
    "QueryRewriter",
    "QueryRewriteResult",
    "RewriteContext",
    "initialize_query_rewriting_hooks",
]
