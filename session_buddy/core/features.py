"""Feature detection and availability checking.

This module provides the FeatureDetector class for detecting available
features and dependencies in the runtime environment.
"""

from __future__ import annotations

import importlib.util
import logging

logger = logging.getLogger(__name__)


class FeatureDetector:
    """Centralized feature detection for MCP server capabilities."""

    def __init__(self) -> None:
        """Initialize feature detector with all availability checks."""
        self.SESSION_MANAGEMENT_AVAILABLE = self._check_session_management()
        self.REFLECTION_TOOLS_AVAILABLE = self._check_reflection_tools()
        self.ENHANCED_SEARCH_AVAILABLE = self._check_enhanced_search()
        self.UTILITY_FUNCTIONS_AVAILABLE = self._check_utility_functions()
        self.MULTI_PROJECT_AVAILABLE = self._check_multi_project()
        self.ADVANCED_SEARCH_AVAILABLE = self._check_advanced_search()
        self.CONFIG_AVAILABLE = self._check_config()
        self.AUTO_CONTEXT_AVAILABLE = self._check_auto_context()
        self.MEMORY_OPTIMIZER_AVAILABLE = self._check_memory_optimizer()
        self.APP_MONITOR_AVAILABLE = self._check_app_monitor()
        self.LLM_PROVIDERS_AVAILABLE = self._check_llm_providers()
        self.SERVERLESS_MODE_AVAILABLE = self._check_serverless_mode()
        self.CRACKERJACK_INTEGRATION_AVAILABLE = self._check_crackerjack()

    @staticmethod
    def _check_session_management() -> bool:
        """Check if session management is available."""
        try:
            import session_buddy.core

            _ = (
                session_buddy.core.session_manager
            )  # Reference to avoid unused import warning during static analysis
            return True
        except (ImportError, AttributeError):
            # `import session_buddy.core` can raise AttributeError when
            # `session_buddy`'s `__getattr__` doesn't know the sub-attribute
            # (e.g. when the feature detector is being scanned in isolation
            # or when the module is being stubbed). Treat that the same as
            # an ImportError: the feature isn't available.
            return False

    @staticmethod
    def _check_reflection_tools() -> bool:
        """Check if reflection tools are available."""
        try:
            import session_buddy.reflection_tools

            _ = (
                session_buddy.reflection_tools
            )  # Use the import to avoid unused import warning
            return True
        except (ImportError, AttributeError):
            # See note in _check_session_management: AttributeError can
            # be raised by the package's `__getattr__` for unknown names.
            return False

    @staticmethod
    def _check_enhanced_search() -> bool:
        """Check if enhanced search is available."""
        try:
            return importlib.util.find_spec("session_buddy.search_enhanced") is not None
        except ImportError:
            return False

    @staticmethod
    def _check_utility_functions() -> bool:
        """Check if utility functions are available."""
        try:
            # Check for the general module availability without importing unused functions
            return (
                importlib.util.find_spec("session_buddy.tools.search_tools") is not None
            )
        except ImportError:
            return False

    @staticmethod
    def _check_multi_project() -> bool:
        """Check if multi-project coordination is available."""
        try:
            return (
                importlib.util.find_spec("session_buddy.multi_project_coordinator")
                is not None
            )
        except ImportError:
            return False

    @staticmethod
    def _check_advanced_search() -> bool:
        """Check if advanced search engine is available."""
        try:
            return importlib.util.find_spec("session_buddy.advanced_search") is not None
        except ImportError:
            return False

    @staticmethod
    def _check_config() -> bool:
        """Check if configuration management is available."""
        try:
            return importlib.util.find_spec("session_buddy.settings") is not None
        except ImportError:
            return False

    @staticmethod
    def _check_auto_context() -> bool:
        """Check if auto-context loading is available."""
        try:
            return importlib.util.find_spec("session_buddy.context_manager") is not None
        except ImportError:
            return False

    @staticmethod
    def _check_memory_optimizer() -> bool:
        """Check if memory optimizer is available."""
        try:
            return (
                importlib.util.find_spec("session_buddy.memory_optimizer") is not None
            )
        except ImportError:
            return False

    @staticmethod
    def _check_app_monitor() -> bool:
        """Check if application monitoring is available."""
        try:
            return importlib.util.find_spec("session_buddy.app_monitor") is not None
        except ImportError:
            return False

    @staticmethod
    def _check_llm_providers() -> bool:
        """Check if LLM providers are available."""
        try:
            return importlib.util.find_spec("session_buddy.llm_providers") is not None
        except ImportError:
            return False

    @staticmethod
    def _check_serverless_mode() -> bool:
        """Check if serverless mode is available."""
        try:
            return importlib.util.find_spec("session_buddy.serverless_mode") is not None
        except ImportError:
            return False

    @staticmethod
    def _check_crackerjack() -> bool:
        """Check if crackerjack integration is available."""
        try:
            return (
                importlib.util.find_spec("session_buddy.crackerjack_integration")
                is not None
            )
        except ImportError:
            return False

    def get_feature_flags(self) -> dict[str, bool]:
        """Get all feature flags as a dictionary."""
        return {
            "SESSION_MANAGEMENT_AVAILABLE": self.SESSION_MANAGEMENT_AVAILABLE,
            "REFLECTION_TOOLS_AVAILABLE": self.REFLECTION_TOOLS_AVAILABLE,
            "ENHANCED_SEARCH_AVAILABLE": self.ENHANCED_SEARCH_AVAILABLE,
            "UTILITY_FUNCTIONS_AVAILABLE": self.UTILITY_FUNCTIONS_AVAILABLE,
            "MULTI_PROJECT_AVAILABLE": self.MULTI_PROJECT_AVAILABLE,
            "ADVANCED_SEARCH_AVAILABLE": self.ADVANCED_SEARCH_AVAILABLE,
            "CONFIG_AVAILABLE": self.CONFIG_AVAILABLE,
            "AUTO_CONTEXT_AVAILABLE": self.AUTO_CONTEXT_AVAILABLE,
            "MEMORY_OPTIMIZER_AVAILABLE": self.MEMORY_OPTIMIZER_AVAILABLE,
            "APP_MONITOR_AVAILABLE": self.APP_MONITOR_AVAILABLE,
            "LLM_PROVIDERS_AVAILABLE": self.LLM_PROVIDERS_AVAILABLE,
            "SERVERLESS_MODE_AVAILABLE": self.SERVERLESS_MODE_AVAILABLE,
            "CRACKERJACK_INTEGRATION_AVAILABLE": self.CRACKERJACK_INTEGRATION_AVAILABLE,
        }


# Create global feature detector instance
_feature_detector = FeatureDetector()


def get_feature_flags() -> dict[str, bool]:
    """Get feature availability flags for the MCP server.

    Returns:
        Dictionary mapping feature names to availability status.

    """
    return _feature_detector.get_feature_flags()
