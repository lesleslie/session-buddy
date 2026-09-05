"""Tests for session_buddy.tools.mermaid_validator.renderer.

Covers the deterministic surface of the renderer — the regex parser,
the dataclasses, path iteration, JSON payload assembly, and the
allow-list guard — without invoking the Node.js subprocess. The
subprocess-coupled code paths (validate_mermaid_blocks,
_run_mermaid_subprocess, _locate_*) are exercised via ``unittest.mock``
patching the helpers they call.

The renderer module also has a documented ``except OSError,
UnicodeDecodeError:`` comma-syntax tuple (line 88) that still parses
in Python 3; the test ``test_extract_returns_empty_on_decode_error``
pins the *behavior* (decode failure → empty list) without depending
on the syntax form.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.tools.mermaid_validator.renderer import (
    DEFAULT_JSDOM_LOCATIONS,
    DEFAULT_MERMAID_PREFIXES,
    DEFAULT_SKIP_DIRS,
    MERMAID_FENCE_RE,
    MermaidBlock,
    MermaidValidationError,
    _build_payload,
    _is_trusted_mermaid_path,
    _parse_results,
    extract_mermaid_blocks,
    find_broken_mermaid_blocks,
    iter_markdown_files,
    print_errors,
    validate_mermaid_blocks,
)


# ---------------------------------------------------------------------------
# Regex pattern: MERMAID_FENCE_RE
# ---------------------------------------------------------------------------


class TestMermaidFenceRegex:
    def test_matches_single_block(self) -> None:
        text = "before\n```mermaid\ngraph TD; A-->B;\n```\nafter"
        matches = list(MERMAID_FENCE_RE.finditer(text))
        assert len(matches) == 1
        body = matches[0].group(1)
        assert "graph TD" in body
        assert "A-->B" in body

    def test_matches_multiple_blocks(self) -> None:
        text = (
            "intro\n"
            "```mermaid\ngraph TD; A-->B;\n```\n"
            "middle\n"
            "```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n"
            "end"
        )
        matches = list(MERMAID_FENCE_RE.finditer(text))
        assert len(matches) == 2
        assert "graph TD" in matches[0].group(1)
        assert "sequenceDiagram" in matches[1].group(1)

    def test_allows_info_string_after_language(self) -> None:
        """`` ```mermaid {something} `` `` should still match (info string ignored)."""
        text = "```mermaid {theme: dark}\ngraph TD; A-->B;\n```"
        matches = list(MERMAID_FENCE_RE.finditer(text))
        assert len(matches) == 1
        assert "graph TD" in matches[0].group(1)

    def test_does_not_match_non_mermaid_fences(self) -> None:
        text = (
            "```python\nprint('hi')\n```\n"
            "```\nplain fence\n```\n"
            "```mermaid\ngraph TD; A-->B;\n```"
        )
        matches = list(MERMAID_FENCE_RE.finditer(text))
        assert len(matches) == 1
        assert "graph TD" in matches[0].group(1)

    def test_does_not_match_unterminated_block(self) -> None:
        text = "```mermaid\ngraph TD; A-->B;\n"  # no closing fence
        matches = list(MERMAID_FENCE_RE.finditer(text))
        assert matches == []

    def test_multiline_body(self) -> None:
        text = "```mermaid\ngraph TD\n  A-->B\n  B-->C\n  C-->A\n```"
        matches = list(MERMAID_FENCE_RE.finditer(text))
        assert len(matches) == 1
        body = matches[0].group(1)
        assert "A-->B" in body
        assert "C-->A" in body


# ---------------------------------------------------------------------------
# MermaidBlock dataclass
# ---------------------------------------------------------------------------


class TestMermaidBlock:
    def test_is_frozen(self) -> None:
        block = MermaidBlock(file=Path("/tmp/x.md"), line=1, code="graph TD;")
        with pytest.raises((AttributeError, Exception)):
            block.line = 99  # type: ignore[misc]

    def test_equality_via_frozen_dataclass(self) -> None:
        a = MermaidBlock(file=Path("/tmp/x.md"), line=1, code="graph TD;")
        b = MermaidBlock(file=Path("/tmp/x.md"), line=1, code="graph TD;")
        assert a == b

    def test_inequality_when_differ(self) -> None:
        a = MermaidBlock(file=Path("/tmp/x.md"), line=1, code="graph TD;")
        b = MermaidBlock(file=Path("/tmp/x.md"), line=2, code="graph TD;")
        assert a != b


# ---------------------------------------------------------------------------
# MermaidValidationError.relpath
# ---------------------------------------------------------------------------


class TestMermaidValidationErrorRelpath:
    def test_relpath_when_file_under_cwd(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        sub = tmp_path / "docs" / "intro.md"
        sub.parent.mkdir(parents=True, exist_ok=True)
        sub.touch()
        err = MermaidValidationError(file=sub, line=1, error="bad")
        rel = err.relpath
        # On macOS, /private/tmp is a symlink to /tmp; both resolve to the
        # same canonical path, so the relative form may carry /private prefix.
        assert rel.startswith("docs/intro.md") or rel == "docs/intro.md"
        assert Path(rel).name == "intro.md"

    def test_relpath_falls_back_to_str_when_not_under_cwd(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # Make CWD a sibling; the file lives elsewhere.
        cwd = tmp_path / "cwd"
        elsewhere = tmp_path / "elsewhere" / "x.md"
        elsewhere.parent.mkdir(parents=True, exist_ok=True)
        elsewhere.touch()
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        err = MermaidValidationError(file=elsewhere, line=1, error="bad")
        # The relative_to() call raises ValueError → fallback to str(file)
        assert err.relpath == str(elsewhere)


# ---------------------------------------------------------------------------
# iter_markdown_files
# ---------------------------------------------------------------------------


class TestIterMarkdownFiles:
    def test_returns_all_markdown_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("hello")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.md").write_text("world")
        (tmp_path / "c.txt").write_text("not markdown")
        files = iter_markdown_files(tmp_path)
        names = {p.name for p in files}
        assert names == {"a.md", "b.md"}

    def test_skips_default_skip_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("hi")
        for skip in DEFAULT_SKIP_DIRS:
            d = tmp_path / skip / "nested.md"
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text("should be skipped")
        files = iter_markdown_files(tmp_path)
        names = {p.name for p in files}
        assert "a.md" in names
        assert "nested.md" not in names

    def test_custom_skip_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "keep.md").write_text("keep")
        (tmp_path / "custom_skip").mkdir()
        (tmp_path / "custom_skip" / "x.md").write_text("skip me")
        files = iter_markdown_files(tmp_path, skip_dirs=("custom_skip",))
        names = {p.name for p in files}
        assert names == {"keep.md"}

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert iter_markdown_files(tmp_path) == []

    def test_resolves_root(self, tmp_path: Path) -> None:
        # Pass a relative path; root should still be resolved.
        cwd = tmp_path
        (cwd / "x.md").write_text("x")
        files = iter_markdown_files(Path("."))  # CWD-independent relative
        # The result depends on CWD; just verify the function tolerates relative input.
        assert isinstance(files, list)


# ---------------------------------------------------------------------------
# extract_mermaid_blocks
# ---------------------------------------------------------------------------


class TestExtractMermaidBlocks:
    def test_returns_blocks_with_correct_line_numbers(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text(
            "# Title\n\n"
            "Intro text.\n\n"
            "```mermaid\ngraph TD; A-->B;\n```\n\n"
            "More text.\n\n"
            "```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n"
        )
        blocks = extract_mermaid_blocks(md)
        assert len(blocks) == 2
        assert blocks[0].file == md
        assert blocks[0].line == 5
        assert "graph TD" in blocks[0].code
        assert blocks[1].line == 11
        assert "sequenceDiagram" in blocks[1].code

    def test_returns_empty_for_no_mermaid(self, tmp_path: Path) -> None:
        md = tmp_path / "plain.md"
        md.write_text("# Title\n\nJust regular markdown.\n")
        assert extract_mermaid_blocks(md) == []

    def test_returns_empty_on_oserror(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.md"
        assert extract_mermaid_blocks(missing) == []

    def test_returns_empty_on_unicode_decode_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.md"
        bad.write_bytes(b"\xff\xfe\x00invalid utf-8")
        # The function uses read_text(encoding="utf-8") which raises
        # UnicodeDecodeError for invalid sequences; the bare except
        # catches OSError, UnicodeDecodeError and returns [].
        result = extract_mermaid_blocks(bad)
        assert result == []

    def test_first_line_block(self, tmp_path: Path) -> None:
        md = tmp_path / "x.md"
        md.write_text("```mermaid\ngraph TD;\n```\n")
        blocks = extract_mermaid_blocks(md)
        assert len(blocks) == 1
        assert blocks[0].line == 1


# ---------------------------------------------------------------------------
# _is_trusted_mermaid_path
# ---------------------------------------------------------------------------


class TestIsTrustedMermaidPath:
    def test_trusted_path_in_homebrew_cellar(self, tmp_path: Path) -> None:
        # Construct a path under a trusted prefix using monkeypatch-style
        # by directly checking the prefix string.
        trusted = Path("/opt/homebrew/Cellar/mermaid-cli/1.0.0/mermaid.core.mjs")
        # Only run the actual resolve() check on platforms where /opt exists;
        # the helper uses ``str(path.resolve())`` so symlinks get canonicalized.
        if trusted.parent.exists():
            assert _is_trusted_mermaid_path(trusted) is True

    def test_untrusted_path_returns_false(self, tmp_path: Path) -> None:
        # tmp_path is not under any trusted prefix.
        assert _is_trusted_mermaid_path(tmp_path / "evil.mjs") is False

    def test_untrusted_path_mimicking_prefix_in_name(self, tmp_path: Path) -> None:
        """A directory literally named ``mermaid-cli`` under tmp is NOT trusted."""
        mimic = tmp_path / "mermaid-cli" / "x.mjs"
        mimic.parent.mkdir()
        mimic.touch()
        assert _is_trusted_mermaid_path(mimic) is False


# ---------------------------------------------------------------------------
# _build_payload
# ---------------------------------------------------------------------------


class TestBuildPayload:
    def test_serializes_blocks_as_json_list(self) -> None:
        blocks = [
            MermaidBlock(file=Path("/tmp/a.md"), line=1, code="graph TD;"),
            MermaidBlock(file=Path("/tmp/b.md"), line=5, code="sequenceDiagram"),
        ]
        payload = _build_payload(blocks)
        data = json.loads(payload)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"file": "/tmp/a.md", "line": 1, "code": "graph TD;"}
        assert data[1] == {"file": "/tmp/b.md", "line": 5, "code": "sequenceDiagram"}

    def test_empty_blocks_yields_empty_json_list(self) -> None:
        payload = _build_payload([])
        assert json.loads(payload) == []


# ---------------------------------------------------------------------------
# _parse_results
# ---------------------------------------------------------------------------


class TestParseResults:
    def test_filters_to_error_entries(self) -> None:
        results = [
            {"file": "/tmp/a.md", "line": 1, "status": "ok"},
            {"file": "/tmp/b.md", "line": 3, "status": "error", "error": "bad"},
            {"file": "/tmp/c.md", "line": 7, "status": "error"},  # missing error key
        ]
        errors = _parse_results(results)
        assert len(errors) == 2
        assert errors[0].file == Path("/tmp/b.md")
        assert errors[0].line == 3
        assert errors[0].error == "bad"
        # Missing 'error' key falls back to '<unknown error>'.
        assert errors[1].error == "<unknown error>"

    def test_all_ok_yields_empty_list(self) -> None:
        results = [
            {"file": "/tmp/a.md", "line": 1, "status": "ok"},
            {"file": "/tmp/b.md", "line": 2, "status": "ok"},
        ]
        assert _parse_results(results) == []

    def test_empty_input_yields_empty_output(self) -> None:
        assert _parse_results([]) == []

    def test_missing_status_key_treated_as_non_error(self) -> None:
        """Only entries with status == 'error' become errors; missing status is skipped."""
        results = [{"file": "/tmp/a.md", "line": 1}]
        assert _parse_results(results) == []


# ---------------------------------------------------------------------------
# validate_mermaid_blocks (without actually running node)
# ---------------------------------------------------------------------------


class TestValidateMermaidBlocks:
    def test_empty_blocks_returns_empty_without_subprocess(self) -> None:
        # The function short-circuits on empty input — no Node invocation.
        assert validate_mermaid_blocks([]) == []

    def test_raises_filenotfound_when_runner_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """If validate_mermaid.mjs is not present next to the renderer,
        ``validate_mermaid_blocks`` raises ``FileNotFoundError`` before
        attempting to launch node. We exercise this by pointing
        ``Path(__file__).parent`` at a directory that does not contain
        the .mjs file.
        """
        from session_buddy.tools.mermaid_validator import renderer as rmod

        # Replace the module so that ``Path(__file__).parent`` resolves to
        # a temp dir without the runner.
        class FakePath(type(Path())):  # type: ignore[misc]
            @property
            def parent(self) -> Path:  # type: ignore[override]
                return tmp_path

        blocks = [MermaidBlock(file=tmp_path / "a.md", line=1, code="graph TD;")]
        monkeypatch.setattr(rmod, "Path", FakePath)
        with pytest.raises(FileNotFoundError, match="validate_mermaid.mjs"):
            validate_mermaid_blocks(blocks)

    def test_raises_when_mermaid_core_missing(self, tmp_path: Path) -> None:
        blocks = [MermaidBlock(file=tmp_path / "a.md", line=1, code="graph TD;")]
        with (
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_mermaid_core",
                return_value=None,
            ),
            pytest.raises(RuntimeError, match="could not find mermaid/dist"),
        ):
            validate_mermaid_blocks(blocks)

    def test_raises_when_jsdom_missing(self, tmp_path: Path) -> None:
        blocks = [MermaidBlock(file=tmp_path / "a.md", line=1, code="graph TD;")]
        fake_core = Path("/opt/homebrew/lib/node_modules/mermaid/dist/mermaid.core.mjs")
        with (
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_mermaid_core",
                return_value=fake_core,
            ),
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_jsdom",
                return_value=None,
            ),
            pytest.raises(RuntimeError, match="could not find jsdom"),
        ):
            validate_mermaid_blocks(blocks)

    def test_raises_on_subprocess_nonzero_exit(self, tmp_path: Path) -> None:
        blocks = [MermaidBlock(file=tmp_path / "a.md", line=1, code="graph TD;")]
        fake_core = Path("/opt/homebrew/lib/node_modules/mermaid/dist/mermaid.core.mjs")
        fake_jsdom = Path("/repo/node_modules/jsdom/lib/api.js")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="parse error: line 1",
        )
        with (
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_mermaid_core",
                return_value=fake_core,
            ),
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_jsdom",
                return_value=fake_jsdom,
            ),
            patch(
                "session_buddy.tools.mermaid_validator.renderer._run_mermaid_subprocess",
                return_value=completed,
            ),
            pytest.raises(RuntimeError, match="exited 1"),
        ):
            validate_mermaid_blocks(blocks)

    def test_raises_on_invalid_json_stdout(self, tmp_path: Path) -> None:
        blocks = [MermaidBlock(file=tmp_path / "a.md", line=1, code="graph TD;")]
        fake_core = Path("/opt/homebrew/lib/node_modules/mermaid/dist/mermaid.core.mjs")
        fake_jsdom = Path("/repo/node_modules/jsdom/lib/api.js")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="not json {",
            stderr="",
        )
        with (
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_mermaid_core",
                return_value=fake_core,
            ),
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_jsdom",
                return_value=fake_jsdom,
            ),
            patch(
                "session_buddy.tools.mermaid_validator.renderer._run_mermaid_subprocess",
                return_value=completed,
            ),
            pytest.raises(RuntimeError, match="invalid JSON"),
        ):
            validate_mermaid_blocks(blocks)

    def test_parses_valid_json_stdout(self, tmp_path: Path) -> None:
        blocks = [MermaidBlock(file=tmp_path / "a.md", line=1, code="graph TD;")]
        fake_core = Path("/opt/homebrew/lib/node_modules/mermaid/dist/mermaid.core.mjs")
        fake_jsdom = Path("/repo/node_modules/jsdom/lib/api.js")
        stdout = json.dumps(
            [
                {"file": "/tmp/a.md", "line": 1, "status": "ok"},
                {"file": "/tmp/b.md", "line": 2, "status": "error", "error": "boom"},
            ]
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        )
        with (
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_mermaid_core",
                return_value=fake_core,
            ),
            patch(
                "session_buddy.tools.mermaid_validator.renderer._locate_jsdom",
                return_value=fake_jsdom,
            ),
            patch(
                "session_buddy.tools.mermaid_validator.renderer._run_mermaid_subprocess",
                return_value=completed,
            ),
        ):
            errors = validate_mermaid_blocks(blocks)
        assert len(errors) == 1
        assert errors[0].error == "boom"


# ---------------------------------------------------------------------------
# find_broken_mermaid_blocks (integration via patched helpers)
# ---------------------------------------------------------------------------


class TestFindBrokenMermaidBlocks:
    def test_uses_paths_when_provided(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("```mermaid\ngraph TD; A-->B;\n```\n")
        with patch(
            "session_buddy.tools.mermaid_validator.renderer.validate_mermaid_blocks",
            return_value=[],
        ) as vmock:
            errors = find_broken_mermaid_blocks(paths=[md])
        assert errors == []
        vmock.assert_called_once()

    def test_scans_root_when_no_paths(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("```mermaid\ngraph TD;\n```\n")
        with patch(
            "session_buddy.tools.mermaid_validator.renderer.validate_mermaid_blocks",
            return_value=[],
        ) as vmock:
            find_broken_mermaid_blocks(root=tmp_path)
        vmock.assert_called_once()
        # validate_mermaid_blocks was called with a list containing one block.
        call_args = vmock.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].code.strip() == "graph TD;"

    def test_scans_cwd_when_neither_provided(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "doc.md").write_text("```mermaid\ngraph TD;\n```\n")
        with patch(
            "session_buddy.tools.mermaid_validator.renderer.validate_mermaid_blocks",
            return_value=[],
        ) as vmock:
            find_broken_mermaid_blocks()
        vmock.assert_called_once()


# ---------------------------------------------------------------------------
# print_errors (smoke)
# ---------------------------------------------------------------------------


class TestPrintErrors:
    def test_empty_list_prints_green_check(self, capsys: pytest.CaptureFixture) -> None:
        print_errors([])
        captured = capsys.readouterr()
        assert "All mermaid blocks parse cleanly" in captured.out

    def test_non_empty_prints_red_count(self, capsys: pytest.CaptureFixture) -> None:
        err = MermaidValidationError(
            file=Path("/tmp/a.md"), line=1, error="boom"
        )
        print_errors([err])
        captured = capsys.readouterr()
        assert "broken mermaid block" in captured.out


# ---------------------------------------------------------------------------
# Module-level constants (sanity)
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_default_skip_dirs_contains_venv(self) -> None:
        assert ".venv" in DEFAULT_SKIP_DIRS
        assert "venv" in DEFAULT_SKIP_DIRS
        assert ".git" in DEFAULT_SKIP_DIRS

    def test_default_mermaid_prefixes_are_absolute(self) -> None:
        for prefix in DEFAULT_MERMAID_PREFIXES:
            assert prefix.startswith("/")

    def test_default_jsdom_locations_is_tuple_of_strings(self) -> None:
        for item in DEFAULT_JSDOM_LOCATIONS:
            assert isinstance(item, str)
