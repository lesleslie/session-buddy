"""MCP tools for Intelligence Engine - skill management and workflow suggestions.

This module provides MCP tools for:
- Listing learned skills
- Invoking skills for workflow guidance
- Getting proactive improvement suggestions
- Managing skill lifecycle
"""

from __future__ import annotations

import typing as t

from session_buddy.core.intelligence import IntelligenceEngine
from session_buddy.server import mcp

# Global intelligence engine instance (initialized at startup)
_intelligence_engine: IntelligenceEngine | None = None


def get_intelligence_engine() -> IntelligenceEngine:
    """Get or create global intelligence engine instance."""
    global _intelligence_engine
    if _intelligence_engine is None:
        _intelligence_engine = IntelligenceEngine()
    return _intelligence_engine


@mcp.tool()
async def list_skills(
    min_success_rate: float = 0.0, limit: int = 20
) -> dict[str, t.Any]:
    """List learned skills available for workflow guidance.

    Args:
        min_success_rate: Minimum success rate filter (0.0 to 1.0)
        limit: Maximum number of skills to return

    Returns:
        Dictionary with list of skills and metadata
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    skills = await engine.list_skills(
        min_success_rate=min_success_rate,
        limit=limit,
    )

    return {
        "success": True,
        "count": len(skills),
        "skills": skills,
        "message": f"Found {len(skills)} skill(s) with success rate ≥ {min_success_rate:.0%}",
    }


@mcp.tool()
async def get_skill_details(skill_name: str) -> dict[str, t.Any]:
    """Get detailed information about a specific skill.

    Args:
        skill_name: Name of the skill to query

    Returns:
        Skill details with pattern information and usage statistics
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    if skill_name not in engine.skill_library:
        return {
            "success": False,
            "error": f"Skill '{skill_name}' not found in library",
            "available_skills": list(engine.skill_library.keys()),
        }

    skill = engine.skill_library[skill_name]

    return {
        "success": True,
        "skill": {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "success_rate": skill.success_rate,
            "invocations": skill.invocations,
            "created_at": skill.created_at.isoformat(),
            "last_used": skill.last_used.isoformat() if skill.last_used else "Never",
            "tags": skill.tags,
            "pattern": skill.pattern,
            "learned_from_sessions": skill.learned_from,
            "usage_count": len(skill.learned_from),
        },
    }


@mcp.tool()
async def invoke_skill(
    skill_name: str, context: dict[str, t.Any] | None = None
) -> dict[str, t.Any]:
    """Invoke a learned skill to get workflow guidance.

    Use this when you want to apply a successful pattern from past sessions
    to your current work.

    Args:
        skill_name: Name of the skill to invoke
        context: Optional current session context for relevance checking

    Returns:
        Skill invocation result with suggested actions
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    result = await engine.invoke_skill(
        skill_name=skill_name,
        context=context or {},
    )

    if result["success"]:
        # Add helpful metadata
        result["message"] = (
            f"Skill '{skill_name}' invoked successfully. "
            f"See suggested actions below for workflow guidance."
        )

    return result


@mcp.tool()
async def suggest_improvements(
    current_session: dict[str, t.Any] | None = None,
) -> dict[str, t.Any]:
    """Get proactive workflow improvement suggestions based on learned skills.

    This tool analyzes your current session context and suggests relevant
    skills and patterns that have been successful in similar situations.

    Args:
        current_session: Optional current session context for matching

    Returns:
        List of workflow suggestions sorted by relevance
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    suggestions = await engine.suggest_workflow_improvements(
        current_session=current_session or {}
    )

    if not suggestions:
        return {
            "success": True,
            "found_suggestions": False,
            "suggestions": [],
            "message": (
                "No relevant suggestions found. "
                "As you complete more sessions, the system will learn patterns "
                "and provide proactive guidance."
            ),
        }

    return {
        "success": True,
        "found_suggestions": True,
        "count": len(suggestions),
        "suggestions": [
            {
                "skill_name": s.skill_name,
                "description": s.description,
                "success_rate": s.success_rate,
                "relevance": s.relevance,
                "suggested_actions": s.suggested_actions,
                "rationale": s.rationale,
            }
            for s in suggestions
        ],
        "message": f"Found {len(suggestions)} relevant suggestion(s) based on learned patterns.",
    }


@mcp.tool()
async def trigger_learning(checkpoint_data: dict[str, t.Any]) -> dict[str, t.Any]:
    """Manually trigger learning from a checkpoint.

    This is typically called automatically by the POST_CHECKPOINT hook,
    but you can use it to manually trigger learning after high-quality work.

    Args:
        checkpoint_data: Checkpoint data with quality score and history

    Returns:
        Learning results with any skills created or updated
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    quality_score = checkpoint_data.get("quality_score", 0)

    if quality_score < 75:
        return {
            "success": True,
            "triggered_learning": False,
            "skills_created": [],
            "message": (
                f"Quality score ({quality_score:.0f}/100) below threshold (75). "
                "Learning only triggered for quality checkpoints ≥75."
            ),
        }

    skill_ids = await engine.learn_from_checkpoint(checkpoint_data)

    if not skill_ids:
        return {
            "success": True,
            "triggered_learning": True,
            "skills_created": [],
            "message": (
                "Learning triggered, but no new skills created. "
                "Patterns need to appear in 3+ sessions to consolidate into skills."
            ),
        }

    return {
        "success": True,
        "triggered_learning": True,
        "skills_created": skill_ids,
        "count": len(skill_ids),
        "message": f"Learning successful! Created/updated {len(skill_ids)} skill(s).",
    }


@mcp.tool()
async def get_intelligence_stats() -> dict[str, t.Any]:
    """Get statistics about the intelligence system.

    Returns metrics about:
    - Total skills in library
    - Average success rate
    - Most invoked skills
    - Recent learning activity

    Returns:
        Intelligence system statistics
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    total_skills = len(engine.skill_library)

    if total_skills == 0:
        return {
            "success": True,
            "total_skills": 0,
            "average_success_rate": 0.0,
            "most_invoked_skills": [],
            "message": "No skills learned yet. System learns from high-quality checkpoints.",
        }

    # Calculate average success rate
    avg_success_rate = (
        sum(skill.success_rate for skill in engine.skill_library.values())
        / total_skills
    )

    # Find most invoked skills
    most_invoked = sorted(
        engine.skill_library.values(),
        key=lambda s: s.invocations,
        reverse=True,
    )[:5]

    return {
        "success": True,
        "total_skills": total_skills,
        "average_success_rate": avg_success_rate,
        "most_invoked_skills": [
            {
                "name": skill.name,
                "invocations": skill.invocations,
                "success_rate": skill.success_rate,
                "last_used": skill.last_used.isoformat()
                if skill.last_used
                else "Never",
            }
            for skill in most_invoked
        ],
        "message": f"Intelligence system has learned {total_skills} skill(s) from past sessions.",
    }


@mcp.tool()
async def capture_successful_pattern(
    pattern_type: str,
    project_id: str,
    context: dict[str, t.Any],
    solution: dict[str, t.Any],
    outcome_score: float,
    tags: list[str] | None = None,
) -> dict[str, t.Any]:
    """Capture a successful pattern for cross-project reuse.

    This tool extracts and stores successful solutions from one project so they
    can be automatically suggested when similar problems arise in other projects.

    Use this after successfully resolving a complex issue that other projects
    might benefit from knowing about.

    Args:
        pattern_type: Type of pattern ('solution', 'workaround', 'optimization')
        project_id: Project where pattern was discovered (e.g., 'session-buddy')
        context: Problem context (what was the issue, symptoms, constraints)
        solution: Solution applied (code changes, configuration, approach)
        outcome_score: Success metric from 0.0 (complete failure) to 1.0 (perfect success)
        tags: Optional tags for categorization (e.g., ['performance', 'database'])

    Returns:
        Dictionary with pattern ID and metadata

    Example:
        >>> capture_successful_pattern(
        ...     pattern_type="solution",
        ...     project_id="session-buddy",
        ...     context={"problem": "Slow database queries", "table": "reflections"},
        ...     solution={"approach": "Add LRU cache", "ttl": 300},
        ...     outcome_score=0.9,
        ...     tags=["performance", "caching"]
        ... )
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    # Validate outcome score range
    if not 0.0 <= outcome_score <= 1.0:
        return {
            "success": False,
            "error": "outcome_score must be between 0.0 and 1.0",
            "received": outcome_score,
        }

    # Validate pattern type
    valid_types = ["solution", "workaround", "optimization"]
    if pattern_type not in valid_types:
        return {
            "success": False,
            "error": f"pattern_type must be one of {valid_types}",
            "received": pattern_type,
        }

    try:
        pattern_id = await engine.capture_successful_pattern(
            pattern_type=pattern_type,
            project_id=project_id,
            context=context,
            solution=solution,
            outcome_score=outcome_score,
            tags=tags,
        )

        return {
            "success": True,
            "pattern_id": pattern_id,
            "message": (
                f"Pattern '{pattern_id}' captured successfully. "
                f"This solution can now be discovered by other projects "
                f"facing similar issues."
            ),
            "pattern_type": pattern_type,
            "project_id": project_id,
            "outcome_score": outcome_score,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to capture pattern: {e}",
        }


@mcp.tool()
async def search_similar_patterns(
    current_context: dict[str, t.Any],
    pattern_type: str | None = None,
    threshold: float = 0.75,
    limit: int = 10,
) -> dict[str, t.Any]:
    """Search for patterns similar to the current context.

    This tool finds successful patterns from past projects that match the
    current problem context, enabling cross-project knowledge reuse.

    Use this when encountering a problem to see if similar issues have been
    successfully resolved in other projects.

    Args:
        current_context: Current problem context (symptoms, constraints, environment)
        pattern_type: Optional filter by pattern type ('solution', 'workaround', 'optimization')
        threshold: Minimum similarity score from 0.0 to 1.0 (default 0.75)
        limit: Maximum number of patterns to return (default 10)

    Returns:
        Dictionary with list of similar patterns sorted by relevance

    Example:
        >>> search_similar_patterns(
        ...     current_context={"problem": "Slow queries", "database": "postgres"},
        ...     threshold=0.7,
        ...     limit=5
        ... )
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    # Validate threshold range
    if not 0.0 <= threshold <= 1.0:
        return {
            "success": False,
            "error": "threshold must be between 0.0 and 1.0",
            "received": threshold,
        }

    # Validate limit
    if limit < 1 or limit > 50:
        return {
            "success": False,
            "error": "limit must be between 1 and 50",
            "received": limit,
        }

    try:
        patterns = await engine.search_similar_patterns(
            current_context=current_context,
            pattern_type=pattern_type,
            threshold=threshold,
            limit=limit,
        )

        if not patterns:
            return {
                "success": True,
                "found_patterns": False,
                "patterns": [],
                "message": (
                    f"No similar patterns found with similarity ≥ {threshold:.0%}. "
                    f"Try lowering the threshold or capture more patterns."
                ),
            }

        return {
            "success": True,
            "found_patterns": True,
            "count": len(patterns),
            "patterns": patterns,
            "message": (
                f"Found {len(patterns)} pattern(s) with similarity ≥ {threshold:.0%}. "
                f"Review the suggested solutions and consider applying relevant patterns."
            ),
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to search patterns: {e}",
        }


@mcp.tool()
async def apply_pattern(
    pattern_id: str,
    applied_to_project: str,
    applied_context: dict[str, t.Any],
) -> dict[str, t.Any]:
    """Record a pattern application for tracking and learning.

    This tool tracks when a pattern is applied to a new project, enabling
    the system to measure cross-project knowledge transfer effectiveness.

    Use this after applying a pattern suggested by search_similar_patterns()
    to track whether the pattern worked in a new context.

    Args:
        pattern_id: ID of pattern being applied (from search_similar_patterns)
        applied_to_project: Project where pattern is being applied (e.g., 'crackerjack')
        applied_context: Context in which pattern is applied (specifics of current situation)

    Returns:
        Dictionary with application ID for later outcome rating

    Example:
        >>> apply_pattern(
        ...     pattern_id="pattern-a1b2c3d4",
        ...     applied_to_project="crackerjack",
        ...     applied_context={"file": "test_runner.py", "issue": "timeout"}
        ... )
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    # Check if pattern exists
    patterns = await engine.search_similar_patterns(
        current_context={},  # Empty search to get all patterns
        threshold=0.0,
        limit=1000,
    )

    pattern_exists = any(p["id"] == pattern_id for p in patterns)

    if not pattern_exists:
        return {
            "success": False,
            "error": f"Pattern '{pattern_id}' not found",
            "hint": "Use search_similar_patterns() to find valid pattern IDs",
        }

    try:
        application_id = await engine.apply_pattern(
            pattern_id=pattern_id,
            applied_to_project=applied_to_project,
            applied_context=applied_context,
        )

        return {
            "success": True,
            "application_id": application_id,
            "message": (
                f"Pattern application recorded. Use rate_pattern_outcome() "
                f"with application_id '{application_id}' to provide feedback on "
                f"whether this pattern worked in the new context."
            ),
            "pattern_id": pattern_id,
            "applied_to_project": applied_to_project,
            "next_step": f"Call rate_pattern_outcome('{application_id}', outcome, feedback) "
            f"after evaluating the pattern's effectiveness",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to apply pattern: {e}",
        }


@mcp.tool()
async def rate_pattern_outcome(
    application_id: str,
    outcome: str,
    feedback: str | None = None,
) -> dict[str, t.Any]:
    """Rate the outcome of a pattern application.

    This tool provides feedback on whether a pattern worked when applied
    to a new project, improving future pattern recommendations.

    Use this after evaluating whether a pattern application was successful.

    Args:
        application_id: ID of pattern application (from apply_pattern)
        outcome: Outcome ('success', 'partial', 'failure')
        feedback: Optional feedback explaining what worked or didn't work

    Returns:
        Dictionary with updated pattern statistics

    Example:
        >>> rate_pattern_outcome(
        ...     application_id="app-x9y8z7w6",
        ...     outcome="success",
        ...     feedback="Pattern worked perfectly, reduced query time by 80%"
        ... )
    """
    engine = get_intelligence_engine()
    await engine.initialize()

    # Validate outcome
    valid_outcomes = ["success", "partial", "failure"]
    if outcome not in valid_outcomes:
        return {
            "success": False,
            "error": f"outcome must be one of {valid_outcomes}",
            "received": outcome,
        }

    try:
        await engine.rate_pattern_outcome(
            application_id=application_id,
            outcome=outcome,
            feedback=feedback,
        )

        # Get updated pattern info
        # Note: We'd need to query the pattern table to get updated stats,
        # but for now just confirm the rating was recorded

        return {
            "success": True,
            "application_id": application_id,
            "outcome": outcome,
            "message": (
                f"Pattern outcome rated as '{outcome}'. "
                f"This feedback improves future pattern recommendations "
                f"and helps other projects avoid unsuccessful patterns."
            ),
            "feedback_recorded": feedback is not None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to rate outcome: {e}",
        }
