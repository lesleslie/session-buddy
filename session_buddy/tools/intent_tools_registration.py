"""Registration function for intent detection tools.

This module provides the registration function that integrates intent detection
tools with the MCP server.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_buddy.server import SessionBuddyServer

logger = logging.getLogger(__name__)


async def initialize_intent_detector() -> None:
    """Initialize intent detector on server startup."""
    from session_buddy.tools.intent_detection_tools import get_intent_detector

    await get_intent_detector()
    print("✅ Natural language intent detection system initialized")


# ============================================================================
# Intent Detection Helper Functions
# ============================================================================


async def _detect_intent_impl(
    user_message: str, confidence_threshold: float
) -> dict[str, Any]:
    """Core implementation for intent detection.

    Args:
        user_message: Natural language message from user
        confidence_threshold: Minimum confidence to suggest a tool (0.0-1.0)

    Returns:
        Detection result dictionary
    """
    from session_buddy.tools.intent_detection_tools import get_intent_detector

    detector = await get_intent_detector()
    match = await detector.detect_intent(user_message, confidence_threshold)

    if match:
        return _format_detected_intent(match)
    return await _format_no_intent_match(detector, user_message)


def _format_detected_intent(match: Any) -> dict[str, Any]:
    """Format detected intent result.

    Args:
        match: Detected intent match

    Returns:
        Formatted result dictionary
    """
    return {
        "detected": True,
        "tool_name": match.tool_name,
        "confidence": match.confidence,
        "extracted_args": match.extracted_args,
        "disambiguation_needed": match.disambiguation_needed,
        "alternatives": match.alternatives,
        "message": (
            f"I detected you want to use '{match.tool_name}' "
            f"(confidence: {match.confidence:.0%}). "
            f"You can say '/{match.tool_name}' or just continue using natural language."
        ),
    }


async def _format_no_intent_match(detector: Any, user_message: str) -> dict[str, Any]:
    """Format result when no intent match is found.

    Args:
        detector: Intent detector instance
        user_message: User's message

    Returns:
        Formatted result with suggestions
    """
    suggestions = await detector.get_suggestions(user_message, limit=3)

    if suggestions:
        suggestions_str = ", ".join(
            [f"{s['tool']} ({s['confidence']:.0%})" for s in suggestions]
        )
        return {
            "detected": False,
            "message": (
                f"I wasn't confident enough to auto-execute. "
                f"Possible matches: {suggestions_str}. "
                f"Please be more specific or use the exact tool name."
            ),
            "suggestions": suggestions,
        }
    return {
        "detected": False,
        "message": (
            "I couldn't determine which tool you want. "
            "Try being more specific, or use '/help' to see available tools."
        ),
    }


def _format_intent_error(error_message: str) -> dict[str, Any]:
    """Format intent detection error result.

    Args:
        error_message: The error message

    Returns:
        Formatted error dictionary
    """
    return {
        "detected": False,
        "error": error_message,
        "message": "Intent detection system encountered an error. Please use exact tool names.",
    }


async def _get_intent_suggestions_impl(user_message: str, limit: int) -> dict[str, Any]:
    """Core implementation for getting intent suggestions.

    Args:
        user_message: Natural language message that was unclear
        limit: Maximum number of suggestions to return

    Returns:
        Suggestions result dictionary
    """
    from session_buddy.tools.intent_detection_tools import get_intent_detector

    detector = await get_intent_detector()
    suggestions = await detector.get_suggestions(user_message, limit)

    if suggestions:
        return {
            "suggestions": suggestions,
            "message": f"Found {len(suggestions)} possible tool matches",
            "count": len(suggestions),
        }
    return {
        "suggestions": [],
        "message": "No matching tools found for this message",
        "count": 0,
    }


def _format_suggestions_error(error_message: str) -> dict[str, Any]:
    """Format suggestions error result.

    Args:
        error_message: The error message

    Returns:
        Formatted error dictionary
    """
    return {
        "suggestions": [],
        "error": error_message,
        "message": "Failed to generate suggestions",
        "count": 0,
    }


async def _list_supported_intents_impl() -> dict[str, Any]:
    """Core implementation for listing supported intents.

    Returns:
        Intents list result dictionary
    """
    from session_buddy.tools.intent_detection_tools import get_intent_detector

    detector = await get_intent_detector()
    tools_info = _build_tools_info(detector)

    return {
        "tools": tools_info,
        "total_tools": len(tools_info),
        "message": (
            f"Intent detection supports {len(tools_info)} tools. "
            "Use natural language to trigger any of these tools."
        ),
    }


def _build_tools_info(detector: Any) -> dict[str, Any]:
    """Build tools information dictionary.

    Args:
        detector: Intent detector instance

    Returns:
        Dictionary of tool information
    """
    tools_info = {}
    for tool_name in detector.patterns.keys():
        tools_info[tool_name] = {
            "patterns": detector.patterns.get(tool_name, []),
            "semantic_examples": detector.semantic_examples.get(tool_name, []),
            "has_argument_extraction": (tool_name in detector.argument_extraction),
        }

    return tools_info


def _format_list_intents_error(error_message: str) -> dict[str, Any]:
    """Format list intents error result.

    Args:
        error_message: The error message

    Returns:
        Formatted error dictionary
    """
    return {
        "tools": {},
        "total_tools": 0,
        "error": error_message,
        "message": "Failed to list supported intents",
    }


# ============================================================================
# Tool Registration Function
# ============================================================================


def register_intent_detection_tools(server: SessionBuddyServer) -> None:
    """Register intent detection tools with the MCP server.

    Args:
        server: SessionBuddyServer instance to register tools on
    """

    @server.tool()  # type: ignore[misc]
    async def detect_intent(
        user_message: str, confidence_threshold: float = 0.7
    ) -> dict[str, Any]:
        """Detect user intent and suggest appropriate MCP tool.

        This tool analyzes natural language messages to determine which
        MCP tool the user wants to invoke. It uses both semantic matching
        (embeddings) and keyword patterns for robust detection.

        Args:
            user_message: Natural language message from user
            confidence_threshold: Minimum confidence to suggest a tool (0.0-1.0)

        Returns:
            Dictionary with:
                - detected: Boolean indicating if intent was detected
                - tool_name: Name of detected tool (if any)
                - confidence: Confidence score (0.0-1.0)
                - extracted_args: Arguments extracted from message
                - disambiguation_needed: Whether multiple tools matched closely
                - alternatives: Alternative tool names if ambiguous
                - message: Human-readable explanation

        Examples:
            >>> detect_intent("what did I learn about async?")
            {'detected': True, 'tool_name': 'search_reflections', ...}

            >>> detect_intent("save my progress")
            {'detected': True, 'tool_name': 'checkpoint', ...}
        """
        try:
            return await _detect_intent_impl(user_message, confidence_threshold)
        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            return _format_intent_error(str(e))

    @server.tool()  # type: ignore[misc]
    async def get_intent_suggestions(
        user_message: str, limit: int = 5
    ) -> dict[str, Any]:
        """Get tool suggestions for an ambiguous message.

        When intent is unclear, this tool provides a ranked list of potential
        tool matches with confidence scores.

        Args:
            user_message: Natural language message that was unclear
            limit: Maximum number of suggestions to return

        Returns:
            Dictionary with:
                - suggestions: List of suggestions with tool, confidence, match_type
                - message: Human-readable explanation
                - count: Number of suggestions found

        Examples:
            >>> get_intent_suggestions("check code")
            {
                'suggestions': [
                    {'tool': 'quality_monitor', 'confidence': 0.85, 'match_type': 'pattern'},
                    {'tool': 'crackerjack_health_check', 'confidence': 0.72, 'match_type': 'semantic'}
                ],
                'message': 'Found 2 possible matches...',
                'count': 2
            }
        """
        try:
            return await _get_intent_suggestions_impl(user_message, limit)
        except Exception as e:
            logger.error(f"Intent suggestions failed: {e}")
            return _format_suggestions_error(str(e))

    @server.tool()  # type: ignore[misc]
    async def list_supported_intents() -> dict[str, Any]:
        """List all supported intent patterns and their tools.

        This shows which natural language phrases can trigger which tools,
        useful for discovering the intent detection capabilities.

        Returns:
            Dictionary with:
                - tools: Dictionary of tool names to their patterns
                - total_tools: Total number of supported tools
                - message: Human-readable overview

        Examples:
            >>> list_supported_intents()
            {
                'tools': {
                    'checkpoint': {
                        'patterns': ['save my progress', 'checkpoint this'],
                        'semantic_examples': ["I've made good progress..."]
                    },
                    ...
                },
                'total_tools': 15
            }
        """
        try:
            return await _list_supported_intents_impl()
        except Exception as e:
            logger.error(f"Listing intents failed: {e}")
            return _format_list_intents_error(str(e))
