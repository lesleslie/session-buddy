"""IDE plugin protocol for session-buddy skills recommendations.

Defines how IDEs (VSCode, PyCharm, etc.) can request skill recommendations
based on current code context. Provides intelligent suggestions for relevant
skills based on file type, cursor position, and selected code.

Example:
    >>> from session_buddy.integrations import IDEPluginProtocol, IDEContext
    >>> plugin = IDEPluginProtocol(db_path="skills.db")
    >>> context = IDEContext(
    ...     file_path="src/main.py",
    ...     line_number=42,
    ...     selected_code="def foo():",
    ...     language="python",
    ...     cursor_position=(42, 0),
    ...     project_name="myproject"
    ... )
    >>> suggestions = plugin.get_code_context_recommendations(context, limit=5)
    >>> for sugg in suggestions:
    ...     print(f"{sugg.skill_name}: {sugg.description}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from session_buddy.storage.skills_storage import SkillsStorage


# Keyboard shortcuts for common skills (IDE-specific)
SKILL_SHORTCUTS: dict[str, str] = {
    # Testing
    "pytest-run": "Ctrl+Shift+T",
    "pytest-coverage": "Ctrl+Shift+U",
    # Quality
    "ruff-format": "Ctrl+Alt+F",
    "ruff-check": "Ctrl+Alt+L",
    "mypy-check": "Ctrl+Alt+M",
    # Refactoring
    "refactoring-agent": "Ctrl+Shift+R",
    # Documentation
    "doc-generate": "Ctrl+Shift+D",
}


@dataclass
class IDEContext:
    """Context information from an IDE for skill recommendations.

    Attributes:
        file_path: Path to current file
        line_number: Current cursor line number (1-indexed)
        selected_code: Currently selected text (empty if no selection)
        language: Programming language (python, javascript, typescript, etc.)
        cursor_position: Tuple of (row, col) for precise cursor location
        project_name: Name of the current project
    """

    file_path: str
    line_number: int
    selected_code: str
    language: str
    cursor_position: tuple[int, int]
    project_name: str | None = None

    def __post_init__(self) -> None:
        """Validate context fields after initialization."""
        if self.line_number < 1:
            raise ValueError("line_number must be >= 1 (1-indexed)")

        row, col = self.cursor_position
        if row < 1 or col < 0:
            raise ValueError("cursor_position must be (row, col) with row>=1, col>=0")

    def get_file_extension(self) -> str:
        """Get file extension from file_path."""
        return Path(self.file_path).suffix.lstrip(".")

    def is_test_file(self) -> bool:
        """Check if current file appears to be a test file."""
        return "test" in Path(self.file_path).name.lower()

    def has_selection(self) -> bool:
        """Check if user has selected code."""
        return bool(self.selected_code.strip())


@dataclass
class IDESuggestion:
    """Skill recommendation for IDE display.

    Attributes:
        skill_name: Name of the recommended skill
        description: Human-readable description of what the skill does
        confidence: Confidence score (0.0 to 1.0)
        shortcut: Keyboard shortcut for invoking the skill
        estimated_duration_seconds: Expected duration in seconds
        workflow_phase: Oneiric workflow phase this skill belongs to
    """

    skill_name: str
    description: str
    confidence: float
    shortcut: str | None = None
    estimated_duration_seconds: float | None = None
    workflow_phase: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "skill_name": self.skill_name,
            "description": self.description,
            "confidence": self.confidence,
            "shortcut": self.shortcut,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "workflow_phase": self.workflow_phase,
        }


class IDEPluginProtocol:
    """IDE plugin protocol for code context recommendations.

    Provides intelligent skill recommendations based on:
    - File type and language
    - Cursor position within code structure
    - Selected code patterns
    - Project context

    Usage Pattern:
        1. Create IDEContext with current editor state
        2. Call get_code_context_recommendations()
        3. Display IDESuggestion objects to user
        4. User invokes skill (via shortcut or click)

    Attributes:
        db_path: Path to skills database
        storage: SkillsStorage instance for queries
    """

    # Language-specific skill patterns
    LANGUAGE_PATTERNS: dict[str, dict[str, list[str]]] = {
        "python": {
            "testing": ["pytest-run", "pytest-coverage", "pytest-debug"],
            "formatting": ["ruff-format", "black-format"],
            "linting": ["ruff-check", "pylint-check", "flake8-check"],
            "type_checking": ["mypy-check", "pyright-check"],
            "security": ["bandit-security", "safety-check"],
        },
        "javascript": {
            "testing": ["jest-run", "mocha-test"],
            "formatting": ["prettier-format", "eslint-format"],
            "linting": ["eslint-check"],
        },
        "typescript": {
            "testing": ["jest-run", "vitest-run"],
            "formatting": ["prettier-format"],
            "linting": ["eslint-check"],
            "type_checking": ["tsc-check"],
        },
    }

    # Code pattern detection for contextual recommendations
    PATTERN_MAPPINGS: dict[str, list[str]] = {
        # Test patterns
        r"\b(def test_|class Test|@pytest|@unittest)": [
            "pytest-run",
            "pytest-coverage",
        ],
        r"\b(describe|it|test)\(": ["jest-run", "vitest-run"],
        # Import patterns
        r"^import |^from ": ["ruff-check", "import-sort"],
        # Function/class definitions
        r"\bdef \w+\(": ["mypy-check", "ruff-check"],
        r"\bclass \w+\(": ["mypy-check", "pylint-check"],
        # Async patterns
        r"\basync def ": ["asyncio-check", "pytest-asyncio"],
        # Type hints
        r": \w+\[": ["mypy-check", "pyright-check"],
        # Docstrings
        r'"""': ["doc-generate", "docstring-check"],
        # SQL patterns
        r"\b(SELECT|INSERT|UPDATE|DELETE)\b": ["sql-lint", "sql-format"],
        # Security patterns
        r"\b(eval|exec|__import__)\(": ["bandit-security", "security-scan"],
        r"\bsubprocess\.": ["security-scan", "bandit-security"],
    }

    def __init__(self, db_path: str | Path) -> None:
        """Initialize IDE plugin.

        Args:
            db_path: Path to skills database file
        """
        self.db_path = Path(db_path)

        # Import here to avoid circular dependency
        from session_buddy.storage.skills_storage import SkillsStorage

        self.storage: SkillsStorage = SkillsStorage(db_path=self.db_path)

    def get_code_context_recommendations(
        self,
        context: IDEContext,
        limit: int = 5,
        min_completion_rate: float = 70.0,
    ) -> list[IDESuggestion]:
        """Get skill recommendations based on code context.

        Analyzes the current IDE context and recommends relevant skills
        based on file type, code patterns, and cursor position.

        Args:
            context: IDEContext with current editor state
            limit: Maximum number of recommendations to return
            min_completion_rate: Minimum completion rate threshold (percent)

        Returns:
            List of IDESuggestion objects, sorted by confidence

        Example:
            >>> context = IDEContext(
            ...     file_path="src/test_main.py",
            ...     line_number=42,
            ...     selected_code="def test_foo():",
            ...     language="python",
            ...     cursor_position=(42, 0),
            ...     project_name="myproject"
            ... )
            >>> suggestions = plugin.get_code_context_recommendations(context)
            >>> for sugg in suggestions:
            ...     print(f"{sugg.skill_name}: {sugg.description}")
        """
        # Build search query from context
        query = self._build_query_from_context(context)

        # Get workflow phase from context
        workflow_phase = self._infer_workflow_phase(context)

        # Search for matching skills
        recommendations = []

        # Try semantic search first
        try:
            from session_buddy.storage.skills_embeddings import (
                get_embedding_service,
                pack_embedding,
            )

            embedding_service = get_embedding_service()
            embedding_service.initialize()

            query_embedding = embedding_service.generate_embedding(query)

            if query_embedding:
                packed = pack_embedding(query_embedding)

                results = self.storage.search_by_query_workflow_aware(
                    packed_embedding=packed,
                    workflow_phase=workflow_phase,
                    limit=limit * 2,  # Get more, then filter
                    min_similarity=0.3,
                    phase_weight=0.4,  # Slight phase preference
                )

                for invocation, score in results:
                    # Filter by completion rate
                    if invocation.completed and score >= min_completion_rate / 100:
                        suggestion = self._generate_suggestion(
                            invocation.skill_name,
                            score,
                            context,
                        )
                        recommendations.append(suggestion)
        except Exception:
            # Embeddings unavailable, fall back to pattern matching
            pass

        # Fallback: Pattern-based recommendations
        if not recommendations:
            recommendations = self._pattern_based_recommendations(
                context,
                limit,
            )

        # Remove duplicates and sort by confidence
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec.skill_name not in seen:
                seen.add(rec.skill_name)
                unique_recommendations.append(rec)

        # Sort by confidence and limit
        unique_recommendations.sort(key=lambda x: x.confidence, reverse=True)
        return unique_recommendations[:limit]

    def _build_query_from_context(self, context: IDEContext) -> str:
        """Build semantic search query from IDE context.

        Args:
            context: IDEContext object

        Returns:
            Natural language query string
        """
        parts = []

        # Add language
        if context.language:
            parts.append(f"{context.language} code")

        # Add file type context
        if context.is_test_file():
            parts.append("testing")
        else:
            parts.append("production code")

        # Add selection context
        if context.has_selection():
            selection = context.selected_code.strip()
            # Extract first few keywords
            keywords = re.findall(r"\b\w{3,}\b", selection)[:3]
            if keywords:
                parts.append(" ".join(keywords))

        # Build query
        if parts:
            return " ".join(parts)
        else:
            return "code quality and testing"

    def _infer_workflow_phase(self, context: IDEContext) -> str:
        """Infer Oneiric workflow phase from context.

        Args:
            context: IDEContext object

        Returns:
            Workflow phase string
        """
        if context.is_test_file():
            return "execution"

        if context.has_selection():
            # User has selected code, likely refactoring
            selection = context.selected_code.strip().lower()
            if any(kw in selection for kw in ["import", "from"]):
                return "setup"
            return "execution"

        # Default to execution phase
        return "execution"

    def _pattern_based_recommendations(
        self,
        context: IDEContext,
        limit: int,
    ) -> list[IDESuggestion]:
        """Generate recommendations based on code pattern matching.

        Args:
            context: IDEContext object
            limit: Maximum recommendations

        Returns:
            List of IDESuggestion objects
        """
        recommendations = []

        # Check language-specific patterns
        language_patterns = self.LANGUAGE_PATTERNS.get(context.language, {})

        # Get code snippet around cursor
        code_to_check = context.selected_code or ""

        # Check pattern mappings
        for pattern, skill_names in self.PATTERN_MAPPINGS.items():
            if re.search(pattern, code_to_check, re.MULTILINE):
                for skill_name in skill_names:
                    suggestion = self._generate_suggestion(
                        skill_name,
                        0.8,  # High confidence for pattern matches
                        context,
                    )
                    recommendations.append(suggestion)

        # Add language-specific recommendations
        for category, skills in language_patterns.items():
            for skill_name in skills:
                if skill_name not in {r.skill_name for r in recommendations}:
                    suggestion = self._generate_suggestion(
                        skill_name,
                        0.6,  # Moderate confidence for language-based
                        context,
                    )
                    recommendations.append(suggestion)

        return recommendations[:limit]

    def _generate_suggestion(
        self,
        skill_name: str,
        confidence: float,
        context: IDEContext,
    ) -> IDESuggestion:
        """Generate IDESuggestion from skill name.

        Args:
            skill_name: Name of the skill
            confidence: Confidence score (0-1)
            context: IDEContext for description generation

        Returns:
            IDESuggestion object
        """
        # Get skill metrics for duration estimate
        metrics = self.storage.get_skill_metrics(skill_name)

        estimated_duration = None
        if metrics:
            estimated_duration = metrics.avg_duration_seconds

        # Get shortcut
        shortcut = SKILL_SHORTCUTS.get(skill_name)

        # Generate description
        description = self._generate_description(skill_name, context)

        # Infer workflow phase
        workflow_phase = self._infer_workflow_phase(context)

        return IDESuggestion(
            skill_name=skill_name,
            description=description,
            confidence=confidence,
            shortcut=shortcut,
            estimated_duration_seconds=estimated_duration,
            workflow_phase=workflow_phase,
        )

    def _generate_description(self, skill_name: str, context: IDEContext) -> str:
        """Generate human-readable description for a skill.

        Args:
            skill_name: Name of the skill
            context: IDEContext for context-aware descriptions

        Returns:
            Description string
        """
        # Base descriptions
        descriptions: dict[str, str] = {
            # Testing
            "pytest-run": "Run pytest test suite",
            "pytest-coverage": "Generate test coverage report",
            "pytest-debug": "Debug failing pytest tests",
            "jest-run": "Run Jest test suite",
            "vitest-run": "Run Vitest test suite",
            # Quality
            "ruff-format": "Format code with Ruff",
            "ruff-check": "Lint code with Ruff",
            "mypy-check": "Type check with mypy",
            "pyright-check": "Type check with Pyright",
            "eslint-check": "Lint code with ESLint",
            "prettier-format": "Format code with Prettier",
            # Security
            "bandit-security": "Security scan with Bandit",
            "safety-check": "Check dependency security",
            # Refactoring
            "refactoring-agent": "AI-powered refactoring",
            # Documentation
            "doc-generate": "Generate documentation",
        }

        base_desc = descriptions.get(
            skill_name,
            f"Invoke {skill_name}",
        )

        # Add context-specific hints
        if context.is_test_file():
            if "test" in skill_name.lower():
                return f"{base_desc} for current test file"
        elif context.has_selection():
            return f"{base_desc} on selected code"

        return base_desc

    def get_shortcut(self, skill_name: str) -> str | None:
        """Get keyboard shortcut for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Shortcut string or None if not defined
        """
        return SKILL_SHORTCUTS.get(skill_name)

    def register_shortcut(self, skill_name: str, shortcut: str) -> None:
        """Register a custom keyboard shortcut for a skill.

        Args:
            skill_name: Name of the skill
            shortcut: Shortcut key combination (e.g., "Ctrl+Shift+T")

        Example:
            >>> plugin.register_shortcut("my-custom-skill", "Ctrl+Alt+M")
        """
        SKILL_SHORTCUTS[skill_name] = shortcut

    def get_available_shortcuts(self) -> dict[str, str]:
        """Get all registered keyboard shortcuts.

        Returns:
            Dictionary mapping skill names to shortcuts
        """
        return SKILL_SHORTCUTS.copy()
