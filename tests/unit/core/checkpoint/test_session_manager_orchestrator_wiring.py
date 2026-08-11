"""Verify SessionLifecycleManager routes checkpoint through orchestrator.

Task 8 wires CheckpointOrchestrator into SessionLifecycleManager so
``perform_git_checkpoint`` is reached only after a safe capture-then-commit
cycle. Lite mode (``ModeConfig.enable_auto_checkpoint=False``) bypasses
the orchestrator entirely. Standard mode captures a defensive snapshot
(advisory) and always proceeds to the legacy commit per spec Constraint
#1 (end-of-task is mandatory). The orchestrator is advisory only — the
actual commit authority is the existing Stop hook path.

Security: ``current_dir`` is validated before being passed to the
orchestrator's subprocess surface. If validation fails, the orchestrator
is skipped and the legacy commit still runs.

NOTE: The brief uses ``SessionManager`` (the natural short-form name) but
the actual class is ``SessionLifecycleManager`` in this codebase — the
test imports the real class.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.session_manager import SessionLifecycleManager


@pytest.mark.unit
async def test_lite_mode_does_not_construct_any_checkpoint_collaborator(
    tmp_path: Path,
) -> None:
    """Lite mode bypasses the orchestrator — verify by spying on all 5 classes.

    Regression guard (Finding I-3): the legacy indirect check
    (``perform_git_checkpoint.assert_awaited_once()``) would still pass
    if a future refactor constructed the orchestrator, ran it, and
    discarded the result. Subprocess-bound collaborators are expensive
    — they fork git, stat working trees, and instantiate
    ``LockfileSignalSource`` — and lite mode MUST pay none of that cost.

    The 5 classes (per the multi-agent review):
      * ``SubagentDetector``
      * ``SnapshotMechanism``
      * ``WorkingTreeInspector``
      * ``CheckpointPolicy``
      * ``CheckpointOrchestrator``
    """
    from session_buddy.modes import LiteMode

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)  # bypass __init__
    real._mode_config = LiteMode().get_config()  # enable_auto_checkpoint=False
    real.perform_git_checkpoint = AsyncMock(return_value=["legacy-output"])
    real.logger = MagicMock()

    with (
        patch("session_buddy.checkpoint.SubagentDetector") as detector_cls,
        patch("session_buddy.checkpoint.SnapshotMechanism") as snapshot_cls,
        patch("session_buddy.checkpoint.WorkingTreeInspector") as inspector_cls,
        patch("session_buddy.checkpoint.CheckpointPolicy") as policy_cls,
        patch("session_buddy.checkpoint.CheckpointOrchestrator") as orchestrator_cls,
    ):
        result = await real._checkpoint_with_safety_capture(
            phase="end_of_task", current_dir=tmp_path, quality_score=80,
        )

    # None of the 5 collaborators may have been instantiated in lite mode.
    detector_cls.assert_not_called()
    snapshot_cls.assert_not_called()
    inspector_cls.assert_not_called()
    policy_cls.assert_not_called()
    orchestrator_cls.assert_not_called()

    # Legacy path still runs — the user's end-of-task commit must not be
    # blocked by lite-mode bypass.
    real.perform_git_checkpoint.assert_awaited_once()
    assert result == ["legacy-output"]


@pytest.mark.unit
async def test_standard_mode_does_construct_checkpoint_orchestrator(
    tmp_path: Path,
) -> None:
    """Positive control: standard mode DOES instantiate the orchestrator.

    Pins the strong-form spies so the lite-mode test cannot pass
    vacuously (e.g. via a typo in the patch target that masked the
    collaborator at import time).
    """
    from session_buddy.modes import StandardMode

    def _fake_orchestrator(*_a, **_kw):
        # run_checkpoint must be an AsyncMock because the caller awaits it.
        m = MagicMock()
        m.run_checkpoint = AsyncMock(
            return_value=MagicMock(
                fired=True,
                snapshot_id=None,
                session_buddy_id=None,
                decision_reason="ok",
            ),
        )
        return m

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)
    real._mode_config = StandardMode().get_config()  # enable_auto_checkpoint=True
    real.perform_git_checkpoint = AsyncMock(return_value=["📦 git commit abc123"])
    real.logger = MagicMock()

    with (
        patch("session_buddy.checkpoint.SubagentDetector") as detector_cls,
        patch("session_buddy.checkpoint.SnapshotMechanism") as snapshot_cls,
        patch("session_buddy.checkpoint.WorkingTreeInspector") as inspector_cls,
        patch("session_buddy.checkpoint.CheckpointPolicy") as policy_cls,
        patch(
            "session_buddy.checkpoint.CheckpointOrchestrator",
            side_effect=_fake_orchestrator,
        ) as orchestrator_cls,
    ):
        await real._checkpoint_with_safety_capture(
            phase="end_of_task", current_dir=tmp_path, quality_score=80,
        )

    # Standard mode constructs the full orchestrator pipeline.
    detector_cls.assert_called_once()
    snapshot_cls.assert_called_once()
    inspector_cls.assert_called_once()
    policy_cls.assert_called_once()
    orchestrator_cls.assert_called_once()


# --- Finding C-7: module-level validate_orchestrator_working_dir ----------------
#
# Before the fix, ``_validate_orchestrator_path`` was a method on
# ``SessionLifecycleManager``. The MCP lifespan startup could not call it
# without instantiating a throwaway manager. The fix extracts the body to a
# module-level function so both call sites share one definition — drift
# between the two becomes impossible.


@pytest.mark.unit
def test_validate_orchestrator_working_dir_accepts_valid_dir(tmp_path: Path) -> None:
    """A real existing directory is accepted and returned resolved."""
    from session_buddy.core.session_manager import validate_orchestrator_working_dir

    result = validate_orchestrator_working_dir(tmp_path)
    assert result is not None
    assert isinstance(result, Path)
    assert result == tmp_path.resolve()


@pytest.mark.unit
def test_validate_orchestrator_working_dir_rejects_nonexistent() -> None:
    """A non-existent path returns None — no orchestrator should be built."""
    from session_buddy.core.session_manager import validate_orchestrator_working_dir

    bogus = Path("/nonexistent/path/xyz/abc-123-no-such-dir")
    assert validate_orchestrator_working_dir(bogus) is None


@pytest.mark.unit
def test_validate_orchestrator_working_dir_rejects_file_not_dir(tmp_path: Path) -> None:
    """A path that exists but is a regular file returns None."""
    from session_buddy.core.session_manager import validate_orchestrator_working_dir

    regular_file = tmp_path / "just_a_file.txt"
    regular_file.write_text("not a directory")
    assert validate_orchestrator_working_dir(regular_file) is None


@pytest.mark.unit
async def test_standard_mode_wraps_orchestrator(tmp_path: Path) -> None:
    """Standard mode routes through orchestrator; legacy output preserved."""
    from session_buddy.modes import StandardMode

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)
    real._mode_config = StandardMode().get_config()  # enable_auto_checkpoint=True
    real.perform_git_checkpoint = AsyncMock(return_value=["📦 git commit abc123"])
    real.logger = MagicMock()

    result = await real._checkpoint_with_safety_capture(
        phase="end_of_task", current_dir=tmp_path, quality_score=80,
    )

    real.perform_git_checkpoint.assert_awaited_once()
    # Legacy output preserved
    assert "📦 git commit abc123" in "\n".join(result)
    # Plus decision summary appended
    assert any("checkpoint_orchestrator_decision" in line for line in result)


@pytest.mark.unit
async def test_invalid_path_skips_orchestrator_but_keeps_commit(
    tmp_path: Path,
) -> None:
    """Security: invalid ``current_dir`` skips orchestrator, legacy commit runs.

    The orchestrator instantiates subprocess-bound components
    (SubagentDetector, WorkingTreeInspector, SnapshotMechanism). Passing
    an unvalidated path risks feeding hostile filesystem state into those
    surfaces. The wrapper must validate ``current_dir`` first and fall
    through to the legacy commit on any failure — never block the user's
    end-of-task commit on a path-validation edge case.
    """
    from session_buddy.modes import StandardMode

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)
    real._mode_config = StandardMode().get_config()  # enable_auto_checkpoint=True
    real.perform_git_checkpoint = AsyncMock(return_value=["📦 git commit abc123"])
    real.logger = MagicMock()

    # Path that does not exist on disk — Path.resolve(strict=True) raises.
    bad_path = tmp_path / "does_not_exist" / "nested"

    # The CheckpointOrchestrator / SubagentDetector / etc. classes must
    # NOT be instantiated when validation fails. We patch the module
    # imports inside ``session_buddy.checkpoint`` and assert none of
    # them were touched.
    with (
        patch("session_buddy.checkpoint.SubagentDetector") as detector_cls,
        patch("session_buddy.checkpoint.WorkingTreeInspector") as inspector_cls,
        patch("session_buddy.checkpoint.SnapshotMechanism") as snapshot_cls,
        patch("session_buddy.checkpoint.CheckpointPolicy") as policy_cls,
        patch("session_buddy.checkpoint.CheckpointOrchestrator") as orchestrator_cls,
    ):
        result = await real._checkpoint_with_safety_capture(
            phase="end_of_task", current_dir=bad_path, quality_score=80,
        )

    # Orchestrator components must not have been instantiated.
    detector_cls.assert_not_called()
    inspector_cls.assert_not_called()
    snapshot_cls.assert_not_called()
    policy_cls.assert_not_called()
    orchestrator_cls.assert_not_called()

    # Legacy commit must still run (we don't break end-of-task on edge case).
    real.perform_git_checkpoint.assert_awaited_once()

    # Output includes legacy commit line and a skipped indicator.
    joined = "\n".join(result)
    assert "📦 git commit abc123" in joined
    assert "safety_capture_skipped" in joined
    assert "reason=invalid_path" in joined


# --- Finding I-4: validated_dir must propagate to orchestrator components --------
#
# Before the fix, ``current_dir`` was passed verbatim to
# SubagentDetector / SnapshotMechanism / WorkingTreeInspector even when
# the validation helper had resolved symlinks and returned a different
# (canonical) path. The orchestrator then watched the wrong ``.session-buddy``
# lockfile and inspected the wrong working tree. The fix threads
# ``target_dir = validated_dir`` into every constructor call.


@pytest.mark.unit
async def test_symlinked_dir_passes_resolved_path_to_orchestrator_components(
    tmp_path: Path,
) -> None:
    """Symlinked ``current_dir`` MUST be resolved before reaching the orchestrator.

    Strategy: spy on every orchestrator component class, drive
    ``_checkpoint_with_safety_capture`` with a symlink, and assert the
    constructor was invoked with the resolved (real) directory — not
    the symlink path. The legacy ``perform_git_checkpoint`` is mocked so
    we don't need a real git repo.
    """
    from session_buddy.modes import StandardMode

    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_path = tmp_path / "link_to_real"
    try:
        link_path.symlink_to(real_dir)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unsupported on this filesystem: {exc}")

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)
    real._mode_config = StandardMode().get_config()
    real.perform_git_checkpoint = AsyncMock(return_value=["📦 legacy ok"])
    real.logger = MagicMock()

    captured: dict[str, Path] = {}

    def _record_subagent(_wd, signal_src):
        captured["detector"] = _wd
        return MagicMock()

    def _record_snapshot(_wd):
        captured["snapshot"] = _wd
        return MagicMock()

    def _record_inspector(_wd):
        captured["inspector"] = _wd
        return MagicMock()

    def _record_policy(*, midpoint_enabled, midpoint_criteria, subagent_detector, working_tree):
        return MagicMock()

    def _record_orch(*, working_dir, policy, snapshot, subagent_detector, forward_to):
        captured["orchestrator"] = working_dir
        # Return a mock whose run_checkpoint returns a fire=True result so
        # the function under test proceeds cleanly.
        m = MagicMock()
        m.run_checkpoint = AsyncMock(
            return_value=MagicMock(fired=True, snapshot_id=None,
                                   session_buddy_id=None,
                                   decision_reason="ok"),
        )
        return m

    with (
        patch("session_buddy.checkpoint.SubagentDetector", side_effect=_record_subagent) as detector_cls,
        patch("session_buddy.checkpoint.SnapshotMechanism", side_effect=_record_snapshot) as snapshot_cls,
        patch("session_buddy.checkpoint.WorkingTreeInspector", side_effect=_record_inspector) as inspector_cls,
        patch("session_buddy.checkpoint.CheckpointPolicy", side_effect=_record_policy),
        patch("session_buddy.checkpoint.CheckpointOrchestrator", side_effect=_record_orch),
    ):
        await real._checkpoint_with_safety_capture(
            phase="end_of_task", current_dir=link_path, quality_score=80,
        )

    # All four components MUST see the resolved (real) directory, not
    # the symlink. ``Path.resolve`` may or may not strip the ``link_to_real``
    # segment depending on platform — the contract is that the returned
    # path resolves to ``real_dir`` and does NOT equal the symlink path.
    expected = real_dir.resolve()
    assert captured["detector"] == expected
    assert captured["snapshot"] == expected
    assert captured["inspector"] == expected
    assert captured["orchestrator"] == expected
    # Belt and suspenders: the spy classes were definitely called.
    detector_cls.assert_called_once()
    snapshot_cls.assert_called_once()
    inspector_cls.assert_called_once()


# --- Finding I-2: end_session MUST route pending-drain via the shared helper ------
#
# Before the fix, end_session loaded each marker, logged, and deleted it
# without ever firing an orchestrator. The fix imports the shared
# ``consume_pending_marker`` helper (extracted to
# ``session_buddy.checkpoint.pending``) and threads every pending marker
# through it. The ``_consume_pending`` helper inside the MCP server
# lifespan loop is the other half — both call sites MUST share one
# helper so they cannot drift. ``test_consume_pending_marker_helper_*``
# in ``tests/unit/mcp/test_auto_checkpoint_timer.py`` covers the helper.
# Here we pin the *wiring shape inside end_session*: the helper must be
# imported and called, not the legacy ``load_pending`` + ``consume_pending``
# pair. A regression that reverts end_session to the old delete-only
# behavior will be caught by this assertion (the helper would never be
# called, and the spy would observe the old symbols).


@pytest.mark.unit
def test_end_session_uses_consume_pending_marker_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-session source imports & awaits ``consume_pending_marker`` (not
    the legacy ``load_pending`` + ``consume_pending`` pair) for the drain.

    Static check is the right shape here: the drain block is inside a
    try/except with multiple import statements and a nested ``async def``
    builder, so a behavioural test would require either running the
    full post-drain code path or re-implementing the loop locally.
    AST/grep-driven regression guards the wiring instead.
    """
    import ast
    from pathlib import Path

    from session_buddy.core import session_manager as sm_mod

    src_path = sm_mod.__file__
    assert src_path is not None
    tree = ast.parse(Path(src_path).read_text())

    # Find end_session definition.
    end_session: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "end_session":
            end_session = node
            break
    assert end_session is not None, "end_session not found"

    # Collect names of all imported symbols inside end_session.
    imported_names: set[str] = set()
    for node in ast.walk(end_session):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add((alias.asname or alias.name).split(".")[0])

    # MUST import the shared helper.
    assert "consume_pending_marker" in imported_names, (
        "end_session must import the shared ``consume_pending_marker`` "
        "helper for the pending-drain path (Finding I-2)"
    )
    # MUST NOT import the legacy delete-only pair.
    assert "load_pending" not in imported_names, (
        "end_session must NOT import ``load_pending`` directly — the "
        "shared helper handles loading. Re-importing it here would be "
        "the regression we are guarding against."
    )
    assert "consume_pending" not in imported_names, (
        "end_session must NOT import ``consume_pending`` directly — "
        "the shared helper handles marker deletion AFTER the orchestrator."
    )

    # end_session MUST await consume_pending_marker (it's async).
    awaited = [
        node for node in ast.walk(end_session)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "consume_pending_marker"
    ]
    assert awaited, (
        "end_session must ``await consume_pending_marker(...)`` for "
        "every pending marker (not just record-and-delete)"
    )
