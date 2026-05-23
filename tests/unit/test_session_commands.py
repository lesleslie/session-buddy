#!/usr/bin/env python3
"""Tests for session_buddy/session_commands.py"""

from __future__ import annotations

import pytest

from session_buddy.session_commands import SESSION_COMMANDS


class TestSessionCommandsExists:
    """Test that SESSION_COMMANDS dictionary exists and has correct structure."""

    def test_session_commands_is_a_dict(self):
        """SESSION_COMMANDS should be a dictionary."""
        assert isinstance(SESSION_COMMANDS, dict)

    def test_session_commands_is_not_empty(self):
        """SESSION_COMMANDS should contain command definitions."""
        assert len(SESSION_COMMANDS) > 0


class TestSessionCommandsKeys:
    """Test that all expected command keys are present."""

    def test_all_expected_command_keys_present(self):
        """All 14 expected session command keys should be present."""
        expected_keys = {
            "init",
            "checkpoint",
            "end",
            "status",
            "permissions",
            "reflect",
            "quick-search",
            "search-summary",
            "reflection-stats",
            "crackerjack-run",
            "crackerjack-history",
            "crackerjack-metrics",
            "crackerjack-patterns",
        }
        assert set(SESSION_COMMANDS.keys()) == expected_keys

    def test_init_command_exists(self):
        """Init command should exist."""
        assert "init" in SESSION_COMMANDS

    def test_checkpoint_command_exists(self):
        """Checkpoint command should exist."""
        assert "checkpoint" in SESSION_COMMANDS

    def test_end_command_exists(self):
        """End command should exist."""
        assert "end" in SESSION_COMMANDS

    def test_status_command_exists(self):
        """Status command should exist."""
        assert "status" in SESSION_COMMANDS

    def test_permissions_command_exists(self):
        """Permissions command should exist."""
        assert "permissions" in SESSION_COMMANDS

    def test_reflect_command_exists(self):
        """Reflect command should exist."""
        assert "reflect" in SESSION_COMMANDS

    def test_quick_search_command_exists(self):
        """Quick-search command should exist."""
        assert "quick-search" in SESSION_COMMANDS

    def test_search_summary_command_exists(self):
        """Search-summary command should exist."""
        assert "search-summary" in SESSION_COMMANDS

    def test_reflection_stats_command_exists(self):
        """Reflection-stats command should exist."""
        assert "reflection-stats" in SESSION_COMMANDS

    def test_crackerjack_run_command_exists(self):
        """Crackerjack-run command should exist."""
        assert "crackerjack-run" in SESSION_COMMANDS

    def test_crackerjack_history_command_exists(self):
        """Crackerjack-history command should exist."""
        assert "crackerjack-history" in SESSION_COMMANDS

    def test_crackerjack_metrics_command_exists(self):
        """Crackerjack-metrics command should exist."""
        assert "crackerjack-metrics" in SESSION_COMMANDS

    def test_crackerjack_patterns_command_exists(self):
        """Crackerjack-patterns command should exist."""
        assert "crackerjack-patterns" in SESSION_COMMANDS


class TestSessionCommandsValues:
    """Test that command values are non-empty strings."""

    @pytest.mark.parametrize("command_key", list(SESSION_COMMANDS.keys()))
    def test_command_value_is_string(self, command_key):
        """Each command value should be a string."""
        assert isinstance(SESSION_COMMANDS[command_key], str)

    @pytest.mark.parametrize("command_key", list(SESSION_COMMANDS.keys()))
    def test_command_value_is_not_empty(self, command_key):
        """Each command value should be non-empty."""
        assert len(SESSION_COMMANDS[command_key]) > 0

    @pytest.mark.parametrize("command_key", list(SESSION_COMMANDS.keys()))
    def test_command_value_has_content(self, command_key):
        """Each command value should contain meaningful content (at least 50 chars)."""
        assert len(SESSION_COMMANDS[command_key]) >= 50


class TestInitCommand:
    """Tests for the 'init' command."""

    def test_init_command_structure(self):
        """Init command should have proper structure."""
        init_cmd = SESSION_COMMANDS["init"]
        assert isinstance(init_cmd, str)
        assert len(init_cmd) > 0

    def test_init_command_contains_session_initialization(self):
        """Init command should mention session initialization."""
        init_cmd = SESSION_COMMANDS["init"]
        assert "Session Initialization" in init_cmd or "Initialize" in init_cmd

    def test_init_command_contains_features(self):
        """Init command should describe key features."""
        init_cmd = SESSION_COMMANDS["init"]
        assert "features" in init_cmd.lower() or "Key" in init_cmd

    def test_init_command_mentions_storage_options(self):
        """Init command should mention storage options."""
        init_cmd = SESSION_COMMANDS["init"]
        assert "file" in init_cmd.lower() or "storage" in init_cmd.lower()

    def test_init_command_mentions_vector_database(self):
        """Init command should mention vector database."""
        init_cmd = SESSION_COMMANDS["init"]
        assert "vector" in init_cmd.lower() or "embedding" in init_cmd.lower()

    def test_init_command_mentions_knowledge_graph(self):
        """Init command should mention knowledge graph."""
        init_cmd = SESSION_COMMANDS["init"]
        assert "knowledge graph" in init_cmd.lower() or "DuckPGQ" in init_cmd

    def test_init_command_mentions_local_embeddings(self):
        """Init command should mention local embeddings (ONNX)."""
        init_cmd = SESSION_COMMANDS["init"]
        assert "onnx" in init_cmd.lower() or "local" in init_cmd.lower()


class TestCheckpointCommand:
    """Tests for the 'checkpoint' command."""

    def test_checkpoint_command_structure(self):
        """Checkpoint command should have proper structure."""
        checkpoint_cmd = SESSION_COMMANDS["checkpoint"]
        assert isinstance(checkpoint_cmd, str)
        assert len(checkpoint_cmd) > 0

    def test_checkpoint_command_contains_session_checkpoint(self):
        """Checkpoint command should mention session checkpoint."""
        checkpoint_cmd = SESSION_COMMANDS["checkpoint"]
        assert "checkpoint" in checkpoint_cmd.lower()

    def test_checkpoint_command_mentions_quality_score(self):
        """Checkpoint command should mention quality score."""
        checkpoint_cmd = SESSION_COMMANDS["checkpoint"]
        assert "quality" in checkpoint_cmd.lower() or "score" in checkpoint_cmd.lower()

    def test_checkpoint_command_mentions_cleanup(self):
        """Checkpoint command should mention cleanup operations."""
        checkpoint_cmd = SESSION_COMMANDS["checkpoint"]
        assert "cleanup" in checkpoint_cmd.lower() or "clean" in checkpoint_cmd.lower()

    def test_checkpoint_command_mentions_optimization(self):
        """Checkpoint command should mention optimization."""
        checkpoint_cmd = SESSION_COMMANDS["checkpoint"]
        assert "optim" in checkpoint_cmd.lower()

    def test_checkpoint_command_mentions_recommendations(self):
        """Checkpoint command should mention recommendations."""
        checkpoint_cmd = SESSION_COMMANDS["checkpoint"]
        assert "recommend" in checkpoint_cmd.lower()


class TestEndCommand:
    """Tests for the 'end' command."""

    def test_end_command_structure(self):
        """End command should have proper structure."""
        end_cmd = SESSION_COMMANDS["end"]
        assert isinstance(end_cmd, str)
        assert len(end_cmd) > 0

    def test_end_command_contains_session_end(self):
        """End command should mention session end."""
        end_cmd = SESSION_COMMANDS["end"]
        assert "Session End" in end_cmd or "session" in end_cmd.lower()

    def test_end_command_mentions_cleanup(self):
        """End command should mention cleanup."""
        end_cmd = SESSION_COMMANDS["end"]
        assert "cleanup" in end_cmd.lower() or "clean" in end_cmd.lower()

    def test_end_command_mentions_handoff(self):
        """End command should mention handoff documentation."""
        end_cmd = SESSION_COMMANDS["end"]
        assert "handoff" in end_cmd.lower() or "documentation" in end_cmd.lower()

    def test_end_command_mentions_reflections(self):
        """End command should mention reflections storage."""
        end_cmd = SESSION_COMMANDS["end"]
        assert "reflection" in end_cmd.lower()

    def test_end_command_mentions_git_automatic(self):
        """End command should mention automatic git behavior."""
        end_cmd = SESSION_COMMANDS["end"]
        assert "git" in end_cmd.lower() or "automatic" in end_cmd.lower()


class TestStatusCommand:
    """Tests for the 'status' command."""

    def test_status_command_structure(self):
        """Status command should have proper structure."""
        status_cmd = SESSION_COMMANDS["status"]
        assert isinstance(status_cmd, str)
        assert len(status_cmd) > 0

    def test_status_command_contains_session_status(self):
        """Status command should mention session status."""
        status_cmd = SESSION_COMMANDS["status"]
        assert "status" in status_cmd.lower()

    def test_status_command_mentions_quality_score(self):
        """Status command should mention quality score."""
        status_cmd = SESSION_COMMANDS["status"]
        assert "quality" in status_cmd.lower() or "score" in status_cmd.lower()

    def test_status_command_mentions_storage_adapters(self):
        """Status command should mention storage adapters."""
        status_cmd = SESSION_COMMANDS["status"]
        assert "storage" in status_cmd.lower() or "adapter" in status_cmd.lower()

    def test_status_command_mentions_database(self):
        """Status command should mention database status."""
        status_cmd = SESSION_COMMANDS["status"]
        assert "database" in status_cmd.lower() or "db" in status_cmd.lower()

    def test_status_command_mentions_git_status(self):
        """Status command should mention git status."""
        status_cmd = SESSION_COMMANDS["status"]
        assert "git" in status_cmd.lower()


class TestPermissionsCommand:
    """Tests for the 'permissions' command."""

    def test_permissions_command_structure(self):
        """Permissions command should have proper structure."""
        permissions_cmd = SESSION_COMMANDS["permissions"]
        assert isinstance(permissions_cmd, str)
        assert len(permissions_cmd) > 0

    def test_permissions_command_contains_permissions(self):
        """Permissions command should mention permissions."""
        permissions_cmd = SESSION_COMMANDS["permissions"]
        assert "permission" in permissions_cmd.lower()

    def test_permissions_command_mentions_trust(self):
        """Permissions command should mention trust operations."""
        permissions_cmd = SESSION_COMMANDS["permissions"]
        assert "trust" in permissions_cmd.lower()

    def test_permissions_command_lists_available_actions(self):
        """Permissions command should list available actions."""
        permissions_cmd = SESSION_COMMANDS["permissions"]
        assert "status" in permissions_cmd or "action" in permissions_cmd.lower()


class TestReflectCommand:
    """Tests for the 'reflect' command."""

    def test_reflect_command_structure(self):
        """Reflect command should have proper structure."""
        reflect_cmd = SESSION_COMMANDS["reflect"]
        assert isinstance(reflect_cmd, str)
        assert len(reflect_cmd) > 0

    def test_reflect_command_contains_reflect(self):
        """Reflect command should mention reflection."""
        reflect_cmd = SESSION_COMMANDS["reflect"]
        assert "reflection" in reflect_cmd.lower() or "reflect" in reflect_cmd.lower()

    def test_reflect_command_mentions_embedding(self):
        """Reflect command should mention embedding for search."""
        reflect_cmd = SESSION_COMMANDS["reflect"]
        assert "embedding" in reflect_cmd.lower() or "semantic" in reflect_cmd.lower()

    def test_reflect_command_mentions_tags(self):
        """Reflect command should mention tagging for categorization."""
        reflect_cmd = SESSION_COMMANDS["reflect"]
        assert "tag" in reflect_cmd.lower()

    def test_reflect_command_mentions_team_knowledge(self):
        """Reflect command should mention team knowledge sharing."""
        reflect_cmd = SESSION_COMMANDS["reflect"]
        assert "team" in reflect_cmd.lower() or "knowledge" in reflect_cmd.lower()


class TestQuickSearchCommand:
    """Tests for the 'quick-search' command."""

    def test_quick_search_command_structure(self):
        """Quick-search command should have proper structure."""
        quick_search_cmd = SESSION_COMMANDS["quick-search"]
        assert isinstance(quick_search_cmd, str)
        assert len(quick_search_cmd) > 0

    def test_quick_search_command_contains_quick_search(self):
        """Quick-search command should mention quick search."""
        quick_search_cmd = SESSION_COMMANDS["quick-search"]
        assert "quick" in quick_search_cmd.lower() or "search" in quick_search_cmd.lower()

    def test_quick_search_command_mentions_semantic_search(self):
        """Quick-search command should mention semantic search."""
        quick_search_cmd = SESSION_COMMANDS["quick-search"]
        assert "semantic" in quick_search_cmd.lower() or "ai" in quick_search_cmd.lower()

    def test_quick_search_command_mentions_cross_project(self):
        """Quick-search command should mention cross-project search."""
        quick_search_cmd = SESSION_COMMANDS["quick-search"]
        assert "cross" in quick_search_cmd.lower() or "project" in quick_search_cmd.lower()


class TestSearchSummaryCommand:
    """Tests for the 'search-summary' command."""

    def test_search_summary_command_structure(self):
        """Search-summary command should have proper structure."""
        search_summary_cmd = SESSION_COMMANDS["search-summary"]
        assert isinstance(search_summary_cmd, str)
        assert len(search_summary_cmd) > 0

    def test_search_summary_command_contains_search_summary(self):
        """Search-summary command should mention search summary."""
        search_summary_cmd = SESSION_COMMANDS["search-summary"]
        assert "search" in search_summary_cmd.lower() or "summary" in search_summary_cmd.lower()

    def test_search_summary_command_mentions_pattern_analysis(self):
        """Search-summary command should mention pattern analysis."""
        search_summary_cmd = SESSION_COMMANDS["search-summary"]
        assert "pattern" in search_summary_cmd.lower() or "analysis" in search_summary_cmd.lower()

    def test_search_summary_command_mentions_knowledge_gaps(self):
        """Search-summary command should mention knowledge gaps."""
        search_summary_cmd = SESSION_COMMANDS["search-summary"]
        assert "knowledge" in search_summary_cmd.lower() or "gap" in search_summary_cmd.lower()


class TestReflectionStatsCommand:
    """Tests for the 'reflection-stats' command."""

    def test_reflection_stats_command_structure(self):
        """Reflection-stats command should have proper structure."""
        reflection_stats_cmd = SESSION_COMMANDS["reflection-stats"]
        assert isinstance(reflection_stats_cmd, str)
        assert len(reflection_stats_cmd) > 0

    def test_reflection_stats_command_contains_reflection_stats(self):
        """Reflection-stats command should mention reflection stats."""
        reflection_stats_cmd = SESSION_COMMANDS["reflection-stats"]
        assert "reflection" in reflection_stats_cmd.lower() or "stats" in reflection_stats_cmd.lower()

    def test_reflection_stats_command_mentions_database_health(self):
        """Reflection-stats command should mention database health."""
        reflection_stats_cmd = SESSION_COMMANDS["reflection-stats"]
        assert "database" in reflection_stats_cmd.lower() or "health" in reflection_stats_cmd.lower()

    def test_reflection_stats_command_mentions_usage_patterns(self):
        """Reflection-stats command should mention usage patterns."""
        reflection_stats_cmd = SESSION_COMMANDS["reflection-stats"]
        assert "usage" in reflection_stats_cmd.lower() or "pattern" in reflection_stats_cmd.lower()


class TestCrackerjackRunCommand:
    """Tests for the 'crackerjack-run' command."""

    def test_crackerjack_run_command_structure(self):
        """Crackerjack-run command should have proper structure."""
        cj_run_cmd = SESSION_COMMANDS["crackerjack-run"]
        assert isinstance(cj_run_cmd, str)
        assert len(cj_run_cmd) > 0

    def test_crackerjack_run_command_contains_crackerjack_run(self):
        """Crackerjack-run command should mention crackerjack run."""
        cj_run_cmd = SESSION_COMMANDS["crackerjack-run"]
        assert "crackerjack" in cj_run_cmd.lower() or "run" in cj_run_cmd.lower()

    def test_crackerjack_run_command_mentions_memory_integration(self):
        """Crackerjack-run command should mention memory integration."""
        cj_run_cmd = SESSION_COMMANDS["crackerjack-run"]
        assert "memory" in cj_run_cmd.lower() or "integration" in cj_run_cmd.lower()

    def test_crackerjack_run_command_lists_available_commands(self):
        """Crackerjack-run command should list available commands."""
        cj_run_cmd = SESSION_COMMANDS["crackerjack-run"]
        # Should mention at least one of: analyze, check, test, lint, security, complexity
        commands_mentioned = any(
            cmd in cj_run_cmd.lower()
            for cmd in ["analyze", "check", "test", "lint", "security", "complexity"]
        )
        assert commands_mentioned


class TestCrackerjackHistoryCommand:
    """Tests for the 'crackerjack-history' command."""

    def test_crackerjack_history_command_structure(self):
        """Crackerjack-history command should have proper structure."""
        cj_history_cmd = SESSION_COMMANDS["crackerjack-history"]
        assert isinstance(cj_history_cmd, str)
        assert len(cj_history_cmd) > 0

    def test_crackerjack_history_command_contains_history(self):
        """Crackerjack-history command should mention history."""
        cj_history_cmd = SESSION_COMMANDS["crackerjack-history"]
        assert "history" in cj_history_cmd.lower() or "crackerjack" in cj_history_cmd.lower()

    def test_crackerjack_history_command_mentions_trends(self):
        """Crackerjack-history command should mention trends."""
        cj_history_cmd = SESSION_COMMANDS["crackerjack-history"]
        assert "trend" in cj_history_cmd.lower()

    def test_crackerjack_history_command_mentions_quality_trends(self):
        """Crackerjack-history command should mention quality trends."""
        cj_history_cmd = SESSION_COMMANDS["crackerjack-history"]
        assert "quality" in cj_history_cmd.lower() or "trend" in cj_history_cmd.lower()


class TestCrackerjackMetricsCommand:
    """Tests for the 'crackerjack-metrics' command."""

    def test_crackerjack_metrics_command_structure(self):
        """Crackerjack-metrics command should have proper structure."""
        cj_metrics_cmd = SESSION_COMMANDS["crackerjack-metrics"]
        assert isinstance(cj_metrics_cmd, str)
        assert len(cj_metrics_cmd) > 0

    def test_crackerjack_metrics_command_contains_metrics(self):
        """Crackerjack-metrics command should mention metrics."""
        cj_metrics_cmd = SESSION_COMMANDS["crackerjack-metrics"]
        assert "metric" in cj_metrics_cmd.lower() or "quality" in cj_metrics_cmd.lower()

    def test_crackerjack_metrics_command_mentions_trend_analysis(self):
        """Crackerjack-metrics command should mention trend analysis."""
        cj_metrics_cmd = SESSION_COMMANDS["crackerjack-metrics"]
        assert "trend" in cj_metrics_cmd.lower() or "analysis" in cj_metrics_cmd.lower()

    def test_crackerjack_metrics_command_mentions_visualizations(self):
        """Crackerjack-metrics command should mention visualizations."""
        cj_metrics_cmd = SESSION_COMMANDS["crackerjack-metrics"]
        assert "visual" in cj_metrics_cmd.lower() or "graph" in cj_metrics_cmd.lower()


class TestCrackerjackPatternsCommand:
    """Tests for the 'crackerjack-patterns' command."""

    def test_crackerjack_patterns_command_structure(self):
        """Crackerjack-patterns command should have proper structure."""
        cj_patterns_cmd = SESSION_COMMANDS["crackerjack-patterns"]
        assert isinstance(cj_patterns_cmd, str)
        assert len(cj_patterns_cmd) > 0

    def test_crackerjack_patterns_command_contains_patterns(self):
        """Crackerjack-patterns command should mention patterns."""
        cj_patterns_cmd = SESSION_COMMANDS["crackerjack-patterns"]
        assert "pattern" in cj_patterns_cmd.lower() or "analysis" in cj_patterns_cmd.lower()

    def test_crackerjack_patterns_command_mentions_failure_detection(self):
        """Crackerjack-patterns command should mention failure detection."""
        cj_patterns_cmd = SESSION_COMMANDS["crackerjack-patterns"]
        assert "failure" in cj_patterns_cmd.lower() or "detect" in cj_patterns_cmd.lower()

    def test_crackerjack_patterns_command_mentions_recommendations(self):
        """Crackerjack-patterns command should mention recommendations."""
        cj_patterns_cmd = SESSION_COMMANDS["crackerjack-patterns"]
        assert "recommend" in cj_patterns_cmd.lower()


class TestCommandDocumentationStructure:
    """Tests for documentation structure across all commands."""

    @pytest.mark.parametrize("command_key", list(SESSION_COMMANDS.keys()))
    def test_all_commands_start_with_header(self, command_key):
        """Each command should start with a header comment (lines starting with #)."""
        command_value = SESSION_COMMANDS[command_key]
        lines = command_value.strip().split("\n")
        # At least the first line should be a header
        assert any(line.strip().startswith("#") for line in lines[:3])

    @pytest.mark.parametrize("command_key", list(SESSION_COMMANDS.keys()))
    def test_all_commands_contain_description(self, command_key):
        """Each command should have a description section."""
        command_value = SESSION_COMMANDS[command_key]
        # Should have multiple lines of content
        assert "\n" in command_value

    @pytest.mark.parametrize("command_key", list(SESSION_COMMANDS.keys()))
    def test_all_commands_use_bullet_points(self, command_key):
        """Each command should use bullet points (dash or asterisk) for features."""
        command_value = SESSION_COMMANDS[command_key]
        # Should contain bullet-like formatting
        assert "-" in command_value or "*" in command_value

    @pytest.mark.parametrize("command_key", list(SESSION_COMMANDS.keys()))
    def test_all_commands_contain_key_features_section(self, command_key):
        """Each command should mention features section or similar structure."""
        command_value = SESSION_COMMANDS[command_key]
        # Most commands mention Key Features or Features or have categorized sections
        lower_value = command_value.lower()
        has_features = any(
            phrase in lower_value
            for phrase in [
                "key features",
                "features:",
                "available",
                "command",
                "metric categories",
                "trend analysis",
                "pattern detection",
                "failure classification",
                "insights provided",
            ]
        )
        assert has_features, f"Command {command_key} should mention features section"


class TestCrackerjackFamilyCommands:
    """Tests for the Crackerjack family of commands."""

    def test_all_crackerjack_commands_mention_quality(self):
        """All crackerjack commands should mention quality metrics."""
        crackerjack_commands = [
            SESSION_COMMANDS["crackerjack-run"],
            SESSION_COMMANDS["crackerjack-history"],
            SESSION_COMMANDS["crackerjack-metrics"],
            SESSION_COMMANDS["crackerjack-patterns"],
        ]
        for cmd in crackerjack_commands:
            assert "quality" in cmd.lower() or "metric" in cmd.lower()

    def test_all_crackerjack_commands_mention_analysis(self):
        """All crackerjack commands should mention analysis."""
        crackerjack_commands = [
            SESSION_COMMANDS["crackerjack-run"],
            SESSION_COMMANDS["crackerjack-history"],
            SESSION_COMMANDS["crackerjack-metrics"],
            SESSION_COMMANDS["crackerjack-patterns"],
        ]
        for cmd in crackerjack_commands:
            assert "analysis" in cmd.lower() or "analyze" in cmd.lower()


class TestSearchCommands:
    """Tests for the search-related commands."""

    def test_search_commands_mention_semantic_search(self):
        """Search commands should mention semantic/AI embeddings."""
        search_commands = [
            SESSION_COMMANDS["quick-search"],
            SESSION_COMMANDS["search-summary"],
        ]
        for cmd in search_commands:
            assert "semantic" in cmd.lower() or "ai" in cmd.lower() or "embedding" in cmd.lower()

    def test_search_commands_mention_cross_project(self):
        """Search commands should mention cross-project search."""
        search_commands = [
            SESSION_COMMANDS["quick-search"],
            SESSION_COMMANDS["search-summary"],
        ]
        for cmd in search_commands:
            assert "cross" in cmd.lower() or "project" in cmd.lower()


class TestSessionLifecycleCommands:
    """Tests for session lifecycle commands (init, checkpoint, end, status)."""

    def test_lifecycle_commands_mention_quality(self):
        """Lifecycle commands should mention quality scores."""
        lifecycle_commands = [
            SESSION_COMMANDS["init"],
            SESSION_COMMANDS["checkpoint"],
            SESSION_COMMANDS["end"],
            SESSION_COMMANDS["status"],
        ]
        for cmd in lifecycle_commands:
            assert "quality" in cmd.lower() or "score" in cmd.lower()

    def test_lifecycle_commands_mention_storage(self):
        """Lifecycle commands should mention storage."""
        lifecycle_commands = [
            SESSION_COMMANDS["init"],
            SESSION_COMMANDS["checkpoint"],
            SESSION_COMMANDS["end"],
            SESSION_COMMANDS["status"],
        ]
        for cmd in lifecycle_commands:
            assert "storage" in cmd.lower() or "database" in cmd.lower()


class TestCommandCompleteness:
    """Tests for overall completeness of the command set."""

    def test_has_all_required_commands(self):
        """Command set should have all required session management commands."""
        required_commands = {"init", "checkpoint", "end", "status"}
        assert required_commands.issubset(SESSION_COMMANDS.keys())

    def test_has_search_commands(self):
        """Command set should have search-related commands."""
        search_commands = {"quick-search", "search-summary", "reflection-stats"}
        assert search_commands.issubset(SESSION_COMMANDS.keys())

    def test_has_crackerjack_commands(self):
        """Command set should have crackerjack integration commands."""
        crackerjack_commands = {
            "crackerjack-run",
            "crackerjack-history",
            "crackerjack-metrics",
            "crackerjack-patterns",
        }
        assert crackerjack_commands.issubset(SESSION_COMMANDS.keys())

    def test_has_permissions_command(self):
        """Command set should have permissions management command."""
        assert "permissions" in SESSION_COMMANDS

    def test_has_reflect_command(self):
        """Command set should have reflect command."""
        assert "reflect" in SESSION_COMMANDS

    def test_total_command_count(self):
        """Should have exactly 13 session commands."""
        assert len(SESSION_COMMANDS) == 13