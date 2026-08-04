"""Unit tests for `session_buddy.mcp.tools.session.prompt_tools`.

Wave 1 Batch 1a Module 2 lift: bring coverage to >=95% line / >=90% branch.

Covers the public surface:

- ``PromptDefinition`` dataclass + ``get_content`` (content_key / content / empty)
- All prompt group tuples (``CORE_PROMPTS`` etc.)
- ``ALL_PROMPT_GROUPS`` aggregation
- ``register_prompt_tools`` MCP registration
- The async handler returned by ``_create_prompt_handler``

The module deliberately tests with a real ``SESSION_COMMANDS`` entry for the
content_key path because the import is already a module-level dependency.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import Mock

import pytest

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
from session_buddy.session_commands import SESSION_COMMANDS

# ---------------------------------------------------------------------------
# PromptDefinition tests
# ---------------------------------------------------------------------------


def test_prompt_definition_with_content_key_returns_session_command() -> None:
    """When ``content_key`` is set, ``get_content`` looks up SESSION_COMMANDS."""
    definition = PromptDefinition(
        name="start",
        description="init desc",
        content_key="init",
    )

    result = definition.get_content()

    assert result == SESSION_COMMANDS["init"]


def test_prompt_definition_with_direct_content_returns_content() -> None:
    """When only ``content`` is set, ``get_content`` returns it verbatim."""
    definition = PromptDefinition(
        name="custom",
        description="custom desc",
        content="direct body",
    )

    result = definition.get_content()

    assert result == "direct body"


def test_prompt_definition_with_neither_returns_empty_string() -> None:
    """With both fields ``None``, ``get_content`` returns empty string."""
    definition = PromptDefinition(name="blank", description="blank desc")

    result = definition.get_content()

    assert result == ""


def test_prompt_definition_content_key_wins_over_content() -> None:
    """``content_key`` takes precedence over ``content`` when both are set."""
    definition = PromptDefinition(
        name="start",
        description="init desc",
        content_key="init",
        content="ignored-body",
    )

    result = definition.get_content()

    assert result == SESSION_COMMANDS["init"]
    assert "ignored-body" not in result


def test_prompt_definition_is_frozen() -> None:
    """PromptDefinition is a frozen dataclass - assignment raises."""
    definition = PromptDefinition(name="x", description="y")

    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError subclass
        definition.name = "mutated"  # type: ignore[misc]


def test_prompt_definition_repr_contains_name_and_description() -> None:
    """Dataclass repr exposes the public fields for diagnostics."""
    definition = PromptDefinition(name="start", description="init desc")

    text = repr(definition)

    assert "start" in text
    assert "init desc" in text


# ---------------------------------------------------------------------------
# Prompt group contents
# ---------------------------------------------------------------------------


def test_core_prompts_has_expected_names() -> None:
    """CORE_PROMPTS contains exactly the four session lifecycle prompts."""
    names = {p.name for p in CORE_PROMPTS}

    assert names == {"start", "checkpoint", "end", "status"}


def test_reflection_prompts_has_expected_names() -> None:
    """REFLECTION_PROMPTS contains the five reflection prompts."""
    names = {p.name for p in REFLECTION_PROMPTS}

    assert names == {
        "permissions",
        "reflect",
        "quick-search",
        "search-summary",
        "reflection-stats",
    }


def test_crackerjack_prompts_has_expected_names() -> None:
    """CRACKERJACK_PROMPTS contains the four crackerjack prompts."""
    names = {p.name for p in CRACKERJACK_PROMPTS}

    assert names == {
        "crackerjack-run",
        "crackerjack-history",
        "crackerjack-metrics",
        "crackerjack-patterns",
    }


def test_memory_prompts_has_expected_names() -> None:
    """MEMORY_PROMPTS contains the three memory management prompts."""
    names = {p.name for p in MEMORY_PROMPTS}

    assert names == {"compress-memory", "compression-stats", "retention-policy"}


def test_context_prompts_has_expected_names() -> None:
    """CONTEXT_PROMPTS contains the five context + search prompts."""
    names = {p.name for p in CONTEXT_PROMPTS}

    assert names == {
        "auto-load-context",
        "context-summary",
        "search-code",
        "search-errors",
        "search-temporal",
    }


def test_monitoring_prompts_has_expected_names() -> None:
    """MONITORING_PROMPTS contains the seven monitoring prompts."""
    names = {p.name for p in MONITORING_PROMPTS}

    assert names == {
        "start-app-monitoring",
        "stop-app-monitoring",
        "activity-summary",
        "context-insights",
        "active-files",
        "quality-monitor",
        "auto-compact",
    }


# ---------------------------------------------------------------------------
# ALL_PROMPT_GROUPS aggregation
# ---------------------------------------------------------------------------


def test_all_prompt_groups_includes_every_known_group() -> None:
    """``ALL_PROMPT_GROUPS`` aggregates all six named groups."""
    assert set(ALL_PROMPT_GROUPS) == {
        CORE_PROMPTS,
        REFLECTION_PROMPTS,
        CRACKERJACK_PROMPTS,
        MEMORY_PROMPTS,
        CONTEXT_PROMPTS,
        MONITORING_PROMPTS,
    }


def test_all_prompt_groups_contains_no_duplicates() -> None:
    """``ALL_PROMPT_GROUPS`` is a tuple - no group appears twice."""
    assert len(ALL_PROMPT_GROUPS) == len(set(ALL_PROMPT_GROUPS))


# ---------------------------------------------------------------------------
# PromptDefinition.get_content across the real groups
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "definition",
    [p for group in ALL_PROMPT_GROUPS for p in group],
    ids=lambda d: getattr(d, "name", "<unknown>"),
)
def test_every_prompt_get_content_returns_non_empty_string(definition: PromptDefinition) -> None:
    """Every prompt definition resolves to a non-empty string."""
    result = definition.get_content()

    assert isinstance(result, str)
    assert result  # non-empty


# ---------------------------------------------------------------------------
# _create_prompt_handler
# ---------------------------------------------------------------------------


def test_create_prompt_handler_returns_async_callable() -> None:
    """The handler produced by ``_create_prompt_handler`` is a coroutine function."""
    definition = PromptDefinition(
        name="start",
        description="init desc",
        content_key="init",
    )

    handler = _create_prompt_handler(definition)

    assert inspect.iscoroutinefunction(handler)


def test_create_prompt_handler_handler_name_is_derived() -> None:
    """The handler's ``__name__`` follows the ``get_<name>_prompt`` convention."""
    definition = PromptDefinition(
        name="quick-search",
        description="qs desc",
        content_key="quick-search",
    )

    handler = _create_prompt_handler(definition)

    assert handler.__name__ == "get_quick_search_prompt"


def test_create_prompt_handler_handler_doc_is_description() -> None:
    """The handler's ``__doc__`` mirrors the definition description."""
    definition = PromptDefinition(
        name="checkpoint",
        description="the description",
        content_key="checkpoint",
    )

    handler = _create_prompt_handler(definition)

    assert handler.__doc__ == "the description"


def test_create_prompt_handler_invokes_get_content() -> None:
    """Calling the async handler returns ``definition.get_content()``."""
    definition = PromptDefinition(
        name="end",
        description="end desc",
        content="handler body",
    )

    handler = _create_prompt_handler(definition)
    result = asyncio.run(handler())  # reason: drive async handler from sync test

    assert result == "handler body"


def test_create_prompt_handler_with_direct_content() -> None:
    """Handler using ``content`` (not ``content_key``) returns it verbatim."""
    definition = PromptDefinition(
        name="custom-direct",
        description="direct desc",
        content="# Hello\nDirect body",
    )

    handler = _create_prompt_handler(definition)
    result = asyncio.run(handler())  # reason: drive async handler from sync test

    assert "Direct body" in result


def test_create_prompt_handler_with_content_key_returns_session_command() -> None:
    """Handler using ``content_key`` resolves through SESSION_COMMANDS."""
    definition = PromptDefinition(
        name="start",
        description="init desc",
        content_key="init",
    )

    handler = _create_prompt_handler(definition)
    result = asyncio.run(handler())  # reason: drive async handler from sync test

    assert result == SESSION_COMMANDS["init"]


# ---------------------------------------------------------------------------
# _register_prompt_group
# ---------------------------------------------------------------------------


def test_register_prompt_group_calls_mcp_prompt_for_each_definition() -> None:
    """``_register_prompt_group`` registers every definition via ``mcp.prompt``."""
    mcp = Mock()
    mcp.prompt = Mock(return_value=lambda f: f)

    _register_prompt_group(mcp, CORE_PROMPTS)

    # All four CORE_PROMPTS were registered
    assert mcp.prompt.call_count == len(CORE_PROMPTS)
    registered_names = {call.args[0] for call in mcp.prompt.call_args_list}
    assert registered_names == {"start", "checkpoint", "end", "status"}


def test_register_prompt_group_with_empty_tuple_is_a_noop() -> None:
    """``_register_prompt_group`` with no definitions does not call ``mcp.prompt``."""
    mcp = Mock()
    mcp.prompt = Mock(return_value=lambda f: f)

    _register_prompt_group(mcp, ())

    assert mcp.prompt.call_count == 0


# ---------------------------------------------------------------------------
# register_prompt_tools
# ---------------------------------------------------------------------------


def test_register_prompt_tools_registers_all_groups() -> None:
    """``register_prompt_tools`` registers every prompt definition across all groups."""
    mcp = Mock()
    mcp.prompt = Mock(return_value=lambda f: f)

    register_prompt_tools(mcp)

    expected_total = sum(len(group) for group in ALL_PROMPT_GROUPS)
    assert mcp.prompt.call_count == expected_total


def test_register_prompt_tools_registers_unique_names() -> None:
    """Every prompt name is registered exactly once."""
    mcp = Mock()
    mcp.prompt = Mock(return_value=lambda f: f)

    register_prompt_tools(mcp)

    names = [call.args[0] for call in mcp.prompt.call_args_list]
    assert len(names) == len(set(names))  # no duplicates


def test_register_prompt_tools_registers_every_known_prompt_name() -> None:
    """The set of registered names matches the union of all group names."""
    mcp = Mock()
    mcp.prompt = Mock(return_value=lambda f: f)

    register_prompt_tools(mcp)

    expected_names = {
        p.name for group in ALL_PROMPT_GROUPS for p in group
    }
    registered_names = {call.args[0] for call in mcp.prompt.call_args_list}
    assert registered_names == expected_names


def test_register_prompt_tools_returns_none() -> None:
    """``register_prompt_tools`` returns ``None`` (side-effecting registration)."""
    mcp = Mock()
    mcp.prompt = Mock(return_value=lambda f: f)

    result = register_prompt_tools(mcp)

    assert result is None


def test_register_prompt_tools_passes_callable_to_decorator() -> None:
    """Each ``mcp.prompt(name)`` returns a decorator; the handler is passed through."""
    received_handlers: list[object] = []
    mcp = Mock()

    def decorator(_name: str):
        def wrap(handler: object) -> object:
            received_handlers.append(handler)
            return handler

        return wrap

    mcp.prompt = decorator

    register_prompt_tools(mcp)

    # Every registration yielded exactly one handler (no missing definitions)
    expected_total = sum(len(group) for group in ALL_PROMPT_GROUPS)
    assert len(received_handlers) == expected_total
    # Every handler is callable (the asyncio callable produced by the module)
    for handler in received_handlers:
        assert callable(handler)


# ---------------------------------------------------------------------------
# MCP registration smoke
# ---------------------------------------------------------------------------


def test_register_prompt_tools_is_importable() -> None:
    """MCP smoke: ``register_prompt_tools`` is exposed and not None."""
    assert register_prompt_tools is not None
    assert callable(register_prompt_tools)