#!/usr/bin/env python3
"""Skills tracking system for session-buddy.

Tracks skill usage during sessions with enhanced context tracking.
This is the home for skills metrics - skills are session-scoped activities.

Enhanced over crackerjack implementation:
- Adds session_id tracking throughout
- Tracks user queries for semantic search
- Records alternative skills considered
- Stores selection rank for effectiveness learning
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class SkillInvocation:
    """Single skill usage event with session context.

    Enhanced from crackerjack implementation with:
    - session_id for correlation with workflows
    - user_query for semantic search analysis
    - alternatives for learning from rejections
    - selection_rank for recommendation effectiveness
    """

    skill_name: str
    invoked_at: str  # ISO format timestamp
    session_id: str  # NEW: Session this skill belongs to
    workflow_path: str | None = None  # e.g., "quick", "comprehensive"
    completed: bool = False
    duration_seconds: float | None = None

    # NEW: Semantic search context
    user_query: str | None = None  # User's problem description
    alternatives_considered: list[str] = field(
        default_factory=list
    )  # Other skills shown
    selection_rank: int | None = None  # Position in recommendation list (1=first)

    follow_up_actions: list[str] = field(default_factory=list)
    error_type: str | None = None  # If skill failed

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class SkillMetrics:
    """Aggregated metrics for a single skill.

    Same as crackerjack implementation with computed properties.
    """

    skill_name: str
    total_invocations: int = 0
    completed_invocations: int = 0
    abandoned_invocations: int = 0
    total_duration_seconds: float = 0.0
    workflow_paths: dict[str, int] = field(default_factory=dict)
    common_errors: dict[str, int] = field(default_factory=dict)
    follow_up_actions: dict[str, int] = field(default_factory=dict)

    # NEW: Recommendation effectiveness
    avg_selection_rank: float | None = None  # Lower = more recommended
    recommendation_success_rate: float | None = None  # When rank 1, success rate

    first_invoked: str | None = None
    last_invoked: str | None = None

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

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            **asdict(self),
            "completion_rate": self.completion_rate(),
            "avg_duration_seconds": self.avg_duration_seconds(),
        }


class SkillsTracker:
    """Track skill usage metrics during sessions.

    Enhanced from crackerjack implementation:
    - Requires session_id for all tracking
    - Tracks semantic search context
    - Generates session-specific reports
    - Integrates with session lifecycle
    """

    def __init__(
        self,
        session_id: str,
        metrics_file: Path | None = None,
    ) -> None:
        """Initialize skills tracker for a session.

        Args:
            session_id: Session this tracker belongs to (required)
            metrics_file: Path to metrics JSON file. Defaults to
                `.session-buddy/skill_metrics.json` in current directory.
        """
        self.session_id = session_id

        if metrics_file is None:
            metrics_file = Path.cwd() / ".session-buddy" / "skill_metrics.json"

        self.metrics_file = metrics_file
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

        self._invocations: list[SkillInvocation] = []
        self._skill_metrics: dict[str, SkillMetrics] = {}
        self._load()

    def track_invocation(
        self,
        skill_name: str,
        workflow_path: str | None = None,
        user_query: str | None = None,
        alternatives_considered: list[str] | None = None,
        selection_rank: int | None = None,
    ) -> Callable[[], None]:
        """Track a skill invocation with enhanced context.

        Args:
            skill_name: Name of the skill being invoked
            workflow_path: Optional workflow path chosen
            user_query: User's problem description (for semantic search)
            alternatives_considered: Other skills shown to user
            selection_rank: Position in recommendation list (1=first choice)

        Returns:
            Function that should be called when skill completes

        Example:
            >>> tracker = SkillsTracker(session_id="abc123")
            >>> complete = tracker.track_invocation(
            ...     "crackerjack-run",
            ...     workflow_path="comprehensive",
            ...     user_query="fix type errors",
            ...     alternatives_considered=["session-checkpoint"],
            ...     selection_rank=1
            ... )
            >>> # ... skill logic ...
            >>> complete(completed=True, follow_up_actions=["git commit"])
        """
        invocation = SkillInvocation(
            skill_name=skill_name,
            invoked_at=datetime.now().isoformat(),
            session_id=self.session_id,
            workflow_path=workflow_path,
            user_query=user_query,
            alternatives_considered=alternatives_considered or [],
            selection_rank=selection_rank,
        )
        self._invocations.append(invocation)

        def completer(
            *,
            completed: bool = True,
            follow_up_actions: list[str] | None = None,
            error_type: str | None = None,
        ) -> None:
            """Mark the skill invocation as complete.

            Args:
                completed: Whether the skill completed successfully
                follow_up_actions: Actions taken after skill completion
                error_type: Type of error if skill failed
            """
            invocation.completed = completed
            invocation.follow_up_actions = follow_up_actions or []
            invocation.error_type = error_type

            # Calculate duration
            invoked_at = datetime.fromisoformat(invocation.invoked_at)
            invocation.duration_seconds = (datetime.now() - invoked_at).total_seconds()

            self._update_aggregates(invocation)
            self._save()

        return completer

    def get_session_skills(self) -> list[SkillInvocation]:
        """Get all skill invocations for this session.

        Returns:
            List of invocations in chronological order
        """
        return [inv for inv in self._invocations if inv.session_id == self.session_id]

    def get_session_summary(self) -> dict[str, object]:
        """Get summary of skills used in this session.

        Returns:
            Dictionary with session skill statistics
        """
        session_invocations = self.get_session_skills()

        if not session_invocations:
            return {
                "session_id": self.session_id,
                "total_skills_used": 0,
                "completed_skills": 0,
                "abandoned_skills": 0,
                "total_duration_seconds": 0.0,
            }

        completed = [inv for inv in session_invocations if inv.completed]
        abandoned = [inv for inv in session_invocations if not inv.completed]

        # Count unique skills
        unique_skills = len(set(inv.skill_name for inv in session_invocations))

        return {
            "session_id": self.session_id,
            "total_skills_used": unique_skills,
            "total_invocations": len(session_invocations),
            "completed_invocations": len(completed),
            "abandoned_invocations": len(abandoned),
            "total_duration_seconds": sum(
                inv.duration_seconds or 0 for inv in session_invocations
            ),
            "skills_by_count": self._count_skills_by_frequency(session_invocations),
        }

    def _count_skills_by_frequency(
        self,
        invocations: list[SkillInvocation],
    ) -> dict[str, int]:
        """Count how many times each skill was used.

        Args:
            invocations: List of skill invocations

        Returns:
            Dictionary mapping skill_name to count
        """
        counts: dict[str, int] = {}
        for inv in invocations:
            counts[inv.skill_name] = counts.get(inv.skill_name, 0) + 1
        return counts

    # Reuse methods from crackerjack implementation
    def get_skill_metrics(self, skill_name: str) -> SkillMetrics | None:
        """Get metrics for a specific skill.

        Args:
            skill_name: Name of the skill

        Returns:
            SkillMetrics if skill has been invoked, None otherwise
        """
        return self._skill_metrics.get(skill_name)

    def get_all_metrics(self) -> dict[str, SkillMetrics]:
        """Get metrics for all skills (across all sessions).

        Returns:
            Dictionary mapping skill names to their metrics
        """
        return self._skill_metrics.copy()

    def get_summary(self) -> dict[str, object]:
        """Get overall metrics summary (all sessions).

        Returns:
            Summary statistics across all sessions
        """
        if not self._skill_metrics:
            return {
                "total_skills": 0,
                "total_invocations": 0,
                "overall_completion_rate": 0.0,
                "most_used_skill": None,
                "avg_duration_seconds": 0.0,
            }

        total_invocations = sum(
            m.total_invocations for m in self._skill_metrics.values()
        )
        total_completed = sum(
            m.completed_invocations for m in self._skill_metrics.values()
        )
        most_used = max(
            self._skill_metrics.items(), key=lambda x: x[1].total_invocations
        )

        total_duration = sum(
            m.total_duration_seconds for m in self._skill_metrics.values()
        )
        total_completed_invocations = sum(
            m.completed_invocations for m in self._skill_metrics.values()
        )
        avg_duration = (
            total_duration / total_completed_invocations
            if total_completed_invocations > 0
            else 0.0
        )

        return {
            "total_skills": len(self._skill_metrics),
            "total_invocations": total_invocations,
            "overall_completion_rate": (
                (total_completed / total_invocations * 100)
                if total_invocations > 0
                else 0.0
            ),
            "most_used_skill": most_used[0],
            "most_used_count": most_used[1].total_invocations,
            "avg_duration_seconds": avg_duration,
            "skills_by_usage": sorted(
                [
                    (name, metrics.total_invocations)
                    for name, metrics in self._skill_metrics.items()
                ],
                key=lambda x: x[1],
                reverse=True,
            ),
        }

    def recommend_skills(
        self,
        user_query: str,
        limit: int = 5,
        session_id: str | None = None,
        min_similarity: float = 0.0,
        db_path: Path | None = None,
        workflow_phase: str | None = None,
        phase_weight: float = 0.3,
    ) -> list[dict[str, object]]:
        """Recommend skills based on semantic similarity to user query.

        Uses vector embeddings to find semantically similar past invocations
        and recommends the skills that were used. Can be workflow-aware to
        prefer skills that work well in the current phase.

        Args:
            user_query: User's problem description or query
            limit: Maximum number of recommendations to return
            session_id: Optional session filter (searches all sessions if None)
            min_similarity: Minimum cosine similarity threshold (0.0 to 1.0)
            db_path: Optional path to skills database. Defaults to
                `.session-buddy/skills.db` in current directory.
            workflow_phase: Current Oneiric workflow phase (e.g., "setup", "execution")
                When provided, boosts recommendations that work well in this phase
            phase_weight: Weight for phase effectiveness (0.0 to 1.0)
                - 0.0 = pure semantic search
                - 0.5 = equal weight semantic and phase
                - 1.0 = pure phase effectiveness
                Default: 0.3 (slight phase preference)

        Returns:
            List of recommendations with structure:
                [
                    {
                        "skill_name": str,
                        "similarity_score": float,
                        "invocation_id": int,
                        "user_query": str,
                        "completed": bool,
                        "duration_seconds": float | None,
                        "workflow_phase": str | None  # Included if workflow_phase specified
                    },
                    ...
                ]

        Example:
            >>> tracker = SkillsTracker(session_id="my_session")
            >>> recommendations = tracker.recommend_skills(
            ...     "how to fix database timeout error",
            ...     limit=5,
            ...     workflow_phase="execution"
            ... )
            >>> for rec in recommendations:
            ...     print(f"{rec['skill_name']}: {rec['similarity_score']:.3f}")
        """
        # Import here to avoid circular dependency
        from session_buddy.storage.skills_embeddings import (
            get_embedding_service,
        )
        from session_buddy.storage.skills_storage import SkillsStorage

        # Generate embedding for user query
        embedding_service = get_embedding_service()
        embedding_service.initialize()

        query_embedding = embedding_service.generate_embedding(user_query)

        if query_embedding is None:
            # Embeddings unavailable, return empty list
            return []

        # Pack embedding
        from session_buddy.storage.skills_embeddings import pack_embedding

        packed_embedding = pack_embedding(query_embedding)

        # Set default database path if not provided
        if db_path is None:
            db_path = Path.cwd() / ".session-buddy" / "skills.db"

        # Create storage and search
        storage = SkillsStorage(db_path=db_path)

        # Use workflow-aware search if phase specified, otherwise regular search
        if workflow_phase:
            results = storage.search_by_query_workflow_aware(
                packed_embedding,
                workflow_phase=workflow_phase,
                limit=limit,
                session_id=session_id,
                min_similarity=min_similarity,
                phase_weight=phase_weight,
            )
        else:
            results = storage.search_by_query(
                packed_embedding,
                limit=limit,
                session_id=session_id,
                min_similarity=min_similarity,
            )

        # Convert to recommendation format
        recommendations = []
        for invocation, score in results:
            recommendation = {
                "skill_name": invocation.skill_name,
                "similarity_score": score,
                "invocation_id": invocation.id,
                "user_query": invocation.user_query,
                "completed": invocation.completed,
                "duration_seconds": invocation.duration_seconds,
                "session_id": invocation.session_id,
                "invoked_at": invocation.invoked_at,
            }
            # Include workflow phase if using workflow-aware search
            if workflow_phase and invocation.workflow_phase:
                recommendation["workflow_phase"] = invocation.workflow_phase

            recommendations.append(recommendation)

        return recommendations

    def generate_report(self) -> str:
        """Generate human-readable metrics report.

        Returns:
            Formatted report string
        """
        summary = self.get_summary()

        lines = [
            "=" * 60,
            "Skills Metrics Report",
            "=" * 60,
            "",
            f"Total Skills Tracked: {summary['total_skills']}",
            f"Total Invocations: {summary['total_invocations']}",
            f"Overall Completion Rate: {summary['overall_completion_rate']:.1f}%",
            f"Average Duration: {summary['avg_duration_seconds']:.1f}s",
            "",
            "Most Used Skills:",
        ]

        for skill_name, count in summary.get("skills_by_usage", [])[:5]:
            metrics = self._skill_metrics[skill_name]
            lines.append(
                f"  {skill_name}: {count} invocations "
                f"({metrics.completion_rate():.1f}% complete, "
                f"{metrics.avg_duration_seconds():.1f}s avg)"
            )

        lines.extend(
            [
                "",
                "Workflow Path Preferences:",
            ]
        )

        # Show workflow paths for most used skills
        for skill_name, _ in summary.get("skills_by_usage", [])[:3]:
            metrics = self._skill_metrics[skill_name]
            if metrics.workflow_paths:
                lines.append(f"  {skill_name}:")
                for path, count in sorted(
                    metrics.workflow_paths.items(),
                    key=lambda x: x[1],
                    reverse=True,
                ):
                    lines.append(f"    {path}: {count} uses")

        lines.extend(
            [
                "",
                "Common Follow-up Actions:",
            ]
        )

        # Aggregate follow-up actions across all skills
        all_actions: dict[str, int] = {}
        for metrics in self._skill_metrics.values():
            for action, count in metrics.follow_up_actions.items():
                all_actions[action] = all_actions.get(action, 0) + count

        for action, count in sorted(
            all_actions.items(), key=lambda x: x[1], reverse=True
        )[:5]:
            lines.append(f"  {action}: {count}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def export_metrics(self, output_file: Path) -> None:
        """Export metrics to JSON file.

        Args:
            output_file: Path to output JSON file
        """
        data = {
            "summary": self.get_summary(),
            "skills": {
                name: metrics.to_dict() for name, metrics in self._skill_metrics.items()
            },
            "invocations": [inv.to_dict() for inv in self._invocations],
            "exported_at": datetime.now().isoformat(),
        }

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(data, indent=2))

    def generate_workflow_report(
        self, db_path: Path | None = None, session_id: str | None = None
    ) -> str:
        """Generate workflow correlation report with visualizations.

        Creates a comprehensive report showing:
        - Skill effectiveness by workflow phase
        - Workflow phase transitions
        - Bottleneck identification
        - Phase-specific recommendations

        Args:
            db_path: Path to skills database (defaults to .session-buddy/skills.db)
            session_id: Optional session filter (None for all sessions)

        Returns:
            Formatted multi-section report with ASCII visualizations

        Example:
            >>> tracker = SkillsTracker(session_id="abc123")
            >>> report = tracker.generate_workflow_report()
            >>> print(report)
        """
        from session_buddy.storage.skills_storage import SkillsStorage

        if db_path is None:
            db_path = Path.cwd() / ".session-buddy" / "skills.db"

        storage = SkillsStorage(db_path=db_path)

        lines = [
            "=" * 70,
            "Workflow Correlation Report",
            "=" * 70,
            "",
            f"Session: {session_id if session_id else 'All Sessions'}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # Section 1: Skill Effectiveness by Phase
        lines.extend(
            [
                "-" * 70,
                "1. Skill Effectiveness by Workflow Phase",
                "-" * 70,
                "",
            ]
        )

        effectiveness = storage.get_workflow_skill_effectiveness(
            workflow_phase=None, min_invocations=1
        )

        if effectiveness:
            # Group by phase
            phases: dict[str, list[dict]] = {}
            for skill in effectiveness:
                phase = skill["workflow_phase"]
                if phase not in phases:
                    phases[phase] = []
                phases[phase].append(skill)

            for phase, skills in sorted(phases.items()):
                lines.append(f"\n📍 Phase: {phase.upper()}")
                lines.append("   " + "-" * 65)
                lines.append(
                    f"   {'Skill':<30} {'Rate':>8} {'Avg Time':>10} {'Total':>8}"
                )
                lines.append("   " + "-" * 65)

                for skill in sorted(
                    skills, key=lambda s: s["completion_rate"], reverse=True
                )[:5]:
                    lines.append(
                        f"   {skill['skill_name']:<30} "
                        f"{skill['completion_rate']:>7.1f}% "
                        f"{skill['avg_duration_seconds']:>9.1f}s "
                        f"{skill['total_invocations']:>8}"
                    )
        else:
            lines.append("No workflow data available yet.")

        # Section 2: Bottleneck Identification
        lines.extend(["", "", "-" * 70, "2. Workflow Bottlenecks", "-" * 70, ""])

        bottlenecks = storage.identify_workflow_bottlenecks(min_abandonment_rate=0.2)

        if bottlenecks:
            lines.append("")
            lines.append("Phases with high abandonment rates (potential bottlenecks):")
            lines.append("")

            for bottleneck in bottlenecks[:5]:
                phase = bottleneck["workflow_phase"]
                rate = bottleneck["abandonment_rate"]
                score = bottleneck["bottleneck_score"]

                # Visual indicator
                if rate > 0.5:
                    indicator = "🔴 CRITICAL"
                elif rate > 0.3:
                    indicator = "🟡 WARNING"
                else:
                    indicator = "🟢 MONITOR"

                lines.append(
                    f"  {phase}: {rate:.1%} abandonment "
                    f"(bottleneck score: {score:.2f}) {indicator}"
                )
        else:
            lines.append("✅ No significant bottlenecks detected!")

        # Section 3: Phase Transition Diagram
        lines.extend(["", "", "-" * 70, "3. Workflow Phase Transitions", "-" * 70, ""])

        transitions = storage.get_workflow_phase_transitions(session_id=session_id)

        if transitions:
            lines.append("")
            lines.append("Most common phase transitions:")
            lines.append("")

            # Create ASCII flow diagram
            for i, transition in enumerate(transitions[:8]):
                from_phase = transition["from_phase"]
                to_phase = transition["to_phase"]
                count = transition["invocation_count"]
                skill = transition["most_common_skill"]

                lines.append(f"  {from_phase} ──[{count}x, {skill}]──> {to_phase}")
        else:
            lines.append("No phase transition data available yet.")

        # Section 4: Phase-Specific Recommendations
        lines.extend(["", "", "-" * 70, "4. Recommendations by Phase", "-" * 70, ""])

        if effectiveness:
            lines.append("")
            lines.append("Top-performing skills for each phase:")
            lines.append("")

            for phase in sorted(phases.keys()):
                phase_skills = [
                    s
                    for s in effectiveness
                    if s["workflow_phase"] == phase and s["completion_rate"] > 70
                ]

                if phase_skills:
                    best_skill = max(phase_skills, key=lambda s: s["completion_rate"])
                    lines.append(
                        f"  🎯 {phase.upper()}: Use {best_skill['skill_name']} "
                        f"({best_skill['completion_rate']:.1f}% success rate)"
                    )
        else:
            lines.append("Insufficient data for recommendations.")

        lines.extend(["", "", "=" * 70])

        return "\n".join(lines)

    def generate_phase_heatmap(
        self, db_path: Path | None = None, session_id: str | None = None
    ) -> str:
        """Generate ASCII heatmap showing skill usage across workflow phases.

        Creates a visual matrix showing which skills are most commonly used
        in each workflow phase.

        Args:
            db_path: Path to skills database (defaults to .session-buddy/skills.db)
            session_id: Optional session filter (None for all sessions)

        Returns:
            ASCII heatmap string

        Example:
            >>> tracker = SkillsTracker(session_id="abc123")
            >>> heatmap = tracker.generate_phase_heatmap()
            >>> print(heatmap)
        """
        from session_buddy.storage.skills_storage import SkillsStorage

        if db_path is None:
            db_path = Path.cwd() / ".session-buddy" / "skills.db"

        storage = SkillsStorage(db_path=db_path)

        # Get phase-specific effectiveness data
        effectiveness = storage.get_workflow_skill_effectiveness(
            workflow_phase=None, min_invocations=1
        )

        if not effectiveness:
            return "No workflow data available for heatmap."

        # Build matrix: skills x phases
        phases = sorted(set(s["workflow_phase"] for s in effectiveness))
        skill_names = sorted(set(s["skill_name"] for s in effectiveness))[:15]  # Top 15

        # Create usage matrix
        matrix: dict[str, dict[str, float]] = {}
        for skill in skill_names:
            matrix[skill] = {}
            for phase in phases:
                matrix[skill][phase] = 0.0

        for data in effectiveness:
            skill = data["skill_name"]
            phase = data["workflow_phase"]
            if skill in matrix and phase in matrix[skill]:
                matrix[skill][phase] = data["completion_rate"]

        # Generate ASCII heatmap
        lines = [
            "=" * 70,
            "Skill Usage Heatmap by Workflow Phase",
            "=" * 70,
            "",
            "Legend: █ 90-100%, ▓ 70-89%, ▒ 50-69%, ░ 30-49%, · 0-29%",
            "",
        ]

        # Header row (phases)
        header = "Skill" + " " * 20 + "  "
        for phase in phases[:8]:  # Limit to 8 phases for width
            header += f"{phase[:8]:>10}"
        lines.append(header)
        lines.append(" " * 21 + "  " + "─" * 10 * len(phases[:8]))

        # Data rows (skills)
        for skill in skill_names[:15]:
            row = skill[:20] + " " * (20 - len(skill)) + "  "
            for phase in phases[:8]:
                rate = matrix[skill][phase]
                if rate >= 90:
                    bar = "█"
                elif rate >= 70:
                    bar = "▓"
                elif rate >= 50:
                    bar = "▒"
                elif rate >= 30:
                    bar = "░"
                else:
                    bar = "·"

                row += f"{bar:>9}{rate:4.0f}%"
            lines.append(row)

        lines.extend(["", "", "=" * 70])

        return "\n".join(lines)

    def _update_aggregates(self, invocation: SkillInvocation) -> None:
        """Update aggregated metrics from invocation.

        Args:
            invocation: Completed invocation to aggregate
        """
        skill_name = invocation.skill_name

        if skill_name not in self._skill_metrics:
            self._skill_metrics[skill_name] = SkillMetrics(
                skill_name=skill_name,
                first_invoked=invocation.invoked_at,
            )

        metrics = self._skill_metrics[skill_name]
        metrics.total_invocations += 1
        metrics.last_invoked = invocation.invoked_at

        if invocation.completed:
            metrics.completed_invocations += 1
            if invocation.duration_seconds:
                metrics.total_duration_seconds += invocation.duration_seconds
        else:
            metrics.abandoned_invocations += 1

        if invocation.workflow_path:
            metrics.workflow_paths[invocation.workflow_path] = (
                metrics.workflow_paths.get(invocation.workflow_path, 0) + 1
            )

        if invocation.error_type:
            metrics.common_errors[invocation.error_type] = (
                metrics.common_errors.get(invocation.error_type, 0) + 1
            )

        for action in invocation.follow_up_actions:
            metrics.follow_up_actions[action] = (
                metrics.follow_up_actions.get(action, 0) + 1
            )

    def _load(self) -> None:
        """Load existing metrics from file."""
        if not self.metrics_file.exists():
            return

        try:
            data = json.loads(self.metrics_file.read_text())

            # Load invocations
            self._invocations = [
                SkillInvocation(**inv) for inv in data.get("invocations", [])
            ]

            # Load aggregated metrics
            for skill_name, skill_data in data.get("skills", {}).items():
                # Remove computed fields before creating dataclass
                skill_data.pop("completion_rate", None)
                skill_data.pop("avg_duration_seconds", None)

                self._skill_metrics[skill_name] = SkillMetrics(**skill_data)
        except (json.JSONDecodeError, TypeError):
            # Corrupted metrics file, start fresh
            self._invocations = []
            self._skill_metrics = {}

    def _save(self) -> None:
        """Save metrics to file."""
        data = {
            "invocations": [inv.to_dict() for inv in self._invocations],
            "skills": {
                name: metrics.to_dict() for name, metrics in self._skill_metrics.items()
            },
            "last_updated": datetime.now().isoformat(),
        }

        self.metrics_file.write_text(json.dumps(data, indent=2))


# Global tracker is session-specific now (no singleton)
# Each session creates its own tracker instance


def get_session_tracker(
    session_id: str, metrics_file: Path | None = None
) -> SkillsTracker:
    """Get or create a skills tracker for a specific session.

    Args:
        session_id: Session this tracker belongs to
        metrics_file: Optional path to metrics file

    Returns:
        SkillsTracker instance for the session

    Example:
        >>> tracker = get_session_tracker(session_id="abc123")
        >>> complete = tracker.track_invocation("crackerjack-run")
        >>> complete(completed=True)
    """
    return SkillsTracker(session_id=session_id, metrics_file=metrics_file)
