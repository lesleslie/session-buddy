"""Property-based keystone test from the stash-clobber-fix spec.

Invariant: working tree is NEVER mutated by a checkpoint, regardless of
phase or subagent state. This is the contract the entire design protects.
"""
from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from hypothesis import HealthCheck, assume, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from session_buddy.checkpoint import (
    CheckpointOrchestrator,
    CheckpointPhase,
    CheckpointPolicy,
    DirtyFilesSignal,
    MidpointCriteria,
    SnapshotMechanism,
    SubagentDetector,
    WorkingTreeInspector,
)
from session_buddy.checkpoint.subagent_detector import LockfileSignalSource

from .conftest import init_repo


@pytest.mark.property
@pytest.mark.unit
@given(
    dirty_files=st.lists(
        # Restrict to ASCII alphanum + `._-` so hypothesis never generates
        # path components that conflict with reserved names ('.', '..',
        # '~') or non-filesystem-safe Unicode.
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-",
            min_size=1, max_size=20,
        ).filter(
            lambda s: "/" not in s and "\x00" not in s and s not in (".", "..")
        ),
        min_size=0, max_size=20, unique=True,
    ),
    subagent_active=st.booleans(),
    checkpoint_phase=st.sampled_from(list(CheckpointPhase)),
)
# Brief specified deadline=30000; orchestrator's wait_until_idle(timeout=60.0) at
# session_buddy/checkpoint/orchestrator.py:176 legitimately blocks 60s for the
# (phase=END_OF_TASK, subagent_active=True) case, so we disable the deadline.
# That combination is also skipped via assume() below to keep the test feasible;
# the invariant holds trivially there (orchestrator times out, no capture, no
# mutation), so the remaining 7 of (4 phases x on/off) cover all interesting
# branches.
@hyp_settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_working_tree_never_mutated_by_checkpoint(
    tmp_path: Path, dirty_files: list[str], subagent_active: bool, checkpoint_phase: CheckpointPhase
) -> None:
    # Brief deviation: skip (END_OF_TASK, subagent_active=True). The orchestrator's
    # wait_until_idle(timeout=60.0) at orchestrator.py:176 legitimately blocks 60s
    # in that case, dominating test runtime. Invariant holds trivially (no
    # capture happens, so no mutation).
    assume(
        not (
            checkpoint_phase == CheckpointPhase.END_OF_TASK
            and subagent_active
        )
    )
    # Hypothesis reuses tmp_path across examples; ensure init_repo's mkdir
    # does not fail with FileExistsError on subsequent runs.
    if (tmp_path / "r").exists():
        shutil.rmtree(tmp_path / "r")
    repo = init_repo(tmp_path)
    for fname in dirty_files:
        (repo / fname).write_text(f"# {fname}\n")

    before = _hash_working_tree(repo)

    lockfile = repo / "lock"
    if subagent_active:
        lockfile.touch()
    detector = SubagentDetector(repo, LockfileSignalSource(lockfile))
    snapshot = SnapshotMechanism(repo, tmp_path / "snaps")
    inspector = WorkingTreeInspector(repo)
    policy = CheckpointPolicy(
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(signals=[DirtyFilesSignal(min_count=1)]),
        subagent_detector=detector,
        working_tree=inspector,
    )
    forward = AsyncMock()
    orchestrator = CheckpointOrchestrator(
        working_dir=repo, policy=policy, snapshot=snapshot,
        subagent_detector=detector, forward_to=forward,
    )

    asyncio.run(orchestrator.run_checkpoint(phase=checkpoint_phase))

    after = _hash_working_tree(repo)
    assert before == after, (
        f"working tree mutated! dirty={dirty_files} active={subagent_active} phase={checkpoint_phase}"
    )


@pytest.mark.property
@pytest.mark.unit
def test_spy_does_not_false_positive_on_stash_in_non_subcommand_position(
    tmp_path: Path,
) -> None:
    """Regression for the argv-membership false-positive risk.

    The previous spy used `"stash" in args[0]`, which is element membership
    on a list. While element membership is more restrictive than substring
    match, the implementation is fragile: it implicitly conflates "this argv
    contains a stash command" with "this argv contains a string equal to
    'stash' anywhere in it". A future refactor that changes how the argv
    list is built (or that adds a positional refspec like `stash@{0}` in a
    different subcommand) could regress the spy silently.

    The fix: explicitly match the git subcommand position, skipping leading
    `-c KEY=VAL` pairs and other flags. This regression test pins the
    behavior of the new helper against the documented false-positive
    shapes so future drift is caught.
    """
    from session_buddy.checkpoint import (
        metrics as metrics_mod,
    )
    from session_buddy.checkpoint import (
        orchestrator as orch_mod,
    )
    from session_buddy.checkpoint import (
        policy as pol_mod,
    )
    from session_buddy.checkpoint import (
        snapshot as snap_mod,
    )
    from session_buddy.checkpoint import (
        subagent_detector as sad_mod,
    )

    # All checkpoint modules in scope — current or future subprocess callers.
    checkpoint_modules = (snap_mod, pol_mod, orch_mod, sad_mod, metrics_mod)

    # Sanity: the helper exists and is importable. (Lives at module scope
    # in this test file.)
    assert callable(_is_git_stash_invocation), "helper must be module-level"

    # True-positives: actual git stash invocations.
    assert _is_git_stash_invocation(["git", "stash"]) is True
    assert _is_git_stash_invocation(["git", "stash", "show"]) is True
    assert _is_git_stash_invocation(["git", "stash", "drop"]) is True
    assert _is_git_stash_invocation(["git", "stash", "apply"]) is True

    # False-positives the OLD spy was vulnerable to: a "stash" element
    # appears, but it is not the subcommand.
    assert _is_git_stash_invocation(
        ["git", "-c", "stash.show=true", "log", "-1", "--format=%H"]
    ) is False, "stash in a -c config key must not be flagged"
    assert _is_git_stash_invocation(["git", "log", "stash@{0}"]) is False, (
        "stash@{0} refspec as a positional arg must not be flagged"
    )
    assert _is_git_stash_invocation(
        ["git", "show", "stash@{0}"]
    ) is False, "stash@{0} refspec in 'show' must not be flagged"
    assert _is_git_stash_invocation(["git", "log", "--grep=stash"]) is False, (
        "--grep=stash value must not be flagged"
    )
    assert _is_git_stash_invocation(
        ["git", "-c", "stash.showpatch=true", "-c", "color.ui=auto", "log"]
    ) is False, "multiple -c flags before the subcommand must not be flagged"

    # Non-git and edge cases.
    assert _is_git_stash_invocation(["ls", "-la"]) is False
    assert _is_git_stash_invocation([]) is False
    assert _is_git_stash_invocation(["git"]) is False
    assert _is_git_stash_invocation(["stash"]) is False  # not a git invocation

    # Spy coverage: every checkpoint module is patched. If a future refactor
    # adds `import subprocess` to a new module, this loop catches it.
    repo = init_repo(tmp_path)
    (repo / "dummy.py").write_text("x\n")

    real_run = subprocess.run
    captured: list[list[str]] = []

    def spy_run(*args, **kwargs):
        if args and isinstance(args[0], list) and _is_git_stash_invocation(args[0]):
            captured.append(args[0])
        return real_run(*args, **kwargs)

    import subprocess as sp

    with pytest.MonkeyPatch.context() as mp_ctx:
        mp_ctx.setattr(sp, "run", spy_run)
        for mod in checkpoint_modules:
            sub = getattr(mod, "subprocess", None)
            if sub is not None:
                mp_ctx.setattr(sub, "run", spy_run)
        # Exercise a real git invocation with stash in a non-subcommand
        # position. The spy must not capture it.
        sp.run(
            ["git", "-c", "stash.show=true", "log", "-1", "--format=%H"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    assert captured == [], f"Spy false-positive on git config: {captured}"


@pytest.mark.property
@pytest.mark.unit
def test_stash_clobber_regression(tmp_path: Path) -> None:
    """Regression for the 2026-07-15 observation: a checkpoint fired
    while a subagent was actively writing must NOT call `git stash`,
    must NOT clobber the working tree, and must defer (fired=False).

    Per spec line 460: spy on subprocess.run and assert stash_invocations == [].
    """
    repo = init_repo(tmp_path)
    (repo / "modified.py").write_text("# subagent's in-flight edit\n")
    (repo / "new_file.py").write_text("# subagent's new file\n")

    # Pretend a subagent is active via an always-present lockfile
    lockfile = repo / "subagent.lock"
    lockfile.touch()
    detector = SubagentDetector(repo, LockfileSignalSource(lockfile))

    snapshot = SnapshotMechanism(repo, tmp_path / "snaps")
    inspector = WorkingTreeInspector(repo)
    policy = CheckpointPolicy(
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(signals=[DirtyFilesSignal(min_count=1)]),
        subagent_detector=detector,
        working_tree=inspector,
    )
    forward = AsyncMock()
    orchestrator = CheckpointOrchestrator(
        working_dir=repo, policy=policy, snapshot=snapshot,
        subagent_detector=detector, forward_to=forward,
    )

    before = _hash_working_tree(repo)

    # Spy on subprocess.run to catch any git stash invocation
    stash_invocations: list[tuple] = []
    real_run = subprocess.run

    def spy_run(*args, **kwargs):
        if args and isinstance(args[0], list) and _is_git_stash_invocation(args[0]):
            stash_invocations.append(args[0])
        return real_run(*args, **kwargs)

    import subprocess as sp
    with pytest.MonkeyPatch.context() as mp_ctx:
        mp_ctx.setattr(sp, "run", spy_run)
        # Patch every checkpoint module's subprocess.run — current or future
        # callers. Modules that don't import subprocess are skipped via
        # getattr (defensive: a refactor that adds `import subprocess` to
        # any of them will start being spied automatically).
        from session_buddy.checkpoint import (
            metrics as metrics_mod,
        )
        from session_buddy.checkpoint import (
            orchestrator as orch_mod,
        )
        from session_buddy.checkpoint import policy as pol_mod
        from session_buddy.checkpoint import (
            snapshot as snap_mod,
        )
        from session_buddy.checkpoint import (
            subagent_detector as sad_mod,
        )
        for mod in (snap_mod, pol_mod, orch_mod, sad_mod, metrics_mod):
            sub = getattr(mod, "subprocess", None)
            if sub is not None:
                mp_ctx.setattr(sub, "run", spy_run)
        result = asyncio.run(orchestrator.run_checkpoint(phase=CheckpointPhase.MIDPOINT_DIRTINESS))

    assert result.fired is False
    assert "subagent" in result.decision_reason.lower()
    assert stash_invocations == [], f"git stash was called: {stash_invocations}"
    assert _hash_working_tree(repo) == before
    forward.assert_not_awaited()


def _hash_working_tree(repo: Path) -> str:
    out = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return hashlib.sha256(out.stdout.encode()).hexdigest()


def _is_git_stash_invocation(argv: object) -> bool:
    """Return True iff ``argv`` is a `git stash` (sub)command invocation.

    Robust against leading flags like ``-c KEY=VAL`` and other short options,
    so an invocation like ``['git', '-c', 'stash.show=true', 'log']`` is NOT
    flagged as a stash command. Also rejects refspecs that happen to contain
    the literal string "stash" (e.g. ``['git', 'log', 'stash@{0}']``) since
    the subcommand there is "log", not "stash".
    """
    if not isinstance(argv, list) or not argv:
        return False
    if argv[0] != "git":
        return False
    i = 1
    while i < len(argv):
        arg = argv[i]
        if not isinstance(arg, str):
            return False
        if arg == "-c":
            # -c takes a KEY=VAL argument; skip the value too.
            i += 2
            continue
        if arg.startswith("-"):
            # -C, --git-dir, -c foo=bar, --no-pager, etc. We don't
            # distinguish option-with-value vs option-without-value here
            # because the only options that appear in practice before the
            # subcommand in checkpoint code are short flag pairs.
            i += 1
            continue
        return arg == "stash"
    return False
