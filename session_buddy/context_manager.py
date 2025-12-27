#!/usr/bin/env python3
"""Auto-Context Loading for Session Management MCP Server.

Automatically detects current development context and loads relevant conversations.
"""

import hashlib
import json
import operator
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .reflection_tools import ReflectionDatabase
from .utils.git_operations import get_worktree_info, list_worktrees


class ContextDetector:
    """Detects current development context from environment and files."""

    def __init__(self) -> None:
        self.context_indicators = {
            "git": [".git", ".gitignore", ".github"],
            "python": ["pyproject.toml", "setup.py", "requirements.txt", "*.py"],
            "javascript": ["package.json", "node_modules", "*.js", "*.ts"],
            "rust": ["Cargo.toml", "Cargo.lock", "*.rs"],
            "go": ["go.mod", "go.sum", "*.go"],
            "java": ["pom.xml", "build.gradle", "*.java"],
            "docker": ["Dockerfile", "docker-compose.yml", ".dockerignore"],
            "web": ["index.html", "*.css", "*.scss"],
            "testing": ["tests/", "test/", "*test*", "pytest.ini"],
            "documentation": ["README.md", "docs/", "*.md"],
            "config": [".env", ".envrc", "config/", "*.ini", "*.yaml", "*.yml"],
        }

        self.project_types = {
            "mcp_server": ["mcp.json", ".mcp.json", "fastmcp"],
            "api": ["api/", "routes/", "endpoints/"],
            "web_app": ["templates/", "static/", "public/"],
            "cli_tool": ["cli/", "commands/", "__main__.py"],
            "library": ["src/", "lib/", "__init__.py"],
            "data_science": ["*.ipynb", "data/", "notebooks/"],
            "ml_project": ["model/", "models/", "training/", "*.pkl"],
            "devops": ["terraform/", "ansible/", "k8s/", "kubernetes/"],
        }

    def _initialize_context(self, working_path: Path) -> dict[str, Any]:
        """Initialize basic context structure."""
        return {
            "working_directory": str(working_path),
            "project_name": working_path.name,
            "detected_languages": [],
            "detected_tools": [],
            "project_type": None,
            "current_files": [],
            "recent_files": [],
            "git_info": {},
            "worktree_info": None,
            "confidence_score": 0.0,
        }

    def _find_indicators(self, working_path: Path, indicators: list[str]) -> list[str]:
        """Find matching indicators in the working directory."""
        found_indicators = []

        for indicator in indicators:
            if indicator.startswith("*"):
                # Glob pattern
                matches = list(working_path.glob(indicator))
                if matches:
                    found_indicators.extend([m.name for m in matches[:3]])  # Limit to 3
            elif indicator.endswith("/"):
                # Directory
                if (working_path / indicator.rstrip("/")).exists():
                    found_indicators.append(indicator)
            # File
            elif (working_path / indicator).exists():
                found_indicators.append(indicator)

        return found_indicators

    def _detect_languages_and_tools(
        self,
        working_path: Path,
        context: dict[str, Any],
    ) -> None:
        """Detect programming languages and development tools."""
        for category, indicators in self.context_indicators.items():
            found_indicators = self._find_indicators(working_path, indicators)

            if found_indicators:
                if category in {"python", "javascript", "rust", "go", "java"}:
                    context["detected_languages"].append(category)
                else:
                    context["detected_tools"].append(category)
                context["confidence_score"] += 0.1

    def _calculate_project_type_score(
        self,
        working_path: Path,
        indicators: list[str],
    ) -> float:
        """Calculate score for a specific project type."""
        type_score = 0.0

        for indicator in indicators:
            if indicator.startswith("*"):
                if list(working_path.glob(indicator)):
                    type_score += 1
            elif indicator.endswith("/"):
                if (working_path / indicator.rstrip("/")).exists():
                    type_score += 1
            elif (working_path / indicator).exists():
                type_score += 1
            elif indicator in str(working_path):  # Check if it's in path name
                type_score += 0.5

        return type_score

    def _detect_project_type(self, working_path: Path, context: dict[str, Any]) -> None:
        """Detect the type of project."""
        best_score = 0.0

        for proj_type, indicators in self.project_types.items():
            type_score = self._calculate_project_type_score(working_path, indicators)

            if type_score > best_score:
                context["project_type"] = proj_type
                best_score = type_score

    def _get_recent_files(self, working_path: Path) -> list[dict[str, Any]]:
        """Get recently modified files."""
        recent_files = []

        try:
            recent_threshold = datetime.now() - timedelta(hours=2)

            for file_path in working_path.rglob("*"):
                if file_path.is_file() and not self._should_ignore_file(file_path):
                    mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)

                    if mod_time > recent_threshold:
                        recent_files.append(
                            {
                                "path": str(file_path.relative_to(working_path)),
                                "modified": mod_time.isoformat(),
                                "size": file_path.stat().st_size,
                            },
                        )

            # Sort by modification time and return top 10
            recent_files.sort(key=lambda x: str(x["modified"]), reverse=True)
            return recent_files[:10]

        except (OSError, PermissionError):
            return []

    def detect_current_context(self, working_dir: str | None = None) -> dict[str, Any]:
        """Detect current development context."""
        working_path = self._resolve_working_path(working_dir)
        context = self._initialize_context(working_path)

        self._gather_project_context(working_path, context)
        self._gather_git_context(working_path, context)

        return context

    def _resolve_working_path(self, working_dir: str | None) -> Path:
        """Resolve the working directory path."""
        if not working_dir:
            try:
                cwd = Path.cwd()
            except FileNotFoundError:
                cwd = Path.home()
            working_dir = os.environ.get("PWD", str(cwd))
        return Path(working_dir) if working_dir else Path.home()

    def _gather_project_context(
        self,
        working_path: Path,
        context: dict[str, Any],
    ) -> None:
        """Gather project-specific context information."""
        self._detect_languages_and_tools(working_path, context)
        self._detect_project_type(working_path, context)
        context["recent_files"] = self._get_recent_files(working_path)

    def _gather_git_context(self, working_path: Path, context: dict[str, Any]) -> None:
        """Gather Git and worktree context information."""
        context["git_info"] = self._get_git_info(working_path)
        self._add_worktree_context(working_path, context)

    def _add_worktree_context(
        self,
        working_path: Path,
        context: dict[str, Any],
    ) -> None:
        """Add worktree information to context."""
        worktree_info = get_worktree_info(working_path)
        if worktree_info:
            context["worktree_info"] = self._format_worktree_info(worktree_info)
            context["all_worktrees"] = self._get_all_worktrees_info(
                working_path,
                worktree_info,
            )

    def _format_worktree_info(self, worktree_info: Any) -> dict[str, Any]:
        """Format worktree information for context."""
        return {
            "path": str(worktree_info.path),
            "branch": worktree_info.branch,
            "is_main_worktree": worktree_info.is_main_worktree,
            "is_detached": worktree_info.is_detached,
            "is_bare": worktree_info.is_bare,
            "locked": worktree_info.locked,
            "prunable": worktree_info.prunable,
        }

    def _get_all_worktrees_info(
        self,
        working_path: Path,
        current_worktree: Any,
    ) -> list[dict[str, Any]]:
        """Get information about all worktrees."""
        all_worktrees = list_worktrees(working_path)
        return [
            {
                "path": str(wt.path),
                "branch": wt.branch,
                "is_main": wt.is_main_worktree,
                "is_current": wt.path == current_worktree.path,
            }
            for wt in all_worktrees
        ]

    def _should_ignore_file(self, file_path: Path) -> bool:
        """Check if file should be ignored."""
        ignore_patterns = {
            ".git",
            ".venv",
            "__pycache__",
            "node_modules",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "dist",
            "build",
            ".DS_Store",
        }

        # Check if any part of the path matches ignore patterns
        for part in file_path.parts:
            if part in ignore_patterns or (part.startswith(".") and len(part) > 4):
                return True

        # Check file extensions to ignore
        ignore_extensions = {".pyc", ".pyo", ".log", ".tmp", ".cache"}
        return file_path.suffix in ignore_extensions

    def _get_git_info(self, working_path: Path) -> dict[str, Any]:
        """Get git repository information."""
        git_dir = working_path / ".git"
        if not git_dir.exists():
            return {}

        from contextlib import suppress

        git_info: dict[str, Any] = {}
        with suppress(OSError, PermissionError):
            self._extract_branch_info(git_dir, git_info, working_path)
            self._extract_platform_info(git_dir, git_info)
            git_info["is_git_repo"] = "True"

        return git_info

    def _extract_branch_info(
        self,
        git_dir: Path,
        git_info: dict[str, Any],
        working_path: Path,
    ) -> None:
        """Extract git branch information using worktree-aware detection."""
        worktree_info = get_worktree_info(working_path)
        if worktree_info:
            self._populate_worktree_info(git_info, worktree_info)
        else:
            self._fallback_branch_detection(git_dir, git_info)

    def _populate_worktree_info(
        self,
        git_info: dict[str, Any],
        worktree_info: Any,
    ) -> None:
        """Populate git info from worktree information."""
        git_info["current_branch"] = worktree_info.branch
        git_info["is_worktree"] = str(not worktree_info.is_main_worktree)
        git_info["is_detached"] = str(worktree_info.is_detached)
        git_info["worktree_path"] = str(worktree_info.path)

    def _fallback_branch_detection(
        self,
        git_dir: Path,
        git_info: dict[str, Any],
    ) -> None:
        """Fallback method for branch detection when worktree info unavailable."""
        head_file = git_dir / "HEAD"
        if not head_file.exists():
            return

        head_content = head_file.read_text().strip()
        if head_content.startswith("ref: refs/heads/"):
            git_info["current_branch"] = head_content.split("/")[-1]

    def _extract_platform_info(self, git_dir: Path, git_info: dict[str, Any]) -> None:
        """Extract git platform information from config."""
        config_file = git_dir / "config"
        if not config_file.exists():
            return

        config_content = config_file.read_text()
        git_info["platform"] = self._determine_git_platform(config_content)

    def _determine_git_platform(self, config_content: str) -> str:
        """Determine git platform from config content."""
        if "github.com" in config_content:
            return "github"
        if "gitlab.com" in config_content:
            return "gitlab"
        return "git"


class RelevanceScorer:
    """Scores conversation relevance based on context."""

    def __init__(self) -> None:
        self.scoring_weights = {
            "project_name_match": 0.3,
            "language_match": 0.2,
            "tool_match": 0.15,
            "file_match": 0.15,
            "recency": 0.1,
            "keyword_match": 0.1,
        }

    def _score_project_match(
        self,
        conv_content: str,
        conv_project: str,
        context: dict[str, Any],
    ) -> float:
        """Score based on project name matching."""
        current_project = context["project_name"].lower()
        if current_project in conv_project or current_project in conv_content:
            return self.scoring_weights["project_name_match"]
        return 0.0

    def _score_language_match(
        self,
        conv_content: str,
        context: dict[str, Any],
    ) -> float:
        """Score based on programming language matching."""
        score = 0.0
        for lang in context["detected_languages"]:
            if lang in conv_content:
                score += self.scoring_weights["language_match"] / len(
                    context["detected_languages"],
                )
        return score

    def _score_tool_match(self, conv_content: str, context: dict[str, Any]) -> float:
        """Score based on development tool matching."""
        score = 0.0
        for tool in context["detected_tools"]:
            if tool in conv_content:
                score += self.scoring_weights["tool_match"] / len(
                    context["detected_tools"],
                )
        return score

    def _score_file_match(self, conv_content: str, context: dict[str, Any]) -> float:
        """Score based on file name matching."""
        score = 0.0
        for file_info in context["recent_files"]:
            file_name = Path(file_info["path"]).name.lower()
            if file_name in conv_content:
                score += self.scoring_weights["file_match"] / len(
                    context["recent_files"],
                )
        return score

    def _score_recency(self, conversation: dict[str, Any]) -> float:
        """Score based on conversation recency."""
        from contextlib import suppress

        with suppress(ValueError, TypeError):
            conv_time = datetime.fromisoformat(conversation.get("timestamp", ""))
            time_diff = datetime.now() - conv_time
            if time_diff.days == 0:
                return self.scoring_weights["recency"]
            if time_diff.days <= 7:
                return self.scoring_weights["recency"] * 0.5
        return 0.0

    def _get_project_keywords(self) -> dict[str, list[str]]:
        """Get project type keyword mappings."""
        return {
            "mcp_server": ["mcp", "server", "fastmcp", "protocol"],
            "api": ["api", "endpoint", "route", "request", "response"],
            "web_app": ["web", "app", "frontend", "backend", "html", "css"],
            "cli_tool": ["cli", "command", "argument", "terminal"],
            "library": ["library", "package", "module", "import"],
            "data_science": ["data", "analysis", "pandas", "numpy", "jupyter"],
            "ml_project": ["machine learning", "model", "training", "neural"],
            "devops": ["deploy", "infrastructure", "docker", "kubernetes"],
        }

    def _score_project_keywords(
        self,
        conv_content: str,
        context: dict[str, Any],
    ) -> float:
        """Score based on project type keywords."""
        if not context.get("project_type"):
            return 0.0

        project_keywords = self._get_project_keywords()
        keywords = project_keywords.get(context["project_type"], [])

        score = 0.0
        for keyword in keywords:
            if keyword in conv_content:
                score += self.scoring_weights["keyword_match"] / len(keywords)

        return score

    def score_conversation_relevance(
        self,
        conversation: dict[str, Any],
        context: dict[str, Any],
    ) -> float:
        """Score how relevant a conversation is to current context."""
        conv_content = conversation.get("content", "").lower()
        conv_project = conversation.get("project", "").lower()

        score = 0.0
        score += self._score_project_match(conv_content, conv_project, context)
        score += self._score_language_match(conv_content, context)
        score += self._score_tool_match(conv_content, context)
        score += self._score_file_match(conv_content, context)
        score += self._score_recency(conversation)
        score += self._score_project_keywords(conv_content, context)

        return min(score, 1.0)  # Cap at 1.0


class AutoContextLoader:
    """Main class for automatic context loading."""

    def __init__(self, reflection_db: ReflectionDatabase) -> None:
        self.reflection_db = reflection_db
        self.context_detector = ContextDetector()
        self.relevance_scorer = RelevanceScorer()
        self.cache: dict[str, Any] = {}
        self.cache_timeout = 300  # 5 minutes

    async def load_relevant_context(
        self,
        working_dir: str | None = None,
        max_conversations: int = 10,
        min_relevance: float = 0.3,
    ) -> dict[str, Any]:
        """Load relevant conversations based on current context."""
        # Detect current context
        current_context = self.context_detector.detect_current_context(working_dir)

        # Generate cache key based on context
        context_hash = self._generate_context_hash(current_context)

        # Check cache
        if context_hash in self.cache:
            cached_time, cached_result = self.cache[context_hash]
            if datetime.now() - cached_time < timedelta(seconds=self.cache_timeout):
                return cached_result  # type: ignore[no-any-return]

        # Get all conversations from database
        relevant_conversations = []

        if hasattr(self.reflection_db, "conn") and self.reflection_db.conn:
            cursor = self.reflection_db.conn.execute(
                "SELECT id, content, project, timestamp, metadata FROM conversations",
            )
            conversations = cursor.fetchall()

            for conv in conversations:
                conv_id, content, project, timestamp, metadata = conv

                conversation_data = {
                    "id": conv_id,
                    "content": content,
                    "project": project,
                    "timestamp": timestamp,
                    "metadata": json.loads(metadata) if metadata else {},
                }

                # Score relevance
                relevance = self.relevance_scorer.score_conversation_relevance(
                    conversation_data,
                    current_context,
                )

                if relevance >= min_relevance:
                    conversation_data["relevance_score"] = relevance
                    relevant_conversations.append(conversation_data)

        # Sort by relevance and limit results
        relevant_conversations.sort(
            key=operator.itemgetter("relevance_score"), reverse=True
        )
        top_conversations = relevant_conversations[:max_conversations]

        result = {
            "context": current_context,
            "relevant_conversations": top_conversations,
            "total_found": len(relevant_conversations),
            "loaded_count": len(top_conversations),
            "min_relevance_threshold": min_relevance,
        }

        # Cache result
        self.cache[context_hash] = (datetime.now(), result)

        return result

    def _generate_context_hash(self, context: dict[str, Any]) -> str:
        """Generate hash for context caching."""
        # Use key context elements for hashing
        hash_data = {
            "project_name": context["project_name"],
            "detected_languages": sorted(context["detected_languages"]),
            "detected_tools": sorted(context["detected_tools"]),
            "project_type": context.get("project_type"),
            "working_directory": context["working_directory"],
        }

        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.md5(hash_string.encode(), usedforsecurity=False).hexdigest()[:12]

    async def get_context_summary(self, working_dir: str | None = None) -> str:
        """Get a human-readable summary of current context."""
        context = self.context_detector.detect_current_context(working_dir)

        summary_parts = []
        summary_parts.extend(
            (
                f"📁 Project: {context['project_name']}",
                f"📂 Directory: {context['working_directory']}",
            )
        )

        if context["detected_languages"]:
            langs = ", ".join(context["detected_languages"])
            summary_parts.append(f"💻 Languages: {langs}")

        if context["detected_tools"]:
            tools = ", ".join(context["detected_tools"])
            summary_parts.append(f"🔧 Tools: {tools}")

        if context["project_type"]:
            summary_parts.append(
                f"📋 Type: {context['project_type'].replace('_', ' ').title()}",
            )

        if context["git_info"].get("is_git_repo"):
            git_info = context["git_info"]
            branch = git_info.get("current_branch", "unknown")
            platform = git_info.get("platform", "git")
            summary_parts.append(f"🌿 Git: {branch} branch on {platform}")

        if context["recent_files"]:
            count = len(context["recent_files"])
            summary_parts.append(f"📄 Recent files: {count} modified in last 2 hours")

        confidence = context["confidence_score"] * 100
        summary_parts.append(f"🎯 Detection confidence: {confidence:.0f}%")

        return "\n".join(summary_parts)
