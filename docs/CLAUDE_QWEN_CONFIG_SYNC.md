# Claude/Qwen Config Sync

**Status**: ✅ Available
**Migrated**: 2026-02-06 from Mahavishnu
**Feature**: Bidirectional configuration synchronization between Claude Code and Qwen Code

______________________________________________________________________

## Overview

Session-Buddy provides **Claude/Qwen configuration synchronization** via MCP, enabling you to keep your Claude Code and Qwen Code configurations in sync automatically.

**What gets synced**:

- ✅ **MCP servers** - JSON dict merge with conflict resolution
- ✅ **Commands** - File-based sync with format conversion (Claude .md → Qwen .md with YAML frontmatter)
- ✅ **Extensions/Plugins** - Tracking only (manual installation required)

**Key Features**:

- Bidirectional sync (Claude ↔ Qwen)
- Skip specific MCP servers (default: homebrew, pycharm)
- Atomic file writes (prevents corruption)
- Error handling with detailed reporting
- Async/await support

______________________________________________________________________

## Quick Start

### Prerequisites

1. **Session-Buddy MCP server running**

   ```bash
   python -m session_buddy.mcp.server
   ```

1. **MCP client configured** - Connect to Session-Buddy MCP server

### Basic Usage

```python
from mcp_client import call_tool

# Sync Claude → Qwen (all types)
result = await call_tool("sync_claude_qwen_config", {
    "source": "claude",
    "destination": "qwen"
})

# Sync specific types only
result = await call_tool("sync_claude_qwen_config", {
    "source": "claude",
    "destination": "qwen",
    "sync_types": ["mcp", "commands"]
})

# Sync with custom skip list
result = await call_tool("sync_claude_qwen_config", {
    "source": "claude",
    "destination": "qwen",
    "skip_servers": ["homebrew", "pycharm", "custom-server"]
})

# Reverse sync (Qwen → Claude)
result = await call_tool("sync_claude_qwen_config", {
    "source": "qwen",
    "destination": "claude"
})
```

______________________________________________________________________

## MCP Tool Specification

### Tool: `sync_claude_qwen_config`

**Description**: Sync Claude and Qwen provider configurations with bidirectional support.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | string | No | "claude" | Source config ("claude" or "qwen") |
| `destination` | string | No | "qwen" | Destination config ("claude" or "qwen") |
| `sync_types` | list[string] | No | ["mcp", "extensions", "commands"] | Types to sync |
| `skip_servers` | list[string] | No | ["homebrew", "pycharm"] | MCP servers to skip |

**Sync Types**:

- `"mcp"` - MCP servers (JSON dict merge)
- `"commands"` - File-based commands (converts formats)
- `"extensions"` - Plugins/extensions (tracking only)
- `"all"` - Sync all types

**Returns**:

```json
{
  "mcp_servers": 10,
  "mcp_servers_skipped": 2,
  "commands_synced": 5,
  "plugins_found": 3,
  "errors": []
}
```

______________________________________________________________________

## What Gets Synced

### MCP Servers

**Location**: `~/.claude.json` ↔ `~/.qwen/settings.json`

**Strategy**: JSON dict merge

- Servers unique to one side → added to other
- Servers on both sides → Source takes precedence (last-write-wins)
- Preserves metadata (type, url, command, args)
- Skips servers in `skip_servers` list

**Example**:

```json
// Claude config
{
  "mcpServers": {
    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]},
    "homebrew": {"command": "/opt/homebrew/bin/mcp-server-homebrew"}
  }
}

// After sync → Qwen config
{
  "mcpServers": {
    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]},
    // homebrew skipped (in skip_servers list)
  }
}
```

### Commands

**Location**: `~/.claude/commands/**/*.md` ↔ `~/.qwen/commands/**/*.md`

**Strategy**: File sync with format conversion

- Claude: Plain markdown with `## description:` headers
- Qwen: YAML frontmatter format

**Claude Format**:

```markdown
## description: Generate TypeScript types

Generate TypeScript types from JSON schema...

import { generate } from 'ts-schema-gen'
...
```

**Qwen Format (after sync)**:

```markdown
---
description: Generate TypeScript types
---

# Command synced from Claude Code
# Original location: ~/.claude/commands/generate-types.md

Generate TypeScript types from JSON schema...

import { generate } from 'ts-schema-gen'
...
```

### Extensions/Plugins

**Location**: `~/.claude/settings.json` → Tracking only

**Strategy**: Plugin discovery only

- Finds enabled Claude plugins
- Lists plugin names
- **Manual installation required** via `qwen extensions install`

**Note**: Qwen extensions must be installed manually:

```bash
qwen extensions install <marketplace-url>:<plugin-name>
```

______________________________________________________________________

## Configuration Paths

| Platform | Claude Config | Qwen Config |
|----------|---------------|--------------|
| **macOS/Linux** | `~/.claude.json` | `~/.qwen/settings.json` |
| **Claude Settings** | `~/.claude/settings.json` | - |
| **Claude Commands** | `~/.claude/commands/**/*.md` | - |
| **Qwen Commands** | - | `~/.qwen/commands/**/*.md` |
| **Claude Plugins** | `~/.claude/plugins/installed_plugins.json` | - |

______________________________________________________________________

## Scheduling Automated Syncs

### Cron (Linux/macOS)

```cron
# Sync every 6 hours
0 */6 * * * /path/to/sync_configs.py >> /var/log/sync.log 2>&1
```

### Python Script

```python
#!/usr/bin/env python3
"""Sync Claude and Qwen configs."""
import asyncio
from mcp_client import MCPClient

async def main():
    client = MCPClient("session-buddy")

    # Sync Claude → Qwen
    result = await client.call_tool("sync_claude_qwen_config", {
        "source": "claude",
        "destination": "qwen",
        "sync_types": ["all"]
    })

    print(result)
    # Output: Synced 10 MCP servers, 5 commands

asyncio.run(main())
```

### systemd Timer (Linux)

```ini
# /etc/systemd/system/sync-claude-qwen.service
[Unit]
Description=Sync Claude and Qwen configs
After=network.target

[Service]
Type=oneshot
ExecStart=/path/to/sync_configs.py
User=your-user

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/sync-claude-qwen.timer
[Unit]
Description=Sync Claude and Qwen configs every 6 hours

[Timer]
OnCalendar=*:0/6
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# Enable and start
systemctl enable sync-claude-qwen.timer
systemctl start sync-claude-qwen.timer
```

______________________________________________________________________

## Error Handling

### Common Errors

**1. Config file not found**

```
Error: Failed to load ~/.claude.json
```

**Solution**: Run Claude Code once to generate the config file

**2. Permission denied**

```
Error: Permission denied when writing ~/.qwen/settings.json
```

**Solution**: Check file permissions or run with appropriate user

**3. Invalid JSON**

```
Error: Failed to load ~/.qwen/settings.json: JSON decode error
```

**Solution**: Manually fix JSON syntax or delete file to regenerate

### Error Output Format

```json
{
  "mcp_servers": 0,
  "mcp_servers_skipped": 2,
  "commands_synced": 0,
  "plugins_found": 0,
  "errors": [
    "Failed to load ~/.claude.json: Permission denied",
    "Failed to convert /path/to/command.md: Invalid encoding"
  ]
}
```

______________________________________________________________________

## Implementation Details

### Location in Code

**Sync Method**: `session_buddy/llm_providers.py:LLMManager.sync_provider_configs()`

**MCP Tool**: `session_buddy/mcp/tools/intelligence/llm_tools.py:sync_claude_qwen_config()`

### Algorithm

1. **Load configs** from both source and destination
1. **Merge MCP servers** using dict merge with skip list
1. **Convert commands** from Claude format → Qwen format (if source=claude)
1. **Track plugins** for manual installation
1. **Write atomically** to prevent corruption (temp file + rename)
1. **Return stats** with errors if any

### Thread Safety

- All file operations are atomic (temp file + rename)
- No locking required (single-writer model)
- Safe for concurrent reads

______________________________________________________________________

## Migration from Mahavishnu

**Previously**: Mahavishu had `mahavishnu sync` CLI command

**Now**: Use Session-Buddy MCP tool

**Migration**: See [CONFIG_SYNC_MIGRATION_GUIDE.md](https://github.com/your-repo/mahavishnu/docs/CONFIG_SYNC_MIGRATION_GUIDE.md) in Mahavishnu docs

______________________________________________________________________

## Troubleshooting

### All Servers Skipped

**Issue**: `mcp_servers_skipped` equals total servers

**Solution**: Check your `skip_servers` parameter:

```python
# Wrong - skips everything
result = await call_tool("sync_claude_qwen_config", {
    "skip_servers": ["*"]  # ❌ Don't use wildcards
})

# Correct - skip only specific servers
result = await call_tool("sync_claude_qwen_config", {
    "skip_servers": ["homebrew", "pycharm"]  # ✅ Specific servers
})

# Or skip nothing
result = await call_tool("sync_claude_qwen_config", {
    "skip_servers": []  # ✅ Empty list = sync all
})
```

### Commands Not Syncing

**Issue**: `commands_synced` is 0

**Checks**:

1. Verify command files exist: `ls ~/.claude/commands/`
1. Check destination directory exists: `ls ~/.qwen/commands/`
1. Look for errors in result["errors"]

### Extensions Not Installing

**Issue**: Plugins found but not in Qwen

**Expected behavior**: Extensions are **tracking only**. You must install manually:

```bash
# 1. Check which plugins were found
result = await call_tool("sync_claude_qwen_config", {
    "source": "claude",
    "destination": "qwen"
})
print(result["plugins_found"])

# 2. Install each plugin in Qwen
qwen extensions install <marketplace-url>:<plugin-name>
```

______________________________________________________________________

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Load configs | \<10ms | JSON parsing |
| Merge MCP servers | \<5ms | Dict merge |
| Convert commands | 50-200ms | Depends on file count |
| Write atomically | \<10ms | File I/O |
| **Total** | **\<250ms** | Typical sync |

______________________________________________________________________

## Security

**File Permissions**:

- Config files: `0600` (read/write for owner only)
- Temp files: Created in same directory with `.tmp` suffix
- Atomic rename: Preserves permissions

**API Keys**: Sync does NOT sync API keys (security measure)

______________________________________________________________________

## See Also

- **Migration Guide**: [Mahavishnu CONFIG_SYNC_MIGRATION_GUIDE.md](https://github.com/your-repo/mahavishnu/docs/CONFIG_SYNC_MIGRATION_GUIDE.md)
- **Migration Plan**: [Mahavishnu CONFIG_SYNC_MIGRATION_PLAN.md](https://github.com/your-repo/mahavishnu/docs/CONFIG_SYNC_MIGRATION_PLAN.md)
- **LLM Providers**: [Session-Buddy API Reference](./reference/API_REFERENCE.md)

______________________________________________________________________

**Last Updated**: 2026-02-06
**Status**: ✅ Production Ready
**Maintainer**: Session-Buddy Team
