"""Unit tests for session_buddy.mcp.tools.session.hooks_tools.

Lifts coverage on ``hooks_tools`` (the only target with single-digit coverage
in the brief). Covers every public tool exposed via
``register_hooks_tools`` plus the private ``_get_hooks_manager`` helper.

Patterns established for hooks/causal-chain tools (per the brief):
- ``_FakeMCP`` server class captures decorated callables.
- Module-scope ``monkeypatch.setattr`` swaps the imported symbol
  (``session_buddy.mcp.tools.session.hooks_tools``), not a dotted string,
  so production-side rebindings do not affect the test fixture.
- Causal chain / hooks manager dependencies are patched at the
  ``session_buddy.core.causal_chains`` / ``session_buddy.core.hooks``
  boundary to keep each test independent of the live DuckDB store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.core.hooks import HooksManager


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Capture tools/prompts decorated on the fake server."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def prompt(self):
        def decorator(fn):
            self.prompts[fn.__name__] = fn
            return fn

        return decorator


@dataclass
class _FakeErrorEvent:
    """Mimic ``ErrorEvent`` for the response payloads."""

    id: str = "err-1"
    error_message: str = "boom"
    error_type: str = "ValueError"
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: str = "session-1"


@dataclass
class _FakeFixAttempt:
    """Mimic ``FixAttempt`` for the response payloads."""

    id: str = "fix-1"
    error_id: str = "err-1"
    action_taken: str = "patched"
    code_changes: str | None = None
    successful: bool = True
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class _FakeCausalChain:
    """Mimic ``CausalChain`` for the response payloads."""

    id: str = "chain-1"
    error_event: _FakeErrorEvent = field(default_factory=_FakeErrorEvent)
    fix_attempts: list[_FakeFixAttempt] = field(default_factory=list)
    successful_fix: _FakeFixAttempt | None = None
    resolution_time_minutes: float | None = 5.0


class _FakeHooksManager(HooksManager):
    """Stand-in for ``HooksManager`` with just the API hooks_tools touches.

    Subclasses the real ``HooksManager`` so the ``isinstance`` check inside
    ``_get_hooks_manager`` (which guards the DI short-circuit branch)
    accepts the fake. The parent ``__init__`` sets up ``_hooks`` and other
    state that ``list_hooks`` consumes; we override ``list_hooks`` to
    return the pre-seeded ``_hooks_by_type`` mapping.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str | None, Any]] = []
        self._hooks_by_type: dict[Any, list[dict[str, Any]]] = {}

    def list_hooks(self, hook_type=None):  # type: ignore[no-untyped-def, override]
        self.calls.append(("list_hooks", hook_type))
        return dict(self._hooks_by_type)


def _make_server_and_tools() -> tuple[_FakeMCP, dict[str, Any]]:
    """Build a fresh fake server, run registration, return tools dict."""
    from session_buddy.mcp.tools.session import hooks_tools as mod

    server = _FakeMCP()
    mod.register_hooks_tools(server)  # type: ignore[arg-type]
    return server, server.tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_hooks_manager(monkeypatch: pytest.MonkeyPatch):
    """Inject a fake ``HooksManager`` via DI so ``_get_hooks_manager`` returns it.

    The fake subclasses ``HooksManager`` so the ``isinstance`` guard inside
    ``_get_hooks_manager`` lets us exercise the DI short-circuit branch.
    """
    fake = _FakeHooksManager()

    from session_buddy.di.container import depends

    depends.set(type(fake), fake)  # type: ignore[arg-defined]

    # Patch the get_sync_typed so DI lookup returns our fake. We patch the
    # symbol on the module-level binding that ``_get_hooks_manager`` imports.
    monkeypatch.setattr(
        "session_buddy.mcp.tools.session.hooks_tools.get_sync_typed",
        lambda _t: fake,
    )
    return fake


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth gate is a no-op when ``SESSION_BUDDY_SECRET`` is unset."""
    monkeypatch.delenv("SESSION_BUDDY_SECRET", raising=False)
    try:
        from session_buddy.mcp.auth import _reset_core_config

        _reset_core_config()
    except (ImportError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# Registration smoke tests
# ---------------------------------------------------------------------------


def test_register_attaches_expected_tools() -> None:
    """Registering exposes exactly six tools and the help prompt."""
    _server, tools = _make_server_and_tools()
    assert set(tools) == {
        "list_hooks",
        "query_similar_errors",
        "record_fix_success",
        "get_causal_chain",
        "enable_hook",
        "disable_hook",
    }


def test_register_attaches_help_prompt() -> None:
    """The hooks_help prompt registers and returns Markdown docs."""
    from session_buddy.mcp.tools.session import hooks_tools as mod

    server = _FakeMCP()
    mod.register_hooks_tools(server)  # type: ignore[arg-type]
    assert "hooks_help" in server.prompts
    help_text = server.prompts["hooks_help"]()
    assert isinstance(help_text, str)
    assert "Hooks and Causal Chains" in help_text
    assert "list_hooks" in help_text
    assert "query_similar_errors" in help_text


def test_tools_are_coroutines() -> None:
    """All registered tools are coroutine functions so FastMCP can await them."""
    import inspect

    _server, tools = _make_server_and_tools()
    for name in (
        "list_hooks",
        "query_similar_errors",
        "record_fix_success",
        "get_causal_chain",
        "enable_hook",
        "disable_hook",
    ):
        assert inspect.iscoroutinefunction(tools[name]), (
            f"{name} must be a coroutine function"
        )


# ---------------------------------------------------------------------------
# list_hooks tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_hooks_no_filter_returns_all(fresh_hooks_manager) -> None:
    """When ``hook_type`` is None, manager.list_hooks is called with None."""
    from session_buddy.core.hooks import HookType

    fake = fresh_hooks_manager
    fake._hooks_by_type = {
        HookType.PRE_CHECKPOINT: [{"name": "a"}],
        HookType.POST_FILE_EDIT: [{"name": "b"}, {"name": "c"}],
    }

    _server, tools = _make_server_and_tools()
    result = await tools["list_hooks"]()

    assert result["success"] is True
    assert result["total_hooks"] == 3
    # HookType is a StrEnum — dict keys stringify to their value (e.g.
    # ``"pre_checkpoint"``). ``hooks_by_type`` therefore carries the bare
    # enum value as key, not the qualified ``HookType.X`` repr.
    assert result["hooks_by_type"]["pre_checkpoint"] == [{"name": "a"}]
    assert result["hooks_by_type"]["post_file_edit"] == [
        {"name": "b"},
        {"name": "c"},
    ]
    assert fake.calls == [("list_hooks", None)]


@pytest.mark.asyncio
async def test_list_hooks_with_hook_type_filter(fresh_hooks_manager) -> None:
    """A valid ``hook_type`` string is converted to HookType before forwarding."""
    from session_buddy.core.hooks import HookType

    fake = fresh_hooks_manager
    fake._hooks_by_type = {HookType.POST_FILE_EDIT: [{"name": "x"}]}

    _server, tools = _make_server_and_tools()
    result = await tools["list_hooks"](hook_type="post_file_edit")

    assert result["success"] is True
    assert result["total_hooks"] == 1
    assert fake.calls == [("list_hooks", HookType.POST_FILE_EDIT)]


@pytest.mark.asyncio
async def test_list_hooks_invalid_hook_type_returns_error(
    fresh_hooks_manager,
) -> None:
    """Invalid hook_type string short-circuits with a structured error."""
    fake = fresh_hooks_manager
    _server, tools = _make_server_and_tools()

    result = await tools["list_hooks"](hook_type="not_a_real_type")

    assert result["success"] is False
    assert "Invalid hook type" in result["error"]
    assert result["total_hooks"] == 0
    assert result["hooks_by_type"] == {}
    # Manager.list_hooks was NOT called — the validation gate short-circuits.
    assert fake.calls == []


# ---------------------------------------------------------------------------
# query_similar_errors tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_similar_errors_empty_returns_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When tracker finds nothing, the tool returns ``found_similar=False``."""
    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        query_similar_failures=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    result = await tools["query_similar_errors"](
        error_message="some new error", limit=3
    )

    tracker.initialize.assert_awaited_once()
    tracker.query_similar_failures.assert_awaited_once_with(
        current_error="some new error", limit=3
    )
    assert result["found_similar"] is False
    assert result["count"] == 0
    assert result["similar_errors"] == []
    assert "No similar errors found" in result["suggestion"]


@pytest.mark.asyncio
async def test_query_similar_errors_with_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful matches are formatted with similarity %, resolution time, code."""
    # Use similarity values whose ``:.1%`` formatting is stable across rounding
    # modes (no x.x5 boundaries) so the test is reproducible on every Python.
    similar_failures = [
        {
            "error_message": "ImportError: cannot import foo",
            "similarity": 0.88,
            "resolution_time_minutes": 7,
            "successful_fix": {
                "action_taken": "added missing import",
                "code_changes": "import foo  # added",
            },
        },
        {
            "error_message": "ModuleNotFoundError: bar",
            "similarity": 0.642,
            "resolution_time_minutes": 3,
            "successful_fix": {
                "action_taken": "pip install bar",
                "code_changes": None,
            },
        },
    ]
    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        query_similar_failures=AsyncMock(return_value=similar_failures),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    result = await tools["query_similar_errors"](error_message="x", limit=5)

    assert result["found_similar"] is True
    assert result["count"] == 2
    assert len(result["similar_errors"]) == 2

    first = result["similar_errors"][0]
    assert first["error_message"] == "ImportError: cannot import foo"
    assert first["similarity"] == "88.0%"
    assert first["resolution_time_minutes"] == 7
    assert first["suggested_fix"] == "added missing import"
    assert first["code_changes"] == "import foo  # added"

    second = result["similar_errors"][1]
    assert second["similarity"] == "64.2%"
    assert second["code_changes"] is None
    assert "2 similar error" in result["suggestion"]


# ---------------------------------------------------------------------------
# record_fix_success tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_fix_success_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Records an error event and a fix attempt, returning fix/error ids."""
    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        record_error_event=AsyncMock(return_value="err-abc"),
        record_fix_attempt=AsyncMock(return_value="fix-xyz"),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    result = await tools["record_fix_success"](
        error_message="AttributeError: foo",
        action_taken="added missing attribute",
        code_changes="self.foo = None  # default",
        error_type="AttributeError",
    )

    tracker.initialize.assert_awaited_once()
    tracker.record_error_event.assert_awaited_once()
    call_kwargs = tracker.record_error_event.await_args.kwargs
    assert call_kwargs["error"] == "AttributeError: foo"
    assert call_kwargs["context"] == {
        "error_type": "AttributeError",
        "recorded_retrospectively": True,
    }
    assert call_kwargs["session_id"] == "manual"

    tracker.record_fix_attempt.assert_awaited_once_with(
        error_id="err-abc",
        action_taken="added missing attribute",
        code_changes="self.foo = None  # default",
        successful=True,
    )

    assert result["success"] is True
    assert result["fix_id"] == "fix-xyz"
    assert result["error_id"] == "err-abc"
    assert "recorded successfully" in result["message"]


@pytest.mark.asyncio
async def test_record_fix_success_without_code_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """code_changes is optional and forwarded as ``None``."""
    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        record_error_event=AsyncMock(return_value="err-1"),
        record_fix_attempt=AsyncMock(return_value="fix-1"),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    result = await tools["record_fix_success"](
        error_message="oops",
        action_taken="restarted process",
    )

    call_kwargs = tracker.record_fix_attempt.await_args.kwargs
    assert call_kwargs["code_changes"] is None
    assert result["success"] is True


@pytest.mark.asyncio
async def test_record_fix_success_default_error_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``error_type`` argument defaults to ``"unknown"``."""
    captured: dict[str, Any] = {}

    async def record_error_event(*, error, context, session_id):
        captured["context"] = context
        return "err-1"

    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        record_error_event=record_error_event,
        record_fix_attempt=AsyncMock(return_value="fix-1"),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    await tools["record_fix_success"](error_message="x", action_taken="y")

    assert captured["context"]["error_type"] == "unknown"


# ---------------------------------------------------------------------------
# get_causal_chain tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_causal_chain_missing_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``get_causal_chain`` returns None the tool returns a 404-like error."""
    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        get_causal_chain=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    result = await tools["get_causal_chain"](chain_id="missing-chain")

    assert result["success"] is False
    assert "missing-chain" in result["error"]
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_causal_chain_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A populated CausalChain is serialized into a dict envelope."""
    error = _FakeErrorEvent(
        id="err-1",
        error_message="boom",
        error_type="ValueError",
        context={"file": "main.py"},
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
        session_id="sess-1",
    )
    attempt = _FakeFixAttempt(
        id="fix-1",
        error_id="err-1",
        action_taken="replaced value",
        code_changes="x = 0",
        successful=False,
        timestamp=datetime(2026, 1, 1, 12, 5, 0),
    )
    successful = _FakeFixAttempt(
        id="fix-2",
        error_id="err-1",
        action_taken="reverted last commit",
        code_changes="git revert HEAD",
        successful=True,
        timestamp=datetime(2026, 1, 1, 12, 10, 0),
    )
    chain = _FakeCausalChain(
        id="chain-1",
        error_event=error,
        fix_attempts=[attempt, successful],
        successful_fix=successful,
        resolution_time_minutes=10.0,
    )

    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        get_causal_chain=AsyncMock(return_value=chain),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    result = await tools["get_causal_chain"](chain_id="chain-1")

    assert result["success"] is True
    assert result["chain"]["id"] == "chain-1"
    assert result["chain"]["error_event"]["id"] == "err-1"
    assert result["chain"]["error_event"]["error_message"] == "boom"
    assert result["chain"]["error_event"]["context"] == {"file": "main.py"}
    assert result["chain"]["error_event"]["timestamp"] == "2026-01-01T12:00:00"
    assert result["chain"]["error_event"]["session_id"] == "sess-1"
    assert len(result["chain"]["fix_attempts"]) == 2
    assert result["chain"]["fix_attempts"][0]["successful"] is False
    assert result["chain"]["fix_attempts"][1]["action_taken"] == "reverted last commit"
    assert result["chain"]["successful_fix"]["id"] == "fix-2"
    assert result["chain"]["successful_fix"]["code_changes"] == "git revert HEAD"
    assert result["chain"]["resolution_time_minutes"] == 10.0


@pytest.mark.asyncio
async def test_get_causal_chain_without_successful_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``successful_fix`` is None the field serializes as None."""
    chain = _FakeCausalChain(
        id="chain-2",
        successful_fix=None,
        fix_attempts=[],
    )
    tracker = SimpleNamespace(
        initialize=AsyncMock(),
        get_causal_chain=AsyncMock(return_value=chain),
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        lambda logger=None: tracker,
    )

    _server, tools = _make_server_and_tools()
    result = await tools["get_causal_chain"](chain_id="chain-2")

    assert result["success"] is True
    assert result["chain"]["successful_fix"] is None
    assert result["chain"]["fix_attempts"] == []


# ---------------------------------------------------------------------------
# enable_hook / disable_hook tools (placeholder behavior)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_hook_returns_not_implemented() -> None:
    """enable_hook is a stub that returns a structured not-implemented error."""
    _server, tools = _make_server_and_tools()
    result = await tools["enable_hook"](hook_name="auto_format_python", hook_type="post_file_edit")

    assert result["success"] is False
    assert "not yet implemented" in result["error"]
    assert "future update" in result["message"]


@pytest.mark.asyncio
async def test_disable_hook_returns_not_implemented() -> None:
    """disable_hook mirrors enable_hook's placeholder contract."""
    _server, tools = _make_server_and_tools()
    result = await tools["disable_hook"](hook_name="auto_format_python", hook_type="post_file_edit")

    assert result["success"] is False
    assert "not yet implemented" in result["error"]
    assert "future update" in result["message"]


# ---------------------------------------------------------------------------
# _get_hooks_manager helper
# ---------------------------------------------------------------------------


def test_get_hooks_manager_returns_di_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """When DI returns a ``HooksManager``, the helper short-circuits and returns it."""
    from session_buddy.core.hooks import HooksManager

    fake = MagicMock(spec=HooksManager)
    monkeypatch.setattr(
        "session_buddy.mcp.tools.session.hooks_tools.get_sync_typed",
        lambda _t: fake,
    )

    from session_buddy.mcp.tools.session import hooks_tools as mod

    assert mod._get_hooks_manager() is fake  # noqa: SLF001


def test_get_hooks_manager_falls_back_when_di_returns_wrong_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If DI returns a non-HooksManager, the helper builds a fresh one."""
    from session_buddy.core.hooks import HooksManager

    monkeypatch.setattr(
        "session_buddy.mcp.tools.session.hooks_tools.get_sync_typed",
        lambda _t: SimpleNamespace(name="decoy"),
    )
    monkeypatch.setattr(
        "session_buddy.mcp.tools.session.hooks_tools.get_sync_typed",
        lambda _t: SimpleNamespace(name="decoy"),
    )

    from session_buddy.mcp.tools.session import hooks_tools as mod

    manager = mod._get_hooks_manager()  # noqa: SLF001
    assert isinstance(manager, HooksManager)


def test_get_hooks_manager_handles_di_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DI exception is swallowed by ``suppress`` and a fresh manager is built."""
    from session_buddy.core.hooks import HooksManager

    def _explode(_t):
        msg = "di boom"
        raise KeyError(msg)

    monkeypatch.setattr(
        "session_buddy.mcp.tools.session.hooks_tools.get_sync_typed",
        _explode,
    )

    from session_buddy.mcp.tools.session import hooks_tools as mod

    manager = mod._get_hooks_manager()  # noqa: SLF001
    assert isinstance(manager, HooksManager)


def test_get_hooks_manager_handles_code_formatter_di_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the ``CodeFormatter`` DI lookup fails, the manager is still built."""
    from session_buddy.core.hooks import HooksManager

    # First lookup (HooksManager) returns a fake HooksManager so we drop
    # into the formatter branch. Second lookup (CodeFormatter) raises to
    # exercise the ``except (ImportError, AttributeError, RuntimeError, KeyError)``.
    from session_buddy.mcp.tools.session import hooks_tools as mod

    fake_manager = MagicMock(spec=HooksManager)

    def _dispatch(t):
        if t is HooksManager:
            return fake_manager
        msg = "formatter boom"
        raise AttributeError(msg)

    monkeypatch.setattr(mod, "get_sync_typed", _dispatch)

    manager = mod._get_hooks_manager()  # noqa: SLF001
    assert manager is fake_manager


def test_get_hooks_manager_handles_non_formatter_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the formatter lookup returns a non-CodeFormatter, ``code_formatter`` is None.

    For this branch to fire, the HooksManager DI lookup must fall through to
    the fallback path (line 37+). We make the HooksManager lookup raise so
    the ``suppress(Exception)`` at line 30 swallows it, then have the
    CodeFormatter lookup return a decoy object — exercising line 39-40.
    """
    from session_buddy.core.hooks import CodeFormatter, HooksManager

    from session_buddy.mcp.tools.session import hooks_tools as mod

    def _dispatch(t):
        if t is HooksManager:
            msg = "hooks manager boom"
            raise KeyError(msg)
        if t is CodeFormatter:
            return SimpleNamespace(name="decoy-formatter")
        msg = "missing"
        raise KeyError(msg)

    monkeypatch.setattr(mod, "get_sync_typed", _dispatch)

    manager = mod._get_hooks_manager()  # noqa: SLF001
    # The non-CodeFormatter return forces ``code_formatter = None``; the
    # manager is still a real HooksManager instance.
    assert isinstance(manager, HooksManager)
    assert manager is not None


# ---------------------------------------------------------------------------
# Ensure tool helpers don't crash when logger is missing
# ---------------------------------------------------------------------------


def test_logger_helper_returns_real_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tracker is constructed with whatever ``_get_logger`` returns.

    The test asserts the factory receives the value returned by
    ``_get_logger`` (whatever that is), proving the call site wires the
    logger correctly. We do not require the underlying value to be a real
    ``logging.Logger`` instance — production returns one but tests can stub.
    """
    seen: dict[str, Any] = {}
    sentinel_logger = object()  # any object — proves it's forwarded verbatim

    def _get_logger():
        return sentinel_logger

    def _factory(logger=None):
        seen["logger"] = logger
        return SimpleNamespace(
            initialize=AsyncMock(),
            query_similar_failures=AsyncMock(return_value=[]),
        )

    monkeypatch.setattr(
        "session_buddy.utils.error_management._get_logger",
        _get_logger,
    )
    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        _factory,
    )

    _server, tools = _make_server_and_tools()
    import asyncio

    asyncio.run(tools["query_similar_errors"](error_message="x"))
    assert seen["logger"] is sentinel_logger


def test_logger_helper_falls_back_to_real_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``_get_logger`` is not patched, the tracker receives a real ``Logger``."""
    seen: dict[str, Any] = {}

    def _factory(logger=None):
        seen["logger"] = logger
        return SimpleNamespace(
            initialize=AsyncMock(),
            query_similar_failures=AsyncMock(return_value=[]),
        )

    monkeypatch.setattr(
        "session_buddy.core.causal_chains.CausalChainTracker",
        _factory,
    )
    # DO NOT patch ``_get_logger`` — the production ``utils.error_management``
    # module is allowed to return a real ``logging.Logger`` instance.

    _server, tools = _make_server_and_tools()
    import asyncio

    asyncio.run(tools["query_similar_errors"](error_message="x"))
    assert seen["logger"] is not None
    assert isinstance(seen["logger"], logging.Logger)