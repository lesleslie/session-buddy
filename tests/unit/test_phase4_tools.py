"""Tests for Phase 4 Skills Analytics tools.

This module provides tests for:
- Real-time skill metrics and monitoring
- Performance anomaly detection
- Skill trend analysis over time
- Collaborative filtering recommendations
- Community baseline comparisons
- Skill dependency analysis
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from session_buddy.mcp.tools.skills.phase4_tools import (
    register_phase4_tools,
    get_real_time_metrics,
    detect_anomalies,
    get_skill_trend,
    get_collaborative_recommendations,
    get_community_baselines,
    get_skill_dependencies,
)


class TestRegisterPhase4Tools:
    """Tests for register_phase4_tools function."""

    def test_register_phase4_tools_calls_tool_decorator_six_times(self):
        """Verify all 6 Phase 4 tools are registered with MCP server."""
        mock_mcp = MagicMock()
        register_phase4_tools(mock_mcp)
        assert mock_mcp.tool.call_count == 6

    def test_register_phase4_tools_registers_correct_functions(self):
        """Verify all 6 Phase 4 tool functions are registered via the decorator."""
        mock_mcp = MagicMock()
        register_phase4_tools(mock_mcp)

        # The decorator is called 6 times, once for each tool function
        assert mock_mcp.tool.call_count == 6


class TestGetRealTimeMetrics:
    """Tests for get_real_time_metrics function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage with real-time metrics."""
        storage = MagicMock()
        storage.get_real_time_metrics.return_value = [
            {
                "skill_name": "pytest-run",
                "invocation_count": 42,
                "completed_count": 38,
                "avg_duration": 45.2,
                "last_invocation_at": "2026-02-10T12:00:00Z",
            },
            {
                "skill_name": "ruff-check",
                "invocation_count": 35,
                "completed_count": 33,
                "avg_duration": 12.5,
                "last_invocation_at": "2026-02-10T11:30:00Z",
            },
        ]
        return storage

    @pytest.mark.asyncio
    async def test_get_real_time_metrics_success(self, mock_storage):
        """Test successful retrieval of real-time metrics."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_real_time_metrics(limit=10, time_window_hours=1.0)

        assert result["success"] is True
        assert len(result["top_skills"]) == 2
        assert result["top_skills"][0]["skill_name"] == "pytest-run"
        assert result["top_skills"][0]["invocation_count"] == 42
        assert "timestamp" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_get_real_time_metrics_with_custom_limit(self, mock_storage):
        """Test real-time metrics with custom limit parameter."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_real_time_metrics(limit=5, time_window_hours=24.0)

        mock_storage.get_real_time_metrics.assert_called_once_with(
            limit=5, time_window_hours=24.0
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_real_time_metrics_empty_results(self):
        """Test handling of empty metrics."""
        mock_storage = MagicMock()
        mock_storage.get_real_time_metrics.return_value = []

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_real_time_metrics(limit=10)

        assert result["success"] is True
        assert result["top_skills"] == []
        assert "0 skills" in result["message"]

    @pytest.mark.asyncio
    async def test_get_real_time_metrics_handles_exception(self):
        """Test error handling when storage fails."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            side_effect=Exception("Database connection failed"),
        ):
            result = await get_real_time_metrics()

        assert result["success"] is False
        assert result["top_skills"] == []
        assert "Database connection failed" in result["message"]


class TestDetectAnomalies:
    """Tests for detect_anomalies function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage with anomalies."""
        storage = MagicMock()
        storage.detect_anomalies.return_value = [
            {
                "skill_name": "ruff-check",
                "anomaly_type": "performance_drop",
                "baseline_value": 0.92,
                "observed_value": 0.65,
                "deviation_score": -2.7,
            },
            {
                "skill_name": "coverage-report",
                "anomaly_type": "performance_spike",
                "baseline_value": 0.75,
                "observed_value": 0.98,
                "deviation_score": 3.2,
            },
        ]
        return storage

    @pytest.mark.asyncio
    async def test_detect_anomalies_success(self, mock_storage):
        """Test successful anomaly detection."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await detect_anomalies(threshold=2.0, time_window_hours=24.0)

        assert result["success"] is True
        assert len(result["anomalies"]) == 2
        assert result["anomalies"][0]["anomaly_type"] == "performance_drop"
        assert result["anomalies"][0]["skill_name"] == "ruff-check"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_detect_anomalies_with_custom_threshold(self, mock_storage):
        """Test anomaly detection with custom Z-score threshold."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await detect_anomalies(threshold=2.5, time_window_hours=48.0)

        mock_storage.detect_anomalies.assert_called_once_with(
            threshold=2.5, time_window_hours=48.0
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_detect_anomalies_no_anomalies_found(self):
        """Test when no anomalies are detected."""
        mock_storage = MagicMock()
        mock_storage.detect_anomalies.return_value = []

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await detect_anomalies(threshold=3.0)

        assert result["success"] is True
        assert result["anomalies"] == []
        assert "0 anomaly(ies)" in result["message"]

    @pytest.mark.asyncio
    async def test_detect_anomalies_handles_exception(self):
        """Test error handling when anomaly detection fails."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            side_effect=Exception("Analysis error"),
        ):
            result = await detect_anomalies()

        assert result["success"] is False
        assert result["anomalies"] == []
        assert "Analysis error" in result["message"]


class TestGetSkillTrend:
    """Tests for get_skill_trend function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage."""
        storage = MagicMock()
        storage.db_path = ":memory:"
        return storage

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock time series analyzer."""
        analyzer = MagicMock()
        analyzer.detect_trend.return_value = MagicMock(
            trend="improving",
            slope=0.0123,
            start_value=0.75,
            end_value=0.82,
            change_percent=9.3,
            confidence=0.04,
        )
        return analyzer

    @pytest.mark.asyncio
    async def test_get_skill_trend_success(self, mock_storage, mock_analyzer):
        """Test successful skill trend analysis."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.time_series.TimeSeriesAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await get_skill_trend("pytest-run", days=7)

        assert result["success"] is True
        assert result["skill_name"] == "pytest-run"
        assert result["trend"] == "improving"
        assert result["slope"] == 0.0123
        assert result["start_value"] == 0.75
        assert result["end_value"] == 0.82
        assert result["change_percent"] == 9.3
        assert result["confidence"] == 0.04

    @pytest.mark.asyncio
    async def test_get_skill_trend_declining(self, mock_storage, mock_analyzer):
        """Test declining trend detection."""
        mock_analyzer.detect_trend.return_value.trend = "declining"
        mock_analyzer.detect_trend.return_value.slope = -0.015
        mock_analyzer.detect_trend.return_value.change_percent = -12.5

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.time_series.TimeSeriesAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await get_skill_trend("coverage-report", days=30)

        assert result["success"] is True
        assert result["trend"] == "declining"
        assert result["slope"] == -0.015
        assert result["change_percent"] == -12.5

    @pytest.mark.asyncio
    async def test_get_skill_trend_stable(self, mock_storage, mock_analyzer):
        """Test stable trend detection."""
        mock_analyzer.detect_trend.return_value.trend = "stable"
        mock_analyzer.detect_trend.return_value.slope = 0.001

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.time_series.TimeSeriesAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await get_skill_trend("ruff-check", days=7)

        assert result["success"] is True
        assert result["trend"] == "stable"

    @pytest.mark.asyncio
    async def test_get_skill_trend_insufficient_data(self, mock_storage, mock_analyzer):
        """Test handling of insufficient data."""
        mock_analyzer.detect_trend.return_value.trend = "insufficient_data"
        mock_analyzer.detect_trend.return_value.slope = 0.0

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.time_series.TimeSeriesAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await get_skill_trend("new-skill", days=90)

        assert result["success"] is True
        assert result["trend"] == "insufficient_data"

    @pytest.mark.asyncio
    async def test_get_skill_trend_handles_exception(self, mock_storage):
        """Test error handling when trend analysis fails."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.time_series.TimeSeriesAnalyzer",
                side_effect=Exception("Analysis engine error"),
            ):
                result = await get_skill_trend("pytest-run")

        assert result["success"] is False
        assert result["skill_name"] == "pytest-run"
        assert result["trend"] == "error"
        assert "error" in result


class TestGetCollaborativeRecommendations:
    """Tests for get_collaborative_recommendations function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage."""
        storage = MagicMock()
        storage.db_path = ":memory:"
        return storage

    @pytest.fixture
    def mock_engine(self):
        """Create mock collaborative filtering engine."""
        engine = MagicMock()
        engine.recommend_from_similar_users.return_value = [
            {
                "skill_name": "coverage-report",
                "score": 0.87,
                "completion_rate": 0.91,
                "source": "collaborative_filtering",
                "similar_user_id": "user-456",
            },
            {
                "skill_name": "ruff-format",
                "score": 0.82,
                "completion_rate": 0.88,
                "source": "collaborative_filtering",
                "similar_user_id": "user-789",
            },
        ]
        engine.get_global_fallback_recommendations.return_value = []
        return engine

    @pytest.mark.asyncio
    async def test_get_collaborative_recommendations_success(
        self, mock_storage, mock_engine
    ):
        """Test successful collaborative filtering recommendations."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.collaborative_filtering.get_collaborative_engine",
                return_value=mock_engine,
            ):
                result = await get_collaborative_recommendations("user-123", limit=5)

        assert result["success"] is True
        assert result["user_id"] == "user-123"
        assert len(result["recommendations"]) == 2
        assert result["recommendations"][0]["skill_name"] == "coverage-report"
        assert result["recommendations"][0]["score"] == 0.87
        assert "similar_user_id" not in result["recommendations"][0]
        assert result["recommendations"][0]["source"] == "collaborative_filtering"

    @pytest.mark.asyncio
    async def test_get_collaborative_recommendations_fallback(
        self, mock_storage, mock_engine
    ):
        """Test fallback to global recommendations when no collaborative results."""
        mock_engine.recommend_from_similar_users.return_value = []
        mock_engine.get_global_fallback_recommendations.return_value = [
            {
                "skill_name": "pytest-run",
                "score": 0.75,
                "completion_rate": 0.85,
                "source": "global_fallback",
            }
        ]

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.collaborative_filtering.get_collaborative_engine",
                return_value=mock_engine,
            ):
                result = await get_collaborative_recommendations("new-user", limit=5)

        assert result["success"] is True
        assert len(result["recommendations"]) == 1
        mock_engine.get_global_fallback_recommendations.assert_called_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_get_collaborative_recommendations_handles_exception(
        self, mock_storage
    ):
        """Test error handling when collaborative filtering fails."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            with patch(
                "session_buddy.analytics.collaborative_filtering.get_collaborative_engine",
                side_effect=Exception("Collaborative engine error"),
            ):
                result = await get_collaborative_recommendations("user-123")

        assert result["success"] is False
        assert result["user_id"] == "user-123"
        assert result["recommendations"] == []
        assert "Collaborative engine error" in result["message"]


class TestGetCommunityBaselines:
    """Tests for get_community_baselines function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage with baselines."""
        storage = MagicMock()
        storage.get_community_baselines.return_value = [
            {
                "skill_name": "pytest-run",
                "total_users": 15,
                "total_invocations": 342,
                "global_completion_rate": 0.88,
                "effectiveness_percentile": 75.3,
            },
            {
                "skill_name": "ruff-check",
                "total_users": 12,
                "total_invocations": 256,
                "global_completion_rate": 0.92,
                "effectiveness_percentile": 82.1,
            },
        ]
        return storage

    @pytest.mark.asyncio
    async def test_get_community_baselines_success(self, mock_storage):
        """Test successful retrieval of community baselines."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_community_baselines(limit=20)

        assert result["success"] is True
        assert len(result["baselines"]) == 2
        assert result["baselines"][0]["skill_name"] == "pytest-run"
        assert result["baselines"][0]["total_users"] == 15
        assert result["baselines"][0]["global_completion_rate"] == 0.88
        assert result["baselines"][0]["effectiveness_percentile"] == 75.3

    @pytest.mark.asyncio
    async def test_get_community_baselines_respects_limit(self, mock_storage):
        """Test that limit parameter is respected."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_community_baselines(limit=1)

        assert result["success"] is True
        assert len(result["baselines"]) == 1

    @pytest.mark.asyncio
    async def test_get_community_baselines_empty_results(self):
        """Test handling of empty baselines."""
        mock_storage = MagicMock()
        mock_storage.get_community_baselines.return_value = []

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_community_baselines()

        assert result["success"] is True
        assert result["baselines"] == []
        assert "0 community baselines" in result["message"]

    @pytest.mark.asyncio
    async def test_get_community_baselines_handles_exception(self):
        """Test error handling when baseline retrieval fails."""
        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            side_effect=Exception("Database error"),
        ):
            result = await get_community_baselines()

        assert result["success"] is False
        assert result["baselines"] == []
        assert "Database error" in result["message"]


class TestGetSkillDependencies:
    """Tests for get_skill_dependencies function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage with dependencies."""
        storage = MagicMock()
        storage.update_skill_dependencies = MagicMock()
        return storage

    @pytest.fixture
    def mock_connection(self):
        """Create mock database connection."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {"related_skill": "ruff-check", "co_occurrence_count": 45, "lift_score": 2.3},
            {"related_skill": "ruff-format", "co_occurrence_count": 38, "lift_score": 1.8},
            {"related_skill": "coverage-report", "co_occurrence_count": 25, "lift_score": 3.5},
        ]
        conn.cursor.return_value = cursor
        conn.row_factory = None
        return conn

    @pytest.mark.asyncio
    async def test_get_skill_dependencies_success(self, mock_storage, mock_connection):
        """Test successful retrieval of skill dependencies."""
        mock_storage._get_connection.return_value.__enter__ = MagicMock(
            return_value=mock_connection
        )
        mock_storage._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_skill_dependencies("pytest-run", limit=10, min_lift=1.5)

        assert result["success"] is True
        assert result["skill_name"] == "pytest-run"
        assert len(result["dependencies"]) == 3
        assert result["dependencies"][0]["skill_b"] == "ruff-check"
        assert result["dependencies"][0]["lift_score"] == 2.3
        assert result["dependencies"][0]["relationship_type"] == "strong_positive"
        assert result["dependencies"][1]["relationship_type"] == "moderate_positive"
        assert result["dependencies"][2]["relationship_type"] == "very_strong_positive"

    @pytest.mark.asyncio
    async def test_get_skill_dependencies_categorizes_relationships_correctly(
        self, mock_storage, mock_connection
    ):
        """Test relationship categorization based on lift scores."""
        mock_connection.cursor.return_value.fetchall.return_value = [
            {"related_skill": "very-strong", "co_occurrence_count": 50, "lift_score": 3.5},
            {"related_skill": "strong", "co_occurrence_count": 40, "lift_score": 2.5},
            {"related_skill": "moderate", "co_occurrence_count": 30, "lift_score": 1.7},
            {"related_skill": "weak", "co_occurrence_count": 20, "lift_score": 1.1},
        ]

        mock_storage._get_connection.return_value.__enter__ = MagicMock(
            return_value=mock_connection
        )
        mock_storage._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_skill_dependencies("pytest-run")

        deps = result["dependencies"]
        assert deps[0]["relationship_type"] == "very_strong_positive"
        assert deps[1]["relationship_type"] == "strong_positive"
        assert deps[2]["relationship_type"] == "moderate_positive"
        assert deps[3]["relationship_type"] == "weak_positive"

    @pytest.mark.asyncio
    async def test_get_skill_dependencies_respects_limit(self, mock_storage, mock_connection):
        """Test that limit parameter is respected."""
        mock_storage._get_connection.return_value.__enter__ = MagicMock(
            return_value=mock_connection
        )
        mock_storage._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_skill_dependencies("pytest-run", limit=2)

        assert len(result["dependencies"]) == 2

    @pytest.mark.asyncio
    async def test_get_skill_dependencies_no_dependencies_found(
        self, mock_storage, mock_connection
    ):
        """Test handling when no dependencies are found."""
        mock_connection.cursor.return_value.fetchall.return_value = []
        mock_storage._get_connection.return_value.__enter__ = MagicMock(
            return_value=mock_connection
        )
        mock_storage._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_skill_dependencies("unused-skill")

        assert result["success"] is True
        assert result["dependencies"] == []
        assert "0 skills" in result["message"]

    @pytest.mark.asyncio
    async def test_get_skill_dependencies_handles_exception(self, mock_storage):
        """Test error handling when dependency analysis fails."""
        mock_storage._get_connection.return_value.__enter__ = MagicMock(
            side_effect=Exception("Database error")
        )
        mock_storage._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            result = await get_skill_dependencies("pytest-run")

        assert result["success"] is False
        assert result["skill_name"] == "pytest-run"
        assert result["dependencies"] == []
        assert "Database error" in result["message"]

    @pytest.mark.asyncio
    async def test_get_skill_dependencies_calls_update(self, mock_storage, mock_connection):
        """Test that update_skill_dependencies is called before querying."""
        mock_storage._get_connection.return_value.__enter__ = MagicMock(
            return_value=mock_connection
        )
        mock_storage._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "session_buddy.storage.skills_storage.get_storage",
            return_value=mock_storage,
        ):
            await get_skill_dependencies("pytest-run", min_lift=2.0)

        mock_storage.update_skill_dependencies.assert_called_once_with(min_co_occurrence=3)


class TestPhase4ToolsIntegration:
    """Integration tests for Phase 4 tools as a group."""

    def test_all_functions_are_async(self):
        """Verify all tool functions are async functions."""
        async_functions = [
            get_real_time_metrics,
            detect_anomalies,
            get_skill_trend,
            get_collaborative_recommendations,
            get_community_baselines,
            get_skill_dependencies,
        ]
        for func in async_functions:
            import inspect
            assert inspect.iscoroutinefunction(func), f"{func.__name__} should be async"

    def test_all_functions_have_proper_signatures(self):
        """Verify all tool functions have proper async signatures."""
        # These functions are async, so we can't test returns directly without mocks
        # but we can verify their structure
        import inspect

        for func in [
            get_real_time_metrics,
            detect_anomalies,
            get_skill_trend,
            get_collaborative_recommendations,
            get_community_baselines,
            get_skill_dependencies,
        ]:
            sig = inspect.signature(func)
            # Verify they have return annotation
            assert sig.return_annotation != inspect.Parameter.empty

    @pytest.mark.asyncio
    async def test_all_functions_handle_exceptions_gracefully(self):
        """Test that all functions handle exceptions and return error dicts."""
        functions_to_test = [
            (get_real_time_metrics, {}),
            (detect_anomalies, {}),
            (get_skill_trend, {"skill_name": "test"}),
            (get_collaborative_recommendations, {"user_id": "test"}),
            (get_community_baselines, {}),
            (get_skill_dependencies, {"skill_name": "test"}),
        ]

        for func, kwargs in functions_to_test:
            with patch(
                "session_buddy.storage.skills_storage.get_storage",
                side_effect=Exception("Simulated failure"),
            ):
                result = await func(**kwargs)
                assert isinstance(result, dict), f"{func.__name__} should return dict"
                assert result.get("success") is False, f"{func.__name__} should return success=False"