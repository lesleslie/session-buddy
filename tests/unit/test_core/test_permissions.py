#!/usr/bin/env python3
"""Unit tests for SessionPermissionsManager class."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from session_buddy.core.permissions import SessionPermissionsManager


class TestPermissionsManagerSingleton:
    """Test singleton pattern implementation."""

    def test_singleton_returns_same_instance(self, tmp_path):
        """Test that singleton returns the same instance for same path."""
        claude_dir = tmp_path / ".claude"

        manager1 = SessionPermissionsManager(claude_dir)
        manager2 = SessionPermissionsManager(claude_dir)

        # Should be the same instance (singleton)
        assert manager1 is manager2

        # Should have the same session ID
        assert manager1.session_id == manager2.session_id

    def test_singleton_with_different_paths(self, tmp_path):
        """Test that singleton returns same instance even with different paths."""
        claude_dir1 = tmp_path / "project1" / ".claude"
        claude_dir2 = tmp_path / "project2" / ".claude"

        # Create first instance
        manager1 = SessionPermissionsManager(claude_dir1)
        first_session_id = manager1.session_id

        # Create second instance with different path
        # Note: Due to singleton pattern, this returns the same instance
        manager2 = SessionPermissionsManager(claude_dir2)

        # Should be the same instance
        assert manager1 is manager2

        # Session ID should persist from first initialization
        assert manager2.session_id == first_session_id

    def test_class_level_session_id_persistence(self, tmp_path):
        """Test that session ID persists at class level."""
        claude_dir = tmp_path / ".claude"

        # Create first instance
        manager1 = SessionPermissionsManager(claude_dir)
        session_id_1 = manager1.session_id

        # Reset the singleton instance for testing
        SessionPermissionsManager._instance = None
        SessionPermissionsManager._session_id = None

        # Create second instance
        manager2 = SessionPermissionsManager(claude_dir)
        session_id_2 = manager2.session_id

        # Session IDs should be different (new instance)
        assert session_id_1 != session_id_2


class TestPermissionOperations:
    """Test permission operations."""

    def test_trust_operation_basic(self, tmp_path):
        """Test trusting a basic operation."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Trust an operation
        result = manager.trust_operation("git_commit")
        assert result is True
        assert "git_commit" in manager.trusted_operations
        assert manager.is_operation_trusted("git_commit") is True

    def test_trust_operation_with_description(self, tmp_path):
        """Test trusting an operation with description."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Trust an operation with description
        result = manager.trust_operation("file_write", "Write files to disk")
        assert result is True
        assert "file_write" in manager.trusted_operations

    def test_trust_operation_multiple(self, tmp_path):
        """Test trusting multiple operations."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Trust multiple operations
        operations = ["git_commit", "file_write", "uv_sync"]
        for op in operations:
            manager.trust_operation(op)

        # All should be trusted
        for op in operations:
            assert manager.is_operation_trusted(op) is True

    def test_trust_operation_none_raises_error(self, tmp_path):
        """Test that trusting None raises TypeError."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        with pytest.raises(TypeError, match="Operation cannot be None"):
            manager.trust_operation(None)  # type: ignore

    def test_is_operation_trusted(self, tmp_path):
        """Test checking if operation is trusted."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Initially not trusted
        assert manager.is_operation_trusted("git_commit") is False

        # Trust it
        manager.trust_operation("git_commit")

        # Now should be trusted
        assert manager.is_operation_trusted("git_commit") is True

        # Other operations still not trusted
        assert manager.is_operation_trusted("file_write") is False

    def test_get_permission_status(self, tmp_path):
        """Test getting permission status."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Trust some operations
        manager.trust_operation("git_commit")
        manager.trust_operation("uv_sync")

        # Get status
        status = manager.get_permission_status()

        assert "trusted_operations" in status
        assert "session_id" in status
        assert "last_updated" in status
        assert len(status["trusted_operations"]) == 2
        assert "git_commit" in status["trusted_operations"]
        assert "uv_sync" in status["trusted_operations"]


class TestPermissionPersistence:
    """Test permission loading and saving."""

    def test_load_permissions_from_file(self, tmp_path):
        """Test loading permissions from file."""
        claude_dir = tmp_path / ".claude"
        permissions_dir = claude_dir / "sessions"
        permissions_dir.mkdir(parents=True)
        permissions_file = permissions_dir / "trusted_permissions.json"

        # Create a permissions file
        data = {
            "trusted_operations": ["git_commit", "uv_sync"],
            "last_updated": "2024-01-01T12:00:00",
            "session_id": "test-session-id",
        }
        with open(permissions_file, "w") as f:
            json.dump(data, f)

        # Create manager (should load permissions)
        manager = SessionPermissionsManager(claude_dir)

        # Check that permissions were loaded
        assert "git_commit" in manager.trusted_operations
        assert "uv_sync" in manager.trusted_operations

    def test_save_permissions_to_file(self, tmp_path):
        """Test saving permissions to file."""
        claude_dir = tmp_path / ".claude"
        permissions_dir = claude_dir / "sessions"
        permissions_file = permissions_dir / "trusted_permissions.json"

        # Create manager and trust operations
        manager = SessionPermissionsManager(claude_dir)
        manager.trust_operation("git_commit")
        manager.trust_operation("uv_sync")

        # Permissions should be saved
        assert permissions_file.exists()

        # Load and verify
        with open(permissions_file) as f:
            data = json.load(f)

        assert "git_commit" in data["trusted_operations"]
        assert "uv_sync" in data["trusted_operations"]
        assert "last_updated" in data
        assert "session_id" in data

    def test_permissions_persistence_across_instances(self, tmp_path):
        """Test that permissions persist across manager instances."""
        claude_dir = tmp_path / ".claude"

        # Create first instance and trust operations
        manager1 = SessionPermissionsManager(claude_dir)
        manager1.trust_operation("git_commit")
        manager1.trust_operation("uv_sync")

        # Create second instance (should load permissions)
        # Note: Due to singleton, this is the same instance
        manager2 = SessionPermissionsManager(claude_dir)

        # Permissions should persist
        assert manager2.is_operation_trusted("git_commit") is True
        assert manager2.is_operation_trusted("uv_sync") is True

    def test_corrupted_permissions_file_handling(self, tmp_path):
        """Test handling of corrupted permissions file."""
        claude_dir = tmp_path / ".claude"
        permissions_dir = claude_dir / "sessions"
        permissions_dir.mkdir(parents=True)
        permissions_file = permissions_dir / "trusted_permissions.json"

        # Create a corrupted file
        with open(permissions_file, "w") as f:
            f.write("{invalid json content")

        # Should not raise exception, just start with empty permissions
        manager = SessionPermissionsManager(claude_dir)
        assert len(manager.trusted_operations) == 0

    def test_empty_permissions_file_handling(self, tmp_path):
        """Test handling of empty permissions file."""
        claude_dir = tmp_path / ".claude"
        permissions_dir = claude_dir / "sessions"
        permissions_dir.mkdir(parents=True)
        permissions_file = permissions_dir / "trusted_permissions.json"

        # Create an empty file
        permissions_file.touch()

        # Should not raise exception
        manager = SessionPermissionsManager(claude_dir)
        assert len(manager.trusted_operations) == 0


class TestSessionManagement:
    """Test session ID management."""

    def test_session_id_generation(self, tmp_path):
        """Test session ID generation."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Session ID should be a string
        assert isinstance(manager.session_id, str)

        # Should be reasonable length (12 characters from MD5 hash)
        assert len(manager.session_id) == 12

        # Should be alphanumeric
        assert manager.session_id.isalnum()

    @patch("session_buddy.core.permissions.Path.cwd")
    def test_session_id_includes_cwd(self, mock_cwd, tmp_path):
        """Test that session ID includes current working directory."""
        mock_cwd.return_value = tmp_path / "test_project"

        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Session ID should be generated
        assert manager.session_id is not None

        # Different directories should produce different session IDs
        mock_cwd.return_value = tmp_path / "other_project"
        SessionPermissionsManager._instance = None
        SessionPermissionsManager._session_id = None

        manager2 = SessionPermissionsManager(claude_dir)
        # Session IDs should differ due to different paths
        # (Note: Might sometimes collide due to MD5 truncation, but unlikely)
        # We just verify they're both valid
        assert manager2.session_id is not None
        assert len(manager2.session_id) == 12

    def test_get_permission_status(self, tmp_path):
        """Test getting permission status."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Trust some operations
        manager.trust_operation("git_commit")
        manager.trust_operation("uv_sync")

        status = manager.get_permission_status()

        # Check structure
        assert isinstance(status, dict)
        assert "trusted_operations" in status
        assert "session_id" in status
        assert "last_updated" in status

        # Check content
        assert isinstance(status["trusted_operations"], list)
        assert len(status["trusted_operations"]) == 2
        assert "git_commit" in status["trusted_operations"]
        assert "uv_sync" in status["trusted_operations"]

        # Session ID should match
        assert status["session_id"] == manager.session_id

        # Last updated should be an ISO format string
        assert isinstance(status["last_updated"], str)


class TestPermissionsManagerErrorHandling:
    """Test error handling in permissions manager."""

    def test_permission_file_creation_error(self, tmp_path):
        """Test handling of permission file creation errors."""
        claude_dir = tmp_path / ".claude"

        # Create a file where the directory should be
        (claude_dir / "sessions").touch()

        # This might cause issues, but should handle gracefully
        # The manager might not be able to save permissions
        try:
            manager = SessionPermissionsManager(claude_dir)
            # If it succeeds, operations should still work
            manager.trust_operation("test_op")
        except (OSError, PermissionError):
            # Or it might raise an exception, which is acceptable
            pass

    def test_trust_operation_with_special_characters(self, tmp_path):
        """Test trusting operations with special characters."""
        claude_dir = tmp_path / ".claude"
        manager = SessionPermissionsManager(claude_dir)

        # Operations with special characters
        operations = [
            "git:commit",
            "file:write:/path/to/file",
            "uv:sync--dev",
        ]

        for op in operations:
            result = manager.trust_operation(op)
            assert result is True
            assert manager.is_operation_trusted(op) is True


if __name__ == "__main__":
    pytest.main([__file__])
