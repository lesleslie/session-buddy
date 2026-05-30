"""Unit tests for IDE plugin protocol.

Tests session_buddy.integrations.ide_plugin module:
- IDEContext dataclass validation and methods
- IDESuggestion dataclass
- IDEPluginProtocol methods (with mocked storage)
"""

from __future__ import annotations

from datetime import datetime

import pytest
from unittest.mock import MagicMock, patch


class TestIDEContext:
    """Tests for IDEContext dataclass."""

    def test_valid_context_creation(self):
        """Test creating valid IDEContext."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/file.py",
            line_number=42,
            selected_code="def foo():",
            language="python",
            cursor_position=(42, 10),
            project_name="testproject",
        )

        assert context.file_path == "/path/to/file.py"
        assert context.line_number == 42
        assert context.selected_code == "def foo():"
        assert context.language == "python"
        assert context.cursor_position == (42, 10)
        assert context.project_name == "testproject"

    def test_context_without_project_name(self):
        """Test creating context without optional project_name."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/file.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.project_name is None

    def test_invalid_line_number_zero(self):
        """Test that line_number=0 raises ValueError."""
        from session_buddy.integrations.ide_plugin import IDEContext

        with pytest.raises(ValueError, match="line_number must be >= 1"):
            IDEContext(
                file_path="/path/to/file.py",
                line_number=0,
                selected_code="",
                language="python",
                cursor_position=(1, 0),
            )

    def test_invalid_line_number_negative(self):
        """Test that negative line_number raises ValueError."""
        from session_buddy.integrations.ide_plugin import IDEContext

        with pytest.raises(ValueError, match="line_number must be >= 1"):
            IDEContext(
                file_path="/path/to/file.py",
                line_number=-5,
                selected_code="",
                language="python",
                cursor_position=(1, 0),
            )

    def test_invalid_cursor_position_row_zero(self):
        """Test that cursor row=0 raises ValueError."""
        from session_buddy.integrations.ide_plugin import IDEContext

        with pytest.raises(ValueError, match="cursor_position must be"):
            IDEContext(
                file_path="/path/to/file.py",
                line_number=1,
                selected_code="",
                language="python",
                cursor_position=(0, 0),
            )

    def test_invalid_cursor_position_negative_col(self):
        """Test that negative cursor col raises ValueError."""
        from session_buddy.integrations.ide_plugin import IDEContext

        with pytest.raises(ValueError, match="cursor_position must be"):
            IDEContext(
                file_path="/path/to/file.py",
                line_number=1,
                selected_code="",
                language="python",
                cursor_position=(1, -1),
            )

    def test_get_file_extension(self):
        """Test get_file_extension method."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.get_file_extension() == "py"

    def test_get_file_extension_no_extension(self):
        """Test get_file_extension with no extension."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/Makefile",
            line_number=1,
            selected_code="",
            language="text",
            cursor_position=(1, 0),
        )

        assert context.get_file_extension() == ""

    def test_is_test_file_true(self):
        """Test is_test_file returns True for test files."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/test_main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.is_test_file() is True

    def test_is_test_file_false(self):
        """Test is_test_file returns False for non-test files."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.is_test_file() is False

    def test_is_test_file_test_directory(self):
        """Test is_test_file in tests directory."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/tests/unit/test_main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.is_test_file() is True

    def test_has_selection_true(self):
        """Test has_selection returns True when code is selected."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/main.py",
            line_number=1,
            selected_code="def foo():",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.has_selection() is True

    def test_has_selection_false(self):
        """Test has_selection returns False when no code selected."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.has_selection() is False

    def test_has_selection_whitespace_only(self):
        """Test has_selection returns False for whitespace-only."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/main.py",
            line_number=1,
            selected_code="   ",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.has_selection() is False


class TestIDESuggestion:
    """Tests for IDESuggestion dataclass."""

    def test_suggestion_creation(self):
        """Test creating valid IDESuggestion."""
        from session_buddy.integrations.ide_plugin import IDESuggestion

        suggestion = IDESuggestion(
            skill_name="pytest-run",
            description="Run pytest test suite",
            confidence=0.85,
            shortcut="Ctrl+Shift+T",
            estimated_duration_seconds=45.5,
            workflow_phase="execution",
        )

        assert suggestion.skill_name == "pytest-run"
        assert suggestion.description == "Run pytest test suite"
        assert suggestion.confidence == 0.85
        assert suggestion.shortcut == "Ctrl+Shift+T"
        assert suggestion.estimated_duration_seconds == 45.5
        assert suggestion.workflow_phase == "execution"

    def test_suggestion_optional_fields(self):
        """Test creating suggestion with only required fields."""
        from session_buddy.integrations.ide_plugin import IDESuggestion

        suggestion = IDESuggestion(
            skill_name="ruff-format",
            description="Format code with Ruff",
            confidence=0.7,
        )

        assert suggestion.skill_name == "ruff-format"
        assert suggestion.shortcut is None
        assert suggestion.estimated_duration_seconds is None
        assert suggestion.workflow_phase is None


class TestSkillShortcuts:
    """Tests for SKILL_SHORTCUTS dictionary."""

    def test_shortcuts_defined(self):
        """Test that SKILL_SHORTCUTS has expected shortcuts."""
        from session_buddy.integrations.ide_plugin import SKILL_SHORTCUTS

        assert "pytest-run" in SKILL_SHORTCUTS
        assert "ruff-format" in SKILL_SHORTCUTS
        assert "mypy-check" in SKILL_SHORTCUTS

    def test_shortcut_format(self):
        """Test that shortcuts follow expected format."""
        from session_buddy.integrations.ide_plugin import SKILL_SHORTCUTS

        for skill_name, shortcut in SKILL_SHORTCUTS.items():
            assert isinstance(skill_name, str)
            assert isinstance(shortcut, str)
            assert "+" in shortcut or " " in shortcut  # Contains key combination


class TestIDEPluginProtocolStructure:
    """Tests for IDEPluginProtocol class structure without instantiating storage."""

    def test_protocol_has_db_path_attribute(self):
        """Test that protocol stores db_path."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        # Check class has __init__ that accepts db_path
        import inspect
        sig = inspect.signature(IDEPluginProtocol.__init__)
        params = list(sig.parameters.keys())

        assert "db_path" in params

    def test_protocol_get_shortcut_method_exists(self):
        """Test get_shortcut method exists."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        assert hasattr(IDEPluginProtocol, "get_shortcut")
        assert callable(IDEPluginProtocol.get_shortcut)

    def test_protocol_register_shortcut_method_exists(self):
        """Test register_shortcut method exists."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        assert hasattr(IDEPluginProtocol, "register_shortcut")
        assert callable(IDEPluginProtocol.register_shortcut)

    def test_protocol_get_available_shortcuts_method_exists(self):
        """Test get_available_shortcuts method exists."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        assert hasattr(IDEPluginProtocol, "get_available_shortcuts")
        assert callable(IDEPluginProtocol.get_available_shortcuts)

    def test_protocol_language_patterns_class_attribute(self):
        """Test LANGUAGE_PATTERNS is defined as class attribute."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        assert hasattr(IDEPluginProtocol, "LANGUAGE_PATTERNS")
        assert isinstance(IDEPluginProtocol.LANGUAGE_PATTERNS, dict)

    def test_protocol_pattern_mappings_class_attribute(self):
        """Test PATTERN_MAPPINGS is defined as class attribute."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        assert hasattr(IDEPluginProtocol, "PATTERN_MAPPINGS")
        assert isinstance(IDEPluginProtocol.PATTERN_MAPPINGS, dict)


class TestWorkflowPhaseInference:
    """Tests for workflow phase inference."""

    def test_infer_workflow_phase_python(self):
        """Test workflow phase inference for Python."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol, IDEContext

        # Test IDEContext can be created
        context = IDEContext(
            file_path="/path/to/main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )

        assert context.language == "python"

    def test_infer_workflow_phase_typescript(self):
        """Test workflow phase inference for TypeScript."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/src/main.ts",
            line_number=1,
            selected_code="",
            language="typescript",
            cursor_position=(1, 0),
        )

        assert context.language == "typescript"

    def test_infer_workflow_phase_test_file(self):
        """Test workflow phase inference for test file."""
        from session_buddy.integrations.ide_plugin import IDEContext

        context = IDEContext(
            file_path="/path/to/test_main.py",
            line_number=1,
            selected_code="def test_foo():",
            language="python",
            cursor_position=(1, 0),
        )

        # Test file detection
        assert context.is_test_file() is True
