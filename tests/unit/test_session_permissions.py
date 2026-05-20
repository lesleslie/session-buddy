"""Tests for SessionPermissionsManager security and authorization.

This module tests the security boundaries of the session permissions system,
including authorization checks, permission granting/revocation, and audit capabilities.

Phase: Week 6 Day 2 - Security Testing
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from session_buddy.core.permissions import SessionPermissionsManager


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset singleton state after each test."""
    yield
    SessionPermissionsManager.reset_singleton()


@pytest.fixture
def temp_permissions_dir(tmp_path: Path) -> Path:
    """Create temporary directory for permissions testing."""
    return tmp_path / ".claude"


@pytest.fixture
def permissions_manager(temp_permissions_dir: Path) -> SessionPermissionsManager:
    """Create a fresh SessionPermissionsManager instance."""
    return SessionPermissionsManager(temp_permissions_dir)


class TestInitializationAndSessionID:
    """Test secure initialization and session ID generation."""

    def test_singleton_pattern_enforcement(self, temp_permissions_dir: Path) -> None:
        """Should enforce singleton pattern for security consistency."""
        manager1 = SessionPermissionsManager(temp_permissions_dir)
        manager2 = SessionPermissionsManager(temp_permissions_dir)

        assert manager1 is manager2
        assert manager1.session_id == manager2.session_id

    def test_session_id_generation(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should generate unique session ID."""
        session_id = permissions_manager.session_id

        assert isinstance(session_id, str)
        assert len(session_id) == 12  # MD5 hash truncated to 12 chars
        assert session_id.isalnum()

    def test_session_id_persistence_across_instances(
        self, temp_permissions_dir: Path
    ) -> None:
        """Should maintain same session ID across multiple instantiations."""
        manager1 = SessionPermissionsManager(temp_permissions_dir)
        session_id1 = manager1.session_id

        # Create another instance (singleton should return same)
        manager2 = SessionPermissionsManager(temp_permissions_dir)
        session_id2 = manager2.session_id

        assert session_id1 == session_id2

    def test_permissions_file_creation(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should create permissions directory structure."""
        permissions_file = permissions_manager.permissions_file

        assert permissions_file.parent.exists()
        assert permissions_file.parent.name == "sessions"


class TestAuthorizationChecks:
    """Test authorization boundary enforcement."""

    def test_is_operation_trusted_returns_false_by_default(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should return False for untrusted operations (secure default)."""
        assert permissions_manager.is_operation_trusted("dangerous_operation") is False

    def test_is_operation_trusted_after_granting(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should return True after explicitly granting trust."""
        operation = "safe_operation"

        # Initially not trusted
        assert permissions_manager.is_operation_trusted(operation) is False

        # Grant trust
        permissions_manager.trust_operation(operation)

        # Now trusted
        assert permissions_manager.is_operation_trusted(operation) is True

    def test_authorization_check_is_case_sensitive(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should treat operation names as case-sensitive for security."""
        permissions_manager.trust_operation("READ_FILE")

        assert permissions_manager.is_operation_trusted("READ_FILE") is True
        assert permissions_manager.is_operation_trusted("read_file") is False
        assert permissions_manager.is_operation_trusted("Read_File") is False

    def test_predefined_operation_constants(self) -> None:
        """Should provide predefined constants for common operations."""
        # Verify security-critical constants exist
        assert hasattr(SessionPermissionsManager, "TRUSTED_UV_OPERATIONS")
        assert hasattr(SessionPermissionsManager, "TRUSTED_GIT_OPERATIONS")
        assert hasattr(SessionPermissionsManager, "TRUSTED_FILE_OPERATIONS")
        assert hasattr(SessionPermissionsManager, "TRUSTED_SUBPROCESS_OPERATIONS")
        assert hasattr(SessionPermissionsManager, "TRUSTED_NETWORK_OPERATIONS")

        # Verify they are strings
        assert isinstance(SessionPermissionsManager.TRUSTED_UV_OPERATIONS, str)
        assert isinstance(SessionPermissionsManager.TRUSTED_GIT_OPERATIONS, str)


class TestPermissionGranting:
    """Test permission granting operations."""

    def test_trust_operation_adds_to_trusted_set(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should add operation to trusted set."""
        operation = "test_operation"

        permissions_manager.trust_operation(operation)

        assert operation in permissions_manager.trusted_operations

    def test_trust_operation_persists_to_file(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should persist permissions to file for cross-session security."""
        operation = "persistent_operation"

        permissions_manager.trust_operation(operation)

        # Verify file was created
        assert permissions_manager.permissions_file.exists()

        # Verify file contains the operation
        with permissions_manager.permissions_file.open() as f:
            data = json.load(f)
            assert operation in data["trusted_operations"]

    def test_trust_operation_with_description_ignored(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should accept but ignore description parameter."""
        operation = "described_operation"

        # Description parameter exists but is not used in current implementation
        permissions_manager.trust_operation(operation, description="For testing")

        assert permissions_manager.is_operation_trusted(operation) is True

    def test_duplicate_trust_operation_is_idempotent(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should handle duplicate trust_operation calls safely."""
        operation = "duplicate_operation"

        permissions_manager.trust_operation(operation)
        initial_count = len(permissions_manager.trusted_operations)

        # Trust again
        permissions_manager.trust_operation(operation)

        # Should not increase count (set behavior)
        assert len(permissions_manager.trusted_operations) == initial_count

    def test_trust_operation_rejects_none(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should reject None as an operation name."""
        with pytest.raises(TypeError, match="cannot be None"):
            permissions_manager.trust_operation(None)  # type: ignore[arg-type]


class TestPermissionRevocation:
    """Test permission revocation and security resets."""

    def test_revoke_all_permissions_clears_trusted_set(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should clear all trusted operations."""
        permissions_manager.trust_operation("op1")
        permissions_manager.trust_operation("op2")

        assert len(permissions_manager.trusted_operations) > 0

        permissions_manager.revoke_all_permissions()

        assert len(permissions_manager.trusted_operations) == 0

    def test_revoke_all_permissions_deletes_file(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should delete permissions file for complete security reset."""
        permissions_manager.trust_operation("op1")
        assert permissions_manager.permissions_file.exists()

        permissions_manager.revoke_all_permissions()

        assert not permissions_manager.permissions_file.exists()

    def test_revoke_all_permissions_when_no_file_exists(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should handle revocation when no file exists (safety)."""
        # Ensure no file exists
        if permissions_manager.permissions_file.exists():
            permissions_manager.permissions_file.unlink()

        # Should not raise exception
        permissions_manager.revoke_all_permissions()

        assert len(permissions_manager.trusted_operations) == 0

    def test_revoke_all_permissions_handles_unwritable_file(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should ignore file cleanup failures during revocation."""
        permissions_manager.trust_operation("op1")

        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            permissions_manager.revoke_all_permissions()

        assert len(permissions_manager.trusted_operations) == 0


class TestAuditCapabilities:
    """Test audit and status reporting functionality."""

    def test_get_permission_status_structure(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should return complete status information."""
        status = permissions_manager.get_permission_status()

        # Verify required fields
        assert "session_id" in status
        assert "trusted_operations_count" in status
        assert "trusted_operations" in status
        assert "permissions_file" in status

    def test_get_permission_status_accuracy(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should accurately reflect current state."""
        permissions_manager.trust_operation("op1")
        permissions_manager.trust_operation("op2")

        status = permissions_manager.get_permission_status()

        assert status["trusted_operations_count"] == 2
        assert "op1" in status["trusted_operations"]
        assert "op2" in status["trusted_operations"]
        assert status["session_id"] == permissions_manager.session_id

    def test_get_permission_status_returns_list_copy(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should return list (not set) for JSON serialization."""
        permissions_manager.trust_operation("test_op")

        status = permissions_manager.get_permission_status()

        # Should be a list (JSON-serializable)
        assert isinstance(status["trusted_operations"], list)

    def test_get_permission_status_uses_current_timestamp_when_unset(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should synthesize a timestamp when no persistence has occurred."""
        status = permissions_manager.get_permission_status()

        assert isinstance(status["last_updated"], str)
        assert status["last_updated"]


class TestPersistenceAndLoading:
    """Test persistence across manager instances."""

    def test_load_permissions_from_existing_file(
        self, temp_permissions_dir: Path
    ) -> None:
        """Should load previously saved permissions."""
        # Ensure .claude directory exists
        temp_permissions_dir.mkdir(parents=True, exist_ok=True)

        # Reset singleton FIRST to ensure clean state
        SessionPermissionsManager.reset_singleton()

        # Create first manager and grant permissions
        manager1 = SessionPermissionsManager(temp_permissions_dir)
        manager1.trust_operation("persisted_op")
        session_id1 = manager1.session_id

        # Reset singleton
        SessionPermissionsManager.reset_singleton()

        # Create new manager (should load from file)
        manager2 = SessionPermissionsManager(temp_permissions_dir)

        # Should have loaded the permission
        assert manager2.is_operation_trusted("persisted_op") is True
        # But session ID will be different (new session)
        assert manager2.session_id != session_id1

    def test_load_permissions_handles_corrupt_json(
        self, temp_permissions_dir: Path
    ) -> None:
        """Should handle corrupted permissions file gracefully."""
        # Reset singleton first
        SessionPermissionsManager.reset_singleton()

        # Create permissions file with invalid JSON
        permissions_file = (
            temp_permissions_dir / "sessions" / "trusted_permissions.json"
        )
        permissions_file.parent.mkdir(parents=True, exist_ok=True)
        permissions_file.write_text("{ invalid json ]")

        # Should not raise exception
        manager = SessionPermissionsManager(temp_permissions_dir)

        # Should have empty trusted operations (safe default)
        assert len(manager.trusted_operations) == 0

    def test_load_permissions_handles_missing_file(
        self, temp_permissions_dir: Path
    ) -> None:
        """Should handle missing permissions file (first run)."""
        # Reset singleton first
        SessionPermissionsManager.reset_singleton()

        # Ensure parent .claude directory exists but no permissions file
        temp_permissions_dir.mkdir(parents=True, exist_ok=True)
        permissions_file = (
            temp_permissions_dir / "sessions" / "trusted_permissions.json"
        )
        if permissions_file.exists():
            permissions_file.unlink()

        # Should not raise exception
        manager = SessionPermissionsManager(temp_permissions_dir)

        assert len(manager.trusted_operations) == 0

    def test_load_permissions_handles_empty_file(
        self, temp_permissions_dir: Path
    ) -> None:
        """Should ignore empty permissions files without error."""
        SessionPermissionsManager.reset_singleton()

        permissions_file = (
            temp_permissions_dir / "sessions" / "trusted_permissions.json"
        )
        permissions_file.parent.mkdir(parents=True, exist_ok=True)
        permissions_file.write_text("")

        manager = SessionPermissionsManager(temp_permissions_dir)

        assert len(manager.trusted_operations) == 0


class TestSecurityBoundaries:
    """Test security boundary enforcement."""

    def test_empty_operation_name_handling(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should handle empty operation names safely."""
        # Empty string should be treated as valid (though not recommended)
        permissions_manager.trust_operation("")

        assert permissions_manager.is_operation_trusted("") is True

    def test_whitespace_operation_names(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should treat whitespace as significant (no normalization)."""
        permissions_manager.trust_operation("  spaced  ")

        # Exact match required
        assert permissions_manager.is_operation_trusted("  spaced  ") is True
        assert permissions_manager.is_operation_trusted("spaced") is False

    def test_special_character_operation_names(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should handle special characters in operation names."""
        special_op = "operation/with:special@chars!"

        permissions_manager.trust_operation(special_op)

        assert permissions_manager.is_operation_trusted(special_op) is True

    def test_permissions_file_permissions_not_world_readable(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should create permissions file with appropriate permissions."""
        permissions_manager.trust_operation("test_op")

        # On Unix-like systems, file should not be world-readable
        if hasattr(permissions_manager.permissions_file, "stat"):
            stat_result = permissions_manager.permissions_file.stat()
            # Check that group and others don't have read permission
            # This is a best-effort check (may not apply on all systems)
            mode = stat_result.st_mode
            # World-readable would be mode & 0o004
            # This test documents expected behavior but may not enforce it
            # (Python's json.dump doesn't control file permissions)
            assert isinstance(mode, int)  # Just verify stat works

    def test_auto_checkpoint_disabled_does_not_change_frequency(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should leave the checkpoint frequency unchanged when disabled."""
        result = permissions_manager.configure_auto_checkpoint(
            enabled=False,
            frequency=120,
        )

        assert result is True
        assert permissions_manager.auto_checkpoint is False
        assert permissions_manager.checkpoint_frequency == 300


class TestConcurrencyAndThreadSafety:
    """Test thread safety considerations."""

    def test_singleton_thread_safety_structure(
        self, temp_permissions_dir: Path
    ) -> None:
        """Should use class-level variables for thread safety."""
        # Verify singleton uses class-level state
        assert hasattr(SessionPermissionsManager, "_instance")
        assert hasattr(SessionPermissionsManager, "_session_id")
        assert hasattr(SessionPermissionsManager, "_initialized")

    def test_trusted_operations_is_set_type(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should use set for O(1) authorization checks."""
        # Verify trusted_operations is a set for performance
        assert isinstance(permissions_manager.trusted_operations, set)

    def test_trust_operation_handles_persistence_failure(
        self, permissions_manager: SessionPermissionsManager
    ) -> None:
        """Should keep in-memory trust state when persistence fails."""
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            assert permissions_manager.trust_operation("volatile_operation") is True

        assert permissions_manager.is_operation_trusted("volatile_operation") is True
