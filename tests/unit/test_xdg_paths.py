"""Guard tests for the XDG Base Directory path migration.

Session-Buddy's runtime data used to live under ``~/.claude/data`` — a
Claude-Code-specific directory. These tests fail if that hardcoded legacy
path creeps back into the code.

The scan has two layers:

* **Textual.** Every ``.py`` file under the package is parsed with
  ``ast``; comment tokens and docstrings are stripped and the remaining
  *code* must not contain the substring ``.claude/data``. Docstrings and
  comments may still name the legacy path — they are documentation, not
  behaviour.
* **Structural.** The legacy path can also be spelled as a path join
  (``Path.home() / ".claude" / "data"``), which never produces the
  contiguous substring. Those joins are rejected too, as is a ``"data"``
  segment appended to a ``claude``-named path.

The resolver itself is checked separately: it must honour
``$XDG_DATA_HOME`` / ``$XDG_STATE_HOME`` / ``$XDG_CACHE_HOME`` /
``$XDG_CONFIG_HOME`` and fall back to the XDG spec defaults.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

from session_buddy import paths as xdg

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "session_buddy"
SCRIPTS_ROOT = REPO_ROOT / "scripts"

LEGACY_FRAGMENT = ".claude/data"
APP_NAME = "session-buddy"


# ---------------------------------------------------------------------------
# Scan helpers
# ---------------------------------------------------------------------------


def _python_files() -> list[Path]:
    """Return every Python file the guard scans."""
    files = sorted(PACKAGE_ROOT.rglob("*.py"))
    files.extend(sorted(SCRIPTS_ROOT.glob("*.py")))
    return files


def _docstring_line_spans(tree: ast.AST) -> list[tuple[int, int]]:
    """Return the (start, end) line spans of every docstring."""
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            spans.append((body[0].lineno, body[0].end_lineno or body[0].lineno))
    return spans


def _code_only(source: str) -> str:
    """Return ``source`` with comment tokens and docstrings removed.

    Line numbers are preserved so any failure message can still point at
    the offending line.

    """
    tree = ast.parse(source)
    lines = source.splitlines()

    for start, end in _docstring_line_spans(tree):
        for lineno in range(start - 1, end):
            if lineno < len(lines):
                lines[lineno] = ""

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        (start_row, start_col), (_, end_col) = token.start, token.end
        index = start_row - 1
        if index >= len(lines):
            continue
        line = lines[index]
        lines[index] = line[:start_col] + " " * (end_col - start_col) + line[end_col:]

    return "\n".join(lines)


def _mentions_claude(node: ast.AST) -> bool:
    """Return True when ``node`` refers to a ``.claude`` path."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if ".claude" in child.value:
                return True
        elif isinstance(child, ast.Name | ast.Attribute):
            identifier = child.id if isinstance(child, ast.Name) else child.attr
            if "claude" in identifier.lower():
                return True
    return False


def _legacy_path_joins(tree: ast.AST) -> list[int]:
    """Return the line numbers of legacy ``... / "data"`` path joins."""
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
            continue
        right = node.right
        if not (isinstance(right, ast.Constant) and right.value == "data"):
            continue
        if _mentions_claude(node.left):
            offenders.append(node.lineno)
    return offenders


# ---------------------------------------------------------------------------
# Guard: the legacy path must not come back
# ---------------------------------------------------------------------------


class TestNoLegacyDataPathInCode:
    """The legacy ``~/.claude/data`` path must not appear in code."""

    def test_python_files_are_found(self) -> None:
        """The scan must actually cover the package."""
        files = _python_files()
        assert files, "no Python files found to scan"
        assert PACKAGE_ROOT / "paths.py" in files

    @pytest.mark.parametrize("source_file", _python_files(), ids=lambda p: p.name)
    def test_code_has_no_legacy_data_path(self, source_file: Path) -> None:
        """Stripped code must not contain the legacy path substring."""
        source = source_file.read_text(encoding="utf-8")
        code = _code_only(source)
        assert LEGACY_FRAGMENT not in code, (
            f"{source_file.relative_to(REPO_ROOT)} contains the hardcoded legacy "
            f"path {LEGACY_FRAGMENT!r} in code; use session_buddy.paths instead"
        )

    @pytest.mark.parametrize("source_file", _python_files(), ids=lambda p: p.name)
    def test_code_has_no_legacy_data_path_join(self, source_file: Path) -> None:
        """The legacy path must not be rebuilt as a path join."""
        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        offenders = _legacy_path_joins(tree)
        assert not offenders, (
            f"{source_file.relative_to(REPO_ROOT)} joins a 'data' segment onto a "
            f"'.claude' path at line(s) {offenders}; use session_buddy.paths instead"
        )


# ---------------------------------------------------------------------------
# Resolver behaviour
# ---------------------------------------------------------------------------


class TestXdgResolver:
    """The resolver honours the XDG environment variables."""

    def test_data_dir_honours_xdg_data_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """$XDG_DATA_HOME moves the persistent-data directory."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        assert xdg.data_dir() == tmp_path / "data" / APP_NAME

    def test_state_dir_honours_xdg_state_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """$XDG_STATE_HOME moves the state directory."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        assert xdg.state_dir() == tmp_path / "state" / APP_NAME

    def test_cache_dir_honours_xdg_cache_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """$XDG_CACHE_HOME moves the cache directory."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        assert xdg.cache_dir() == tmp_path / "cache" / APP_NAME

    def test_config_dir_honours_xdg_config_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """$XDG_CONFIG_HOME moves the settings directory."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        assert xdg.config_dir() == tmp_path / "config" / APP_NAME

    @pytest.mark.parametrize(
        ("env_var", "fallback", "resolver"),
        [
            ("XDG_DATA_HOME", ".local/share", xdg.data_dir),
            ("XDG_STATE_HOME", ".local/state", xdg.state_dir),
            ("XDG_CACHE_HOME", ".cache", xdg.cache_dir),
            ("XDG_CONFIG_HOME", ".config", xdg.config_dir),
        ],
    )
    def test_falls_back_to_xdg_spec_default(
        self,
        env_var: str,
        fallback: str,
        resolver: object,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without the environment variable the XDG spec default applies."""
        monkeypatch.delenv(env_var, raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        expected = tmp_path / fallback / APP_NAME
        assert resolver() == expected  # type: ignore[operator]

    def test_home_override_is_honoured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """$HOME steers the spec defaults (no Path.home() in the resolver)."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert xdg.data_dir() == tmp_path / ".local" / "share" / APP_NAME

    def test_app_name_is_joined(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The app name is appended to the resolved root."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert xdg.data_dir("other-app") == tmp_path / "other-app"

    def test_data_owner_is_always_session_buddy(self) -> None:
        """The data owner never becomes the consuming repository's app name."""
        for resolver in (xdg.data_dir, xdg.state_dir, xdg.cache_dir, xdg.config_dir):
            assert resolver().name == APP_NAME

    def test_resolver_has_no_filesystem_side_effects(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolving a directory must not create it."""
        roots = {
            "data": tmp_path / "data",
            "state": tmp_path / "state",
            "cache": tmp_path / "cache",
            "config": tmp_path / "config",
        }
        monkeypatch.setenv("XDG_DATA_HOME", str(roots["data"]))
        monkeypatch.setenv("XDG_STATE_HOME", str(roots["state"]))
        monkeypatch.setenv("XDG_CACHE_HOME", str(roots["cache"]))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(roots["config"]))

        xdg.data_dir()
        xdg.state_dir()
        xdg.cache_dir()
        xdg.config_dir()

        for name, root in roots.items():
            assert not root.exists(), f"XDG {name} root was created on disk"

    def test_dir_under_home_ignores_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit home anchors the tree and wins over the environment."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "elsewhere"))
        assert xdg.data_dir_under(tmp_path / "home") == (
            tmp_path / "home" / ".local" / "share" / APP_NAME
        )
        assert xdg.state_dir_under(tmp_path / "home") == (
            tmp_path / "home" / ".local" / "state" / APP_NAME
        )
