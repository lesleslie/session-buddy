# Session Buddy - Qwen Context

## Project Overview

This is a Python-based MCP (Model Context Protocol) server that provides comprehensive session management functionality for Claude Code sessions. It's designed to be integrated into any project's `.mcp.json` file to provide automatic access to session initialization, checkpoints, and cleanup via slash commands.

Key features include:

- Session initialization with UV dependency management
- Mid-session quality checkpoints with workflow analysis
- Session cleanup with learning capture
- Status monitoring with project context analysis
- Built-in conversation memory with semantic search capabilities
- Git worktree management tools
- Permissions management to reduce prompts

## Project Structure

```
session-buddy/
├── session_buddy/           # Main Python package
│   ├── core/                   # Core session management functionality
│   ├── tools/                  # Individual MCP tool implementations
│   ├── utils/                  # Utility functions (git operations, logging)
│   └── server.py               # Main MCP server entry point
├── tests/                      # Test suite
├── docs/                       # Documentation
├── pyproject.toml              # Project configuration and dependencies
├── requirements.txt            # Generated dependencies list
└── README.md                   # Project documentation
```

## Key Technologies

- **Python 3.13+**: Primary programming language
- **FastMCP**: Framework for building MCP servers
- **DuckDB**: Local database for conversation storage
- **ONNX Runtime & Transformers**: For local semantic embeddings (optional)
- **UV**: Package manager for Python dependencies
- **Ruff**: Code linting and formatting

## Building and Running

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/lesleslie/session-buddy.git
   cd session-buddy
   ```

1. Install dependencies using UV (recommended):

   ```bash
   uv sync --group dev
   ```

   Or using pip:

   ```bash
   pip install -e .
   ```

### MCP Configuration

Add to your global `~/.claude/.mcp.json` file (recommended):

```json
{
  "mcpServers": {
    "session-buddy": {
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

Alternative using script entry point (if installed with pip/uv):

```json
{
  "mcpServers": {
    "session-buddy": {
      "command": "session-buddy",
      "args": [],
      "env": {}
    }
  }
}
```

### Running the Server

For development:

```bash
python -m session_buddy.server
# or
session-buddy
```

## Development Conventions

### Code Style

- Follows PEP 8 standards
- Uses Ruff for linting and formatting with line length 88
- Type hints are required for all functions
- Uses strict pyright configuration for type checking

### Testing

- Uses pytest for testing
- Tests are located in the `tests/` directory
- Run tests with: `pytest` or `uv run pytest`

### Dependencies

Dependencies are managed using:

- `pyproject.toml` for project configuration
- `uv.lock` for lock file (UV)
- `requirements.txt` for pip-compatible list

Install optional dependencies for semantic search:

```bash
# Ensure all dependencies are installed (embeddings are included by default)
uv sync
# or
pip install session-buddy
```

## Available MCP Tools

### Session Management

- `init` - Comprehensive session initialization
- `checkpoint` - Mid-session quality assessment
- `end` - Complete session cleanup
- `status` - Current session status

### Memory & Reflection System

- `reflect_on_past` - Search past conversations with semantic similarity
- `store_reflection` - Store important insights
- `search_nodes` - Advanced search capabilities
- `quick_search` - Fast overview search
- `get_more_results` - Pagination support

### Permissions System

- `permissions` - Manage trusted operations

### Git Worktree Management

- `git_worktree_list` - List all git worktrees
- `git_worktree_add` - Create new worktrees
- `git_worktree_remove` - Remove worktrees
- `git_worktree_status` - Comprehensive worktree status
- `git_worktree_prune` - Clean up stale references

## Data Storage

- Memory Storage: `~/.claude/data/reflection.duckdb`
- Session Logs: `~/.claude/logs/`

## Recommended Session Workflow

1. Initialize Session: `/session-buddy:start`
1. Monitor Progress: `/session-buddy:checkpoint` (every 30-45 minutes)
1. Search Past Work: `/session-buddy:reflect_on_past`
1. Store Important Insights: `/session-buddy:store_reflection`
1. End Session: `/session-buddy:end`

## Testing and Quality Assurance

The project uses several tools for quality assurance:

- Pytest for unit and integration tests
- Ruff for linting and formatting
- Pyright for type checking
- Hypothesis for property-based testing

Run the full test suite:

```bash
uv run pytest
```

Run tests with coverage:

```bash
uv run pytest --cov=session_buddy
```

## Troubleshooting

Common issues:

- Memory not working: Ensure all dependencies are installed with `uv sync` or `pip install session-buddy`
- Path errors: Ensure `cwd` and `PYTHONPATH` are set correctly in `.mcp.json`
- Permission issues: Use `/session-buddy:permissions` to trust operations

Debug mode:

```bash
PYTHONPATH=/path/to/session-buddy python -m session_buddy.server --debug
```
