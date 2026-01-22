"""Context window optimization for intelligent token management.

This module provides dynamic context injection to maximize the value
of each token while staying within context window limits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ContextOptimizer:
    """Optimize context window by prioritizing high-value content."""

    def __init__(self, max_tokens: int = 180000):
        """Initialize context optimizer.

        Args:
            max_tokens: Maximum context window size (default: 180k for Claude 3.5)
        """
        self.max_tokens = max_tokens
        self.project_contexts = {
            "python": {
                "extensions": [".py"],
                "patterns": [
                    "type hints",
                    "docstrings",
                    "async/await",
                    "decorators",
                    "context managers",
                ],
                "anti_patterns": [
                    "suppress(Exception)",
                    "pass  # TODO",
                    "except:",
                ],
            },
            "typescript": {
                "extensions": [".ts", ".tsx"],
                "patterns": [
                    "interface definitions",
                    "type annotations",
                    "generics",
                    "decorators",
                ],
                "anti_patterns": [
                    "suppress",
                    "any",
                    "@ts-ignore",
                ],
            },
            "rust": {
                "extensions": [".rs"],
                "patterns": [
                    "impl blocks",
                    "trait definitions",
                    "lifetime annotations",
                    "macros",
                ],
                "anti_patterns": [
                    "unsafe",
                    "panic!",
                ],
            },
        }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Rough approximation: 1 token ≈ 4 characters
        return len(text) // 4

    def load_project_context(
        self, project_path: str | Path, project_type: str | None = None
    ) -> dict[str, Any]:
        """Load project-specific context for intelligent filtering.

        Args:
            project_path: Path to project directory
            project_type: Optional project type override

        Returns:
            Project context dictionary
        """
        path_obj: Path = Path(project_path)

        # Auto-detect project type if not provided
        if project_type is None:
            project_type = self._detect_project_type(path_obj)

        # Get context configuration for project type
        context_config = self.project_contexts.get(project_type, {})

        # Load project structure
        structure = self._analyze_project_structure(path_obj)

        return {
            "project_type": project_type,
            "patterns": context_config.get("patterns", []),
            "anti_patterns": context_config.get("anti_patterns", []),
            "extensions": context_config.get("extensions", []),
            "structure": structure,
        }

    def _detect_project_type(self, project_path: Path) -> str:
        """Detect project type from directory structure.

        Args:
            project_path: Path to project directory

        Returns:
            Detected project type (python, typescript, rust, or generic)
        """
        # Check for Python
        if (project_path / "pyproject.toml").exists() or (
            project_path / "setup.py"
        ).exists():
            return "python"

        # Check for TypeScript/Node
        if (project_path / "package.json").exists() or (
            project_path / "tsconfig.json"
        ).exists():
            return "typescript"

        # Check for Rust
        if (project_path / "Cargo.toml").exists():
            return "rust"

        # Default to generic
        return "generic"

    def _analyze_project_structure(self, project_path: Path) -> dict[str, Any]:
        """Analyze project directory structure.

        Args:
            project_path: Path to project directory

        Returns:
            Project structure metadata
        """
        try:
            # Count files by extension
            extension_counts = {}
            total_files = 0

            for ext in ("*.py", "*.ts", "*.tsx", "*.rs", "*.go", "*.java"):
                matches = list(project_path.rglob(ext))
                count = len(matches)
                if count > 0:
                    extension_counts[ext] = count
                    total_files += count

            # Identify key directories
            directories = []
            for dir_name in ("src", "lib", "app", "test", "tests"):
                dir_path = project_path / dir_name
                if dir_path.is_dir():
                    directories.append(dir_name)

            return {
                "extension_counts": extension_counts,
                "total_files": total_files,
                "key_directories": directories,
            }

        except Exception:
            return {
                "extension_counts": {},
                "total_files": 0,
                "key_directories": [],
            }

    def optimize_context_for_task(
        self,
        task_description: str,
        project_context: dict[str, Any],
        available_tokens: int,
        relevant_patterns: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate optimized context for a specific task.

        Args:
            task_description: Current task description
            project_context: Project context from load_project_context()
            available_tokens: Tokens available for context
            relevant_patterns: Optional list of relevant patterns

        Returns:
            Optimized context string
        """
        context_parts = []
        tokens_used = 0

        # 1. Add project context (highest priority)
        project_ctx = self._format_project_context(project_context)
        project_tokens = self.estimate_tokens(project_ctx)

        if (
            project_tokens <= available_tokens * 0.3
        ):  # Use up to 30% for project context
            context_parts.append(project_ctx)
            tokens_used += project_tokens
        else:
            # Truncate project context
            project_ctx = self._truncate_context(
                project_ctx, int(available_tokens * 0.3)
            )
            context_parts.append(project_ctx)
            tokens_used += int(available_tokens * 0.3)

        # 2. Add relevant patterns (high priority)
        if relevant_patterns:
            patterns_ctx = self._format_patterns(relevant_patterns)
            patterns_tokens = self.estimate_tokens(patterns_ctx)

            if (
                tokens_used + patterns_tokens <= available_tokens * 0.5
            ):  # Use up to 50% total
                context_parts.append(patterns_ctx)
                tokens_used += patterns_tokens
            else:
                # Truncate patterns
                remaining = int(available_tokens * 0.5) - tokens_used
                patterns_ctx = self._truncate_context(patterns_ctx, remaining)
                context_parts.append(patterns_ctx)
                tokens_used += remaining

        # 3. Add task-specific guidance
        task_guidance = self._generate_task_guidance(task_description, project_context)
        task_tokens = self.estimate_tokens(task_guidance)

        remaining_tokens = available_tokens - tokens_used
        if task_tokens <= remaining_tokens:
            context_parts.append(task_guidance)
            tokens_used += task_tokens
        else:
            task_guidance = self._truncate_context(task_guidance, remaining_tokens)
            context_parts.append(task_guidance)

        return "\n\n".join(context_parts)

    def _format_project_context(self, project_context: dict[str, Any]) -> str:
        """Format project context for injection.

        Args:
            project_context: Project context dictionary

        Returns:
            Formatted context string
        """
        parts = [f"Project Type: {project_context['project_type']}"]

        if project_context.get("patterns"):
            parts.append(
                f"Patterns to Look For: {', '.join(project_context['patterns'])}"
            )

        if project_context.get("anti_patterns"):
            parts.append(f"Avoid: {', '.join(project_context['anti_patterns'])}")

        structure = project_context.get("structure", {})
        if structure.get("key_directories"):
            parts.append(f"Key Directories: {', '.join(structure['key_directories'])}")

        return "\n".join(parts)

    def _format_patterns(self, patterns: list[dict[str, Any]]) -> str:
        """Format relevant patterns for injection.

        Args:
            patterns: List of pattern dictionaries

        Returns:
            Formatted patterns string
        """
        if not patterns:
            return "No relevant patterns found."

        parts = ["Relevant Patterns from Other Projects:"]
        for i, pattern in enumerate(patterns[:3], 1):  # Top 3 patterns
            parts.extend(
                (
                    f"\n{i}. {pattern.get('name', 'Unknown')}",
                    f"   From: {pattern.get('project_id', 'Unknown')}",
                    f"   Success Rate: {pattern.get('outcome_score', 0):.0%}",
                    f"   Similarity: {pattern.get('similarity', 0):.0%}",
                )
            )

            # Add context/problem
            context_snapshot = json.loads(pattern.get("context_snapshot", "{}"))
            if "problem" in context_snapshot:
                parts.append(f"   Problem: {context_snapshot['problem']}")

            # Add solution approach
            solution_snapshot = json.loads(pattern.get("solution_snapshot", "{}"))
            if "approach" in solution_snapshot:
                parts.append(f"   Solution: {solution_snapshot['approach']}")

        return "\n".join(parts)

    def _generate_task_guidance(
        self, task_description: str, project_context: dict[str, Any]
    ) -> str:
        """Generate task-specific guidance.

        Args:
            task_description: Current task description
            project_context: Project context dictionary

        Returns:
            Task guidance string
        """
        project_type = project_context.get("project_type", "generic")

        guidance = {
            "python": "Focus on type hints, docstrings, and error handling. Avoid suppressing exceptions.",
            "typescript": "Use strict types, avoid 'any', and prefer interfaces over types.",
            "rust": "Prefer safe code over unsafe, handle errors properly, use lifetimes judiciously.",
            "generic": "Write clear, maintainable code with proper error handling.",
        }

        return f"Guidance: {guidance.get(project_type, guidance['generic'])}"

    def _truncate_context(self, context: str, max_tokens: int) -> str:
        """Truncate context to fit within token budget.

        Args:
            context: Context string
            max_tokens: Maximum tokens to use

        Returns:
            Truncated context string
        """
        # Rough character limit (4 chars per token)
        max_chars = max_tokens * 4

        if len(context) <= max_chars:
            return context

        # Truncate with ellipsis
        return context[: max_chars - 3] + "..."


# Singleton instance for import convenience
_instance: ContextOptimizer | None = None


def get_context_optimizer(max_tokens: int = 180000) -> ContextOptimizer:
    """Get or create context optimizer instance.

    Args:
        max_tokens: Maximum context window size

    Returns:
        ContextOptimizer instance
    """
    global _instance
    if _instance is None:
        _instance = ContextOptimizer(max_tokens=max_tokens)
    return _instance
