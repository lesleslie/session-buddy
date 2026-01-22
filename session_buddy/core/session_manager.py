#!/usr/bin/env python3
"""Session lifecycle management for session-buddy.

This module handles session initialization, quality assessment, checkpoints,
and cleanup operations.
"""

import asyncio
import importlib
import logging
import os
import shutil
import sys
import typing as t
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from session_buddy.core.hooks import HookResult, HooksManager
from session_buddy.utils.git_operations import (
    create_checkpoint_commit,
    is_git_repository,
)


def get_session_logger() -> logging.Logger:
    """Get the session logger instance.

    This function is used in tests for mocking purposes.
    """
    return logging.getLogger(__name__)


class SessionLifecycleManager:
    """Manages session lifecycle operations."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize session lifecycle manager.

        Args:
            logger: Logger instance (injected by DI container or standard logger)

        """
        if logger is None:
            logger = logging.getLogger(__name__)

        self.logger = logger
        self.current_project: str | None = None
        self._quality_history: dict[str, list[int]] = {}  # project -> [scores]
        self._captured_insight_hashes: set[str] = (
            set()
        )  # Track captured insights for deduplication
        self.session_context: dict[
            str, t.Any
        ] = {}  # Conversation context for insight extraction

        # Initialize templates renderer for handoff documentation
        self.templates: t.Any | None = None
        self._initialize_templates()

    def _initialize_templates(self) -> None:
        """Initialize Jinja2 environment for handoff documentation."""
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            templates_dir = Path(__file__).parent.parent.parent / "templates"
            self.templates = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                autoescape=select_autoescape(["html", "xml"]),
            )
            self.logger.info(
                "Templates environment initialized, templates_dir=%s",
                str(templates_dir),
            )
        except Exception as e:
            self.logger.warning(
                "Templates environment initialization failed, using fallback, error=%s",
                str(e),
            )
            self.templates = None

    async def calculate_quality_score(
        self,
        project_dir: Path | None = None,
    ) -> dict[str, t.Any]:
        """Calculate session quality score using V2 algorithm.

        Delegates to the centralized quality scoring in server.py to avoid
        code duplication and ensure consistent scoring across the system.

        Args:
            project_dir: Path to the project directory. If not provided, will use current directory.

        """
        if project_dir is None:
            project_dir = Path.cwd()

        if "session_buddy.server" in sys.modules:
            server = sys.modules["session_buddy.server"]
        else:
            server = await asyncio.to_thread(
                importlib.import_module,
                "session_buddy.server",
            )

        return t.cast(
            "dict[str, t.Any]",
            await server.calculate_quality_score(project_dir=project_dir),
        )

    def _calculate_project_score(self, project_context: dict[str, bool]) -> float:
        """Calculate project health score (40% of total)."""
        return (
            sum(1 for detected in project_context.values() if detected)
            / len(project_context)
        ) * 40

    def _calculate_permissions_score(self) -> int:
        """Calculate permissions health score (20% of total)."""
        try:
            from session_buddy.server import permissions_manager

            if hasattr(permissions_manager, "trusted_operations"):
                trusted_count = len(permissions_manager.trusted_operations)
                return min(
                    trusted_count * 4,
                    20,
                )  # 4 points per trusted operation, max 20
            return 10  # Basic score if we can't access trusted operations
        except (ImportError, AttributeError):
            return 10  # Fallback score

    def _calculate_session_score(self) -> int:
        """Calculate session management score (20% of total)."""
        return 20  # Always available in this refactored version

    def _calculate_tool_score(self) -> int:
        """Calculate tool availability score (20% of total)."""
        uv_available = shutil.which("uv") is not None
        return 20 if uv_available else 10

    def _format_quality_score_result(
        self,
        total_score: int,
        project_score: float,
        permissions_score: int,
        session_score: int,
        tool_score: int,
        project_context: dict[str, bool],
        uv_available: bool,
    ) -> dict[str, t.Any]:
        """Format the quality score calculation result."""
        return {
            "total_score": total_score,
            "breakdown": {
                "project_health": project_score,
                "permissions": permissions_score,
                "session_management": session_score,
                "tools": tool_score,
            },
            "recommendations": self._generate_quality_recommendations(
                total_score,
                project_context,
                uv_available,
            ),
        }

    def _generate_quality_recommendations(
        self,
        score: int,
        project_context: dict[str, t.Any],
        uv_available: bool,
    ) -> list[str]:
        """Generate quality improvement recommendations based on score factors."""
        recommendations = []

        if score < 50:
            recommendations.append(
                "Session needs attention - multiple areas for improvement",
            )

        if not project_context.get("has_pyproject_toml"):
            recommendations.append(
                "Consider adding pyproject.toml for modern Python project structure",
            )

        if not project_context.get("has_git_repo"):
            recommendations.append("Initialize git repository for version control")

        if not uv_available:
            recommendations.append(
                "Install UV package manager for improved dependency management",
            )

        if not project_context.get("has_tests"):
            recommendations.append("Add test suite to improve code quality")

        if score >= 80:
            recommendations.append("Excellent session setup! Keep up the good work")
        elif score >= 60:
            recommendations.append("Good session quality with room for optimization")

        return recommendations[:5]  # Limit to top 5 recommendations

    async def perform_quality_assessment(
        self,
        project_dir: Path | None = None,
    ) -> tuple[int, dict[str, t.Any]]:
        """Perform quality assessment and return score and data."""
        quality_data = await self.calculate_quality_score(project_dir=project_dir)
        quality_score = quality_data["total_score"]
        return quality_score, quality_data

    def _format_trust_score(self, trust: t.Any) -> list[str]:
        """Format trust score section (helper to reduce complexity). Target complexity: ≤5."""
        output = []
        # Defensive check: trust_score may be a dict or object with total attribute
        if hasattr(trust, "total"):
            total_score = trust.total
        elif isinstance(trust, dict) and "total" in trust:
            total_score = trust["total"]
        else:
            total_score = 0

        if total_score > 0:
            output.append(f"\n🔐 Trust score: {total_score:.0f}/100 (separate metric)")
            # Handle both dict and object-based trust score
            if isinstance(trust, dict):
                details = trust.get("details", {})
            else:
                details = getattr(trust, "details", {})
                if not isinstance(details, dict):
                    details = {}

            # Only show breakdown if available
            if details:
                output.extend(
                    (
                        f"   • Trusted operations: {details.get('permissions_count', 0)}/40",
                        f"   • Session features: {details.get('session_available', False)} (available)",
                        f"   • Tool ecosystem: {details.get('tool_count', 0)} tools",
                    )
                )
        return output

    def format_quality_results(
        self,
        quality_score: int,
        quality_data: dict[str, t.Any],
        checkpoint_result: dict[str, t.Any] | None = None,
    ) -> list[str]:
        """Format quality assessment results for display. Target complexity: ≤10."""
        output = []

        # Quality status
        if quality_score >= 80:
            output.append(f"✅ Session quality: EXCELLENT (Score: {quality_score}/100)")
        elif quality_score >= 60:
            output.append(f"✅ Session quality: GOOD (Score: {quality_score}/100)")
        else:
            output.append(
                f"⚠️ Session quality: NEEDS ATTENTION (Score: {quality_score}/100)",
            )

        # Quality breakdown - V2 format (actual code quality metrics)
        output.append("\n📈 Quality breakdown (code health metrics):")
        breakdown = quality_data["breakdown"]
        output.extend(
            (
                f"   • Code quality: {breakdown['code_quality']:.1f}/40",
                f"   • Project health: {breakdown['project_health']:.1f}/30",
                f"   • Dev velocity: {breakdown['dev_velocity']:.1f}/20",
                f"   • Security: {breakdown['security']:.1f}/10",
            )
        )

        # Trust score (separate from quality) - extracted to helper
        if "trust_score" in quality_data:
            output.extend(self._format_trust_score(quality_data["trust_score"]))

        # Recommendations
        recommendations = quality_data["recommendations"]
        if recommendations:
            output.append("\n💡 Recommendations:")
            for rec in recommendations[:3]:
                output.append(f"   • {rec}")

        # Session management specific results
        if checkpoint_result:
            strengths = checkpoint_result.get("strengths", [])
            if strengths:
                output.append("\n🌟 Session strengths:")
                for strength in strengths[:3]:
                    output.append(f"   • {strength}")

            session_stats = checkpoint_result.get("session_stats", {})
            if session_stats:
                output.extend(
                    (
                        "\n⏱️ Session progress:",
                        f"   • Duration: {session_stats.get('duration_minutes', 0)} minutes",
                        f"   • Checkpoints: {session_stats.get('total_checkpoints', 0)}",
                        f"   • Success rate: {session_stats.get('success_rate', 0):.1f}%",
                    )
                )

        return output

    async def perform_git_checkpoint(
        self,
        current_dir: Path,
        quality_score: int,
    ) -> list[str]:
        """Handle git operations for checkpoint commit using the new git utilities."""
        output: list[str] = []
        output.extend(("\n" + "=" * 50, "📦 Git Checkpoint Commit", "=" * 50))

        try:
            # Use the new git utilities
            success, result, git_output = create_checkpoint_commit(
                current_dir,
                self.current_project or "Unknown",
                quality_score,
            )

            output.extend(git_output)

            if success and result != "clean":
                self.logger.info(
                    "Checkpoint commit created, project=%s, commit_hash=%s, quality_score=%d",
                    self.current_project,
                    result,
                    quality_score,
                )

        except Exception as e:
            output.append(f"\n⚠️ Git operations error: {e}")
            self.logger.exception(
                "Git checkpoint error occurred, error=%s, project=%s",
                str(e),
                self.current_project,
            )

        return output

    def _setup_working_directory(self, working_directory: str | None) -> Path:
        """Set up working directory and project name."""
        if working_directory:
            os.chdir(working_directory)

        current_dir = Path.cwd()
        self.current_project = current_dir.name
        return current_dir

    def _setup_claude_directories(self) -> Path:
        """Create .claude directory structure."""
        claude_dir = Path.home() / ".claude"
        claude_dir.mkdir(exist_ok=True)
        (claude_dir / "data").mkdir(exist_ok=True)
        (claude_dir / "logs").mkdir(exist_ok=True)
        return claude_dir

    def _discover_session_files(self, current_dir: Path) -> list[Path]:
        """Discover session files in the current directory and subdirectories."""
        return [
            file_path
            for file_path in current_dir.rglob("*.session.json")
            if file_path.is_file()
        ]

    async def _read_previous_session_info(
        self, file_path: Path
    ) -> dict[str, t.Any] | None:
        """Read previous session information from a file - handles both JSON and markdown files."""
        try:
            content = file_path.read_text(encoding="utf-8")

            # Try JSON first
            import json

            try:
                data = json.loads(content)
                # Ensure the return type is properly typed as dict[str, t.Any] | None
                if isinstance(data, dict):
                    return data
                return None
            except json.JSONDecodeError:
                # If not JSON, try to parse as markdown handoff file
                from session_buddy.core.lifecycle.session_info import (
                    parse_session_file,
                )

                # Parse the markdown file content
                session_info = await parse_session_file(file_path)

                # Convert SessionInfo to dictionary format expected by the system
                if session_info.is_complete():
                    return {
                        "ended_at": session_info.ended_at,
                        "quality_score": session_info.quality_score,
                        "working_directory": session_info.working_directory,
                        "top_recommendation": session_info.top_recommendation,
                        "session_id": session_info.session_id,
                    }

                return None
        except OSError:
            return None

    def _find_latest_handoff_file(self, current_dir: Path) -> Path | None:
        """Find the latest handoff file in the project - supports both JSON and markdown files."""
        # Look for markdown handoff files in the current directory (legacy format)
        legacy_handoff_files = list(current_dir.glob("session_handoff_*.md"))
        latest_legacy = None
        if legacy_handoff_files:
            latest_legacy = max(legacy_handoff_files, key=lambda f: f.stat().st_mtime)

        # Look in the .crackerjack/session/handoff directory for newer markdown files
        crackerjack_handoff_dir = current_dir / ".crackerjack" / "session" / "handoff"
        if crackerjack_handoff_dir.exists():
            handoff_files = list(crackerjack_handoff_dir.glob("session_handoff_*.md"))
            if handoff_files:
                latest_nested = max(handoff_files, key=lambda f: f.stat().st_mtime)
                # Compare with legacy files if present and return the most recent
                if (
                    latest_legacy
                    and latest_nested.stat().st_mtime < latest_legacy.stat().st_mtime
                ):
                    return latest_legacy
                return latest_nested
        # If the nested directory doesn't exist, return the legacy file if found
        elif latest_legacy:
            return latest_legacy

        # Next, look for JSON handoff files anywhere in the directory
        handoff_files = list(current_dir.rglob("*.handoff.json"))
        if handoff_files:
            return max(handoff_files, key=lambda f: f.stat().st_mtime)

        # Finally, fall back to any session-related JSON files
        session_files = list(current_dir.rglob("*.session.json"))
        if session_files:
            return max(session_files, key=lambda f: f.stat().st_mtime)

        return None

    async def _get_previous_session_info(
        self,
        current_dir: Path,
    ) -> dict[str, t.Any] | None:
        """Get previous session information if available. Target complexity: ≤5."""
        session_files = self._discover_session_files(current_dir)

        for file_path in session_files:
            session_info = await self._read_previous_session_info(file_path)
            if session_info:
                return session_info

        # Fallback to old method
        latest_handoff = self._find_latest_handoff_file(current_dir)
        if latest_handoff:
            return await self._read_previous_session_info(latest_handoff)

        return None

    async def analyze_project_context(self, current_dir: Path) -> dict[str, bool]:
        """Analyze project context and return relevant information."""
        # Ensure current_dir is a Path object
        current_dir = Path(current_dir)

        def _safe_any_glob(pattern: str) -> bool:
            try:
                return any(current_dir.glob(pattern))
            except (OSError, PermissionError):
                return False

        # This is a basic implementation; could be expanded based on requirements
        has_git_repo = is_git_repository(
            current_dir
        )  # Use the function from git_operations
        has_readme = _safe_any_glob("README*")
        has_pyproject_toml = (current_dir / "pyproject.toml").is_file()
        has_setup_py = (current_dir / "setup.py").is_file()
        has_requirements_txt = (current_dir / "requirements.txt").is_file()
        has_src_structure = (current_dir / "src").is_dir()
        has_tests = _safe_any_glob("test*") or _safe_any_glob("**/test*")
        has_docs = _safe_any_glob("docs/**") or _safe_any_glob("**/*.md")
        has_ci_cd = (
            (current_dir / ".github").exists()
            or (current_dir / ".gitlab").exists()
            or (current_dir / ".circleci").exists()
        )
        has_venv = (current_dir / ".venv").exists() or (current_dir / "venv").exists()
        has_python_files = _safe_any_glob("**/*.py")

        # Detect commonly used Python web frameworks and libraries
        requirements_content = ""
        with suppress(OSError, PermissionError):
            if (current_dir / "requirements.txt").is_file():
                requirements_content += (current_dir / "requirements.txt").read_text()
        with suppress(OSError, PermissionError):
            if (current_dir / "pyproject.toml").is_file():
                requirements_content += (current_dir / "pyproject.toml").read_text()

        # Scan Python files for framework imports (first 10 files as suggested by test)
        try:
            python_files = list(current_dir.glob("**/*.py"))[:10]
        except (OSError, PermissionError):
            python_files = []
        for py_file in python_files:
            try:
                content = py_file.read_text()
                requirements_content += content  # Add file content to check for imports
            except (OSError, UnicodeDecodeError):
                # Skip files that can't be read
                continue

        uses_fastapi = "fastapi" in requirements_content.lower()
        uses_django = "django" in requirements_content.lower()
        uses_flask = "flask" in requirements_content.lower()

        return {
            "has_git_repo": has_git_repo,
            "has_readme": has_readme,
            "has_pyproject_toml": has_pyproject_toml,
            "has_setup_py": has_setup_py,
            "has_requirements_txt": has_requirements_txt,
            "has_src_structure": has_src_structure,
            "has_tests": has_tests,
            "has_docs": has_docs,
            "has_ci_cd": has_ci_cd,
            "has_venv": has_venv,
            "has_python_files": has_python_files,
            "uses_fastapi": uses_fastapi,
            "uses_django": uses_django,
            "uses_flask": uses_flask,
        }

    async def _generate_handoff_documentation(
        self, summary: dict[str, t.Any], quality_data: dict[str, t.Any]
    ) -> str:
        """Generate handoff documentation based on session summary and quality data."""
        from datetime import datetime

        # Format as markdown document
        markdown_content: list[str] = []
        markdown_content.extend(
            (
                f"# Session Handoff Report - {summary.get('project', 'unknown')}",
                f"\n**Session ended:** {summary.get('session_end_time', datetime.now().isoformat())}",
            )
        )
        markdown_content.extend(
            (
                f"**Final quality score:** {summary.get('final_quality_score', 0)}/100",
                f"**Working directory:** {summary.get('working_directory', 'N/A')}",
                "",
            )
        )

        if summary.get("recommendations"):
            markdown_content.append("## Recommendations")
            for rec in summary["recommendations"]:
                markdown_content.append(f"- {rec}")
            markdown_content.append("")

        # Add quality details
        breakdown = quality_data.get("breakdown", {})
        if breakdown:
            markdown_content.append("## Quality Breakdown")
            for key, value in breakdown.items():
                markdown_content.append(f"- {key}: {value}")
            markdown_content.append("")

        return "\n".join(markdown_content)

    def _save_handoff_documentation(
        self, content: str, current_dir: Path
    ) -> Path | None:
        """Save handoff documentation to a file."""
        from datetime import datetime

        try:
            # Save to .claude/handoff/ directory instead of project root
            handoff_dir = current_dir / ".claude" / "handoff"
            handoff_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            handoff_file = handoff_dir / f"session_handoff_{timestamp}.md"
            handoff_file.write_text(content)
            return handoff_file
        except Exception:
            # Return None on any failure to save
            return None

    async def initialize_session(
        self,
        working_directory: str | None = None,
    ) -> dict[str, t.Any]:
        """Initialize a new session with comprehensive setup."""
        try:
            # Setup directories and project
            current_dir = self._setup_working_directory(working_directory)
            claude_dir = self._setup_claude_directories()

            # Analyze project and assess quality
            project_context = await self.analyze_project_context(current_dir)
            quality_score, quality_data = await self.perform_quality_assessment(
                project_dir=current_dir,
            )

            # Get previous session info
            previous_session_info = await self._get_previous_session_info(current_dir)

            self.logger.info(
                "Session initialized, project=%s, quality_score=%d, working_directory=%s, has_previous_session=%s",
                self.current_project,
                quality_score,
                str(current_dir),
                previous_session_info is not None,
            )

            return {
                "success": True,
                "project": self.current_project,
                "working_directory": str(current_dir),
                "quality_score": quality_score,
                "quality_data": quality_data,
                "project_context": project_context,
                "claude_directory": str(claude_dir),
                "previous_session": previous_session_info,
            }

        except Exception as e:
            self.logger.exception("Session initialization failed: %s", str(e))
            return {"success": False, "error": str(e)}

    def get_previous_quality_score(self, project: str) -> int | None:
        """Get the most recent quality score for a project."""
        scores = self._quality_history.get(project, [])
        return scores[-1] if scores else None

    def record_quality_score(self, project: str, score: int) -> None:
        """Record a quality score for quality trend tracking."""
        if project not in self._quality_history:
            self._quality_history[project] = []
        self._quality_history[project].append(score)
        # Keep only last 10 scores to prevent unbounded growth
        if len(self._quality_history[project]) > 10:
            self._quality_history[project] = self._quality_history[project][-10:]

    async def checkpoint_session(
        self,
        working_directory: str | None = None,
        is_manual: bool = False,
    ) -> dict[str, t.Any]:
        """Perform a comprehensive session checkpoint.

        Args:
            working_directory: Optional working directory override
            is_manual: Whether this is a manually-triggered checkpoint

        Returns:
            Dictionary containing checkpoint results and auto-store decision

        """
        try:
            from session_buddy.core.hooks import HookContext, HookType
            from session_buddy.di import get_sync_typed

            current_dir = Path(working_directory) if working_directory else Path.cwd()
            self.current_project = current_dir.name

            # Generate session ID for this checkpoint
            session_id = (
                f"{self.current_project}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )

            # Execute PRE_CHECKPOINT hooks (quality validation, etc.)
            pre_hooks_results: list[HookResult] = []
            try:
                hooks_manager = get_sync_typed(HooksManager)
                pre_context = HookContext(
                    hook_type=HookType.PRE_CHECKPOINT,
                    session_id=session_id,
                    timestamp=datetime.now(),
                    metadata={
                        "working_directory": str(current_dir),
                        "is_manual": is_manual,
                    },
                )
                pre_hooks_results = await hooks_manager.execute_hooks(
                    HookType.PRE_CHECKPOINT, pre_context
                )
            except Exception as e:
                self.logger.warning("PRE_CHECKPOINT hooks failed: %s", str(e))

            # Quality assessment
            quality_score, quality_data = await self.perform_quality_assessment(
                project_dir=current_dir,
            )

            # Get previous score for trend analysis
            previous_score = self.get_previous_quality_score(self.current_project)

            # Record this score for future comparisons
            self.record_quality_score(self.current_project, quality_score)

            # Determine if reflection should be auto-stored
            from session_buddy.utils.reflection_utils import (
                format_auto_store_summary,
                should_auto_store_checkpoint,
            )

            auto_store_decision = should_auto_store_checkpoint(
                quality_score=quality_score,
                previous_score=previous_score,
                is_manual=is_manual,
                session_phase="checkpoint",
            )

            # Extract and store insights from checkpoint (with deduplication)
            insights_extracted = await self._extract_and_store_insights(
                capture_point="checkpoint"
            )

            # Git checkpoint
            git_output = await self.perform_git_checkpoint(current_dir, quality_score)

            # Execute POST_CHECKPOINT hooks (pattern learning, etc.)
            post_hooks_results = []
            try:
                post_context = HookContext(
                    hook_type=HookType.POST_CHECKPOINT,
                    session_id=session_id,
                    timestamp=datetime.now(),
                    metadata={
                        "quality_score": quality_score,
                        "previous_score": previous_score,
                        "auto_store_decision": auto_store_decision.should_store,
                        "insights_extracted": insights_extracted,
                    },
                    checkpoint_data={
                        "quality_score": quality_score,
                        "quality_data": quality_data,
                        "auto_store_decision": auto_store_decision,
                    },
                )
                post_hooks_results = await hooks_manager.execute_hooks(
                    HookType.POST_CHECKPOINT, post_context
                )
            except Exception as e:
                self.logger.warning("POST_CHECKPOINT hooks failed: %s", str(e))

            # Format results
            quality_output = self.format_quality_results(quality_score, quality_data)

            self.logger.info(
                "Session checkpoint completed, project=%s, quality_score=%d, auto_store_decision=%s, auto_store_reason=%s",
                self.current_project,
                quality_score,
                auto_store_decision.should_store,
                auto_store_decision.reason.value,
            )

            return {
                "success": True,
                "quality_score": quality_score,
                "quality_output": quality_output,
                "git_output": git_output,
                "timestamp": datetime.now().isoformat(),
                "auto_store_decision": auto_store_decision,
                "auto_store_summary": format_auto_store_summary(auto_store_decision),
                "insights_extracted": insights_extracted,
                "pre_hooks_results": pre_hooks_results,
                "post_hooks_results": post_hooks_results,
            }

        except Exception as e:
            self.logger.exception("Session checkpoint failed, error=%s", str(e))
            return {"success": False, "error": str(e)}

    async def _extract_and_store_insights(
        self,
        capture_point: str,
    ) -> int:
        """Extract and store insights with deduplication.

        This is a reusable helper for multi-point capture strategy.
        Extracts insights from session context, filters duplicates using
        session-level hash tracking, and stores unique insights to database.

        Args:
            capture_point: Label for logging (e.g., "checkpoint", "session_end")

        Returns:
            Number of unique insights stored (excluding duplicates)

        """
        insights_extracted = 0

        try:
            # Import settings to check if insight extraction is enabled
            from session_buddy.settings import SessionMgmtSettings

            settings = SessionMgmtSettings()  # Load settings

            if not settings.enable_insight_extraction:
                return 0

            from session_buddy.adapters.reflection_adapter_oneiric import (
                ReflectionDatabase,
            )
            from session_buddy.adapters.settings import ReflectionAdapterSettings
            from session_buddy.insights.extractor import (
                extract_insights_from_context,
                filter_duplicate_insights,
            )

            # Extract insights from session context
            insights = extract_insights_from_context(
                context=self.session_context,
                project=self.current_project,
                min_confidence=settings.insight_extraction_confidence_threshold,
            )

            # Limit to max_per_checkpoint
            insights = insights[: settings.insight_extraction_max_per_checkpoint]

            # Filter out duplicates using session-level tracking
            unique_insights, self._captured_insight_hashes = filter_duplicate_insights(
                insights,
                seen_hashes=self._captured_insight_hashes,
            )

            # Store unique insights to database
            if unique_insights:
                async with ReflectionDatabase(
                    collection_name="default",
                    settings=ReflectionAdapterSettings(
                        database_path=settings.database_path,
                        collection_name="default",
                    ),
                ) as db:
                    for insight in unique_insights:
                        await db.store_insight(
                            content=insight.content,
                            insight_type=insight.insight_type,
                            topics=insight.topics,
                            projects=[self.current_project]
                            if self.current_project
                            else None,
                            source_conversation_id=insight.source_conversation_id,
                            source_reflection_id=insight.source_reflection_id,
                            confidence_score=insight.confidence,
                            quality_score=insight.quality_score,
                        )
                        insights_extracted += 1

            if insights_extracted > 0:
                self.logger.info(
                    "Extracted and stored %d unique insights from %s, project=%s (filtered %d duplicates)",
                    insights_extracted,
                    capture_point,
                    self.current_project,
                    len(insights) - insights_extracted,
                )

        except Exception as e:
            # Don't fail operation if insight extraction fails
            self.logger.warning(
                "Insight extraction failed at %s (continuing), error=%s",
                capture_point,
                str(e),
            )

        return insights_extracted

    async def end_session(
        self,
        working_directory: str | None = None,
    ) -> dict[str, t.Any]:
        """End the current session with cleanup and summary."""
        try:
            from session_buddy.core.hooks import HookContext, HookType
            from session_buddy.di import get_sync_typed

            current_dir = Path(working_directory) if working_directory else Path.cwd()
            self.current_project = current_dir.name

            # Generate session ID for this session end
            session_id = (
                f"{self.current_project}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )

            # Execute PRE_SESSION_END hooks (cleanup preparation, etc.)
            pre_hooks_results = []
            try:
                hooks_manager = get_sync_typed(HooksManager)
                pre_context = HookContext(
                    hook_type=HookType.PRE_SESSION_END,
                    session_id=session_id,
                    timestamp=datetime.now(),
                    metadata={
                        "working_directory": str(current_dir),
                    },
                )
                pre_hooks_results = await hooks_manager.execute_hooks(
                    HookType.PRE_SESSION_END, pre_context
                )
            except Exception as e:
                self.logger.warning("PRE_SESSION_END hooks failed: %s", str(e))

            # Final quality assessment
            quality_score, quality_data = await self.perform_quality_assessment(
                project_dir=current_dir,
            )

            # Extract and store insights from session end (with deduplication)
            # This final capture ensures no insights are missed before cleanup
            insights_extracted = await self._extract_and_store_insights(
                capture_point="session_end"
            )

            # Create session summary
            summary = {
                "project": self.current_project,
                "final_quality_score": quality_score,
                "session_end_time": datetime.now().isoformat(),
                "working_directory": str(current_dir),
                "recommendations": quality_data.get("recommendations", []),
            }

            # Generate handoff documentation
            handoff_content = await self._generate_handoff_documentation(
                summary,
                quality_data,
            )

            # Save handoff documentation
            handoff_path = self._save_handoff_documentation(
                handoff_content,
                current_dir,
            )

            # Execute SESSION_END hooks (final cleanup, notifications, etc.)
            post_hooks_results = []
            try:
                post_context = HookContext(
                    hook_type=HookType.SESSION_END,
                    session_id=session_id,
                    timestamp=datetime.now(),
                    metadata={
                        "quality_score": quality_score,
                        "insights_extracted": insights_extracted,
                        "handoff_path": str(handoff_path) if handoff_path else None,
                    },
                    checkpoint_data={
                        "quality_score": quality_score,
                        "quality_data": quality_data,
                        "handoff_content": handoff_content,
                    },
                )
                post_hooks_results = await hooks_manager.execute_hooks(
                    HookType.SESSION_END, post_context
                )
            except Exception as e:
                self.logger.warning("SESSION_END hooks failed: %s", str(e))

            self.logger.info(
                "Session ended, project=%s, final_quality_score=%d, insights_extracted=%d",
                self.current_project,
                quality_score,
                insights_extracted,
            )

            summary["handoff_documentation"] = (
                str(handoff_path) if handoff_path else None
            )
            summary["insights_extracted"] = insights_extracted

            return {
                "success": True,
                "summary": summary,
                "pre_hooks_results": pre_hooks_results,
                "post_hooks_results": post_hooks_results,
            }

        except Exception as e:
            self.logger.exception("Session end failed, error=%s", str(e))
            return {"success": False, "error": str(e)}

    async def get_session_status(
        self,
        working_directory: str | None = None,
    ) -> dict[str, t.Any]:
        """Get current session status and health information."""
        try:
            current_dir = Path(working_directory) if working_directory else Path.cwd()

            self.current_project = current_dir.name

            # Get comprehensive status
            project_context = await self.analyze_project_context(current_dir)
            quality_score, quality_data = await self.perform_quality_assessment(
                project_dir=current_dir,
            )

            # Check system health
            uv_available = shutil.which("uv") is not None
            git_available = is_git_repository(current_dir)
            claude_dir = Path.home() / ".claude"
            claude_dir_exists = claude_dir.exists()

            return {
                "success": True,
                "project": self.current_project,
                "working_directory": str(current_dir),
                "quality_score": quality_score,
                "quality_breakdown": quality_data["breakdown"],
                "recommendations": quality_data["recommendations"],
                "project_context": project_context,
                "system_health": {
                    "uv_available": uv_available,
                    "git_repository": git_available,
                    "claude_directory": claude_dir_exists,
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.exception("Failed to get session status, error=%s", str(e))
            return {"success": False, "error": str(e)}
