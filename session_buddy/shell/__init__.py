"""Session-Buddy admin shell with session-specific formatters and helpers.

This module extends the Oneiric AdminShell with Session-Buddy-specific functionality
for session management, conversation memory, and quality monitoring.

Example:
    >>> from session_buddy.shell import SessionBuddyShell
    >>> from session_buddy.core.session_manager import SessionLifecycleManager
    >>> manager = SessionLifecycleManager()
    >>> shell = SessionBuddyShell(manager)
    >>> shell.start()
"""

from .adapter import SessionBuddyShell

__all__ = ["SessionBuddyShell"]
