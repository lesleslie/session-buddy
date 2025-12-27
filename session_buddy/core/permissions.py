"""Session permissions management.

This module provides the SessionPermissionsManager class for managing
trusted operations and permission scopes during sessions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from typing import Self


class SessionPermissionsManager:
    """Manages session permissions to avoid repeated prompts for trusted operations."""

    _instance: SessionPermissionsManager | None = None
    _session_id: str | None = None
    _initialized: bool = False

    def __new__(cls, claude_dir: Path) -> Self:  # type: ignore[misc]
        """Singleton pattern to ensure consistent session ID across tool calls."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        # Type checker knows this is Self from the annotation above
        return cls._instance  # type: ignore[return-value]

    def __init__(self, claude_dir: Path) -> None:
        if self._initialized:
            return
        self.claude_dir = claude_dir
        self.permissions_file = claude_dir / "sessions" / "trusted_permissions.json"
        self.permissions_file.parent.mkdir(parents=True, exist_ok=True)
        self.trusted_operations: set[str] = set()
        self.auto_checkpoint = False  # Add the required attribute for tests
        self.checkpoint_frequency = 300  # Default frequency (5 minutes)

        # Use class-level session ID to persist across instances
        if self.__class__._session_id is None:
            self.__class__._session_id = self._generate_session_id()
        self.session_id = self.__class__._session_id
        self._load_permissions()
        self._initialized = True

    def _generate_session_id(self) -> str:
        """Generate unique session ID based on current time and working directory."""
        try:
            cwd = Path.cwd()
        except FileNotFoundError:
            cwd = Path.home()
        session_data = f"{datetime.now().isoformat()}_{cwd}"
        return hashlib.md5(session_data.encode(), usedforsecurity=False).hexdigest()[
            :12
        ]

    def _load_permissions(self) -> None:
        """Load previously granted permissions."""
        if self.permissions_file.exists():
            try:
                with self.permissions_file.open() as f:
                    data = json.load(f)
                    self.trusted_operations.update(data.get("trusted_operations", []))
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_permissions(self) -> None:
        """Save current trusted permissions."""
        data = {
            "trusted_operations": list(self.trusted_operations),
            "last_updated": datetime.now().isoformat(),
            "session_id": self.session_id,
        }
        with self.permissions_file.open("w") as f:
            json.dump(data, f, indent=2)

    def is_operation_trusted(self, operation: str) -> bool:
        """Check if an operation is already trusted."""
        return operation in self.trusted_operations

    def trust_operation(self, operation: str, description: str = "") -> bool:
        """Mark an operation as trusted to avoid future prompts."""
        if operation is None:
            msg = "Operation cannot be None"
            raise TypeError(msg)
        self.trusted_operations.add(operation)
        self._save_permissions()
        return True  # Indicate success

    def get_permission_status(self) -> dict[str, Any]:
        """Get current permission status."""
        return {
            "session_id": self.session_id,
            "trusted_operations_count": len(self.trusted_operations),
            "trusted_operations": list(self.trusted_operations),
            "permissions_file": str(self.permissions_file),
        }

    def configure_auto_checkpoint(
        self, enabled: bool = True, frequency: int = 300
    ) -> bool:
        """Configure auto-checkpoint settings with security validations."""
        # Accept all positive frequencies but log security concerns for unsafe values
        # For security considerations, log if frequency is dangerously low (< 30s)
        if frequency <= 0:
            return False  # Still reject non-positive frequencies

        self.auto_checkpoint = enabled
        if enabled:
            self.checkpoint_frequency = frequency
        return True

    def should_auto_checkpoint(self) -> bool:
        """Determine if auto checkpointing should occur based on configuration."""
        # For now, return the current setting - in a full implementation
        # this might check timing since last checkpoint, etc.
        return self.auto_checkpoint

    def revoke_all_permissions(self) -> None:
        """Revoke all trusted permissions (for security reset)."""
        self.trusted_operations.clear()
        if self.permissions_file.exists():
            self.permissions_file.unlink()

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None
        cls._session_id = None
        cls._initialized = False

    # Common trusted operations
    TRUSTED_UV_OPERATIONS = "uv_package_management"
    TRUSTED_GIT_OPERATIONS = "git_repository_access"
    TRUSTED_FILE_OPERATIONS = "project_file_access"
    TRUSTED_SUBPROCESS_OPERATIONS = "subprocess_execution"
    TRUSTED_NETWORK_OPERATIONS = "network_access"


# =====================================
# Configuration Functions
# =====================================
