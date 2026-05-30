from __future__ import annotations

import json
import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SkillInvocation:
    skill_name: str
    invoked_at: str
    session_id: str
    workflow_path: str | None = None
    completed: bool = False
    duration_seconds: float | None = None
    user_query: str | None = None
    alternatives_considered: list[str] = field(default_factory=list)
    selection_rank: int | None = None
    follow_up_actions: list[str] = field(default_factory=list)
    error_type: str | None = None


@dataclass
class SkillMetrics:
    skill_name: str
    total_invocations: int = 0
    completed_invocations: int = 0
    abandoned_invocations: int = 0
    total_duration_seconds: float = 0.0
    workflow_paths: dict[str, int] = field(default_factory=dict)
    common_errors: dict[str, int] = field(default_factory=dict)

    def completion_rate(self) -> float:
        if self.total_invocations == 0:
            return 0.0
        return (self.completed_invocations / self.total_invocations) * 100


class SkillsTracker:
    def __init__(self, session_id: str, metrics_file: Path | None = None) -> None:
        self.session_id = session_id
        self.metrics_file = metrics_file
        self._invocations: list[SkillInvocation] = []
        self._skill_metrics: dict[str, SkillMetrics] = {}

        if self.metrics_file and self.metrics_file.exists():
            self._load_metrics()

    def _load_metrics(self) -> None:
        if self.metrics_file is None:
            return
        raw = self.metrics_file.read_text().strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        self._invocations = [
            SkillInvocation(**item) for item in payload.get("invocations", [])
        ]
        self._rebuild_metrics()

    def _rebuild_metrics(self) -> None:
        self._skill_metrics = {}
        for invocation in self._invocations:
            self._update_metrics(invocation)

    def _update_metrics(self, invocation: SkillInvocation) -> None:
        metrics = self._skill_metrics.setdefault(
            invocation.skill_name,
            SkillMetrics(skill_name=invocation.skill_name),
        )
        metrics.total_invocations += 1
        if invocation.completed:
            metrics.completed_invocations += 1
            if invocation.duration_seconds is not None:
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

    def track_invocation(
        self,
        skill_name: str,
        workflow_path: str | None = None,
        user_query: str | None = None,
        alternatives_considered: list[str] | None = None,
        selection_rank: int | None = None,
    ) -> Callable[..., None]:
        invocation = SkillInvocation(
            skill_name=skill_name,
            invoked_at=datetime.now().isoformat(),
            session_id=self.session_id,
            workflow_path=workflow_path,
            user_query=user_query,
            alternatives_considered=list(alternatives_considered or []),
            selection_rank=selection_rank,
        )
        self._invocations.append(invocation)

        def complete(**kwargs: Any) -> None:
            invocation.completed = kwargs.get("completed", True)
            invocation.follow_up_actions = list(kwargs.get("follow_up_actions", []))
            invocation.error_type = kwargs.get("error_type")
            if invocation.completed:
                invocation.duration_seconds = kwargs.get("duration_seconds", 0.01)
            self._skill_metrics.clear()
            self._rebuild_metrics()

        return complete

    def get_session_skills(self) -> list[SkillInvocation]:
        return self._invocations.copy()

    def get_session_summary(self) -> dict[str, Any]:
        total_duration = sum(
            inv.duration_seconds or 0.0 for inv in self._invocations if inv.completed
        )
        return {
            "session_id": self.session_id,
            "total_invocations": len(self._invocations),
            "completed_invocations": sum(
                1 for inv in self._invocations if inv.completed
            ),
            "abandoned_invocations": sum(
                1 for inv in self._invocations if not inv.completed
            ),
            "total_duration_seconds": total_duration,
        }

    def get_skill_metrics(self, skill_name: str) -> SkillMetrics | None:
        return self._skill_metrics.get(skill_name)

    def export_metrics(self, path: Path) -> None:
        payload = {
            "invocations": [inv.__dict__ for inv in self._invocations],
        }
        path.write_text(json.dumps(payload, indent=2))

    def recommend_skills(
        self,
        user_query: str,
        limit: int = 5,
        workflow_phase: str | None = None,
        phase_weight: float = 0.3,
        db_path: Path | None = None,
    ) -> list[dict[str, Any]]:
        """Return simple skill recommendations for backward compatibility."""
        if db_path is None:
            return []

        from session_buddy.storage.skills_storage import SkillsStorage

        storage = SkillsStorage(db_path=db_path)
        metrics = storage.get_all_metrics()

        recommendations: list[dict[str, Any]] = []
        for metric in sorted(
            metrics,
            key=lambda item: (item.completion_rate, item.total_invocations),
            reverse=True,
        )[:limit]:
            rec: dict[str, Any] = {
                "skill_name": metric.skill_name,
                "similarity_score": metric.completion_rate / 100.0,
            }
            if workflow_phase is not None:
                rec["workflow_phase"] = workflow_phase
            recommendations.append(rec)

        return recommendations

    def generate_workflow_report(
        self,
        db_path: Path | None = None,
        session_id: str | None = None,
    ) -> str:
        """Generate a plain-text workflow report for compatibility tests."""
        if db_path is None:
            return "Workflow Correlation Report\nNo database available."

        from session_buddy.storage.skills_storage import SkillsStorage

        storage = SkillsStorage(db_path=db_path)
        lines: list[str] = [
            "Workflow Correlation Report",
            "=" * 30,
        ]
        if session_id:
            lines.append(f"Session: {session_id}")

        effectiveness = storage.get_workflow_skill_effectiveness()
        lines.extend(["", "Skill Effectiveness by Workflow Phase"])
        if effectiveness:
            for item in effectiveness[:10]:
                lines.append(
                    f"- {item['workflow_phase']}: {item['skill_name']} "
                    f"({item['completion_rate']:.1f}% complete)"
                )
        else:
            lines.append("No workflow data available.")

        lines.extend(["", "Workflow Bottlenecks"])
        bottlenecks = storage.identify_workflow_bottlenecks()
        if bottlenecks:
            for item in bottlenecks[:10]:
                lines.append(
                    f"- {item['workflow_phase']}: {item['abandonment_rate']:.1%} abandonment"
                )
        else:
            lines.append("No significant bottlenecks detected.")

        lines.extend(["", "Phase Transitions"])
        transitions = storage.get_workflow_phase_transitions(session_id=session_id)
        if transitions:
            for item in transitions[:10]:
                lines.append(
                    f"- {item['from_phase']} -> {item['to_phase']} ({item['invocation_count']})"
                )
        else:
            lines.append("No phase transition data available.")

        lines.extend(["", "Recommendations by Phase"])
        if effectiveness:
            for item in effectiveness[:5]:
                lines.append(f"- {item['workflow_phase']}: {item['skill_name']}")
        else:
            lines.append("No recommendations available.")

        return "\n".join(lines)

    def generate_phase_heatmap(
        self,
        db_path: Path | None = None,
        session_id: str | None = None,
    ) -> str:
        """Generate a simple text heatmap for compatibility tests."""
        if db_path is None:
            return "Skill Usage Heatmap\nNo workflow data available.\nLegend: higher usage = denser marks"

        from session_buddy.storage.skills_storage import SkillsStorage

        storage = SkillsStorage(db_path=db_path)
        effectiveness = storage.get_workflow_skill_effectiveness()
        if not effectiveness:
            return "Skill Usage Heatmap\nNo workflow data available.\nLegend: higher usage = denser marks"

        phases: list[str] = sorted(
            {
                str(item["workflow_phase"])
                for item in effectiveness
                if item.get("workflow_phase")
            }
        )
        lines: list[str] = [
            "Skill Usage Heatmap",
            "=" * 20,
            "Phase | " + " | ".join(phases),
            "Legend: higher usage = denser marks",
        ]

        for skill_name in sorted({str(item["skill_name"]) for item in effectiveness}):
            row: list[str] = [skill_name]
            for phase in phases:
                count = sum(
                    1
                    for item in effectiveness
                    if item["skill_name"] == skill_name
                    and item["workflow_phase"] == phase
                )
                row.append("##" if count else "..")
            lines.append(" | ".join(row))

        return "\n".join(lines)


def _compute_skill(
    self: Any, db_path: Path | None = None, session_id: str | None = None
) -> str:
    result = _compute_to_phase(self, db_path, session_id)
    return result if result is not None else ""


def _section_1_skill_effectiveness_by_phase(
    storage: Any, lines: list[str]
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
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
        phases: dict[str, list[dict[str, Any]]] = {}
        for skill in effectiveness:
            phase = skill["workflow_phase"]
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(skill)

        for phase, skills in sorted(phases.items()):
            lines.extend(
                [
                    f"\n📍 Phase: {phase.upper()}",
                    "   " + "-" * 65,
                    f"   {'Skill':<30} {'Rate':>8} {'Avg Time':>10} {'Total':>8}",
                    "   " + "-" * 65,
                ]
            )

            for skill in sorted(
                skills, key=operator.itemgetter("completion_rate"), reverse=True
            )[:5]:
                lines.append(
                    f"   {skill['skill_name']:<30} "
                    f"{skill['completion_rate']:>7.1f}% "
                    f"{skill['avg_duration_seconds']:>9.1f}s "
                    f"{skill['total_invocations']:>8}"
                )
    else:
        lines.append("No workflow data available yet.")
    return effectiveness, phases


def _section_2_bottleneck_identification(storage: Any, lines: list[str]) -> None:
    lines.extend(["", "", "-" * 70, "2. Workflow Bottlenecks", "-" * 70, ""])

    bottlenecks = storage.identify_workflow_bottlenecks(min_abandonment_rate=0.2)

    if bottlenecks:
        lines.extend(
            ["", "Phases with high abandonment rates (potential bottlenecks):", ""]
        )

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


def _section_3_phase_transition_diagram(
    session_id: str | None, storage: Any, lines: list[str]
) -> None:
    lines.extend(["", "", "-" * 70, "3. Workflow Phase Transitions", "-" * 70, ""])

    transitions = storage.get_workflow_phase_transitions(session_id=session_id)

    if transitions:
        lines.extend(["", "Most common phase transitions:", ""])

        # Create ASCII flow diagram
        for transition in transitions[:8]:
            from_phase = transition["from_phase"]
            to_phase = transition["to_phase"]
            count = transition["invocation_count"]
            skill = transition["most_common_skill"]

            lines.append(f"  {from_phase} ──[{count}x, {skill}]──> {to_phase}")
    else:
        lines.append("No phase transition data available yet.")


def _section_4_phasespecific_recommendations(
    lines: list[str],
    effectiveness: list[dict[str, Any]],
    phases: dict[str, list[dict[str, Any]]],
) -> None:
    lines.extend(["", "", "-" * 70, "4. Recommendations by Phase", "-" * 70, ""])

    if effectiveness:
        lines.extend(["", "Top-performing skills for each phase:", ""])

        for phase in sorted(phases.keys()):
            phase_skills = [
                s
                for s in effectiveness
                if s["workflow_phase"] == phase and s["completion_rate"] > 70
            ]

            if phase_skills:
                best_skill = max(
                    phase_skills, key=operator.itemgetter("completion_rate")
                )
                lines.append(
                    f"  🎯 {phase.upper()}: Use {best_skill['skill_name']} "
                    f"({best_skill['completion_rate']:.1f}% success rate)"
                )
    else:
        lines.append("Insufficient data for recommendations.")

    lines.extend(["", "", "=" * 70])

    return None


def _compute_to_phase(
    self: Any, db_path: Path | None = None, session_id: str | None = None
) -> str | None:
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
        f"Session: {session_id or 'All Sessions'}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # Section 1: Skill Effectiveness by Phase
    effectiveness, phases = _section_1_skill_effectiveness_by_phase(storage, lines)

    # Section 2: Bottleneck Identification
    _section_2_bottleneck_identification(storage, lines)

    # Section 3: Phase Transition Diagram
    _section_3_phase_transition_diagram(session_id, storage, lines)

    # Section 4: Phase-Specific Recommendations
    _section_4_phasespecific_recommendations(lines, effectiveness, phases)

    return "\n".join(lines)
