"""Conversation summary utilities.

This module provides helper functions for creating and processing conversation
summaries, extracting key topics, decisions, and next steps from reflections.
"""

from __future__ import annotations

from typing import Any


def create_empty_summary() -> dict[str, Any]:
    """Create empty conversation summary structure."""
    return {
        "key_topics": [],
        "decisions_made": [],
        "next_steps": [],
        "problems_solved": [],
        "code_changes": [],
    }


def extract_topics_from_content(content: str) -> set[str]:
    """Extract topics from reflection content."""
    topics: set[str] = set()
    if "project context:" in content:
        context_part = content.split("project context:")[1].split(".")[0]
        topics.update(word.strip() for word in context_part.split(","))
    return topics


def extract_decisions_from_content(content: str) -> list[str]:
    """Extract decisions from reflection content."""
    decisions = []
    if "excellent" in content:
        decisions.append("Maintaining productive workflow patterns")
    elif "attention" in content:
        decisions.append("Identified areas needing workflow optimization")
    elif "good progress" in content:
        decisions.append("Steady development progress confirmed")
    return decisions


def extract_next_steps_from_content(content: str) -> list[str]:
    """Extract next steps from reflection content."""
    next_steps = []
    if "priority:" in content:
        priority_part = content.split("priority:")[1].split(".")[0]
        if priority_part.strip():
            next_steps.append(priority_part.strip())
    return next_steps


async def process_recent_reflections(db: Any, summary: dict[str, Any]) -> None:
    """Process recent reflections to extract conversation insights."""
    recent_reflections = await db.search_reflections("checkpoint", limit=5)

    if not recent_reflections:
        return

    topics = set()
    decisions = []
    next_steps = []

    for reflection in recent_reflections:
        content = reflection["content"].lower()

        topics.update(extract_topics_from_content(content))
        decisions.extend(extract_decisions_from_content(content))
        next_steps.extend(extract_next_steps_from_content(content))

    summary["key_topics"] = list(topics)[:5]
    summary["decisions_made"] = decisions[:3]
    summary["next_steps"] = next_steps[:3]


def ensure_summary_defaults(summary: dict[str, Any]) -> None:
    """Ensure summary has default values if empty."""
    if not summary["key_topics"]:
        summary["key_topics"] = [
            "session management",
            "workflow optimization",
        ]

    if not summary["decisions_made"]:
        summary["decisions_made"] = ["Proceeding with current development approach"]

    if not summary["next_steps"]:
        summary["next_steps"] = ["Continue with regular checkpoint monitoring"]


def get_fallback_summary() -> dict[str, Any]:
    """Get fallback summary when reflection processing fails."""
    return {
        "key_topics": ["development session", "workflow management"],
        "decisions_made": ["Maintaining current session approach"],
        "next_steps": ["Continue monitoring session quality"],
        "problems_solved": ["Session management optimization"],
        "code_changes": ["Enhanced checkpoint functionality"],
    }


def get_error_summary(error: Exception) -> dict[str, Any]:
    """Get error summary when conversation analysis fails."""
    return {
        "key_topics": ["session analysis"],
        "decisions_made": ["Error during analysis"],
        "next_steps": ["Retry conversation summary"],
        "problems_solved": [],
        "code_changes": [],
        "error": str(error),
    }
