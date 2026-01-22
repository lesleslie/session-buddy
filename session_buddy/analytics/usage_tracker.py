"""Usage analytics for adaptive result ranking (Phase 5).

This module tracks user interactions with search results to enable:
- Personalized result ranking based on usage patterns
- Adaptive threshold tuning based on success metrics
- Result diversity scoring to avoid repetitive results
- Performance analytics and optimization insights

Tracking Data:
- Click tracking: Which results users click/select
- Dwell time: How long users spend on results
- Result position: Where in ranking the result appeared
- Query context: What was searched for
- Session info: Which session/user made the query

Usage Patterns Detected:
- Preferred content types (conversations vs reflections vs insights)
- Result quality thresholds (what similarity scores are useful)
- Temporal patterns (recent vs older content preference)
- Query reformulation patterns (how users refine searches)
"""

from __future__ import annotations

import logging
import typing as t
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class ResultInteraction:
    """Track a single user interaction with a search result.

    Attributes:
        query: The search query that generated the result
        result_id: ID of the content (conversation/reflection ID)
        result_type: Type of content (conversation/reflection/insight)
        position: Position in results list (0-indexed)
        similarity_score: Semantic similarity score from search
        clicked: Whether user clicked/selected this result
        dwell_time_ms: Time spent viewing this result (milliseconds)
        timestamp: When the interaction occurred
        session_id: Optional session identifier
    """

    query: str
    result_id: str
    result_type: t.Literal["conversation", "reflection", "insight"]
    position: int
    similarity_score: float
    clicked: bool
    dwell_time_ms: int | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None

    def to_dict(self) -> dict[str, t.Any]:
        """Convert to dictionary for database storage."""
        return {
            "query": self.query,
            "result_id": self.result_id,
            "result_type": self.result_type,
            "position": self.position,
            "similarity_score": self.similarity_score,
            "clicked": int(self.clicked),  # Convert bool to int
            "dwell_time_ms": self.dwell_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
        }


@dataclass
class UsageMetrics:
    """Aggregated usage metrics for ranking decisions.

    Attributes:
        total_interactions: Total number of tracked interactions
        click_through_rate: Percentage of results that were clicked
        avg_dwell_time_ms: Average time spent on results
        avg_position_clicked: Average position of clicked results
        type_preference: Preference for each content type
        success_threshold: Minimum similarity score for useful results
    """

    total_interactions: int = 0
    click_through_rate: float = 0.0
    avg_dwell_time_ms: float = 0.0
    avg_position_clicked: float = 0.0
    type_preference: dict[str, float] = field(default_factory=dict)
    success_threshold: float = 0.7  # Default minimum similarity

    def update_from_interactions(self, interactions: list[ResultInteraction]) -> None:
        """Update metrics from a list of interactions.

        Args:
            interactions: List of interaction records to analyze
        """
        if not interactions:
            return

        self.total_interactions += len(interactions)

        # Calculate click-through rate
        clicked = [i for i in interactions if i.clicked]
        self.click_through_rate = len(clicked) / len(interactions)

        # Calculate average dwell time (only for clicked results)
        clicked_with_dwell = [i for i in clicked if i.dwell_time_ms is not None]
        if clicked_with_dwell:
            self.avg_dwell_time_ms = sum(
                i.dwell_time_ms
                for i in clicked_with_dwell
                if i.dwell_time_ms is not None
            ) / len(clicked_with_dwell)

        # Calculate average position of clicked results
        if clicked:
            positions = [i.position for i in clicked]
            self.avg_position_clicked = sum(positions) / len(positions)

        # Calculate type preference (which types get clicked most)
        type_counts: dict[str, int] = {}
        for i in clicked:
            type_counts[i.result_type] = type_counts.get(i.result_type, 0) + 1

        if type_counts:
            total_clicked = sum(type_counts.values())
            self.type_preference = {
                result_type: count / total_clicked
                for result_type, count in type_counts.items()
            }

        # Calculate success threshold (similarity score of useful results)
        # "Useful" = clicked with dwell time > 2 seconds
        useful_results = [
            i for i in clicked if i.dwell_time_ms and i.dwell_time_ms > 2000
        ]
        if useful_results:
            self.success_threshold = sum(
                i.similarity_score for i in useful_results
            ) / len(useful_results)


@dataclass
class RankingWeights:
    """Weights for personalized result ranking.

    Attributes:
        similarity_weight: Weight for semantic similarity score (0.0-1.0)
        recency_weight: Weight for result recency (0.0-1.0)
        type_preference_weight: Weight for user's type preference (0.0-1.0)
        position_boost: Boost factor for higher-ranked positions
        diversity_weight: Weight for result diversity (0.0-1.0)
    """

    similarity_weight: float = 0.7  # Primary factor: semantic relevance
    recency_weight: float = 0.15  # Slight preference for recent content
    type_preference_weight: float = 0.1  # Mild personalization
    position_boost: float = 0.05  # Slight boost for top positions
    diversity_weight: float = 0.0  # Disabled initially, can enable

    def normalize(self) -> RankingWeights:
        """Normalize weights to sum to 1.0."""
        total = (
            self.similarity_weight
            + self.recency_weight
            + self.type_preference_weight
            + self.position_boost
            + self.diversity_weight
        )

        if total == 0:
            return RankingWeights()

        return RankingWeights(
            similarity_weight=self.similarity_weight / total,
            recency_weight=self.recency_weight / total,
            type_preference_weight=self.type_preference_weight / total,
            position_boost=self.position_boost / total,
            diversity_weight=self.diversity_weight / total,
        )


class UsageTracker:
    """Track and analyze user interaction patterns for personalized ranking.

    This class provides:
    - Interaction recording (clicks, dwell time, position)
    - Metric aggregation (click-through rate, average position, etc.)
    - Pattern detection (type preferences, success thresholds)
    - Ranking weight calculation based on usage patterns
    """

    def __init__(self) -> None:
        """Initialize usage tracker."""
        self._interactions: list[ResultInteraction] = []
        self._metrics = UsageMetrics()
        self._weights = RankingWeights()

    def record_interaction(self, interaction: ResultInteraction) -> None:
        """Record a single user interaction.

        Args:
            interaction: Interaction details to record
        """
        self._interactions.append(interaction)
        # Update metrics incrementally
        self._metrics.update_from_interactions([interaction])

    def record_interactions(self, interactions: list[ResultInteraction]) -> None:
        """Record multiple interactions at once.

        Args:
            interactions: List of interaction details to record
        """
        self._interactions.extend(interactions)
        self._metrics.update_from_interactions(interactions)

    def get_metrics(self) -> UsageMetrics:
        """Get current aggregated usage metrics.

        Returns:
            Current usage metrics
        """
        return self._metrics

    def get_weights(self) -> RankingWeights:
        """Get personalized ranking weights based on usage patterns.

        Returns:
            Normalized ranking weights
        """
        # Adapt weights based on usage patterns
        weights = RankingWeights()

        # If user strongly prefers certain content types, boost type preference
        if self._metrics.type_preference:
            max_pref = max(self._metrics.type_preference.values())
            min_pref = min(self._metrics.type_preference.values())
            if max_pref - min_pref > 0.3:  # Strong preference
                weights.type_preference_weight = 0.2

        # If user consistently clicks low-position results, reduce position boost
        if self._metrics.avg_position_clicked > 3.0:
            weights.position_boost = 0.02  # Reduce boost
        elif self._metrics.avg_position_clicked < 1.5:
            weights.position_boost = 0.1  # Increase boost

        return weights.normalize()

    def calculate_ranking_score(
        self,
        result: dict[str, t.Any],
        result_position: int,
        recent_results: list[dict[str, t.Any]] | None = None,
    ) -> float:
        """Calculate personalized ranking score for a result.

        Args:
            result: Result dictionary with 'score', 'type', 'created_at' etc.
            result_position: Position in default ranking
            recent_results: Other results in this search (for diversity)

        Returns:
            Personalized ranking score (0.0-1.0)
        """
        weights = self.get_weights()
        score = 0.0

        # 1. Similarity score (primary factor)
        similarity = result.get("score", result.get("similarity", 0.0))
        score += weights.similarity_weight * similarity

        # 2. Recency boost (slight preference for recent content)
        created_at = result.get("created_at")
        if created_at:
            age_days = (datetime.now(UTC) - created_at).days
            # Normalize: 0 days = 1.0, 365+ days = 0.0
            recency_score = max(0.0, 1.0 - (age_days / 365.0))
            score += weights.recency_weight * recency_score

        # 3. Type preference (user's preferred content types)
        result_type = result.get("type", "conversation")
        type_pref = self._metrics.type_preference.get(result_type, 0.0)
        score += weights.type_preference_weight * type_pref

        # 4. Position boost (slight boost for top-ranked results)
        # Inverse position: position 0 = 1.0, position 10+ = 0.0
        position_score = max(0.0, 1.0 - (result_position / 10.0))
        score += weights.position_boost * position_score

        # 5. Diversity penalty (avoid repetitive content types)
        if weights.diversity_weight > 0 and recent_results:
            recent_types = [r.get("type") for r in recent_results[:5]]
            same_type_count = recent_types.count(result_type)
            diversity_penalty = (
                (same_type_count / len(recent_types)) if recent_types else 0
            )
            score -= weights.diversity_weight * diversity_penalty

        return max(0.0, min(1.0, score))  # Clamp to [0, 1]

    def get_success_threshold(self) -> float:
        """Get minimum similarity score for useful results based on usage.

        Returns:
            Minimum similarity threshold (0.0-1.0)
        """
        return max(0.5, min(0.95, self._metrics.success_threshold))

    def clear_interactions(self) -> None:
        """Clear all recorded interactions (for testing or privacy)."""
        self._interactions.clear()
        self._metrics = UsageMetrics()
        self._weights = RankingWeights()
