"""AI agent recommendation system for crackerjack failures."""

import re
import typing as t
from dataclasses import dataclass
from enum import StrEnum


class AgentType(StrEnum):
    """Available crackerjack AI agents."""

    REFACTORING = "RefactoringAgent"
    PERFORMANCE = "PerformanceAgent"
    SECURITY = "SecurityAgent"
    DOCUMENTATION = "DocumentationAgent"
    TEST_CREATION = "TestCreationAgent"
    DRY = "DRYAgent"
    FORMATTING = "FormattingAgent"
    IMPORT_OPTIMIZATION = "ImportOptimizationAgent"
    TEST_SPECIALIST = "TestSpecialistAgent"


@dataclass
class AgentRecommendation:
    """Recommendation for using a specific AI agent."""

    agent: AgentType
    confidence: float  # 0.0-1.0
    reason: str
    quick_fix_command: str
    pattern_matched: str


class AgentAnalyzer:
    """Analyze crackerjack failures and recommend AI agents."""

    # Error patterns mapped to agents with confidence scores
    PATTERNS: t.Final[list[dict[str, t.Any]]] = [
        # Complexity issues → RefactoringAgent
        {
            "pattern": r"Complexity of (\d+) is too high",
            "agent": AgentType.REFACTORING,
            "confidence": 0.9,
            "reason": "Complexity violation detected (limit: 15)",
            "command": "python -m crackerjack --ai-fix",
        },
        {
            "pattern": r"Function .* is too complex \((\d+)\)",
            "agent": AgentType.REFACTORING,
            "confidence": 0.85,
            "reason": "Complex function needs refactoring",
            "command": "python -m crackerjack --ai-fix",
        },
        # Security issues → SecurityAgent
        {
            "pattern": r"B\d{3}:",
            "agent": AgentType.SECURITY,
            "confidence": 0.8,
            "reason": "Bandit security issue found",
            "command": "python -m crackerjack --ai-fix",
        },
        {
            "pattern": r"hardcoded.*path|shell=True|unsafe",
            "agent": AgentType.SECURITY,
            "confidence": 0.85,
            "reason": "Security vulnerability detected",
            "command": "python -m crackerjack --ai-fix",
        },
        # Test failures → TestCreationAgent
        {
            "pattern": r"(\d+) failed",
            "agent": AgentType.TEST_CREATION,
            "confidence": 0.8,
            "reason": "Test failures need investigation",
            "command": "python -m crackerjack --ai-fix --run-tests",
        },
        {
            "pattern": r"FAILED tests/.*::",
            "agent": AgentType.TEST_CREATION,
            "confidence": 0.85,
            "reason": "Specific test failure identified",
            "command": "python -m crackerjack --ai-fix --run-tests",
        },
        # Coverage issues → TestSpecialistAgent
        {
            "pattern": r"coverage:?\s*(\d+(?:\.\d+)?)%",
            "agent": AgentType.TEST_SPECIALIST,
            "confidence": 0.7,
            "reason": "Coverage below baseline (42%)",
            "command": "python -m crackerjack --ai-fix --run-tests",
        },
        # Type errors → ImportOptimizationAgent
        {
            "pattern": r"error:|type.*error|Found (\d+) error",
            "agent": AgentType.IMPORT_OPTIMIZATION,
            "confidence": 0.75,
            "reason": "Type or import errors detected",
            "command": "python -m crackerjack --ai-fix",
        },
        # Formatting issues → FormattingAgent
        {
            "pattern": r"would reformat|line too long|trailing whitespace",
            "agent": AgentType.FORMATTING,
            "confidence": 0.9,
            "reason": "Code formatting violations found",
            "command": "python -m crackerjack --ai-fix",
        },
        # Code duplication → DRYAgent
        {
            "pattern": r"duplicate|repeated code|similar.*block",
            "agent": AgentType.DRY,
            "confidence": 0.8,
            "reason": "Code duplication detected",
            "command": "python -m crackerjack --ai-fix",
        },
        # Performance issues → PerformanceAgent
        {
            "pattern": r"slow|timeout|O\(n[²³]\)|inefficient",
            "agent": AgentType.PERFORMANCE,
            "confidence": 0.75,
            "reason": "Performance issue identified",
            "command": "python -m crackerjack --ai-fix",
        },
        # Documentation issues → DocumentationAgent
        {
            "pattern": r"missing.*docstring|undocumented|changelog",
            "agent": AgentType.DOCUMENTATION,
            "confidence": 0.7,
            "reason": "Documentation needs improvement",
            "command": "python -m crackerjack --ai-fix",
        },
    ]

    @classmethod
    def _should_skip_coverage_recommendation(
        cls,
        pattern_config: dict[str, t.Any],
        combined: str,
    ) -> bool:
        """Check if coverage recommendation should be skipped."""
        if pattern_config["agent"] != AgentType.TEST_SPECIALIST:
            return False

        coverage_match = re.search(  # REGEX OK: coverage extraction
            r"coverage:?\s*(\d+(?:\.\d+)?)%",
            combined,
        )
        return bool(coverage_match and float(coverage_match.group(1)) >= 42)

    @classmethod
    def _deduplicate_recommendations(
        cls,
        recommendations: list[AgentRecommendation],
    ) -> list[AgentRecommendation]:
        """Remove duplicate recommendations, keeping highest confidence."""
        unique: dict[AgentType, AgentRecommendation] = {}
        for rec in recommendations:
            if rec.agent not in unique or rec.confidence > unique[rec.agent].confidence:
                unique[rec.agent] = rec

        return sorted(unique.values(), key=lambda x: x.confidence, reverse=True)[:3]

    @classmethod
    def analyze(
        cls,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[AgentRecommendation]:
        """Analyze crackerjack output and recommend agents.

        Args:
            stdout: Standard output from crackerjack
            stderr: Standard error from crackerjack
            exit_code: Process exit code

        Returns:
            List of agent recommendations sorted by confidence (highest first)

        """
        if exit_code == 0:
            return []  # No failures, no recommendations needed

        recommendations: list[AgentRecommendation] = []
        combined = stdout + stderr

        for pattern_config in cls.PATTERNS:
            pattern = pattern_config["pattern"]
            matches = (
                re.findall(  # REGEX OK: error pattern matching from PATTERNS config
                    pattern,
                    combined,
                    re.IGNORECASE,
                )
            )

            if matches and not cls._should_skip_coverage_recommendation(
                pattern_config,
                combined,
            ):
                recommendation = AgentRecommendation(
                    agent=pattern_config["agent"],
                    confidence=pattern_config["confidence"],
                    reason=pattern_config["reason"],
                    quick_fix_command=pattern_config["command"],
                    pattern_matched=pattern,
                )
                recommendations.append(recommendation)

        return cls._deduplicate_recommendations(recommendations)

    @classmethod
    def format_recommendations(cls, recommendations: list[AgentRecommendation]) -> str:
        """Format recommendations for display.

        Args:
            recommendations: List of agent recommendations

        Returns:
            Formatted string for user display

        """
        if not recommendations:
            return ""

        output = "\n🤖 **AI Agent Recommendations**:\n"

        for i, rec in enumerate(recommendations, 1):
            confidence_emoji = "🔥" if rec.confidence >= 0.85 else "✨"
            output += (
                f"\n{i}. {confidence_emoji} **{rec.agent.value}** "
                f"(confidence: {rec.confidence:.0%})\n"
            )
            output += f"   - **Reason**: {rec.reason}\n"
            output += f"   - **Quick Fix**: `{rec.quick_fix_command}`\n"

        return output
