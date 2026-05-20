from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest


def _load_hooks_module():
    for name in (
        "session_buddy.core",
        "session_buddy.core.causal_chains",
        "session_buddy.core.intelligence",
        "session_buddy.core.workflow_metrics",
    ):
        sys.modules.pop(name, None)

    core_pkg = types.ModuleType("session_buddy.core")
    core_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["session_buddy.core"] = core_pkg

    causal_module = types.ModuleType("session_buddy.core.causal_chains")

    class CausalChainTracker:
        def __init__(self, logger=None):
            self.logger = logger

        async def initialize(self):
            return None

        async def record_error_event(self, **kwargs):
            return "chain-1"

    causal_module.CausalChainTracker = CausalChainTracker  # type: ignore[attr-defined]
    sys.modules["session_buddy.core.causal_chains"] = causal_module

    intelligence_module = types.ModuleType("session_buddy.core.intelligence")

    class IntelligenceEngine:
        def __init__(self):
            self.initialized = False
            self.checkpoints: list[dict[str, object]] = []

        async def initialize(self):
            self.initialized = True

        async def learn_from_checkpoint(self, checkpoint):
            self.checkpoints.append(checkpoint)
            return ["pattern-1"]

    intelligence_module.IntelligenceEngine = IntelligenceEngine  # type: ignore[attr-defined]
    sys.modules["session_buddy.core.intelligence"] = intelligence_module

    workflow_metrics_module = types.ModuleType("session_buddy.core.workflow_metrics")

    class Engine:
        def __init__(self):
            self.initialized = False
            self.calls = []

        async def initialize(self):
            self.initialized = True

        async def collect_session_metrics(self, **kwargs):
            self.calls.append(kwargs)

    workflow_metrics_module.Engine = Engine  # type: ignore[attr-defined]
    workflow_metrics_module.get_workflow_metrics_engine = lambda: Engine()  # type: ignore[attr-defined]
    sys.modules["session_buddy.core.workflow_metrics"] = workflow_metrics_module

    module_path = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "core"
        / "hooks.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_buddy.core.hooks",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hooks = _load_hooks_module()


def make_context(
    hook_type: hooks.HookType = hooks.HookType.POST_CHECKPOINT,
    *,
    checkpoint_data: dict[str, object] | None = None,
    error_info: dict[str, object] | None = None,
    file_path: str | None = None,
) -> hooks.HookContext:
    return hooks.HookContext(
        hook_type=hook_type,
        session_id="session-1",
        timestamp=hooks.datetime.now(hooks.UTC),
        metadata={},
        checkpoint_data=checkpoint_data,
        error_info=error_info,
        file_path=file_path,
    )


@pytest.mark.asyncio
async def test_register_and_list_hooks_cover_order_and_replacement() -> None:
    manager = hooks.HooksManager(logger=Mock())

    async def handler(ctx):
        return hooks.HookResult(success=True)

    await manager.register_hook(
        hooks.Hook(
            name="late",
            hook_type=hooks.HookType.POST_CHECKPOINT,
            priority=200,
            handler=handler,
        )
    )
    await manager.register_hook(
        hooks.Hook(
            name="early",
            hook_type=hooks.HookType.POST_CHECKPOINT,
            priority=10,
            handler=handler,
            metadata={"tag": "early"},
        )
    )
    await manager.register_hook(
        hooks.Hook(
            name="late",
            hook_type=hooks.HookType.POST_CHECKPOINT,
            priority=50,
            handler=handler,
            metadata={"tag": "replacement"},
        )
    )

    listed = manager.list_hooks(hooks.HookType.POST_CHECKPOINT)
    assert [hook["name"] for hook in listed[hooks.HookType.POST_CHECKPOINT]] == ["early", "late"]
    assert listed[hooks.HookType.POST_CHECKPOINT][1]["metadata"] == {"tag": "replacement"}

    all_hooks = manager.list_hooks()
    assert hooks.HookType.POST_CHECKPOINT in all_hooks


@pytest.mark.asyncio
async def test_execute_hooks_covers_success_disabled_and_failure_paths() -> None:
    manager = hooks.HooksManager(logger=Mock())
    call_order: list[str] = []

    async def success_handler(ctx):
        call_order.append("success")
        return hooks.HookResult(success=True, modified_context={"seen": True})

    async def failing_handler(ctx):
        call_order.append("failing")
        raise RuntimeError("boom")

    error_handler = AsyncMock(side_effect=RuntimeError("error-handler boom"))

    await manager.register_hook(
        hooks.Hook(
            name="success",
            hook_type=hooks.HookType.POST_CHECKPOINT,
            priority=10,
            handler=success_handler,
        )
    )
    await manager.register_hook(
        hooks.Hook(
            name="disabled",
            hook_type=hooks.HookType.POST_CHECKPOINT,
            priority=20,
            handler=success_handler,
            enabled=False,
        )
    )
    await manager.register_hook(
        hooks.Hook(
            name="failing",
            hook_type=hooks.HookType.POST_CHECKPOINT,
            priority=30,
            handler=failing_handler,
            error_handler=error_handler,
        )
    )

    context = make_context()
    results = await manager.execute_hooks(hooks.HookType.POST_CHECKPOINT, context)

    assert call_order == ["success", "failing"]
    assert len(results) == 2
    assert results[0].success is True
    assert results[0].execution_time_ms >= 0
    assert results[1].success is False
    assert results[1].error == "boom"
    assert context.metadata["seen"] is True
    error_handler.assert_awaited_once()

    empty = await manager.execute_hooks(hooks.HookType.POST_FILE_EDIT, context)
    assert empty == []


@pytest.mark.asyncio
async def test_initialize_covers_intelligence_failure_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingIntel:
        def __init__(self):
            pass

        async def initialize(self):
            raise RuntimeError("intel boom")

    monkeypatch.setattr(
        sys.modules["session_buddy.core.intelligence"],
        "IntelligenceEngine",
        FailingIntel,
    )

    manager = hooks.HooksManager(logger=Mock())
    await manager.initialize()

    assert manager._causal_tracker is not None
    assert manager._intelligence_engine is None
    assert hooks.HookType.POST_CHECKPOINT in manager._hooks
    assert hooks.HookType.PRE_CHECKPOINT in manager._hooks
    assert hooks.HookType.POST_ERROR in manager._hooks


@pytest.mark.asyncio
async def test_initialize_with_intelligence_success(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = hooks.HooksManager(logger=Mock())
    await manager.initialize()

    assert manager._causal_tracker is not None
    assert manager._intelligence_engine is not None


@pytest.mark.asyncio
async def test_builtin_handlers_cover_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    formatter = Mock()
    formatter.format_file = AsyncMock(return_value=False)
    manager = hooks.HooksManager(logger=Mock(), formatter=formatter)
    manager._causal_tracker = Mock()
    manager._causal_tracker.record_error_event = AsyncMock(return_value="chain-99")

    # Auto format
    assert (await manager._auto_format_handler(make_context(file_path=None))).success is True
    assert (await manager._auto_format_handler(make_context(file_path="note.txt"))).success is True
    assert (await manager._auto_format_handler(make_context(file_path="a.py"))).success is False
    formatter.format_file.assert_awaited_once()

    # Quality validation
    assert (await manager._quality_validation_handler(make_context(checkpoint_data={"quality_score": 55}))).success is False
    valid = await manager._quality_validation_handler(
        make_context(checkpoint_data={"quality_score": 75})
    )
    assert valid.success is True
    assert valid.modified_context == {"validated_quality": 75}

    # Pattern learning
    manager._intelligence_engine = None
    assert (await manager._pattern_learning_handler(make_context(checkpoint_data={"quality_score": 90}))).success is True
    intel = Mock()
    intel.learn_from_checkpoint = AsyncMock(side_effect=RuntimeError("learn boom"))
    manager._intelligence_engine = intel
    assert (await manager._pattern_learning_handler(make_context(checkpoint_data={"quality_score": 90}))).success is True

    # Causal chain
    assert (await manager._causal_chain_handler(make_context(error_info=None))).success is True
    chain = await manager._causal_chain_handler(
        make_context(error_info={"error_message": "oops", "context": {"step": 1}})
    )
    assert chain.success is True
    assert chain.causal_chain_id == "chain-99"
    manager._causal_tracker.record_error_event = AsyncMock(side_effect=RuntimeError("track boom"))
    failed_chain = await manager._causal_chain_handler(
        make_context(error_info={"error_message": "oops", "context": {"step": 1}})
    )
    assert failed_chain.success is False
    assert failed_chain.error == "track boom"

    # Workflow metrics
    engine = Mock()
    engine.initialize = AsyncMock(return_value=None)
    engine.collect_session_metrics = AsyncMock(return_value=None)
    monkeypatch.setattr(
        sys.modules["session_buddy.core.workflow_metrics"],
        "get_workflow_metrics_engine",
        lambda: engine,
    )
    ok = await manager._workflow_metrics_handler(
        make_context(checkpoint_data={"working_directory": "/tmp/demo"})
    )
    assert ok.success is True
    assert engine.collect_session_metrics.await_count == 1

    engine.initialize = AsyncMock(side_effect=RuntimeError("engine boom"))
    warning = await manager._workflow_metrics_handler(make_context())
    assert warning.success is True
