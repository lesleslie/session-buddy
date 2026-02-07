"""Event subscribers for cross-system integration.

This module provides subscribers that listen to events from other systems
like Mahavishnu and store them in the reflection database.
"""

from session_buddy.subscribers.code_graph_subscriber import register_code_graph_tools

__all__ = ["register_code_graph_tools"]
