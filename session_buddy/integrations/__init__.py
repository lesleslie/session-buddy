"""Session-Buddy Integration Layer.

Phase 4 integration with external tools:
- Crackerjack quality gate hooks
- IDE plugin protocol for code context recommendations
- CI/CD pipeline tracking

This package enables session-buddy to integrate with external development tools
for comprehensive skill tracking across the entire development workflow.
"""

from session_buddy.integrations.cicd_tracker import (
    CICDTracker,
    CIPipelineContext,
)
from session_buddy.integrations.crackerjack_hooks import CrackerjackIntegration
from session_buddy.integrations.ide_plugin import (
    IDEContext,
    IDEPluginProtocol,
    IDESuggestion,
)

__all__ = [
    "CrackerjackIntegration",
    "IDEPluginProtocol",
    "IDEContext",
    "IDESuggestion",
    "CICDTracker",
    "CIPipelineContext",
]
