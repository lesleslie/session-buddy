"""MCP tools for hooks management and causal chain operations.

This module provides Model Context Protocol tools for:
    - Listing and managing hooks
    - Querying similar errors with debugging intelligence
    - Recording successful fixes for learning
    - Inspecting causal chain history
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_buddy.server import SessionBuddyServer


def register_hooks_tools(server: SessionBuddyServer) -> None:
    """Register hooks and causal chain MCP tools.

    Args:
        server: SessionBuddyServer instance to register tools on
    """
    from session_buddy.core.causal_chains import CausalChainTracker
    from session_buddy.core.hooks import HookType

    @server.tool()  # type: ignore[misc]
    async def list_hooks(
        hook_type: str | None = None,
    ) -> dict[str, Any]:
        """List all registered hooks.

        Provides visibility into what hooks are registered, their priorities,
        and whether they're enabled. Useful for debugging and understanding
        system behavior.

        Args:
            hook_type: Optional hook type filter (e.g., "post_checkpoint", "pre_tool_execution").
                       If not provided, returns all hooks.

        Returns:
            Dictionary with:
                - total_hooks: Total number of registered hooks
                - hooks_by_type: Dictionary mapping hook types to their hooks
                - message: Human-readable summary

        Example:
            >>> result = await list_hooks("post_checkpoint")
            >>> print(result["hooks_by_type"]["post_checkpoint"])
        """
        if not server.hooks_manager:
            return {
                "success": False,
                "error": "Hooks manager not initialized",
                "total_hooks": 0,
                "hooks_by_type": {},
            }

        # Convert string to HookType if provided
        hook_type_enum = None
        if hook_type:
            try:
                hook_type_enum = HookType(hook_type)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid hook type: {hook_type}",
                    "total_hooks": 0,
                    "hooks_by_type": {},
                }

        hooks_dict = server.hooks_manager.list_hooks(hook_type_enum)

        # Count total hooks
        total_hooks = sum(len(hooks) for hooks in hooks_dict.values())

        return {
            "success": True,
            "total_hooks": total_hooks,
            "hooks_by_type": {
                ht.value: hooks_list for ht, hooks_list in hooks_dict.items()
            },
            "message": f"Found {total_hooks} registered hooks",
        }

    @server.tool()  # type: ignore[misc]
    async def query_similar_errors(
        error_message: str, limit: int = 5
    ) -> dict[str, Any]:
        """Find similar past errors and their fixes.

        Uses semantic search to find historically similar errors from past
        debugging sessions and returns what fixes worked.

        Args:
            error_message: Current error message to search for
            limit: Maximum number of similar errors to return (default: 5)

        Returns:
            Dictionary with:
                - found_similar: Whether similar errors were found
                - count: Number of similar errors found
                - similar_errors: List of similar errors with fixes
                - suggestion: Human-readable guidance

        Example:
            >>> result = await query_similar_errors(
            ...     "ImportError: cannot import name 'foo'",
            ...     limit=3
            ... )
            >>> if result["found_similar"]:
            ...     for err in result["similar_errors"]:
            ...         print(f"Try: {err['successful_fix']['action_taken']}")
        """
        tracker = CausalChainTracker(logger=server.logger)
        await tracker.initialize()

        similar_failures = await tracker.query_similar_failures(
            current_error=error_message, limit=limit
        )

        if not similar_failures:
            return {
                "found_similar": False,
                "count": 0,
                "similar_errors": [],
                "suggestion": (
                    "No similar errors found in history. "
                    "This appears to be a new error pattern."
                ),
            }

        # Format suggestions
        suggestions = []
        for failure in similar_failures:
            fix = failure["successful_fix"]
            suggestion = {
                "error_message": failure["error_message"],
                "similarity": f"{failure['similarity']:.1%}",
                "resolution_time_minutes": failure["resolution_time_minutes"],
                "suggested_fix": fix["action_taken"],
                "code_changes": fix.get("code_changes"),
            }
            suggestions.append(suggestion)

        return {
            "found_similar": True,
            "count": len(similar_failures),
            "similar_errors": suggestions,
            "suggestion": (
                f"Found {len(similar_failures)} similar error(s) from past. "
                "Try the successful fixes shown above."
            ),
        }

    @server.tool()  # type: ignore[misc]
    async def record_fix_success(
        error_message: str,
        action_taken: str,
        code_changes: str | None = None,
        error_type: str = "unknown",
    ) -> dict[str, Any]:
        """Record a successful fix for learning.

        Manually record a fix that resolved an error. This adds to the
        causal chain database for future debugging assistance.

        Args:
            error_message: The error that was fixed
            action_taken: What was done to fix it
            code_changes: Optional code changes made
            error_type: Type of error (e.g., "TypeError", "ImportError")

        Returns:
            Dictionary with:
                - success: Whether recording succeeded
                - fix_id: Fix attempt identifier
                - message: Confirmation message

        Example:
            >>> result = await record_fix_success(
            ...     error_message="NameError: name 'undefined_var' is not defined",
            ...     action_taken="Defined undefined_var with proper value",
            ...     error_type="NameError"
            ... )
        """
        tracker = CausalChainTracker(logger=server.logger)
        await tracker.initialize()

        # Check for recent error event from this session
        # (In real implementation, would track current session's errors)
        error_id = None

        # For now, create a new error event
        error_id = await tracker.record_error_event(
            error=error_message,
            context={
                "error_type": error_type,
                "recorded_retrospectively": True,
            },
            session_id=server.session_manager.current_session_id
            if server.session_manager
            else "manual",
        )

        # Record successful fix
        fix_id = await tracker.record_fix_attempt(
            error_id=error_id,
            action_taken=action_taken,
            code_changes=code_changes,
            successful=True,
        )

        return {
            "success": True,
            "fix_id": fix_id,
            "error_id": error_id,
            "message": (
                "Fix recorded successfully. Will be suggested for "
                "similar errors in future."
            ),
        }

    @server.tool()  # type: ignore[misc]
    async def get_causal_chain(
        chain_id: str,
    ) -> dict[str, Any]:
        """Get complete causal chain by ID.

        Retrieves the full error→attempts→solution chain for a
        specific debugging session.

        Args:
            chain_id: Causal chain identifier (format: chain-XXXXXXXX)

        Returns:
            Dictionary with complete chain details or error if not found

        Example:
            >>> result = await get_causal_chain("chain-a1b2c3d4")
            >>> if result["success"]:
            ...     chain = result["chain"]
            ...     print(f"Error: {chain['error_event']['error_message']}")
            ...     print(f"Fixes attempted: {len(chain['fix_attempts'])}")
        """
        tracker = CausalChainTracker(logger=server.logger)
        await tracker.initialize()

        chain = await tracker.get_causal_chain(chain_id)

        if not chain:
            return {
                "success": False,
                "error": f"Causal chain not found: {chain_id}",
            }

        # Format for JSON response
        return {
            "success": True,
            "chain": {
                "id": chain.id,
                "error_event": {
                    "id": chain.error_event.id,
                    "error_message": chain.error_event.error_message,
                    "error_type": chain.error_event.error_type,
                    "context": chain.error_event.context,
                    "timestamp": chain.error_event.timestamp.isoformat(),
                    "session_id": chain.error_event.session_id,
                },
                "fix_attempts": [
                    {
                        "id": attempt.id,
                        "action_taken": attempt.action_taken,
                        "code_changes": attempt.code_changes,
                        "successful": attempt.successful,
                        "timestamp": attempt.timestamp.isoformat(),
                    }
                    for attempt in chain.fix_attempts
                ],
                "successful_fix": {
                    "id": chain.successful_fix.id,
                    "action_taken": chain.successful_fix.action_taken,
                    "code_changes": chain.successful_fix.code_changes,
                }
                if chain.successful_fix
                else None,
                "resolution_time_minutes": chain.resolution_time_minutes,
            },
        }

    @server.tool()  # type: ignore[misc]
    async def enable_hook(hook_name: str, hook_type: str) -> dict[str, Any]:
        """Enable a specific hook.

        Args:
            hook_name: Name of the hook to enable
            hook_type: Type of hook (e.g., "post_checkpoint")

        Returns:
            Success/error message
        """
        # This would require hooks_manager to have a enable_hook method
        # For now, return placeholder
        return {
            "success": False,
            "error": "Hook enable/disable not yet implemented",
            "message": "This feature will be added in a future update",
        }

    @server.tool()  # type: ignore[misc]
    async def disable_hook(hook_name: str, hook_type: str) -> dict[str, Any]:
        """Disable a specific hook.

        Args:
            hook_name: Name of the hook to disable
            hook_type: Type of hook (e.g., "post_checkpoint")

        Returns:
            Success/error message
        """
        # This would require hooks_manager to have a disable_hook method
        # For now, return placeholder
        return {
            "success": False,
            "error": "Hook enable/disable not yet implemented",
            "message": "This feature will be added in a future update",
        }

    # Register prompts
    @server.prompt()  # type: ignore[misc]
    def hooks_help() -> str:
        """Get help for using hooks and causal chains."""
        return """# Hooks and Causal Chains - Usage Guide

## Available Tools

### Hook Management

- **list_hooks**: View all registered hooks
  - See what hooks are active, their priorities, and what they do
  - Use to debug hook execution order

- **enable_hook / disable_hook**: Control hook execution
  - Turn specific hooks on or off
  - Useful for testing or temporary disabling

### Causal Chain Tracking

- **query_similar_errors**: Find past debugging solutions
  - Get suggestions from similar errors you've fixed before
  - See what fixes worked and how long they took

- **record_fix_success**: Document what worked
  - Manually record successful fixes for learning
  - Builds debugging intelligence over time

- **get_causal_chain**: Inspect complete debugging history
  - See full error→attempt→solution chain
  - Learn from past debugging sessions

## Common Workflows

### Debugging a New Error

1. Run: `query_similar_errors` with your error message
2. Review suggested fixes from similar past errors
3. Try the most promising solution
4. If it works, run: `record_fix_success` to document it

### Understanding System Behavior

1. Run: `list_hooks` to see all registered hooks
2. Check hook priorities to understand execution order
3. Disable hooks temporarily for testing
4. Re-enable hooks when done

## Built-in Hooks

The system includes several default hooks:

- **auto_format_python**: Formats Python files after edits
- **quality_validation**: Ensures quality before checkpoints
- **learn_from_checkpoint**: Extracts patterns from successful sessions
- **track_error_fix_chain**: Records debugging patterns

These hooks provide automation while you work!
"""
