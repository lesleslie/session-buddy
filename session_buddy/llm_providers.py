import json
import logging
import os
import time
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from mcp_common.llm import FallbackChain, LLMSettings

from session_buddy.llm.models import LLMMessage, LLMResponse
from session_buddy.settings import get_settings

try:
    from mcp_common.security import APIKeyValidator

    SECURITY_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    APIKeyValidator = None  # type: ignore[assignment]
    SECURITY_AVAILABLE = False


__all__ = [
    "APIKeyValidator",
    "LLMManager",
    "LLMMessage",
    "LLMResponse",
    "SECURITY_AVAILABLE",
    "get_masked_api_key",
    "validate_llm_api_keys_at_startup",
    "_get_configured_providers",
    "_get_provider_api_key_and_env",
    "_validate_provider_basic",
    "_validate_provider_with_security",
]


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


def get_masked_api_key(provider: str = "openai") -> str:
    """Return a masked API key suitable for logging."""
    settings = get_settings()
    key_field_map = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
        "qwen": "qwen_api_key",
        "minimax": "minimax_api_key",
        "zai": "zai_api_key",
    }
    key_field = key_field_map.get(provider)
    if key_field:
        configured = getattr(settings, key_field, None)
        if isinstance(configured, str) and configured.strip():
            if SECURITY_AVAILABLE and APIKeyValidator is not None:
                return APIKeyValidator.mask_key(configured, visible_chars=4)
            if len(configured) <= 4:
                return "***"
            return f"...{configured[-4:]}"

    api_key = None
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    elif provider == "qwen":
        api_key = os.getenv("QWEN_API_KEY")
    elif provider == "minimax":
        api_key = os.getenv("MINIMAX_API_KEY")
    elif provider == "zai":
        api_key = os.getenv("ZAI_API_KEY")
    elif provider == "ollama":
        return "N/A (local service)"

    if not api_key:
        return "***"

    if SECURITY_AVAILABLE and APIKeyValidator is not None:
        return APIKeyValidator.mask_key(api_key, visible_chars=4)

    if len(api_key) <= 4:
        return "***"
    return f"...{api_key[-4:]}"


def _get_provider_api_key_and_env(provider: str) -> tuple[str | None, str | None]:
    """Return configured API key and the backing source name."""
    settings = get_settings()
    field_map = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
        "qwen": "qwen_api_key",
        "minimax": "minimax_api_key",
        "zai": "zai_api_key",
    }
    field = field_map.get(provider)
    if field is not None:
        configured = getattr(settings, field, None)
        if isinstance(configured, str) and configured.strip():
            return configured, f"settings.{field}"

    if provider == "openai":
        return os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY"
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY"
    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        env_var_name = (
            "GEMINI_API_KEY" if os.getenv("GEMINI_API_KEY") else "GOOGLE_API_KEY"
        )
        return api_key, env_var_name
    if provider == "qwen":
        return os.getenv("QWEN_API_KEY"), "QWEN_API_KEY"
    if provider == "minimax":
        return os.getenv("MINIMAX_API_KEY"), "MINIMAX_API_KEY"
    if provider == "zai":
        return os.getenv("ZAI_API_KEY"), "ZAI_API_KEY"
    return None, None


def _get_configured_providers() -> list[str]:
    """Return all configured providers from settings and environment."""
    providers: set[str] = set()
    for provider in ("minimax", "zai", "openai", "gemini", "anthropic", "qwen"):
        api_key, _ = _get_provider_api_key_and_env(provider)
        if api_key:
            providers.add(provider)
    return sorted(providers)


def _validate_provider_basic(provider: str, api_key: str) -> str:
    """Fallback validation used when the security module is unavailable."""
    import sys

    _ = provider
    if len(api_key) < 16:
        sys.stderr.write(
            f"API Key Warning: {provider} API key appears very short\n",
        )
    return "basic_check"


def _validate_provider_with_security(provider: str, api_key: str) -> tuple[bool, str]:
    """Validate an API key with the optional security module."""
    import sys

    if APIKeyValidator is None:
        return False, "security unavailable"

    validator = APIKeyValidator(provider=provider)
    try:
        validator.validate(api_key, raise_on_invalid=True)
        sys.stderr.write(f"✅ API Key validated for {provider}\n")
        get_masked_api_key(provider)
        return True, "valid"
    except ValueError:
        sys.exit(1)


def validate_llm_api_keys_at_startup() -> dict[str, str]:
    """Validate configured provider API keys at startup."""
    import sys

    validated_providers: dict[str, str] = {}
    providers_configured = _get_configured_providers()

    if not providers_configured:
        sys.stderr.write("No LLM Provider API Keys Configured\n")
        return validated_providers

    for provider in providers_configured:
        api_key, _env_var_name = _get_provider_api_key_and_env(provider)
        if not api_key or not api_key.strip():
            sys.exit(1)

        if SECURITY_AVAILABLE and APIKeyValidator is not None:
            _, status = _validate_provider_with_security(provider, api_key)
            validated_providers[provider] = status
        else:
            validated_providers[provider] = _validate_provider_basic(provider, api_key)

    return validated_providers


class LLMManager:
    """Thin wrapper around mcp_common FallbackChain for session-buddy LLM calls."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.config_path = Path(config_path) if config_path else None
        self._chain = self._build_chain()

    def _build_chain(self) -> FallbackChain:
        llama_url = os.environ.get("LLAMA_SERVER_URL", "http://localhost:8081")
        settings = LLMSettings(
            providers={
                "minimax": {
                    "name": "minimax",
                    "base_url": os.environ.get(
                        "MINIMAX_BASE_URL", "https://api.minimax.io/v1"
                    ),
                    "api_key_env": "MINIMAX_API_KEY",
                    "api_key": "${MINIMAX_API_KEY}",
                    "require_auth": True,
                    "task_routing": {
                        "chat": "MiniMax-M2.7",
                        "code_generation": "MiniMax-M2.7",
                        "analysis": "MiniMax-M2.7",
                        "summarization": "MiniMax-M2.7",
                    },
                    "timeout_seconds": 60,
                },
                "llama_server": {
                    "name": "llama_server",
                    "base_url": llama_url,
                    "require_auth": False,
                    "task_routing": {
                        "chat": "qwen3.5",
                        "code_generation": "qwen3.5",
                        "analysis": "qwen3.5",
                        "summarization": "qwen3.5",
                    },
                    "timeout_seconds": 120,
                },
                "ollama": {
                    "name": "ollama",
                    "base_url": os.environ.get(
                        "OLLAMA_BASE_URL", "http://localhost:11434/v1"
                    ),
                    "require_auth": False,
                    "task_routing": {
                        "chat": "qwen2.5-coder:7b",
                        "code_generation": "qwen2.5-coder:7b",
                        "analysis": "qwen2.5-coder:7b",
                        "summarization": "qwen2.5-coder:7b",
                    },
                    "timeout_seconds": 120,
                },
            },
            fallback_chain=["minimax", "llama_server", "ollama"],
        )
        return FallbackChain.from_settings(settings)

    @property
    def _provider_list(self):  # type: ignore[no-untyped-def]
        return self._chain._providers

    def list_providers(self) -> list[str]:
        return [p.name for p in self._provider_list]

    def _is_valid_provider(self, provider: str) -> bool:
        return provider in self.list_providers()

    async def get_available_providers(self) -> list[str]:
        available: list[str] = []
        for provider in self._provider_list:
            try:
                if await provider.health_check():
                    available.append(provider.name)
            except Exception:
                continue
        return available

    async def generate(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,  # ignored — FallbackChain controls order
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        use_fallback: bool = True,  # ignored — FallbackChain always falls back
        task_type: str = "chat",
        **kwargs: Any,
    ) -> LLMResponse:
        task: dict[str, Any] = {
            "task_type": task_type,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if model:
            task["model"] = model
        if max_tokens is not None:
            task["max_tokens"] = max_tokens

        try:
            result = await self._chain.execute(task)
        except Exception as exc:
            raise RuntimeError("No available LLM providers") from exc

        return LLMResponse(
            content=result.get("content", ""),
            model=result.get("model", ""),
            provider=result.get("provider", ""),
            usage=result.get("usage", {}),
            finish_reason="stop",
            timestamp=datetime.now().isoformat(),
        )

    async def generate_text(
        self,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        use_fallback: bool = True,
        task_type: str = "chat",
    ) -> dict[str, Any]:
        messages = [LLMMessage(role="user", content=prompt)]
        try:
            response = await self.generate(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                task_type=task_type,
            )
            return {
                "success": True,
                "content": response.content,
                "provider": response.provider,
                "model": response.model,
                "error": "",
            }
        except Exception as exc:
            return {
                "success": False,
                "content": "",
                "provider": "unknown",
                "model": model or "",
                "error": str(exc),
            }

    async def chat(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        use_fallback: bool = True,
    ) -> dict[str, Any]:
        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"]) for m in messages
        ]
        try:
            response = await self.generate(
                llm_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return {
                "success": True,
                "content": response.content,
                "provider": response.provider,
                "model": response.model,
                "error": "",
            }
        except Exception as exc:
            return {
                "success": False,
                "content": "",
                "provider": "unknown",
                "model": model or "",
                "error": str(exc),
            }

    async def stream_generate(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        use_fallback: bool = True,
        task_type: str = "chat",
        **kwargs: Any,
    ):
        """Yield non-streaming result as a single chunk (FallbackChain has no streaming)."""
        try:
            response = await self.generate(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                task_type=task_type,
            )
            yield response.content
        except RuntimeError:
            raise

    async def test_all_providers(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        probe_task: dict[str, Any] = {
            "messages": [{"role": "user", "content": "ping"}],
            "task_type": "chat",
            "max_tokens": 10,
        }
        for provider in self._provider_list:
            start = time.perf_counter()
            try:
                result = await provider.execute(probe_task)
                results[provider.name] = {
                    "success": True,
                    "response_time_ms": (time.perf_counter() - start) * 1000,
                    "model": result.get("model", ""),
                    "error": "",
                }
            except Exception as exc:
                results[provider.name] = {
                    "success": False,
                    "response_time_ms": (time.perf_counter() - start) * 1000,
                    "model": "",
                    "error": str(exc),
                }
        return results

    def get_provider_info(self) -> dict[str, Any]:
        providers: dict[str, Any] = {}
        for provider in self._provider_list:
            config = provider._config
            providers[provider.name] = {
                "base_url": config.base_url,
                "require_auth": config.require_auth,
                "task_routing": config.task_routing or {},
            }
        return {
            "fallback_chain": self.list_providers(),
            "providers": providers,
        }

    async def sync_provider_configs(
        self,
        source: str = "claude",
        destination: str = "qwen",
        sync_types: list[str] | None = None,
        skip_servers: list[str] | None = None,
    ) -> dict[str, Any]:
        return await _helper_functions(
            self,
            source=source,
            destination=destination,
            sync_types=sync_types,
            skip_servers=skip_servers,
        )
