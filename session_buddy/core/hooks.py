"""Comprehensive hooks system for session lifecycle management.

This module provides a full-featured hooks infrastructure that supports:
- Pre/post operation hooks (checkpoint, tool execution, file edits, errors)
- Priority-based execution with error handling
- Causal chain tracking for debugging intelligence
- Extensible hook registration system

Architecture:
    HookType (enum) → Hook → HookContext → HookResult → HooksManager
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_buddy.core.causal_chains import CausalChainTracker
    from session_buddy.core.intelligence import IntelligenceEngine


class HookType(str, Enum):
    """Hook types for session lifecycle events.

    Pre-operation hooks:
        - Execute before an operation occurs
        - Can validate, modify, or cancel operations
        - PRE_SEARCH_QUERY: Rewrite ambiguous queries before search execution

    Post-operation hooks:
        - Execute after an operation completes
        - Can react to results, trigger side effects

    Session boundary hooks:
        - Execute at session start/end boundaries
        - Useful for setup/teardown operations
    """

    # Pre-operation hooks
    PRE_CHECKPOINT = "pre_checkpoint"
    PRE_TOOL_EXECUTION = "pre_tool_execution"
    PRE_REFLECTION_STORE = "pre_reflection_store"
    PRE_SESSION_END = "pre_session_end"
    PRE_SEARCH_QUERY = "pre_search_query"

    # Post-operation hooks
    POST_CHECKPOINT = "post_checkpoint"
    POST_TOOL_EXECUTION = "post_tool_execution"
    POST_FILE_EDIT = "post_file_edit"
    POST_ERROR = "post_error"  # Causal chain tracking hook

    # Session boundary (existing integration points)
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    USER_PROMPT_SUBMIT = "user_prompt_submit"


@dataclass
class HookContext:
    """Context passed to hook handlers.

    Attributes:
        hook_type: The type of hook being executed
        session_id: Current session identifier
        timestamp: When the hook was triggered
        metadata: Additional contextual information
        error_info: For POST_ERROR hooks - error details
        file_path: For POST_FILE_EDIT hooks - modified file path
        checkpoint_data: For checkpoint hooks - checkpoint information
    """

    hook_type: HookType
    session_id: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    # For error hooks
    error_info: dict[str, Any] | None = None
    # For file edit hooks
    file_path: str | None = None
    # For checkpoint hooks
    checkpoint_data: dict[str, Any] | None = None


@dataclass
class HookResult:
    """Result from hook execution.

    Attributes:
        success: Whether hook executed successfully
        modified_context: Optional context modifications to propagate
        error: Error message if hook failed
        execution_time_ms: Hook execution duration in milliseconds
        causal_chain_id: Optional causal chain ID from error tracking
    """

    success: bool
    modified_context: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    # For causal chain tracking
    causal_chain_id: str | None = None


@dataclass
class Hook:
    """Hook definition with priority and error handling.

    Attributes:
        name: Unique hook identifier
        hook_type: When this hook executes
        priority: Lower numbers execute earlier (0-1000 range)
        handler: Async function that processes the hook
        error_handler: Optional async error handler for this hook
        enabled: Whether hook is active
        metadata: Additional hook information

    Example:
        >>> async def my_handler(ctx: HookContext) -> HookResult:
        ...     return HookResult(success=True)
        >>> hook = Hook(
        ...     name="auto_format",
        ...     hook_type=HookType.POST_FILE_EDIT,
        ...     priority=100,
        ...     handler=my_handler
        ... )
    """

    name: str
    hook_type: HookType
    priority: int  # Lower = earlier execution
    handler: Callable[[HookContext], Awaitable[HookResult]]
    error_handler: Callable[[Exception], Awaitable[None]] | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class HooksManager:
    """Central hook management system.

    This manager handles:
        - Hook registration with priority ordering
        - Sequential hook execution with error handling
        - Integration with causal chain tracking
        - Default hook registration

    Usage:
        >>> manager = HooksManager()
        >>> await manager.initialize()
        >>> await manager.register_hook(my_hook)
        >>> results = await manager.execute_hooks(HookType.POST_CHECKPOINT, context)
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize hooks manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self._hooks: dict[HookType, list[Hook]] = {}
        self._causal_tracker: CausalChainTracker | None = None
        self._intelligence_engine: IntelligenceEngine | None = None

    async def initialize(self) -> None:
        """Initialize hook system with causal tracking and intelligence.

        This sets up:
            - Causal chain tracker integration
            - Intelligence engine for pattern learning
            - Default built-in hooks
            - Hook storage initialization
        """
        # Import here to avoid circular dependency
        from session_buddy.core.causal_chains import CausalChainTracker
        from session_buddy.core.intelligence import IntelligenceEngine

        # Initialize causal tracker
        self._causal_tracker = CausalChainTracker(logger=self.logger)
        await self._causal_tracker.initialize()

        # Initialize intelligence engine (optional - graceful degradation)
        try:
            self._intelligence_engine = IntelligenceEngine()
            await self._intelligence_engine.initialize()
        except Exception as e:
            self.logger.warning(
                "Intelligence engine initialization failed: %s. Pattern learning will be disabled.",
                e,
            )
            self._intelligence_engine = None

        # Register default built-in hooks
        await self._register_default_hooks()

        self.logger.info(
            "HooksManager initialized with causal_chain_tracker=%s, intelligence_engine=%s",
            self._causal_tracker is not None,
            self._intelligence_engine is not None,
        )

    async def register_hook(self, hook: Hook) -> None:
        """Register a new hook.

        Hooks are stored in priority order (lower numbers first).
        If a hook with the same name already exists for the same type,
        it will be replaced.

        Args:
            hook: Hook definition to register
        """
        if hook.hook_type not in self._hooks:
            self._hooks[hook.hook_type] = []

        # Check for existing hook with same name
        hooks = self._hooks[hook.hook_type]
        for i, existing in enumerate(hooks):
            if existing.name == hook.name:
                self.logger.info(
                    "Replacing existing hook: name=%s, type=%s",
                    hook.name,
                    hook.hook_type,
                )
                hooks[i] = hook
                return

        # Insert by priority (lower first)
        insert_idx = 0
        for i, existing in enumerate(hooks):
            if hook.priority < existing.priority:
                insert_idx = i
                break
            insert_idx = i + 1

        hooks.insert(insert_idx, hook)
        self.logger.debug(
            "Registered hook: name=%s, type=%s, priority=%d, position=%d",
            hook.name,
            hook.hook_type,
            hook.priority,
            insert_idx,
        )

    async def execute_hooks(
        self, hook_type: HookType, context: HookContext
    ) -> list[HookResult]:
        """Execute all hooks for a given type.

        Hooks execute in priority order (lower numbers first).
        Failed hooks don't stop execution of subsequent hooks.
        Modified context from each hook is accumulated.

        Args:
            hook_type: Type of hooks to execute
            context: Context to pass to each hook

        Returns:
            List of hook execution results in execution order
        """
        results: list[HookResult] = []

        if hook_type not in self._hooks:
            self.logger.debug("No hooks registered for type: %s", hook_type)
            return results

        hooks = self._hooks[hook_type]
        self.logger.debug(
            "Executing %d hooks for type=%s, session=%s",
            len(hooks),
            hook_type,
            context.session_id,
        )

        for hook in hooks:
            if not hook.enabled:
                self.logger.debug("Skipping disabled hook: %s", hook.name)
                continue

            try:
                start_time = datetime.now()
                result = await hook.handler(context)
                execution_time = (datetime.now() - start_time).total_seconds() * 1000

                result.execution_time_ms = execution_time
                results.append(result)

                # Update context with modifications from hook
                if result.modified_context:
                    context.metadata.update(result.modified_context)
                    self.logger.debug(
                        "Hook %s modified context with %d keys",
                        hook.name,
                        len(result.modified_context),
                    )

                self.logger.debug(
                    "Hook %s completed: success=%s, time=%.2fms",
                    hook.name,
                    result.success,
                    execution_time,
                )

            except Exception as e:
                self.logger.error(
                    "Hook %s failed: %s",
                    hook.name,
                    str(e),
                    exc_info=True,
                )

                # Try error handler if available
                if hook.error_handler:
                    try:
                        await hook.error_handler(e)
                    except Exception as eh:
                        self.logger.error(
                            "Hook error handler failed for %s: %s",
                            hook.name,
                            str(eh),
                            exc_info=True,
                        )

                results.append(HookResult(success=False, error=str(e)))

        self.logger.info(
            "Executed %d/%d hooks for type=%s: %d succeeded",
            len(results),
            len(hooks),
            hook_type,
            sum(1 for r in results if r.success),
        )

        return results

    async def _register_default_hooks(self) -> None:
        """Register built-in default hooks.

        These hooks provide core functionality:
            - Auto-formatting after file edits
            - Quality validation before checkpoints
            - Pattern learning from successful checkpoints
            - Error tracking for causal chains
            - Workflow metrics collection for monitoring
        """
        # Auto-formatting hook
        await self.register_hook(
            Hook(
                name="auto_format_python",
                hook_type=HookType.POST_FILE_EDIT,
                priority=100,
                handler=self._auto_format_handler,
            )
        )

        # Quality validation hook
        await self.register_hook(
            Hook(
                name="quality_validation",
                hook_type=HookType.PRE_CHECKPOINT,
                priority=50,
                handler=self._quality_validation_handler,
            )
        )

        # Pattern learning hook
        await self.register_hook(
            Hook(
                name="learn_from_checkpoint",
                hook_type=HookType.POST_CHECKPOINT,
                priority=200,
                handler=self._pattern_learning_handler,
            )
        )

        # Causal chain tracking hook
        await self.register_hook(
            Hook(
                name="track_error_fix_chain",
                hook_type=HookType.POST_ERROR,
                priority=10,
                handler=self._causal_chain_handler,
            )
        )

        # Workflow metrics collection hook
        await self.register_hook(
            Hook(
                name="collect_workflow_metrics",
                hook_type=HookType.POST_CHECKPOINT,
                priority=300,  # Run after pattern learning
                handler=self._workflow_metrics_handler,
            )
        )

        self.logger.info("Registered %d default hooks", 5)

    async def _auto_format_handler(self, context: HookContext) -> HookResult:
        """Auto-format Python files after edits.

        This hook runs crackerjack lint on Python files to ensure
        consistent code formatting after edits.

        Args:
            context: Hook context with file_path

        Returns:
            HookResult indicating success/failure
        """
        file_path = context.file_path

        if not file_path or not str(file_path).endswith(".py"):
            return HookResult(success=True)

        try:
            # Import here to avoid circular dependency
            from session_buddy.server import run_crackerjack_command

            await run_crackerjack_command(["lint", "--fix", str(file_path)], timeout=30)
            return HookResult(success=True)
        except Exception as e:
            self.logger.warning(
                "Auto-format failed for %s: %s",
                file_path,
                str(e),
            )
            return HookResult(success=False, error=str(e))

    async def _quality_validation_handler(self, context: HookContext) -> HookResult:
        """Validate quality before checkpoint.

        Ensures minimum quality threshold is met before allowing
        checkpoint to proceed.

        Args:
            context: Hook context with checkpoint_data

        Returns:
            HookResult with validation result
        """
        checkpoint_data = context.checkpoint_data or {}

        # Calculate quality score
        # Note: This would call the quality scoring system
        # For now, we'll extract it from checkpoint data
        quality_score = checkpoint_data.get("quality_score", 0)

        if quality_score < 60:
            return HookResult(
                success=False,
                error=f"Quality too low for checkpoint (score: {quality_score}/100)",
            )

        return HookResult(
            success=True,
            modified_context={"validated_quality": quality_score},
        )

    async def _pattern_learning_handler(self, context: HookContext) -> HookResult:
        """Learn from successful checkpoints.

        Extracts patterns from high-quality checkpoints (>85 score)
        and consolidates them into reusable skills.

        Args:
            context: Hook context with checkpoint_data

        Returns:
            HookResult indicating learning completed
        """
        checkpoint = context.checkpoint_data or {}

        # Only learn from high-quality checkpoints
        quality_score = checkpoint.get("quality_score", 0)
        if quality_score > 85 and self._intelligence_engine:
            try:
                # Extract patterns from this checkpoint
                pattern_ids = await self._intelligence_engine.learn_from_checkpoint(
                    checkpoint=checkpoint,
                )

                if pattern_ids:
                    self.logger.info(
                        "Extracted %d pattern(s) from checkpoint (quality=%s)",
                        len(pattern_ids),
                        quality_score,
                    )
                else:
                    self.logger.debug(
                        "No patterns extracted from checkpoint (quality=%s)",
                        quality_score,
                    )

            except Exception as e:
                # Don't fail the checkpoint if learning fails
                self.logger.warning(
                    "Pattern learning failed (quality=%s): %s",
                    quality_score,
                    e,
                    exc_info=True,
                )

        return HookResult(success=True)

    async def _causal_chain_handler(self, context: HookContext) -> HookResult:
        """Track error→fix causal chains.

        Records error events in causal chain tracker for
        debugging intelligence and pattern learning.

        Args:
            context: Hook context with error_info

        Returns:
            HookResult with causal_chain_id if tracking succeeded
        """
        error_info = context.error_info

        if not error_info or not self._causal_tracker:
            return HookResult(success=True)

        try:
            # Record in causal chain tracker
            chain_id = await self._causal_tracker.record_error_event(
                error=error_info.get("error_message", "Unknown error"),
                context=error_info.get("context", {}),
                session_id=context.session_id,
            )

            return HookResult(success=True, causal_chain_id=chain_id)
        except Exception as e:
            self.logger.error(
                "Causal chain tracking failed: %s",
                str(e),
                exc_info=True,
            )
            return HookResult(success=False, error=str(e))

    async def _workflow_metrics_handler(self, context: HookContext) -> HookResult:
        """Collect workflow metrics from checkpoints.

        Tracks session velocity, quality trends, and working patterns
        for comprehensive workflow analytics.

        Args:
            context: Hook context with checkpoint_data

        Returns:
            HookResult indicating metrics collection completed
        """
        checkpoint = context.checkpoint_data or {}

        try:
            # Import here to avoid circular dependency
            from session_buddy.core.workflow_metrics import get_workflow_metrics_engine

            engine = get_workflow_metrics_engine()
            await engine.initialize()

            # Get session start time from metadata
            session_start = checkpoint.get("session_start_time")
            if not session_start:
                # Use checkpoint timestamp if session start unavailable
                session_start = checkpoint.get("timestamp", datetime.now(UTC))

            # Collect and store metrics
            await engine.collect_session_metrics(
                session_id=context.session_id,
                project_path=checkpoint.get("working_directory", ""),
                started_at=session_start,
                checkpoint_data=checkpoint,
            )

            self.logger.debug(
                "Workflow metrics collected for session %s",
                context.session_id,
            )
            return HookResult(success=True)

        except Exception as e:
            self.logger.warning(
                "Workflow metrics collection failed for session %s: %s",
                context.session_id,
                str(e),
                exc_info=False,
            )
            # Don't fail checkpoint if metrics collection fails
            return HookResult(success=True)

    def list_hooks(
        self, hook_type: HookType | None = None
    ) -> dict[HookType, list[dict[str, Any]]]:
        """List registered hooks for inspection.

        Args:
            hook_type: Optional hook type filter. If None, returns all hooks.

        Returns:
            Dictionary mapping hook types to their registered hooks
        """
        if hook_type:
            hooks = self._hooks.get(hook_type, [])
            return {
                hook_type: [
                    {
                        "name": h.name,
                        "priority": h.priority,
                        "enabled": h.enabled,
                        "metadata": h.metadata,
                    }
                    for h in hooks
                ]
            }

        return {
            ht: [
                {
                    "name": h.name,
                    "priority": h.priority,
                    "enabled": h.enabled,
                    "metadata": h.metadata,
                }
                for h in hooks_list
            ]
            for ht, hooks_list in self._hooks.items()
        }
