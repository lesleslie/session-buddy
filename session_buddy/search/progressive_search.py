"""Progressive Search system for Session Buddy (Phase 3).

This module implements multi-tier search with early stopping to optimize search
performance by searching faster data sources first and stopping when sufficient results
are found.

Architecture:
    CATEGORIES → INSIGHTS → REFLECTIONS → CONVERSATIONS
         ↓              ↓            ↓             ↓
    Fastest         Faster        Slower        Slowest

Usage:
    >>> from session_buddy.search.progressive_search import ProgressiveSearchEngine
    >>> engine = ProgressiveSearchEngine()
    >>> results = await engine.search_progressive(
    ...     query="async patterns",
    ...     project="session-buddy",
    ...     max_tiers=4
    ... )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

logger = logging.getLogger(__name__)


class SearchTier(str, Enum):
    """Search tiers ordered by speed (fastest to slowest).

    Tiers are searched sequentially, with early stopping when sufficient
    results are found. Each tier has specific data characteristics and
    minimum quality thresholds.
    """

    CATEGORIES = "categories"  # High-quality insights (min_score: 0.9)
    INSIGHTS = "insights"  # Learned skills (min_score: 0.75)
    REFLECTIONS = "reflections"  # Stored reflections
    CONVERSATIONS = "conversations"  # Full conversation search

    @classmethod
    def get_min_score(cls, tier: SearchTier) -> float:
        """Get minimum quality score for a tier.

        Args:
            tier: The search tier

        Returns:
            Minimum score threshold (0.0-1.0)
        """
        min_scores = {
            SearchTier.CATEGORIES: 0.9,
            SearchTier.INSIGHTS: 0.75,
            SearchTier.REFLECTIONS: 0.7,
            SearchTier.CONVERSATIONS: 0.6,
        }
        return min_scores.get(tier, 0.6)

    @classmethod
    def get_max_results(cls, tier: SearchTier) -> int:
        """Get maximum results to return from a tier.

        Args:
            tier: The search tier

        Returns:
            Maximum number of results
        """
        max_results = {
            SearchTier.CATEGORIES: 10,
            SearchTier.INSIGHTS: 15,
            SearchTier.REFLECTIONS: 20,
            SearchTier.CONVERSATIONS: 30,
        }
        return max_results.get(tier, 30)

    @classmethod
    def get_tier_name(cls, tier: SearchTier) -> str:
        """Get human-readable tier name.

        Args:
            tier: The search tier

        Returns:
            Human-readable name
        """
        names = {
            SearchTier.CATEGORIES: "High-quality insights",
            SearchTier.INSIGHTS: "Learned skills",
            SearchTier.REFLECTIONS: "Stored reflections",
            SearchTier.CONVERSATIONS: "Full conversations",
        }
        return names.get(tier, "Unknown")


@dataclass
class TierSearchResult:
    """Results from searching a single tier."""

    tier: SearchTier
    results: list[dict[str, Any]]
    total_found: int
    latency_ms: float
    min_score: float
    max_score: float
    avg_score: float
    searched: bool = True


@dataclass
class ProgressiveSearchResult:
    """Complete progressive search results across all tiers."""

    query: str
    project: str | None
    total_results: int
    tiers_searched: list[SearchTier]
    tier_results: list[TierSearchResult]
    total_latency_ms: float
    early_stop: bool
    search_complete: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SufficiencyConfig:
    """Configuration for result sufficiency evaluation.

    Controls when to stop searching based on result quality and quantity.
    """

    min_results: int = 5  # Minimum results before considering early stop
    high_quality_threshold: float = 0.85  # Avg score to consider results "high quality"
    high_quality_min_count: int = 3  # Min high-quality results for early stop
    perfect_match_threshold: float = 0.95  # Score to consider "perfect match"

    # Progressive search tier limits
    max_tiers: int = 4  # Maximum tiers to search (0-4)
    tier_timeout_ms: float = 5000  # Maximum time per tier (5 seconds)

    # Quality-weighted scoring
    quality_weight: float = 0.7  # Weight for quality score in sufficiency (0.0-1.0)
    quantity_weight: float = 0.3  # Weight for result count in sufficiency (0.0-1.0)


class SufficiencyEvaluator:
    """Evaluates whether search results are sufficient for early stopping.

    The evaluator considers:
    - Result quantity (do we have enough results?)
    - Result quality (are the results highly relevant?)
    - Score distribution (do we have perfect matches?)
    """

    def __init__(self, config: SufficiencyConfig | None = None) -> None:
        """Initialize sufficiency evaluator.

        Args:
            config: Optional configuration for sufficiency evaluation
        """
        self.config = config or SufficiencyConfig()

    def is_sufficient(
        self,
        results: list[dict[str, Any]],
        tier: SearchTier,
    ) -> tuple[bool, str]:
        """Evaluate if results are sufficient for early stopping.

        Args:
            results: Search results from current tier
            tier: Current search tier

        Returns:
            Tuple of (is_sufficient, reason)
        """
        if not results:
            return False, "No results found"

        result_count = len(results)

        # Extract scores
        scores = [
            r.get("score", r.get("similarity", 0.0))
            for r in results
            if "score" in r or "similarity" in r
        ]

        if not scores:
            # Text search results might not have scores
            return (
                result_count >= self.config.min_results,
                f"{result_count} text results found",
            )

        avg_score = sum(scores) / len(scores)

        # Check for perfect matches
        perfect_matches = sum(
            1 for s in scores if s >= self.config.perfect_match_threshold
        )
        if perfect_matches >= 3:
            return (
                True,
                f"Found {perfect_matches} perfect matches (score >={self.config.perfect_match_threshold})",
            )

        # Check for high quality results
        high_quality_count = sum(
            1 for s in scores if s >= self.config.high_quality_threshold
        )
        if (
            result_count >= self.config.min_results
            and high_quality_count >= self.config.high_quality_min_count
            and avg_score >= self.config.high_quality_threshold
        ):
            return (
                True,
                f"Found {high_quality_count} high-quality results (avg score: {avg_score:.2f})",
            )

        # Check tier-specific sufficiency
        min_score = SearchTier.get_min_score(tier)
        if avg_score >= min_score and result_count >= self.config.min_results:
            return (
                True,
                f"Avg score {avg_score:.2f} meets tier minimum {min_score:.2f} with {result_count} results",
            )

        # Not sufficient yet
        return (
            False,
            f"Need more or better results (current: {result_count} results, avg score: {avg_score:.2f})",
        )

    def calculate_sufficiency_score(
        self,
        results: list[dict[str, Any]],
    ) -> float:
        """Calculate sufficiency score (0.0-1.0) for a set of results.

        Higher scores indicate more sufficient results. Considers both quality
        and quantity according to configured weights.

        Args:
            results: Search results

        Returns:
            Sufficiency score (0.0-1.0)
        """
        if not results:
            return 0.0

        result_count = len(results)

        # Extract scores
        scores = []
        for r in results:
            if "score" in r or "similarity" in r:
                score_val = r.get("score", r.get("similarity", 0.0))
                scores.append(score_val)

        if not scores:
            # Text search without scores - base on quantity only
            quantity_score = min(result_count / 10.0, 1.0)  # Max quality at 10 results
            return quantity_score * self.config.quantity_weight

        avg_score = sum(scores) / len(scores)

        # Normalize quantity (0.0-1.0, with diminishing returns)
        quantity_score = min(result_count / 20.0, 1.0)

        # Normalize quality (0.0-1.0)
        quality_score = avg_score

        # Weighted combination
        sufficiency_score = (
            quality_score * self.config.quality_weight
            + quantity_score * self.config.quantity_weight
        )

        return min(sufficiency_score, 1.0)  # type: ignore[no-any-return]


class ProgressiveSearchEngine:
    """Multi-tier search engine with early stopping optimization.

    The engine searches tiers sequentially (CATEGORIES → INSIGHTS → REFLECTIONS → CONVERSATIONS)
    and stops early when sufficient results are found. This reduces unnecessary computation by
    prioritizing faster, higher-quality data sources.

    Usage:
        >>> engine = ProgressiveSearchEngine()
        >>> result = await engine.search_progressive(
        ...     query="async patterns",
        ...     project="session-buddy",
        ...     max_tiers=4
        ... )
        >>> print(f"Searched {len(result.tiers_searched)} tiers, found {result.total_results} results")
    """

    def __init__(
        self,
        config: SufficiencyConfig | None = None,
        db_adapter: ReflectionDatabaseAdapter | None = None,
    ) -> None:
        """Initialize progressive search engine.

        Args:
            config: Optional sufficiency configuration
            db_adapter: Optional database adapter (uses default if None)
        """
        self.config = config or SufficiencyConfig()
        self.evaluator = SufficiencyEvaluator(config)
        self._db = db_adapter

        logger.info(
            "ProgressiveSearchEngine initialized with %d tiers", len(SearchTier)
        )

    async def search_progressive(
        self,
        query: str,
        project: str | None = None,
        min_score: float = 0.6,
        max_results: int = 30,
        max_tiers: int = 4,
        enable_early_stop: bool = True,
    ) -> ProgressiveSearchResult:
        """Execute progressive search across multiple tiers.

        Searches tiers from fastest to slowest, stopping early when sufficient
        results are found. Each tier is searched with tier-specific quality thresholds.

        Args:
            query: Search query string
            project: Optional project filter
            min_score: Minimum similarity score (0.0-1.0)
            max_results: Maximum total results across all tiers
            max_tiers: Maximum number of tiers to search (1-4)
            enable_early_stop: Whether to enable early stopping optimization

        Returns:
            ProgressiveSearchResult with all tier results and metadata

        Raises:
            ValueError: If max_tiers is not in range 1-4
        """
        if not 1 <= max_tiers <= 4:
            raise ValueError(f"max_tiers must be 1-4, got {max_tiers}")

        import time

        start_time = time.perf_counter()
        tiers_searched: list[SearchTier] = []
        all_results: list[dict[str, Any]] = []
        tier_results: list[TierSearchResult] = []
        early_stop = False

        # Define tier search order
        search_order = [
            SearchTier.CATEGORIES,
            SearchTier.INSIGHTS,
            SearchTier.REFLECTIONS,
            SearchTier.CONVERSATIONS,
        ][:max_tiers]

        for i, tier in enumerate(search_order):
            tier_start = time.perf_counter()

            logger.info(
                "Searching tier %d/%d: %s (min_score: %.2f)",
                i + 1,
                len(search_order),
                SearchTier.get_tier_name(tier),
                SearchTier.get_min_score(tier),
            )

            # Search this tier
            tier_result = await self._search_tier(
                query, project, tier, min_score, max_results
            )

            tier_latency = (time.perf_counter() - tier_start) * 1000
            tiers_searched.append(tier)
            tier_results.append(tier_result)

            # Collect results
            if tier_result.searched and tier_result.results:
                all_results.extend(tier_result.results)

                # Log tier completion
                logger.info(
                    "Tier %s: %d results (latency: %.2fms, avg score: %.2f)",
                    SearchTier.get_tier_name(tier),
                    len(tier_result.results),
                    tier_latency,
                    tier_result.avg_score,
                )

            # Check for early stopping
            if (
                enable_early_stop and i < len(search_order) - 1
            ):  # Don't stop on last tier
                is_sufficient, reason = self.evaluator.is_sufficient(all_results, tier)

                if is_sufficient:
                    early_stop = True
                    logger.info(
                        "Early stopping at tier %s: %s (total results: %d)",
                        SearchTier.get_tier_name(tier),
                        reason,
                        len(all_results),
                    )
                    break

        total_latency = (time.perf_counter() - start_time) * 1000

        # Build metadata
        metadata = {
            "avg_tiers_searched": len(tiers_searched),
            "max_tiers_allowed": max_tiers,
            "early_stop_reason": None,
        }

        if early_stop:
            # Capture the early stop reason for the last tier checked
            is_sufficient, reason = self.evaluator.is_sufficient(
                all_results, tiers_searched[-1]
            )
            metadata["early_stop_reason"] = reason  # type: ignore[assignment]

        # Build final result
        result = ProgressiveSearchResult(
            query=query,
            project=project,
            total_results=len(all_results),
            tiers_searched=tiers_searched,
            tier_results=tier_results,
            total_latency_ms=total_latency,
            early_stop=early_stop,
            search_complete=len(tiers_searched) >= max_tiers or not enable_early_stop,
            metadata=metadata,
        )

        return result

    async def _search_tier(
        self,
        query: str,
        project: str | None,
        tier: SearchTier,
        min_score: float,
        max_results: int,
    ) -> TierSearchResult:
        """Search a single tier.

        Args:
            query: Search query
            project: Optional project filter
            tier: Tier to search
            min_score: Minimum similarity score
            max_results: Maximum results to return

        Returns:
            TierSearchResult with tier-specific results
        """
        import time

        start_time = time.perf_counter()

        # Get database adapter
        db = self._db
        if db is None:
            from session_buddy.di import depends

            db = depends.get_sync("ReflectionDatabaseAdapter")

        # Search based on tier type
        if tier == SearchTier.CATEGORIES:
            results = await self._search_categories(
                db, query, project, min_score, max_results
            )
        elif tier == SearchTier.INSIGHTS:
            results = await self._search_insights(
                db, query, project, min_score, max_results
            )
        elif tier == SearchTier.REFLECTIONS:
            results = await self._search_reflections(
                db, query, project, min_score, max_results
            )
        elif tier == SearchTier.CONVERSATIONS:
            results = await self._search_conversations(
                db, query, project, min_score, max_results
            )
        else:
            results = []

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Calculate statistics
        if results:
            scores = [
                r.get("score", r.get("similarity", 0.0))
                for r in results
                if "score" in r or "similarity" in r
            ]
            min_score = min(scores) if scores else 0.0
            max_score = max(scores) if scores else 0.0
            avg_score = sum(scores) / len(scores) if scores else 0.0
        else:
            min_score = 0.0
            max_score = 0.0
            avg_score = 0.0

        return TierSearchResult(
            tier=tier,
            results=results,
            total_found=len(results),
            latency_ms=latency_ms,
            min_score=min_score,
            max_score=max_score,
            avg_score=avg_score,
            searched=True,
        )

    async def _search_categories(
        self,
        db: ReflectionDatabaseAdapter,
        query: str,
        project: str | None,
        min_score: float,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Search high-quality categories/insights.

        Args:
            db: Database adapter
            query: Search query
            project: Optional project filter
            min_score: Minimum similarity score
            max_results: Maximum results

        Returns:
            List of search results
        """
        # Search reflections with high score threshold (categories)
        tier_min_score = max(min_score, SearchTier.get_min_score(SearchTier.CATEGORIES))
        results = await db.search_reflections(
            query=query,
            limit=max_results,
            use_cache=True,  # Integrate with Phase 1 query cache
            use_embeddings=True,
        )

        # Filter by project and score manually (since search_reflections doesn't support these)
        if project:
            results = [r for r in results if r.get("project") == project]

        results = [
            r
            for r in results
            if r.get("score", r.get("similarity", 0.0)) >= tier_min_score
        ]

        # Add tier metadata
        for result in results:
            result["tier"] = SearchTier.CATEGORIES.value
            result["tier_name"] = SearchTier.get_tier_name(SearchTier.CATEGORIES)

        return results

    async def _search_insights(
        self,
        db: ReflectionDatabaseAdapter,
        query: str,
        project: str | None,
        min_score: float,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Search learned skills and insights.

        Args:
            db: Database adapter
            query: Search query
            project: Optional project filter
            min_score: Minimum similarity score
            max_results: Maximum results

        Returns:
            List of search results
        """
        # Search reflections with medium score threshold (insights)
        tier_min_score = max(min_score, SearchTier.get_min_score(SearchTier.INSIGHTS))
        results = await db.search_reflections(
            query=query,
            limit=max_results,
            use_cache=True,  # Integrate with Phase 1 query cache
            use_embeddings=True,
        )

        # Filter by project and score manually
        if project:
            results = [r for r in results if r.get("project") == project]

        results = [
            r
            for r in results
            if r.get("score", r.get("similarity", 0.0)) >= tier_min_score
        ]

        # Add tier metadata
        for result in results:
            result["tier"] = SearchTier.INSIGHTS.value
            result["tier_name"] = SearchTier.get_tier_name(SearchTier.INSIGHTS)

        return results

    async def _search_reflections(
        self,
        db: ReflectionDatabaseAdapter,
        query: str,
        project: str | None,
        min_score: float,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Search stored reflections.

        Args:
            db: Database adapter
            query: Search query
            project: Optional project filter
            min_score: Minimum similarity score
            max_results: Maximum results

        Returns:
            List of search results
        """
        # Search reflections with standard threshold
        tier_min_score = max(
            min_score, SearchTier.get_min_score(SearchTier.REFLECTIONS)
        )
        results = await db.search_reflections(
            query=query,
            limit=max_results,
            use_cache=True,  # Integrate with Phase 1 query cache
            use_embeddings=True,
        )

        # Filter by project and score manually
        if project:
            results = [r for r in results if r.get("project") == project]

        results = [
            r
            for r in results
            if r.get("score", r.get("similarity", 0.0)) >= tier_min_score
        ]

        # Add tier metadata
        for result in results:
            result["tier"] = SearchTier.REFLECTIONS.value
            result["tier_name"] = SearchTier.get_tier_name(SearchTier.REFLECTIONS)

        return results

    async def _search_conversations(
        self,
        db: ReflectionDatabaseAdapter,
        query: str,
        project: str | None,
        min_score: float,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Search full conversations.

        Args:
            db: Database adapter
            query: Search query
            project: Optional project filter
            min_score: Minimum similarity score
            max_results: Maximum results

        Returns:
            List of search results
        """
        # Search conversations with lower score threshold
        tier_min_score = max(
            min_score, SearchTier.get_min_score(SearchTier.CONVERSATIONS)
        )
        results = await db.search_conversations(
            query=query,
            project=project,
            threshold=tier_min_score,  # search_conversations uses 'threshold' not 'min_score'
            limit=max_results,
            use_cache=True,  # Integrate with Phase 1 query cache
        )

        # Add tier metadata
        for result in results:
            result["tier"] = SearchTier.CONVERSATIONS.value
            result["tier_name"] = SearchTier.get_tier_name(SearchTier.CONVERSATIONS)

        return results

    def get_search_stats(self) -> dict[str, Any]:
        """Get progressive search statistics.

        Returns:
            Dictionary with search statistics
        """
        # Statistics would be tracked during search operations
        # For now, return basic info
        return {
            "total_searches": 0,  # Would be incremented during searches
            "avg_tiers_searched": 0.0,
            "early_stop_rate": 0.0,
            "avg_latency_ms": 0.0,
        }
