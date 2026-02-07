#!/usr/bin/env python3
"""MCP prompt management tools.

This module provides all MCP prompt definitions following crackerjack
architecture patterns with single responsibility principle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from session_buddy.session_commands import SESSION_COMMANDS

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


@dataclass(frozen=True)
class PromptDefinition:
    """Immutable prompt definition with metadata."""

    name: str
    description: str
    content_key: str | None = None
    content: str | None = None

    def get_content(self) -> str:
        """Get prompt content from key or direct content."""
        if self.content_key:
            return SESSION_COMMANDS[self.content_key]
        return self.content or ""


# Core session management prompts
CORE_PROMPTS: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        "init",
        "Initialize Claude session with comprehensive setup including UV dependencies, global workspace verification, and automation tools.",
        content_key="init",
    ),
    PromptDefinition(
        "checkpoint",
        "Perform mid-session quality checkpoint with workflow analysis and optimization recommendations.",
        content_key="checkpoint",
    ),
    PromptDefinition(
        "end",
        "End Claude session with cleanup, learning capture, and handoff file creation.",
        content_key="end",
    ),
    PromptDefinition(
        "status",
        "Get current session status and project context information with health checks.",
        content_key="status",
    ),
)

# Permission and reflection prompts
REFLECTION_PROMPTS: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        "permissions",
        "Manage session permissions for trusted operations to avoid repeated prompts.",
        content_key="permissions",
    ),
    PromptDefinition(
        "reflect",
        "Search past conversations and store reflections with semantic similarity.",
        content_key="reflect",
    ),
    PromptDefinition(
        "quick-search",
        "Quick search that returns only the count and top result for fast overview.",
        content_key="quick-search",
    ),
    PromptDefinition(
        "search-summary",
        "Get aggregated insights from search results without individual result details.",
        content_key="search-summary",
    ),
    PromptDefinition(
        "reflection-stats",
        "Get statistics about the reflection database and conversation memory.",
        content_key="reflection-stats",
    ),
)

# Crackerjack integration prompts
CRACKERJACK_PROMPTS: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        "crackerjack-run",
        "Execute a Crackerjack command and parse the output for insights.",
        content_key="crackerjack-run",
    ),
    PromptDefinition(
        "crackerjack-history",
        "Get recent Crackerjack command execution history with parsed results.",
        content_key="crackerjack-history",
    ),
    PromptDefinition(
        "crackerjack-metrics",
        "Get quality metrics trends from Crackerjack execution history.",
        content_key="crackerjack-metrics",
    ),
    PromptDefinition(
        "crackerjack-patterns",
        "Analyze test failure patterns and trends for debugging insights.",
        content_key="crackerjack-patterns",
    ),
)

# Memory management prompts
MEMORY_PROMPTS: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        "compress-memory",
        "Compress conversation memory by consolidating old conversations into summaries.",
        content="""# Memory Compression

Compress conversation memory by consolidating old conversations into summaries.

This command will:
- Analyze conversation age and importance
- Group related conversations into clusters
- Create consolidated summaries of old conversations
- Remove redundant conversation data
- Calculate space savings and compression ratios

Examples:
- Default compression: compress_memory()
- Preview changes: dry_run=True
- Aggressive compression: max_age_days=14, importance_threshold=0.5

Use this periodically to keep your conversation memory manageable and efficient.""",
    ),
    PromptDefinition(
        "compression-stats",
        "Get detailed statistics about memory compression history and current database status.",
        content="""# Compression Statistics

Get detailed statistics about memory compression history and current database status.

This command will:
- Show last compression run details
- Display space savings and compression ratios
- Report current database size and conversation count
- Show number of consolidated conversations
- Provide compression efficiency metrics

Use this to monitor memory usage and compression effectiveness.""",
    ),
    PromptDefinition(
        "retention-policy",
        "Configure memory retention policy parameters for automatic compression.",
        content="""# Retention Policy

Configure memory retention policy parameters for automatic compression.

This command will:
- Set maximum conversation age and count limits
- Configure importance threshold for retention
- Define consolidation age triggers
- Adjust compression ratio targets

Examples:
- Conservative: max_age_days=365, importance_threshold=0.2
- Aggressive: max_age_days=90, importance_threshold=0.5
- Custom: consolidation_age_days=14

Use this to customize how your conversation memory is managed over time.""",
    ),
)

# Context and search prompts
CONTEXT_PROMPTS: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        "auto-load-context",
        "Automatically detect current development context and load relevant conversations.",
        content="""# Auto-Context Loading

Automatically detect current development context and load relevant conversations.

This command will:
- Analyze your current project structure and files
- Detect programming languages and tools in use
- Identify project type (web app, CLI tool, library, etc.)
- Find recent file modifications
- Load conversations relevant to your current context
- Score conversations by relevance to current work

Examples:
- Load default context: auto_load_context()
- Increase results: max_conversations=20
- Lower threshold: min_relevance=0.2

Use this at the start of coding sessions to get relevant context automatically.""",
    ),
    PromptDefinition(
        "context-summary",
        "Get a quick summary of your current development context without loading conversations.",
        content="""# Context Summary

Get a quick summary of your current development context without loading conversations.

This command will:
- Detect current project name and type
- Identify programming languages and tools
- Show Git repository information
- Display recently modified files
- Calculate detection confidence score

Use this to understand what context the system has detected about your current work.""",
    ),
    PromptDefinition(
        "search-code",
        "Search for code patterns in conversations using AST parsing.",
        content="""# Code Pattern Search

Search for code patterns in your conversation history using AST (Abstract Syntax Tree) parsing.

This command will:
- Parse Python code blocks from conversations
- Extract functions, classes, imports, loops, and other patterns
- Rank results by relevance to your query
- Show code context and project information

Examples:
- Search for functions: pattern_type='function'
- Search for class definitions: pattern_type='class'
- Search for error handling: query='try except'

Use this to find code examples and patterns from your development sessions.""",
    ),
    PromptDefinition(
        "search-errors",
        "Search for error patterns and debugging contexts in conversations.",
        content="""# Error Pattern Search

Search for error messages, exceptions, and debugging contexts in your conversation history.

This command will:
- Find Python tracebacks and exceptions
- Detect JavaScript errors and warnings
- Identify debugging and testing contexts
- Show error context and solutions

Examples:
- Find Python errors: error_type='python_exception'
- Find import issues: query='ImportError'
- Find debugging sessions: query='debug'

Use this to quickly find solutions to similar errors you've encountered before.""",
    ),
    PromptDefinition(
        "search-temporal",
        "Search conversations within a specific time range using natural language.",
        content="""# Temporal Search

Search your conversation history using natural language time expressions.

This command will:
- Parse time expressions like "yesterday", "last week", "2 days ago"
- Find conversations within that time range
- Optionally filter by additional search terms
- Sort results by time and relevance

Examples:
- "yesterday" - conversations from yesterday
- "last week" - conversations from the past week
- "2 days ago" - conversations from 2 days ago
- "this month" + query - filter by content within the month

Use this to find recent discussions or work from specific time periods.""",
    ),
)

# Monitoring prompts
MONITORING_PROMPTS: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        "start-app-monitoring",
        "Start monitoring IDE activity and browser documentation usage.",
        content="""# Start Application Monitoring

Monitor your development activity to provide better context and insights.

This command will:
- Start file system monitoring for code changes
- Track application focus (IDE, browser, terminal)
- Monitor documentation site visits
- Build activity profiles for better context

Monitoring includes:
- File modifications in your project directories
- IDE and editor activity patterns
- Browser navigation to documentation sites
- Application focus and context switching

Use this to automatically capture your development context for better session insights.""",
    ),
    PromptDefinition(
        "stop-app-monitoring",
        "Stop all application monitoring.",
        content="""# Stop Application Monitoring

Stop monitoring your development activity.

This command will:
- Stop file system monitoring
- Stop application focus tracking
- Preserve collected activity data
- Clean up monitoring resources

Use this when you want to pause monitoring or when you're done with a development session.""",
    ),
    PromptDefinition(
        "activity-summary",
        "Get activity summary for recent development work.",
        content="""# Activity Summary

Get a comprehensive summary of your recent development activity.

This command will:
- Show file modification patterns
- List most active applications
- Display visited documentation sites
- Calculate productivity metrics

Summary includes:
- Event counts by type and application
- Most actively edited files
- Documentation resources consulted
- Average relevance scores

Use this to understand your development patterns and identify productive sessions.""",
    ),
    PromptDefinition(
        "context-insights",
        "Get contextual insights from recent activity.",
        content="""# Context Insights

Analyze recent development activity for contextual insights.

This command will:
- Identify primary focus areas
- Detect technologies being used
- Count context switches
- Calculate productivity scores

Insights include:
- Primary application focus
- Active programming languages
- Documentation topics explored
- Project switching patterns
- Overall productivity assessment

Use this to understand your current development context and optimize your workflow.""",
    ),
    PromptDefinition(
        "active-files",
        "Get files currently being worked on.",
        content="""# Active Files

Show files that are currently being actively worked on.

This command will:
- List recently modified files
- Show activity scores and patterns
- Highlight most frequently changed files
- Include project context

File activity is scored based on:
- Frequency of modifications
- Recency of changes
- File type and relevance
- Project context

Use this to quickly see what you're currently working on and resume interrupted tasks.""",
    ),
    PromptDefinition(
        "quality-monitor",
        "Proactive session quality monitoring with trend analysis and early warnings.",
        content="""# Quality Monitor

Phase 3: Proactive quality monitoring with early warning system.

This command will:
- Monitor code quality trends in real-time
- Detect quality degradation early
- Provide alerts for potential issues
- Generate improvement recommendations
- Track quality metrics over time

Use this for continuous quality assurance during development.""",
    ),
    PromptDefinition(
        "auto-compact",
        "Automatically trigger conversation compaction with context preservation.",
        content="""# Auto Compact

Automatically trigger conversation compaction with intelligent summary.

This command will:
- Analyze conversation length and complexity
- Identify consolidation opportunities
- Preserve important context and decisions
- Compress redundant information
- Maintain searchable history

Use this to manage conversation memory efficiently.""",
    ),
)

# All prompts grouped for efficient processing
ALL_PROMPT_GROUPS: tuple[Any, ...] = (  # type: ignore[assignment]
    CORE_PROMPTS,
    REFLECTION_PROMPTS,
    CRACKERJACK_PROMPTS,
    MEMORY_PROMPTS,
    CONTEXT_PROMPTS,
    MONITORING_PROMPTS,
)


def _create_prompt_handler(
    definition: PromptDefinition,
) -> Callable[[], Coroutine[Any, Any, str]]:
    """Create async prompt handler function for a definition."""

    async def handler() -> str:
        return definition.get_content()

    handler.__name__ = f"get_{definition.name.replace('-', '_')}_prompt"
    handler.__doc__ = definition.description
    return handler


def register_prompt_tools(mcp: Any) -> None:
    """Register all MCP prompt definitions using data-driven approach.

    Args:
        mcp: FastMCP server instance

    """
    # Register prompts in groups for better organization
    for prompt_group in ALL_PROMPT_GROUPS:
        _register_prompt_group(mcp, prompt_group)


def _register_prompt_group(mcp: Any, prompts: tuple[PromptDefinition, ...]) -> None:
    """Register a group of prompts with MCP server."""
    for definition in prompts:
        handler = _create_prompt_handler(definition)
        mcp.prompt(definition.name)(handler)
