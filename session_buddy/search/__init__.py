"""Progressive Search system for Session Buddy (Phase 3).

This package provides multi-tier search with early stopping to optimize search
performance by searching faster data sources first and stopping when sufficient results
are found.

Architecture:
    CATEGORIES → INSIGHTS → REFLECTIONS → CONVERSATIONS
         ↓              ↓            ↓             ↓
    Fastest         Faster        Slower        Slowest

Usage:
    >>> from session_buddy.search import ProgressiveSearchEngine
    >>> engine = ProgressiveSearchEngine()
    >>> result = await engine.search_progressive(
    ...     query="async patterns",
    ...     project="session-buddy",
    ...     max_tiers=4
    ... )
    >>> print(f"Searched {len(result.tiers_searched)} tiers, found {result.total_results} results")
"""

from __future__ import annotations

from session_buddy.search.progressive_search import (
    ProgressiveSearchEngine,
    ProgressiveSearchResult,
    SearchTier,
    SufficiencyConfig,
    SufficiencyEvaluator,
    TierSearchResult,
)

__all__ = [
    "ProgressiveSearchEngine",
    "SearchTier",
    "SufficiencyConfig",
    "SufficiencyEvaluator",
    "TierSearchResult",
    "ProgressiveSearchResult",
]
