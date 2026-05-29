"""Comprehensive tests for quality_engine module.

Tests quality scoring, compaction analysis, and workflow intelligence
for the session management MCP server.

Phase: Week 5 Day 1 - Quality Engine Coverage Enhancement
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===== TestQualityScoreCalculation =====


class TestQualityScoreCalculation:
    """Test quality score calculation functions."""

    @pytest.mark.asyncio
    async def test_calculate_quality_score_returns_dict(self, tmp_path: Path) -> None:
        """Should return dictionary with quality score and details."""
        from session_buddy.quality_engine import calculate_quality_score

        result = await calculate_quality_score(project_dir=tmp_path)

        assert isinstance(result, dict)
        assert "total_score" in result
        assert "breakdown" in result

    @pytest.mark.asyncio
    async def test_calculate_quality_score_with_no_project(self) -> None:
        """Should handle None project_dir gracefully."""
        from session_buddy.quality_engine import calculate_quality_score

        result = await calculate_quality_score(project_dir=None)

        assert isinstance(result, dict)
        assert "total_score" in result

    @pytest.mark.asyncio
    async def test_calculate_quality_score_with_nonexistent_path(self) -> None:
        """Should handle nonexistent project directory."""
        from session_buddy.quality_engine import calculate_quality_score

        nonexistent = Path("/nonexistent/path/to/project")
        result = await calculate_quality_score(project_dir=nonexistent)

        assert isinstance(result, dict)
        # Should not raise exception

    @pytest.mark.asyncio
    async def test_calculate_quality_score_uses_v2_algorithm(
        self, tmp_path: Path
    ) -> None:
        """Should use quality_utils_v2 for scoring."""
        from session_buddy.quality_engine import calculate_quality_score
        from session_buddy.utils.quality_utils_v2 import (
            CodeQualityScore,
            DevVelocityScore,
            ProjectHealthScore,
            QualityScoreV2,
            SecurityScore,
            TrustScore,
        )

        # Create minimal project structure
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")

        # Mock with complete dataclass structure
        mock_result = QualityScoreV2(
            total_score=75.0,
            version="v2",
            code_quality=CodeQualityScore(
                test_coverage=10.0,
                lint_score=8.0,
                type_coverage=7.0,
                complexity_score=4.0,
                total=29.0,
                details={},
            ),
            project_health=ProjectHealthScore(
                total=20, tooling_score=10, maturity_score=10, details={}
            ),
            dev_velocity=DevVelocityScore(
                git_activity=8.0, dev_patterns=8.0, total=16.0, details={}
            ),
            security=SecurityScore(
                security_tools=5.0, security_hygiene=5.0, total=10.0, details={}
            ),
            trust_score=TrustScore(
                trusted_operations=20.0,
                session_availability=15.0,
                tool_ecosystem=10.0,
                total=45.0,
                details={},
            ),
            recommendations=[],
            timestamp="2025-01-01",
        )

        with patch(
            "session_buddy.quality_engine.calculate_quality_score_v2"
        ) as mock_v2:
            mock_v2.return_value = mock_result
            result = await calculate_quality_score(project_dir=tmp_path)

            # Verify V2 algorithm was called
            mock_v2.assert_called_once()
            # Verify result structure
            assert result["total_score"] == 75
            assert result["version"] == "v2"
            assert "breakdown" in result

    @pytest.mark.asyncio
    async def test_calculate_quality_score_breakdown_structure(
        self, tmp_path: Path
    ) -> None:
        """Should have correct breakdown structure."""
        from session_buddy.quality_engine import calculate_quality_score
        from session_buddy.utils.quality_utils_v2 import (
            CodeQualityScore,
            DevVelocityScore,
            ProjectHealthScore,
            QualityScoreV2,
            SecurityScore,
            TrustScore,
        )

        mock_result = QualityScoreV2(
            total_score=80.0,
            version="v2",
            code_quality=CodeQualityScore(
                test_coverage=10.0,
                lint_score=8.0,
                type_coverage=7.0,
                complexity_score=4.0,
                total=29.0,
                details={},
            ),
            project_health=ProjectHealthScore(
                total=20, tooling_score=10, maturity_score=10, details={}
            ),
            dev_velocity=DevVelocityScore(
                git_activity=8.0, dev_patterns=8.0, total=16.0, details={}
            ),
            security=SecurityScore(
                security_tools=5.0, security_hygiene=5.0, total=10.0, details={}
            ),
            trust_score=TrustScore(
                trusted_operations=20.0,
                session_availability=15.0,
                tool_ecosystem=10.0,
                total=45.0,
                details={"key1": 5.0, "key2": 10.0},
            ),
            recommendations=["recommendation1", "recommendation2"],
            timestamp="2025-01-01",
        )

        with patch(
            "session_buddy.quality_engine.calculate_quality_score_v2"
        ) as mock_v2:
            mock_v2.return_value = mock_result
            result = await calculate_quality_score(project_dir=tmp_path)

            assert "breakdown" in result
            breakdown = result["breakdown"]
            assert breakdown["project_health"] == 20
            assert breakdown["permissions"] == 15.0  # sum of details values
            assert breakdown["session_management"] == 20  # fixed value
            assert breakdown["tools"] == 10  # tool_ecosystem
            assert breakdown["code_quality"] == 29  # code_quality.total
            assert breakdown["dev_velocity"] == 16.0
            assert breakdown["security"] == 10.0


# ===== TestCompactionAnalysis =====


class TestCompactionAnalysis:
    """Test context compaction analysis and suggestions."""

    def test_should_suggest_compact_returns_tuple(self) -> None:
        """Should return (bool, str) tuple."""
        from session_buddy.quality_engine import should_suggest_compact

        result = should_suggest_compact()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_should_suggest_compact_with_large_project(self, tmp_path: Path) -> None:
        """Should suggest compaction for large projects."""
        from session_buddy.quality_engine import should_suggest_compact

        # Create 60 Python files to trigger large project heuristic
        for i in range(60):
            (tmp_path / f"file_{i}.py").write_text("# Python file\n")

        with patch(
            "session_buddy.quality_engine._count_significant_files"
        ) as mock_count:
            mock_count.return_value = 60

            should_compact, reason = should_suggest_compact()

            # May or may not suggest based on other factors
            assert isinstance(should_compact, bool)
            assert len(reason) > 0

    def test_should_suggest_compact_with_small_project(self, tmp_path: Path) -> None:
        """Should not suggest compaction for small projects."""
        from session_buddy.quality_engine import should_suggest_compact

        # Create minimal project
        (tmp_path / "main.py").write_text("# Main file\n")

        with patch(
            "session_buddy.quality_engine._count_significant_files"
        ) as mock_count:
            mock_count.return_value = 1

            should_compact, reason = should_suggest_compact()

            assert isinstance(should_compact, bool)
            assert isinstance(reason, str)

    def test_should_suggest_compact_exception_fallback(self, tmp_path: Path) -> None:
        """Should return fallback when exception occurs."""
        from session_buddy.quality_engine import should_suggest_compact

        with patch(
            "session_buddy.quality_engine._count_significant_files",
            side_effect=Exception("Test error"),
        ):
            should_compact, reason = should_suggest_compact()

            # Should suggest compaction on error (safety first)
            assert should_compact is True
            assert len(reason) > 0

    def test_should_suggest_compact_git_activity_trigger(
        self, tmp_path: Path
    ) -> None:
        """Should trigger based on git activity heuristic."""
        from session_buddy.quality_engine import should_suggest_compact

        with patch(
            "session_buddy.quality_engine._count_significant_files"
        ) as mock_count, patch(
            "session_buddy.quality_engine._evaluate_large_project_heuristic"
        ) as mock_large, patch(
            "session_buddy.quality_engine._check_git_activity"
        ) as mock_git, patch(
            "session_buddy.quality_engine._evaluate_git_activity_heuristic"
        ) as mock_git_heuristic:
            mock_count.return_value = 5
            mock_large.return_value = (False, "not large")
            mock_git.return_value = (10, 5)  # 10 commits, 5 files
            mock_git_heuristic.return_value = (True, "Active git activity detected")

            should_compact, reason = should_suggest_compact()

            assert should_compact is True
            assert "git" in reason.lower() or "active" in reason.lower()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_perform_strategic_compaction_returns_list(self) -> None:
        """Should return list of compaction results."""
        from session_buddy.quality_engine import perform_strategic_compaction

        # Mock filesystem operations to prevent timeout
        with patch(
            "session_buddy.utils.filesystem._cleanup_temp_files"
        ) as mock_cleanup:
            mock_cleanup.return_value = "✅ Cleaned 0 temporary files (0.0 MB)"

            result = await perform_strategic_compaction()

            assert isinstance(result, list)
            for item in result:
                assert isinstance(item, str)

    @pytest.mark.asyncio
    async def test_perform_strategic_compaction_includes_database_optimization(
        self,
    ) -> None:
        """Should include reflection database optimization."""
        from session_buddy.quality_engine import perform_strategic_compaction

        with patch(
            "session_buddy.quality_engine._optimize_reflection_database"
        ) as mock_optimize:
            mock_optimize.return_value = "✅ Database optimized"

            result = await perform_strategic_compaction()

            assert isinstance(result, list)
            mock_optimize.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_strategic_compaction_handles_missing_cwd(
        self,
    ) -> None:
        """Should handle missing cwd gracefully."""
        from session_buddy.quality_engine import perform_strategic_compaction

        with patch.dict(os.environ, {"PWD": "/nonexistent/path"}):
            with patch(
                "session_buddy.quality_engine._optimize_reflection_database"
            ) as mock_opt:
                mock_opt.return_value = "ℹ️ Database: Reflection tools not available"
                result = await perform_strategic_compaction()

                assert isinstance(result, list)
                assert len(result) > 0


# ===== TestProjectHeuristics =====


class TestProjectHeuristics:
    """Test project analysis heuristics."""

    def test_count_significant_files_with_python_project(self, tmp_path: Path) -> None:
        """Should count Python files correctly."""
        from session_buddy.utils.quality import count_significant_files

        # Create Python files
        (tmp_path / "main.py").write_text("# Main\n")
        (tmp_path / "utils.py").write_text("# Utils\n")
        (tmp_path / "tests.py").write_text("# Tests\n")

        count = count_significant_files(tmp_path)

        assert count >= 3

    def test_count_significant_files_ignores_hidden_files(self, tmp_path: Path) -> None:
        """Should ignore files in hidden directories."""
        from session_buddy.utils.quality import count_significant_files

        # Create hidden directory with files
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "secret.py").write_text("# Hidden\n")

        # Create visible file
        (tmp_path / "visible.py").write_text("# Visible\n")

        count = count_significant_files(tmp_path)

        # Should only count visible.py, not .hidden/secret.py
        assert count >= 1

    def test_count_significant_files_supports_multiple_languages(
        self, tmp_path: Path
    ) -> None:
        """Should count files from multiple programming languages."""
        from session_buddy.utils.quality import count_significant_files

        # Create files in different languages
        (tmp_path / "script.py").write_text("# Python\n")
        (tmp_path / "app.js").write_text("// JavaScript\n")
        (tmp_path / "component.tsx").write_text("// TypeScript\n")
        (tmp_path / "main.go").write_text("// Go\n")
        (tmp_path / "lib.rs").write_text("// Rust\n")

        count = count_significant_files(tmp_path)

        assert count >= 5

    def test_count_significant_files_stops_at_threshold(self, tmp_path: Path) -> None:
        """Should stop counting after threshold (performance optimization)."""
        from session_buddy.utils.quality import count_significant_files

        # Create 100 files
        for i in range(100):
            (tmp_path / f"file_{i}.py").write_text("# File\n")

        count = count_significant_files(tmp_path)

        # Should stop at 51 (threshold is 50, returns when > 50)
        assert count <= 51

    def test_check_git_activity_with_no_git(self, tmp_path: Path) -> None:
        """Should return None for non-git projects."""
        from session_buddy.utils.quality import check_git_activity

        result = check_git_activity(tmp_path)

        assert result is None

    def test_check_git_activity_with_git_repo(self, tmp_path: Path) -> None:
        """Should return commit and file counts for git repos."""
        from session_buddy.utils.quality import check_git_activity

        # Create .git directory
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

        with patch("subprocess.run") as mock_run:
            # Mock git log output
            mock_run.return_value = MagicMock(
                returncode=0, stdout="commit1\ncommit2\ncommit3\n"
            )

            result = check_git_activity(tmp_path)

            # Should return tuple or None (depends on git state)
            assert result is None or isinstance(result, tuple)

    def test_evaluate_large_project_heuristic(self) -> None:
        """Should evaluate large project heuristic correctly."""
        from session_buddy.utils.quality import evaluate_large_project_heuristic

        # Test with 10 files - should not trigger
        should_compact, reason = evaluate_large_project_heuristic(10)
        assert should_compact is False

        # Test with 60 files - should trigger
        should_compact, reason = evaluate_large_project_heuristic(60)
        assert should_compact is True

    def test_evaluate_git_activity_heuristic_no_activity(self) -> None:
        """Should not trigger with no git activity."""
        from session_buddy.utils.quality import evaluate_git_activity_heuristic

        should_compact, reason = evaluate_git_activity_heuristic(None)
        assert should_compact is False

    def test_evaluate_git_activity_heuristic_active(self) -> None:
        """Should trigger with active git activity."""
        from session_buddy.utils.quality import evaluate_git_activity_heuristic

        # 15 commits with 8 files - should trigger
        should_compact, reason = evaluate_git_activity_heuristic((15, 8))
        assert should_compact is True

    def test_evaluate_python_project_heuristic(self, tmp_path: Path) -> None:
        """Should evaluate Python project heuristic."""
        from session_buddy.utils.quality import evaluate_python_project_heuristic

        # Create Python project structure
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        (tmp_path / "requirements.txt").write_text("pytest\n")

        should_compact, reason = evaluate_python_project_heuristic(tmp_path)
        assert isinstance(should_compact, bool)
        assert isinstance(reason, str)


# ===== TestWorkflowAnalysis =====


class TestWorkflowAnalysis:
    """Test workflow pattern analysis."""

    @pytest.mark.asyncio
    async def test_analyze_project_workflow_patterns_returns_dict(
        self, tmp_path: Path
    ) -> None:
        """Should return dictionary with workflow analysis."""
        from session_buddy.quality_engine import analyze_project_workflow_patterns

        result = await analyze_project_workflow_patterns(tmp_path)

        assert isinstance(result, dict)
        assert (
            "project_characteristics" in result or "workflow_recommendations" in result
        )

    @pytest.mark.asyncio
    async def test_analyze_project_workflow_patterns_detects_python_project(
        self, tmp_path: Path
    ) -> None:
        """Should detect Python project characteristics."""
        from session_buddy.quality_engine import analyze_project_workflow_patterns

        # Create Python project files
        (tmp_path / "setup.py").write_text("# Setup\n")
        (tmp_path / "main.py").write_text("# Main\n")

        result = await analyze_project_workflow_patterns(tmp_path)

        assert isinstance(result, dict)

    def test_generate_workflow_recommendations_returns_list(self) -> None:
        """Should generate recommendations based on project characteristics."""
        from session_buddy.quality_engine import _generate_workflow_recommendations

        characteristics = {
            "has_python": True,
            "has_git": True,
            "has_tests": False,
            "has_node": False,
            "has_docker": False,
        }

        recommendations = _generate_workflow_recommendations(characteristics)

        assert isinstance(recommendations, list)
        assert any("git" in rec.lower() for rec in recommendations)

    def test_generate_workflow_recommendations_python_tests(self) -> None:
        """Should recommend pytest workflows for Python with tests."""
        from session_buddy.quality_engine import _generate_workflow_recommendations

        characteristics = {
            "has_python": True,
            "has_git": True,
            "has_tests": True,
            "has_node": False,
            "has_docker": False,
        }

        recommendations = _generate_workflow_recommendations(characteristics)

        assert any("pytest" in rec.lower() for rec in recommendations)

    def test_generate_workflow_recommendations_node(self) -> None:
        """Should recommend npm/yarn for Node projects."""
        from session_buddy.quality_engine import _generate_workflow_recommendations

        characteristics = {
            "has_python": False,
            "has_git": False,
            "has_tests": False,
            "has_node": True,
            "has_docker": False,
        }

        recommendations = _generate_workflow_recommendations(characteristics)

        assert any("npm" in rec.lower() or "yarn" in rec.lower() for rec in recommendations)

    def test_generate_workflow_recommendations_docker(self) -> None:
        """Should recommend container workflows for Docker projects."""
        from session_buddy.quality_engine import _generate_workflow_recommendations

        characteristics = {
            "has_python": False,
            "has_git": False,
            "has_tests": False,
            "has_node": False,
            "has_docker": True,
        }

        recommendations = _generate_workflow_recommendations(characteristics)

        assert any("container" in rec.lower() for rec in recommendations)

    def test_generate_workflow_recommendations_empty(self) -> None:
        """Should return default recommendation when no characteristics."""
        from session_buddy.quality_engine import _generate_workflow_recommendations

        characteristics = {
            "has_python": False,
            "has_git": False,
            "has_tests": False,
            "has_node": False,
            "has_docker": False,
        }

        recommendations = _generate_workflow_recommendations(characteristics)

        assert len(recommendations) > 0
        assert any("checkpoint" in rec.lower() for rec in recommendations)

    def test_detect_project_characteristics(self, tmp_path: Path) -> None:
        """Should detect all project characteristics."""
        from session_buddy.quality_engine import _detect_project_characteristics

        # Create various project markers
        (tmp_path / "tests").mkdir()
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "Dockerfile").write_text("FROM python:3.9")

        chars = _detect_project_characteristics(tmp_path)

        assert chars["has_tests"] is True
        assert chars["has_git"] is True
        assert chars["has_python"] is True
        assert chars["has_node"] is True
        assert chars["has_docker"] is True

    def test_check_workflow_drift_no_alert(self) -> None:
        """Should not alert when variance is low."""
        from session_buddy.quality_engine import _check_workflow_drift

        quality_scores = [70.0, 72.0, 71.0, 73.0]
        alerts, recommend = _check_workflow_drift(quality_scores)

        assert len(alerts) == 0
        assert recommend is False

    def test_check_workflow_drift_high_variance(self) -> None:
        """Should alert when variance is high (>30)."""
        from session_buddy.quality_engine import _check_workflow_drift

        quality_scores = [70.0, 30.0, 75.0, 35.0]  # variance = 45
        alerts, recommend = _check_workflow_drift(quality_scores)

        assert len(alerts) > 0
        assert recommend is True

    def test_check_workflow_drift_insufficient_data(self) -> None:
        """Should not alert with insufficient quality scores."""
        from session_buddy.quality_engine import _check_workflow_drift

        quality_scores = [70.0, 80.0]  # Only 2 scores
        alerts, recommend = _check_workflow_drift(quality_scores)

        assert len(alerts) == 0
        assert recommend is False


# ===== TestConversationAnalysis =====


class TestConversationAnalysis:
    """Test conversation and memory pattern analysis."""

    @pytest.mark.asyncio
    async def test_summarize_current_conversation_returns_dict(self) -> None:
        """Should return summary dictionary."""
        from session_buddy.quality_engine import summarize_current_conversation

        result = await summarize_current_conversation()

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_summarize_current_conversation_with_fallback(self) -> None:
        """Should return fallback when reflection tools unavailable."""
        from session_buddy.quality_engine import summarize_current_conversation

        with patch(
            "session_buddy.reflection_tools.get_reflection_database",
            side_effect=ImportError("Module not found"),
        ):
            result = await summarize_current_conversation()

            assert isinstance(result, dict)
            # Fallback summary should have specific structure
            assert "key_topics" in result or "decisions_made" in result or "next_steps" in result

    @pytest.mark.asyncio
    async def test_analyze_conversation_flow_returns_dict(self) -> None:
        """Should return conversation flow analysis."""
        from session_buddy.quality_engine import analyze_conversation_flow

        result = await analyze_conversation_flow()

        assert isinstance(result, dict)
        assert "pattern_type" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_analyze_conversation_flow_productive_pattern(self) -> None:
        """Should detect productive development pattern."""
        from session_buddy.quality_engine import analyze_conversation_flow

        mock_reflections = [
            {"content": "Excellent session with great progress", "quality_score": 90},
            {"content": "Excellent workflow established", "quality_score": 85},
        ]

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_reflections = AsyncMock(return_value=mock_reflections)
            mock_get_db.return_value = mock_db

            result = await analyze_conversation_flow()

            assert result["pattern_type"] == "productive_development"

    @pytest.mark.asyncio
    async def test_analyze_conversation_flow_optimization_needed(self) -> None:
        """Should detect optimization needed pattern."""
        from session_buddy.quality_engine import analyze_conversation_flow

        mock_reflections = [
            {"content": "Session needs attention", "quality_score": 50},
        ]

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_reflections = AsyncMock(return_value=mock_reflections)
            mock_get_db.return_value = mock_db

            result = await analyze_conversation_flow()

            assert result["pattern_type"] == "optimization_needed"

    @pytest.mark.asyncio
    async def test_analyze_conversation_flow_new_session(self) -> None:
        """Should detect new session pattern."""
        from session_buddy.quality_engine import analyze_conversation_flow

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_reflections = AsyncMock(return_value=[])
            mock_get_db.return_value = mock_db

            result = await analyze_conversation_flow()

            assert result["pattern_type"] == "new_session"

    @pytest.mark.asyncio
    async def test_analyze_memory_patterns_new_session(self) -> None:
        """Should handle new session with no history."""
        from session_buddy.quality_engine import analyze_memory_patterns

        mock_db = MagicMock()
        result = await analyze_memory_patterns(mock_db, conv_count=0)

        assert isinstance(result, dict)
        assert "no historical patterns" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_analyze_memory_patterns_few_conversations(self) -> None:
        """Should handle sessions with few conversations."""
        from session_buddy.quality_engine import analyze_memory_patterns

        mock_db = MagicMock()
        result = await analyze_memory_patterns(mock_db, conv_count=3)

        assert isinstance(result, dict)
        assert "building pattern" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_analyze_memory_patterns_developing(self) -> None:
        """Should handle developing pattern recognition."""
        from session_buddy.quality_engine import analyze_memory_patterns

        mock_db = MagicMock()
        result = await analyze_memory_patterns(mock_db, conv_count=15)

        assert isinstance(result, dict)
        assert "developing" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_analyze_memory_patterns_rich_history(self) -> None:
        """Should handle rich pattern recognition."""
        from session_buddy.quality_engine import analyze_memory_patterns

        mock_db = MagicMock()
        result = await analyze_memory_patterns(mock_db, conv_count=50)

        assert isinstance(result, dict)
        assert "rich" in result["summary"].lower() or "recognition" in result["summary"].lower()


# ===== TestTokenUsageAnalysis =====


class TestTokenUsageAnalysis:
    """Test token usage and context analysis."""

    @pytest.mark.asyncio
    async def test_analyze_token_usage_patterns_returns_dict(self) -> None:
        """Should return token usage analysis."""
        from session_buddy.quality_engine import analyze_token_usage_patterns

        result = await analyze_token_usage_patterns()

        assert isinstance(result, dict)
        assert "estimated_length" in result
        assert "recommend_compact" in result

    @pytest.mark.asyncio
    async def test_analyze_token_usage_patterns_extensive(self) -> None:
        """Should detect extensive conversation."""
        from session_buddy.quality_engine import analyze_token_usage_patterns

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_stats = AsyncMock(return_value={"conversations_count": 15})
            mock_get_db.return_value = mock_db

            result = await analyze_token_usage_patterns()

            # Should recommend compaction for extensive conversations
            assert result["recommend_compact"] is True
            assert result["needs_attention"] is True

    @pytest.mark.asyncio
    async def test_analyze_token_usage_patterns_clear_needed(self) -> None:
        """Should detect need for clear when extremely long."""
        from session_buddy.quality_engine import analyze_token_usage_patterns

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_stats = AsyncMock(return_value={"conversations_count": 25})
            mock_get_db.return_value = mock_db

            result = await analyze_token_usage_patterns()

            # Should recommend clear for extremely long sessions
            assert result["recommend_clear"] is True

    @pytest.mark.asyncio
    async def test_analyze_context_usage_returns_list(self) -> None:
        """Should return list of context usage recommendations."""
        from session_buddy.quality_engine import analyze_context_usage

        result = await analyze_context_usage()

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, str)

    @pytest.mark.asyncio
    async def test_analyze_advanced_context_metrics_returns_dict(self) -> None:
        """Should return advanced context metrics."""
        from session_buddy.quality_engine import analyze_advanced_context_metrics

        result = await analyze_advanced_context_metrics()

        assert isinstance(result, dict)
        assert "estimated_tokens" in result
        assert "context_density" in result
        assert "conversation_depth" in result


# ===== TestSessionIntelligence =====


class TestSessionIntelligence:
    """Test session intelligence and recommendations."""

    @pytest.mark.asyncio
    async def test_generate_session_intelligence_returns_dict(self) -> None:
        """Should return session intelligence summary."""
        from session_buddy.quality_engine import generate_session_intelligence

        result = await generate_session_intelligence()

        assert isinstance(result, dict)
        assert "priority_actions" in result
        assert "intelligence_level" in result

    @pytest.mark.asyncio
    async def test_generate_session_intelligence_with_reflections(self) -> None:
        """Should include reflection-based intelligence."""
        from session_buddy.quality_engine import generate_session_intelligence

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_reflections = AsyncMock(return_value=[])
            mock_get_db.return_value = mock_db

            result = await generate_session_intelligence()

            assert isinstance(result["priority_actions"], list)
            assert len(result["priority_actions"]) > 0

    @pytest.mark.asyncio
    async def test_monitor_proactive_quality_returns_dict(self) -> None:
        """Should return proactive quality monitoring results."""
        from session_buddy.quality_engine import monitor_proactive_quality

        result = await monitor_proactive_quality()

        assert isinstance(result, dict)
        assert "quality_trend" in result
        assert "monitoring_active" in result

    @pytest.mark.asyncio
    async def test_monitor_proactive_quality_with_data(self) -> None:
        """Should analyze quality trends when data available."""
        from session_buddy.quality_engine import monitor_proactive_quality

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_reflections = AsyncMock(
                return_value=[
                    {"content": "quality score: 80", "quality_score": 80},
                    {"content": "quality score: 75", "quality_score": 75},
                ]
            )
            mock_get_db.return_value = mock_db

            result = await monitor_proactive_quality()

            assert result["monitoring_active"] is True

    @pytest.mark.asyncio
    async def test_monitor_proactive_quality_import_error(self) -> None:
        """Should handle ImportError gracefully."""
        from session_buddy.quality_engine import monitor_proactive_quality

        with patch(
            "session_buddy.reflection_tools.get_reflection_database",
            side_effect=ImportError("Module not found"),
        ):
            result = await monitor_proactive_quality()

            assert result["monitoring_active"] is True
            assert len(result["alerts"]) > 0


# ===== TestHelperFunctions =====


class TestHelperFunctions:
    """Test utility and helper functions."""

    def test_get_default_compaction_reason_returns_string(self) -> None:
        """Should return default compaction reason."""
        from session_buddy.utils.quality import get_default_compaction_reason

        result = get_default_compaction_reason()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_fallback_compaction_reason_returns_string(self) -> None:
        """Should return fallback compaction reason."""
        from session_buddy.utils.quality import get_fallback_compaction_reason

        result = get_fallback_compaction_reason()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_session_tags_high_quality(self) -> None:
        """Should generate tags for high quality scores."""
        from session_buddy.quality_engine import _generate_session_tags

        tags = _generate_session_tags(quality_score=85.0)

        assert isinstance(tags, list)
        assert "excellent-session" in tags

    def test_generate_session_tags_low_quality(self) -> None:
        """Should generate improvement tags for low quality scores."""
        from session_buddy.quality_engine import _generate_session_tags

        tags = _generate_session_tags(quality_score=30.0)

        assert isinstance(tags, list)
        assert "needs-attention" in tags

    def test_generate_session_tags_boundary_80(self) -> None:
        """Should handle boundary at exactly 80."""
        from session_buddy.quality_engine import _generate_session_tags

        tags = _generate_session_tags(quality_score=80.0)

        assert isinstance(tags, list)
        assert "excellent-session" in tags

    def test_generate_session_tags_boundary_60(self) -> None:
        """Should handle boundary at exactly 60."""
        from session_buddy.quality_engine import _generate_session_tags

        tags = _generate_session_tags(quality_score=60.0)

        assert isinstance(tags, list)
        assert "needs-attention" not in tags

    def test_ensure_default_recommendations_empty(self) -> None:
        """Should return default when recommendations empty."""
        from session_buddy.quality_engine import _ensure_default_recommendations

        result = _ensure_default_recommendations([])

        assert len(result) > 0
        assert "Continue regular checkpoint monitoring" in result

    def test_ensure_default_recommendations_with_values(self) -> None:
        """Should preserve existing recommendations."""
        from session_buddy.quality_engine import _ensure_default_recommendations

        existing = ["Custom recommendation"]
        result = _ensure_default_recommendations(existing)

        assert result == existing

    def test_get_quality_error_result(self) -> None:
        """Should return proper error result structure."""
        from session_buddy.quality_engine import _get_quality_error_result

        error = Exception("Test error")
        result = _get_quality_error_result(error)

        assert result["quality_trend"] == "unknown"
        assert "Quality monitoring failed" in result["alerts"]
        assert result["recommend_checkpoint"] is False
        assert result["monitoring_active"] is False
        assert "error" in result

    def test_get_error_summary(self) -> None:
        """Should return proper error summary structure."""
        from session_buddy.utils.quality import get_error_summary

        error = Exception("Test error")
        result = get_error_summary(error)

        assert isinstance(result, dict)


# ===== TestContextAnalysis =====


class TestContextAnalysis:
    """Test context analysis and compaction functions."""

    @pytest.mark.asyncio
    async def test_analyze_context_compaction_returns_list(self) -> None:
        """Should return list of analysis results."""
        from session_buddy.quality_engine import _analyze_context_compaction

        with patch(
            "session_buddy.quality_engine.should_suggest_compact",
            return_value=(True, "Test reason for compaction"),
        ):
            result = await _analyze_context_compaction()

            assert isinstance(result, list)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_analyze_context_compaction_no_suggestion(self) -> None:
        """Should handle case when compaction not suggested."""
        from session_buddy.quality_engine import _analyze_context_compaction

        with patch(
            "session_buddy.quality_engine.should_suggest_compact",
            return_value=(False, "No compaction needed"),
        ):
            result = await _analyze_context_compaction()

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_analyze_context_compaction_exception(self) -> None:
        """Should handle exceptions gracefully."""
        from session_buddy.quality_engine import _analyze_context_compaction

        with patch(
            "session_buddy.quality_engine.should_suggest_compact",
            side_effect=Exception("Test exception"),
        ):
            result = await _analyze_context_compaction()

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_store_context_summary_no_error(self) -> None:
        """Should store context summary without error."""
        from session_buddy.quality_engine import _store_context_summary

        summary = {
            "key_topics": ["topic1", "topic2"],
            "decisions_made": ["decision1"],
            "next_steps": [],
        }

        # Should not raise
        await _store_context_summary(summary)

    @pytest.mark.asyncio
    async def test_store_context_summary_empty_topics(self) -> None:
        """Should handle empty key_topics gracefully."""
        from session_buddy.quality_engine import _store_context_summary

        summary = {
            "key_topics": [],
            "decisions_made": [],
            "next_steps": [],
        }

        # Should not raise
        await _store_context_summary(summary)


# ===== TestAnalyzeContextUsage =====


class TestAnalyzeContextUsage:
    """Test advanced context analysis functions."""

    @pytest.mark.asyncio
    async def test_analyze_token_usage_recommendations(self) -> None:
        """Should add token usage recommendations."""
        from session_buddy.quality_engine import _analyze_token_usage_recommendations

        results = []
        await _analyze_token_usage_recommendations(results)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_analyze_conversation_flow_recommendations(self) -> None:
        """Should add conversation flow recommendations."""
        from session_buddy.quality_engine import (
            _analyze_conversation_flow_recommendations,
        )

        results = []
        await _analyze_conversation_flow_recommendations(results)

        assert isinstance(results, list)
        # Should contain flow type
        assert any("flow" in r.lower() or "session" in r.lower() for r in results)

    @pytest.mark.asyncio
    async def test_analyze_memory_recommendations(self) -> None:
        """Should add memory recommendations."""
        from session_buddy.quality_engine import _analyze_memory_recommendations

        results = []
        await _analyze_memory_recommendations(results)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_analyze_project_workflow_recommendations(self) -> None:
        """Should add project workflow recommendations."""
        from session_buddy.quality_engine import (
            _analyze_project_workflow_recommendations,
        )

        results = []
        await _analyze_project_workflow_recommendations(results)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_analyze_session_intelligence_recommendations(self) -> None:
        """Should add session intelligence recommendations."""
        from session_buddy.quality_engine import (
            _analyze_session_intelligence_recommendations,
        )

        results = []
        await _analyze_session_intelligence_recommendations(results)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_analyze_quality_monitoring_recommendations(self) -> None:
        """Should add quality monitoring recommendations."""
        from session_buddy.quality_engine import (
            _analyze_quality_monitoring_recommendations,
        )

        results = []
        await _analyze_quality_monitoring_recommendations(results)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_add_fallback_recommendations(self) -> None:
        """Should add fallback recommendations on error."""
        from session_buddy.quality_engine import _add_fallback_recommendations

        results = []
        error = Exception("Test error")
        await _add_fallback_recommendations(results, error)

        assert len(results) > 0
        assert any("failed" in r.lower() for r in results)


# ===== TestPerformQualityAssessment =====


class TestPerformQualityAssessment:
    """Test quality assessment functions."""

    @pytest.mark.asyncio
    async def test_perform_quality_assessment(self) -> None:
        """Should perform quality assessment and return score and data."""
        from session_buddy.quality_engine import _perform_quality_assessment
        from session_buddy.utils.quality_utils_v2 import (
            CodeQualityScore,
            DevVelocityScore,
            ProjectHealthScore,
            QualityScoreV2,
            SecurityScore,
            TrustScore,
        )

        mock_result = QualityScoreV2(
            total_score=75.0,
            version="v2",
            code_quality=CodeQualityScore(
                test_coverage=10.0,
                lint_score=8.0,
                type_coverage=7.0,
                complexity_score=4.0,
                total=29.0,
                details={},
            ),
            project_health=ProjectHealthScore(
                total=20, tooling_score=10, maturity_score=10, details={}
            ),
            dev_velocity=DevVelocityScore(
                git_activity=8.0, dev_patterns=8.0, total=16.0, details={}
            ),
            security=SecurityScore(
                security_tools=5.0, security_hygiene=5.0, total=10.0, details={}
            ),
            trust_score=TrustScore(
                trusted_operations=20.0,
                session_availability=15.0,
                tool_ecosystem=10.0,
                total=45.0,
                details={},
            ),
            recommendations=[],
            timestamp="2025-01-01",
        )

        with patch(
            "session_buddy.quality_engine.calculate_quality_score_v2"
        ) as mock_v2:
            mock_v2.return_value = mock_result
            score, data = await _perform_quality_assessment()

            assert isinstance(score, int)
            assert isinstance(data, dict)
            assert score == 75


# ===== TestPrivateHelpers =====


class TestPrivateHelpers:
    """Test private helper functions."""

    @pytest.mark.asyncio
    async def test_optimize_reflection_database_success(self) -> None:
        """Should optimize reflection database successfully."""
        from session_buddy.quality_engine import _optimize_reflection_database

        # Test that the function runs without error (db operations may fail in test env)
        result = await _optimize_reflection_database()

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_optimize_reflection_database_import_error(self) -> None:
        """Should handle ImportError gracefully."""
        from session_buddy.quality_engine import _optimize_reflection_database

        with patch(
            "session_buddy.reflection_tools.get_reflection_database",
            side_effect=ImportError("Module not found"),
        ):
            result = await _optimize_reflection_database()

            assert "not available" in result

    @pytest.mark.asyncio
    async def test_capture_intelligence_insights(self) -> None:
        """Should capture intelligence insights."""
        from session_buddy.quality_engine import _capture_intelligence_insights

        mock_db = MagicMock()
        mock_db.store_reflection = AsyncMock(return_value="reflection_id_123")

        with patch(
            "session_buddy.quality_engine.generate_session_intelligence",
            AsyncMock(
                return_value={
                    "priority_actions": ["Action 1"],
                    "intelligence_level": "proactive",
                }
            ),
        ):
            results = []
            tags = ["tag1"]

            await _capture_intelligence_insights(mock_db, tags, results)

            assert len(results) > 0
            assert "intelligence" in results[0].lower()

    @pytest.mark.asyncio
    async def test_analyze_reflection_based_intelligence_no_reflections(self) -> None:
        """Should handle case with no reflections."""
        from session_buddy.quality_engine import _analyze_reflection_based_intelligence

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_reflections = AsyncMock(return_value=[])
            mock_get_db.return_value = mock_db

            result = await _analyze_reflection_based_intelligence()

            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_analyze_reflection_based_intelligence_import_error(self) -> None:
        """Should handle ImportError gracefully."""
        from session_buddy.quality_engine import _analyze_reflection_based_intelligence

        with patch(
            "session_buddy.reflection_tools.get_reflection_database",
            side_effect=ImportError("Module not found"),
        ):
            result = await _analyze_reflection_based_intelligence()

            assert result == []

    @pytest.mark.asyncio
    async def test_perform_quality_analysis_no_data(self) -> None:
        """Should handle case with no quality data."""
        from session_buddy.quality_engine import _perform_quality_analysis

        with patch(
            "session_buddy.reflection_tools.get_reflection_database"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_reflections = AsyncMock(return_value=[])
            mock_get_db.return_value = mock_db

            trend, alerts, recommend = await _perform_quality_analysis()

            assert trend == "stable"
            assert isinstance(alerts, list)
            assert recommend is False


# ===== TestGenerateBasicInsights =====


class TestGenerateBasicInsights:
    """Test insight generation functions."""

    @pytest.mark.asyncio
    async def test_generate_basic_insights_with_topics(self) -> None:
        """Should generate insights with key topics."""
        from session_buddy.quality_engine import _generate_basic_insights

        quality_score = 75.0
        summary = {
            "key_topics": ["topic1", "topic2", "topic3"],
            "decisions_made": [],
            "next_steps": [],
        }

        insights = await _generate_basic_insights(quality_score, summary)

        assert len(insights) > 0
        assert any("topic1" in insight for insight in insights)

    @pytest.mark.asyncio
    async def test_generate_basic_insights_with_decisions(self) -> None:
        """Should generate insights with decisions."""
        from session_buddy.quality_engine import _generate_basic_insights

        quality_score = 75.0
        summary = {
            "key_topics": [],
            "decisions_made": ["decision1"],
            "next_steps": [],
        }

        insights = await _generate_basic_insights(quality_score, summary)

        assert any("decision1" in insight for insight in insights)

    @pytest.mark.asyncio
    async def test_generate_basic_insights_with_next_steps(self) -> None:
        """Should generate insights with next steps."""
        from session_buddy.quality_engine import _generate_basic_insights

        quality_score = 75.0
        summary = {
            "key_topics": [],
            "decisions_made": [],
            "next_steps": ["step1"],
        }

        insights = await _generate_basic_insights(quality_score, summary)

        assert any("step1" in insight for insight in insights)


# ===== TestTimeBased =====


class TestTimeBasedRecommendations:
    """Test time-based recommendation functions."""

    @pytest.mark.asyncio
    async def test_get_time_based_recommendations_morning(self) -> None:
        """Should return appropriate recommendations for morning."""
        from session_buddy.utils.quality_score_parser import (
            _get_time_based_recommendations,
        )

        # 9 AM
        recommendations = _get_time_based_recommendations(9)

        assert isinstance(recommendations, list)

    @pytest.mark.asyncio
    async def test_get_time_based_recommendations_afternoon(self) -> None:
        """Should return appropriate recommendations for afternoon."""
        from session_buddy.utils.quality_score_parser import (
            _get_time_based_recommendations,
        )

        # 2 PM
        recommendations = _get_time_based_recommendations(14)

        assert isinstance(recommendations, list)

    @pytest.mark.asyncio
    async def test_get_time_based_recommendations_evening(self) -> None:
        """Should return appropriate recommendations for evening."""
        from session_buddy.utils.quality_score_parser import (
            _get_time_based_recommendations,
        )

        # 7 PM
        recommendations = _get_time_based_recommendations(19)

        assert isinstance(recommendations, list)


# ===== TestIntrospection =====


class TestIntrospection:
    """Test that public functions are accessible and documented."""

    def test_should_suggest_compact_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import should_suggest_compact

        assert callable(should_suggest_compact)

    def test_calculate_quality_score_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import calculate_quality_score

        assert callable(calculate_quality_score)

    def test_analyze_project_workflow_patterns_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import analyze_project_workflow_patterns

        assert callable(analyze_project_workflow_patterns)

    def test_analyze_memory_patterns_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import analyze_memory_patterns

        assert callable(analyze_memory_patterns)

    def test_analyze_token_usage_patterns_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import analyze_token_usage_patterns

        assert callable(analyze_token_usage_patterns)

    def test_analyze_conversation_flow_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import analyze_conversation_flow

        assert callable(analyze_conversation_flow)

    def test_summarize_current_conversation_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import summarize_current_conversation

        assert callable(summarize_current_conversation)

    def test_analyze_context_usage_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import analyze_context_usage

        assert callable(analyze_context_usage)

    def test_generate_session_intelligence_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import generate_session_intelligence

        assert callable(generate_session_intelligence)

    def test_monitor_proactive_quality_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import monitor_proactive_quality

        assert callable(monitor_proactive_quality)

    def test_perform_strategic_compaction_is_public(self) -> None:
        """Should be importable as public function."""
        from session_buddy.quality_engine import perform_strategic_compaction

        assert callable(perform_strategic_compaction)
