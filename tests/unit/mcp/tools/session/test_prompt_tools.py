"""Tests for ``session_buddy.mcp.tools.session.prompt_tools``.

Targets ``prompt_tools.py`` (453 LOC, 52.5% baseline coverage).
Covers:
- ``PromptDefinition`` dataclass (init, ``get_content`` with/without content_key)
- ``_create_prompt_handler`` returns an async handler that resolves content
- ``register_prompt_tools`` / ``_register_prompt_group`` decorator flow
- All prompt groups are registered with the right names
- Each prompt group renders its content correctly
"""

from __future__ import annotations

from typing import Any

import pytest

from session_buddy.mcp.tools.session import prompt_tools as mod
from session_buddy.mcp.tools.session.prompt_tools import (
    ALL_PROMPT_GROUPS,
    CONTEXT_PROMPTS,
    CORE_PROMPTS,
    CRACKERJACK_PROMPTS,
    MEMORY_PROMPTS,
    MONITORING_PROMPTS,
    REFLECTION_PROMPTS,
    PromptDefinition,
    _create_prompt_handler,
    _register_prompt_group,
    register_prompt_tools,
)


class _FakeMCP:
    """Capture-only MCP stand-in for prompt-registration tests."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}
        self.resources: dict[str, Any] = {}

    def tool(self, *_args: Any, **_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            return fn

        return decorator

    def add_tool(self, fn: Any, name: str | None = None, **_kwargs: Any) -> None:
        self.tools[name or fn.__name__] = fn

    def prompt(self, *_args: Any, **_kwargs: Any) -> Any:
        # Supports both ``@mcp.prompt("name")`` and ``@mcp.prompt()``.
        name: str | None = None
        if _args and isinstance(_args[0], str):
            name = _args[0]

        def decorator(fn: Any) -> Any:
            registered_name = name or fn.__name__
            self.prompts[registered_name] = fn
            return fn

        return decorator

    def resource(self, *_args: Any, **_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            return fn

        return decorator


@pytest.fixture
def fake_mcp() -> _FakeMCP:
    return _FakeMCP()


# ---------------------------------------------------------------------------
# PromptDefinition
# ---------------------------------------------------------------------------


class TestPromptDefinition:
    def test_init_stores_all_fields(self) -> None:
        definition = PromptDefinition(
            name="x",
            description="desc",
            content_key="k",
            content="C",
        )
        assert definition.name == "x"
        assert definition.description == "desc"
        assert definition.content_key == "k"
        assert definition.content == "C"

    def test_init_optional_fields_default_to_none(self) -> None:
        definition = PromptDefinition(name="x", description="d")
        assert definition.content_key is None
        assert definition.content is None

    def test_is_frozen(self) -> None:
        definition = PromptDefinition(name="x", description="d")
        with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError subclass
            definition.name = "changed"  # type: ignore[misc]

    def test_get_content_returns_content_key_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sentinel = "from-session-commands"
        # The class uses SESSION_COMMANDS at module level; patch its __getitem__.
        monkeypatch.setitem(mod.SESSION_COMMANDS, "ck", sentinel)
        definition = PromptDefinition(name="x", description="d", content_key="ck")
        assert definition.get_content() == sentinel

    def test_get_content_falls_back_to_inline_content(self) -> None:
        definition = PromptDefinition(name="x", description="d", content="inline")
        assert definition.get_content() == "inline"

    def test_get_content_returns_empty_string_when_neither_set(self) -> None:
        definition = PromptDefinition(name="x", description="d")
        assert definition.get_content() == ""


# ---------------------------------------------------------------------------
# _create_prompt_handler
# ---------------------------------------------------------------------------


class TestCreatePromptHandler:
    def test_handler_returns_definition_content(self) -> None:
        definition = PromptDefinition(name="x", description="d", content="hello")
        handler = _create_prompt_handler(definition)
        assert handler.__name__ == "get_x_prompt"

    def test_handler_underscores_dashes(self) -> None:
        definition = PromptDefinition(name="search-code", description="d", content="hi")
        handler = _create_prompt_handler(definition)
        assert handler.__name__ == "get_search_code_prompt"

    def test_handler_sets_doc(self) -> None:
        definition = PromptDefinition(name="x", description="this is doc", content="hi")
        handler = _create_prompt_handler(definition)
        assert handler.__doc__ == "this is doc"

    @pytest.mark.asyncio
    async def test_handler_invocation_returns_content(self) -> None:
        definition = PromptDefinition(name="x", description="d", content="payload")
        handler = _create_prompt_handler(definition)
        result = await handler()
        assert result == "payload"


# ---------------------------------------------------------------------------
# _register_prompt_group
# ---------------------------------------------------------------------------


class TestRegisterPromptGroup:
    def test_registers_every_prompt_in_group(self, fake_mcp: _FakeMCP) -> None:
        group = (
            PromptDefinition(name="a", description="A", content="A-content"),
            PromptDefinition(name="b", description="B", content="B-content"),
        )
        _register_prompt_group(fake_mcp, group)
        assert set(fake_mcp.prompts) == {"a", "b"}
        assert all(callable(v) for v in fake_mcp.prompts.values())


# ---------------------------------------------------------------------------
# register_prompt_tools
# ---------------------------------------------------------------------------


class TestRegisterPromptTools:
    def test_registers_all_grouped_prompts(self, fake_mcp: _FakeMCP) -> None:
        register_prompt_tools(fake_mcp)
        # Aggregate expected names across all groups.
        expected = set()
        for group in ALL_PROMPT_GROUPS:
            expected.update(d.name for d in group)
        assert expected.issubset(set(fake_mcp.prompts))
        # Spot check canonical names.
        assert "start" in fake_mcp.prompts
        assert "checkpoint" in fake_mcp.prompts
        assert "end" in fake_mcp.prompts
        assert "status" in fake_mcp.prompts
        assert "permissions" in fake_mcp.prompts
        assert "reflect" in fake_mcp.prompts
        assert "crackerjack-run" in fake_mcp.prompts
        assert "compress-memory" in fake_mcp.prompts
        assert "auto-load-context" in fake_mcp.prompts
        assert "start-app-monitoring" in fake_mcp.prompts

    def test_no_duplicate_names_across_groups(self, fake_mcp: _FakeMCP) -> None:
        register_prompt_tools(fake_mcp)
        all_names = [d.name for group in ALL_PROMPT_GROUPS for d in group]
        assert len(all_names) == len(set(all_names)), "duplicate prompt names"

    def test_all_groups_covered(self) -> None:
        # ALL_PROMPT_GROUPS must reference every module-level group.
        assert CORE_PROMPTS in ALL_PROMPT_GROUPS
        assert REFLECTION_PROMPTS in ALL_PROMPT_GROUPS
        assert CRACKERJACK_PROMPTS in ALL_PROMPT_GROUPS
        assert MEMORY_PROMPTS in ALL_PROMPT_GROUPS
        assert CONTEXT_PROMPTS in ALL_PROMPT_GROUPS
        assert MONITORING_PROMPTS in ALL_PROMPT_GROUPS

    @pytest.mark.asyncio
    async def test_registered_prompt_inlines_content(self, fake_mcp: _FakeMCP) -> None:
        register_prompt_tools(fake_mcp)
        # ``compress-memory`` has direct inline content.
        handler = fake_mcp.prompts["compress-memory"]
        content = await handler()
        assert "Memory Compression" in content
        assert "compress_memory()" in content


# ---------------------------------------------------------------------------
# Per-group sanity tests — exercise each prompt group's rendering.
# ---------------------------------------------------------------------------


class TestPromptGroups:
    @pytest.mark.parametrize(
        "group",
        [
            CORE_PROMPTS,
            REFLECTION_PROMPTS,
            CRACKERJACK_PROMPTS,
            MEMORY_PROMPTS,
            CONTEXT_PROMPTS,
            MONITORING_PROMPTS,
        ],
    )
    @pytest.mark.asyncio
    async def test_group_registers_and_renders(self, fake_mcp: _FakeMCP, group: tuple) -> None:
        _register_prompt_group(fake_mcp, group)
        for definition in group:
            handler = fake_mcp.prompts[definition.name]
            content = await handler()
            if definition.content_key:
                # SESSION_COMMANDS must back this entry.
                content_str = mod.SESSION_COMMANDS[definition.content_key]
                assert content == content_str
            elif definition.content:
                assert content == definition.content
            else:
                assert content == ""

    @pytest.mark.asyncio
    async def test_crackerjack_run_prompt_resolves_via_session_commands(
        self, fake_mcp: _FakeMCP
    ) -> None:
        _register_prompt_group(fake_mcp, CRACKERJACK_PROMPTS)
        # The four crackerjack prompts all use content_key.
        for name in ("crackerjack-run", "crackerjack-history",
                     "crackerjack-metrics", "crackerjack-patterns"):
            handler = fake_mcp.prompts[name]
            result = await handler()
            # Should be a string — the actual SESSION_COMMANDS entry is opaque.
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_context_prompts_inline_content(self, fake_mcp: _FakeMCP) -> None:
        _register_prompt_group(fake_mcp, CONTEXT_PROMPTS)
        for name in ("auto-load-context", "context-summary",
                     "search-code", "search-errors", "search-temporal"):
            handler = fake_mcp.prompts[name]
            result = await handler()
            assert isinstance(result, str)
            assert result  # non-empty

    @pytest.mark.asyncio
    async def test_monitoring_prompts_inline_content(self, fake_mcp: _FakeMCP) -> None:
        _register_prompt_group(fake_mcp, MONITORING_PROMPTS)
        for name in (
            "start-app-monitoring",
            "stop-app-monitoring",
            "activity-summary",
            "context-insights",
            "active-files",
            "quality-monitor",
            "auto-compact",
        ):
            handler = fake_mcp.prompts[name]
            result = await handler()
            assert isinstance(result, str)
            assert result
