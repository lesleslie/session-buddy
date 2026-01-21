# Hooks System and Causal Chain Tracking

**Phase 1 Feature** - Enhanced Automation and Debugging Intelligence

## Overview

Session Buddy now includes a comprehensive hooks system and causal chain tracking for intelligent automation and debugging assistance. This system enables:

- **Automated Workflows**: Execute custom logic at key session lifecycle points
- **Debugging Intelligence**: Learn from past errors to suggest fixes for new failures
- **Priority-Based Execution**: Control hook execution order with configurable priorities
- **Fault Tolerance**: Failed hooks don't break the session workflow

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Session Lifecycle                            │
│  (start, checkpoint, end, tool execution, file edits)         │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      HooksManager                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Hook Registry (by HookType)                              │  │
│  │  • PRE_CHECKPOINT                                         │  │
│  │  • POST_CHECKPOINT                                        │  │
│  │  • PRE_SESSION_END                                        │  │
│  │  • SESSION_END                                            │  │
│  │  • PRE_TOOL_EXECUTION                                     │  │
│  │  • POST_TOOL_EXECUTION                                    │  │
│  │  • POST_FILE_EDIT                                         │  │
│  │  • POST_ERROR (causal chain tracking)                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CausalChainTracker                             │
│  • Error Event Recording (with semantic embeddings)            │
│  • Fix Attempt Tracking                                       │
│  • Causal Chain Construction                                  │
│  • Similar Error Search (HNSW vector indexing)                │
└─────────────────────────────────────────────────────────────────┘
```

## Hook Types

### Pre-Operation Hooks

Execute before an operation occurs, can validate, modify, or cancel operations:

- `PRE_CHECKPOINT` - Before session checkpoint (quality validation, etc.)
- `PRE_TOOL_EXECUTION` - Before MCP tool execution
- `PRE_REFLECTION_STORE` - Before storing reflection/memory
- `PRE_SESSION_END` - Before session end (cleanup preparation)

### Post-Operation Hooks

Execute after an operation completes, can react to results:

- `POST_CHECKPOINT` - After checkpoint (pattern learning, etc.)
- `POST_TOOL_EXECUTION` - After tool execution
- `POST_FILE_EDIT` - After file edits
- `POST_ERROR` - After errors occur (causal chain tracking)

### Session Boundary Hooks

Execute at session lifecycle boundaries:

- `SESSION_START` - When session starts
- `SESSION_END` - When session ends (final cleanup)
- `USER_PROMPT_SUBMIT` - When user submits a prompt

## Usage Examples

### Registering a Custom Hook

```python
from session_buddy.core.hooks import Hook, HookContext, HookResult, HookType, HooksManager
from session_buddy.di import get_sync_typed

# Define your hook handler
async def my_custom_hook(context: HookContext) -> HookResult:
    """Custom hook logic here."""
    quality_score = context.metadata.get("quality_score", 0)

    if quality_score < 70:
        return HookResult(
            success=True,
            modified_context={"suggested_action": "Improve code quality"}
        )

    return HookResult(success=True)

# Register the hook
manager = get_sync_typed(HooksManager)
hook = Hook(
    name="quality_improvement_suggester",
    hook_type=HookType.POST_CHECKPOINT,
    priority=100,  # Lower = earlier execution
    handler=my_custom_hook,
    enabled=True,
    metadata={"description": "Suggests quality improvements"}
)

await manager.register_hook(hook)
```

### Accessing Hook Context Data

```python
async def context_aware_hook(context: HookContext) -> HookResult:
    """Hook that reads and uses context data."""

    # Access metadata
    quality_score = context.metadata.get("quality_score")
    is_manual = context.metadata.get("is_manual", False)

    # Access checkpoint data (for checkpoint hooks)
    if context.checkpoint_data:
        recommendations = context.checkpoint_data.get("recommendations", [])

    # Access error info (for error hooks)
    if context.error_info:
        error_message = context.error_info.get("error_message")

    return HookResult(success=True)
```

### Error Handling in Hooks

```python
async def safe_hook_with_error_handler(context: HookContext) -> HookResult:
    """Hook with custom error handling."""

    async def handle_error(exc: Exception) -> None:
        """Custom error handler for failed hook execution."""
        logger.error(f"Hook failed: {exc}")
        # Custom error handling logic (cleanup, notifications, etc.)

    hook = Hook(
        name="safe_hook",
        hook_type=HookType.PRE_CHECKPOINT,
        priority=100,
        handler=context_aware_hook,
        error_handler=handle_error,  # Optional custom error handler
        enabled=True
    )

    return await hook.handler(context)
```

## Causal Chain Tracking

The causal chain tracker provides debugging intelligence by learning from past failures:

### Recording Errors

```python
from session_buddy.core.causal_chains import CausalChainTracker
from session_buddy.di import get_sync_typed

tracker = get_sync_typed(CausalChainTracker)

# Record an error event
error_id = await tracker.record_error_event(
    error="ImportError: module 'numpy' not found",
    context={
        "error_type": "ImportError",
        "file": "data_processor.py",
        "line": 15,
        "code": "import numpy as np"
    },
    session_id="session-123"
)
# Returns: "err-a1b2c3d4"
```

### Recording Fix Attempts

```python
# Record a fix attempt
attempt_id = await tracker.record_fix_attempt(
    error_id=error_id,
    action_taken="Added missing import statement",
    code_changes="import numpy as np",
    successful=True
)
# Returns: "fix-e5f6g7h8"
```

### Querying Similar Errors

```python
# Find similar past errors when encountering a new error
similar_errors = await tracker.query_similar_failures(
    current_error="ImportError: module 'pandas' not found",
    limit=5
)

# Returns list of similar errors with context:
# [
#   {
#     "error_message": "ImportError: module 'numpy' not found",
#     "error_type": "ImportError",
#     "context": {"file": "data_processor.py", ...},
#     "similarity": 0.85,
#     "successful_fixes": [
#       {
#         "action_taken": "Added missing import",
#         "code_changes": "import numpy as np",
#         "resolution_time_minutes": 2.5
#       }
#     ]
#   },
#   ...
# ]
```

### Retrieving Causal Chains

```python
# Get complete causal chain for a fix attempt
chain = await tracker.get_causal_chain(attempt_id)

if chain:
    print(f"Error: {chain.error_event.error_message}")
    print(f"Resolution time: {chain.resolution_time_minutes} minutes")

    for attempt in chain.fix_attempts:
        print(f"  Attempt: {attempt.action_taken}")
        print(f"  Successful: {attempt.successful}")
```

## Default Hooks

Session Buddy includes several default hooks:

### Auto-Format Python (priority=100)

Automatically formats Python code after file edits.

### Quality Validation (priority=50)

Validates quality metrics before checkpoints.

### Learn from Checkpoint (priority=200)

Extracts insights from checkpoint data for learning.

### Track Error Fix Chain (priority=10)

Records errors and fix attempts for causal chain tracking.

## Priority System

Hooks execute in priority order (lower number = earlier execution):

- **0-49**: Critical validation hooks
- **50-99**: Quality checks and validation
- **100-199**: Standard automation hooks
- **200-299**: Learning and analysis hooks
- **300-999**: Optional and user-defined hooks

Example:

```python
# High priority (executes first)
high_priority_hook = Hook(name="validator", priority=10, ...)

# Medium priority
medium_priority_hook = Hook(name="formatter", priority=150, ...)

# Low priority (executes last)
low_priority_hook = Hook(name="logger", priority=500, ...)
```

## MCP Tools

The hooks system exposes several MCP tools for Claude Code integration:

### `list_hooks`

List all registered hooks, optionally filtered by type.

```python
@mcp.tool()
async def list_hooks(hook_type: Optional[str] = None) -> dict[str, Any]:
    """List registered hooks.

    Args:
        hook_type: Optional filter by hook type

    Returns:
        Dictionary with hook list and metadata
    """
```

### `enable_hook` / `disable_hook`

Enable or disable specific hooks.

```python
@mcp.tool()
async def enable_hook(hook_name: str, hook_type: str) -> dict[str, Any]:
    """Enable a hook.

    Args:
        hook_name: Name of hook to enable
        hook_type: Type of hook

    Returns:
        Success status
    """
```

### `query_similar_errors`

Query for similar past errors using semantic search.

```python
@mcp.tool()
async def query_similar_errors(
    error_message: str,
    limit: int = 5
) -> dict[str, Any]:
    """Query similar errors.

    Args:
        error_message: Current error message
        limit: Maximum number of results

    Returns:
        List of similar errors with fix suggestions
    """
```

### `record_fix_success`

Record a successful fix for tracking.

```python
@mcp.tool()
async def record_fix_success(
    error_message: str,
    action_taken: str,
    code_changes: Optional[str] = None,
    resolution_time_minutes: Optional[float] = None
) -> dict[str, Any]:
    """Record successful fix.

    Args:
        error_message: Error that was fixed
        action_taken: Description of fix
        code_changes: Optional code changes
        resolution_time_minutes: Time to fix

    Returns:
        Fix attempt ID and causal chain ID
    """
```

### `get_causal_chain`

Retrieve complete causal chain for a fix attempt.

```python
@mcp.tool()
async def get_causal_chain(chain_id: str) -> dict[str, Any]:
    """Get causal chain details.

    Args:
        chain_id: Causal chain ID

    Returns:
        Complete chain with error and all attempts
    """
```

## Database Schema

The causal chain tracker uses three DuckDB tables:

### `causal_error_events`

Stores error records with semantic embeddings:

```sql
CREATE TABLE causal_error_events (
    id TEXT PRIMARY KEY,
    error_message TEXT,
    error_type TEXT,
    context TEXT,  -- JSON
    timestamp TIMESTAMP,
    session_id TEXT,
    embedding FLOAT[384]  -- Semantic vector for similarity search
)
```

### `causal_fix_attempts`

Stores fix attempts linked to errors:

```sql
CREATE TABLE causal_fix_attempts (
    id TEXT PRIMARY KEY,
    error_id TEXT,
    action_taken TEXT,
    code_changes TEXT,
    successful BOOLEAN,
    timestamp TIMESTAMP,
    FOREIGN KEY (error_id) REFERENCES causal_error_events(id)
)
```

### `causal_chains`

Stores completed causal chains:

```sql
CREATE TABLE causal_chains (
    id TEXT PRIMARY KEY,
    error_id TEXT,
    successful_fix_id TEXT,
    resolution_time_minutes FLOAT,
    created_at TIMESTAMP,
    FOREIGN KEY (error_id) REFERENCES causal_error_events(id),
    FOREIGN KEY (successful_fix_id) REFERENCES causal_fix_attempts(id)
)
```

### Vector Index

HNSW index for fast semantic similarity search:

```sql
CREATE INDEX idx_causal_error_events_embeddings
ON causal_error_events USING HNSW (embedding)
WITH (metric = 'cosine', M = 16, ef_construction = 200)
```

## Design Patterns

### Fault Tolerance

All hook execution is wrapped in error handling:

```python
try:
    results = await hooks_manager.execute_hooks(HookType.PRE_CHECKPOINT, context)
except Exception as e:
    logger.warning("PRE_CHECKPOINT hooks failed: %s", str(e))
    # Session continues despite hook failure
```

### Context Propagation

Hooks can modify context that propagates to subsequent hooks:

```python
result = HookResult(
    success=True,
    modified_context={"suggested_quality_improvements": [...]}
)
```

### Semantic Search

Error similarity uses cosine similarity on 384-dimensional embeddings:

```sql
SELECT error_message, error_type, context,
       array_cosine_similarity(embedding, $1) as similarity
FROM causal_error_events
WHERE similarity > 0.7
ORDER BY similarity DESC, timestamp DESC
LIMIT 5
```

## Testing

The hooks system includes comprehensive unit tests:

```bash
# Run hooks system tests
pytest tests/unit/test_hooks_system.py -v

# Run specific test class
pytest tests/unit/test_hooks_system.py::TestHooksManager -v

# Run with coverage
pytest tests/unit/test_hooks_system.py --cov=session_buddy.core.hooks --cov=session_buddy.core.causal_chains
```

Test coverage includes:

- Hook registration and execution
- Priority ordering
- Enabled/disabled state
- Error handling and fault tolerance
- Context data access
- Causal chain dataclass structure
- Error event and fix attempt creation

## Integration with Session Lifecycle

Hooks are integrated into key session methods:

### Checkpoint Session

```python
# In checkpoint_session method:
pre_hooks_results = await hooks_manager.execute_hooks(
    HookType.PRE_CHECKPOINT, pre_context
)

# ... quality assessment and git checkpoint ...

post_hooks_results = await hooks_manager.execute_hooks(
    HookType.POST_CHECKPOINT, post_context
)
```

### End Session

```python
# In end_session method:
pre_hooks_results = await hooks_manager.execute_hooks(
    HookType.PRE_SESSION_END, pre_context
)

# ... final quality assessment and handoff ...

post_hooks_results = await hooks_manager.execute_hooks(
    HookType.SESSION_END, post_context
)
```

## Performance Considerations

- **Async Execution**: All hooks execute asynchronously to avoid blocking
- **Priority Sorting**: O(n log n) sorting by priority for each hook type
- **HNSW Index**: O(log n) similarity search for error patterns
- **Connection Pooling**: Database operations use connection pooling
- **Fault Isolation**: Failed hooks don't block subsequent hooks

## Future Enhancements

Potential future improvements:

1. **Hook Dependencies**: Allow hooks to depend on other hooks
1. **Conditional Execution**: More sophisticated hook enabling conditions
1. **Hook Composition**: Combine multiple hooks into composite hooks
1. **Distributed Tracking**: Share causal chains across projects
1. **ML-Based Suggestions**: Use ML to predict successful fixes
1. **Hook Templates**: Pre-built hook templates for common tasks

## Troubleshooting

### Hooks Not Executing

Check that:

1. Hooks are registered: `await manager.register_hook(hook)`
1. Hooks are enabled: `hook.enabled = True`
1. Correct hook type is used
1. No exceptions in hook handler

### Causal Chain Tracking Not Working

Check that:

1. CausalChainTracker is initialized: `await tracker.initialize()`
1. Database adapter is available in DI container
1. Embeddings are being generated (check ONNX runtime)

### Priority Order Issues

Remember:

- Lower priority numbers execute FIRST (priority 10 before priority 100)
- Same priority hooks execute in registration order
- Use priority ranges consistently (10, 20, 30 not 10, 11, 12)

## See Also

- **Core Implementation**: `session_buddy/core/hooks.py`, `session_buddy/core/causal_chains.py`
- **MCP Tools**: `session_buddy/tools/hooks_tools.py`
- **Tests**: `tests/unit/test_hooks_system.py`
- **Integration Plan**: `docs/migrations/CLAUDE_FLOW_INTEGRATION_PLAN_V2.md`
