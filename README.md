# Session Buddy

A Session Management MCP Server for Claude Code

[![Code style: crackerjack](https://img.shields.io/badge/code%20style-crackerjack-000042)](https://github.com/lesleslie/crackerjack)
[![Python: 3.13+](https://img.shields.io/badge/python-3.13%2B-green)](https://www.python.org/downloads/)
![Coverage](https://img.shields.io/badge/coverage-45.6%25-red)
![Static Badge](https://img.shields.io/badge/claude--code-black?style=flat&logo=claude&logoColor=%23D97757&link=https%3A%2F%2Fgithub.com%2Fanthropics%2Fclaude-code)

A dedicated MCP server that provides comprehensive session management functionality for Claude Code sessions across any project.

## Features

- **🚀 Session Initialization**: Complete setup with UV dependency management, project analysis, and automation tools
- **🔍 Quality Checkpoints**: Mid-session quality monitoring with workflow analysis and optimization recommendations
- **🏁 Session Cleanup**: Comprehensive cleanup with learning capture and handoff file creation
- **📊 Status Monitoring**: Real-time session status and project context analysis
- **⚡ Auto-Generated Shortcuts**: Automatically creates `/start`, `/checkpoint`, and `/end` Claude Code slash commands

## 🚀 Automatic Session Management (NEW!)

**For Git Repositories:**

- ✅ **Automatic initialization** when Claude Code connects
- ✅ **Automatic cleanup** when session ends (quit, crash, or network failure)
- ✅ **Intelligent auto-compaction** during checkpoints
- ✅ **Zero manual intervention** required

**For Non-Git Projects:**

- 📝 Use `/start` for manual initialization
- 📝 Use `/end` for manual cleanup
- 📝 Full session management features available on-demand

The server automatically detects git repositories and provides seamless session lifecycle management with crash resilience and network failure recovery. Non-git projects retain manual control for flexible workflow management.

## Available MCP Tools

This server provides **79+ specialized tools** organized into 11 functional categories.
For a complete list of tools, see the [MCP Tools Reference](docs/user/MCP_TOOLS_REFERENCE.md).

**Core Session Management:**

- `start` - Comprehensive session initialization with project analysis and memory setup
- `checkpoint` - Mid-session quality assessment with workflow analysis
- `end` - Complete session cleanup with learning capture
- `status` - Current session overview with health checks
- `permissions` - Manage trusted operations to reduce permission prompts

**Memory & Conversation Search:**

- `reflect_on_past` - Semantic search through past conversations using local AI embeddings
- `store_reflection` - Store insights with tagging and embeddings
- `quick_search` - Fast overview search with count and top results
- `get_more_results` - Pagination support for large result sets

**Knowledge Graph (DuckPGQ):**

- Entity and relationship management for project knowledge
- SQL/PGQ graph queries for complex relationship analysis
- See [Knowledge Graph Integration Guide](docs/archive/integration-docs/KNOWLEDGE_GRAPH_INTEGRATION.md)

All tools use **local processing** for privacy, with **DuckDB vector storage** (FLOAT[384] embeddings) and **ONNX-based semantic search** requiring no external API calls.

## 🚀 Integration with Crackerjack

Session-mgmt includes deep integration with [Crackerjack](https://github.com/lesleslie/crackerjack), the AI-driven Python development platform:

**Key Features:**

- **📊 Quality Metrics Tracking**: Automatically captures and tracks quality scores over time
- **🧪 Test Result Monitoring**: Learns from test patterns, failures, and successful fixes
- **🔍 Error Pattern Recognition**: Remembers how specific errors were resolved and suggests solutions

**Example Workflow:**

1. 🚀 **Session-mgmt `start`** - Sets up your session with accumulated context from previous work
1. 🔧 **Crackerjack runs** quality checks and applies AI agent fixes to resolve issues
1. 💾 **Session-mgmt captures** successful patterns and error resolutions
1. 🧠 **Next session starts** with all accumulated knowledge

For detailed information on Crackerjack integration, see [Crackerjack Integration Guide](docs/CRACKERJACK.md).

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/lesleslie/session-buddy.git
cd session-buddy

# Install with all dependencies (development + testing)
uv sync --group dev

# Or install minimal production dependencies only
uv sync

# Or use pip (for production only)
pip install session-buddy
```

### MCP Configuration

Add to your project's `.mcp.json` file:

```json
{
  "mcpServers": {
    "session-mgmt": {
      "command": "python",
      "args": ["-m", "session_buddy.server"],
      "cwd": "/path/to/session-buddy",
      "env": {
        "PYTHONPATH": "/path/to/session-buddy"
      }
    }
  }
}
```

### Alternative: Use Script Entry Point

If installed with pip/uv, you can use the script entry point:

```json
{
  "mcpServers": {
    "session-mgmt": {
      "command": "session-buddy",
      "args": [],
      "env": {}
    }
  }
}
```

**Dependencies:** Requires Python 3.13+. For a complete list of dependencies, see [pyproject.toml](pyproject.toml).
Recent changes include pinning FastAPI to \<0.121.0 to prevent circular import bugs and removing sitecustomize.py for improved startup reliability.

## Usage

Once configured, the following slash commands become available in Claude Code:

**Primary Session Commands:**

- `/session-buddy:start` - Full session initialization
- `/session-buddy:checkpoint` - Quality monitoring checkpoint with scoring
- `/session-buddy:end` - Complete session cleanup with learning capture
- `/session-buddy:status` - Current status overview with health checks

**Auto-Generated Shortcuts:**
After running `/session-buddy:start` once, these shortcuts are automatically created:

- `/start` → `/session-buddy:start`
- `/checkpoint [name]` → `/session-buddy:checkpoint`
- `/end` → `/session-buddy:end`

> These shortcuts are created in `~/.claude/commands/` and work across all projects

**Memory & Search Commands:**

- `/session-buddy:reflect_on_past` - Search past conversations with semantic similarity
- `/session-buddy:store_reflection` - Store important insights with tagging
- `/session-buddy:quick_search` - Fast search with overview results
- `/session-buddy:permissions` - Manage trusted operations

For running the server directly in development mode:

```bash
python -m session_buddy.server
# or
session-buddy
```

## Memory System

**Built-in Conversation Memory:**

- **Local Storage**: DuckDB database at `~/.claude/data/reflection.duckdb`
- **Embeddings**: Local ONNX models for semantic search (no external API needed)
- **Privacy**: Everything runs locally with no external dependencies
- **Cross-Project**: Conversations tagged by project context for organized retrieval

**Search Capabilities:**

- **Semantic Search**: Vector similarity matching with customizable thresholds
- **Time Decay**: Recent conversations prioritized in results
- **Filtering**: Search by project context or across all projects

## Data Storage

This server manages its data locally in the user's home directory:

- **Memory Storage**: `~/.claude/data/reflection.duckdb`
- **Session Logs**: `~/.claude/logs/`
- **Configuration**: Uses pyproject.toml and environment variables

## Recommended Session Workflow

1. **Initialize Session**: `/session-buddy:start` - Sets up project context, dependencies, and memory system
1. **Monitor Progress**: `/session-buddy:checkpoint` (every 30-45 minutes) - Quality scoring and optimization
1. **Search Past Work**: `/session-buddy:reflect_on_past` - Find relevant past conversations and solutions
1. **Store Important Insights**: `/session-buddy:store_reflection` - Capture key learnings for future sessions
1. **End Session**: `/session-buddy:end` - Final assessment, learning capture, and cleanup

## Benefits

### Comprehensive Coverage

- **Session Quality**: Real-time monitoring and optimization
- **Memory Persistence**: Cross-session conversation retention
- **Project Structure**: Context-aware development workflows

### Reduced Friction

- **Single Command Setup**: One `/session-buddy:start` sets up everything
- **Local Dependencies**: No external API calls or services required
- **Intelligent Permissions**: Reduces repeated permission prompts
- **Automated Workflows**: Structured processes for common tasks

### Enhanced Productivity

- **Quality Scoring**: Guides session effectiveness
- **Built-in Memory**: Enables building on past work automatically
- **Project Templates**: Accelerates development setup
- **Knowledge Persistence**: Maintains context across sessions

## Documentation

Complete documentation is available in the [docs/](docs/) directory:

- **[User Documentation](docs/user/)** - Quick start, configuration, and deployment guides
- **[Developer Documentation](docs/developer/)** - Architecture, testing, and integration guides
- **[Feature Guides](docs/features/)** - AI integration, token optimization, and other features
- **[Reference](docs/reference/)** - MCP schemas and command references

## Troubleshooting

**Common Issues:**

- **Memory/embedding issues**: Ensure all dependencies are installed with `uv sync`
- **Path errors**: Verify `cwd` and `PYTHONPATH` are set correctly in `.mcp.json`
- **Permission issues**: Use `/session-buddy:permissions` to trust operations

**Debug Mode:**

```bash
# Run with verbose logging
PYTHONPATH=/path/to/session-buddy python -m session_buddy.server --debug
```

For more detailed troubleshooting guidance, see [Configuration Guide](docs/user/CONFIGURATION.md) or [Quick Start Guide](docs/user/QUICK_START.md).
