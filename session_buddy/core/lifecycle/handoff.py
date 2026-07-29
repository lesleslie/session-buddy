"""Handoff documentation generation for session management.

This module provides utilities for generating comprehensive handoff documentation
when sessions end, including quality assessment, recommendations, and context.
"""

from __future__ import annotations

import logging
import typing as t
from datetime import UTC, datetime

if t.TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def build_handoff_header(summary: dict[str, t.Any]) -> list[str]:
    """Build handoff documentation header section."""
    return [
        f"# Session Handoff Report - {summary['project']}",
        "",
        f"**Session ended:** {summary['session_end_time']}",
        f"**Final quality score:** {summary['final_quality_score']}/100",
        f"**Working directory:** {summary['working_directory']}",
        "",
    ]


def build_quality_section(quality_data: dict[str, t.Any]) -> list[str]:
    """Build quality assessment section of handoff documentation."""
    lines = ["## Quality Assessment", ""]
    breakdown = quality_data.get("breakdown", {})
    lines.extend(
        [
            f"- **Code quality:** {breakdown.get('code_quality', 0):.1f}/40",
            f"- **Project health:** {breakdown.get('project_health', 0):.1f}/30",
            f"- **Dev velocity:** {breakdown.get('dev_velocity', 0):.1f}/20",
            f"- **Security:** {breakdown.get('security', 0):.1f}/10",
            "",
        ],
    )
    return lines


def build_recommendations_section(recommendations: list[str]) -> list[str]:
    """Build recommendations section of handoff documentation."""
    if not recommendations:
        return []

    lines = ["## Recommendations for Next Session", ""]
    for rec in recommendations[:5]:
        lines.append(f"- {rec}")
    lines.append("")
    return lines


def build_static_sections() -> list[str]:
    """Build static sections of handoff documentation."""
    return [
        "## Context for Next Session",
        "",
        "This session has completed. Use the quality score and recommendations above",
        "to guide next steps. Review the working directory state and apply any",
        "suggested improvements.",
        "",
        "## Session Continuity",
        "",
        "The session management system maintains context between sessions through:",
        "- Reflection database for key insights",
        "- Quality score history for trend analysis",
        "- Project structure analysis for optimization",
        "",
    ]


def save_handoff_documentation(content: str, working_dir: Path) -> Path | None:
    """Save handoff documentation to file."""
    try:
        handoff_dir = working_dir / ".claude" / "handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        handoff_path = handoff_dir / f"session_handoff_{timestamp}.md"

        handoff_path.write_text(content)
        return handoff_path

    except Exception:
        logger.exception("Handoff document generation failed")
        return None


async def generate_handoff_documentation(
    summary: dict[str, t.Any],
    quality_data: dict[str, t.Any],
) -> str:
    """Generate comprehensive handoff documentation."""
    lines: list[str] = []

    # Header section
    lines.extend(build_handoff_header(summary))

    # Quality section
    lines.extend(build_quality_section(quality_data))

    # Recommendations section
    lines.extend(build_recommendations_section(summary.get("recommendations", [])))

    # Static sections
    lines.extend(build_static_sections())

    return "\n".join(lines)
