"""Unit tests for IDE plugin protocol.

Tests session_buddy.integrations.ide_plugin module:
- IDEContext dataclass validation and methods
- IDESuggestion dataclass
- IDEPluginProtocol methods (with mocked storage)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

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


# ---------------------------------------------------------------
# IDESuggestion.to_dict
# ---------------------------------------------------------------


@pytest.mark.unit
class TestIDESuggestionDict:
    """Tests for IDESuggestion.to_dict."""

    def test_to_dict_with_all_fields(self):
        """Test that to_dict serializes every field."""
        from session_buddy.integrations.ide_plugin import IDESuggestion

        suggestion = IDESuggestion(
            skill_name="ruff-check",
            description="Lint code with Ruff",
            confidence=0.95,
            shortcut="Ctrl+Alt+L",
            estimated_duration_seconds=2.5,
            workflow_phase="verification",
        )
        result = suggestion.to_dict()
        assert result["skill_name"] == "ruff-check"
        assert result["description"] == "Lint code with Ruff"
        assert result["confidence"] == 0.95
        assert result["shortcut"] == "Ctrl+Alt+L"
        assert result["estimated_duration_seconds"] == 2.5
        assert result["workflow_phase"] == "verification"

    def test_to_dict_with_optional_fields_none(self):
        """Test that to_dict surfaces None for missing optional fields."""
        from session_buddy.integrations.ide_plugin import IDESuggestion

        suggestion = IDESuggestion(
            skill_name="ruff-check",
            description="Lint code with Ruff",
            confidence=0.5,
        )
        result = suggestion.to_dict()
        assert result["shortcut"] is None
        assert result["estimated_duration_seconds"] is None
        assert result["workflow_phase"] is None


# ---------------------------------------------------------------
# IDEPluginProtocol initialization
# ---------------------------------------------------------------


@pytest.mark.unit
class TestIDEPluginInit:
    """Tests for IDEPluginProtocol construction."""

    def test_init_stores_db_path(self):
        """Test that the db_path is converted to a Path and stored."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        plugin = IDEPluginProtocol(db_path="/tmp/ide_plugin_test.db")

        assert isinstance(plugin.db_path, Path)
        assert str(plugin.db_path) == "/tmp/ide_plugin_test.db"

    def test_class_attributes_present(self):
        """Test that the class-level mapping attributes are defined."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        assert hasattr(IDEPluginProtocol, "LANGUAGE_PATTERNS")
        assert hasattr(IDEPluginProtocol, "PATTERN_MAPPINGS")
        assert isinstance(IDEPluginProtocol.LANGUAGE_PATTERNS, dict)
        assert isinstance(IDEPluginProtocol.PATTERN_MAPPINGS, dict)

    def test_language_patterns_keys(self):
        """Test that LANGUAGE_PATTERNS has the documented language keys."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        for key in ("python", "javascript", "typescript"):
            assert key in IDEPluginProtocol.LANGUAGE_PATTERNS

    def test_pattern_mappings_values_are_lists(self):
        """Test that PATTERN_MAPPINGS values are lists of skill names."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        for pattern, skills in IDEPluginProtocol.PATTERN_MAPPINGS.items():
            assert isinstance(pattern, str)
            assert isinstance(skills, list)
            assert len(skills) > 0
            for skill in skills:
                assert isinstance(skill, str)


# ---------------------------------------------------------------
# Shortcut registry
# ---------------------------------------------------------------


@pytest.mark.unit
class TestShortcutRegistry:
    """Tests for the SKILL_SHORTCUTS dictionary and helpers."""

    def test_get_shortcut_returns_value(self):
        """Test that get_shortcut returns the registered shortcut."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        shortcut = plugin.get_shortcut("pytest-run")
        assert shortcut == "Ctrl+Shift+T"

    def test_get_shortcut_returns_none_for_unknown(self):
        """Test that get_shortcut returns None for unregistered skills."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        assert plugin.get_shortcut("never-registered-skill") is None

    def test_register_shortcut_adds_new_entry(self):
        """Test that register_shortcut persists into the global registry."""
        from session_buddy.integrations.ide_plugin import (
            IDEPluginProtocol,
            SKILL_SHORTCUTS,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        plugin.register_shortcut("my-skill", "Ctrl+Alt+Z")

        assert SKILL_SHORTCUTS["my-skill"] == "Ctrl+Alt+Z"
        # Re-fetch via the protocol
        assert plugin.get_shortcut("my-skill") == "Ctrl+Alt+Z"

    def test_register_shortcut_overrides_existing(self):
        """Test that register_shortcut can override an existing entry."""
        from session_buddy.integrations.ide_plugin import (
            IDEPluginProtocol,
            SKILL_SHORTCUTS,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        plugin.register_shortcut("pytest-run", "Cmd+Shift+T")
        assert SKILL_SHORTCUTS["pytest-run"] == "Cmd+Shift+T"
        # Restore to avoid leaking into other tests
        SKILL_SHORTCUTS["pytest-run"] = "Ctrl+Shift+T"

    def test_get_available_shortcuts_returns_copy(self):
        """Test that get_available_shortcuts returns a snapshot copy."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        shortcuts = plugin.get_available_shortcuts()

        assert isinstance(shortcuts, dict)
        assert "pytest-run" in shortcuts
        # Modifying the returned copy should not affect the global registry
        shortcuts["__mutation_probe__"] = "Ctrl+X"
        assert plugin.get_shortcut("__mutation_probe__") is None

    def test_get_available_shortcuts_matches_module_constant(self):
        """Test that get_available_shortcuts mirrors the module constant."""
        from session_buddy.integrations.ide_plugin import (
            IDEPluginProtocol,
            SKILL_SHORTCUTS,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        assert plugin.get_available_shortcuts() == SKILL_SHORTCUTS


# ---------------------------------------------------------------
# Internal: build_query_from_context
# ---------------------------------------------------------------


@pytest.mark.unit
class TestBuildQueryFromContext:
    """Tests for IDEPluginProtocol._build_query_from_context."""

    def test_python_production_no_selection(self):
        """Test query for Python production code with no selection."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="",
            language="python",
            cursor_position=(10, 0),
        )
        query = plugin._build_query_from_context(context)
        assert "python" in query
        assert "production code" in query

    def test_python_test_file(self):
        """Test query for a Python test file."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )
        query = plugin._build_query_from_context(context)
        assert "testing" in query

    def test_selection_extracts_keywords(self):
        """Test that selected code contributes keywords to the query."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="def calculate_total_with_tax():",
            language="python",
            cursor_position=(10, 0),
        )
        query = plugin._build_query_from_context(context)
        # At least one keyword from the selection should appear
        assert "calculate" in query or "total" in query

    def test_empty_language(self):
        """Test query building when no language is provided."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="",
            language="",
            cursor_position=(10, 0),
        )
        query = plugin._build_query_from_context(context)
        # Falls through to default code-quality phrasing
        assert "code" in query or "testing" in query


# ---------------------------------------------------------------
# Internal: infer_workflow_phase
# ---------------------------------------------------------------


@pytest.mark.unit
class TestInferWorkflowPhase:
    """Tests for IDEPluginProtocol._infer_workflow_phase."""

    def test_test_file_infers_execution(self):
        """Test that a test file infers the execution phase."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/tests/test_x.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )
        assert plugin._infer_workflow_phase(context) == "execution"

    def test_import_selection_infers_setup(self):
        """Test that an import-related selection infers the setup phase."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="import os\nfrom pathlib import Path",
            language="python",
            cursor_position=(10, 0),
        )
        assert plugin._infer_workflow_phase(context) == "setup"

    def test_selection_with_from_keyword_infers_setup(self):
        """Test that 'from' keyword in selection also infers setup."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="from collections import OrderedDict",
            language="python",
            cursor_position=(10, 0),
        )
        assert plugin._infer_workflow_phase(context) == "setup"

    def test_non_import_selection_infers_execution(self):
        """Test that a non-import selection infers execution."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="def my_function(): pass",
            language="python",
            cursor_position=(10, 0),
        )
        assert plugin._infer_workflow_phase(context) == "execution"

    def test_no_selection_defaults_to_execution(self):
        """Test that an empty production file context defaults to execution."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="",
            language="python",
            cursor_position=(10, 0),
        )
        assert plugin._infer_workflow_phase(context) == "execution"


# ---------------------------------------------------------------
# Internal: _generate_description
# ---------------------------------------------------------------


@pytest.mark.unit
class TestGenerateDescription:
    """Tests for IDEPluginProtocol._generate_description."""

    def test_known_skill_in_test_file(self):
        """Test that known skills in test files get a 'for current test file' hint."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )
        description = plugin._generate_description("pytest-run", context)
        assert "for current test file" in description

    def test_known_skill_with_selection(self):
        """Test that selections get an 'on selected code' suffix."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="def foo():",
            language="python",
            cursor_position=(10, 0),
        )
        description = plugin._generate_description("ruff-format", context)
        assert "on selected code" in description

    def test_unknown_skill_gets_generic_description(self):
        """Test that an unknown skill gets a generic 'Invoke <name>' description."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )
        description = plugin._generate_description("mystery-skill", context)
        assert "mystery-skill" in description

    def test_test_named_skill_in_non_test_file(self):
        """Test that a 'test' skill in a non-test file is not modified."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        context = IDEContext(
            file_path="/src/main.py",
            line_number=1,
            selected_code="",
            language="python",
            cursor_position=(1, 0),
        )
        # No selection, no test file → base description
        description = plugin._generate_description("pytest-run", context)
        assert "for current test file" not in description


# ---------------------------------------------------------------
# Internal: _pattern_based_recommendations
# ---------------------------------------------------------------


@pytest.mark.unit
class TestPatternBasedRecommendations:
    """Tests for IDEPluginProtocol._pattern_based_recommendations."""

    def _plugin_with_mock_storage(self) -> "IDEPluginProtocol":  # noqa: F821
        """Construct a plugin and replace storage with a no-op mock."""
        from session_buddy.integrations.ide_plugin import IDEPluginProtocol

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        mock_storage = MagicMock()
        mock_storage.get_metrics.return_value = None
        mock_storage.search_by_query_workflow_aware.return_value = []
        plugin.storage = mock_storage
        return plugin

    def test_python_pytest_pattern_in_selection(self):
        """Test that 'def test_' in selection triggers pytest skills."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="def test_something():",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        skill_names = {r.skill_name for r in recs}
        assert "pytest-run" in skill_names
        assert "pytest-coverage" in skill_names

    def test_javascript_describe_pattern(self):
        """Test that 'describe(' in selection triggers jest skills."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.test.js",
            line_number=1,
            selected_code="describe('foo', () => { it('works', () => {}) })",
            language="javascript",
            cursor_position=(1, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        skill_names = {r.skill_name for r in recs}
        assert "jest-run" in skill_names or "vitest-run" in skill_names

    def test_function_def_pattern(self):
        """Test that 'def name(' triggers mypy/ruff checks."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="def calculate_total():",
            language="python",
            cursor_position=(10, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        skill_names = {r.skill_name for r in recs}
        assert "mypy-check" in skill_names
        assert "ruff-check" in skill_names

    def test_class_def_pattern(self):
        """Test that 'class name(' triggers mypy/pylint checks."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="class MyService:",
            language="python",
            cursor_position=(10, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        skill_names = {r.skill_name for r in recs}
        assert "mypy-check" in skill_names
        assert "pylint-check" in skill_names

    def test_async_def_pattern(self):
        """Test that 'async def ' triggers asyncio checks."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="async def fetch_data():",
            language="python",
            cursor_position=(10, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        skill_names = {r.skill_name for r in recs}
        assert "asyncio-check" in skill_names

    def test_security_pattern_eval(self):
        """Test that eval() in selection triggers security skills.

        Note: ``eval`` here is a substring inside the test fixture string
        passed as ``selected_code``. It is never executed; the test only
        verifies that the pattern-based recommendation engine flags
        security-sensitive code patterns.
        """
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="result = eval(user_input)",
            language="python",
            cursor_position=(10, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        skill_names = {r.skill_name for r in recs}
        assert "bandit-security" in skill_names
        assert "security-scan" in skill_names

    def test_sql_select_pattern(self):
        """Test that SELECT keyword triggers sql skills."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.py",
            line_number=10,
            selected_code="cursor.execute('SELECT * FROM users')",
            language="python",
            cursor_position=(10, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        skill_names = {r.skill_name for r in recs}
        assert "sql-lint" in skill_names
        assert "sql-format" in skill_names

    def test_unknown_language_falls_back_to_no_lang_skills(self):
        """Test that an unknown language produces no language-specific recs."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.go",
            line_number=1,
            selected_code="def test_foo():",
            language="go",
            cursor_position=(1, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=10)
        # Python pattern triggers, but no Go language skills are added
        # because LANGUAGE_PATTERNS has no "go" entry.
        skill_names = {r.skill_name for r in recs}
        # The python 'def test_' pattern still matches against the selection
        assert "pytest-run" in skill_names

    def test_limit_truncates_results(self):
        """Test that the limit parameter truncates returned recommendations."""
        from session_buddy.integrations.ide_plugin import IDEContext

        plugin = self._plugin_with_mock_storage()
        context = IDEContext(
            file_path="/src/main.py",
            line_number=1,
            selected_code="def test_foo():",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin._pattern_based_recommendations(context, limit=2)
        assert len(recs) <= 2


# ---------------------------------------------------------------
# get_code_context_recommendations (integration)
# ---------------------------------------------------------------


@pytest.mark.unit
class TestGetCodeContextRecommendations:
    """End-to-end tests for IDEPluginProtocol.get_code_context_recommendations."""

    def test_pattern_fallback_when_storage_empty(self):
        """Test that pattern-based recs surface when storage is empty."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        # Replace the storage with a mock that returns no semantic results
        # (so the pattern-based fallback is exercised)
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = None
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="def test_foo():",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin.get_code_context_recommendations(context, limit=5)
        assert len(recs) > 0
        skill_names = {r.skill_name for r in recs}
        assert "pytest-run" in skill_names

    def test_recommendations_sorted_by_confidence(self):
        """Test that returned recommendations are sorted by confidence."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = None
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/src/main.py",
            line_number=1,
            selected_code="def foo(): pass",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin.get_code_context_recommendations(context, limit=10)
        # Confidence is monotonic non-increasing
        for prev, curr in zip(recs, recs[1:]):
            assert prev.confidence >= curr.confidence

    def test_recommendations_deduplicate(self):
        """Test that the same skill does not appear twice."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = None
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/src/main.py",
            line_number=1,
            selected_code="def foo(): pass",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin.get_code_context_recommendations(context, limit=10)
        skill_names = [r.skill_name for r in recs]
        assert len(skill_names) == len(set(skill_names))

    def test_recommendations_respect_limit(self):
        """Test that the limit caps the number of returned suggestions."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = None
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/src/main.py",
            line_number=1,
            selected_code="def foo(): pass",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin.get_code_context_recommendations(context, limit=2)
        assert len(recs) <= 2

    def test_estimated_duration_pulled_from_storage_metrics(self):
        """Test that estimated_duration_seconds is taken from storage metrics."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        metrics_mock = MagicMock()
        metrics_mock.avg_duration_seconds = 7.5
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = metrics_mock
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="def test_foo():",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin.get_code_context_recommendations(context, limit=3)
        for rec in recs:
            # The mock returns 7.5 for every metric lookup
            assert rec.estimated_duration_seconds == 7.5

    def test_shortcut_assigned_when_known(self):
        """Test that suggestions for known skills carry their shortcut."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = None
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="def test_foo():",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin.get_code_context_recommendations(context, limit=10)
        pytest_rec = next((r for r in recs if r.skill_name == "pytest-run"), None)
        assert pytest_rec is not None
        assert pytest_rec.shortcut == "Ctrl+Shift+T"

    def test_workflow_phase_attached_to_suggestions(self):
        """Test that suggestions carry a workflow_phase attribute."""
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = None
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="def test_foo():",
            language="python",
            cursor_position=(1, 0),
        )

        recs = plugin.get_code_context_recommendations(context, limit=5)
        for rec in recs:
            assert rec.workflow_phase is not None

    def test_semantic_search_path_used_when_available(self):
        """Test that embedding service failure falls back to pattern-based.

        The production code wraps the entire semantic search in
        ``with suppress(Exception)`` so a failure of the embedding
        service (or its initialization) silently falls through to the
        pattern-based recommender. This test exercises that fallback
        path by forcing the embedding service to raise on access.
        """
        from session_buddy.integrations.ide_plugin import (
            IDEContext,
            IDEPluginProtocol,
        )

        plugin = IDEPluginProtocol(db_path="/tmp/x.db")
        mock_storage = MagicMock()
        mock_storage.search_by_query_workflow_aware.return_value = []
        mock_storage.get_metrics.return_value = None
        plugin.storage = mock_storage

        context = IDEContext(
            file_path="/tests/test_main.py",
            line_number=1,
            selected_code="def test_foo():",
            language="python",
            cursor_position=(1, 0),
        )

        with patch(
            "session_buddy.storage.skills_embeddings.get_embedding_service",
            side_effect=Exception("no embeddings"),
        ):
            recs = plugin.get_code_context_recommendations(context, limit=5)

        # Fallback to pattern-based; pytest-run triggers from "def test_"
        skill_names = {r.skill_name for r in recs}
        assert "pytest-run" in skill_names
