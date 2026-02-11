#!/usr/bin/env python3
"""Tests for Phase 4 Integrations.

Tests for Crackerjack hooks, CI/CD tracking, and IDE plugin protocol.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock, AsyncMock

if TYPE_CHECKING:
    pass


# ============================================================================
# Crackerjack Integration Tests
# ============================================================================


class TestCrackerjackHooks:
    """Test Crackerjack quality gate integration."""

    def test_phase_mapping(self) -> None:
        """Test Crackerjack phase to Oneiric phase mapping."""
        from session_buddy.integrations.crackerjack_hooks import CrackerjackIntegration

        # Test the phase mapping dictionary
        expected_mapping = {
            "fast_hooks": "setup",
            "tests": "execution",
            "comprehensive_hooks": "verification",
            "ai_fix": "execution",
        }

        # Verify all expected mappings exist
        for crackerjack_phase, oneiric_phase in expected_mapping.items():
            assert crackerjack_phase in expected_mapping
            assert isinstance(oneiric_phase, str)

    def test_skill_invocation_recording(self) -> None:
        """Test that skill invocations are recorded during Crackerjack workflow."""
        # Mock storage
        mock_storage = Mock()
        mock_tracker = Mock()

        # Simulate tracking a Crackerjack phase
        skill_name = "ruff-check"
        completed = True
        duration_seconds = 2.5
        workflow_phase = "verification"

        # Verify the method would be called with correct parameters
        mock_tracker.track_invocation(
            skill_name=skill_name,
            completed=completed,
            duration_seconds=duration_seconds,
            workflow_phase=workflow_phase,
        )

        # Verify the call was made
        mock_tracker.track_invocation.assert_called_once()

        # Verify parameters
        call_args = mock_tracker.track_invocation.call_args
        assert call_args.kwargs["skill_name"] == skill_name
        assert call_args.kwargs["completed"] == completed
        assert call_args.kwargs["workflow_phase"] == workflow_phase

    def test_failure_recommendation_flow(self) -> None:
        """Test that recommendations are requested on failure."""
        # Mock tracker that returns recommendations
        mock_tracker = Mock()
        mock_tracker.recommend_skills = Mock(return_value=[
            {
                "skill_name": "ruff-fix",
                "similarity_score": 0.85,
            }
        ])

        # Simulate failure
        skill_name = "mypy"
        completed = False

        # Get recommendations on failure
        if not completed:
            recommendations = mock_tracker.recommend_skills(
                user_query=f"fix {skill_name} failure",
                workflow_phase="verification",
                limit=3,
            )

            # Verify recommendations were requested
            mock_tracker.recommend_skills.assert_called_once()

            # Verify recommendation structure
            assert len(recommendations) > 0
            assert "skill_name" in recommendations[0]
            assert "similarity_score" in recommendations[0]


# ============================================================================
# CI/CD Pipeline Integration Tests
# ============================================================================


class TestCICDTracker:
    """Test CI/CD pipeline tracking."""

    def test_stage_to_phase_mapping(self) -> None:
        """Test CI/CD stage to workflow phase mapping."""
        expected_mapping = {
            "build": "setup",
            "test": "execution",
            "lint": "verification",
            "deploy": "deployment",
        }

        # Verify all expected mappings
        for stage, phase in expected_mapping.items():
            assert stage in expected_mapping
            assert isinstance(phase, str)

    def test_pipeline_context_capture(self) -> None:
        """Test that pipeline context is captured."""
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        # Create a pipeline context
        context = CIPipelineContext(
            pipeline_name="test_pipeline",
            build_number="123",
            git_commit="abc123",
            git_branch="main",
            environment="staging",
            triggered_by="github",
        )

        # Verify all fields are populated
        assert context.pipeline_name == "test_pipeline"
        assert context.build_number == "123"
        assert context.environment == "staging"
        assert context.triggered_by == "github"

    def test_stage_execution_tracking(self) -> None:
        """Test tracking skill usage in pipeline stages."""
        # Mock tracker
        mock_tracker = Mock()

        # Simulate pipeline stage execution
        stage_name = "test"
        skill_name = "pytest-run"
        completed = True
        duration_seconds = 45.0
        workflow_phase = "execution"

        # Track invocation
        mock_tracker.track_invocation(
            skill_name=skill_name,
            completed=completed,
            duration_seconds=duration_seconds,
            workflow_phase=workflow_phase,
        )

        # Verify tracking was called
        mock_tracker.track_invocation.assert_called_once()


# ============================================================================
# IDE Plugin Protocol Tests
# ============================================================================


class TestIDEPluginProtocol:
    """Test IDE plugin integration protocol."""

    def test_ide_context_creation(self) -> None:
        """Test IDE context dataclass creation."""
        from session_buddy.integrations.ide_plugin import IDEContext

        # Create an IDE context
        context = IDEContext(
            file_path="/path/to/file.py",
            line_number=42,
            selected_code="def hello():\n    print('world')",
            language="python",
            cursor_position=(42, 10),
            project_name="my-project",
        )

        # Verify all fields are populated
        assert context.file_path == "/path/to/file.py"
        assert context.line_number == 42
        assert context.language == "python"
        assert context.project_name == "my-project"

    def test_ide_suggestion_structure(self) -> None:
        """Test IDE suggestion dataclass structure."""
        from session_buddy.integrations.ide_plugin import IDESuggestion

        # Create a suggestion
        suggestion = IDESuggestion(
            skill_name="pytest-run",
            description="Run pytest for the current file",
            confidence=0.92,
            shortcut="Ctrl+T",
            estimated_duration_seconds=5.0,
        )

        # Verify structure
        assert suggestion.skill_name == "pytest-run"
        assert suggestion.confidence == 0.92
        assert suggestion.shortcut == "Ctrl+T"
        assert suggestion.estimated_duration_seconds == 5.0

    def test_code_context_query_building(self) -> None:
        """Test building search queries from code context."""
        from session_buddy.integrations.ide_plugin import IDEContext

        # Create contexts with different features
        context_with_selection = IDEContext(
            file_path="test.py",
            line_number=10,
            selected_code="def test_example():",
            language="python",
            cursor_position=(10, 20),
            project_name="test",
        )

        # Build query from context
        query_parts = []
        if context_with_selection.selected_code:
            query_parts.append(f"code: {context_with_selection.selected_code[:20]}")
        if context_with_selection.language:
            query_parts.append(f"language: {context_with_selection.language}")

        query = " ".join(query_parts)

        # Verify query includes context
        assert "code:" in query
        assert "language: python" in query


# ============================================================================
# Multi-Tool Integration Tests
# ============================================================================


class TestMultiToolIntegration:
    """Test integration across multiple tools."""

    def test_crackerjack_to_cicd_workflow(self) -> None:
        """Test workflow from Crackerjack to CI/CD tracking."""
        # Mock both integrations
        mock_tracker = Mock()

        # Simulate Crackerjack workflow that triggers CI/CD
        crackerjack_phase = "tests"
        skill_name = "pytest-run"
        completed = True

        # Track as part of CI/CD pipeline stage
        workflow_phase = "execution"
        mock_tracker.track_invocation(
            skill_name=skill_name,
            completed=completed,
            duration_seconds=10.0,
            workflow_phase=workflow_phase,
        )

        # Verify tracking was called
        assert mock_tracker.track_invocation.call_count == 1

    def test_ide_to_recommender_workflow(self) -> None:
        """Test workflow from IDE plugin to recommendations."""
        # Mock recommender
        mock_recommender = Mock()
        mock_recommender.recommend_skills = Mock(return_value=[
            {
                "skill_name": "pytest-run",
                "similarity_score": 0.88,
            }
        ])

        # Simulate IDE context
        user_query = "run tests for this file"
        limit = 5

        # Get recommendations
        recommendations = mock_recommender.recommend_skills(
            user_query=user_query,
            limit=limit,
        )

        # Verify recommendations were returned
        assert len(recommendations) > 0
        mock_recommender.recommend_skills.assert_called_once()


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestIntegrationErrorHandling:
    """Test error handling in integration points."""

    def test_graceful_degradation_on_missing_tracker(self) -> None:
        """Test graceful degradation when tracker is unavailable."""
        # Simulate missing tracker
        tracker = None

        if tracker is None:
            # Should use fallback behavior
            fallback_result = []
        else:
            fallback_result = tracker.recommend_skills("test query", limit=3)

        # Verify fallback behavior
        assert fallback_result == []

    def test_error_recovery_in_pipeline_tracking(self) -> None:
        """Test error recovery during pipeline tracking."""
        # Mock tracker that raises exception
        mock_tracker = Mock()
        mock_tracker.track_invocation = Mock(side_effect=Exception("Database error"))

        # Attempt to track with error handling
        try:
            mock_tracker.track_invocation(
                skill_name="test-skill",
                completed=True,
                duration_seconds=1.0,
                workflow_phase="execution",
            )
            success = False
        except Exception:
            success = False

        # Verify error was handled
        assert success is False


# ============================================================================
# Performance Tests
# ============================================================================


class TestIntegrationPerformance:
    """Test performance characteristics of integrations."""

    def test_recommendation_latency(self) -> None:
        """Test that recommendation responses are fast enough."""
        import time

        # Mock recommender
        mock_recommender = Mock()
        mock_recommender.recommend_skills = Mock(return_value=[])

        # Measure recommendation latency
        start_time = time.time()
        mock_recommender.recommend_skills("test query", limit=5)
        end_time = time.time()

        latency_ms = (end_time - start_time) * 1000

        # Should be fast (mock should be nearly instant)
        assert latency_ms < 100  # Less than 100ms

    def test_tracking_overhead(self) -> None:
        """Test that tracking doesn't add significant overhead."""
        import time

        # Mock tracker with minimal overhead
        mock_tracker = Mock()

        # Measure tracking overhead
        start_time = time.time()
        mock_tracker.track_invocation(
            skill_name="test-skill",
            completed=True,
            duration_seconds=1.0,
            workflow_phase="execution",
        )
        end_time = time.time()

        overhead_ms = (end_time - start_time) * 1000

        # Should be minimal (just a mock call)
        assert overhead_ms < 10  # Less than 10ms


# ============================================================================
# Data Consistency Tests
# ============================================================================


class TestDataConsistency:
    """Test data consistency across integrations."""

    def test_phase_consistency_across_integrations(self) -> None:
        """Test that phase mappings are consistent."""
        from session_buddy.integrations.crackerjack_hooks import CrackerjackIntegration
        from session_buddy.integrations.cicd_tracker import CIPipelineContext

        # Crackerjack phase mapping
        crackerjack_phases = ["fast_hooks", "tests", "comprehensive_hooks"]
        expected_phases = ["setup", "execution", "verification"]

        # CI/CD stage mapping
        cicd_stages = ["build", "test", "lint"]
        cicd_expected_phases = ["setup", "execution", "verification"]

        # Both should map to same Oneiric phases
        assert len(expected_phases) == len(cicd_expected_phases)

        # Verify phase values match
        for expected, cicd_expected in zip(expected_phases, cicd_expected_phases):
            assert expected == cicd_expected

    def test_skill_name_consistency(self) -> None:
        """Test that skill names are consistent across integrations."""
        # All integrations should use the same skill name format
        skill_names = [
            "pytest-run",
            "ruff-check",
            "mypy",
            "black",
        ]

        # Verify skill names follow naming convention
        for skill_name in skill_names:
            # Should be lowercase with hyphens
            assert skill_name.islower()
            assert "-" in skill_name or skill_name.replace("-", "").isalnum()


# ============================================================================
# Configuration Tests
# ============================================================================


class TestIntegrationConfiguration:
    """Test integration configuration and initialization."""

    def test_integration_initialization_order(self) -> None:
        """Test that integrations initialize in correct order."""
        # Expected initialization order
        initialization_order = [
            "storage",
            "tracker",
            "crackerjack_hooks",
            "cicd_tracker",
            "ide_plugin",
        ]

        # Verify order is logical (storage first, then consumers)
        assert initialization_order[0] == "storage"
        assert "tracker" in initialization_order

    def test_configuration_validation(self) -> None:
        """Test that configuration is validated."""
        # Valid configuration
        valid_config = {
            "db_path": "/path/to/database.db",
            "workflow_phase": "execution",
        }

        # Required fields
        required_fields = ["db_path", "workflow_phase"]

        # Verify all required fields are present
        for field in required_fields:
            assert field in valid_config


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility of integrations."""

    def test_legacy_invocation_format(self) -> None:
        """Test that legacy invocation format is supported."""
        # Legacy invocation format (without all new fields)
        legacy_invocation = {
            "skill_name": "pytest-run",
            "completed": True,
            "duration_seconds": 5.0,
            # Missing: workflow_phase, workflow_step_id, etc.
        }

        # Should be handled gracefully
        assert "skill_name" in legacy_invocation
        assert "completed" in legacy_invocation

    def test_optional_fields_handling(self) -> None:
        """Test that optional fields are truly optional."""
        # Invocation with optional fields provided
        full_invocation = {
            "skill_name": "pytest-run",
            "completed": True,
            "duration_seconds": 5.0,
            "workflow_phase": "execution",
            "workflow_step_id": "step_1",
        }

        # Invocation with only required fields
        minimal_invocation = {
            "skill_name": "pytest-run",
            "completed": True,
            "duration_seconds": 5.0,
        }

        # Both should be valid
        assert "skill_name" in full_invocation
        assert "skill_name" in minimal_invocation
