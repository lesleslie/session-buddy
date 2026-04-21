import json
from functools import partial
from pathlib import Path
from typing import Any


def _load_json_safely_impl(path: Path, *, self=None) -> dict[str, Any]:
    """Load JSON file safely, returning empty dict if not exists."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        self.logger.error(f"Failed to load {path}: {e}")
    return {}


def _save_json_atomically_impl(path: Path, data: dict[str, Any], *, self=None) -> None:
    """Save JSON file atomically to prevent corruption."""
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2))
    temp_path.replace(path)
    self.logger.debug(f"Saved {path} atomically")


def _merge_mcp_servers_impl(
    claude: dict[str, Any],
    qwen: dict[str, Any],
    skip_servers_list: list[str] | None = None,
    *,
    self=None,
    skip_servers=None,
    source=None,
    destination=None,
) -> dict[str, Any]:
    """Merge MCP servers from both configs.

    Strategy:
    - Servers unique to one side: add to other
    - Servers on both sides: Source takes precedence (last-write-wins)
    - Preserve server metadata (type, url, command, args)
    - Skip servers in skip_servers list
    """
    if skip_servers_list is None:
        skip_servers_list = skip_servers
    claude_mcp = claude.get("mcpServers", {})
    qwen_mcp = qwen.get("mcpServers", {})
    if source == "claude":
        filtered_source_mcp = {
            name: config
            for name, config in claude_mcp.items()
            if name not in skip_servers_list
        }
        merged = {**qwen_mcp}
        merged.update(filtered_source_mcp)
    else:
        filtered_source_mcp = {
            name: config
            for name, config in qwen_mcp.items()
            if name not in skip_servers_list
        }
        merged = {**claude_mcp}
        merged.update(filtered_source_mcp)
    skipped_count = len(claude_mcp if source == "claude" else qwen_mcp) - len(
        filtered_source_mcp
    )
    self.logger.debug(
        "Merged "
        f"{len(filtered_source_mcp)}"
        " "
        f"{source}"
        " + "
        f"{len(qwen_mcp if source == 'claude' else claude_mcp)}"
        " "
        f"{destination}"
        " MCP servers (skipped "
        f"{skipped_count}"
        ")"
    )
    return merged


def _markdown_to_qwen_markdown_impl(md_content: str, command_name: str) -> str:
    """Convert Claude command markdown to Qwen markdown format."""
    import re

    lines = md_content.strip().split("\n")
    description = command_name
    prompt_start = 0
    for i, line in enumerate(lines):
        if "description:" in line.lower():
            match = re.search("description:\\s*(.+?)(?:\\s+id:)?$", line, re.IGNORECASE)
            if match:
                description = match.group(1).strip()
                prompt_start = i + 1
                break
        elif line.strip().startswith("#"):
            description = line.strip("#").strip()
            prompt_start = i + 1
            break
    prompt_lines = [line for line in lines[prompt_start:]]
    prompt_content = "\n".join(prompt_lines).strip()
    qwen_md = (
        "---\n"
        "description: "
        f"{description}"
        "\n"
        "---\n"
        "\n"
        "# Command synced from Claude Code\n"
        "# Original location: ~/.claude/commands/"
        f"{command_name}"
        ".md\n"
        "\n"
        f"{prompt_content}"
        "\n"
    )
    return qwen_md


def _sync_commands_source_to_dest_impl(
    *,
    self=None,
    source=None,
    CLAUDE_COMMANDS_DIR=None,
    markdown_to_qwen_markdown=None,
    QWEN_COMMANDS_DIR=None,
    destination=None,
) -> dict[str, Any]:
    """Sync commands from source to destination."""
    stats = {"commands_synced": 0, "commands_skipped": 0, "errors": []}
    try:
        if source == "claude":
            src_dir = CLAUDE_COMMANDS_DIR
            dst_dir = QWEN_COMMANDS_DIR
        else:
            src_dir = QWEN_COMMANDS_DIR
            dst_dir = CLAUDE_COMMANDS_DIR
        dst_dir.mkdir(parents=True, exist_ok=True)
        md_files = list(src_dir.glob("**/*.md"))
        self.logger.debug(f"Found {len(md_files)} command files in {source}")
        for md_file in md_files:
            try:
                rel_path = md_file.relative_to(src_dir)
                md_name = rel_path.with_suffix(".md")
                dst_md_file = dst_dir / md_name
                dst_md_file.parent.mkdir(parents=True, exist_ok=True)
                if source == "claude":
                    src_md = md_file.read_text()
                    dst_md = _markdown_to_qwen_markdown_impl(src_md, md_file.stem)
                else:
                    dst_md = md_file.read_text()
                dst_md_file.write_text(dst_md)
                stats["commands_synced"] += 1
                self.logger.debug(f"Converted: {rel_path} → {md_name}")
            except Exception as e:
                error_msg = f"Failed to convert {md_file}: {e}"
                self.logger.warning(error_msg)
                stats["errors"].append(error_msg)
                stats["commands_skipped"] += 1
        self.logger.info(
            f"✅ Synced {stats['commands_synced']} commands to {destination}"
        )
    except Exception as e:
        error_msg = f"Failed to sync commands: {e}"
        self.logger.error(error_msg)
        stats["errors"].append(error_msg)
    return stats


async def _helper_functions(
    self,
    source: str = "claude",
    destination: str = "qwen",
    sync_types: list[str] | None = None,
    skip_servers: list[str] | None = None,
) -> dict[str, Any]:
    """Sync provider configurations between Claude and Qwen.

    Provides bidirectional synchronization between Claude Code and Qwen Code:
    - MCP servers (JSON dict merge)
    - Extensions/plugins (JSON dict merge)
    - File-based resources (agents, commands, skills)

    Args:
        source: Source config ("claude" or "qwen")
        destination: Destination config ("claude" or "qwen")
        sync_types: Types to sync (mcp, commands, extensions, all)
        skip_servers: MCP servers to skip during sync

    Returns:
        Sync result with stats and any errors

    Example:
        >>> manager = LLMManager()
        >>> result = await manager.sync_provider_configs(
        ...     source="claude",
        ...     destination="qwen",
        ...     sync_types=["mcp", "commands"],
        ...     skip_servers=["homebrew", "pycharm"]
        ... )
    """
    from pathlib import Path

    # Configuration paths
    CLAUDE_CONFIG = Path.home() / ".claude.json"
    QWEN_CONFIG = Path.home() / ".qwen" / "settings.json"
    CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
    CLAUDE_COMMANDS_DIR = Path.home() / ".claude" / "commands"
    QWEN_COMMANDS_DIR = Path.home() / ".qwen" / "commands"
    CLAUDE_PLUGINS_FILE = Path.home() / ".claude" / "plugins" / "installed_plugins.json"

    # Default skip servers
    DEFAULT_SKIP_SERVERS = ["homebrew", "pycharm"]

    if skip_servers is None:
        skip_servers = DEFAULT_SKIP_SERVERS

    # Helper functions
    load_json_safely = partial(_load_json_safely_impl, self=self)

    save_json_atomically = partial(_save_json_atomically_impl, self=self)

    merge_mcp_servers = partial(
        _merge_mcp_servers_impl,
        self=self,
        skip_servers=skip_servers,
        source=source,
        destination=destination,
    )

    markdown_to_qwen_markdown = _markdown_to_qwen_markdown_impl

    sync_commands_source_to_dest = partial(
        _sync_commands_source_to_dest_impl,
        self=self,
        source=source,
        CLAUDE_COMMANDS_DIR=CLAUDE_COMMANDS_DIR,
        markdown_to_qwen_markdown=markdown_to_qwen_markdown,
        QWEN_COMMANDS_DIR=QWEN_COMMANDS_DIR,
        destination=destination,
    )

    # Main sync logic
    self.logger.info(f"Syncing {source} → {destination}")

    # Load configs
    if source == "claude":
        src_config = load_json_safely(CLAUDE_CONFIG)
        dst_config = load_json_safely(QWEN_CONFIG)
        dst_config_path = QWEN_CONFIG
    else:
        src_config = load_json_safely(QWEN_CONFIG)
        dst_config = load_json_safely(CLAUDE_CONFIG)
        dst_config_path = CLAUDE_CONFIG

    stats = {
        "mcp_servers": 0,
        "mcp_servers_skipped": 0,
        "plugins_found": 0,
        "commands_synced": 0,
        "errors": [],
    }

    # Default sync types if not specified
    if sync_types is None:
        sync_types = ["mcp", "extensions", "commands"]

    # Sync MCP servers
    if "mcp" in sync_types or "all" in sync_types:
        try:
            if "mcpServers" in src_config:
                src_mcp_count = len(src_config["mcpServers"])
                dst_config["mcpServers"] = merge_mcp_servers(
                    src_config, dst_config, skip_servers
                )
                stats["mcp_servers"] = src_mcp_count
                stats["mcp_servers_skipped"] = len(
                    [s for s in src_config["mcpServers"] if s in skip_servers]
                )
                save_json_atomically(dst_config_path, dst_config)
                self.logger.info(
                    f"✅ Synced {stats['mcp_servers']} MCP servers to {destination} "
                    "(skipped "
                    f"{stats['mcp_servers_skipped']}"
                    ": "
                    f"{', '.join(skip_servers)}"
                    ")"
                )
        except Exception as e:
            error_msg = f"Failed to sync MCP servers: {e}"
            self.logger.error(error_msg)
            stats["errors"].append(error_msg)

    # Sync extensions (tracking only - manual install required)
    if "extensions" in sync_types or "all" in sync_types:
        try:
            if source == "claude":
                claude_settings = load_json_safely(CLAUDE_SETTINGS)
                load_json_safely(CLAUDE_PLUGINS_FILE)

                enabled_plugins = claude_settings.get("enabledPlugins", {})
                stats["plugins_found"] = len(enabled_plugins)

                plugin_names = []
                for plugin_id in enabled_plugins.keys():
                    name = plugin_id.split("@")[0]
                    plugin_names.append(name)

                self.logger.info(
                    f"Found {len(plugin_names)} Claude plugins to potentially sync"
                )
                # Note: Actual extension installation requires manual action
        except Exception as e:
            error_msg = f"Failed to sync extensions: {e}"
            self.logger.error(error_msg)
            stats["errors"].append(error_msg)

    # Sync commands
    if "commands" in sync_types or "all" in sync_types:
        cmd_stats = sync_commands_source_to_dest()
        stats["commands_synced"] = cmd_stats["commands_synced"]
        stats["errors"].extend(cmd_stats["errors"])

    return stats
