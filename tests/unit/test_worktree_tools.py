"""Tests for the new worktree tools and helpers added in 2026-07-26.

Covers:
- New helpers in ``session_buddy/utils/git_worktrees.py``
  (``create_worktree``, ``remove_worktree``)
- New ``register_worktree_tools`` MCP registration function
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_git_worktrees_module() -> types.ModuleType:
    """Load ``session_buddy.utils.git_worktrees`` without importing the
    full session-buddy package (which has heavy init dependencies).

    Mirrors the pattern used in ``test_git_operations.py``.
    """
    repo_root = Path(__file__).resolve().parents[2]

    package_name = "session_buddy"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(repo_root / "session_buddy")]  # type: ignore[attr-defined]
        sys.modules[package_name] = package
    else:
        package = sys.modules[package_name]

    utils_package_name = "session_buddy.utils"
    if utils_package_name not in sys.modules:
        utils_package = types.ModuleType(utils_package_name)
        utils_package.__path__ = [str(repo_root / "session_buddy" / "utils")]  # type: ignore[attr-defined]
        sys.modules[utils_package_name] = utils_package
    else:
        utils_package = sys.modules[utils_package_name]
    setattr(package, "utils", utils_package)

    module_path = repo_root / "session_buddy" / "utils" / "git_worktrees.py"
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.git_worktrees",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    setattr(utils_package, "git_worktrees", module)
    spec.loader.exec_module(module)
    return module


git_worktrees = _load_git_worktrees_module()
create_worktree = git_worktrees.create_worktree
remove_worktree = git_worktrees.remove_worktree
WorktreeInfo = git_worktrees.WorktreeInfo


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create an empty git repo in tmp_path with one initial commit."""

    def _run(args: list[str]) -> None:
        subprocess.run(
            args,
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=True,
        )

    _run(["git", "init", "-q"])
    _run(["git", "config", "user.email", "test@example.com"])
    _run(["git", "config", "user.name", "Test"])
    _run(["git", "config", "commit.gpgsign", "false"])
    (tmp_path / "README.md").write_text("hello\n")
    _run(["git", "add", "README.md"])
    _run(["git", "commit", "-q", "-m", "init"])
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestCreateWorktree:
    def test_returns_error_when_path_is_not_a_repo(self, tmp_path: Path) -> None:
        not_repo = tmp_path / "not-a-repo"
        not_repo.mkdir()
        ok, info = create_worktree(not_repo, str(tmp_path / "wt"), branch="feat")
        assert ok is False
        assert info["error_code"] == "not_git_repository"
        assert "Not a git repository" in info["error"]

    def test_creates_worktree_with_existing_branch(self, tmp_repo: Path) -> None:
        # Make a branch first
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat-x"], cwd=str(tmp_repo), check=True
        )
        subprocess.run(
            ["git", "checkout", "-q", "main"], cwd=str(tmp_repo), check=True
        )

        wt_path = tmp_repo / "wt"
        ok, info = create_worktree(tmp_repo, str(wt_path), branch="feat-x")
        assert ok is True, info
        assert info["branch"] == "feat-x"
        assert info["worktree_path"] == str(wt_path)
        assert isinstance(info["head"], str) and len(info["head"]) >= 7
        assert wt_path.exists()

    def test_create_branch_with_new_branch(self, tmp_repo: Path) -> None:
        wt_path = tmp_repo / "wt-new"
        ok, info = create_worktree(
            tmp_repo,
            str(wt_path),
            branch="brand-new-branch",
            create_branch=True,
        )
        assert ok is True, info
        assert info["branch"] == "brand-new-branch"


# ---------------------------------------------------------------------------
# remove_worktree
# ---------------------------------------------------------------------------


class TestRemoveWorktree:
    def test_returns_error_when_path_is_not_a_repo(self, tmp_path: Path) -> None:
        not_repo = tmp_path / "not-a-repo"
        not_repo.mkdir()
        ok, info = remove_worktree(not_repo, str(tmp_path / "wt"))
        assert ok is False
        assert info["error_code"] == "not_git_repository"

    def test_removes_a_clean_worktree(self, tmp_repo: Path) -> None:
        # Create a worktree first (branch must exist for `git worktree add`)
        wt_path = tmp_repo / "wt-clean"
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat-clean"], cwd=str(tmp_repo), check=True
        )
        subprocess.run(
            ["git", "checkout", "-q", "main"], cwd=str(tmp_repo), check=True
        )
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-q",
                str(wt_path),
                "feat-clean",
            ],
            cwd=str(tmp_repo),
            check=True,
        )
        assert wt_path.exists()

        ok, info = remove_worktree(tmp_repo, str(wt_path), force=False)
        assert ok is True, info
        assert not wt_path.exists()

    def test_dirty_worktree_refuses_without_force(self, tmp_repo: Path) -> None:
        # Create a worktree (branch must exist for `git worktree add`)
        wt_path = tmp_repo / "wt-dirty"
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat-dirty"], cwd=str(tmp_repo), check=True
        )
        subprocess.run(
            ["git", "checkout", "-q", "main"], cwd=str(tmp_repo), check=True
        )
        subprocess.run(
            ["git", "worktree", "add", "-q", str(wt_path), "feat-dirty"],
            cwd=str(tmp_repo),
            check=True,
        )
        # Make it dirty
        (wt_path / "uncommitted.txt").write_text("dirty\n")

        ok, info = remove_worktree(tmp_repo, str(wt_path), force=False)
        assert ok is False
        assert info.get("force_required") is True
        assert info.get("safety_check") == "uncommitted_changes"
        assert wt_path.exists()  # Still present

        # Force=True should clean it up
        ok, info = remove_worktree(
            tmp_repo,
            str(wt_path),
            force=True,
            force_reason="test-cleanup",
        )
        assert ok is True, info
        assert not wt_path.exists()

    def test_force_reason_preserved_in_info(self, tmp_repo: Path) -> None:
        wt_path = tmp_repo / "wt-reason"
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat-reason"], cwd=str(tmp_repo), check=True
        )
        subprocess.run(
            ["git", "checkout", "-q", "main"], cwd=str(tmp_repo), check=True
        )
        subprocess.run(
            ["git", "worktree", "add", "-q", str(wt_path), "feat-reason"],
            cwd=str(tmp_repo),
            check=True,
        )

        ok, info = remove_worktree(
            tmp_repo,
            str(wt_path),
            force=False,
            force_reason="human explicitly requested",
        )
        # Cleaner path: should NOT echo force_reason (returned only on success/force=True)
        assert ok is True
        assert info["force_reason"] == "human explicitly requested"


# ---------------------------------------------------------------------------
# WorktreeInfo head field (added for the new MCP tool contract)
# ---------------------------------------------------------------------------


class TestWorktreeInfoHead:
    def test_worktree_info_has_head_field(self) -> None:
        info = WorktreeInfo(path=Path("/tmp"), branch="main", head="abc1234")
        assert info.head == "abc1234"

    def test_worktree_info_head_defaults_empty(self) -> None:
        info = WorktreeInfo(path=Path("/tmp"), branch="main")
        assert info.head == ""


# ---------------------------------------------------------------------------
# Module export surface
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_create_worktree_is_exported(self) -> None:
        assert "create_worktree" in git_worktrees.__all__

    def test_remove_worktree_is_exported(self) -> None:
        assert "remove_worktree" in git_worktrees.__all__


# ---------------------------------------------------------------------------
# register_worktree_tools MCP registration
# ---------------------------------------------------------------------------


class FakeFastMCP:
    """Minimal FastMCP stand-in that captures registered tools.

    Lets us call ``register_worktree_tools(mcp)`` and then assert the
    three tools were registered with the expected names.
    """

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self) -> "object":  # noqa: D401 — context-manager-like decorator
        outer_self = self

        class _Decor:
            def __enter__(self) -> None:
                pass

            def __exit__(self, *_exc: object) -> bool:
                return False

            def __call__(self, func: object) -> object:
                outer_self.tools[func.__name__] = func  # type: ignore[attr-defined]
                return func

        return _Decor()


def _import_register_worktree_tools() -> object:
    """Load ``session_buddy.mcp.tools.worktree_tools.register_worktree_tools``
    without importing the full session-buddy package.

    The module imports ``mcp_common.fastmcp``, which is available. If
    importing the package root would be expensive, fall back to loading
    the file directly via importlib.
    """
    repo_root = Path(__file__).resolve().parents[2]
    module_path = (
        repo_root / "session_buddy" / "mcp" / "tools" / "worktree_tools.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_buddy.mcp.tools.worktree_tools",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.register_worktree_tools  # type: ignore[no-any-return]


class TestRegisterWorktreeTools:
    def test_registers_three_tools(self) -> None:
        register_fn = _import_register_worktree_tools()
        mcp = FakeFastMCP()
        register_fn(mcp)
        assert set(mcp.tools) == {
            "list_worktrees",
            "create_worktree",
            "remove_worktree",
        }

    @pytest.mark.asyncio
    async def test_list_worktrees_returns_json_with_worktrees_field(
        self, tmp_path: Path
    ) -> None:
        """The list_worktrees tool must return a JSON string with
        a 'worktrees' list — that's the contract the Mahavishnu
        SessionBuddyWorktreeProvider expects via coordinator.list_worktrees.
        """
        # Set up a tiny git repo and a worktree
        subprocess.run(
            ["git", "init", "-q", str(tmp_path)], check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "t@example.com"],
            cwd=str(tmp_path),
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(tmp_path),
            check=True,
        )
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"],
            cwd=str(tmp_path),
            check=True,
        )
        (tmp_path / "f.txt").write_text("a")
        subprocess.run(
            ["git", "add", "f.txt"],
            cwd=str(tmp_path),
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"],
            cwd=str(tmp_path),
            check=True,
        )

        register_fn = _import_register_worktree_tools()
        mcp = FakeFastMCP()
        register_fn(mcp)

        list_fn = mcp.tools["list_worktrees"]  # type: ignore[attr-defined]
        result = await list_fn(repository_path=str(tmp_path))
        payload = json.loads(result)
        assert payload["success"] is True
        assert isinstance(payload["worktrees"], list)
        # First entry should be the main worktree itself.
        # git worktree list --porcelain emits the branch as the full ref
        # ("refs/heads/main") so accept that form.
        assert payload["worktrees"], "expected at least the main worktree"
        assert any(
            wt["branch"] in ("refs/heads/main", "refs/heads/master", "main", "master")
            for wt in payload["worktrees"]
        )

    @pytest.mark.asyncio
    async def test_list_worktrees_handles_missing_path_gracefully(self) -> None:
        register_fn = _import_register_worktree_tools()
        mcp = FakeFastMCP()
        register_fn(mcp)
        list_fn = mcp.tools["list_worktrees"]  # type: ignore[attr-defined]
        result = await list_fn(repository_path="/nonexistent/path/that/does/not/exist")
        payload = json.loads(result)
        # Should return success=False with a clear error rather than raising
        assert payload["success"] is False
        assert "error" in payload
        assert payload.get("error_code") == "not_git_repository"


@pytest.fixture
def mock_magic() -> MagicMock:
    return MagicMock()


# Smoke: ensure module loads cleanly even if parts of session-buddy aren't importable
def test_module_imports_cleanly() -> None:
    fn = _import_register_worktree_tools()
    assert callable(fn)
