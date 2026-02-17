"""CI/CD pipeline tracking for session-buddy.

Tracks skill usage during CI/CD pipeline execution, mapping pipeline stages
to Oneiric workflow phases for comprehensive analytics across the entire
development lifecycle.

Example:
    >>> from session_buddy.integrations import CICDTracker, CIPipelineContext
    >>> tracker = CICDTracker(db_path="skills.db")
    >>> context = CIPipelineContext(
    ...     pipeline_name="test-pipeline",
    ...     build_number="123",
    ...     git_commit="abc123",
    ...     git_branch="main",
    ...     environment="staging",
    ...     triggered_by="github"
    ... )
    >>> tracker.track_pipeline_stage(
    ...     context, "test", "pytest-run", True, 45.2
    ... )
    >>> analytics = tracker.get_pipeline_analytics("test-pipeline", days=7)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from session_buddy.storage.skills_storage import SkillsStorage


@dataclass
class CIPipelineContext:
    """Context information for a CI/CD pipeline execution.

    Attributes:
        pipeline_name: Name of the pipeline (e.g., "ci-pipeline", "deploy-prod")
        build_number: Build or run number (as string to preserve leading zeros)
        git_commit: Git commit SHA being built
        git_branch: Git branch name
        environment: Deployment environment (staging, production, etc.)
        triggered_by: What triggered the pipeline (github, gitlab, manual, etc.)
    """

    pipeline_name: str
    build_number: str
    git_commit: str
    git_branch: str
    environment: str
    triggered_by: str

    def __post_init__(self) -> None:
        """Validate context fields after initialization."""
        if not self.git_commit:
            raise ValueError("git_commit cannot be empty")

        if not self.git_branch:
            raise ValueError("git_branch cannot be empty")

        valid_environments = {"staging", "production", "development", "testing"}
        if self.environment not in valid_environments:
            raise ValueError(
                f"Invalid environment: {self.environment}. Valid: {valid_environments}"
            )

    def get_short_commit(self) -> str:
        """Get short (7-character) commit SHA."""
        return self.git_commit[:7]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "pipeline_name": self.pipeline_name,
            "build_number": self.build_number,
            "git_commit": self.git_commit,
            "git_branch": self.git_branch,
            "environment": self.environment,
            "triggered_by": self.triggered_by,
        }


@dataclass
class PipelineStageMetrics:
    """Metrics for a single pipeline stage.

    Attributes:
        stage_name: Pipeline stage name (build, test, lint, deploy)
        workflow_phase: Mapped Oneiric workflow phase
        total_runs: Total number of stage executions
        successful_runs: Number of successful executions
        failed_runs: Number of failed executions
        total_duration_seconds: Total time spent in this stage
        skills_used: Set of skills invoked in this stage
        common_failures: Dictionary mapping error types to counts
    """

    stage_name: str
    workflow_phase: str
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_duration_seconds: float = 0.0
    skills_used: set[str] = field(default_factory=set)
    common_failures: dict[str, int] = field(default_factory=dict)

    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_runs == 0:
            return 0.0
        return (self.successful_runs / self.total_runs) * 100

    def avg_duration_seconds(self) -> float:
        """Calculate average duration in seconds."""
        if self.successful_runs == 0:
            return 0.0
        return self.total_duration_seconds / self.successful_runs


class CICDTracker:
    """CI/CD pipeline skill tracking integration.

    Maps CI/CD pipeline stages to Oneiric workflow phases and provides
    comprehensive tracking of skill usage during automated pipelines.

    Stage Mapping:
        - build → setup: Package installation, compilation
        - test → execution: Running test suites
        - lint → verification: Code quality checks
        - deploy → deployment: Deployment to environments

    Attributes:
        db_path: Path to skills database
        storage: SkillsStorage instance for queries
        stage_metrics: Dictionary tracking metrics per stage
    """

    # Mapping from CI/CD stages to Oneiric workflow phases
    STAGE_MAPPING: dict[str, str] = {
        "build": "setup",
        "test": "execution",
        "lint": "verification",
        "security": "verification",
        "deploy": "deployment",
        "publish": "deployment",
    }

    # Common CI/CD skills by stage
    STAGE_SKILLS: dict[str, list[str]] = {
        "build": [
            "uv-install",
            "npm-install",
            "docker-build",
            "compile",
        ],
        "test": [
            "pytest-run",
            "jest-run",
            "test-discovery",
            "coverage-report",
        ],
        "lint": [
            "ruff-check",
            "mypy-check",
            "eslint-check",
            "tsc-check",
        ],
        "security": [
            "bandit-security",
            "safety-check",
            "npm-audit",
        ],
        "deploy": [
            "docker-push",
            "helm-deploy",
            "terraform-apply",
        ],
        "publish": [
            "npm-publish",
            "pypi-publish",
        ],
    }

    def __init__(self, db_path: str | Path) -> None:
        """Initialize CI/CD tracker.

        Args:
            db_path: Path to skills database file
        """
        self.db_path = Path(db_path)

        # Import here to avoid circular dependency
        from session_buddy.storage.skills_storage import SkillsStorage

        self.storage: SkillsStorage = SkillsStorage(db_path=self.db_path)

        # Track metrics per stage
        self.stage_metrics: dict[str, PipelineStageMetrics] = {}

        # Initialize metrics for all known stages
        for stage in self.STAGE_MAPPING:
            self.stage_metrics[stage] = PipelineStageMetrics(
                stage_name=stage,
                workflow_phase=self.STAGE_MAPPING[stage],
            )

    def track_pipeline_stage(
        self,
        context: CIPipelineContext,
        stage_name: str,
        skill_name: str,
        completed: bool,
        duration_seconds: float,
        artifacts: list[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Track a skill invocation during a CI/CD pipeline stage.

        Maps the CI/CD stage to an Oneiric workflow phase and records
        the skill invocation with pipeline context.

        Args:
            context: CIPipelineContext for this pipeline execution
            stage_name: CI/CD stage (build, test, lint, deploy, etc.)
            skill_name: Name of the tool/skill being invoked
            completed: Whether the invocation completed successfully
            duration_seconds: Time taken for the invocation
            artifacts: Optional list of artifacts generated (files, reports, etc.)
            error_message: Optional error message if invocation failed

        Raises:
            ValueError: If stage_name is not a recognized CI/CD stage

        Example:
            >>> tracker.track_pipeline_stage(
            ...     context, "test", "pytest-run", True, 45.2
            ... )
        """
        # Validate stage
        if stage_name not in self.STAGE_MAPPING:
            valid_stages = ", ".join(self.STAGE_MAPPING.keys())
            raise ValueError(
                f"Unknown CI/CD stage: {stage_name}. Valid stages: {valid_stages}"
            )

        # Map to Oneiric workflow phase
        self.STAGE_MAPPING[stage_name]

        # Store invocation in database
        self._store_invocation(
            context=context,
            stage_name=stage_name,
            skill_name=skill_name,
            completed=completed,
            duration_seconds=duration_seconds,
            artifacts=artifacts,
            error_message=error_message,
        )

        # Update stage metrics
        metrics = self.stage_metrics[stage_name]
        metrics.total_runs += 1
        metrics.skills_used.add(skill_name)

        if completed:
            metrics.successful_runs += 1
            metrics.total_duration_seconds += duration_seconds
        else:
            metrics.failed_runs += 1
            if error_message:
                metrics.common_failures[error_message] = (
                    metrics.common_failures.get(error_message, 0) + 1
                )

    def _store_invocation(
        self,
        context: CIPipelineContext,
        stage_name: str,
        skill_name: str,
        completed: bool,
        duration_seconds: float,
        artifacts: list[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Store skill invocation in database.

        Args:
            context: CIPipelineContext
            stage_name: CI/CD stage
            skill_name: Skill name
            completed: Completion status
            duration_seconds: Duration
            artifacts: Generated artifacts
            error_message: Error if failed
        """
        # Create session ID from pipeline context
        session_id = f"{context.pipeline_name}-{context.build_number}"

        # Create skill invocation record
        from session_buddy.storage.skills_storage import SkillInvocation

        invocation = SkillInvocation(
            skill_name=skill_name,
            invoked_at=datetime.now().isoformat(),
            session_id=session_id,
            workflow_phase=self.STAGE_MAPPING[stage_name],
            user_query=f"CI/CD stage: {stage_name}",
            completed=completed,
            duration_seconds=duration_seconds,
            error_type=error_message,
        )

        # Store in database
        self.storage.store_invocation(invocation)

        # Store pipeline context as metadata
        self._store_pipeline_context(
            session_id=session_id,
            context=context,
            stage_name=stage_name,
            artifacts=artifacts,
        )

    def _store_pipeline_context(
        self,
        session_id: str,
        context: CIPipelineContext,
        stage_name: str,
        artifacts: list[str] | None = None,
    ) -> None:
        """Store pipeline context metadata.

        Args:
            session_id: Session identifier
            context: CIPipelineContext
            stage_name: Stage name
            artifacts: Optional artifacts
        """
        # In a full implementation, this would store to a separate table
        # For now, we'll store as JSON metadata
        {
            "session_id": session_id,
            "pipeline_context": context.to_dict(),
            "stage_name": stage_name,
            "artifacts": artifacts or [],
            "stored_at": datetime.now().isoformat(),
        }

        # Could be stored in a separate ci_metadata table
        # For now, this is a placeholder for future implementation
        pass

    def get_workflow_phase(self, stage_name: str) -> str:
        """Get Oneiric workflow phase for a CI/CD stage.

        Args:
            stage_name: CI/CD stage name

        Returns:
            Corresponding Oneiric workflow phase

        Raises:
            ValueError: If stage_name is not recognized
        """
        if stage_name not in self.STAGE_MAPPING:
            valid_stages = ", ".join(self.STAGE_MAPPING.keys())
            raise ValueError(
                f"Unknown CI/CD stage: {stage_name}. Valid stages: {valid_stages}"
            )

        return self.STAGE_MAPPING[stage_name]

    def get_pipeline_analytics(
        self,
        pipeline_name: str,
        days: int = 7,
    ) -> dict:
        """Get analytics for a pipeline over a time window.

        Provides comprehensive analytics including:
        - Stage success rates
        - Average durations
        - Bottleneck identification
        - Failure patterns

        Args:
            pipeline_name: Name of the pipeline
            days: Number of days to look back (default: 7)

        Returns:
            Dictionary with analytics data

        Example:
            >>> analytics = tracker.get_pipeline_analytics("test-pipeline", days=30)
            >>> print(f"Success rate: {analytics['overall_success_rate']:.1f}%")
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        # Query database for pipeline runs in time window
        # This is a simplified implementation
        analytics = {
            "pipeline_name": pipeline_name,
            "time_window_days": days,
            "from_date": cutoff_date.isoformat(),
            "to_date": datetime.now().isoformat(),
            "stage_analytics": {},
            "overall_success_rate": 0.0,
            "bottlenecks": [],
            "recommendations": [],
        }

        # Aggregate stage metrics
        total_runs = 0
        total_successful = 0

        for stage_name, metrics in self.stage_metrics.items():
            if metrics.total_runs > 0:
                stage_data = {
                    "stage_name": stage_name,
                    "workflow_phase": metrics.workflow_phase,
                    "total_runs": metrics.total_runs,
                    "successful_runs": metrics.successful_runs,
                    "success_rate": metrics.success_rate(),
                    "avg_duration_seconds": metrics.avg_duration_seconds(),
                    "skills_used": list(metrics.skills_used),
                }

                if metrics.common_failures:
                    stage_data["common_failures"] = metrics.common_failures

                analytics["stage_analytics"][stage_name] = stage_data

                total_runs += metrics.total_runs
                total_successful += metrics.successful_runs

        # Calculate overall success rate
        if total_runs > 0:
            analytics["overall_success_rate"] = (total_successful / total_runs) * 100

        # Identify bottlenecks (stages with low success rate)
        bottlenecks = []
        for stage_name, stage_data in analytics["stage_analytics"].items():
            if stage_data["success_rate"] < 80.0:
                bottlenecks.append(
                    {
                        "stage": stage_name,
                        "success_rate": stage_data["success_rate"],
                        "avg_duration": stage_data["avg_duration_seconds"],
                        "severity": "high"
                        if stage_data["success_rate"] < 50
                        else "medium",
                    }
                )

        analytics["bottlenecks"] = sorted(
            bottlenecks,
            key=lambda x: x["success_rate"],
        )

        # Generate recommendations
        analytics["recommendations"] = self._generate_pipeline_recommendations(
            analytics
        )

        return analytics

    def _generate_pipeline_recommendations(
        self,
        analytics: dict,
    ) -> list[dict]:
        """Generate recommendations based on pipeline analytics.

        Args:
            analytics: Pipeline analytics dictionary

        Returns:
            List of recommendation dictionaries
        """
        recommendations = []

        # Check for high failure rates
        for stage_name, stage_data in analytics["stage_analytics"].items():
            if stage_data["success_rate"] < 70.0:
                recommendations.append(
                    {
                        "priority": "high",
                        "stage": stage_name,
                        "message": (
                            f"Stage '{stage_name}' has low success rate "
                            f"({stage_data['success_rate']:.1f}%). "
                            f"Investigate common failures."
                        ),
                    }
                )

        # Check for slow stages
        for stage_name, stage_data in analytics["stage_analytics"].items():
            if stage_data["avg_duration_seconds"] > 300:  # 5 minutes
                recommendations.append(
                    {
                        "priority": "medium",
                        "stage": stage_name,
                        "message": (
                            f"Stage '{stage_name}' is slow "
                            f"({stage_data['avg_duration_seconds']:.1f}s avg). "
                            f"Consider optimization or parallelization."
                        ),
                    }
                )

        # Check for missing skills
        for stage_name in self.STAGE_SKILLS:
            if stage_name in analytics["stage_analytics"]:
                used_skills = set(
                    analytics["stage_analytics"][stage_name]["skills_used"]
                )
                expected_skills = set(self.STAGE_SKILLS[stage_name])
                missing = expected_skills - used_skills

                if missing:
                    recommendations.append(
                        {
                            "priority": "low",
                            "stage": stage_name,
                            "message": (
                                f"Consider adding skills to '{stage_name}': "
                                f"{', '.join(missing)}"
                            ),
                        }
                    )

        return recommendations

    def get_stage_summary(self, stage_name: str) -> dict:
        """Get summary dictionary for a specific stage.

        Args:
            stage_name: CI/CD stage name

        Returns:
            Dictionary with stage metrics

        Example:
            >>> summary = tracker.get_stage_summary("test")
            >>> print(f"Success rate: {summary['success_rate']:.1f}%")
        """
        if stage_name not in self.stage_metrics:
            raise ValueError(f"Unknown stage: {stage_name}")

        metrics = self.stage_metrics[stage_name]

        return {
            "stage_name": metrics.stage_name,
            "workflow_phase": metrics.workflow_phase,
            "total_runs": metrics.total_runs,
            "successful_runs": metrics.successful_runs,
            "failed_runs": metrics.failed_runs,
            "success_rate": metrics.success_rate(),
            "total_duration_seconds": metrics.total_duration_seconds,
            "avg_duration_seconds": metrics.avg_duration_seconds(),
            "skills_used": list(metrics.skills_used),
            "common_failures": metrics.common_failures.copy(),
        }

    def generate_pipeline_report(self, pipeline_name: str, days: int = 7) -> str:
        """Generate comprehensive pipeline report.

        Creates a detailed report showing:
        - Stage-by-stage metrics
        - Success rates and durations
        - Bottleneck identification
        - Recommendations for improvement

        Args:
            pipeline_name: Name of the pipeline
            days: Number of days to include in report

        Returns:
            Formatted multi-section report

        Example:
            >>> report = tracker.generate_pipeline_report("test-pipeline", days=30)
            >>> print(report)
        """
        analytics = self.get_pipeline_analytics(pipeline_name, days)

        lines = [
            "=" * 70,
            "CI/CD Pipeline Analytics Report",
            "=" * 70,
            "",
            f"Pipeline: {pipeline_name}",
            f"Time Window: Last {days} days",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Overall Success Rate: {analytics['overall_success_rate']:.1f}%",
            "",
        ]

        # Section 1: Stage-by-Stage Metrics
        lines.extend(
            [
                "-" * 70,
                "1. Stage Metrics",
                "-" * 70,
                "",
            ]
        )

        for stage_name in ["build", "test", "lint", "security", "deploy", "publish"]:
            if stage_name in analytics["stage_analytics"]:
                stage_data = analytics["stage_analytics"][stage_name]

                lines.extend(
                    [
                        f"\nStage: {stage_name.upper()} (→ {stage_data['workflow_phase']})",
                        "  " + "-" * 65,
                        f"  Total Runs: {stage_data['total_runs']}",
                        f"  Successful: {stage_data['successful_runs']}",
                        f"  Success Rate: {stage_data['success_rate']:.1f}%",
                        f"  Avg Duration: {stage_data['avg_duration_seconds']:.1f}s",
                        "",
                    ]
                )

                if stage_data["skills_used"]:
                    lines.append("  Skills Used:")
                    for skill in sorted(stage_data["skills_used"]):
                        lines.append(f"    - {skill}")

                if "common_failures" in stage_data:
                    lines.append("")
                    lines.append("  Common Failures:")
                    for error, count in sorted(
                        stage_data["common_failures"].items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:5]:
                        lines.append(f"    - {error}: {count}x")

        # Section 2: Bottlenecks
        lines.extend(
            [
                "",
                "",
                "-" * 70,
                "2. Pipeline Bottlenecks",
                "-" * 70,
                "",
            ]
        )

        if analytics["bottlenecks"]:
            lines.append("Stages requiring attention:")
            lines.append("")

            for bottleneck in analytics["bottlenecks"]:
                stage = bottleneck["stage"]
                rate = bottleneck["success_rate"]
                severity = bottleneck["severity"].upper()

                lines.append(f"  {severity}: {stage} ({rate:.1f}% success)")
        else:
            lines.append("No significant bottlenecks detected!")

        # Section 3: Recommendations
        lines.extend(
            [
                "",
                "",
                "-" * 70,
                "3. Recommendations",
                "-" * 70,
                "",
            ]
        )

        if analytics["recommendations"]:
            for rec in analytics["recommendations"]:
                priority = rec["priority"].upper()
                message = rec["message"]
                lines.append(f"  [{priority}] {message}")
        else:
            lines.append("No recommendations at this time.")

        lines.extend(["", "", "=" * 70])

        return "\n".join(lines)

    def export_analytics(
        self,
        pipeline_name: str,
        output_file: Path,
        days: int = 7,
    ) -> None:
        """Export pipeline analytics to JSON file.

        Args:
            pipeline_name: Name of the pipeline
            output_file: Path to output JSON file
            days: Number of days to include

        Example:
            >>> tracker.export_analytics(
            ...     "test-pipeline",
            ...     Path("analytics.json"),
            ...     days=30
            ... )
        """
        analytics = self.get_pipeline_analytics(pipeline_name, days)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(analytics, indent=2),
        )
