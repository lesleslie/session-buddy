def _compute_skill(
    self, db_path: Path | None = None, session_id: str | None = None
) -> str:
    return _compute_to_phase(self, db_path, session_id)


def _section_1_skill_effectiveness_by_phase(storage, lines):
    phases = {}
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
            lines.append(f"   {'Skill':<30} {'Rate':>8} {'Avg Time':>10} {'Total':>8}")
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
    return effectiveness, phases


def _section_2_bottleneck_identification(storage, lines):
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


def _section_3_phase_transition_diagram(session_id, storage, lines):
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


def _section_4_phasespecific_recommendations(lines, effectiveness, phases):
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


def _compute_to_phase(
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
    effectiveness, phases = _section_1_skill_effectiveness_by_phase(storage, lines)

    # Section 2: Bottleneck Identification
    _section_2_bottleneck_identification(storage, lines)

    # Section 3: Phase Transition Diagram
    _section_3_phase_transition_diagram(session_id, storage, lines)

    # Section 4: Phase-Specific Recommendations
    _section_4_phasespecific_recommendations(lines, effectiveness, phases)
