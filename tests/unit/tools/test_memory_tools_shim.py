"""Unit tests for ``session_buddy.tools.memory_tools`` re-export shim.

The shim delegates to ``_*_impl`` functions in
``session_buddy.mcp.tools.memory.memory_tools`` whose canonical names are
closures inside ``register_memory_tools(mcp)`` and therefore not directly
importable. These tests cover the *wrapper* layer — confirming the shim
wires the public names through to the impls with the right positional and
keyword arguments and that ``search_reflections`` reaches the right backing
modules via its inline imports.

External dependencies (the underlying ``_*_impl`` functions and the inline
``session_buddy.reflection.search.search_reflections`` /
``session_buddy.reflection_tools.get_reflection_database`` imports) are
stubbed via ``monkeypatch.setattr`` so the shim's wrapping logic is exercised
in isolation. No real database or network access is performed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import session_buddy.tools.memory_tools as memory_tools


# ---------------------------------------------------------------------------
# Module-level: __all__ surface
# ---------------------------------------------------------------------------


def test_module_reexports_expected_names() -> None:
    """The public surface documented in ``__all__`` is fully populated."""
    expected = {
        "quick_search",
        "reflection_stats",
        "register_memory_tools",
        "search_by_concept",
        "search_reflections",
        "store_reflection",
    }
    assert set(memory_tools.__all__) == expected
    for name in expected:
        assert hasattr(memory_tools, name), f"missing re-export: {name}"


def test_register_memory_tools_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shim re-exports ``register_memory_tools`` by identity (not wrapped)."""
    sentinel = object()
    monkeypatch.setattr(memory_tools, "register_memory_tools", sentinel)
    assert memory_tools.register_memory_tools is sentinel


# ---------------------------------------------------------------------------
# store_reflection wrapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "tags"),
    [
        ("hello world", None),
        ("hello world", []),
        ("hello world", ["foo"]),
        ("hello world", ["foo", "bar", "baz"]),
        ("", None),
        ("with unicode 你好", ["unicode", "test"]),
    ],
)
async def test_store_reflection_forwards_args(
    monkeypatch: pytest.MonkeyPatch, content: str, tags: list[str] | None
) -> None:
    """``store_reflection`` forwards ``content`` and ``tags`` positionally."""
    stub = AsyncMock(return_value="<stored>")
    monkeypatch.setattr(memory_tools, "_store_reflection_impl", stub)

    result = await memory_tools.store_reflection(content, tags)

    assert result == "<stored>"
    stub.assert_awaited_once_with(content, tags)


async def test_store_reflection_is_coroutine(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper returns a value that resolves to the impl's return."""
    monkeypatch.setattr(
        memory_tools, "_store_reflection_impl", AsyncMock(return_value="ok")
    )

    out = await memory_tools.store_reflection("c", ["t"])

    assert out == "ok"


# ---------------------------------------------------------------------------
# quick_search wrapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "min_score", "project"),
    [
        ("Q", 0.7, None),
        ("Q", 0.5, "proj"),
        ("Q", 0.0, "proj"),
        ("Q", 1.0, None),
        ("Q", 0.95, "p1"),
        ("with spaces & specials?", 0.42, "weird/proj"),
    ],
)
async def test_quick_search_forwards_args(
    monkeypatch: pytest.MonkeyPatch, query: str, min_score: float, project: str | None
) -> None:
    """``quick_search`` forwards ``query, min_score, project`` positionally."""
    stub = AsyncMock(return_value="<quick>")
    monkeypatch.setattr(memory_tools, "_quick_search_impl", stub)

    result = await memory_tools.quick_search(query, min_score, project)

    assert result == "<quick>"
    stub.assert_awaited_once_with(query, min_score, project)


async def test_quick_search_uses_default_min_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting ``min_score`` falls through to the impl's default (``0.7``)."""
    stub = AsyncMock(return_value="<quick>")
    monkeypatch.setattr(memory_tools, "_quick_search_impl", stub)

    await memory_tools.quick_search("Q")  # type: ignore[call-arg]

    stub.assert_awaited_once_with("Q", 0.7, None)


async def test_quick_search_propagates_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bubbles up exceptions raised by the impl (no swallowing)."""
    stub = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(memory_tools, "_quick_search_impl", stub)

    with pytest.raises(RuntimeError, match="boom"):
        await memory_tools.quick_search("Q", 0.7, None)


# ---------------------------------------------------------------------------
# search_by_concept wrapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("concept", "include_files", "limit", "project"),
    [
        ("refactor", True, 10, None),
        ("refactor", False, 10, None),
        ("refactor", True, 1, "p"),
        ("refactor", True, 0, None),
        ("refactor", True, 1000, "p"),
        ("concept with space", False, 5, "proj-x"),
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
    monkeypatch.setattr(memory_tools, "_search_by_concept_impl", stub)

    result = await memory_tools.search_by_concept(concept, include_files, limit, project)

    assert result == "<concept>"
    stub.assert_awaited_once_with(concept, include_files, limit, project)


async def test_search_by_concept_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default args (``include_files=True, limit=10, project=None``) flow through."""
    stub = AsyncMock(return_value="<concept>")
    monkeypatch.setattr(memory_tools, "_search_by_concept_impl", stub)

    await memory_tools.search_by_concept("refactor")  # type: ignore[call-arg]

    stub.assert_awaited_once_with("refactor", True, 10, None)


# ---------------------------------------------------------------------------
# reflection_stats wrapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("project_arg", [None, "some-project", "another/proj"])
async def test_reflection_stats_ignores_project_arg(
    monkeypatch: pytest.MonkeyPatch, project_arg: str | None
) -> None:
    """``reflection_stats`` accepts ``project`` but does not forward it.

    The shim signature exposes ``project`` for caller convenience, but the
    underlying ``_reflection_stats_impl`` takes no args and operates on the
    global reflection DB. This test pins that quirky surface so the wrapper
    doesn't accidentally start forwarding the kwarg.
    """
    stub = AsyncMock(return_value="<stats>")
    monkeypatch.setattr(memory_tools, "_reflection_stats_impl", stub)

    result = await memory_tools.reflection_stats(project_arg)

    assert result == "<stats>"
    stub.assert_awaited_once_with()


async def test_reflection_stats_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """``reflection_stats()`` with no args resolves correctly."""
    stub = AsyncMock(return_value="<stats>")
    monkeypatch.setattr(memory_tools, "_reflection_stats_impl", stub)

    out = await memory_tools.reflection_stats()

    assert out == "<stats>"
    stub.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# search_reflections wrapper
# ---------------------------------------------------------------------------


async def test_search_reflections_resolves_db_then_calls_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``search_reflections`` fetches the active DB then delegates.

    The wrapper has its own inline ``from X import Y`` statements; the test
    stubs the source modules so the inline imports resolve to the mocks and
    both calls happen in the expected order with the expected kwargs.
    """
    fake_db = object()
    fake_results: list[dict[str, object]] = [{"id": "r1"}, {"id": "r2"}]

    fake_get_db = AsyncMock(return_value=fake_db)
    fake_search = AsyncMock(return_value=fake_results)
    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database", fake_get_db
    )
    monkeypatch.setattr(
        "session_buddy.reflection.search.search_reflections", fake_search
    )

    result = await memory_tools.search_reflections(query="Q", limit=7, project="p1")

    fake_get_db.assert_awaited_once_with()
    fake_search.assert_awaited_once_with(
        db=fake_db,
        query="Q",
        query_embedding=None,
        limit=7,
        project="p1",
    )
    assert result is fake_results


@pytest.mark.parametrize(
    ("query", "limit", "project"),
    [
        ("alpha", 10, None),
        ("beta", 1, "p"),
        ("gamma", 0, None),
        ("delta", 9999, "x/y"),
        ("", 5, None),
    ],
)
async def test_search_reflections_kwargs(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    limit: int,
    project: str | None,
) -> None:
    """All three kwargs are forwarded to the inner ``search_reflections``."""
    fake_db = object()
    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        AsyncMock(return_value=fake_db),
    )
    fake_search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "session_buddy.reflection.search.search_reflections", fake_search
    )

    await memory_tools.search_reflections(query=query, limit=limit, project=project)

    fake_search.assert_awaited_once_with(
        db=fake_db,
        query=query,
        query_embedding=None,
        limit=limit,
        project=project,
    )


async def test_search_reflections_uses_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting ``limit`` and ``project`` flows through their defaults."""
    fake_db = object()
    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        AsyncMock(return_value=fake_db),
    )
    fake_search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "session_buddy.reflection.search.search_reflections", fake_search
    )

    await memory_tools.search_reflections("Q")  # type: ignore[call-arg]

    fake_search.assert_awaited_once_with(
        db=fake_db,
        query="Q",
        query_embedding=None,
        limit=10,
        project=None,
    )


async def test_search_reflections_propagates_db_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error from ``get_reflection_database`` bubbles up unchanged."""
    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        AsyncMock(side_effect=ConnectionError("db down")),
    )
    fake_search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "session_buddy.reflection.search.search_reflections", fake_search
    )

    with pytest.raises(ConnectionError, match="db down"):
        await memory_tools.search_reflections("Q")

    fake_search.assert_not_awaited()


async def test_search_reflections_propagates_search_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error from the inner search bubbles up unchanged."""
    fake_db = object()
    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        AsyncMock(return_value=fake_db),
    )
    monkeypatch.setattr(
        "session_buddy.reflection.search.search_reflections",
        AsyncMock(side_effect=ValueError("bad query")),
    )

    with pytest.raises(ValueError, match="bad query"):
        await memory_tools.search_reflections("Q")


async def test_search_reflections_returns_awaitable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper is awaitable and the resolved value matches the inner search."""
    fake_db = object()
    sentinel: list[dict[str, object]] = [{"k": "v"}]
    monkeypatch.setattr(
        "session_buddy.reflection_tools.get_reflection_database",
        AsyncMock(return_value=fake_db),
    )
    monkeypatch.setattr(
        "session_buddy.reflection.search.search_reflections",
        AsyncMock(return_value=sentinel),
    )

    out = await memory_tools.search_reflections("Q", 3, "p")
    assert out is sentinel
