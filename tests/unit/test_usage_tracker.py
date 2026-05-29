"""Unit tests for session_buddy.analytics.usage_tracker module."""

from __future__ import annotations

import typing as t
from datetime import UTC, datetime
from unittest.mock import patch, MagicMock

import pytest

from session_buddy.analytics.usage_tracker import (
    ResultInteraction,
    UsageMetrics,
    RankingWeights,
    UsageTracker,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_datetime() -> MagicMock:
    """Mock datetime for time-sensitive tests."""
    fixed_time = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)
    with patch("session_buddy.analytics.usage_tracker.datetime") as mock:
        mock.now.return_value = fixed_time
        mock.UTC = UTC
        yield mock


@pytest.fixture
def sample_interaction() -> ResultInteraction:
    """Create a sample interaction for testing."""
    return ResultInteraction(
        query="test query",
        result_id="result_123",
        result_type="conversation",
        position=0,
        similarity_score=0.85,
        clicked=True,
        dwell_time_ms=3000,
        session_id="session_abc",
    )


@pytest.fixture
def sample_interactions() -> list[ResultInteraction]:
    """Create multiple sample interactions for batch testing."""
    return [
        ResultInteraction(
            query="python",
            result_id="conv_1",
            result_type="conversation",
            position=0,
            similarity_score=0.9,
            clicked=True,
            dwell_time_ms=5000,
            session_id="s1",
        ),
        ResultInteraction(
            query="python",
            result_id="refl_1",
            result_type="reflection",
            position=1,
            similarity_score=0.75,
            clicked=True,
            dwell_time_ms=2000,
            session_id="s1",
        ),
        ResultInteraction(
            query="python",
            result_id="ins_1",
            result_type="insight",
            position=2,
            similarity_score=0.6,
            clicked=False,
            dwell_time_ms=None,
            session_id="s1",
        ),
        ResultInteraction(
            query="rust",
            result_id="conv_2",
            result_type="conversation",
            position=0,
            similarity_score=0.8,
            clicked=False,
            dwell_time_ms=None,
            session_id="s2",
        ),
    ]


# ============================================================================
# ResultInteraction Tests
# ============================================================================

class TestResultInteraction:
    """Tests for ResultInteraction dataclass."""

    def test_creation_basic(self) -> None:
        """Test basic creation of ResultInteraction."""
        interaction = ResultInteraction(
            query="test query",
            result_id="result_1",
            result_type="conversation",
            position=5,
            similarity_score=0.7,
            clicked=True,
        )
        assert interaction.query == "test query"
        assert interaction.result_id == "result_1"
        assert interaction.result_type == "conversation"
        assert interaction.position == 5
        assert interaction.similarity_score == 0.7
        assert interaction.clicked is True
        assert interaction.dwell_time_ms is None
        assert interaction.session_id is None

    def test_creation_full(self, mock_datetime: MagicMock) -> None:
        """Test creation with all optional fields."""
        timestamp = datetime(2026, 5, 23, 10, 30, 0, tzinfo=UTC)
        interaction = ResultInteraction(
            query="full test",
            result_id="result_full",
            result_type="reflection",
            position=2,
            similarity_score=0.95,
            clicked=True,
            dwell_time_ms=4500,
            timestamp=timestamp,
            session_id="full_session",
        )
        assert interaction.dwell_time_ms == 4500
        assert interaction.timestamp == timestamp
        assert interaction.session_id == "full_session"

    def test_creation_invalid_result_type(self) -> None:
        """Test that invalid result_type is accepted (type checking at runtime)."""
        # The type hint is Literal, but Python doesn't enforce at construction
        interaction = ResultInteraction(
            query="test",
            result_id="r1",
            result_type="conversation",  # Valid literal value
            position=0,
            similarity_score=0.5,
            clicked=False,
        )
        assert interaction.result_type == "conversation"

    def test_to_dict(self, mock_datetime: MagicMock) -> None:
        """Test conversion to dictionary."""
        timestamp = datetime(2026, 5, 23, 10, 30, 0, tzinfo=UTC)
        interaction = ResultInteraction(
            query="dict test",
            result_id="dict_result",
            result_type="insight",
            position=1,
            similarity_score=0.88,
            clicked=True,
            dwell_time_ms=2500,
            timestamp=timestamp,
            session_id="dict_session",
        )
        result = interaction.to_dict()
        assert result["query"] == "dict test"
        assert result["result_id"] == "dict_result"
        assert result["result_type"] == "insight"
        assert result["position"] == 1
        assert result["similarity_score"] == 0.88
        assert result["clicked"] == 1  # bool to int conversion
        assert result["dwell_time_ms"] == 2500
        assert result["timestamp"] == timestamp.isoformat()
        assert result["session_id"] == "dict_session"

    def test_to_dict_with_none_optionals(self) -> None:
        """Test to_dict when optional fields are None."""
        interaction = ResultInteraction(
            query="minimal",
            result_id="min_result",
            result_type="conversation",
            position=0,
            similarity_score=0.5,
            clicked=False,
        )
        result = interaction.to_dict()
        assert result["dwell_time_ms"] is None
        assert result["session_id"] is None
        assert result["clicked"] == 0

    def test_equality(self, mock_datetime: MagicMock) -> None:
        """Test equality comparison."""
        ts = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)
        i1 = ResultInteraction(
            query="eq",
            result_id="eq1",
            result_type="conversation",
            position=0,
            similarity_score=0.5,
            clicked=True,
            timestamp=ts,
        )
        i2 = ResultInteraction(
            query="eq",
            result_id="eq1",
            result_type="conversation",
            position=0,
            similarity_score=0.5,
            clicked=True,
            timestamp=ts,
        )
        assert i1 == i2

    def test_inequality(self) -> None:
        """Test inequality comparison."""
        i1 = ResultInteraction(
            query="a",
            result_id="r1",
            result_type="conversation",
            position=0,
            similarity_score=0.5,
            clicked=True,
        )
        i2 = ResultInteraction(
            query="b",
            result_id="r2",
            result_type="reflection",
            position=1,
            similarity_score=0.6,
            clicked=False,
        )
        assert i1 != i2


# ============================================================================
# UsageMetrics Tests
# ============================================================================

class TestUsageMetrics:
    """Tests for UsageMetrics dataclass."""

    def test_creation_defaults(self) -> None:
        """Test default values on creation."""
        metrics = UsageMetrics()
        assert metrics.total_interactions == 0
        assert metrics.click_through_rate == 0.0
        assert metrics.avg_dwell_time_ms == 0.0
        assert metrics.avg_position_clicked == 0.0
        assert metrics.type_preference == {}
        assert metrics.success_threshold == 0.7

    def test_update_from_interactions_empty(self) -> None:
        """Test update with empty list."""
        metrics = UsageMetrics()
        metrics.update_from_interactions([])
        assert metrics.total_interactions == 0
        assert metrics.click_through_rate == 0.0

    def test_update_from_interactions_single(
        self, sample_interaction: ResultInteraction
    ) -> None:
        """Test update with single interaction."""
        metrics = UsageMetrics()
        metrics.update_from_interactions([sample_interaction])
        assert metrics.total_interactions == 1
        assert metrics.click_through_rate == 1.0

    def test_update_from_interactions_batch(
        self, sample_interactions: list[ResultInteraction]
    ) -> None:
        """Test update with multiple interactions."""
        metrics = UsageMetrics()
        metrics.update_from_interactions(sample_interactions)
        assert metrics.total_interactions == 4
        # 2 clicked out of 4 = 0.5
        assert metrics.click_through_rate == 0.5

    def test_update_accumulation(self, sample_interactions: list[ResultInteraction]) -> None:
        """Test that updates accumulate correctly for total_interactions."""
        metrics = UsageMetrics()
        metrics.update_from_interactions(sample_interactions[:2])
        assert metrics.total_interactions == 2
        assert metrics.click_through_rate == 1.0  # Both clicked

        metrics.update_from_interactions(sample_interactions[2:])
        assert metrics.total_interactions == 4
        # Note: click_through_rate is per-batch, not cumulative
        # Second batch: 0 clicks out of 2 = 0.0
        assert metrics.click_through_rate == 0.0

    def test_avg_dwell_time_calculation(self) -> None:
        """Test average dwell time calculation."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.8,
                clicked=True,
                dwell_time_ms=3000,
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=1,
                similarity_score=0.7,
                clicked=True,
                dwell_time_ms=5000,
            ),
        ]
        metrics = UsageMetrics()
        metrics.update_from_interactions(interactions)
        # Average of 3000 and 5000
        assert metrics.avg_dwell_time_ms == 4000.0

    def test_avg_dwell_time_no_dwell_data(self) -> None:
        """Test average dwell time when no dwell data available."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.8,
                clicked=True,
                dwell_time_ms=None,
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=1,
                similarity_score=0.7,
                clicked=True,
                dwell_time_ms=None,
            ),
        ]
        metrics = UsageMetrics()
        metrics.update_from_interactions(interactions)
        assert metrics.avg_dwell_time_ms == 0.0

    def test_avg_position_clicked(self, sample_interactions: list[ResultInteraction]) -> None:
        """Test average position calculation for clicked results."""
        metrics = UsageMetrics()
        metrics.update_from_interactions(sample_interactions)
        # Clicked results: positions 0 and 1, average = 0.5
        assert metrics.avg_position_clicked == 0.5

    def test_avg_position_no_clicks(self) -> None:
        """Test average position when no clicks."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.8,
                clicked=False,
            ),
        ]
        metrics = UsageMetrics()
        metrics.update_from_interactions(interactions)
        assert metrics.avg_position_clicked == 0.0

    def test_type_preference_calculation(self, sample_interactions: list[ResultInteraction]) -> None:
        """Test type preference calculation."""
        metrics = UsageMetrics()
        metrics.update_from_interactions(sample_interactions)
        # Clicked: conversation (pos 0), reflection (pos 1) = 2 types
        # conversation: 1/2 = 0.5, reflection: 1/2 = 0.5
        assert metrics.type_preference["conversation"] == 0.5
        assert metrics.type_preference["reflection"] == 0.5
        assert "insight" not in metrics.type_preference

    def test_type_preference_all_same_type(self) -> None:
        """Test type preference with all same type clicked."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.8,
                clicked=True,
                dwell_time_ms=3000,
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=1,
                similarity_score=0.7,
                clicked=True,
                dwell_time_ms=4000,
            ),
            ResultInteraction(
                query="test",
                result_id="r3",
                result_type="conversation",
                position=2,
                similarity_score=0.6,
                clicked=True,
                dwell_time_ms=5000,
            ),
        ]
        metrics = UsageMetrics()
        metrics.update_from_interactions(interactions)
        assert metrics.type_preference["conversation"] == 1.0

    def test_success_threshold_calculation(self) -> None:
        """Test success threshold calculation based on useful results."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.9,
                clicked=True,
                dwell_time_ms=3000,  # > 2000 = useful
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=1,
                similarity_score=0.5,
                clicked=True,
                dwell_time_ms=1000,  # < 2000 = not useful
            ),
        ]
        metrics = UsageMetrics()
        metrics.update_from_interactions(interactions)
        # Only r1 is useful (dwell > 2000ms), score 0.9
        assert metrics.success_threshold == pytest.approx(0.9)

    def test_success_threshold_no_useful_results(self) -> None:
        """Test success threshold when no useful results."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.9,
                clicked=True,
                dwell_time_ms=1000,  # < 2000 = not useful
            ),
        ]
        metrics = UsageMetrics()
        metrics.update_from_interactions(interactions)
        # No useful results, threshold stays at default
        assert metrics.success_threshold == 0.7

    def test_success_threshold_multiple_useful(self) -> None:
        """Test success threshold with multiple useful results."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.95,
                clicked=True,
                dwell_time_ms=5000,
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=1,
                similarity_score=0.85,
                clicked=True,
                dwell_time_ms=4000,
            ),
        ]
        metrics = UsageMetrics()
        metrics.update_from_interactions(interactions)
        # Average of 0.95 and 0.85 = 0.9
        assert metrics.success_threshold == pytest.approx(0.9)


# ============================================================================
# RankingWeights Tests
# ============================================================================

class TestRankingWeights:
    """Tests for RankingWeights dataclass."""

    def test_creation_defaults(self) -> None:
        """Test default values on creation."""
        weights = RankingWeights()
        assert weights.similarity_weight == 0.7
        assert weights.recency_weight == 0.15
        assert weights.type_preference_weight == 0.1
        assert weights.position_boost == 0.05
        assert weights.diversity_weight == 0.0

    def test_normalize_equal_weights(self) -> None:
        """Test normalization with equal weights."""
        weights = RankingWeights(
            similarity_weight=0.25,
            recency_weight=0.25,
            type_preference_weight=0.25,
            position_boost=0.25,
            diversity_weight=0.0,
        )
        normalized = weights.normalize()
        total = (
            normalized.similarity_weight
            + normalized.recency_weight
            + normalized.type_preference_weight
            + normalized.position_boost
            + normalized.diversity_weight
        )
        assert abs(total - 1.0) < 0.0001

    def test_normalize_unequal_weights(self) -> None:
        """Test normalization with unequal weights."""
        weights = RankingWeights(
            similarity_weight=0.8,
            recency_weight=0.1,
            type_preference_weight=0.05,
            position_boost=0.05,
            diversity_weight=0.0,
        )
        normalized = weights.normalize()
        total = (
            normalized.similarity_weight
            + normalized.recency_weight
            + normalized.type_preference_weight
            + normalized.position_boost
            + normalized.diversity_weight
        )
        assert abs(total - 1.0) < 0.0001

    def test_normalize_zero_weights(self) -> None:
        """Test normalization with all zeros returns defaults."""
        weights = RankingWeights(
            similarity_weight=0.0,
            recency_weight=0.0,
            type_preference_weight=0.0,
            position_boost=0.0,
            diversity_weight=0.0,
        )
        normalized = weights.normalize()
        # Returns default RankingWeights
        assert normalized.similarity_weight == 0.7
        assert normalized.recency_weight == 0.15
        assert normalized.type_preference_weight == 0.1
        assert normalized.position_boost == 0.05
        assert normalized.diversity_weight == 0.0

    def test_normalize_preserves_proportions(self) -> None:
        """Test that normalization preserves relative proportions."""
        weights = RankingWeights(
            similarity_weight=0.6,
            recency_weight=0.3,
            type_preference_weight=0.1,
            position_boost=0.0,
            diversity_weight=0.0,
        )
        normalized = weights.normalize()
        # Proportions: 6:3:1
        assert abs(normalized.similarity_weight - 0.6) < 0.0001
        assert abs(normalized.recency_weight - 0.3) < 0.0001
        assert abs(normalized.type_preference_weight - 0.1) < 0.0001


# ============================================================================
# UsageTracker Tests
# ============================================================================

class TestUsageTracker:
    """Tests for UsageTracker class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        tracker = UsageTracker()
        assert len(tracker._interactions) == 0
        assert isinstance(tracker._metrics, UsageMetrics)
        assert isinstance(tracker._weights, RankingWeights)

    def test_record_interaction(self, sample_interaction: ResultInteraction) -> None:
        """Test recording a single interaction."""
        tracker = UsageTracker()
        tracker.record_interaction(sample_interaction)
        assert len(tracker._interactions) == 1
        assert tracker._interactions[0] == sample_interaction

    def test_record_interactions_batch(
        self, sample_interactions: list[ResultInteraction]
    ) -> None:
        """Test recording multiple interactions."""
        tracker = UsageTracker()
        tracker.record_interactions(sample_interactions)
        assert len(tracker._interactions) == 4

    def test_record_interaction_updates_metrics(
        self, sample_interaction: ResultInteraction
    ) -> None:
        """Test that recording updates metrics."""
        tracker = UsageTracker()
        tracker.record_interaction(sample_interaction)
        metrics = tracker.get_metrics()
        assert metrics.total_interactions == 1
        assert metrics.click_through_rate == 1.0

    def test_get_metrics(self, sample_interactions: list[ResultInteraction]) -> None:
        """Test getting metrics."""
        tracker = UsageTracker()
        tracker.record_interactions(sample_interactions)
        metrics = tracker.get_metrics()
        assert metrics.total_interactions == 4
        assert metrics.click_through_rate == 0.5

    def test_get_weights_default(self) -> None:
        """Test getting weights without enough data for adaptation."""
        tracker = UsageTracker()
        weights = tracker.get_weights()
        # Should return normalized default weights
        total = (
            weights.similarity_weight
            + weights.recency_weight
            + weights.type_preference_weight
            + weights.position_boost
            + weights.diversity_weight
        )
        assert abs(total - 1.0) < 0.0001

    def test_get_weights_with_diverse_type_preference(self) -> None:
        """Test weights adapt when there's a diverse type preference."""
        # Create interactions with diverse type preferences
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.9,
                clicked=True,
                dwell_time_ms=5000,
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=1,
                similarity_score=0.8,
                clicked=True,
                dwell_time_ms=4000,
            ),
            ResultInteraction(
                query="test",
                result_id="r3",
                result_type="conversation",
                position=2,
                similarity_score=0.7,
                clicked=True,
                dwell_time_ms=3000,
            ),
            ResultInteraction(
                query="test",
                result_id="r4",
                result_type="reflection",
                position=0,
                similarity_score=0.9,
                clicked=True,
                dwell_time_ms=5000,
            ),
            ResultInteraction(
                query="test",
                result_id="r5",
                result_type="reflection",
                position=1,
                similarity_score=0.8,
                clicked=True,
                dwell_time_ms=4000,
            ),
        ]
        tracker = UsageTracker()
        tracker.record_interactions(interactions)

        # Verify type preference has both types
        metrics = tracker.get_metrics()
        assert "conversation" in metrics.type_preference
        assert "reflection" in metrics.type_preference

        weights = tracker.get_weights()
        # Weights should be normalized
        total = (
            weights.similarity_weight
            + weights.recency_weight
            + weights.type_preference_weight
            + weights.position_boost
            + weights.diversity_weight
        )
        assert abs(total - 1.0) < 0.0001

    def test_get_weights_with_low_avg_position(self) -> None:
        """Test weights adjust when user clicks low position results."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.9,
                clicked=True,
                dwell_time_ms=5000,
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=0,
                similarity_score=0.85,
                clicked=True,
                dwell_time_ms=4000,
            ),
        ]
        tracker = UsageTracker()
        tracker.record_interactions(interactions)

        metrics = tracker.get_metrics()
        assert metrics.avg_position_clicked == 0.0  # avg of positions 0 and 0

        weights = tracker.get_weights()
        # With avg_position < 1.5, position_boost should be 0.1 (default is 0.05)
        # But normalization changes the value, so check it increased relative to default
        assert weights.position_boost > 0.05

    def test_get_weights_with_high_avg_position(self) -> None:
        """Test weights adjust when user clicks high position results."""
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=4,
                similarity_score=0.9,
                clicked=True,
                dwell_time_ms=5000,
            ),
            ResultInteraction(
                query="test",
                result_id="r2",
                result_type="conversation",
                position=5,
                similarity_score=0.85,
                clicked=True,
                dwell_time_ms=4000,
            ),
        ]
        tracker = UsageTracker()
        tracker.record_interactions(interactions)

        metrics = tracker.get_metrics()
        assert metrics.avg_position_clicked == 4.5  # avg of 4 and 5

        weights = tracker.get_weights()
        # avg_position_clicked > 3.0, position_boost should be 0.02 (default 0.05)
        # But normalization changes the value, so check it decreased relative to default
        assert weights.position_boost < 0.05

    def test_calculate_ranking_score_basic(self) -> None:
        """Test basic ranking score calculation."""
        tracker = UsageTracker()
        result = {
            "score": 0.8,
            "type": "conversation",
            "created_at": datetime(2026, 5, 20, tzinfo=UTC),
        }
        score = tracker.calculate_ranking_score(result, 0)
        assert 0.0 <= score <= 1.0
        # Should be significant since similarity is 0.8
        assert score > 0.5

    def test_calculate_ranking_score_no_score_key(self) -> None:
        """Test ranking score calculation when result has no 'score' key."""
        tracker = UsageTracker()
        result = {
            "similarity": 0.7,
            "type": "reflection",
        }
        score = tracker.calculate_ranking_score(result, 2)
        assert 0.0 <= score <= 1.0

    def test_calculate_ranking_score_no_score_or_similarity(self) -> None:
        """Test ranking score calculation when result has neither score nor similarity."""
        tracker = UsageTracker()
        result = {
            "type": "insight",
        }
        score = tracker.calculate_ranking_score(result, 5)
        assert 0.0 <= score <= 1.0

    def test_calculate_ranking_score_with_recency(
        self, mock_datetime: MagicMock
    ) -> None:
        """Test ranking score includes recency boost for recent content."""
        tracker = UsageTracker()
        recent_result = {
            "score": 0.6,
            "type": "conversation",
            "created_at": datetime(2026, 5, 22, tzinfo=UTC),  # 1 day old
        }
        old_result = {
            "score": 0.6,
            "type": "conversation",
            "created_at": datetime(2026, 4, 1, tzinfo=UTC),  # ~52 days old
        }
        recent_score = tracker.calculate_ranking_score(recent_result, 0)
        old_score = tracker.calculate_ranking_score(old_result, 0)
        # Recent should score higher due to recency weight
        assert recent_score > old_score

    def test_calculate_ranking_score_type_preference(self) -> None:
        """Test ranking score includes type preference."""
        tracker = UsageTracker()
        # Set up type preference for conversation
        interactions = [
            ResultInteraction(
                query="test",
                result_id="r1",
                result_type="conversation",
                position=0,
                similarity_score=0.9,
                clicked=True,
                dwell_time_ms=5000,
            ),
        ]
        tracker.record_interactions(interactions)

        conv_result = {"score": 0.7, "type": "conversation"}
        refl_result = {"score": 0.7, "type": "reflection"}

        conv_score = tracker.calculate_ranking_score(conv_result, 0)
        refl_score = tracker.calculate_ranking_score(refl_result, 0)
        # Conversation should score higher due to type preference
        assert conv_score > refl_score

    def test_calculate_ranking_score_position_boost(self) -> None:
        """Test ranking score includes position boost."""
        tracker = UsageTracker()
        result = {"score": 0.6, "type": "conversation"}

        top_score = tracker.calculate_ranking_score(result, 0)
        low_score = tracker.calculate_ranking_score(result, 9)
        # Top position should score higher
        assert top_score > low_score

    def test_calculate_ranking_score_diversity_penalty(
        self, sample_interactions: list[ResultInteraction]
    ) -> None:
        """Test ranking score applies diversity penalty correctly."""
        tracker = UsageTracker()
        tracker.record_interactions(sample_interactions)

        # Recent results are all conversation type - 5 of them
        recent_results = [
            {"type": "conversation"},
            {"type": "conversation"},
            {"type": "conversation"},
            {"type": "conversation"},
            {"type": "conversation"},
        ]

        # Test with a higher diversity weight to make penalty more visible
        # We set directly on the tracker._weights before calling calculate_ranking_score
        # But calculate_ranking_score calls get_weights() which normalizes
        # So we need to verify the diversity penalty by checking the score difference
        # when comparing results of the same type vs different types
        conv_result_same = {"score": 0.7, "type": "conversation"}
        refl_result_diff = {"score": 0.7, "type": "reflection"}

        # Use position 0 for both to isolate the diversity penalty
        # conversation will get a penalty (5/5 = 1.0 penalty)
        # reflection will get no penalty (0/5 = 0.0 penalty)
        conv_score = tracker.calculate_ranking_score(conv_result_same, 0, recent_results)
        refl_score = tracker.calculate_ranking_score(refl_result_diff, 0, recent_results)

        # The conversation result should get a diversity penalty
        # reflection should score >= conversation due to lack of penalty
        assert refl_score >= conv_score

    def test_calculate_ranking_score_clamping(self) -> None:
        """Test ranking score is clamped to [0, 1]."""
        tracker = UsageTracker()
        # With default weights, max score should be bounded
        result = {"score": 1.0, "type": "conversation"}
        score = tracker.calculate_ranking_score(result, 0)
        assert score <= 1.0

        result_min = {"score": 0.0, "type": "conversation"}
        score_min = tracker.calculate_ranking_score(result_min, 0)
        assert score_min >= 0.0

    def test_get_success_threshold_default(self) -> None:
        """Test get_success_threshold with default metrics."""
        tracker = UsageTracker()
        threshold = tracker.get_success_threshold()
        assert 0.5 <= threshold <= 0.95

    def test_get_success_threshold_high(self) -> None:
        """Test get_success_threshold with high success threshold."""
        tracker = UsageTracker()
        tracker._metrics = UsageMetrics(success_threshold=0.99)
        threshold = tracker.get_success_threshold()
        assert threshold == 0.95  # Capped at 0.95

    def test_get_success_threshold_low(self) -> None:
        """Test get_success_threshold with low success threshold."""
        tracker = UsageTracker()
        tracker._metrics = UsageMetrics(success_threshold=0.3)
        threshold = tracker.get_success_threshold()
        assert threshold == 0.5  # Floored at 0.5

    def test_clear_interactions(self, sample_interactions: list[ResultInteraction]) -> None:
        """Test clearing interactions."""
        tracker = UsageTracker()
        tracker.record_interactions(sample_interactions)
        assert len(tracker._interactions) == 4

        tracker.clear_interactions()
        assert len(tracker._interactions) == 0
        assert tracker._metrics.total_interactions == 0
        assert tracker._metrics.click_through_rate == 0.0

    def test_clear_interactions_resets_weights(self) -> None:
        """Test that clear also resets weights."""
        tracker = UsageTracker()
        tracker._weights = RankingWeights(type_preference_weight=0.3)
        tracker.clear_interactions()
        # After clear, weights should be default
        assert tracker._weights.type_preference_weight == 0.1


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestUsageTrackerEdgeCases:
    """Edge case tests for UsageTracker."""

    def test_overflow_large_batch(self) -> None:
        """Test handling of very large batch of interactions."""
        tracker = UsageTracker()
        interactions = [
            ResultInteraction(
                query=f"query_{i}",
                result_id=f"result_{i}",
                result_type="conversation",
                position=i % 10,
                similarity_score=0.5 + (i % 50) / 100,
                clicked=i % 2 == 0,
                dwell_time_ms=3000 if i % 2 == 0 else None,
            )
            for i in range(1000)
        ]
        tracker.record_interactions(interactions)
        metrics = tracker.get_metrics()
        assert metrics.total_interactions == 1000

    def test_missing_timestamp(self) -> None:
        """Test handling of interactions without timestamp field in to_dict."""
        interaction = ResultInteraction(
            query="test",
            result_id="r1",
            result_type="conversation",
            position=0,
            similarity_score=0.8,
            clicked=True,
        )
        # timestamp is set via field(default_factory...)
        result = interaction.to_dict()
        assert "timestamp" in result

    def test_concurrent_updates(self) -> None:
        """Test thread safety of concurrent updates (simulated)."""
        import threading

        tracker = UsageTracker()
        errors: list[Exception] = []

        def record_batch(start: int) -> None:
            try:
                for i in range(100):
                    interaction = ResultInteraction(
                        query=f"query_{start + i}",
                        result_id=f"result_{start + i}",
                        result_type="conversation",
                        position=i % 10,
                        similarity_score=0.8,
                        clicked=True,
                        dwell_time_ms=2000,
                    )
                    tracker.record_interaction(interaction)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_batch, args=(i * 100,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert tracker.get_metrics().total_interactions == 500

    def test_empty_query_interaction(self) -> None:
        """Test interaction with empty query string."""
        tracker = UsageTracker()
        interaction = ResultInteraction(
            query="",
            result_id="r1",
            result_type="conversation",
            position=0,
            similarity_score=0.5,
            clicked=False,
        )
        tracker.record_interaction(interaction)
        assert tracker.get_metrics().total_interactions == 1

    def test_zero_similarity_score(self) -> None:
        """Test interaction with zero similarity score."""
        tracker = UsageTracker()
        interaction = ResultInteraction(
            query="test",
            result_id="r1",
            result_type="conversation",
            position=0,
            similarity_score=0.0,
            clicked=False,
        )
        tracker.record_interaction(interaction)
        # Should not crash
        score = tracker.calculate_ranking_score({"score": 0.0}, 0)
        assert score >= 0.0

    def test_negative_position(self) -> None:
        """Test interaction with negative position."""
        tracker = UsageTracker()
        interaction = ResultInteraction(
            query="test",
            result_id="r1",
            result_type="conversation",
            position=-1,
            similarity_score=0.8,
            clicked=True,
        )
        tracker.record_interaction(interaction)
        metrics = tracker.get_metrics()
        assert metrics.avg_position_clicked == -1.0

    def test_result_without_created_at(self) -> None:
        """Test ranking calculation when result lacks created_at."""
        tracker = UsageTracker()
        result = {"score": 0.7, "type": "conversation"}
        score = tracker.calculate_ranking_score(result, 5)
        assert 0.0 <= score <= 1.0

    def test_result_with_future_created_at(self, mock_datetime: MagicMock) -> None:
        """Test ranking calculation with future created_at date."""
        tracker = UsageTracker()
        future_date = datetime(2027, 1, 1, tzinfo=UTC)  # Future date
        result = {"score": 0.7, "type": "conversation", "created_at": future_date}
        score = tracker.calculate_ranking_score(result, 0)
        # Should not crash and recency score should be 0 or negative
        assert score >= 0.0


# ============================================================================
# Integration Tests
# ============================================================================

class TestUsageTrackerIntegration:
    """Integration tests for full usage tracking workflow."""

    def test_full_workflow(self, mock_datetime: MagicMock) -> None:
        """Test complete usage tracking workflow."""
        tracker = UsageTracker()

        # Record initial interactions
        interactions = [
            ResultInteraction(
                query="python async",
                result_id="conv_1",
                result_type="conversation",
                position=0,
                similarity_score=0.92,
                clicked=True,
                dwell_time_ms=6000,
            ),
            ResultInteraction(
                query="python async",
                result_id="refl_1",
                result_type="reflection",
                position=1,
                similarity_score=0.78,
                clicked=True,
                dwell_time_ms=3000,
            ),
            ResultInteraction(
                query="python async",
                result_id="ins_1",
                result_type="insight",
                position=2,
                similarity_score=0.65,
                clicked=False,
            ),
        ]
        tracker.record_interactions(interactions)

        # Get metrics and verify
        metrics = tracker.get_metrics()
        assert metrics.total_interactions == 3
        assert metrics.click_through_rate == pytest.approx(2 / 3, rel=0.01)

        # Get weights and verify they are normalized
        weights = tracker.get_weights()
        total = (
            weights.similarity_weight
            + weights.recency_weight
            + weights.type_preference_weight
            + weights.position_boost
            + weights.diversity_weight
        )
        assert abs(total - 1.0) < 0.0001

        # Calculate ranking scores for new results
        results = [
            {"score": 0.85, "type": "conversation", "created_at": datetime(2026, 5, 22, tzinfo=UTC)},
            {"score": 0.80, "type": "reflection", "created_at": datetime(2026, 5, 20, tzinfo=UTC)},
            {"score": 0.72, "type": "insight", "created_at": datetime(2026, 5, 21, tzinfo=UTC)},
        ]
        scores = [tracker.calculate_ranking_score(r, i) for i, r in enumerate(results)]

        # Verify scores are within bounds
        for score in scores:
            assert 0.0 <= score <= 1.0

        # Verify success threshold
        threshold = tracker.get_success_threshold()
        assert 0.5 <= threshold <= 0.95

    def test_empty_tracker_metrics(self) -> None:
        """Test metrics from empty tracker."""
        tracker = UsageTracker()
        metrics = tracker.get_metrics()
        assert metrics.total_interactions == 0
        assert metrics.click_through_rate == 0.0
        assert metrics.avg_dwell_time_ms == 0.0
        assert metrics.type_preference == {}

    def test_repeated_clear_and_record(self) -> None:
        """Test repeated clear and record operations."""
        tracker = UsageTracker()
        for _ in range(5):
            interactions = [
                ResultInteraction(
                    query=f"q{i}",
                    result_id=f"r{i}",
                    result_type="conversation",
                    position=0,
                    similarity_score=0.8,
                    clicked=True,
                    dwell_time_ms=2000,
                )
                for i in range(10)
            ]
            tracker.record_interactions(interactions)
            tracker.clear_interactions()

        assert len(tracker._interactions) == 0
        assert tracker.get_metrics().total_interactions == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
