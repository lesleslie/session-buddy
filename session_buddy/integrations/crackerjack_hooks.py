"""Crackerjack integration for session-buddy.

Bridges between session-buddy skills tracking and crackerjack workflow phases.
Maps crackerjack quality tool invocations to Oneiric workflow phases for
comprehensive skill tracking across development workflows.

Example:
    >>> from session_buddy.core.skills_tracker import SkillsTracker
    >>> from session_buddy.integrations import CrackerjackIntegration
    >>> from pathlib import Path
    >>> tracker = SkillsTracker(session_id="crackerjack_123")
    >>> integration = CrackerjackIntegration(tracker, Path("/path/to/project"))
    >>> integration.track_crackerjack_phase(
    ...     "fast_hooks", "ruff-check", True, 2.5
    ... )
    >>> report = integration.get_crackerjack_workflow_report()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from session_buddy.core.skills_tracker import SkillsTracker


@dataclass
class CrackerjackPhaseMetrics:
    """Metrics for a single crackerjack phase.

    Attributes:
        phase_name: Crackerjack phase (fast_hooks, tests, comprehensive_hooks, ai_fix)
        total_invocations: Total number of tool invocations in this phase
        completed_invocations: Number of successful invocations
        total_duration_seconds: Total time spent in this phase
        tools_used: Set of tools invoked in this phase
        common_failures: Dictionary mapping error types to counts
    """

    phase_name: str
    total_invocations: int = 0
    completed_invocations: int = 0
    total_duration_seconds: float = 0.0
    tools_used: set[str] = field(default_factory=set)
    common_failures: dict[str, int] = field(default_factory=dict)

    def completion_rate(self) -> float:
        """Calculate completion rate as percentage."""
        if self.total_invocations == 0:
            return 0.0
        return (self.completed_invocations / self.total_invocations) * 100

    def avg_duration_seconds(self) -> float:
        """Calculate average duration in seconds."""
        if self.completed_invocations == 0:
            return 0.0
        return self.total_duration_seconds / self.completed_invocations


class CrackerjackIntegration:
    """Integration layer for crackerjack workflow phases.

    Maps crackerjack phases to Oneiric workflow phases and provides
    comprehensive tracking of skill usage during development workflows.

    Phase Mapping:
        - fast_hooks → setup: Initial formatting and basic checks
        - tests → execution: Running test suites
        - comprehensive_hooks → verification: Type checking, security, complexity
        - ai_fix → execution: AI-powered code fixes

    Attributes:
        skills_tracker: SkillsTracker instance for recording invocations
        crackerjack_project_path: Path to crackerjack project
        phase_metrics: Dictionary tracking metrics per phase
    """

    # Mapping from crackerjack phases to Oneiric workflow phases
    PHASE_MAPPING: dict[str, str] = {
        "fast_hooks": "setup",
        "tests": "execution",
        "comprehensive_hooks": "verification",
        "ai_fix": "execution",
    }

    # Common crackerjack tools by phase
    PHASE_TOOLS: dict[str, list[str]] = {
        "fast_hooks": [
            "ruff-format",
            "ruff-check",
            "codespell",
            "whitespace-check",
        ],
        "tests": [
            "pytest-run",
            "pytest-coverage",
            "test-discovery",
        ],
        "comprehensive_hooks": [
            "mypy-check",
            "pyright-check",
            "zuban-check",
            "bandit-security",
            "complexity-check",
            "skylos-deadcode",
        ],
        "ai_fix": [
            "refactoring-agent",
            "security-agent",
            "performance-agent",
            "test-creation-agent",
        ],
    }

    def __init__(
        self,
        skills_tracker: SkillsTracker,
        crackerjack_project_path: Path,
    ) -> None:
        """Initialize crackerjack integration.

        Args:
            skills_tracker: SkillsTracker instance for recording skill usage
            crackerjack_project_path: Path to crackerjack project directory
        """
        self.skills_tracker = skills_tracker
        self.crackerjack_project_path = crackerjack_project_path

        # Track metrics per phase
        self.phase_metrics: dict[str, CrackerjackPhaseMetrics] = {}

        # Initialize metrics for all known phases
        for phase in self.PHASE_MAPPING:
            self.phase_metrics[phase] = CrackerjackPhaseMetrics(phase_name=phase)

    def track_crackerjack_phase(
        self,
        phase_name: str,
        skill_name: str,
        completed: bool,
        duration_seconds: float,
        error_message: str | None = None,
    ) -> None:
        """Track a skill invocation during a crackerjack phase.

        Maps the crackerjack phase to an Oneiric workflow phase and records
        the skill invocation with appropriate context.

        Args:
            phase_name: Crackerjack phase (fast_hooks, tests, comprehensive_hooks, ai_fix)
            skill_name: Name of the tool/skill being invoked
            completed: Whether the invocation completed successfully
            duration_seconds: Time taken for the invocation
            error_message: Optional error message if invocation failed

        Raises:
            ValueError: If phase_name is not a recognized crackerjack phase

        Example:
            >>> integration.track_crackerjack_phase(
            ...     "fast_hooks", "ruff-check", True, 2.5
            ... )
        """
        # Validate phase
        if phase_name not in self.PHASE_MAPPING:
            valid_phases = ", ".join(self.PHASE_MAPPING.keys())
            raise ValueError(
                f"Unknown crackerjack phase: {phase_name}. Valid phases: {valid_phases}"
            )

        # Map to Oneiric workflow phase
        workflow_phase = self.PHASE_MAPPING[phase_name]

        # Track via skills tracker
        complete_fn = self.skills_tracker.track_invocation(
            skill_name=skill_name,
            workflow_path=workflow_phase,
            user_query=f"crackerjack phase: {phase_name}",
        )

        # Mark completion
        complete_fn(
            completed=completed,
            error_type=error_message,
        )

        # Update phase metrics
        metrics = self.phase_metrics[phase_name]
        metrics.total_invocations += 1
        metrics.tools_used.add(skill_name)

        if completed:
            metrics.completed_invocations += 1
            metrics.total_duration_seconds += duration_seconds
        else:
            if error_message:
                metrics.common_failures[error_message] = (
                    metrics.common_failures.get(error_message, 0) + 1
                )

    def get_workflow_phase(self, crackerjack_phase: str) -> str:
        """Get Oneiric workflow phase for a crackerjack phase.

        Args:
            crackerjack_phase: Crackerjack phase name

        Returns:
            Corresponding Oneiric workflow phase

        Raises:
            ValueError: If crackerjack_phase is not recognized
        """
        if crackerjack_phase not in self.PHASE_MAPPING:
            valid_phases = ", ".join(self.PHASE_MAPPING.keys())
            raise ValueError(
                f"Unknown crackerjack phase: {crackerjack_phase}. "
                f"Valid phases: {valid_phases}"
            )

        return self.PHASE_MAPPING[crackerjack_phase]

    def get_recommended_skills(
        self,
        phase_name: str,
        limit: int = 5,
    ) -> list[dict]:
        """Get recommended skills for a specific crackerjack phase.

        Uses workflow-aware recommendations to find skills that work well
        in the corresponding Oneiric phase.

        Args:
            phase_name: Crackerjack phase name
            limit: Maximum number of recommendations

        Returns:
            List of recommended skills with metadata

        Example:
            >>> recommendations = integration.get_recommended_skills("tests")
            >>> for rec in recommendations:
            ...     print(f"{rec['skill_name']}: {rec['similarity_score']:.3f}")
        """
        workflow_phase = self.get_workflow_phase(phase_name)

        return self.skills_tracker.recommend_skills(
            user_query=f"crackerjack {phase_name}",
            limit=limit,
            workflow_phase=workflow_phase,
            phase_weight=0.5,  # Equal weight semantic and phase
        )

    def get_crackerjack_workflow_report(self) -> str:
        """Generate comprehensive crackerjack workflow report.

        Creates a detailed report showing:
        - Phase-by-phase metrics
        - Tool usage patterns
        - Failure analysis
        - Workflow phase transitions

        Returns:
            Formatted multi-section report

        Example:
            >>> report = integration.get_crackerjack_workflow_report()
            >>> print(report)
        """
        lines = [
            "=" * 70,
            "Crackerjack Workflow Integration Report",
            "=" * 70,
            "",
            f"Project: {self.crackerjack_project_path}",
            f"Session: {self.skills_tracker.session_id}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # Section 1: Phase-by-Phase Metrics
        lines.extend(
            [
                "-" * 70,
                "1. Phase Metrics",
                "-" * 70,
                "",
            ]
        )

        for phase_name in ["fast_hooks", "tests", "comprehensive_hooks", "ai_fix"]:
            metrics = self.phase_metrics[phase_name]
            workflow_phase = self.PHASE_MAPPING[phase_name]

            lines.extend(
                [
                    f"\nPhase: {phase_name.upper()} (→ {workflow_phase})",
                    "  " + "-" * 65,
                    f"  Total Invocations: {metrics.total_invocations}",
                    f"  Completed: {metrics.completed_invocations}",
                    f"  Completion Rate: {metrics.completion_rate():.1f}%",
                    f"  Total Duration: {metrics.total_duration_seconds:.1f}s",
                    f"  Avg Duration: {metrics.avg_duration_seconds():.1f}s",
                    "",
                ]
            )

            if metrics.tools_used:
                lines.append("  Tools Used:")
                for tool in sorted(metrics.tools_used):
                    lines.append(f"    - {tool}")

            if metrics.common_failures:
                lines.append("")
                lines.append("  Common Failures:")
                for error, count in sorted(
                    metrics.common_failures.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:5]:
                    lines.append(f"    - {error}: {count}x")

        # Section 2: Workflow Phase Mapping
        lines.extend(
            [
                "",
                "",
                "-" * 70,
                "2. Crackerjack → Oneiric Phase Mapping",
                "-" * 70,
                "",
            ]
        )

        for crackerjack_phase, oneiric_phase in self.PHASE_MAPPING.items():
            lines.append(f"  {crackerjack_phase:<25} → {oneiric_phase}")

        # Section 3: Recommendations
        lines.extend(
            [
                "",
                "",
                "-" * 70,
                "3. Phase-Specific Recommendations",
                "-" * 70,
                "",
            ]
        )

        for phase_name in ["fast_hooks", "tests", "comprehensive_hooks", "ai_fix"]:
            recommendations = self.get_recommended_skills(phase_name, limit=3)

            lines.append(f"\n{phase_name.upper()}:")
            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    lines.append(
                        f"  {i}. {rec['skill_name']} "
                        f"({rec['similarity_score']:.2f} confidence)"
                    )
            else:
                lines.append("  No recommendations available yet.")

        lines.extend(["", "", "=" * 70])

        return "\n".join(lines)

    def get_phase_summary(self, phase_name: str) -> dict:
        """Get summary dictionary for a specific phase.

        Args:
            phase_name: Crackerjack phase name

        Returns:
            Dictionary with phase metrics

        Example:
            >>> summary = integration.get_phase_summary("fast_hooks")
            >>> print(f"Completion: {summary['completion_rate']:.1f}%")
        """
        if phase_name not in self.phase_metrics:
            raise ValueError(f"Unknown phase: {phase_name}")

        metrics = self.phase_metrics[phase_name]

        return {
            "phase_name": metrics.phase_name,
            "workflow_phase": self.PHASE_MAPPING[phase_name],
            "total_invocations": metrics.total_invocations,
            "completed_invocations": metrics.completed_invocations,
            "completion_rate": metrics.completion_rate(),
            "total_duration_seconds": metrics.total_duration_seconds,
            "avg_duration_seconds": metrics.avg_duration_seconds(),
            "tools_used": list(metrics.tools_used),
            "common_failures": metrics.common_failures.copy(),
        }
