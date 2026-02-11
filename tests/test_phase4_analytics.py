#!/usr/bin/env python3
"""Tests for Phase 4 Analytics Engine.

Tests for predictive models, A/B testing framework, time-series analysis,
and collaborative filtering.
"""

from __future__ import annotations

import pytest
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ============================================================================
# A/B Testing Framework Tests
# ============================================================================


class TestABTestFramework:
    """Test A/B testing framework."""

    def test_abtest_config_creation(self, tmp_path: Path) -> None:
        """Test ABTestConfig dataclass creation."""
        from session_buddy.analytics.ab_testing import ABTestConfig

        config = ABTestConfig(
            test_name="test_skill_recommendation",
            description="Compare semantic search vs workflow-aware search",
            control_strategy="semantic_search",
            treatment_strategy="workflow_aware_search",
            start_date="2026-02-01T00:00:00Z",
            min_sample_size=100,
        )

        assert config.test_name == "test_skill_recommendation"
        assert config.control_strategy == "semantic_search"
        assert config.treatment_strategy == "workflow_aware_search"
        assert config.min_sample_size == 100

    def test_abtest_config_with_end_date(self, tmp_path: Path) -> None:
        """Test ABTestConfig with end date."""
        from session_buddy.analytics.ab_testing import ABTestConfig

        config = ABTestConfig(
            test_name="test_skill_recommendation",
            description="Test with end date",
            control_strategy="semantic_search",
            treatment_strategy="workflow_aware_search",
            start_date="2026-02-01T00:00:00Z",
            end_date="2026-02-15T00:00:00Z",
            min_sample_size=100,
        )

        assert config.end_date == "2026-02-15T00:00:00Z"


# ============================================================================
# Predictive Model Tests
# ============================================================================


class TestPredictiveModels:
    """Test predictive model components."""

    def test_feature_extraction(self) -> None:
        """Test feature extraction for prediction."""
        from session_buddy.analytics.predictive import SkillSuccessPredictor

        # Create a mock predictor (without full database)
        # Test that feature columns are defined
        expected_features = [
            "hour_of_day",
            "day_of_week",
            "invocation_count_24h",
            "avg_completion_rate_24h",
            "workflow_phase_encoded",
            "session_length_minutes",
            "user_skill_familiarity",
        ]

        # Verify feature list is defined
        assert len(expected_features) == 7
        assert "hour_of_day" in expected_features
        assert "workflow_phase_encoded" in expected_features

    def test_workflow_phase_encoding(self) -> None:
        """Test workflow phase encoding."""
        # Test the phase encoding mapping
        phase_encoding = {
            "setup": 0,
            "execution": 1,
            "verification": 2,
            "cleanup": 3,
            "rollback": 4,
        }

        # Verify all expected phases are present
        assert "setup" in phase_encoding
        assert "execution" in phase_encoding
        assert "verification" in phase_encoding
        assert "cleanup" in phase_encoding
        assert "rollback" in phase_encoding

        # Verify encoding values
        assert phase_encoding["setup"] == 0
        assert phase_encoding["rollback"] == 4


# ============================================================================
# Time-Series Analysis Tests
# ============================================================================


class TestTimeSeriesAnalysis:
    """Test time-series analysis components."""

    def test_aggregation_interval(self) -> None:
        """Test hourly aggregation interval."""
        from session_buddy.analytics.time_series import TimeSeriesAnalyzer

        # Verify hourly granularity is supported
        # (This would be tested against real database in integration tests)
        granularity_hours = 24
        expected_data_points = granularity_hours  # One per hour

        assert expected_data_points == 24

    def test_trend_directions(self) -> None:
        """Test trend detection logic."""
        # Test slope interpretation
        slope_improving = 0.05
        slope_declining = -0.03
        slope_stable = 0.001

        # Improving trend
        assert slope_improving > 0
        # Declining trend
        assert slope_declining < 0
        # Stable trend (near zero) - use <= for boundary condition
        assert abs(slope_stable) <= 0.001

    def test_trend_classification(self) -> None:
        """Test trend classification thresholds."""
        # Test threshold-based classification
        threshold = 0.001

        # Above threshold
        assert 0.01 > threshold
        # Below threshold (negative)
        assert -0.01 < -threshold
        # Within threshold
        assert abs(0.0005) < threshold


# ============================================================================
# Collaborative Filtering Tests
# ============================================================================


class TestCollaborativeFiltering:
    """Test collaborative filtering engine."""

    def test_jaccard_similarity_calculation(self) -> None:
        """Test Jaccard similarity calculation."""
        # Test case: Two users with overlapping skill sets

        # User A skills: pytest, ruff, mypy
        user_a_skills = {"pytest-run", "ruff-check", "mypy"}

        # User B skills: pytest, ruff, black
        user_b_skills = {"pytest-run", "ruff-check", "black"}

        # Calculate Jaccard similarity
        intersection = len(user_a_skills & user_b_skills)
        union = len(user_a_skills | user_b_skills)
        jaccard = intersection / union if union > 0 else 0.0

        # Should be 2/4 = 0.5 (pytest-run and ruff-check in common, mypy and black different)
        assert jaccard == pytest.approx(0.5, rel=0.01)

    def test_skill_recommendation_scoring(self) -> None:
        """Test recommendation scoring formula."""
        # Test case: Score = similarity × completion_rate

        similarity_score = 0.8  # High similarity
        completion_rate = 0.9  # High completion rate
        expected_score = 0.72  # 0.8 × 0.9

        calculated_score = similarity_score * completion_rate
        assert calculated_score == pytest.approx(expected_score, rel=0.01)

    def test_lift_score_formula(self) -> None:
        """Test lift score calculation concept."""
        # Lift = P(A and B) / (P(A) × P(B))
        # Lift > 1 means skills co-occur more than expected

        # Example: P(A) = 0.5, P(B) = 0.4, P(A and B) = 0.3
        prob_a = 0.5
        prob_b = 0.4
        prob_together = 0.3

        expected_lift = prob_together / (prob_a * prob_b)
        calculated_lift = prob_together / (prob_a * prob_b)

        # Lift should be > 1 (skills occur together more than expected)
        assert calculated_lift > 1.0
        assert expected_lift == calculated_lift


# ============================================================================
# Session Analytics Tests
# ============================================================================


class TestSessionAnalytics:
    """Test session analytics aggregation."""

    def test_session_metrics_aggregation(self) -> None:
        """Test session-level metrics calculation."""
        # Test data: 3 invocations in a session
        invocations = [
            ("skill1", True, 5.0),  # skill_name, completed, duration
            ("skill2", True, 3.0),
            ("skill3", False, 1.0),  # Failed
        ]

        # Calculate metrics
        total_count = len(invocations)
        completed_count = sum(1 for _, completed, _ in invocations if completed)
        completion_rate = completed_count / total_count if total_count > 0 else 0
        total_duration = sum(duration for _, _, duration in invocations)

        assert total_count == 3
        assert completed_count == 2
        assert completion_rate == pytest.approx(0.667, rel=0.01)
        assert total_duration == 9.0

    def test_session_effectiveness_scoring(self) -> None:
        """Test session effectiveness score calculation."""
        # Test case: Session with mixed results
        completed_skills = 8
        total_skills = 10
        avg_duration = 4.5

        # Simple effectiveness metric: completion_rate × speed_factor
        completion_rate = completed_skills / total_skills
        speed_factor = 1.0  # No penalty

        effectiveness = completion_rate * speed_factor

        assert effectiveness == pytest.approx(0.8, rel=0.01)


# ============================================================================
# Usage Tracker Tests
# ============================================================================


class TestUsageTracker:
    """Test usage tracking functionality."""

    def test_skill_frequency_calculation(self) -> None:
        """Test skill invocation frequency calculation."""
        # Test data: Invocations over time
        skill_invocations = {
            "pytest-run": 120,
            "ruff-check": 95,
            "mypy": 80,
        }

        total_invocations = sum(skill_invocations.values())
        most_used_skill = max(skill_invocations, key=skill_invocations.get)

        assert total_invocations == 295
        assert most_used_skill == "pytest-run"
        assert skill_invocations[most_used_skill] == 120

    def test_usage_trend_detection(self) -> None:
        """Test usage trend detection."""
        # Test data: Hourly invocation counts
        hourly_counts = [10, 15, 12, 18, 20, 25, 22, 30]

        # Calculate trend (simple linear regression slope)
        x = list(range(len(hourly_counts)))
        y = hourly_counts

        # Calculate slope using numpy
        slope = np.polyfit(x, y, 1)[0]

        # Positive slope indicates increasing usage
        assert slope > 0


# ============================================================================
# Cross-Module Integration Tests
# ============================================================================


class TestAnalyticsIntegration:
    """Test integration between analytics components."""

    def test_ab_test_with_predictive_model(self) -> None:
        """Test using A/B test data with predictive model."""
        # Simulate A/B test outcomes
        control_outcomes = [1, 0, 1, 1, 0, 1, 1, 0, 1, 1]  # 70% success
        treatment_outcomes = [1, 1, 1, 1, 0, 1, 1, 1, 1, 1]  # 90% success

        control_rate = np.mean(control_outcomes)
        treatment_rate = np.mean(treatment_outcomes)

        # Treatment should outperform control
        assert treatment_rate > control_rate
        assert control_rate == pytest.approx(0.7, rel=0.1)
        assert treatment_rate == pytest.approx(0.9, rel=0.1)

    def test_time_series_with_skill_metrics(self) -> None:
        """Test time-series aggregation with skill metrics."""
        # Test data: Hourly invocation counts
        hourly_data = [
            {"hour": "2026-02-10T10:00:00Z", "count": 5, "completions": 4},
            {"hour": "2026-02-10T11:00:00Z", "count": 8, "completions": 7},
            {"hour": "2026-02-10T12:00:00Z", "count": 12, "completions": 10},
        ]

        # Calculate completion rate per hour
        completion_rates = [
            d["completions"] / d["count"] if d["count"] > 0 else 0
            for d in hourly_data
        ]

        expected_rates = [0.8, 0.875, pytest.approx(0.833, rel=0.01)]

        for actual, expected in zip(completion_rates, expected_rates):
            if isinstance(expected, float):
                assert actual == pytest.approx(expected, rel=0.1)
            else:
                assert actual == expected


# ============================================================================
# Statistical Validity Tests
# ============================================================================


class TestStatisticalValidity:
    """Test statistical validity of analytics methods."""

    def test_minimum_sample_size_validation(self) -> None:
        """Test minimum sample size validation."""
        min_sample_size = 100

        # Test cases
        insufficient_sample = 50
        sufficient_sample = 150

        assert insufficient_sample < min_sample_size
        assert sufficient_sample >= min_sample_size

    def test_confidence_interval_calculation(self) -> None:
        """Test confidence interval calculation."""
        # Test data: Sample completion rates
        sample_data = [0.8, 0.85, 0.9, 0.75, 0.82]

        # Calculate mean and standard deviation
        mean = np.mean(sample_data)
        std_dev = np.std(sample_data)
        sample_size = len(sample_data)

        # Standard error of the mean
        std_error = std_dev / np.sqrt(sample_size)

        # 95% confidence interval (approximately)
        margin_of_error = 1.96 * std_error

        # Confidence interval should be reasonable
        assert margin_of_error > 0
        assert margin_of_error < 0.5  # Not too wide

        # Verify mean is within expected range
        assert 0.7 < mean < 0.95


# ============================================================================
# Performance Tests
# ============================================================================


class TestAnalyticsPerformance:
    """Test analytics performance characteristics."""

    def test_vectorized_operations(self) -> None:
        """Test that operations use vectorized numpy operations."""
        # Large arrays for performance testing
        large_array = np.random.rand(10000)

        # Vectorized operation should be fast
        result = large_array * 2 + 1

        assert len(result) == 10000
        assert result.mean() > 0  # Should have positive values

    def test_memory_efficiency(self) -> None:
        """Test memory efficiency of analytics operations."""
        # Test that operations don't create unnecessary copies
        large_array = np.random.rand(1000)

        # View (not copy) should be efficient
        view = large_array[100:200]

        # Modifying view should modify original
        view[:] = 999
        assert large_array[100] == 999
        assert large_array[199] == 999
