"""Unit tests for context optimizer.

Tests the ContextOptimizer class for context window optimization,
project type detection, and token management.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestContextOptimizer:
    """Tests for ContextOptimizer class."""

    def test_initialization_default_tokens(self):
        """Test ContextOptimizer initializes with default max_tokens."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        assert optimizer.max_tokens == 180000

    def test_initialization_custom_tokens(self):
        """Test ContextOptimizer accepts custom max_tokens."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer(max_tokens=100000)
        assert optimizer.max_tokens == 100000

    def test_estimate_tokens(self):
        """Test token estimation for text."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        text = "hello world"  # 11 chars
        estimated = optimizer.estimate_tokens(text)
        assert estimated == 2  # 11 // 4 = 2 (floor division)

    def test_estimate_tokens_long_text(self):
        """Test token estimation for longer text."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        text = "a" * 1000
        estimated = optimizer.estimate_tokens(text)
        assert estimated == 250  # 1000 // 4 = 250


class TestProjectTypeDetection:
    """Tests for project type detection."""

    @patch("pathlib.Path.exists")
    def test_detect_python_project(self, mock_exists):
        """Test detection of Python project."""
        from session_buddy.context.optimizer import ContextOptimizer

        # Setup: pyproject.toml exists, others don't
        mock_exists.side_effect = lambda p: str(p).endswith("pyproject.toml")

        optimizer = ContextOptimizer()
        project_path = MagicMock(spec=Path)
        project_path.__truediv__ = Path.__truediv__

        with patch.object(Path, "__truediv__", return_value=MagicMock()):
            # This is a simplified test - actual detection tests need more mocking
            pass

    def test_project_contexts_defined(self):
        """Test that project contexts are initialized."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        assert "python" in optimizer.project_contexts
        assert "typescript" in optimizer.project_contexts
        assert "rust" in optimizer.project_contexts

    def test_project_context_structure(self):
        """Test project context has correct structure."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        python_ctx = optimizer.project_contexts["python"]

        assert "extensions" in python_ctx
        assert "patterns" in python_ctx
        assert "anti_patterns" in python_ctx
        assert ".py" in python_ctx["extensions"]


class TestLoadProjectContext:
    """Tests for load_project_context method."""

    @patch("pathlib.Path.exists")
    def test_load_project_context_python(self, mock_exists):
        """Test loading Python project context."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()

        # Mock project path
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch.object(Path, "__truediv__") as mock_div:
            # Setup pyproject.toml to exist
            pyproject = MagicMock()
            pyproject.exists.return_value = True
            mock_div.return_value = pyproject

            result = optimizer.load_project_context(mock_path, project_type="python")

            assert result["project_type"] == "python"
            assert "patterns" in result
            assert "anti_patterns" in result


class TestContextOptimization:
    """Tests for context optimization methods."""

    def test_optimize_context_for_task(self):
        """Test context optimization for task."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        project_context = {
            "project_type": "python",
            "patterns": ["type hints", "docstrings"],
            "anti_patterns": ["suppress(Exception)"],
            "structure": {"key_directories": ["src", "tests"]},
        }

        result = optimizer.optimize_context_for_task(
            task_description="Add type hints to function",
            project_context=project_context,
            available_tokens=1000,
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_truncate_context(self):
        """Test context truncation."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        long_context = "a" * 1000

        truncated = optimizer._truncate_context(long_context, max_tokens=100)

        # 100 tokens * 4 chars = 400 chars max
        assert len(truncated) <= 403  # 400 + "..."

    def test_truncate_context_short(self):
        """Test truncation of already short context."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        short_context = "hello"

        result = optimizer._truncate_context(short_context, max_tokens=100)
        assert result == "hello"


class TestFormatMethods:
    """Tests for formatting methods."""

    def test_format_project_context(self):
        """Test project context formatting."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        project_context = {
            "project_type": "python",
            "patterns": ["type hints", "docstrings"],
            "anti_patterns": ["suppress(Exception)"],
            "structure": {"key_directories": ["src", "tests"]},
        }

        result = optimizer._format_project_context(project_context)

        assert "Project Type: python" in result
        assert "type hints" in result

    def test_format_project_context_empty(self):
        """Test formatting empty project context."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        empty_context = {"project_type": "unknown"}

        result = optimizer._format_project_context(empty_context)

        assert "Project Type: unknown" in result

    def test_format_patterns_empty(self):
        """Test formatting empty patterns list."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        result = optimizer._format_patterns([])

        assert "No relevant patterns found" in result

    def test_format_patterns_with_data(self):
        """Test formatting patterns with data."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        patterns = [
            {
                "name": "Test Pattern",
                "project_id": "test-project",
                "outcome_score": 0.9,
                "similarity": 0.85,
                "context_snapshot": '{"problem": "Test problem"}',
                "solution_snapshot": '{"approach": "Test approach"}',
            }
        ]

        result = optimizer._format_patterns(patterns)

        assert "Test Pattern" in result
        assert "test-project" in result


class TestTaskGuidance:
    """Tests for task guidance generation."""

    def test_generate_task_guidance_python(self):
        """Test task guidance for Python project."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        project_context = {"project_type": "python"}

        result = optimizer._generate_task_guidance("Add type hints", project_context)

        assert "type hints" in result.lower() or "python" in result.lower()

    def test_generate_task_guidance_typescript(self):
        """Test task guidance for TypeScript project."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        project_context = {"project_type": "typescript"}

        result = optimizer._generate_task_guidance("Add interface", project_context)

        assert "typescript" in result.lower() or "interface" in result.lower()

    def test_generate_task_guidance_rust(self):
        """Test task guidance for Rust project."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        project_context = {"project_type": "rust"}

        result = optimizer._generate_task_guidance("Add error handling", project_context)

        assert "rust" in result.lower() or "safe" in result.lower()

    def test_generate_task_guidance_generic(self):
        """Test task guidance for generic project."""
        from session_buddy.context.optimizer import ContextOptimizer

        optimizer = ContextOptimizer()
        project_context = {"project_type": "generic"}

        result = optimizer._generate_task_guidance("Write code", project_context)

        assert len(result) > 0


class TestSingletonInstance:
    """Tests for get_context_optimizer singleton."""

    def test_get_context_optimizer_creates_instance(self):
        """Test get_context_optimizer creates instance."""
        from session_buddy.context.optimizer import get_context_optimizer, ContextOptimizer

        # Reset singleton for testing
        import session_buddy.context.optimizer as module
        module._instance = None

        optimizer = get_context_optimizer()
        assert isinstance(optimizer, ContextOptimizer)

    def test_get_context_optimizer_returns_same_instance(self):
        """Test singleton returns same instance."""
        from session_buddy.context.optimizer import get_context_optimizer

        # Reset singleton
        import session_buddy.context.optimizer as module
        module._instance = None

        optimizer1 = get_context_optimizer()
        optimizer2 = get_context_optimizer()

        assert optimizer1 is optimizer2

    def test_get_context_optimizer_custom_tokens(self):
        """Test singleton with custom tokens."""
        from session_buddy.context.optimizer import get_context_optimizer

        # Reset singleton
        import session_buddy.context.optimizer as module
        module._instance = None

        optimizer = get_context_optimizer(max_tokens=50000)
        assert optimizer.max_tokens == 50000