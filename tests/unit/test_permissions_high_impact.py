from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from session_buddy.core.permissions import SessionPermissionsManager


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    SessionPermissionsManager.reset_singleton()
    yield
    SessionPermissionsManager.reset_singleton()


def test_generate_session_id_falls_back_to_home_when_cwd_missing(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"

    with patch("session_buddy.core.permissions.Path.cwd", side_effect=FileNotFoundError), patch(
        "session_buddy.core.permissions.Path.home", return_value=tmp_path
    ):
        manager = SessionPermissionsManager(claude_dir)

    assert manager.session_id
    assert len(manager.session_id) == 12


def test_initialization_handles_sessions_directory_mkdir_failure(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"

    with patch.object(Path, "mkdir", side_effect=OSError("blocked")):
        manager = SessionPermissionsManager(claude_dir)

    assert manager.claude_dir == claude_dir
    assert manager.permissions_file == claude_dir / "sessions" / "trusted_permissions.json"
    assert manager.trusted_operations == set()


def test_reuses_existing_instance_for_same_path(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"

    manager1 = SessionPermissionsManager(claude_dir)
    manager1.trust_operation("shared-op")
    manager2 = SessionPermissionsManager(claude_dir)

    assert manager1 is manager2
    assert manager2.is_operation_trusted("shared-op") is True


def test_reinitializes_when_claude_dir_changes(tmp_path: Path) -> None:
    first_dir = tmp_path / "first" / ".claude"
    second_dir = tmp_path / "second" / ".claude"

    manager1 = SessionPermissionsManager(first_dir)
    manager1.trust_operation("first-op")
    first_session_id = manager1.session_id

    manager2 = SessionPermissionsManager(second_dir)

    assert manager1 is manager2
    assert manager2.claude_dir == second_dir
    assert manager2.permissions_file == second_dir / "sessions" / "trusted_permissions.json"
    assert manager2.session_id == first_session_id
    assert "first-op" not in manager2.trusted_operations


def test_load_permissions_restores_last_updated(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    permissions_file = claude_dir / "sessions" / "trusted_permissions.json"
    permissions_file.parent.mkdir(parents=True, exist_ok=True)
    permissions_file.write_text(
        """
        {
          "trusted_operations": ["git_commit"],
          "last_updated": "2024-01-01T12:00:00",
          "session_id": "abc123"
        }
        """.strip()
    )

    manager = SessionPermissionsManager(claude_dir)

    assert manager.is_operation_trusted("git_commit") is True
    assert manager.get_permission_status()["last_updated"] == "2024-01-01T12:00:00"


def test_load_permissions_without_last_updated_keeps_runtime_default(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    permissions_file = claude_dir / "sessions" / "trusted_permissions.json"
    permissions_file.parent.mkdir(parents=True, exist_ok=True)
    permissions_file.write_text(
        """
        {
          "trusted_operations": ["git_commit"],
          "session_id": "abc123"
        }
        """.strip()
    )

    manager = SessionPermissionsManager(claude_dir)

    assert manager.is_operation_trusted("git_commit") is True
    assert manager._last_updated is None


def test_load_permissions_handles_empty_and_corrupt_files(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty" / ".claude"
    empty_file = empty_dir / "sessions" / "trusted_permissions.json"
    empty_file.parent.mkdir(parents=True, exist_ok=True)
    empty_file.write_text("")

    manager_empty = SessionPermissionsManager(empty_dir)
    assert manager_empty.trusted_operations == set()

    SessionPermissionsManager.reset_singleton()

    corrupt_dir = tmp_path / "corrupt" / ".claude"
    corrupt_file = corrupt_dir / "sessions" / "trusted_permissions.json"
    corrupt_file.parent.mkdir(parents=True, exist_ok=True)
    corrupt_file.write_text("{ not json }")

    manager_corrupt = SessionPermissionsManager(corrupt_dir)
    assert manager_corrupt.trusted_operations == set()


def test_configure_auto_checkpoint_rejects_non_positive_frequency(tmp_path: Path) -> None:
    manager = SessionPermissionsManager(tmp_path / ".claude")

    assert manager.configure_auto_checkpoint(enabled=True, frequency=0) is False
    assert manager.configure_auto_checkpoint(enabled=True, frequency=-5) is False
    assert manager.auto_checkpoint is False
    assert manager.checkpoint_frequency == 300


def test_configure_auto_checkpoint_updates_state(tmp_path: Path) -> None:
    manager = SessionPermissionsManager(tmp_path / ".claude")

    assert manager.configure_auto_checkpoint(enabled=True, frequency=120) is True
    assert manager.auto_checkpoint is True
    assert manager.checkpoint_frequency == 120

    assert manager.configure_auto_checkpoint(enabled=False, frequency=240) is True
    assert manager.auto_checkpoint is False
    assert manager.checkpoint_frequency == 120


def test_should_auto_checkpoint_reflects_current_setting(tmp_path: Path) -> None:
    manager = SessionPermissionsManager(tmp_path / ".claude")

    assert manager.should_auto_checkpoint() is False
    manager.auto_checkpoint = True
    assert manager.should_auto_checkpoint() is True


def test_revoke_all_permissions_handles_missing_file_without_error(tmp_path: Path) -> None:
    manager = SessionPermissionsManager(tmp_path / ".claude")
    manager.trust_operation("write-file")
    manager.permissions_file.unlink()

    manager.revoke_all_permissions()

    assert manager.trusted_operations == set()


def test_revoke_all_permissions_handles_unlink_failure(tmp_path: Path) -> None:
    manager = SessionPermissionsManager(tmp_path / ".claude")
    manager.trust_operation("write-file")

    with patch.object(Path, "unlink", side_effect=OSError("blocked")):
        manager.revoke_all_permissions()

    assert manager.trusted_operations == set()


def test_trust_operation_persists_even_if_save_fails(tmp_path: Path) -> None:
    manager = SessionPermissionsManager(tmp_path / ".claude")

    with patch.object(Path, "open", side_effect=OSError("blocked")):
        assert manager.trust_operation("volatile-operation") is True

    assert manager.is_operation_trusted("volatile-operation") is True


def test_trust_operation_rejects_none_value(tmp_path: Path) -> None:
    manager = SessionPermissionsManager(tmp_path / ".claude")

    with pytest.raises(TypeError, match="cannot be None"):
        manager.trust_operation(None)  # type: ignore[arg-type]
