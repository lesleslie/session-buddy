"""Services module for session buddy.

This module contains standalone services that use hooks for loose coupling
with the session lifecycle.
"""

from session_buddy.services.git_maintenance import (
    GitMaintenanceConfig,
    GitMaintenanceService,
    GitProcessTracker,
    get_git_maintenance_service,
)

__all__ = [
    "GitMaintenanceConfig",
    "GitMaintenanceService",
    "GitProcessTracker",
    "get_git_maintenance_service",
]
