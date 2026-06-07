"""Comprehensive tests for quality scoring V2 algorithm.

Week 8 Day 2 - Phase 4: Test quality_utils_v2.py implementation.
Tests filesystem-based quality assessment with component scoring.
"""

from __future__ import annotations

import json
import subprocess
import typing as t
from unittest.mock import AsyncMock, Mock, patch

import pytest
from session_buddy.utils.quality_utils_v2 import (
    CodeQualityScore,
    DevVelocityScore,
    ProjectHealthScore,
    QualityScoreV2,
    SecurityScore,
    TrustScore,
    calculate_quality_score_v2,
)

if t.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
class TestCalculateQualityScoreV2:
    """Test main quality score calculation function."""

    @patch("session_buddy.utils.quality_utils_v2._get_crackerjack_metrics")
    async def test_calculate_quality_score_v2_with_perfect_metrics(
        self, mock_metrics: AsyncMock, tmp_path: Path
    ):
        """Quality score V2 with perfect metrics returns high score."""
        # Mock perfect Crackerjack metrics
        mock_metrics.return_value = {
            "code_coverage": 100,
            "lint_score": 100,
            "type_coverage": 100,
            "complexity_score": 100,
            "security_score": 100,
        }

        # Create perfect project structure
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / "uv.lock").write_text("# lock file\n")
        (tmp_path / ".gitignore").write_text(".env\n")

        # Initialize git
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Create test infrastructure
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "conftest.py").write_text("# conftest\n")
        for i in range(15):
            (tests_dir / f"test_{i}.py").write_text("def test_pass(): pass\n")

        # Create documentation
        (tmp_path / "README.md").write_text("# Project\n")
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        for i in range(6):
            (docs_dir / f"doc_{i}.md").write_text(f"# Doc {i}\n")

        # Create CI/CD
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "ci.yml").write_text("name: CI\n")
        (workflows_dir / "release.yml").write_text("name: Release\n")

        # Calculate score
        result = await calculate_quality_score_v2(
            tmp_path, permissions_count=4, session_available=True, tool_count=10
        )

        # Verify result structure
        assert isinstance(result, QualityScoreV2)
        assert result.version == "2.0"
        assert (
            result.total_score >= 75
        )  # Should be high (git velocity may be low in test)

        # Verify components are present
        assert isinstance(result.code_quality, CodeQualityScore)
        assert isinstance(result.project_health, ProjectHealthScore)
        assert isinstance(result.dev_velocity, DevVelocityScore)
        assert isinstance(result.security, SecurityScore)
        assert isinstance(result.trust_score, TrustScore)

        # Verify recommendations list
        assert isinstance(result.recommendations, list)

    @patch("session_buddy.utils.quality_utils_v2._get_crackerjack_metrics")
    async def test_calculate_quality_score_v2_with_poor_metrics(
        self, mock_metrics: AsyncMock, tmp_path: Path
    ):
        """Quality score V2 with poor metrics returns low score."""
        # Mock poor Crackerjack metrics
        mock_metrics.return_value = {
            "code_coverage": 10,
            "lint_score": 40,
            "type_coverage": 20,
            "complexity_score": 50,
            "security_score": 60,
        }

        # Minimal project structure
        (tmp_path / "pyproject.toml").write_text("[project]\n")

        result = await calculate_quality_score_v2(
            tmp_path, permissions_count=0, session_available=False, tool_count=0
        )

        # Low score expected
        assert result.total_score < 50
        assert len(result.recommendations) > 2

    @patch("session_buddy.utils.quality_utils_v2._get_crackerjack_metrics")
    async def test_calculate_quality_score_v2_with_no_metrics(
        self, mock_metrics: AsyncMock, tmp_path: Path
    ):
        """Quality score V2 works with no Crackerjack metrics (fallback)."""
        # No Crackerjack data
        mock_metrics.return_value = {}

        result = await calculate_quality_score_v2(tmp_path)

        # Should still calculate with fallback defaults
        assert isinstance(result, QualityScoreV2)
        assert 0 <= result.total_score <= 100
        assert isinstance(result.recommendations, list)


@pytest.mark.asyncio
class TestCodeQualityCalculation:
    """Test code quality component (40 points max)."""

    @patch("session_buddy.utils.quality_utils_v2._get_crackerjack_metrics")
    @patch("session_buddy.utils.quality_utils_v2._get_type_coverage")
    async def test_code_quality_with_perfect_scores(
        self, mock_type_coverage: AsyncMock, mock_metrics: AsyncMock, tmp_path: Path
    ):
        """Code quality with perfect metrics returns 40 points."""
        from session_buddy.utils.quality_utils_v2 import _calculate_code_quality

        mock_metrics.return_value = {
            "code_coverage": 100,
            "lint_score": 100,
            "complexity_score": 100,
        }
        mock_type_coverage.return_value = 100.0

        result = await _calculate_code_quality(tmp_path)

        # Perfect scores
        assert result.test_coverage == 15.0  # 100% coverage * 15
        assert result.lint_score == 10.0  # 100 lint * 10
        assert result.type_coverage == 10.0  # 100% types * 10
        assert result.complexity_score == 5.0  # 100 complexity * 5
        assert result.total == 40.0

    @patch("session_buddy.utils.quality_utils_v2._get_crackerjack_metrics")
    @patch("session_buddy.utils.quality_utils_v2._get_type_coverage")
    async def test_code_quality_with_low_coverage(
        self, mock_type_coverage: AsyncMock, mock_metrics: AsyncMock, tmp_path: Path
    ):
        """Code quality with low test coverage returns reduced score."""
        from session_buddy.utils.quality_utils_v2 import _calculate_code_quality

        mock_metrics.return_value = {
            "code_coverage": 50,
            "lint_score": 80,
            "complexity_score": 70,
        }
        mock_type_coverage.return_value = 60.0

        result = await _calculate_code_quality(tmp_path)

        # Scaled scores
        assert result.test_coverage == 7.5  # 50% * 15
        assert result.lint_score == 8.0  # 80 * 10 / 100
        assert result.type_coverage == 6.0  # 60% * 10
        assert result.complexity_score == 3.5  # 70 * 5 / 100
        assert result.total == 25.0

    @patch("session_buddy.utils.quality_utils_v2._get_crackerjack_metrics")
    @patch("session_buddy.utils.quality_utils_v2._get_type_coverage")
    async def test_code_quality_with_no_metrics(
        self, mock_type_coverage: AsyncMock, mock_metrics: AsyncMock, tmp_path: Path
    ):
        """Code quality with no metrics uses fallback defaults."""
        from session_buddy.utils.quality_utils_v2 import _calculate_code_quality

        mock_metrics.return_value = {}
        mock_type_coverage.return_value = 30.0

        result = await _calculate_code_quality(tmp_path)

        # Fallback defaults (perfect lint/complexity, no coverage, low types)
        assert result.test_coverage == 0.0  # No coverage data
        assert result.lint_score == 10.0  # Default perfect
        assert result.type_coverage == 3.0  # 30% * 10
        assert result.complexity_score == 5.0  # Default perfect
        assert result.total == 18.0


@pytest.mark.asyncio
class TestProjectHealthCalculation:
    """Test project health component (30 points max)."""

    async def test_project_health_with_perfect_setup(self, tmp_path: Path):
        """Project health with all tooling returns high score."""
        from session_buddy.utils.quality_utils_v2 import _calculate_project_health

        # Perfect tooling setup
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "uv.lock").write_text("# lock\n")

        # Git with history
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Project\n")
        subprocess.run(
            ["git", "add", "."], cwd=tmp_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Create multiple commits for history
        for i in range(6):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}\n")
            subprocess.run(
                ["git", "add", f"file_{i}.txt"],
                cwd=tmp_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Add file {i}"],
                cwd=tmp_path,
                check=True,
                capture_output=True,
            )

        # Comprehensive test infrastructure
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "conftest.py").write_text("# conftest\n")
        for i in range(15):
            (tests_dir / f"test_{i}.py").write_text("def test(): pass\n")

        # Comprehensive documentation
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        for i in range(6):
            (docs_dir / f"doc_{i}.md").write_text(f"# Doc {i}\n")

        # CI/CD
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "ci.yml").write_text("name: CI\n")
        (workflows_dir / "release.yml").write_text("name: Release\n")

        result = await _calculate_project_health(tmp_path)

        # Should get high score
        assert result.tooling_score >= 12.0  # Near max 15
        assert result.maturity_score >= 12.0  # Near max 15
        assert result.total >= 24.0  # Near max 30

    async def test_project_health_with_minimal_setup(self, tmp_path: Path):
        """Project health with minimal setup returns low score."""
        from session_buddy.utils.quality_utils_v2 import _calculate_project_health

        # Only pyproject.toml
        (tmp_path / "pyproject.toml").write_text("[project]\n")

        result = await _calculate_project_health(tmp_path)

        # Low score expected
        assert result.tooling_score <= 8.0
        assert result.maturity_score <= 5.0
        assert result.total <= 13.0


@pytest.mark.asyncio
class TestTrustScoreCalculation:
    """Test trust score calculation (separate 0-100 scale)."""

    def test_trust_score_with_perfect_environment(self):
        """Trust score with perfect environment returns 100."""
        from session_buddy.utils.quality_utils_v2 import _calculate_trust_score

        result = _calculate_trust_score(
            permissions_count=4, session_available=True, tool_count=10
        )

        # Perfect trust
        assert result.trusted_operations == 40  # 4 ops * 10
        assert result.session_availability == 30
        assert result.tool_ecosystem == 30  # 10 tools * 3
        assert result.total == 100

    def test_trust_score_with_no_trust(self):
        """Trust score with no trust returns minimal score."""
        from session_buddy.utils.quality_utils_v2 import _calculate_trust_score

        result = _calculate_trust_score(
            permissions_count=0, session_available=False, tool_count=0
        )

        # Minimal trust
        assert result.trusted_operations == 0
        assert result.session_availability == 5  # Minimal for unavailable
        assert result.tool_ecosystem == 0
        assert result.total == 5


@pytest.mark.asyncio
class TestRecommendationGeneration:
    """Test recommendation generation logic."""

    def test_recommendations_for_excellent_quality(self):
        """Recommendations for excellent quality include maintenance message."""
        from session_buddy.utils.quality_utils_v2 import (
            _generate_recommendations_v2,
        )

        # Perfect scores
        code_quality = CodeQualityScore(
            test_coverage=15.0,
            lint_score=10.0,
            type_coverage=10.0,
            complexity_score=5.0,
            total=40.0,
            details={"coverage_pct": 100},
        )
        project_health = ProjectHealthScore(
            tooling_score=15.0, maturity_score=15.0, total=30.0, details={}
        )
        dev_velocity = DevVelocityScore(
            git_activity=10.0, dev_patterns=10.0, total=20.0, details={}
        )
        security = SecurityScore(
            security_tools=5.0, security_hygiene=5.0, total=10.0, details={}
        )

        recommendations = _generate_recommendations_v2(
            code_quality, project_health, dev_velocity, security, total_score=100.0
        )

        # Should include excellent message
        assert any("Excellent" in rec or "maintain" in rec for rec in recommendations)

    def test_recommendations_for_poor_quality(self):
        """Recommendations for poor quality include critical issues."""
        from session_buddy.utils.quality_utils_v2 import (
            _generate_recommendations_v2,
        )

        # Poor scores
        code_quality = CodeQualityScore(
            test_coverage=5.0,
            lint_score=4.0,
            type_coverage=3.0,
            complexity_score=2.0,
            total=14.0,
            details={"coverage_pct": 33.3},
        )
        project_health = ProjectHealthScore(
            tooling_score=5.0, maturity_score=5.0, total=10.0, details={}
        )
        dev_velocity = DevVelocityScore(
            git_activity=3.0, dev_patterns=2.0, total=5.0, details={}
        )
        security = SecurityScore(
            security_tools=3.0, security_hygiene=2.0, total=5.0, details={}
        )

        recommendations = _generate_recommendations_v2(
            code_quality, project_health, dev_velocity, security, total_score=34.0
        )

        # Should include multiple critical recommendations
        assert len(recommendations) >= 5
        assert any("Critical" in rec or "attention" in rec for rec in recommendations)


@pytest.mark.asyncio
class TestTypeCoverageCalculation:
    """Test type coverage estimation."""

    async def test_type_coverage_from_crackerjack_metrics(self, tmp_path: Path):
        """Type coverage uses Crackerjack data when available."""
        from session_buddy.utils.quality_utils_v2 import _get_type_coverage

        metrics = {"type_coverage": 87.5}

        result = await _get_type_coverage(tmp_path, metrics)

        # Use Crackerjack value
        assert result == 87.5

    async def test_type_coverage_with_pyright_config(self, tmp_path: Path):
        """Type coverage estimates 70% when pyright configured."""
        from session_buddy.utils.quality_utils_v2 import _get_type_coverage

        (tmp_path / "pyrightconfig.json").write_text("{}")

        result = await _get_type_coverage(tmp_path, {})

        # Estimate for configured type checker
        assert result == 70.0

    async def test_type_coverage_with_no_type_checker(self, tmp_path: Path):
        """Type coverage returns 30% default when no type checker."""
        from session_buddy.utils.quality_utils_v2 import _get_type_coverage

        result = await _get_type_coverage(tmp_path, {})

        # Low default
        assert result == 30.0


class TestReadCoverageDotfile:
    """Tests for _read_coverage_dotfile fallback."""

    def test_returns_zero_when_no_dotfile(self, tmp_path: Path):
        """Returns 0 when .coverage file does not exist."""
        from session_buddy.utils.quality_utils_v2 import _read_coverage_dotfile

        assert _read_coverage_dotfile(tmp_path) == 0

    def test_returns_zero_on_corrupt_dotfile(self, tmp_path: Path):
        """Returns 0 gracefully when .coverage file is not a valid SQLite DB."""
        from session_buddy.utils.quality_utils_v2 import _read_coverage_dotfile

        (tmp_path / ".coverage").write_bytes(b"not a coverage db")
        assert _read_coverage_dotfile(tmp_path) == 0

    def test_reads_real_dotfile(self, tmp_path: Path):
        """Reads actual coverage percentage from a real .coverage file."""
        from unittest.mock import MagicMock, patch

        from session_buddy.utils.quality_utils_v2 import _read_coverage_dotfile

        # Create a stub .coverage file so the existence check passes
        (tmp_path / ".coverage").write_bytes(b"")

        mock_cov = MagicMock()
        mock_cov.report.return_value = 42.5

        # Coverage is imported lazily inside the function, so patch via coverage module
        with patch("coverage.Coverage", return_value=mock_cov):
            result = _read_coverage_dotfile(tmp_path)

        assert result == 42.5
        mock_cov.load.assert_called_once()

    def test_preferred_over_missing_json(self, tmp_path: Path):
        """_get_crackerjack_metrics uses .coverage when coverage.json is absent."""
        import asyncio
        from unittest.mock import MagicMock, patch

        from session_buddy.utils.quality_utils_v2 import _get_crackerjack_metrics

        (tmp_path / ".coverage").write_bytes(b"")

        mock_cov = MagicMock()
        mock_cov.report.return_value = 55.0

        with (
            patch("session_buddy.utils.quality_scoring.CRACKERJACK_AVAILABLE", False),
            patch("coverage.Coverage", return_value=mock_cov),
        ):
            # Use asyncio.run() rather than get_event_loop() to get a
            # fresh event loop. The previous pattern (get_event_loop) was
            # deprecated and returned a closed loop when this test ran
            # after pytest-asyncio tests, causing intermittent failures.
            metrics = asyncio.run(_get_crackerjack_metrics(tmp_path))

        assert metrics.get("code_coverage") == 55.0
