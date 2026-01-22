"""Natural Language Intent Detection for MCP tool activation.

This module provides intelligent intent detection that allows users to trigger
MCP tools using natural language instead of requiring exact slash command syntax.

Architecture:
    IntentDetector → semantic_match + pattern_match → ToolMatch → tool execution
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import yaml

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ToolMatch:
    """Result of intent detection.

    Attributes:
        tool_name: Name of the matched MCP tool
        confidence: Confidence score (0.0 to 1.0)
        extracted_args: Arguments extracted from natural language
        disambiguation_needed: Whether multiple tools matched closely
        alternatives: Alternative tool names if disambiguation needed
    """

    tool_name: str
    confidence: float
    extracted_args: dict[str, Any]
    disambiguation_needed: bool = False
    alternatives: list[str] = field(default_factory=list)


class IntentDetector:
    """Detect user intent and map to MCP tools.

    Uses hybrid approach:
    1. Semantic matching with embeddings (understands meaning)
    2. Pattern matching with keywords (fast keyword detection)
    3. Confidence combination (best of both approaches)
    """

    def __init__(self) -> None:
        """Initialize intent detector."""
        self.patterns: dict[str, list[str]] = {}
        self.semantic_examples: dict[str, list[str]] = {}
        self.argument_extraction: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """Load intent patterns from configuration.

        Loads training data from YAML file containing:
        - Keyword patterns for fast matching
        - Semantic examples for embedding-based matching
        - Argument extraction rules
        """
        try:
            patterns_path = (
                Path(__file__).parent.parent / "data" / "intent_patterns.yaml"
            )

            if not patterns_path.exists():
                logger.warning(
                    f"Intent patterns file not found: {patterns_path}. "
                    "Using default patterns."
                )
                self._load_default_patterns()
                return

            with patterns_path.open() as f:
                config = yaml.safe_load(f)

            for tool, data in config.items():
                self.patterns[tool] = data.get("patterns", [])
                self.semantic_examples[tool] = data.get("semantic_examples", [])
                self.argument_extraction[tool] = data.get("argument_extraction", {})

            logger.info(
                f"Loaded intent patterns for {len(self.patterns)} tools: "
                f"{', '.join(self.patterns.keys())}"
            )

        except Exception as e:
            logger.error(f"Failed to load intent patterns: {e}")
            self._load_default_patterns()

    def _load_default_patterns(self) -> None:
        """Load fallback patterns when YAML file unavailable."""
        self.patterns = {
            "checkpoint": [
                "save my progress",
                "create a checkpoint",
                "checkpoint this",
            ],
            "search_reflections": [
                "what did I learn about",
                "find insights on",
                "search for",
            ],
            "quality_monitor": [
                "how's the code quality",
                "check quality",
                "analyze project health",
            ],
        }
        self.semantic_examples = {
            "checkpoint": [
                "I've made good progress, let me save",
                "Time to checkpoint before the next feature",
            ],
            "search_reflections": [
                "What did I learn about error handling?",
                "Find my insights on authentication",
            ],
            "quality_monitor": [
                "How is the code quality looking?",
                "What's the current project health?",
            ],
        }
        self.argument_extraction = {}

    async def detect_intent(
        self,
        user_message: str,
        confidence_threshold: float = 0.7,
    ) -> ToolMatch | None:
        """Match user message to tool intent.

        Args:
            user_message: Natural language message from user
            confidence_threshold: Minimum confidence to return a match (0.0-1.0)

        Returns:
            ToolMatch if confident match found, None otherwise
        """
        # Skip if empty message
        if not user_message or not user_message.strip():
            return None

        # 1. Try semantic matching with embeddings
        semantic_match = await self._semantic_match(user_message)

        # 2. Try pattern matching
        pattern_match = self._pattern_match(user_message)

        # 3. Combine scores
        best_match = self._combine_matches(semantic_match, pattern_match)

        if best_match and best_match.confidence >= confidence_threshold:
            # 4. Extract arguments from message
            best_match.extracted_args = await self._extract_arguments(
                user_message, best_match.tool_name
            )
            return best_match

        return None

    async def _semantic_match(self, user_message: str) -> ToolMatch | None:
        """Match using embeddings.

        Compares user message embedding against semantic examples
        for each tool using cosine similarity.

        Args:
            user_message: User's natural language message

        Returns:
            ToolMatch if good semantic match found, None otherwise
        """
        try:
            # Import here to avoid hard dependency on embedding system
            from session_buddy.reflection_tools import generate_embedding

            # Generate embedding for user message
            query_embedding = await generate_embedding(user_message)

            best_tool: str | None = None
            best_score = 0.0

            # Compare against semantic examples for each tool
            for tool, examples in self.semantic_examples.items():
                for example in examples:
                    example_embedding = await generate_embedding(example)

                    # Cosine similarity: dot product of normalized vectors
                    similarity = float(
                        np.dot(query_embedding, example_embedding)
                        / (
                            np.linalg.norm(query_embedding)
                            * np.linalg.norm(example_embedding)
                        )
                    )

                    if similarity > best_score:
                        best_score = similarity
                        best_tool = tool

            # Return match if similarity is high enough
            if best_tool and best_score > 0.6:
                return ToolMatch(
                    tool_name=best_tool, confidence=best_score, extracted_args={}
                )

        except ImportError:
            logger.info(
                "Embedding system unavailable, skipping semantic match. "
                "Pattern matching will be used instead."
            )
        except Exception as e:
            logger.error(f"Semantic matching failed: {e}")

        return None

    def _pattern_match(self, user_message: str) -> ToolMatch | None:
        """Match using keyword patterns.

        Fast keyword-based matching for common phrases.

        Args:
            user_message: User's natural language message

        Returns:
            ToolMatch if pattern match found, None otherwise
        """
        message_lower = user_message.lower()

        for tool, patterns in self.patterns.items():
            for pattern in patterns:
                if pattern.lower() in message_lower:
                    # Fixed confidence for pattern match
                    return ToolMatch(tool_name=tool, confidence=0.8, extracted_args={})

        return None

    def _combine_matches(
        self,
        semantic: ToolMatch | None,
        pattern: ToolMatch | None,
    ) -> ToolMatch | None:
        """Combine semantic and pattern matching results.

        Args:
            semantic: Result from semantic matching (may be None)
            pattern: Result from pattern matching (may be None)

        Returns:
            Combined ToolMatch, or None if both are None
        """
        if not semantic and not pattern:
            return None

        # Both agree - high confidence
        if semantic and pattern and semantic.tool_name == pattern.tool_name:
            return ToolMatch(
                tool_name=semantic.tool_name,
                confidence=min(0.95, semantic.confidence + 0.2),
                extracted_args={},
            )

        # Only semantic match
        if semantic and not pattern:
            return semantic

        # Only pattern match
        if pattern and not semantic:
            return pattern

        # Disagree - return higher confidence with alternatives
        result: ToolMatch | None = None

        if semantic and pattern and semantic.confidence > pattern.confidence:
            result = semantic
            result.alternatives = [pattern.tool_name]  # type: ignore[attr-defined]
        elif semantic and pattern:
            result = pattern
            result.alternatives = [semantic.tool_name]  # type: ignore[attr-defined]
        else:
            # Handle case where one is None
            result = semantic or pattern

        if result:
            result.disambiguation_needed = True  # type: ignore[attr-defined]

        return result

    async def _extract_arguments(
        self,
        user_message: str,
        tool_name: str,
    ) -> dict[str, Any]:
        """Extract tool arguments from natural language.

        Uses regex patterns to extract named arguments from user message.

        Args:
            user_message: User's natural language message
            tool_name: Name of the matched tool

        Returns:
            Dictionary of extracted argument names to values
        """
        args: dict[str, Any] = {}

        if tool_name not in self.argument_extraction:
            return args

        extraction_rules = self.argument_extraction[tool_name]

        for arg_name, rules in extraction_rules.items():
            for pattern in rules.get("patterns", []):
                match = re.search(pattern, user_message, re.IGNORECASE)
                if match:
                    args[arg_name] = match.group(1)
                    break

        return args

    async def get_suggestions(
        self, user_message: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Get tool suggestions for ambiguous messages.

        Returns potential tool matches with confidence scores
        when intent is unclear or confidence is low.

        Args:
            user_message: User's natural language message
            limit: Maximum number of suggestions to return

        Returns:
            List of suggestion dictionaries with tool name and confidence
        """
        suggestions = []

        # Get semantic match
        semantic = await self._semantic_match(user_message)

        # Get pattern match
        pattern = self._pattern_match(user_message)

        # Add both if they exist
        if semantic:
            suggestions.append(
                {
                    "tool": semantic.tool_name,
                    "confidence": semantic.confidence,
                    "match_type": "semantic",
                }
            )

        if pattern and (not semantic or pattern.tool_name != semantic.tool_name):
            suggestions.append(
                {
                    "tool": pattern.tool_name,
                    "confidence": pattern.confidence,
                    "match_type": "pattern",
                }
            )

        # Sort by confidence
        suggestions.sort(
            key=lambda s: s["confidence"]
            if isinstance(s["confidence"], (int, float))
            else 0,
            reverse=True,
        )

        return suggestions[:limit]
