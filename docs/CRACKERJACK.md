# Crackerjack Integration

This document provides comprehensive guidance on session-buddy's deep integration with [Crackerjack](https://github.com/lesleslie/crackerjack), the AI-driven Python development platform.

## Table of Contents

1. [Quick Start](#quick-start)
1. [MCP Tool Interface](#mcp-tool-interface)
1. [Integration Architecture](#integration-architecture)
1. [Hook Output Parsing](#hook-output-parsing)
1. [API Reference](#api-reference)
1. [Workflow Examples](#workflow-examples)
1. [Configuration](#configuration)
1. [Troubleshooting](#troubleshooting)

______________________________________________________________________

## Quick Start

### Basic Usage

```text
# Via MCP tool
await crackerjack_run(command="test")

# With AI auto-fix enabled
await crackerjack_run(command="test", ai_agent_mode=True)

# With additional arguments
await crackerjack_run(
    command="check", args="--verbose", ai_agent_mode=True, timeout=600
)
```

### Available Commands

```text
# Quality checks
crackerjack_run(command="check")  # Basic quality checks
crackerjack_run(command="lint")  # Linting and style
crackerjack_run(command="test")  # Test execution
crackerjack_run(command="analyze")  # Comprehensive analysis

# Security and complexity
crackerjack_run(command="security")  # Security scanning
crackerjack_run(command="complexity")  # Complexity analysis
crackerjack_run(command="coverage")  # Coverage reporting

# Maintenance
crackerjack_run(command="format")  # Code formatting
crackerjack_run(command="clean")  # Cleanup operations
```

______________________________________________________________________

## MCP Tool Interface

### Tool Definition

The integration provides a sophisticated MCP tool with input validation and error handling:

```text
@mcp.tool()
async def crackerjack_run(
    command: str,
    args: str = "",
    working_directory: str = ".",
    timeout: int = 300,
    ai_agent_mode: bool = False,
) -> str:
    """Run crackerjack with enhanced analytics and optional AI auto-fix.

    Args:
        command: Semantic command (test, lint, check, etc.)
        args: Additional arguments (NOT --ai-fix)
        working_directory: Working directory (default: ".")
        timeout: Timeout in seconds (default: 300)
        ai_agent_mode: Enable AI auto-fix (default: False)

    Returns:
        Formatted execution results with status and metrics
    """
```

### Parameter Validation

The tool includes comprehensive input validation to prevent common mistakes:

**✅ Correct Usage:**

```python
# Semantic command with ai_agent_mode
await crackerjack_run(command="test", ai_agent_mode=True)

# With additional args
await crackerjack_run(command="check", args="--verbose", ai_agent_mode=True)

# Dry-run mode
await crackerjack_run(command="test", args="--dry-run", ai_agent_mode=True)
```

**❌ Incorrect Usage (Will Error):**

```python
# Flags in command parameter
await crackerjack_run(command="--ai-fix -t")
# Error: "Invalid Command: '--ai-fix'"

# --ai-fix in args parameter
await crackerjack_run(command="test", args="--ai-fix")
# Error: "Invalid Args: Found '--ai-fix' in args parameter"

# Unknown command
await crackerjack_run(command="invalid")
# Error: "Unknown Command: 'invalid'"
```

### Valid Commands

| Command | Description |
|---------|-------------|
| `all` | Run all quality checks |
| `check` | Basic quality verification |
| `analyze` | Comprehensive code analysis |
| `test` | Execute test suite |
| `lint` | Linting and style checks |
| `format` | Code formatting |
| `typecheck` | Type checking |
| `security` | Security vulnerability scanning |
| `complexity` | Cognitive complexity analysis |
| `coverage` | Test coverage reporting |
| `build` | Build operations |
| `clean` | Cleanup operations |
| `docs` | Documentation generation |

______________________________________________________________________

## Integration Architecture

### Component Architecture

```
┌─────────────────┐
│   Claude Code   │
│   (User Agent)  │
└────────┬────────┘
         │ MCP Protocol
         ▼
┌─────────────────────────────────┐
│  session-buddy MCP Server    │
│                                 │
│  ┌───────────────────────────┐ │
│  │  crackerjack_tools.py     │ │
│  │  - Input Validation       │ │
│  │  - Command Building       │ │
│  │  - Result Formatting      │ │
│  └───────────┬───────────────┘ │
│              │                  │
│  ┌───────────▼───────────────┐ │
│  │  hook_parser.py           │ │
│  │  - Reverse Parsing        │ │
│  │  - Status Extraction      │ │
│  └───────────┬───────────────┘ │
│              │                  │
│  ┌───────────▼───────────────┐ │
│  │  crackerjack_integration  │ │
│  │  - Quality Metrics        │ │
│  │  - Test Analysis          │ │
│  │  - Progress Tracking      │ │
│  └───────────────────────────┘ │
└────────────┬────────────────────┘
             │ subprocess
             ▼
     ┌────────────────┐
     │  Crackerjack   │
     │  CLI Process   │
     └────────────────┘
```

### Integration Module Features

The `crackerjack_integration.py` module (50KB+) provides:

- **Command Execution Framework** - Direct command execution with result capture
- **Progress Monitoring System** - Real-time tracking during operations
- **Quality Metrics Intelligence** - Advanced metric extraction and trend analysis
- **Test Pattern Recognition** - Test result monitoring and pattern detection
- **Error Resolution Learning** - Building knowledge base of project-specific fixes
- **Build Status Tracking** - Comprehensive build and deployment monitoring

### Data Flow

```
User Request
    ↓
MCP Tool (crackerjack_run)
    ↓
Validate Command & Args
    ↓
Build Crackerjack Command
    ↓
Execute Subprocess
    ↓
Parse Hook Output
    ↓
Extract Quality Metrics
    ↓
Format Results
    ↓
Store Session Memory
    ↓
Return to User
```

### CLI Structure Transformation

The integration handles the transformation from semantic commands to the **new Crackerjack CLI structure (v0.47+)**:

**OLD CLI (v0.46 and earlier):**

```text
python -m crackerjack --fast
python -m crackerjack --test
python -m crackerjack --comp
```

**NEW CLI (v0.47+):**

```text
python -m crackerjack run --fast
python -m crackerjack run --run-tests
python -m crackerjack run --comp
```

**Command Mapping:**

| Semantic Command | CLI Flags | Description |
|-----------------|-----------|-------------|
| `lint` | `run --fast --quick` | Fast linting hooks |
| `check` | `run --comp --quick` | Comprehensive checks |
| `test` | `run --run-tests --quick` | Test execution |
| `format` | `run --fast --quick` | Code formatting |
| `typecheck` | `run --comp --quick` | Type checking |
| `security` | `run --comp` | Security scanning (in comp) |
| `complexity` | `run --comp` | Complexity analysis (in comp) |
| `analyze` | `run --comp` | Comprehensive analysis |
| `build` | `run` | Build operations |
| `clean` | `run` | Cleanup operations |
| `all` | `run` | All quality checks (NOT `--all` which requires version arg) |

**Implementation:**

The `_build_command_flags()` method in `crackerjack_integration.py` performs this transformation:

```python
def _build_command_flags(self, command: str, ai_agent_mode: bool) -> list[str]:
    """Build appropriate command flags for the given command.

    NEW Crackerjack CLI structure (v0.47+):
    - Uses 'run' subcommand followed by flags
    - Example: python -m crackerjack run --fast --quick
    """
    command_mappings = {
        "lint": ["run", "--fast"],
        "check": ["run", "--comp"],
        "test": ["run", "--run-tests"],
        # ... (see full implementation)
    }

    flags = command_mappings.get(command.lower(), ["run"])
    if ai_agent_mode:
        flags.append("--ai-fix")
    return flags
```

This abstraction layer means:

- ✅ Users work with simple semantic commands (`lint`, `test`, `check`)
- ✅ Integration handles CLI complexity automatically
- ✅ Easy to adapt to future CLI changes
- ✅ Consistent interface across Crackerjack versions

______________________________________________________________________

## Hook Output Parsing

### Reverse Parsing Algorithm

The integration uses a **reverse parsing** algorithm to reliably extract hook names and status markers from crackerjack output:

```python
def parse_hook_line(line: str) -> HookResult:
    """Parse hook output line using reverse parsing.

    Format: hook_name + padding_dots + space + status_marker
    Example: "refurb...................... ❌"

    Algorithm:
        1. Split from right on whitespace
        2. Validate status marker
        3. Extract hook name (strip padding dots)
    """
    # Step 1: Split from right
    left_part, status_marker = line.rsplit(maxsplit=1)

    # Step 2: Validate status marker
    if status_marker not in ["✅", "Passed", "❌", "Failed"]:
        raise ParseError(f"Unknown status marker: {status_marker}")

    # Step 3: Extract hook name
    hook_name = left_part.rstrip(".")

    return HookResult(hook_name=hook_name, passed=(status_marker in ["✅", "Passed"]))
```

### Why Reverse Parsing?

**Problem:** Hook names can contain dots (e.g., `test.integration.api`)

**Solution:** Parse from right to left:

1. Split on last whitespace: `hook_name....... ❌` → `[hook_name......., ❌]`
1. Strip dots from right: `hook_name.......` → `hook_name`
1. Handles any hook name pattern correctly

### Example Parsing

```
Input: "test.integration.api...................... ✅"

Step 1 - rsplit(maxsplit=1):
  ["test.integration.api......................", "✅"]

Step 2 - Validate marker:
  "✅" in PASS_MARKERS → True

Step 3 - rstrip("."):
  "test.integration.api......................" → "test.integration.api"

Result:
  HookResult(hook_name="test.integration.api", passed=True)
```

### Supported Status Markers

**Pass Markers:**

- `✅` (green checkmark)
- `Passed` (text)

**Fail Markers:**

- `❌` (red X)
- `Failed` (text)

______________________________________________________________________

## API Reference

### Core Functions

#### execute_crackerjack_command()

Execute a Crackerjack command with comprehensive result capture:

```python
async def execute_crackerjack_command(
    command: str,
    *,
    test: bool = False,
    ai_agent: bool = False,
    interactive: bool = False,
    verbose: bool = False,
    working_directory: str | None = None,
    timeout: int = 300,
    capture_progress: bool = True,
) -> CrackerjackResult:
    """Execute Crackerjack command with full result capture.

    Args:
        command: Crackerjack command to execute
        test: Include test execution
        ai_agent: Enable AI agent auto-fixing
        interactive: Enable interactive mode
        verbose: Enable verbose output
        working_directory: Directory to execute in
        timeout: Command timeout in seconds
        capture_progress: Enable real-time progress capture

    Returns:
        Comprehensive execution result with metrics
    """
```

#### get_crackerjack_quality_metrics()

Retrieve quality metrics with trend analysis:

```python
async def get_crackerjack_quality_metrics(
    *,
    days: int = 30,
    working_directory: str | None = None,
    include_trends: bool = True,
    metric_types: list[QualityMetric] | None = None,
) -> dict[str, Any]:
    """Retrieve quality metrics with trend analysis.

    Args:
        days: Number of days to analyze
        working_directory: Project directory
        include_trends: Include trend calculations
        metric_types: Specific metrics to retrieve

    Returns:
        Quality metrics with trends and analysis
    """
```

#### analyze_crackerjack_test_patterns()

Analyze test execution patterns for optimization:

```python
async def analyze_crackerjack_test_patterns(
    *,
    days: int = 7,
    working_directory: str | None = None,
    include_failures: bool = True,
    pattern_types: list[str] | None = None,
) -> dict[str, Any]:
    """Analyze test patterns for workflow optimization.

    Args:
        days: Analysis period in days
        working_directory: Project directory
        include_failures: Include failure pattern analysis
        pattern_types: Specific pattern types to analyze

    Returns:
        Test patterns and optimization suggestions
    """
```

### Data Models

#### CrackerjackResult

```python
@dataclass
class CrackerjackResult:
    command: str  # Command executed
    exit_code: int  # Process exit code
    stdout: str  # Standard output
    stderr: str  # Standard error
    execution_time: float  # Execution time (seconds)
    timestamp: datetime  # Completion timestamp
    working_directory: str  # Execution directory
    parsed_data: dict[str, Any] | None  # Structured data
    quality_metrics: dict[str, float]  # Quality scores
    test_results: list[dict[str, Any]]  # Individual test results
    memory_insights: list[str]  # Session insights
```

#### QualityMetric

```text
class QualityMetric(Enum):
    CODE_COVERAGE = "coverage"  # Test coverage %
    COMPLEXITY = "complexity"  # Cognitive complexity
    LINT_SCORE = "lint_score"  # Code quality score
    SECURITY_SCORE = "security_score"  # Security assessment
    TEST_PASS_RATE = "test_pass_rate"  # Test success rate
    BUILD_STATUS = "build_status"  # Build success/failure
```

______________________________________________________________________

## Workflow Examples

### Basic Quality Check

```text
# Run all hooks without auto-fix
result = await crackerjack_run(command="check")

# Output:
"""
✅ **Status**: Success

All hooks passed successfully!
"""
```

### AI-Powered Auto-Fix Workflow

```text
# Run with AI auto-fix enabled
result = await crackerjack_run(
    command="test",
    ai_agent_mode=True,
    timeout=600,  # Allow time for AI fixes
)

# Output (if fixes applied):
"""
✅ **Status**: Success after 3 iterations

**Fixes Applied**: 5
- refurb: Fixed unnecessary comprehension
- complexity: Simplified nested conditions
- ruff: Fixed line length issues

**Convergence**: All hooks now passing
"""
```

### Quality Trend Analysis

```python
# Get 30-day quality trend
metrics = await get_crackerjack_quality_metrics(
    days=30, working_directory="/path/to/project", include_trends=True
)

# Analyze trends
coverage_trend = metrics["trends"]["coverage"]
if coverage_trend["direction"] == "improving":
    print(f"Coverage improving by {coverage_trend['rate']:.1f}% per week")
else:
    print(f"Coverage declining by {coverage_trend['rate']:.1f}% per week")
```

### Test Pattern Recognition

```python
# Analyze test patterns
patterns = await analyze_crackerjack_test_patterns(
    days=7, working_directory="/path/to/project", include_failures=True
)

# Show failure patterns
for pattern in patterns["failure_patterns"]:
    print(f"Frequent failure: {pattern['error_type']}")
    print(f"Success rate: {pattern['success_rate']:.1f}%")
    print(f"Suggested fix: {pattern['suggested_fix']}")
```

### Integrated Session Workflow

```python
async def development_session():
    """Complete development session with quality tracking."""

    # 1. Initialize session
    await init_session_with_crackerjack_context()

    # 2. Run quality analysis
    result = await execute_crackerjack_command("analyze", test=True, ai_agent=True)

    # 3. Store results for future sessions
    await store_quality_metrics(result.quality_metrics)
    await store_test_results(result.test_results)

    # 4. Generate insights
    insights = await generate_session_insights(result)
    await store_reflection(
        content=f"Quality: {result.quality_metrics.get('overall_score')}",
        tags=["quality", "crackerjack", "analysis"],
    )

    return result
```

______________________________________________________________________

## Configuration

### MCP Server Settings

**Location:** `session_buddy/config.py`

```python
# Crackerjack integration settings
CRACKERJACK_TIMEOUT_DEFAULT = 300  # 5 minutes
CRACKERJACK_TIMEOUT_MAX = 1800  # 30 minutes
CRACKERJACK_MAX_RETRIES = 3
```

### Hook Parser Settings

**Location:** `session_buddy/tools/hook_parser.py`

```python
# Status markers (frozen sets for performance)
_PASS_MARKERS = frozenset(["✅", "Passed"])
_FAIL_MARKERS = frozenset(["❌", "Failed"])
```

### Environment Variables

```bash
# Optional: Override crackerjack binary location
export CRACKERJACK_BIN=/path/to/crackerjack

# Optional: Default working directory
export CRACKERJACK_WORKDIR=/path/to/project

# Integration control
export CRACKERJACK_INTEGRATION_ENABLED="true"
export CRACKERJACK_CAPTURE_PROGRESS="true"
export CRACKERJACK_STORE_METRICS="true"
export CRACKERJACK_AI_LEARNING="true"
```

### Integration Configuration

```text
# Configuration file settings
integration_config = {
    "enabled": True,
    "max_execution_time": 600,
    "capture_progress": True,
    "store_metrics": True,
    "ai_learning": True,
    "quality_thresholds": {
        "coverage_minimum": 10.0,
        "complexity_maximum": 15,
        "security_score_minimum": 8.0,
    },
}
```

______________________________________________________________________

## Error Handling

### Input Validation Errors

**Error: Command with flags**

````text
await crackerjack_run(command="--ai-fix")

# Returns:
"""
❌ **Invalid Command**: '--ai-fix'

**Error**: Commands should be semantic names, not flags.

**Valid commands**: all, check, complexity, format, lint, security, test

**Correct usage**:
```text
crackerjack_run(command='test', ai_agent_mode=True)
````

"""

````

**Error: --ai-fix in args**
```text
await crackerjack_run(command="test", args="--ai-fix")

# Returns:
"""
❌ **Invalid Args**: Found '--ai-fix' in args parameter

**Use instead**: Set `ai_agent_mode=True` parameter

**Correct**:
```text
crackerjack_run(command='test', ai_agent_mode=True)
````

"""

````

### Execution Errors

**Timeout:**
```text
await crackerjack_run(command="all", timeout=10)

# Returns:
"""
❌ **Execution Error**: Command timed out after 10 seconds

**Suggestion**: Increase timeout parameter or run fewer hooks
"""
````

**Hook Failures:**

```text
# When hooks fail (basic mode)
result = await crackerjack_run(command="lint")

# Output:
"""
❌ **Status**: Failed (exit code: 1)
**Failed Hooks**: refurb, complexipy

refurb................................................................ ❌
complexipy............................................................ ❌
bandit................................................................ ✅
ruff.................................................................. ✅
"""
```

______________________________________________________________________

## Troubleshooting

### MCP Server Not Responding

**Symptoms:** Timeout or no response

**Solutions:**

1. Check MCP server running: `pgrep -fl session-buddy`
1. Restart MCP server
1. Check logs: `tail -f ~/.claude/logs/session-buddy.log`

### Hook Parsing Fails

**Symptoms:** "ParseError" in output

**Causes:**

- Unexpected hook output format
- Extra characters in hook output
- Status markers changed

**Solutions:**

1. Check raw hook output
1. Verify hook configuration
1. Update `hook_parser.py` if format changed

### Command Validation Errors

**Symptoms:** "Invalid Command" or "Invalid Args" errors

**Solutions:**

- Use semantic commands: `test`, `lint`, `check`
- Don't put flags in `command` parameter
- Use `ai_agent_mode=True` instead of `--ai-fix`

### Performance Issues

```python
# Monitor performance
perf_stats = await get_integration_performance_stats()
print(f"Avg execution: {perf_stats['avg_execution_time']:.2f}s")
print(f"Memory usage: {perf_stats['memory_mb']:.1f}MB")
print(f"Cache hit rate: {perf_stats['cache_hit_rate']:.1f}%")
```

### Debug Mode

```python
import logging

# Enable debug logging
logging.getLogger("session_buddy.crackerjack_integration").setLevel(logging.DEBUG)

# Execute with verbose output
result = await execute_crackerjack_command("test", verbose=True, capture_progress=True)
```

______________________________________________________________________

## Advanced Features

### Predictive Analysis

```python
# Predict completion time
prediction = await predict_crackerjack_completion_time(
    command="test", ai_agent=True, project_size_lines=15000, test_count=450
)

print(f"Estimated: {prediction['estimated_minutes']} minutes")
print(f"Confidence: {prediction['confidence']:.1f}%")
```

### Error Pattern Learning

```python
# Record successful fix
await record_successful_fix(
    error_pattern="F401: imported but unused",
    fix_method="ai_agent_refactoring",
    success_rate=0.95,
    project_context="/path/to/project",
)

# Query historical fixes
fixes = await get_historical_fixes(
    error_pattern="complexity exceeds 15", confidence_threshold=0.8
)
```

### Workflow Optimization

```python
# Get optimized workflow suggestions
suggestions = await get_workflow_suggestions(
    current_state="test_failures", project_type="python_package", quality_score=75
)

for suggestion in suggestions["recommended_sequence"]:
    print(f"Step {suggestion['order']}: {suggestion['command']}")
    print(f"Success rate: {suggestion['success_rate']:.1f}%")
    print(f"Expected improvement: +{suggestion['quality_improvement']:.1f}")
```

______________________________________________________________________

## Resources

**Documentation:**

- [Crackerjack GitHub](https://github.com/lesleslie/crackerjack)
- [MCP Protocol Specification](https://modelcontextprotocol.io)

**Project Files:**

- Integration module: `session_buddy/crackerjack_integration.py`
- MCP tools: `session_buddy/tools/crackerjack_tools.py`
- Hook parser: `session_buddy/tools/hook_parser.py`

**Testing:**

- Unit tests: `tests/unit/test_hook_parser.py`
- Integration tests: `tests/integration/test_crackerjack_integration.py`

______________________________________________________________________

**Last Updated:** 2025-01-04
**Version:** 2.0
**Status:** Production Ready
