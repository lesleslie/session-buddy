"""Intelligence Engine - Learning and Pattern Recognition System.

This module implements the Intelligence Engine for Session Buddy, which learns
from past development sessions to provide proactive guidance and workflow suggestions.

Key Features:
- Pattern extraction from checkpoints and conversations
- Skill library management with consolidation logic
- Suggestion engine for proactive guidance
- Integration with existing reflection database for semantic search

Architecture:
- IntelligenceEngine: Main orchestrator for learning and suggestions
- LearnedSkill: Data model for consolidated patterns
- Pattern extraction: Analyze conversations, edits, and tool usage
- Skill consolidation: 3+ similar pattern instances → reusable skill
"""

from __future__ import annotations

import json
import logging
import typing as t
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.di import depends

logger = logging.getLogger(__name__)


def safe_json_parse(value: t.Any, expected_type: type) -> t.Any:
    """Safely parse JSON with type checking and error handling.

    Args:
        value: The value to parse (can be dict, list, or JSON string)
        expected_type: The expected type (dict or list)

    Returns:
        Parsed value or empty default if parsing fails
    """
    # Already the right type
    if isinstance(value, expected_type):
        return value

    # Not a string - can't parse
    if not isinstance(value, str):
        logger.warning(f"Unexpected type for JSON parsing: {type(value)}")
        return _get_default_value(expected_type)

    # Size check to prevent DoS
    if len(value) > 1_000_000:  # 1MB limit
        logger.warning("JSON data exceeds size limit")
        return _get_default_value(expected_type)

    try:
        result = json.loads(value)
        return _validate_json_result(result, expected_type)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error(f"JSON decode error: {e}")
        return _get_default_value(expected_type)


def _get_default_value(expected_type: type) -> t.Any:
    """Get default value for a type.

    Args:
        expected_type: The expected type

    Returns:
        Default empty value for the type

    """
    if expected_type in (dict, list):
        return expected_type()
    return None


def _validate_json_result(result: t.Any, expected_type: type) -> t.Any:
    """Validate JSON parse result.

    Args:
        result: Parsed JSON result
        expected_type: Expected type

    Returns:
        Validated result or default value

    """
    # Validate type
    if not isinstance(result, expected_type):
        logger.warning(
            f"JSON parsed but type mismatch: expected {expected_type}, got {type(result)}"
        )
        return _get_default_value(expected_type)

    # Validate structure size
    if isinstance(result, dict) and len(result) > 1000:
        logger.warning("JSON data has too many keys")
        return {}

    if isinstance(result, list) and len(result) > 1000:
        logger.warning("JSON data has too many items")
        return []

    return result


@dataclass(frozen=True, slots=True)
class LearnedSkill:
    """A consolidated skill learned from pattern instances.

    Skills are created when 3+ similar pattern instances are found across
    sessions with high quality scores (>80). They represent reusable
    development patterns that consistently lead to success.
    """

    id: str
    name: str
    description: str
    success_rate: float  # 0.0 to 1.0
    invocations: int  # Number of times used
    pattern: dict[str, t.Any]  # The underlying pattern
    learned_from: list[str]  # Session IDs where pattern was successful
    created_at: datetime
    last_used: datetime | None
    tags: list[str]  # Semantic tags for organization


@dataclass(frozen=True, slots=True)
class PatternInstance:
    """A single pattern instance extracted from a checkpoint.

    Pattern instances are the raw material for skill consolidation.
    They represent specific occurrences of successful patterns in sessions.
    """

    id: str
    session_id: str
    checkpoint_id: str
    pattern_type: str  # "conversation", "edit", "tool_usage", etc.
    context: dict[str, t.Any]  # Session context when pattern occurred
    outcome: dict[str, t.Any]  # What happened (quality improvement, etc.)
    quality_score: float  # Quality checkpoint score
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class WorkflowSuggestion:
    """A proactive workflow improvement suggestion."""

    skill_name: str
    description: str
    success_rate: float
    relevance: float  # 0.0 to 1.0, how relevant to current context
    suggested_actions: list[str]
    rationale: str  # Why this suggestion is being made


class IntelligenceEngine:
    """Learn from experience and provide proactive guidance.

    The Intelligence Engine analyzes past development sessions to:
    1. Extract successful patterns (conversation flows, edit sequences, tool usage)
    2. Consolidate patterns into reusable skills (3+ instances → skill)
    3. Suggest improvements based on current context and past success
    4. Track skill usage and effectiveness over time

    Integration Points:
    - Hooks: POST_CHECKPOINT hook triggers learn_from_checkpoint()
    - MCP Tools: suggest_improvements, invoke_skill, list_skills
    - Reflection DB: Semantic search for similar patterns
    """

    def __init__(self) -> None:
        self.db: ReflectionDatabaseAdapterOneiric | None = None
        self.skill_library: dict[str, LearnedSkill] = {}
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize intelligence system with database connection."""
        if self._initialized:
            return

        # Get reflection database from DI container
        self.db = depends.get_sync(ReflectionDatabaseAdapterOneiric)

        # Create intelligence tables
        await self._ensure_tables()

        # Load existing skills
        await self._load_skill_library()

        self._initialized = True

    async def _ensure_tables(self) -> None:
        """Create intelligence system tables."""
        if not self.db:
            raise RuntimeError(
                "IntelligenceEngine not initialized - call initialize() first"
            )

        # Learned skills table - consolidated reusable patterns
        self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_learned_skills (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL,
                success_rate FLOAT NOT NULL DEFAULT 0.0,
                invocations INTEGER NOT NULL DEFAULT 0,
                pattern JSON NOT NULL,
                learned_from JSON NOT NULL,  -- Array of session IDs
                created_at TIMESTAMP NOT NULL,
                last_used TIMESTAMP,
                tags JSON NOT NULL DEFAULT '[]'
            )
            """
        )

        # Pattern instances table - raw pattern observations
        self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_pattern_instances (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                checkpoint_id TEXT,
                pattern_type TEXT NOT NULL,
                context JSON NOT NULL,
                outcome JSON NOT NULL,
                quality_score FLOAT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create index on pattern_type for faster consolidation queries
        self.db.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pattern_instances_type_quality
            ON intelligence_pattern_instances (pattern_type, quality_score)
            """
        )

        # Cross-project successful patterns table - for Phase 1 pattern capture
        self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_cross_project_patterns (
                id TEXT PRIMARY KEY,
                pattern_type TEXT NOT NULL,
                project_id TEXT,
                context_snapshot JSON NOT NULL,
                solution_snapshot JSON NOT NULL,
                outcome_score FLOAT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                last_applied TIMESTAMP,
                application_count INTEGER NOT NULL DEFAULT 0,
                tags JSON NOT NULL DEFAULT '[]'
            )
            """
        )

        # Pattern applications table - track pattern reuse across projects
        # Note: Foreign key constraint removed to avoid DuckDB constraint issues
        # Referential integrity maintained at application level
        self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_pattern_applications (
                id TEXT PRIMARY KEY,
                pattern_id TEXT NOT NULL,
                applied_to_project TEXT NOT NULL,
                applied_context JSON NOT NULL,
                outcome TEXT NOT NULL,
                feedback TEXT,
                applied_at TIMESTAMP NOT NULL
            )
            """
        )

        # Create indexes for cross-project pattern queries
        self.db.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cross_project_patterns_type_score
            ON intelligence_cross_project_patterns (pattern_type, outcome_score)
            """
        )

        self.db.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pattern_applications_pattern_id
            ON intelligence_pattern_applications (pattern_id)
            """
        )

    async def _load_skill_library(self) -> None:
        """Load learned skills from database into memory."""
        if not self.db:
            return

        results = self.db.conn.execute(
            """
            SELECT id, name, description, success_rate, invocations,
                   pattern, learned_from, created_at, last_used, tags
            FROM intelligence_learned_skills
            ORDER BY success_rate DESC, invocations DESC
            """
        ).fetchall()

        for row in results:
            # DuckDB returns datetime objects directly for TIMESTAMP columns
            # No need to parse with fromisoformat()
            created_at_value = row[7]
            if isinstance(created_at_value, str):
                created_at_value = datetime.fromisoformat(created_at_value)

            last_used_value = row[8]
            if last_used_value:
                if isinstance(last_used_value, str):
                    last_used_value = datetime.fromisoformat(last_used_value)
                # else: already a datetime object

            # DuckDB may auto-deserialize JSON columns to Python objects
            # Check if already deserialized before calling json.loads
            pattern_value = row[5]
            pattern_data = safe_json_parse(pattern_value, dict)

            learned_from_value = row[6]
            learned_from_data = safe_json_parse(learned_from_value, list)

            tags_value = row[9]
            tags_data = safe_json_parse(tags_value, list)

            skill = LearnedSkill(
                id=row[0],
                name=row[1],
                description=row[2],
                success_rate=row[3],
                invocations=row[4],
                pattern=pattern_data,
                learned_from=learned_from_data,
                created_at=created_at_value,
                last_used=last_used_value,
                tags=tags_data,
            )
            self.skill_library[skill.name] = skill

    async def learn_from_checkpoint(self, checkpoint: dict[str, t.Any]) -> list[str]:
        """Extract learnings from a successful checkpoint.

        Args:
            checkpoint: Checkpoint data with quality score, conversation history, etc.

        Returns:
            List of skill IDs created or updated (empty if quality too low)
        """
        if not self._initialized:
            await self.initialize()

        # Only learn from quality checkpoints (adjustable threshold)
        quality_score = checkpoint.get("quality_score", 0)
        if quality_score < 75:
            return []

        # Extract patterns from checkpoint
        patterns = await self._extract_patterns(checkpoint)
        skill_ids = []

        for pattern in patterns:
            # Store pattern instance
            await self._store_pattern_instance(pattern)

            # Check if pattern should consolidate into skill
            skill_id = await self._consolidate_into_skill(pattern)
            if skill_id:
                skill_ids.append(skill_id)

        return skill_ids

    async def _extract_patterns(
        self, checkpoint: dict[str, t.Any]
    ) -> list[dict[str, t.Any]]:
        """Extract actionable patterns from checkpoint.

        Analyzes multiple dimensions of the checkpoint:
        - Conversation patterns (problem-solving sequences)
        - Edit patterns (refactoring sequences)
        - Tool usage patterns (effective workflows)

        Args:
            checkpoint: Checkpoint data with history

        Returns:
            List of extracted pattern dictionaries
        """
        patterns = []
        quality_score = checkpoint.get("quality_score", 0)

        # Analyze conversation history
        conv_pattern = await self._analyze_conversation_patterns(
            checkpoint.get("conversation_history", [])
        )
        if conv_pattern:
            conv_pattern["quality_score"] = quality_score
            patterns.append(conv_pattern)

        # Analyze edit history
        edit_pattern = await self._analyze_edit_patterns(
            checkpoint.get("edit_history", [])
        )
        if edit_pattern:
            edit_pattern["quality_score"] = quality_score
            patterns.append(edit_pattern)

        # Analyze tool usage
        tool_pattern = await self._analyze_tool_patterns(
            checkpoint.get("tool_usage", [])
        )
        if tool_pattern:
            tool_pattern["quality_score"] = quality_score
            patterns.append(tool_pattern)

        return patterns

    async def _analyze_conversation_patterns(
        self, conversation_history: list[dict[str, t.Any]]
    ) -> dict[str, t.Any] | None:
        """Analyze conversation for successful problem-solving patterns.

        Looks for sequences like:
        - "tried X, failed, tried Y, succeeded"
        - "asked question → got answer → implemented solution"
        - "searched past work → found relevant → reused approach"

        Args:
            conversation_history: List of conversation turns

        Returns:
            Pattern dict if successful pattern found, None otherwise
        """
        if not conversation_history or len(conversation_history) < 2:
            return None

        # Pattern 1: Search before implement (reuse pattern)
        search_pattern = self._detect_search_before_implement(conversation_history)
        if search_pattern:
            return {
                "type": "search_before_implement",
                "context": {"pattern": "searched_reflections_then_reused"},
                "outcome": {"pattern": "code_reuse"},
                "tags": ["code_reuse", "search_before_coding"],
                "actions": ["search_reflections", "reuse_solution"],
            }

        # Pattern 2: Iterative problem solving (try, fail, try, succeed)
        iterative_pattern = self._detect_iterative_problem_solving(conversation_history)
        if iterative_pattern:
            return {
                "type": "iterative_problem_solving",
                "context": {"pattern": "multiple_attempts_before_success"},
                "outcome": {"pattern": "persistent_debugging"},
                "tags": ["debugging", "persistence"],
                "actions": ["try_solution", "analyze_failure", "try_alternative"],
            }

        # Pattern 3: Quality checkpoint review pattern
        checkpoint_pattern = self._detect_checkpoint_driven_work(conversation_history)
        if checkpoint_pattern:
            return {
                "type": "checkpoint_driven_development",
                "context": {"pattern": "periodic_quality_checks"},
                "outcome": {"pattern": "maintained_quality"},
                "tags": ["quality_assurance", "checkpointing"],
                "actions": ["periodic_checkpoint", "quality_review"],
            }

        return None

    async def _analyze_edit_patterns(
        self, edit_history: list[dict[str, t.Any]]
    ) -> dict[str, t.Any] | None:
        """Analyze file edits for successful refactoring patterns.

        Looks for sequences like:
        - "added type hints → quality improved"
        - "refactored class → added tests → all pass"
        - "extracted function → simplified logic"

        Args:
            edit_history: List of file edit operations

        Returns:
            Pattern dict if successful pattern found, None otherwise
        """
        if not edit_history or len(edit_history) < 2:
            return None

        # Pattern 1: Type annotation improvements
        if self._detect_type_hypothesis_pattern(edit_history):
            return {
                "type": "type_hypothesis_addition",
                "context": {"pattern": "added_type_annotations"},
                "outcome": {"pattern": "improved_type_safety"},
                "tags": ["type_safety", "documentation"],
                "actions": ["add_type_hints", "verify_compatibility"],
            }

        # Pattern 2: Test-driven refactoring
        if self._detect_test_refactor_pattern(edit_history):
            return {
                "type": "test_driven_refactoring",
                "context": {"pattern": "tests_before_refactor"},
                "outcome": {"pattern": "verified_refactoring"},
                "tags": ["testing", "refactoring"],
                "actions": ["write_tests", "refactor_code", "verify_passing"],
            }

        # Pattern 3: Function extraction simplification
        if self._detect_extraction_pattern(edit_history):
            return {
                "type": "function_extraction",
                "context": {"pattern": "extracted_function"},
                "outcome": {"pattern": "simplified_logic"},
                "tags": ["refactoring", "simplification"],
                "actions": ["extract_function", "verify_behavior"],
            }

        return None

    async def _analyze_tool_patterns(
        self, tool_usage: list[dict[str, t.Any]]
    ) -> dict[str, t.Any] | None:
        """Analyze tool usage for effective workflow patterns.

        Looks for sequences like:
        - "crackerjack lint → fix issues → pytest → all pass"
        - "search_reflections → find relevant → reuse solution"
        - "checkpoint → analyze → improve quality"

        Args:
            tool_usage: List of tool invocations

        Returns:
            Pattern dict if successful pattern found, None otherwise
        """
        if not tool_usage or len(tool_usage) < 2:
            return None

        # Pattern 1: Test-driven quality workflow
        if self._detect_test_driven_quality(tool_usage):
            return {
                "type": "test_driven_quality",
                "context": {"pattern": "lint_then_fix_then_test"},
                "outcome": {"pattern": "quality_assurance"},
                "tags": ["testing", "quality_assurance"],
                "actions": ["run_linter", "fix_issues", "run_tests", "verify_passing"],
            }

        # Pattern 2: Reflection-guided development
        if self._detect_reflection_guided_pattern(tool_usage):
            return {
                "type": "reflection_guided_development",
                "context": {"pattern": "search_then_apply"},
                "outcome": {"pattern": "informed_development"},
                "tags": ["learning", "code_reuse"],
                "actions": ["search_reflections", "apply_pattern", "verify_solution"],
            }

        # Pattern 3: Checkpoint-driven iteration
        if self._detect_checkpoint_iteration_pattern(tool_usage):
            return {
                "type": "checkpoint_iteration",
                "context": {"pattern": "checkpoint_analyze_improve"},
                "outcome": {"pattern": "continuous_improvement"},
                "tags": ["quality", "iteration"],
                "actions": [
                    "create_checkpoint",
                    "analyze_quality",
                    "implement_improvements",
                ],
            }

        return None

    async def _consolidate_into_skill(self, pattern: dict[str, t.Any]) -> str | None:
        """Check if pattern should become a reusable skill.

        Consolidation Logic:
        1. Find similar pattern instances in database
        2. Need at least 3 instances with quality > 80
        3. Average quality must be > 85
        4. Create new skill or update existing

        Args:
            pattern: Pattern to consolidate

        Returns:
            Skill ID if consolidated, None otherwise
        """
        if not self.db:
            return None

        pattern_type = pattern.get("type", "unknown")

        # Find similar pattern instances
        similar_instances = self.db.conn.execute(
            """
            SELECT session_id, quality_score, outcome
            FROM intelligence_pattern_instances
            WHERE pattern_type = ?
              AND quality_score > 80
            ORDER BY quality_score DESC
            """,
            (pattern_type,),
        ).fetchall()

        # Need at least 3 successful instances
        if len(similar_instances) < 3:
            return None

        # Calculate average quality
        avg_quality = sum(row[1] for row in similar_instances) / len(similar_instances)

        if avg_quality < 85:
            return None  # Not consistent enough

        # Generate skill name
        skill_name = self._generate_skill_name(pattern)

        if skill_name in self.skill_library:
            # Update existing skill
            skill = self.skill_library[skill_name]
            # Note: Can't modify frozen dataclass, create new instance
            updated_skill = LearnedSkill(
                id=skill.id,
                name=skill.name,
                description=skill.description,
                success_rate=(skill.success_rate + avg_quality) / 2,
                invocations=skill.invocations + 1,
                pattern=skill.pattern,
                learned_from=[*skill.learned_from, pattern.get("session_id", "")],
                created_at=skill.created_at,
                last_used=skill.last_used,
                tags=skill.tags,
            )
            self.skill_library[skill_name] = updated_skill
            await self._save_skill(updated_skill)
            return updated_skill.id
        else:
            # Create new skill
            skill = LearnedSkill(
                id=f"skill-{uuid.uuid4().hex[:8]}",
                name=skill_name,
                description=self._generate_skill_description(pattern),
                success_rate=avg_quality,
                invocations=1,
                pattern=pattern,
                learned_from=[pattern.get("session_id", "")],
                created_at=datetime.now(UTC),
                last_used=None,
                tags=pattern.get("tags", []),
            )
            self.skill_library[skill_name] = skill
            await self._save_skill(skill)
            return skill.id

    async def _store_pattern_instance(self, pattern: dict[str, t.Any]) -> str:
        """Store pattern instance for later consolidation.

        Args:
            pattern: Pattern to store

        Returns:
            Pattern instance ID
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        pattern_id = f"pattern-{uuid.uuid4().hex[:8]}"

        self.db.conn.execute(
            """
            INSERT INTO intelligence_pattern_instances
            (id, session_id, checkpoint_id, pattern_type, context, outcome,
             quality_score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pattern_id,
                pattern.get("session_id", ""),
                pattern.get("checkpoint_id", ""),
                pattern.get("type", "unknown"),
                json.dumps(pattern.get("context", {})),
                json.dumps(pattern.get("outcome", {})),
                pattern.get("quality_score", 0.0),
                datetime.now(UTC),
            ),
        )

        return pattern_id

    async def _save_skill(self, skill: LearnedSkill) -> None:
        """Persist skill to database.

        Args:
            skill: Skill to save
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        self.db.conn.execute(
            """
            INSERT INTO intelligence_learned_skills
            (id, name, description, success_rate, invocations, pattern,
             learned_from, created_at, last_used, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                success_rate=excluded.success_rate,
                invocations=excluded.invocations,
                pattern=excluded.pattern,
                learned_from=excluded.learned_from,
                created_at=excluded.created_at,
                last_used=excluded.last_used,
                tags=excluded.tags
            """,
            (
                skill.id,
                skill.name,
                skill.description,
                skill.success_rate,
                skill.invocations,
                json.dumps(skill.pattern),
                json.dumps(skill.learned_from),
                skill.created_at.isoformat(),
                skill.last_used.isoformat() if skill.last_used else None,
                json.dumps(skill.tags),
            ),
        )

    def _generate_skill_name(self, pattern: dict[str, t.Any]) -> str:
        """Generate readable skill name from pattern.

        Examples:
        - "refactor_before_feature_implementation"
        - "search_before_implement"
        - "test_after_refactor"

        Args:
            pattern: Pattern to generate name from

        Returns:
            Snake_case skill name
        """
        # TODO: Implement proper skill name generation
        pattern_type = pattern.get("type", "unknown")
        return f"skill_{pattern_type}_{uuid.uuid4().hex[:6]}"

    def _generate_skill_description(self, pattern: dict[str, t.Any]) -> str:
        """Generate human-readable skill description.

        Examples:
        - "Search past work before implementing to avoid duplication"
        - "Add tests after refactoring to verify behavior"

        Args:
            pattern: Pattern to describe

        Returns:
            Human-readable description
        """
        # TODO: Implement proper skill description generation
        return f"Skill learned from {pattern.get('type', 'unknown')} pattern"

    async def suggest_workflow_improvements(
        self, current_session: dict[str, t.Any]
    ) -> list[WorkflowSuggestion]:
        """Suggest workflow improvements based on learned skills.

        Args:
            current_session: Current session context

        Returns:
            List of workflow suggestions, sorted by relevance
        """
        if not self._initialized:
            await self.initialize()

        suggestions = []

        # Extract current context
        current_context = self._extract_context(current_session)

        # Match skills to current context
        for skill in self.skill_library.values():
            if skill.success_rate < 0.8:
                continue  # Only suggest high-confidence skills

            # Calculate relevance to current context
            relevance = self._calculate_relevance(current_context, skill.pattern)

            if relevance > 0.7:
                suggestions.append(
                    WorkflowSuggestion(
                        skill_name=skill.name,
                        description=skill.description,
                        success_rate=skill.success_rate,
                        relevance=relevance,
                        suggested_actions=skill.pattern.get("actions", []),
                        rationale=(
                            f"This pattern has {skill.success_rate:.0%} success rate "
                            f"and was used successfully in {len(skill.learned_from)} sessions."
                        ),
                    )
                )

        # Sort by relevance * success_rate
        suggestions.sort(
            key=lambda s: s.relevance * s.success_rate,
            reverse=True,
        )

        return suggestions[:5]  # Top 5 suggestions

    def _extract_context(self, session: dict[str, t.Any]) -> dict[str, t.Any]:
        """Extract context from current session.

        Args:
            session: Session data

        Returns:
            Context dict with relevant features
        """
        # TODO: Implement proper context extraction
        context = session.get("context", {})
        if isinstance(context, dict):
            return context
        return {}

    def _calculate_relevance(
        self, current_context: dict[str, t.Any], pattern: dict[str, t.Any]
    ) -> float:
        """Calculate how relevant a pattern is to current context.

        Uses:
        - Semantic similarity (embeddings)
        - Tag matching
        - File type matching
        - Project similarity

        Args:
            current_context: Current session context
            pattern: Pattern to evaluate

        Returns:
            Relevance score 0.0 to 1.0
        """
        # TODO: Implement proper relevance calculation
        # For now, use simple tag matching
        current_tags = set(current_context.get("tags", []))
        pattern_tags = set(pattern.get("tags", []))

        if not current_tags or not pattern_tags:
            return 0.5  # Neutral relevance

        # Jaccard similarity
        intersection = len(current_tags & pattern_tags)
        union = len(current_tags | pattern_tags)

        return intersection / union if union > 0 else 0.0

    async def invoke_skill(
        self, skill_name: str, context: dict[str, t.Any]
    ) -> dict[str, t.Any]:
        """Invoke a learned skill.

        Args:
            skill_name: Name of skill to invoke
            context: Current session context

        Returns:
            Invocation result with suggested actions
        """
        if not self._initialized:
            await self.initialize()

        if skill_name not in self.skill_library:
            return {
                "success": False,
                "error": f"Skill '{skill_name}' not found in library",
            }

        skill = self.skill_library[skill_name]

        # Update usage stats (create new instance with updated stats)
        updated_skill = LearnedSkill(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            success_rate=skill.success_rate,
            invocations=skill.invocations + 1,
            pattern=skill.pattern,
            learned_from=skill.learned_from,
            created_at=skill.created_at,
            last_used=datetime.now(UTC),
            tags=skill.tags,
        )
        self.skill_library[skill_name] = updated_skill
        await self._save_skill(updated_skill)

        return {
            "success": True,
            "skill": {
                "name": skill.name,
                "description": skill.description,
                "pattern": skill.pattern,
                "confidence": skill.success_rate,
            },
            "suggested_actions": skill.pattern.get("actions", []),
            "rationale": skill.description,
        }

    async def list_skills(
        self, min_success_rate: float = 0.0, limit: int = 20
    ) -> list[dict[str, t.Any]]:
        """List available skills, optionally filtered by success rate.

        Args:
            min_success_rate: Minimum success rate to include
            limit: Maximum number of skills to return

        Returns:
            List of skill summaries
        """
        if not self._initialized:
            await self.initialize()

        skills = [
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "success_rate": skill.success_rate,
                "invocations": skill.invocations,
                "tags": skill.tags,
                "learned_from_count": len(skill.learned_from),
                "created_at": skill.created_at.isoformat(),
                "last_used": skill.last_used.isoformat() if skill.last_used else None,
            }
            for skill in self.skill_library.values()
            if skill.success_rate >= min_success_rate
        ]

        # Sort by success_rate * invocations
        skills.sort(
            key=lambda s: float(s["success_rate"]) * int(s["invocations"])
            if s["success_rate"] is not None
            and s["invocations"] is not None
            and isinstance(s["success_rate"], (int, float))
            and isinstance(s["invocations"], (int, float))
            else 0.0,
            reverse=True,
        )

        return skills[:limit]

    # ============== Pattern Detection Helpers ==============

    def _detect_search_before_implement(
        self, conversation_history: list[dict[str, t.Any]]
    ) -> bool:
        """Detect pattern: search reflections → reuse solution."""
        has_search = False
        has_implementation = False

        for entry in conversation_history:
            content = entry.get("content", "").lower()
            if "search" in content and ("reflection" in content or "past" in content):
                has_search = True
            if has_search and ("implement" in content or "apply" in content):
                has_implementation = True

        return has_search and has_implementation

    def _detect_iterative_problem_solving(
        self, conversation_history: list[dict[str, t.Any]]
    ) -> bool:
        """Detect pattern: try → fail → try alternative → succeed."""
        attempt_count = 0
        has_success = False

        for entry in conversation_history:
            content = entry.get("content", "").lower()
            if any(word in content for word in ("try", "attempt", "fix")):
                attempt_count += 1
            if any(word in content for word in ("success", "works", "solved")):
                has_success = True

        return attempt_count >= 2 and has_success

    def _detect_checkpoint_driven_work(
        self, conversation_history: list[dict[str, t.Any]]
    ) -> bool:
        """Detect pattern: periodic checkpointing during work."""
        checkpoint_count = sum(
            1
            for entry in conversation_history
            if "checkpoint" in entry.get("content", "").lower()
        )
        return checkpoint_count >= 2

    def _detect_type_hypothesis_pattern(
        self, edit_history: list[dict[str, t.Any]]
    ) -> bool:
        """Detect pattern: added type hints to improve code."""
        for edit in edit_history:
            content = edit.get("content", "").lower()
            if "def " in content and ("->" in content or ": " in content):
                # Check for type annotation additions
                if any(
                    word in content
                    for word in ("str", "int", "bool", "float", "list", "dict")
                ):
                    return True
        return False

    def _detect_test_refactor_pattern(
        self, edit_history: list[dict[str, t.Any]]
    ) -> bool:
        """Detect pattern: added/updated tests alongside refactoring."""
        has_test = False
        has_refactor = False

        for edit in edit_history:
            file_path = edit.get("file_path", "")
            if "test" in file_path.lower():
                has_test = True
            if any(
                word in edit.get("content", "").lower()
                for word in ("refactor", "extract", "simplify")
            ):
                has_refactor = True

        return has_test and has_refactor

    def _detect_extraction_pattern(self, edit_history: list[dict[str, t.Any]]) -> bool:
        """Detect pattern: extracted function to simplify logic."""
        for edit in edit_history:
            content = edit.get("content", "").lower()
            # Look for function extraction patterns
            if "def " in content and any(
                word in content for word in ("extract", "helper", "utility")
            ):
                return True
        return False

    def _detect_test_driven_quality(self, tool_usage: list[dict[str, t.Any]]) -> bool:
        """Detect pattern: lint → fix → test workflow."""
        has_lint = False
        has_test = False

        for invocation in tool_usage:
            tool_name = invocation.get("name", "").lower()
            if "lint" in tool_name:
                has_lint = True
            if "test" in tool_name:
                has_test = True

        return has_lint and has_test

    def _detect_reflection_guided_pattern(
        self, tool_usage: list[dict[str, t.Any]]
    ) -> bool:
        """Detect pattern: search reflections → apply solution."""
        has_search = False
        has_implementation = False

        for invocation in tool_usage:
            tool_name = invocation.get("name", "").lower()
            if "search" in tool_name or "reflection" in tool_name:
                has_search = True
            # After search, look for implementation tools
            if has_search and any(
                word in tool_name for word in ("edit", "write", "create", "implement")
            ):
                has_implementation = True

        return has_search and has_implementation

    def _detect_checkpoint_iteration_pattern(
        self, tool_usage: list[dict[str, t.Any]]
    ) -> bool:
        """Detect pattern: checkpoint → analyze → improve cycle."""
        checkpoint_count = sum(
            1
            for invocation in tool_usage
            if "checkpoint" in invocation.get("name", "").lower()
        )
        return checkpoint_count >= 2

    # ============== Cross-Project Pattern Methods ==============

    async def capture_successful_pattern(
        self,
        pattern_type: str,
        project_id: str,
        context: dict[str, t.Any],
        solution: dict[str, t.Any],
        outcome_score: float,
        tags: list[str] | None = None,
    ) -> str:
        """Capture a successful pattern for cross-project reuse.

        Args:
            pattern_type: Type of pattern (solution, workaround, optimization)
            project_id: Project where pattern was discovered
            context: Problem context (what was the issue)
            solution: Solution applied (how it was fixed)
            outcome_score: Success metric (0.0 to 1.0)
            tags: Optional tags for categorization

        Returns:
            Pattern ID
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        pattern_id = f"pattern-{uuid.uuid4().hex[:8]}"

        self.db.conn.execute(
            """
            INSERT INTO intelligence_cross_project_patterns
            (id, pattern_type, project_id, context_snapshot, solution_snapshot,
             outcome_score, created_at, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pattern_id,
                pattern_type,
                project_id,
                json.dumps(context),
                json.dumps(solution),
                outcome_score,
                datetime.now(UTC),
                json.dumps(tags or []),
            ),
        )

        return pattern_id

    async def search_similar_patterns(
        self,
        current_context: dict[str, t.Any],
        pattern_type: str | None = None,
        threshold: float = 0.75,
        limit: int = 10,
    ) -> list[dict[str, t.Any]]:
        """Search for patterns similar to current context.

        Uses semantic matching and keyword overlap to find relevant patterns.

        Args:
            current_context: Current problem context
            pattern_type: Optional filter by pattern type
            threshold: Minimum similarity score (0.0 to 1.0)
            limit: Maximum number of patterns to return

        Returns:
            List of similar patterns sorted by relevance
        """
        if not self.db:
            await self.initialize()

        # Build query based on parameters
        query = """
            SELECT id, pattern_type, project_id, context_snapshot, solution_snapshot,
                   outcome_score, application_count, tags
            FROM intelligence_cross_project_patterns
        """
        params = []

        if pattern_type:
            query += " WHERE pattern_type = ?"
            params.append(pattern_type)

        query += " ORDER BY outcome_score DESC, application_count DESC"

        if limit:
            query += " LIMIT ?"
            params.append(str(limit))

        if not self.db:
            return []
        results = self.db.conn.execute(query, params).fetchall()

        # Calculate similarity for each pattern
        similar_patterns = []
        for row in results:
            pattern_context = safe_json_parse(row[3], dict)
            similarity = self._calculate_context_similarity(
                current_context, pattern_context
            )

            if similarity >= threshold:
                similar_patterns.append(
                    {
                        "id": row[0],
                        "pattern_type": row[1],
                        "project_id": row[2],
                        "context": safe_json_parse(row[3], dict),
                        "solution": safe_json_parse(row[4], dict),
                        "outcome_score": row[5],
                        "application_count": row[6],
                        "tags": safe_json_parse(row[7], list),
                        "similarity": similarity,
                    }
                )

        # Sort by similarity * outcome_score
        similar_patterns.sort(
            key=lambda p: p["similarity"] * p["outcome_score"],
            reverse=True,
        )

        return similar_patterns

    async def apply_pattern(
        self,
        pattern_id: str,
        applied_to_project: str,
        applied_context: dict[str, t.Any],
    ) -> str:
        """Record pattern application for tracking.

        Args:
            pattern_id: ID of pattern being applied
            applied_to_project: Project where pattern is being applied
            applied_context: Context in which pattern is applied

        Returns:
            Application ID
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        application_id = f"application-{uuid.uuid4().hex[:8]}"

        self.db.conn.execute(
            """
            INSERT INTO intelligence_pattern_applications
            (id, pattern_id, applied_to_project, applied_context, outcome, applied_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                application_id,
                pattern_id,
                applied_to_project,
                json.dumps(applied_context),
                "pending",  # Outcome will be updated later
                datetime.now(UTC),
            ),
        )

        # Update application count in pattern table
        self.db.conn.execute(
            """
            UPDATE intelligence_cross_project_patterns
            SET application_count = application_count + 1,
                last_applied = ?
            WHERE id = ?
            """,
            (datetime.now(UTC), pattern_id),
        )

        return application_id

    async def rate_pattern_outcome(
        self,
        application_id: str,
        outcome: str,
        feedback: str | None = None,
    ) -> None:
        """Rate the outcome of a pattern application.

        Args:
            application_id: ID of pattern application
            outcome: Outcome (success, partial, failure)
            feedback: Optional feedback for learning
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        # Get application details to update pattern score
        application = self.db.conn.execute(
            """
            SELECT pattern_id
            FROM intelligence_pattern_applications
            WHERE id = ?
            """,
            (application_id,),
        ).fetchone()

        if not application:
            raise ValueError(f"Application {application_id} not found")

        pattern_id = application[0]

        # Update application record
        self.db.conn.execute(
            """
            UPDATE intelligence_pattern_applications
            SET outcome = ?, feedback = ?
            WHERE id = ?
            """,
            (outcome, feedback, application_id),
        )

        # Recalculate pattern outcome_score based on applications
        await self._recalculate_pattern_score(pattern_id)

    async def _recalculate_pattern_score(self, pattern_id: str) -> None:
        """Recalculate pattern score based on application outcomes.

        Args:
            pattern_id: ID of pattern to recalculate
        """
        if not self.db:
            return

        # Get all applications for this pattern
        applications = self.db.conn.execute(
            """
            SELECT outcome, COUNT(*) as count
            FROM intelligence_pattern_applications
            WHERE pattern_id = ?
            GROUP BY outcome
            """,
            (pattern_id,),
        ).fetchall()

        # Calculate weighted score
        total_count = sum(row[1] for row in applications)
        if total_count == 0:
            return

        weighted_score = 0.0
        for outcome, count in applications:
            if outcome == "success":
                weighted_score += 1.0 * count
            elif outcome == "partial":
                weighted_score += 0.5 * count
            elif outcome == "failure":
                weighted_score += 0.0 * count

        new_score = weighted_score / total_count

        # Update pattern score (blend with original score)
        self.db.conn.execute(
            """
            UPDATE intelligence_cross_project_patterns
            SET outcome_score = ?
            WHERE id = ?
            """,
            (new_score, pattern_id),
        )

    def _calculate_context_similarity(
        self, context1: dict[str, t.Any], context2: dict[str, t.Any]
    ) -> float:
        """Calculate similarity between two contexts.

        Uses keyword overlap and semantic tags matching.

        Args:
            context1: First context dict
            context2: Second context dict

        Returns:
            Similarity score 0.0 to 1.0
        """
        # Extract keywords from both contexts
        keywords1 = self._extract_keywords(context1)
        keywords2 = self._extract_keywords(context2)

        # Jaccard similarity
        intersection = len(set(keywords1) & set(keywords2))
        union = len(set(keywords1) | set(keywords2))

        if union == 0:
            return 0.0

        return intersection / union

    def _extract_keywords(self, context: dict[str, t.Any]) -> list[str]:
        """Extract keywords from context for similarity matching.

        Args:
            context: Context dict

        Returns:
            List of keywords
        """
        keywords = []

        # Common stop words to filter out
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "what",
            "which",
            "who",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "every",
            "both",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "also",
            "now",
            "here",
            "there",
            "then",
            "once",
            "about",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "up",
            "down",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "their",
            "your",
            "our",
            "its",
            "him",
            "her",
            "us",
            "them",
            "his",
            "hers",
            "ours",
            "yours",
            "mine",
            "yours",
            "hers",
        }

        # Extract keywords from dict values only (not keys)
        for value in context.values():
            if isinstance(value, str):
                # Split on common delimiters
                words = value.lower().split()
                keywords.extend(words)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        keywords.extend(item.lower().split())
            elif isinstance(value, dict):
                keywords.extend(self._extract_keywords(value))

        # Filter out stop words and short words
        keywords = [k for k in keywords if k not in stop_words and len(k) > 2]

        return keywords
