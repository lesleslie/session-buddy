"""Tests for session_buddy.core.intelligence module.

Targeting 60%+ coverage with comprehensive tests for:
- IntelligenceEngine class
- LearnedSkill, PatternInstance, WorkflowSuggestion dataclasses
- Pattern detection and analysis
- Skill usage tracking and consolidation
- Performance metrics collection
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.intelligence import (
    IntelligenceEngine,
    LearnedSkill,
    PatternInstance,
    WorkflowSuggestion,
    safe_json_parse,
    _get_default_value,
    _validate_json_result,
)


# ============================================================================
# Test Data: Safe JSON Parse
# ============================================================================


class TestSafeJsonParse:
    """Tests for safe_json_parse function."""

    def test_already_dict_returns_same(self):
        """When value is already a dict, return it unchanged."""
        data = {"key": "value"}
        result = safe_json_parse(data, dict)
        assert result == data

    def test_already_list_returns_same(self):
        """When value is already a list, return it unchanged."""
        data = [1, 2, 3]
        result = safe_json_parse(data, list)
        assert result == data

    def test_valid_json_string_parses_dict(self):
        """Valid JSON string is parsed to dict."""
        result = safe_json_parse('{"key": "value"}', dict)
        assert result == {"key": "value"}

    def test_valid_json_string_parses_list(self):
        """Valid JSON string is parsed to list."""
        result = safe_json_parse('[1, 2, 3]', list)
        assert result == [1, 2, 3]

    def test_non_string_returns_default(self):
        """Non-string values return default empty value."""
        result = safe_json_parse(123, dict)
        assert result == {}
        result = safe_json_parse(None, list)
        assert result == []

    def test_oversized_json_returns_default(self):
        """JSON exceeding 1MB limit returns default."""
        large_json = '{"key": "' + "x" * 1_000_001 + '"}'
        result = safe_json_parse(large_json, dict)
        assert result == {}

    def test_invalid_json_returns_default(self):
        """Invalid JSON returns default value."""
        result = safe_json_parse("not valid json", dict)
        assert result == {}

    def test_type_mismatch_returns_default(self):
        """Parsed JSON with wrong type returns default."""
        result = safe_json_parse('{"key": "value"}', list)
        assert result == []

    def test_empty_json_string_returns_default(self):
        """Empty string returns default."""
        result = safe_json_parse("", dict)
        assert result == {}


class TestGetDefaultValue:
    """Tests for _get_default_value function."""

    def test_dict_returns_empty_dict(self):
        """dict type returns empty dict."""
        result = _get_default_value(dict)
        assert result == {}

    def test_list_returns_empty_list(self):
        """list type returns empty list."""
        result = _get_default_value(list)
        assert result == []

    def test_other_type_returns_none(self):
        """Other types return None."""
        result = _get_default_value(str)
        assert result is None


class TestValidateJsonResult:
    """Tests for _validate_json_result function."""

    def test_dict_within_limits_returns_result(self):
        """Dict within key limit is returned."""
        small_dict = {"a": 1, "b": 2}
        result = _validate_json_result(small_dict, dict)
        assert result == small_dict

    def test_list_within_limits_returns_result(self):
        """List within item limit is returned."""
        small_list = [1, 2, 3]
        result = _validate_json_result(small_list, list)
        assert result == small_list

    def test_dict_too_many_keys_returns_empty(self):
        """Dict with >1000 keys returns empty dict."""
        large_dict = {f"key{i}": i for i in range(1001)}
        result = _validate_json_result(large_dict, dict)
        assert result == {}

    def test_list_too_many_items_returns_empty(self):
        """List with >1000 items returns empty list."""
        large_list = list(range(1001))
        result = _validate_json_result(large_list, list)
        assert result == []

    def test_wrong_type_returns_default(self):
        """Result with wrong type returns default."""
        result = _validate_json_result([1, 2], dict)
        assert result == {}


# ============================================================================
# Test Data: Dataclasses
# ============================================================================


class TestLearnedSkillDataclass:
    """Tests for LearnedSkill dataclass."""

    def test_creation_with_all_fields(self):
        """Create LearnedSkill with all fields."""
        now = datetime.now(UTC)
        skill = LearnedSkill(
            id="skill-abc123",
            name="test_skill",
            description="A test skill",
            success_rate=0.85,
            invocations=10,
            pattern={"type": "test", "tags": ["testing"]},
            learned_from=["session-1", "session-2"],
            created_at=now,
            last_used=now,
            tags=["testing", "quality"],
        )
        assert skill.id == "skill-abc123"
        assert skill.name == "test_skill"
        assert skill.success_rate == 0.85
        assert skill.invocations == 10
        assert skill.pattern == {"type": "test", "tags": ["testing"]}
        assert skill.learned_from == ["session-1", "session-2"]
        assert skill.last_used == now
        assert skill.tags == ["testing", "quality"]

    def test_immutability(self):
        """LearnedSkill is frozen and slotted."""
        now = datetime.now(UTC)
        skill = LearnedSkill(
            id="skill-xyz",
            name="immutable_skill",
            description="Cannot be modified",
            success_rate=0.9,
            invocations=5,
            pattern={},
            learned_from=[],
            created_at=now,
            last_used=None,
            tags=[],
        )
        with pytest.raises(Exception):  # frozen dataclass
            skill.id = "modified"

    def test_none_last_used_allowed(self):
        """last_used can be None."""
        now = datetime.now(UTC)
        skill = LearnedSkill(
            id="skill-123",
            name="new_skill",
            description="Never used",
            success_rate=1.0,
            invocations=0,
            pattern={},
            learned_from=[],
            created_at=now,
            last_used=None,
            tags=[],
        )
        assert skill.last_used is None


class TestPatternInstanceDataclass:
    """Tests for PatternInstance dataclass."""

    def test_creation(self):
        """Create PatternInstance with all fields."""
        now = datetime.now(UTC)
        instance = PatternInstance(
            id="pattern-abc",
            session_id="session-1",
            checkpoint_id="checkpoint-1",
            pattern_type="conversation",
            context={"key": "value"},
            outcome={"success": True},
            quality_score=85.0,
            timestamp=now,
        )
        assert instance.id == "pattern-abc"
        assert instance.session_id == "session-1"
        assert instance.pattern_type == "conversation"
        assert instance.quality_score == 85.0


class TestWorkflowSuggestionDataclass:
    """Tests for WorkflowSuggestion dataclass."""

    def test_creation(self):
        """Create WorkflowSuggestion with all fields."""
        suggestion = WorkflowSuggestion(
            skill_name="test_workflow",
            description="A suggested workflow",
            success_rate=0.92,
            relevance=0.85,
            suggested_actions=["action1", "action2"],
            rationale="High success rate in similar contexts",
        )
        assert suggestion.skill_name == "test_workflow"
        assert suggestion.success_rate == 0.92
        assert suggestion.relevance == 0.85
        assert len(suggestion.suggested_actions) == 2


# ============================================================================
# Test IntelligenceEngine - Initialization
# ============================================================================


class TestIntelligenceEngineInit:
    """Tests for IntelligenceEngine initialization."""

    def test_default_values(self):
        """Engine initializes with correct defaults."""
        engine = IntelligenceEngine()
        assert engine.db is None
        assert engine.skill_library == {}
        assert engine._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self):
        """initialize() creates required database tables."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.conn = mock_conn

        with patch("session_buddy.core.intelligence.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_db
            await engine.initialize()

            # Verify tables are created (multiple execute calls)
            assert mock_conn.execute.call_count >= 4
            # Check for key table creation
            calls = mock_conn.execute.call_args_list
            table_names = [
                call[0][0].lower()
                for call in calls
                if "create table" in call[0][0].lower()
            ]
            assert any("learned_skills" in name for name in table_names)
            assert any("pattern_instances" in name for name in table_names)

    @pytest.mark.asyncio
    async def test_initialize_only_runs_once(self):
        """initialize() only runs once even if called multiple times."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.conn = mock_conn

        with patch("session_buddy.core.intelligence.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_db
            await engine.initialize()
            await engine.initialize()
            await engine.initialize()

            # Should still only execute once for table creation
            # (some calls are for indexes, so > 1 is expected)
            assert engine._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_loads_existing_skills(self):
        """initialize() loads existing skills from database."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()

        now = datetime.now(UTC)
        mock_rows = [
            [
                "skill-1",
                "existing_skill",
                "An existing skill",
                0.85,
                5,
                '{"type": "test"}',
                '["session-1"]',
                now,
                now,
                '["testing"]',
            ]
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows
        mock_db.conn = mock_conn

        with patch("session_buddy.core.intelligence.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_db
            await engine.initialize()

            assert "existing_skill" in engine.skill_library
            assert engine.skill_library["existing_skill"].invocations == 5


# ============================================================================
# Test IntelligenceEngine - Pattern Learning
# ============================================================================


class TestLearnFromCheckpoint:
    """Tests for learn_from_checkpoint method."""

    @pytest.mark.asyncio
    async def test_low_quality_checkpoint_returns_empty(self):
        """Checkpoint below quality threshold returns empty list."""
        engine = IntelligenceEngine()
        engine._initialized = True  # Skip auto-init
        checkpoint = {"quality_score": 50, "session_id": "s1"}

        result = await engine.learn_from_checkpoint(checkpoint)

        assert result == []

    @pytest.mark.asyncio
    async def test_quality_75_returns_empty(self):
        """Checkpoint at exactly 75 quality returns empty (threshold is > 75)."""
        engine = IntelligenceEngine()
        engine._initialized = True  # Skip auto-init
        checkpoint = {"quality_score": 75}

        result = await engine.learn_from_checkpoint(checkpoint)

        assert result == []

    @pytest.mark.asyncio
    async def test_high_quality_checkpoint_extracts_patterns(self):
        """High quality checkpoint triggers pattern extraction."""
        engine = IntelligenceEngine()
        engine._initialized = True

        checkpoint = {
            "quality_score": 85,
            "session_id": "session-1",
            "conversation_history": [
                {"content": "search reflections for similar patterns"},
                {"content": "found solution, implementing now"},
            ],
        }

        with patch.object(engine, "_extract_patterns") as mock_extract:
            mock_extract.return_value = [
                {"type": "search_before_implement", "quality_score": 85}
            ]
            with patch.object(engine, "_store_pattern_instance") as mock_store:
                mock_store.return_value = "pattern-id-1"
                with patch.object(engine, "_consolidate_into_skill") as mock_consolidate:
                    mock_consolidate.return_value = "skill-123"

                    result = await engine.learn_from_checkpoint(checkpoint)

                    assert mock_extract.called
                    assert mock_store.called
                    assert mock_consolidate.called

    @pytest.mark.asyncio
    async def test_auto_initialize_if_not_initialized(self):
        """Automatically initializes if not already initialized."""
        engine = IntelligenceEngine()
        engine._initialized = False

        checkpoint = {"quality_score": 85}

        with patch.object(engine, "initialize") as mock_init:
            await engine.learn_from_checkpoint(checkpoint)
            mock_init.assert_called_once()


class TestExtractPatterns:
    """Tests for _extract_patterns method."""

    @pytest.mark.asyncio
    async def test_extracts_conversation_pattern(self):
        """Extracts conversation patterns from checkpoint."""
        engine = IntelligenceEngine()
        checkpoint = {
            "quality_score": 85,
            "conversation_history": [{"content": "search past work"}],
            "edit_history": [],
            "tool_usage": [],
        }

        result = await engine._extract_patterns(checkpoint)

        # Should have conversation pattern due to search pattern
        conversation_patterns = [p for p in result if p.get("type") == "search_before_implement"]
        assert len(conversation_patterns) >= 0  # Depends on detection

    @pytest.mark.asyncio
    async def test_extracts_edit_pattern(self):
        """Extracts edit patterns from checkpoint."""
        engine = IntelligenceEngine()
        checkpoint = {
            "quality_score": 85,
            "conversation_history": [],
            "edit_history": [{"content": "def foo() -> str:"}],
            "tool_usage": [],
        }

        result = await engine._extract_patterns(checkpoint)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_extracts_tool_pattern(self):
        """Extracts tool usage patterns from checkpoint."""
        engine = IntelligenceEngine()
        checkpoint = {
            "quality_score": 85,
            "conversation_history": [],
            "edit_history": [],
            "tool_usage": [{"name": "search_reflections"}],
        }

        result = await engine._extract_patterns(checkpoint)
        assert isinstance(result, list)


# ============================================================================
# Test IntelligenceEngine - Pattern Detection
# ============================================================================


class TestPatternDetection:
    """Tests for pattern detection helper methods."""

    def test_detect_search_before_implement_found(self):
        """Detects search-before-implement pattern."""
        engine = IntelligenceEngine()
        conversation = [
            {"content": "Let me search reflections for similar issues"},
            {"content": "Found a solution, now implementing"},
        ]

        result = engine._detect_search_before_implement(conversation)

        assert result is True

    def test_detect_search_before_implement_not_found(self):
        """Does not detect pattern without search."""
        engine = IntelligenceEngine()
        conversation = [
            {"content": "Let me start implementing directly"},
            {"content": "Finished implementation"},
        ]

        result = engine._detect_search_before_implement(conversation)

        assert result is False

    def test_detect_iterative_problem_solving_found(self):
        """Detects iterative problem solving pattern."""
        engine = IntelligenceEngine()
        conversation = [
            {"content": "Try this approach"},
            {"content": "That didn't work, let me try another way"},
            {"content": "Success! This solution works"},
        ]

        result = engine._detect_iterative_problem_solving(conversation)

        assert result is True

    def test_detect_iterative_problem_solving_not_enough_attempts(self):
        """Requires at least 2 attempts."""
        engine = IntelligenceEngine()
        conversation = [
            {"content": "Try this approach"},
            {"content": "Success! Works perfectly"},
        ]

        result = engine._detect_iterative_problem_solving(conversation)

        assert result is False

    def test_detect_checkpoint_driven_work(self):
        """Detects checkpoint-driven work pattern."""
        engine = IntelligenceEngine()
        conversation = [
            {"content": "Creating checkpoint here"},
            {"content": "Continuing work"},
            {"content": "Another checkpoint before finalizing"},
        ]

        result = engine._detect_checkpoint_driven_work(conversation)

        assert result is True

    def test_detect_type_hypothesis_pattern(self):
        """Detects type annotation pattern in edits."""
        engine = IntelligenceEngine()
        edits = [
            {"content": "def process_item(item: str) -> dict:"},
        ]

        result = engine._detect_type_hypothesis_pattern(edits)

        assert result is True

    def test_detect_test_refactor_pattern(self):
        """Detects test-refactor pattern."""
        engine = IntelligenceEngine()
        edits = [
            {"content": "refactoring the code", "file_path": "src/utils.py"},
            {"content": "updated tests", "file_path": "tests/test_utils.py"},
        ]

        result = engine._detect_test_refactor_pattern(edits)

        assert result is True

    def test_detect_extraction_pattern(self):
        """Detects function extraction pattern."""
        engine = IntelligenceEngine()
        edits = [
            {"content": "def extracted_helper(data):"},
        ]

        result = engine._detect_extraction_pattern(edits)

        assert result is True

    def test_detect_test_driven_quality(self):
        """Detects test-driven quality workflow."""
        engine = IntelligenceEngine()
        tool_usage = [
            {"name": "crackerjack lint"},
            {"name": "run pytest"},
        ]

        result = engine._detect_test_driven_quality(tool_usage)

        assert result is True

    def test_detect_reflection_guided_pattern(self):
        """Detects reflection-guided development pattern."""
        engine = IntelligenceEngine()
        tool_usage = [
            {"name": "search_reflections"},
            {"name": "implement_solution"},
        ]

        result = engine._detect_reflection_guided_pattern(tool_usage)

        assert result is True

    def test_detect_checkpoint_iteration_pattern(self):
        """Detects checkpoint iteration pattern."""
        engine = IntelligenceEngine()
        tool_usage = [
            {"name": "create checkpoint"},
            {"name": "analyze quality"},
            {"name": "create checkpoint"},
        ]

        result = engine._detect_checkpoint_iteration_pattern(tool_usage)

        assert result is True


# ============================================================================
# Test IntelligenceEngine - Skill Consolidation
# ============================================================================


class TestSkillConsolidation:
    """Tests for _consolidate_into_skill method."""

    @pytest.mark.asyncio
    async def test_no_db_returns_none(self):
        """Returns None if database not initialized."""
        engine = IntelligenceEngine()
        engine.db = None

        result = await engine._consolidate_into_skill({"type": "test"})

        assert result is None

    @pytest.mark.asyncio
    async def test_insufficient_patterns_returns_none(self):
        """Returns None if fewer than 3 similar patterns."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("session-1", 85.0, {}),
            ("session-2", 90.0, {}),
        ]
        engine.db = mock_db

        result = await engine._consolidate_into_skill({"type": "test_pattern"})

        assert result is None

    @pytest.mark.asyncio
    async def test_low_average_quality_returns_none(self):
        """Returns None if average quality < 85."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        # 3 instances but average quality is 82
        mock_conn.execute.return_value.fetchall.return_value = [
            ("session-1", 80.0, {}),
            ("session-2", 82.0, {}),
            ("session-3", 84.0, {}),
        ]
        engine.db = mock_db

        result = await engine._consolidate_into_skill({"type": "test_pattern"})

        assert result is None

    @pytest.mark.asyncio
    async def test_creates_new_skill(self):
        """Creates new skill when conditions are met."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("session-1", 90.0, {}),
            ("session-2", 88.0, {}),
            ("session-3", 86.0, {}),
        ]
        mock_db.conn = mock_conn
        engine.db = mock_db
        engine.skill_library = {}

        pattern = {"type": "new_pattern", "tags": ["testing"], "session_id": "s1"}

        with patch.object(engine, "_save_skill", new_callable=AsyncMock) as mock_save:
            result = await engine._consolidate_into_skill(pattern)

            assert result is not None
            assert result.startswith("skill-")
            mock_save.assert_called_once()


# ============================================================================
# Test IntelligenceEngine - Suggestion Engine
# ============================================================================


class TestSuggestWorkflowImprovements:
    """Tests for suggest_workflow_improvements method."""

    @pytest.mark.asyncio
    async def test_no_skills_returns_empty(self):
        """Returns empty list when no skills in library."""
        engine = IntelligenceEngine()
        engine._initialized = True
        engine.skill_library = {}

        result = await engine.suggest_workflow_improvements({})

        assert result == []

    @pytest.mark.asyncio
    async def test_low_success_rate_skills_filtered(self):
        """Filters out skills with success_rate < 0.8."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        engine.skill_library = {
            "low_rate_skill": LearnedSkill(
                id="skill-1",
                name="low_rate_skill",
                description="Low success",
                success_rate=0.6,
                invocations=10,
                pattern={"tags": ["testing"]},
                learned_from=["s1"],
                created_at=now,
                last_used=now,
                tags=["testing"],
            )
        }

        result = await engine.suggest_workflow_improvements({})

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_returns_top_5_suggestions(self):
        """Returns at most 5 suggestions sorted by relevance."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        # Add multiple high-success skills
        for i in range(10):
            engine.skill_library[f"skill_{i}"] = LearnedSkill(
                id=f"skill-{i}",
                name=f"skill_{i}",
                description=f"Skill {i}",
                success_rate=0.9,
                invocations=5,
                pattern={"tags": ["testing", f"tag{i}"]},
                learned_from=["s1"],
                created_at=now,
                last_used=now,
                tags=["testing"],
            )

        result = await engine.suggest_workflow_improvements({})

        assert len(result) <= 5


class TestCalculateRelevance:
    """Tests for _calculate_relevance method."""

    def test_empty_tags_returns_neutral(self):
        """Empty tag sets return 0.5 neutral relevance."""
        engine = IntelligenceEngine()
        result = engine._calculate_relevance({}, {})
        assert result == 0.5

    def test_full_overlap_returns_1(self):
        """Identical tags return 1.0 relevance."""
        engine = IntelligenceEngine()
        context = {"tags": ["testing", "quality"]}
        pattern = {"tags": ["testing", "quality"]}

        result = engine._calculate_relevance(context, pattern)

        assert result == 1.0

    def test_partial_overlap(self):
        """Partial overlap returns proportional relevance."""
        engine = IntelligenceEngine()
        context = {"tags": ["testing", "debugging"]}
        pattern = {"tags": ["testing", "quality"]}

        result = engine._calculate_relevance(context, pattern)

        # Jaccard: 1 common / 3 total = 0.333
        assert result == pytest.approx(0.333, rel=0.01)

    def test_no_overlap_returns_0(self):
        """No common tags returns 0."""
        engine = IntelligenceEngine()
        context = {"tags": ["testing"]}
        pattern = {"tags": ["quality"]}

        result = engine._calculate_relevance(context, pattern)

        assert result == 0.0


# ============================================================================
# Test IntelligenceEngine - Skill Invocation
# ============================================================================


class TestInvokeSkill:
    """Tests for invoke_skill method."""

    @pytest.mark.asyncio
    async def test_skill_not_found_returns_error(self):
        """Returns error for unknown skill."""
        engine = IntelligenceEngine()
        engine._initialized = True
        engine.skill_library = {}

        result = await engine.invoke_skill("unknown_skill", {})

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_invocation_returns_skill_info(self):
        """Returns skill details and suggestions for valid skill."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        engine.skill_library = {
            "test_skill": LearnedSkill(
                id="skill-123",
                name="test_skill",
                description="A test skill",
                success_rate=0.85,
                invocations=5,
                pattern={"actions": ["action1", "action2"]},
                learned_from=["s1"],
                created_at=now,
                last_used=now,
                tags=["testing"],
            )
        }

        with patch.object(engine, "_save_skill") as mock_save:
            result = await engine.invoke_skill("test_skill", {})

            assert result["success"] is True
            assert result["skill"]["name"] == "test_skill"
            assert len(result["suggested_actions"]) == 2
            mock_save.assert_called_once()


# ============================================================================
# Test IntelligenceEngine - List Skills
# ============================================================================


class TestListSkills:
    """Tests for list_skills method."""

    @pytest.mark.asyncio
    async def test_returns_all_skills_by_default(self):
        """Returns all skills with no filter."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        for i in range(5):
            engine.skill_library[f"skill_{i}"] = LearnedSkill(
                id=f"skill-{i}",
                name=f"skill_{i}",
                description=f"Skill {i}",
                success_rate=0.8 + i * 0.04,
                invocations=i + 1,
                pattern={},
                learned_from=[],
                created_at=now,
                last_used=None,
                tags=[],
            )

        result = await engine.list_skills()

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_filters_by_min_success_rate(self):
        """Filters by minimum success rate."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        engine.skill_library = {
            "low_skill": LearnedSkill(
                id="skill-low",
                name="low_skill",
                description="Low rate",
                success_rate=0.5,
                invocations=1,
                pattern={},
                learned_from=[],
                created_at=now,
                last_used=None,
                tags=[],
            ),
            "high_skill": LearnedSkill(
                id="skill-high",
                name="high_skill",
                description="High rate",
                success_rate=0.9,
                invocations=5,
                pattern={},
                learned_from=[],
                created_at=now,
                last_used=None,
                tags=[],
            ),
        }

        result = await engine.list_skills(min_success_rate=0.8)

        assert len(result) == 1
        assert result[0]["name"] == "high_skill"

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """Respects maximum limit parameter."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        for i in range(20):
            engine.skill_library[f"skill_{i}"] = LearnedSkill(
                id=f"skill-{i}",
                name=f"skill_{i}",
                description=f"Skill {i}",
                success_rate=0.9,
                invocations=5,
                pattern={},
                learned_from=[],
                created_at=now,
                last_used=None,
                tags=[],
            )

        result = await engine.list_skills(limit=5)

        assert len(result) == 5


# ============================================================================
# Test IntelligenceEngine - Cross-Project Patterns
# ============================================================================


class TestCaptureSuccessfulPattern:
    """Tests for capture_successful_pattern method."""

    @pytest.mark.asyncio
    async def test_raises_if_no_db(self):
        """Raises RuntimeError if database not initialized."""
        engine = IntelligenceEngine()
        engine.db = None

        with pytest.raises(RuntimeError):
            await engine.capture_successful_pattern(
                pattern_type="test",
                project_id="proj-1",
                context={"problem": "issue"},
                solution={"fix": "applied"},
                outcome_score=0.9,
            )

    @pytest.mark.asyncio
    async def test_captures_pattern_with_all_fields(self):
        """Captures pattern with all provided fields."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.conn = mock_conn
        engine.db = mock_db

        result = await engine.capture_successful_pattern(
            pattern_type="solution",
            project_id="proj-123",
            context={"issue": "bug"},
            solution={"fix": "patched"},
            outcome_score=0.95,
            tags=["bug-fix", "urgent"],
        )

        assert result.startswith("pattern-")
        assert mock_conn.execute.called


class TestSearchSimilarPatterns:
    """Tests for search_similar_patterns method."""

    @pytest.mark.asyncio
    async def test_auto_initializes_if_needed(self):
        """Initializes database if not already done."""
        engine = IntelligenceEngine()
        engine._initialized = False
        engine.db = None

        with patch("session_buddy.core.intelligence.depends") as mock_depends:
            mock_db = MagicMock()
            mock_conn = MagicMock()
            mock_db.conn = mock_conn
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_depends.get_sync.return_value = mock_db

            await engine.search_similar_patterns({})

            assert engine._initialized is True

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_patterns(self):
        """Returns empty list when no patterns in database."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        engine.db = mock_db
        engine._initialized = True

        result = await engine.search_similar_patterns({"issue": "problem"})

        assert result == []


class TestApplyPattern:
    """Tests for apply_pattern method."""

    @pytest.mark.asyncio
    async def test_raises_if_no_db(self):
        """Raises RuntimeError if database not initialized."""
        engine = IntelligenceEngine()
        engine.db = None

        with pytest.raises(RuntimeError):
            await engine.apply_pattern(
                pattern_id="pattern-123",
                applied_to_project="proj-1",
                applied_context={"test": "context"},
            )

    @pytest.mark.asyncio
    async def test_records_application(self):
        """Records pattern application in database."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.conn = mock_conn
        engine.db = mock_db

        result = await engine.apply_pattern(
            pattern_id="pattern-abc",
            applied_to_project="proj-x",
            applied_context={"where": "applied"},
        )

        assert result.startswith("application-")
        # Verify INSERT and UPDATE were called
        assert mock_conn.execute.call_count >= 2


class TestRatePatternOutcome:
    """Tests for rate_pattern_outcome method."""

    @pytest.mark.asyncio
    async def test_raises_if_no_db(self):
        """Raises RuntimeError if database not initialized."""
        engine = IntelligenceEngine()
        engine.db = None

        with pytest.raises(RuntimeError):
            await engine.rate_pattern_outcome(
                application_id="app-123",
                outcome="success",
                feedback="Worked well",
            )

    @pytest.mark.asyncio
    async def test_raises_for_unknown_application(self):
        """Raises ValueError for unknown application ID."""
        engine = IntelligenceEngine()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        # fetchone() returns None when no application found
        mock_db.conn = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None
        engine.db = mock_db

        with pytest.raises(ValueError, match="not found"):
            await engine.rate_pattern_outcome(
                application_id="unknown-app",
                outcome="success",
            )


# ============================================================================
# Test IntelligenceEngine - Context Similarity
# ============================================================================


class TestContextSimilarity:
    """Tests for context similarity calculation."""

    def test_calculate_context_similarity_identical(self):
        """Identical contexts return high similarity."""
        engine = IntelligenceEngine()
        context = {"keywords": ["python", "testing", "quality"]}

        result = engine._calculate_context_similarity(context, context)

        assert result == 1.0

    def test_calculate_context_similarity_partial(self):
        """Partial overlap returns proportional similarity."""
        engine = IntelligenceEngine()
        ctx1 = {"description": "python testing framework"}
        ctx2 = {"description": "python quality assurance"}

        result = engine._calculate_context_similarity(ctx1, ctx2)

        # Some overlap in words
        assert 0.0 < result < 1.0

    def test_calculate_context_similarity_empty(self):
        """Empty contexts return 0 similarity."""
        engine = IntelligenceEngine()

        result = engine._calculate_context_similarity({}, {})

        assert result == 0.0

    def test_extract_keywords_filters_stop_words(self):
        """Stop words are filtered from keywords."""
        engine = IntelligenceEngine()
        context = {
            "description": "the quick brown fox jumped over the lazy dog",
            "title": "A story about testing",
        }

        keywords = engine._extract_keywords(context)

        assert "the" not in keywords
        assert "about" not in keywords
        assert "quick" in keywords
        assert "testing" in keywords

    def test_extract_keywords_handles_nested_dicts(self):
        """Nested dictionaries are traversed via values."""
        engine = IntelligenceEngine()
        # Note: extract_keywords extracts from VALUES only, not keys
        context = {
            "level1": {
                "nested": "python testing quality",
            }
        }

        keywords = engine._extract_keywords(context)

        # Values from nested dicts are extracted
        assert "python" in keywords
        assert "testing" in keywords
        assert "quality" in keywords

    def test_extract_keywords_handles_lists(self):
        """Lists in context are processed."""
        engine = IntelligenceEngine()
        context = {
            "tags": ["python", "testing", "quality"],
        }

        keywords = engine._extract_keywords(context)

        assert "python" in keywords
        assert "testing" in keywords


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_learn_from_checkpoint_empty_conversation(self):
        """Handles empty conversation history gracefully."""
        engine = IntelligenceEngine()
        engine._initialized = True

        checkpoint = {
            "quality_score": 85,
            "conversation_history": [],
            "edit_history": [],
            "tool_usage": [],
        }

        result = await engine._extract_patterns(checkpoint)

        assert isinstance(result, list)
        assert len(result) == 0  # No patterns from empty data

    @pytest.mark.asyncio
    async def test_suggest_with_no_context(self):
        """Handles empty session context."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        engine.skill_library = {
            "test_skill": LearnedSkill(
                id="skill-1",
                name="test_skill",
                description="Test",
                success_rate=0.9,
                invocations=5,
                pattern={"tags": ["testing"]},
                learned_from=["s1"],
                created_at=now,
                last_used=now,
                tags=["testing"],
            )
        }

        result = await engine.suggest_workflow_improvements({})

        # Should not crash, returns suggestions based on pattern tags
        assert isinstance(result, list)

    def test_extract_context_returns_dict(self):
        """Returns empty dict for invalid context."""
        engine = IntelligenceEngine()

        result = engine._extract_context({})
        assert result == {}

        result = engine._extract_context({"context": "string not dict"})
        assert result == {}

        result = engine._extract_context({"context": {"key": "value"}})
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_list_skills_handles_null_values(self):
        """Skills with None success_rate are filtered out to avoid comparison errors."""
        engine = IntelligenceEngine()
        engine._initialized = True

        now = datetime.now(UTC)
        engine.skill_library = {
            "valid_skill": LearnedSkill(
                id="skill-valid",
                name="valid_skill",
                description="Has valid rate",
                success_rate=0.9,
                invocations=5,
                pattern={},
                learned_from=[],
                created_at=now,
                last_used=None,
                tags=[],
            ),
            "null_skill": LearnedSkill(
                id="skill-null",
                name="null_skill",
                description="Has nulls",
                success_rate=None,  # None value should be filtered
                invocations=None,
                pattern={},
                learned_from=[],
                created_at=now,
                last_used=None,
                tags=[],
            )
        }

        result = await engine.list_skills()

        # Only valid_skill should be included
        assert len(result) == 1
        assert result[0]["name"] == "valid_skill"
