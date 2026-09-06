"""Unit tests for ``session_buddy.tools.search_tools`` re-export shim.

The shim delegates to ``_*_impl`` functions in
``session_buddy.mcp.tools.memory.search_tools`` whose canonical names are
closures inside ``register_search_tools(mcp)`` and therefore not directly
importable. These tests cover the *wrapper* layer — confirming the shim
wires the public names through to the impls with the right positional and
keyword arguments.

External dependencies (the underlying ``_*_impl`` functions) are stubbed via
``monkeypatch.setattr`` so the shim's wrapping logic is exercised in
isolation. No real database or network access is performed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import session_buddy.tools.search_tools as search_tools


# ---------------------------------------------------------------------------
# Module-level: __all__ surface
# ---------------------------------------------------------------------------


def test_module_reexports_expected_names() -> None:
    """The public surface documented in ``__all__`` is fully populated."""
    expected = {
        "quick_search",
        "reflection_stats",
        "register_search_tools",
        "search_by_concept",
        "search_code",
        "store_reflection",
    }
    assert set(search_tools.__all__) == expected
    for name in expected:
        assert hasattr(search_tools, name), f"missing re-export: {name}"


def test_register_search_tools_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shim re-exports ``register_search_tools`` by identity (not wrapped)."""
    sentinel = object()
    monkeypatch.setattr(search_tools, "register_search_tools", sentinel)
    assert search_tools.register_search_tools is sentinel


# ---------------------------------------------------------------------------
# store_reflection wrapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "tags"),
    [
        ("hello", None),
        ("hello", []),
        ("hello", ["a"]),
        ("hello", ["a", "b"]),
        ("", ["only-tags"]),
        ("", None),
    ],
)
async def test_store_reflection_forwards_args(
    monkeypatch: pytest.MonkeyPatch, content: str, tags: list[str] | None
) -> None:
    """``store_reflection`` forwards ``content, tags`` positionally."""
    stub = AsyncMock(return_value="<stored>")
    monkeypatch.setattr(search_tools, "_store_reflection_impl", stub)

    result = await search_tools.store_reflection(content, tags)

    assert result == "<stored>"
    stub.assert_awaited_once_with(content, tags)


async def test_store_reflection_is_coroutine(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper resolves to the impl's return value."""
    monkeypatch.setattr(
        search_tools, "_store_reflection_impl", AsyncMock(return_value="ok")
    )

    out = await search_tools.store_reflection("c", ["t"])

    assert out == "ok"


# ---------------------------------------------------------------------------
# quick_search wrapper (note: differs from memory_tools version — adds ``limit``)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "project", "min_score", "limit"),
    [
        ("Q", None, 0.7, 5),
        ("Q", "p", 0.7, 5),
        ("Q", None, 0.0, 1),
        ("Q", None, 1.0, 1000),
        ("Q", "deep/path", 0.42, 0),
        ("with ?specials&", None, 0.95, 25),
    ],
)
async def test_quick_search_forwards_args(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    project: str | None,
    min_score: float,
    limit: int,
) -> None:
    """``quick_search`` forwards ``query, project, min_score, limit`` positionally."""
    stub = AsyncMock(return_value="<quick>")
    monkeypatch.setattr(search_tools, "_quick_search_impl", stub)

    result = await search_tools.quick_search(query, project, min_score, limit)

    assert result == "<quick>"
    stub.assert_awaited_once_with(query, project, min_score, limit)


async def test_quick_search_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default args (``project=None, min_score=0.7, limit=5``) flow through."""
    stub = AsyncMock(return_value="<quick>")
    monkeypatch.setattr(search_tools, "_quick_search_impl", stub)

    await search_tools.quick_search("Q")  # type: ignore[call-arg]

    stub.assert_awaited_once_with("Q", None, 0.7, 5)


async def test_quick_search_propagates_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bubbles up exceptions raised by the impl (no swallowing)."""
    stub = AsyncMock(side_effect=RuntimeError("kaboom"))
    monkeypatch.setattr(search_tools, "_quick_search_impl", stub)

    with pytest.raises(RuntimeError, match="kaboom"):
        await search_tools.quick_search("Q", None, 0.7, 5)


# ---------------------------------------------------------------------------
# search_by_concept wrapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("concept", "include_files", "limit", "project"),
    [
        ("refactor", True, 10, None),
        ("refactor", False, 10, None),
        ("refactor", True, 0, "p"),
        ("refactor", False, 1, "p"),
        ("c", True, 100, "deep/proj"),
        ("with spaces and ?", False, 5, None),
    ],
)
async def test_search_by_concept_forwards_args(
    monkeypatch: pytest.MonkeyPatch,
    concept: str,
    include_files: bool,
    limit: int,
    project: str | None,
) -> None:
    """``search_by_concept`` forwards all four args positionally."""
    stub = AsyncMock(return_value="<concept>")
    monkeypatch.setattr(search_tools, "_search_by_concept_impl", stub)

    result = await search_tools.search_by_concept(concept, include_files, limit, project)

    assert result == "<concept>"
    stub.assert_awaited_once_with(concept, include_files, limit, project)


async def test_search_by_concept_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default args (``include_files=True, limit=10, project=None``) flow through."""
    stub = AsyncMock(return_value="<concept>")
    monkeypatch.setattr(search_tools, "_search_by_concept_impl", stub)

    await search_tools.search_by_concept("refactor")  # type: ignore[call-arg]

    stub.assert_awaited_once_with("refactor", True, 10, None)


# ---------------------------------------------------------------------------
# search_code wrapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "pattern_type", "limit", "project"),
    [
        ("async def", None, 10, None),
        ("async def", "function", 10, None),
        ("async def", "class", 10, None),
        ("async def", "method", 10, None),
        ("async def", "decorator", 10, None),
        ("async def", None, 1, "p"),
        ("async def", None, 0, "p"),
        ("async def", "module", 1000, "deep/proj"),
        ("with ?specials&", None, 5, None),
        ("", "function", 5, None),
    ],
)
async def test_search_code_forwards_args(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    pattern_type: str | None,
    limit: int,
    project: str | None,
) -> None:
    """``search_code`` forwards all four args positionally."""
    stub = AsyncMock(return_value="<code>")
    monkeypatch.setattr(search_tools, "_search_code_impl", stub)

    result = await search_tools.search_code(query, pattern_type, limit, project)

    assert result == "<code>"
    stub.assert_awaited_once_with(query, pattern_type, limit, project)


async def test_search_code_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default args (``pattern_type=None, limit=10, project=None``) flow through."""
    stub = AsyncMock(return_value="<code>")
    monkeypatch.setattr(search_tools, "_search_code_impl", stub)

    await search_tools.search_code("async def")  # type: ignore[call-arg]

    stub.assert_awaited_once_with("async def", None, 10, None)


async def test_search_code_propagates_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bubbles up exceptions raised by the impl (no swallowing)."""
    stub = AsyncMock(side_effect=ValueError("bad regex"))
    monkeypatch.setattr(search_tools, "_search_code_impl", stub)

    with pytest.raises(ValueError, match="bad regex"):
        await search_tools.search_code("(?P<unbalanced", None, 10, None)


# ---------------------------------------------------------------------------
# reflection_stats wrapper
# ---------------------------------------------------------------------------


async def test_reflection_stats_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """``reflection_stats()`` takes no args and forwards none to the impl."""
    stub = AsyncMock(return_value="<stats>")
    monkeypatch.setattr(search_tools, "_reflection_stats_impl", stub)

    result = await search_tools.reflection_stats()

    assert result == "<stats>"
    stub.assert_awaited_once_with()


async def test_reflection_stats_is_awaitable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper is awaitable and resolves to the impl's value."""
    monkeypatch.setattr(
        search_tools, "_reflection_stats_impl", AsyncMock(return_value="<stats>")
    )

    out = await search_tools.reflection_stats()

    assert out == "<stats>"


async def test_reflection_stats_propagates_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bubbles up exceptions raised by the impl (no swallowing)."""
    stub = AsyncMock(side_effect=KeyError("missing"))
    monkeypatch.setattr(search_tools, "_reflection_stats_impl", stub)

    with pytest.raises(KeyError, match="missing"):
        await search_tools.reflection_stats()
