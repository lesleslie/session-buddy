#!/usr/bin/env python3
"""Comprehensive unit tests for Pydantic parameter validation models.

Tests ALL public model classes from session_buddy.parameter_models:
- WorkingDirectoryParams
- ProjectContextParams
- SearchLimitParams
- TimeRangeParams
- ScoreThresholdParams
- TagParams
- IDParams
- FilePathParams
- CommandExecutionParams
- BooleanFlagParams
- SessionInitParams
- SessionStatusParams
- ReflectionStoreParams
- SearchQueryParams
- FileSearchParams
- ConceptSearchParams
- CrackerjackExecutionParams
- CrackerjackHistoryParams
- TeamUserParams
- TeamCreationParams
- TeamReflectionParams
- TeamSearchParams

Tests cover:
- Model instantiation with valid inputs
- Field validation (types, ranges, constraints)
- Default values
- Required vs optional fields
- Serialization/deserialization
- Edge cases: invalid types, out-of-range values, missing required fields, extra fields
"""

import os
import tempfile
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from session_buddy.parameter_models import (
    BooleanFlagParams,
    CommandExecutionParams,
    ConceptSearchParams,
    CrackerjackExecutionParams,
    CrackerjackHistoryParams,
    FilePathParams,
    FileSearchParams,
    IDParams,
    ProjectContextParams,
    ReflectionStoreParams,
    ScoreThresholdParams,
    SearchLimitParams,
    SearchQueryParams,
    SessionInitParams,
    SessionStatusParams,
    TagParams,
    TeamCreationParams,
    TeamReflectionParams,
    TeamSearchParams,
    TeamUserParams,
    TimeRangeParams,
    ValidationResponse,
    WorkingDirectoryParams,
    validate_mcp_params,
)


class TestWorkingDirectoryParams:
    """Test WorkingDirectoryParams model."""

    def test_valid_directory_with_current_dir(self, tmp_path):
        """Test valid working directory."""
        params = WorkingDirectoryParams(working_directory=str(tmp_path))
        assert params.working_directory == str(tmp_path)

    def test_none_directory(self):
        """Test None working directory is valid."""
        params = WorkingDirectoryParams(working_directory=None)
        assert params.working_directory is None

    def test_empty_string_becomes_none(self):
        """Test empty string becomes None."""
        params = WorkingDirectoryParams(working_directory="")
        assert params.working_directory is None

    def test_whitespace_string_becomes_none(self):
        """Test whitespace-only string becomes None."""
        params = WorkingDirectoryParams(working_directory="   ")
        assert params.working_directory is None

    def test_expanduser_path(self):
        """Test home directory expansion."""
        params = WorkingDirectoryParams(working_directory="~/")
        expected = os.path.expanduser("~/")
        assert params.working_directory == expected

    def test_nonexistent_directory_raises(self):
        """Test non-existent directory raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            WorkingDirectoryParams(working_directory="/nonexistent/path/12345")
        assert "Working directory does not exist" in str(exc_info.value)

    def test_file_not_directory_raises(self):
        """Test file path in directory field raises ValidationError."""
        with tempfile.NamedTemporaryFile() as tmp_file:
            with pytest.raises(ValidationError) as exc_info:
                WorkingDirectoryParams(working_directory=tmp_file.name)
            assert "Working directory is not a directory" in str(exc_info.value)


class TestProjectContextParams:
    """Test ProjectContextParams model."""

    def test_valid_project(self):
        """Test valid project identifier."""
        params = ProjectContextParams(project="my-app")
        assert params.project == "my-app"

    def test_none_project(self):
        """Test None project is valid."""
        params = ProjectContextParams(project=None)
        assert params.project is None

    def test_empty_string_raises(self):
        """Test empty string raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            ProjectContextParams(project="")

    def test_whitespace_strips_and_becomes_none(self):
        """Test whitespace-only string becomes None."""
        params = ProjectContextParams(project="   ")
        assert params.project is None

    def test_max_length_project(self):
        """Test project at max length (200)."""
        params = ProjectContextParams(project="a" * 200)
        assert params.project == "a" * 200

    def test_over_max_length_raises(self):
        """Test project over max length raises ValidationError."""
        with pytest.raises(ValidationError):
            ProjectContextParams(project="a" * 201)


class TestSearchLimitParams:
    """Test SearchLimitParams model."""

    def test_default_values(self):
        """Test default limit and offset."""
        params = SearchLimitParams()
        assert params.limit == 10
        assert params.offset == 0

    def test_valid_limit_and_offset(self):
        """Test valid limit and offset values."""
        params = SearchLimitParams(limit=50, offset=100)
        assert params.limit == 50
        assert params.offset == 100

    def test_limit_minimum_boundary(self):
        """Test limit at minimum (1)."""
        params = SearchLimitParams(limit=1)
        assert params.limit == 1

    def test_limit_maximum_boundary(self):
        """Test limit at maximum (1000)."""
        params = SearchLimitParams(limit=1000)
        assert params.limit == 1000

    def test_limit_below_minimum_raises(self):
        """Test limit below minimum raises ValidationError."""
        with pytest.raises(ValidationError):
            SearchLimitParams(limit=0)

    def test_limit_above_maximum_raises(self):
        """Test limit above maximum raises ValidationError."""
        with pytest.raises(ValidationError):
            SearchLimitParams(limit=1001)

    def test_offset_minimum_boundary(self):
        """Test offset at minimum (0)."""
        params = SearchLimitParams(offset=0)
        assert params.offset == 0

    def test_offset_negative_raises(self):
        """Test negative offset raises ValidationError."""
        with pytest.raises(ValidationError):
            SearchLimitParams(offset=-1)


class TestTimeRangeParams:
    """Test TimeRangeParams model."""

    def test_default_days(self):
        """Test default days value."""
        params = TimeRangeParams()
        assert params.days == 7

    def test_valid_days(self):
        """Test valid days values."""
        params = TimeRangeParams(days=30)
        assert params.days == 30

    def test_days_minimum_boundary(self):
        """Test days at minimum (1)."""
        params = TimeRangeParams(days=1)
        assert params.days == 1

    def test_days_maximum_boundary(self):
        """Test days at maximum (3650)."""
        params = TimeRangeParams(days=3650)
        assert params.days == 3650

    def test_days_below_minimum_raises(self):
        """Test days below minimum raises ValidationError."""
        with pytest.raises(ValidationError):
            TimeRangeParams(days=0)

    def test_days_above_maximum_raises(self):
        """Test days above maximum raises ValidationError."""
        with pytest.raises(ValidationError):
            TimeRangeParams(days=3651)


class TestScoreThresholdParams:
    """Test ScoreThresholdParams model."""

    def test_default_min_score(self):
        """Test default min_score value."""
        params = ScoreThresholdParams()
        assert params.min_score == 0.7

    def test_valid_min_score(self):
        """Test valid min_score values."""
        params = ScoreThresholdParams(min_score=0.5)
        assert params.min_score == 0.5

    def test_min_score_at_minimum_boundary(self):
        """Test min_score at minimum (0.0)."""
        params = ScoreThresholdParams(min_score=0.0)
        assert params.min_score == 0.0

    def test_min_score_at_maximum_boundary(self):
        """Test min_score at maximum (1.0)."""
        params = ScoreThresholdParams(min_score=1.0)
        assert params.min_score == 1.0

    def test_min_score_below_minimum_raises(self):
        """Test min_score below minimum raises ValidationError."""
        with pytest.raises(ValidationError):
            ScoreThresholdParams(min_score=-0.1)

    def test_min_score_above_maximum_raises(self):
        """Test min_score above maximum raises ValidationError."""
        with pytest.raises(ValidationError):
            ScoreThresholdParams(min_score=1.1)


class TestTagParams:
    """Test TagParams model."""

    def test_valid_tags(self):
        """Test valid tag lists."""
        params = TagParams(tags=["python", "async"])
        assert params.tags == ["python", "async"]

    def test_none_tags(self):
        """Test None tags is valid."""
        params = TagParams(tags=None)
        assert params.tags is None

    def test_empty_list_becomes_none(self):
        """Test empty list becomes None."""
        params = TagParams(tags=[])
        assert params.tags is None

    def test_tag_normalization_lowercase(self):
        """Test tags are lowercased."""
        params = TagParams(tags=["PYTHON", "ASYNC"])
        assert params.tags == ["python", "async"]

    def test_tag_whitespace_stripping(self):
        """Test tags have whitespace stripped."""
        params = TagParams(tags=["  python  ", " async "])
        assert params.tags == ["python", "async"]

    def test_skip_empty_tags(self):
        """Test empty strings in tags are skipped."""
        params = TagParams(tags=["python", "", "  ", "async"])
        assert params.tags == ["python", "async"]

    def test_hyphen_and_underscore_allowed(self):
        """Test hyphens and underscores are valid in tags."""
        params = TagParams(tags=["bug-fix", "feature_request", "ui_v2"])
        assert params.tags == ["bug-fix", "feature_request", "ui_v2"]

    def test_invalid_special_characters_raises(self):
        """Test invalid special characters raise ValidationError."""
        with pytest.raises(ValidationError):
            TagParams(tags=["invalid@tag"])
        with pytest.raises(ValidationError):
            TagParams(tags=["tag with spaces"])
        with pytest.raises(ValidationError):
            TagParams(tags=["bad!tag"])

    def test_tag_too_long_raises(self):
        """Test tag exceeding max length raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TagParams(tags=["a" * 51])
        assert "Tag too long" in str(exc_info.value)

    def test_tag_at_max_length(self):
        """Test tag at exactly max length (50)."""
        params = TagParams(tags=["a" * 50])
        assert params.tags == ["a" * 50]

    def test_non_string_tag_type_raises(self):
        """Test non-string tag raises ValidationError."""
        with pytest.raises(ValidationError):
            TagParams(tags=["valid", 123])

    def test_non_list_type_raises(self):
        """Test non-list type raises ValidationError."""
        with pytest.raises(ValidationError):
            TagParams(tags="not a list")


class TestIDParams:
    """Test IDParams model."""

    def test_valid_id(self):
        """Test valid ID formats."""
        params = IDParams(id="abc123")
        assert params.id == "abc123"

    def test_id_with_hyphens_underscores_dots(self):
        """Test IDs with hyphens, underscores, and dots."""
        params1 = IDParams(id="session_20250106")
        params2 = IDParams(id="reflection-456")
        params3 = IDParams(id="file.v1")
        assert params1.id == "session_20250106"
        assert params2.id == "reflection-456"
        assert params3.id == "file.v1"

    def test_id_whitespace_stripping(self):
        """Test ID whitespace is stripped."""
        params = IDParams(id="  abc123  ")
        assert params.id == "abc123"

    def test_empty_id_raises(self):
        """Test empty ID raises ValidationError."""
        with pytest.raises(ValidationError):
            IDParams(id="")

    def test_whitespace_only_id_raises(self):
        """Test whitespace-only ID raises ValidationError."""
        with pytest.raises(ValidationError):
            IDParams(id="   ")

    def test_id_with_invalid_characters_raises(self):
        """Test ID with invalid characters raises ValidationError."""
        with pytest.raises(ValidationError):
            IDParams(id="invalid@id")
        with pytest.raises(ValidationError):
            IDParams(id="id with spaces")
        with pytest.raises(ValidationError):
            IDParams(id="bad!id")

    def test_id_max_length(self):
        """Test ID at max length (100)."""
        params = IDParams(id="a" * 100)
        assert params.id == "a" * 100

    def test_id_over_max_length_raises(self):
        """Test ID over max length raises ValidationError."""
        with pytest.raises(ValidationError):
            IDParams(id="a" * 101)


class TestFilePathParams:
    """Test FilePathParams model."""

    def test_valid_file_path(self):
        """Test valid file paths."""
        params = FilePathParams(file_path="README.md")
        assert params.file_path == "README.md"

    def test_file_path_whitespace_stripping(self):
        """Test file path whitespace is stripped."""
        params = FilePathParams(file_path="  src/main.py  ")
        assert params.file_path == "src/main.py"

    def test_empty_file_path_raises(self):
        """Test empty file path raises ValidationError."""
        with pytest.raises(ValidationError):
            FilePathParams(file_path="")

    def test_whitespace_only_file_path_raises(self):
        """Test whitespace-only file path raises ValidationError."""
        with pytest.raises(ValidationError):
            FilePathParams(file_path="   ")

    def test_null_character_raises(self):
        """Test file path with null character raises ValidationError."""
        with pytest.raises(ValidationError):
            FilePathParams(file_path="file\x00name")

    def test_max_length_file_path(self):
        """Test file path at reasonable max length."""
        params = FilePathParams(file_path="a" * 1000)
        assert params.file_path == "a" * 1000


class TestCommandExecutionParams:
    """Test CommandExecutionParams model."""

    def test_valid_command(self):
        """Test valid command parameters."""
        params = CommandExecutionParams(command="lint", args="--fix", timeout=600)
        assert params.command == "lint"
        assert params.args == "--fix"
        assert params.timeout == 600

    def test_default_values(self):
        """Test default values for args and timeout."""
        params = CommandExecutionParams(command="test")
        assert params.command == "test"
        assert params.args == ""
        assert params.timeout == 300

    def test_empty_command_raises(self):
        """Test empty command raises ValidationError."""
        with pytest.raises(ValidationError):
            CommandExecutionParams(command="")

    def test_whitespace_only_command_raises(self):
        """Test whitespace-only command raises ValidationError."""
        with pytest.raises(ValidationError):
            CommandExecutionParams(command="   ")

    def test_timeout_minimum_boundary(self):
        """Test timeout at minimum (1)."""
        params = CommandExecutionParams(command="test", timeout=1)
        assert params.timeout == 1

    def test_timeout_maximum_boundary(self):
        """Test timeout at maximum (3600)."""
        params = CommandExecutionParams(command="test", timeout=3600)
        assert params.timeout == 3600

    def test_timeout_below_minimum_raises(self):
        """Test timeout below minimum raises ValidationError."""
        with pytest.raises(ValidationError):
            CommandExecutionParams(command="test", timeout=0)

    def test_timeout_above_maximum_raises(self):
        """Test timeout above maximum raises ValidationError."""
        with pytest.raises(ValidationError):
            CommandExecutionParams(command="test", timeout=3601)

    def test_args_max_length(self):
        """Test args at max length (2000)."""
        params = CommandExecutionParams(command="test", args="a" * 2000)
        assert params.args == "a" * 2000

    def test_args_over_max_length_raises(self):
        """Test args over max length raises ValidationError."""
        with pytest.raises(ValidationError):
            CommandExecutionParams(command="test", args="a" * 2001)


class TestBooleanFlagParams:
    """Test BooleanFlagParams model."""

    def test_default_values(self):
        """Test all flags default to False."""
        params = BooleanFlagParams()
        assert params.force is False
        assert params.verbose is False
        assert params.dry_run is False

    def test_all_flags_true(self):
        """Test all flags can be set to True."""
        params = BooleanFlagParams(force=True, verbose=True, dry_run=True)
        assert params.force is True
        assert params.verbose is True
        assert params.dry_run is True

    def test_mixed_flags(self):
        """Test mixed flag values."""
        params = BooleanFlagParams(force=True, verbose=False, dry_run=True)
        assert params.force is True
        assert params.verbose is False
        assert params.dry_run is True

    def test_string_coerces_to_boolean(self):
        """Test string values are coerced to boolean (Pydantic 2 behavior)."""
        # Pydantic 2 coerces "true"/"false" strings to True/False
        params = BooleanFlagParams(force="true")
        assert params.force is True
        params = BooleanFlagParams(verbose="0")  # empty string coerces to False
        assert params.verbose is False
        params = BooleanFlagParams(dry_run="yes")
        assert params.dry_run is True  # non-empty string is truthy


class TestSessionInitParams:
    """Test SessionInitParams model (extends WorkingDirectoryParams)."""

    def test_inherits_from_working_directory_params(self):
        """Test SessionInitParams inherits working_directory."""
        params = SessionInitParams(working_directory=None)
        assert params.working_directory is None

    def test_with_valid_directory(self, tmp_path):
        """Test with existing directory."""
        params = SessionInitParams(working_directory=str(tmp_path))
        assert params.working_directory == str(tmp_path)


class TestSessionStatusParams:
    """Test SessionStatusParams model (extends WorkingDirectoryParams)."""

    def test_inherits_from_working_directory_params(self):
        """Test SessionStatusParams inherits working_directory."""
        params = SessionStatusParams(working_directory=None)
        assert params.working_directory is None

    def test_with_valid_directory(self, tmp_path):
        """Test with existing directory."""
        params = SessionStatusParams(working_directory=str(tmp_path))
        assert params.working_directory == str(tmp_path)


class TestReflectionStoreParams:
    """Test ReflectionStoreParams model."""

    def test_valid_reflection(self):
        """Test valid reflection with content and tags."""
        params = ReflectionStoreParams(
            content="Python async patterns improve performance.",
            tags=["python", "async"],
        )
        assert params.content == "Python async patterns improve performance."
        assert params.tags == ["python", "async"]

    def test_content_only(self):
        """Test reflection with content only."""
        params = ReflectionStoreParams(content="Valid content here")
        assert params.content == "Valid content here"
        assert params.tags is None

    def test_content_strips_whitespace(self):
        """Test content whitespace is stripped."""
        params = ReflectionStoreParams(content="  trimmed content  ")
        assert params.content == "trimmed content"

    def test_empty_content_raises(self):
        """Test empty content raises ValidationError."""
        with pytest.raises(ValidationError):
            ReflectionStoreParams(content="")

    def test_whitespace_only_content_raises(self):
        """Test whitespace-only content raises ValidationError."""
        with pytest.raises(ValidationError):
            ReflectionStoreParams(content="   ")

    def test_content_min_length(self):
        """Test content at minimum length (1)."""
        params = ReflectionStoreParams(content="x")
        assert params.content == "x"

    def test_content_max_length(self):
        """Test content at maximum length (50000)."""
        params = ReflectionStoreParams(content="x" * 50000)
        assert len(params.content) == 50000

    def test_content_over_max_length_raises(self):
        """Test content over maximum length raises ValidationError."""
        with pytest.raises(ValidationError):
            ReflectionStoreParams(content="x" * 50001)

    def test_tags_optional(self):
        """Test both None and absent tags are valid."""
        params = ReflectionStoreParams(content="Valid", tags=None)
        assert params.tags is None


class TestSearchQueryParams:
    """Test SearchQueryParams model."""

    def test_valid_search_params(self):
        """Test valid search query parameters."""
        params = SearchQueryParams(
            query="python async patterns",
            limit=20,
            project="my-project",
            min_score=0.8,
        )
        assert params.query == "python async patterns"
        assert params.limit == 20
        assert params.project == "my-project"
        assert params.min_score == 0.8

    def test_default_values(self):
        """Test default values from inherited models."""
        params = SearchQueryParams(query="test query")
        assert params.query == "test query"
        assert params.limit == 10
        assert params.offset == 0
        assert params.project is None
        assert params.min_score == 0.7

    def test_query_required(self):
        """Test query is required."""
        with pytest.raises(ValidationError):
            SearchQueryParams()

    def test_empty_query_raises(self):
        """Test empty query raises ValidationError."""
        with pytest.raises(ValidationError):
            SearchQueryParams(query="")

    def test_whitespace_only_query_raises(self):
        """Test whitespace-only query raises ValidationError."""
        with pytest.raises(ValidationError):
            SearchQueryParams(query="   ")

    def test_query_max_length(self):
        """Test query at max length (1000)."""
        params = SearchQueryParams(query="a" * 1000)
        assert params.query == "a" * 1000

    def test_query_over_max_length_raises(self):
        """Test query over max length raises ValidationError."""
        with pytest.raises(ValidationError):
            SearchQueryParams(query="a" * 1001)

    def test_limit_inherited_validation(self):
        """Test limit validation inherited from SearchLimitParams."""
        with pytest.raises(ValidationError):
            SearchQueryParams(query="test", limit=0)
        with pytest.raises(ValidationError):
            SearchQueryParams(query="test", limit=1001)

    def test_min_score_inherited_validation(self):
        """Test min_score validation inherited from ScoreThresholdParams."""
        with pytest.raises(ValidationError):
            SearchQueryParams(query="test", min_score=-0.1)
        with pytest.raises(ValidationError):
            SearchQueryParams(query="test", min_score=1.1)


class TestFileSearchParams:
    """Test FileSearchParams model."""

    def test_valid_file_search(self):
        """Test valid file search parameters."""
        params = FileSearchParams(
            file_path="src/main.py",
            limit=15,
            project="backend",
            min_score=0.6,
        )
        assert params.file_path == "src/main.py"
        assert params.limit == 15
        assert params.project == "backend"
        assert params.min_score == 0.6

    def test_default_values(self):
        """Test default values from inherited models."""
        params = FileSearchParams(file_path="src/main.py")
        assert params.file_path == "src/main.py"
        assert params.limit == 10
        assert params.offset == 0
        assert params.project is None
        assert params.min_score == 0.7

    def test_empty_file_path_raises(self):
        """Test empty file path raises ValidationError."""
        with pytest.raises(ValidationError):
            FileSearchParams(file_path="")

    def test_whitespace_only_file_path_raises(self):
        """Test whitespace-only file path raises ValidationError."""
        with pytest.raises(ValidationError):
            FileSearchParams(file_path="   ")


class TestConceptSearchParams:
    """Test ConceptSearchParams model."""

    def test_valid_concept_search(self):
        """Test valid concept search parameters."""
        params = ConceptSearchParams(
            concept="connection pooling",
            limit=25,
            project="backend",
            min_score=0.5,
            include_files=True,
        )
        assert params.concept == "connection pooling"
        assert params.limit == 25
        assert params.project == "backend"
        assert params.min_score == 0.5
        assert params.include_files is True

    def test_default_values(self):
        """Test default values from inherited models."""
        params = ConceptSearchParams(concept="caching")
        assert params.concept == "caching"
        assert params.limit == 10
        assert params.offset == 0
        assert params.project is None
        assert params.min_score == 0.7
        assert params.include_files is True

    def test_include_files_default_true(self):
        """Test include_files defaults to True."""
        params = ConceptSearchParams(concept="testing")
        assert params.include_files is True

    def test_empty_concept_raises(self):
        """Test empty concept raises ValidationError."""
        with pytest.raises(ValidationError):
            ConceptSearchParams(concept="")

    def test_whitespace_only_concept_raises(self):
        """Test whitespace-only concept raises ValidationError."""
        with pytest.raises(ValidationError):
            ConceptSearchParams(concept="   ")

    def test_concept_max_length(self):
        """Test concept at max length (200)."""
        params = ConceptSearchParams(concept="a" * 200)
        assert params.concept == "a" * 200

    def test_concept_over_max_length_raises(self):
        """Test concept over max length raises ValidationError."""
        with pytest.raises(ValidationError):
            ConceptSearchParams(concept="a" * 201)


class TestCrackerjackExecutionParams:
    """Test CrackerjackExecutionParams model."""

    def test_valid_execution_params(self):
        """Test valid crackerjack execution parameters."""
        params = CrackerjackExecutionParams(
            command="lint",
            args="--fix",
            timeout=600,
            working_directory=".",
            ai_agent_mode=True,
        )
        assert params.command == "lint"
        assert params.args == "--fix"
        assert params.timeout == 600
        assert params.working_directory == "."
        assert params.ai_agent_mode is True

    def test_default_values(self):
        """Test default values from inherited models."""
        params = CrackerjackExecutionParams(command="test")
        assert params.command == "test"
        assert params.args == ""
        assert params.timeout == 300
        assert params.working_directory is None
        assert params.ai_agent_mode is False

    def test_ai_agent_mode_default_false(self):
        """Test ai_agent_mode defaults to False."""
        params = CrackerjackExecutionParams(command="test")
        assert params.ai_agent_mode is False


class TestCrackerjackHistoryParams:
    """Test CrackerjackHistoryParams model."""

    def test_valid_history_params(self):
        """Test valid crackerjack history parameters."""
        params = CrackerjackHistoryParams(
            days=30,
            working_directory=".",
            command_filter="lint",
        )
        assert params.days == 30
        assert params.working_directory == "."
        assert params.command_filter == "lint"

    def test_default_values(self):
        """Test default values from inherited models."""
        params = CrackerjackHistoryParams()
        assert params.days == 7
        assert params.working_directory is None
        assert params.command_filter == ""

    def test_empty_command_filter(self):
        """Test empty command filter is valid."""
        params = CrackerjackHistoryParams(command_filter="")
        assert params.command_filter == ""

    def test_command_filter_max_length(self):
        """Test command filter at max length (100)."""
        params = CrackerjackHistoryParams(command_filter="a" * 100)
        assert params.command_filter == "a" * 100

    def test_command_filter_over_max_length_raises(self):
        """Test command filter over max length raises ValidationError."""
        with pytest.raises(ValidationError):
            CrackerjackHistoryParams(command_filter="a" * 101)


class TestTeamUserParams:
    """Test TeamUserParams model."""

    def test_valid_team_user(self):
        """Test valid team user parameters."""
        params = TeamUserParams(
            user_id="user123",
            username="john_doe",
            role="contributor",
            email="john@example.com",
        )
        assert params.user_id == "user123"
        assert params.username == "john_doe"
        assert params.role == "contributor"
        assert params.email == "john@example.com"

    def test_default_role(self):
        """Test default role is contributor."""
        params = TeamUserParams(user_id="user123", username="john")
        assert params.role == "contributor"

    def test_all_valid_roles(self):
        """Test all valid role values."""
        for role in ["owner", "admin", "moderator", "contributor", "viewer"]:
            params = TeamUserParams(user_id="user123", username="john", role=role)
            assert params.role == role

    def test_invalid_role_raises(self):
        """Test invalid role raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamUserParams(user_id="user123", username="john", role="invalid")

    def test_empty_user_id_raises(self):
        """Test empty user_id raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamUserParams(user_id="", username="john")

    def test_empty_username_raises(self):
        """Test empty username raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamUserParams(user_id="user123", username="")

    def test_whitespace_only_ids_raises(self):
        """Test whitespace-only IDs raise ValidationError."""
        with pytest.raises(ValidationError):
            TeamUserParams(user_id="   ", username="john")
        with pytest.raises(ValidationError):
            TeamUserParams(user_id="user123", username="   ")

    def test_email_optional(self):
        """Test email is optional."""
        params = TeamUserParams(user_id="user123", username="john", email=None)
        assert params.email is None

    def test_empty_email_becomes_none(self):
        """Test empty email becomes None."""
        params = TeamUserParams(user_id="user123", username="john", email="")
        assert params.email is None

    def test_valid_emails(self):
        """Test valid email formats."""
        valid_emails = [
            "user@example.com",
            "test.user+tag@domain.co.uk",
            "simple@test.io",
        ]
        for email in valid_emails:
            params = TeamUserParams(
                user_id="user123", username="john", email=email
            )
            assert params.email == email

    def test_invalid_emails_raise(self):
        """Test invalid email formats raise ValidationError."""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user@.com",
            "user@example",
        ]
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                TeamUserParams(user_id="user123", username="john", email=email)

    def test_email_too_long_raises(self):
        """Test email over 254 characters raises ValidationError."""
        long_email = "a" * 255 + "@example.com"
        with pytest.raises(ValidationError):
            TeamUserParams(user_id="user123", username="john", email=long_email)


class TestTeamCreationParams:
    """Test TeamCreationParams model."""

    def test_valid_team_creation(self):
        """Test valid team creation parameters."""
        params = TeamCreationParams(
            team_id="team_backend",
            name="Backend Team",
            description="Backend services team",
            owner_id="owner123",
        )
        assert params.team_id == "team_backend"
        assert params.name == "Backend Team"
        assert params.description == "Backend services team"
        assert params.owner_id == "owner123"

    def test_empty_fields_raise(self):
        """Test empty required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            TeamCreationParams(team_id="", name="Test", description="Desc", owner_id="owner")
        with pytest.raises(ValidationError):
            TeamCreationParams(team_id="team", name="", description="Desc", owner_id="owner")
        with pytest.raises(ValidationError):
            TeamCreationParams(team_id="team", name="Test", description="", owner_id="owner")
        with pytest.raises(ValidationError):
            TeamCreationParams(team_id="team", name="Test", description="Desc", owner_id="")

    def test_whitespace_only_fields_raise(self):
        """Test whitespace-only fields raise ValidationError."""
        with pytest.raises(ValidationError):
            TeamCreationParams(
                team_id="   ", name="Test", description="Desc", owner_id="owner"
            )

    def test_stripped_whitespace(self):
        """Test whitespace is stripped from fields."""
        params = TeamCreationParams(
            team_id="  team_id  ",
            name="  Test Name  ",
            description="  Test Desc  ",
            owner_id="  owner_id  ",
        )
        assert params.team_id == "team_id"
        assert params.name == "Test Name"
        assert params.description == "Test Desc"
        assert params.owner_id == "owner_id"

    def test_max_length_fields(self):
        """Test fields at max length."""
        params = TeamCreationParams(
            team_id="a" * 100,
            name="a" * 200,
            description="a" * 1000,
            owner_id="a" * 100,
        )
        assert params.team_id == "a" * 100
        assert params.name == "a" * 200
        assert params.description == "a" * 1000


class TestTeamReflectionParams:
    """Test TeamReflectionParams model."""

    def test_valid_team_reflection(self):
        """Test valid team reflection parameters."""
        params = TeamReflectionParams(
            content="Key insight about database performance",
            author_id="author123",
            team_id="team456",
            project_id="project789",
            tags=["database", "performance"],
            access_level="team",
        )
        assert params.content == "Key insight about database performance"
        assert params.author_id == "author123"
        assert params.team_id == "team456"
        assert params.project_id == "project789"
        assert params.tags == ["database", "performance"]
        assert params.access_level == "team"

    def test_optional_ids(self):
        """Test optional team_id and project_id."""
        params = TeamReflectionParams(
            content="Valid content",
            author_id="author123",
            team_id=None,
            project_id=None,
        )
        assert params.team_id is None
        assert params.project_id is None

    def test_empty_string_ids_raise(self):
        """Test empty string IDs raise ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            TeamReflectionParams(
                content="Valid content",
                author_id="author123",
                team_id="",
                project_id="",
            )

    def test_empty_author_id_raises(self):
        """Test empty author_id raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamReflectionParams(content="Valid content", author_id="")

    def test_all_valid_access_levels(self):
        """Test all valid access level values."""
        for level in ["private", "team", "public"]:
            params = TeamReflectionParams(
                content="Valid content",
                author_id="author123",
                access_level=level,
            )
            assert params.access_level == level

    def test_invalid_access_level_raises(self):
        """Test invalid access level raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamReflectionParams(
                content="Valid content", author_id="author123", access_level="invalid"
            )

    def test_default_access_level(self):
        """Test default access level is team."""
        params = TeamReflectionParams(content="Valid content", author_id="author123")
        assert params.access_level == "team"

    def test_inherits_reflection_store_tags_validation(self):
        """Test tags validation inherited from ReflectionStoreParams."""
        with pytest.raises(ValidationError):
            TeamReflectionParams(
                content="Valid content",
                author_id="author123",
                tags=["invalid@tag"],
            )


class TestTeamSearchParams:
    """Test TeamSearchParams model."""

    def test_valid_team_search(self):
        """Test valid team search parameters."""
        params = TeamSearchParams(
            query="database performance improvements",
            user_id="user123",
            team_id="team456",
            project_id="project789",
            limit=20,
            min_score=0.8,
        )
        assert params.query == "database performance improvements"
        assert params.user_id == "user123"
        assert params.team_id == "team456"
        assert params.project_id == "project789"
        assert params.limit == 20
        assert params.min_score == 0.8

    def test_user_id_required(self):
        """Test user_id is required."""
        with pytest.raises(ValidationError):
            TeamSearchParams(query="test query", user_id="")

    def test_empty_team_and_project_ids(self):
        """Test optional team_id and project_id can be None."""
        params = TeamSearchParams(
            query="test query",
            user_id="user123",
            team_id=None,
            project_id=None,
        )
        assert params.team_id is None
        assert params.project_id is None

    def test_inherits_search_query_params_validation(self):
        """Test query validation inherited from SearchQueryParams."""
        with pytest.raises(ValidationError):
            TeamSearchParams(query="", user_id="user123")


class TestValidationResponse:
    """Test ValidationResponse NamedTuple."""

    def test_valid_response(self):
        """Test valid ValidationResponse."""
        response = ValidationResponse(is_valid=True, params=None, errors=None)
        assert response.is_valid is True
        assert response.params is None
        assert response.errors is None

    def test_with_params_and_errors(self):
        """Test ValidationResponse with params and errors."""
        response = ValidationResponse(
            is_valid=True,
            params=SearchQueryParams(query="test"),
            errors=None,
        )
        assert response.is_valid is True
        assert response.params is not None
        assert response.params.query == "test"

    def test_invalid_with_errors(self):
        """Test invalid ValidationResponse with errors."""
        response = ValidationResponse(
            is_valid=False,
            params=None,
            errors="Parameter validation failed",
        )
        assert response.is_valid is False
        assert response.params is None
        assert response.errors == "Parameter validation failed"


class TestValidateMcpParams:
    """Test validate_mcp_params helper function."""

    def test_valid_params(self):
        """Test successful validation of valid parameters."""
        result = validate_mcp_params(SearchQueryParams, query="test query")
        assert result.is_valid is True
        assert result.params is not None
        assert result.params.query == "test query"
        assert result.errors is None

    def test_invalid_params(self):
        """Test validation failure with invalid parameters."""
        result = validate_mcp_params(SearchQueryParams, query="", limit=-1)
        assert result.is_valid is False
        assert result.params is None
        assert result.errors is not None
        assert "Parameter validation failed" in result.errors

    def test_partial_params_use_defaults(self):
        """Test partial params with defaults filled in."""
        result = validate_mcp_params(SearchQueryParams, query="test")
        assert result.is_valid is True
        assert result.params.limit == 10
        assert result.params.min_score == 0.7


class TestDeserialization:
    """Test model serialization and deserialization."""

    def test_model_dump(self):
        """Test model_dump serialization."""
        params = WorkingDirectoryParams(working_directory="/tmp")
        data = params.model_dump()
        assert data == {"working_directory": "/tmp"}

    def test_model_dump_exclude_none(self):
        """Test model_dump with exclude_none."""
        params = ProjectContextParams(project=None)
        data = params.model_dump(exclude_none=True)
        assert data == {}

    def test_model_dump_json(self):
        """Test model_dump_json serialization."""
        params = SearchLimitParams(limit=50, offset=10)
        json_str = params.model_dump_json()
        assert "limit" in json_str
        assert "50" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])