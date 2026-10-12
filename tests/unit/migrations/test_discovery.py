"""Tests for ``session_buddy.migrations.runner.discovery.ScriptDiscovery``."""

from __future__ import annotations

from pathlib import Path

from session_buddy.migrations.runner.discovery import ScriptDiscovery


def test_discover_scripts_in_lex_order(tmp_path: Path) -> None:
    (tmp_path / "000_init.sql").write_text("INIT")
    (tmp_path / "001_first.sql").write_text("FIRST")
    (tmp_path / "002_second.sql").write_text("SECOND")
    (tmp_path / "008_last.sql").write_text("LAST")
    # An unrelated file that must NOT match the glob.
    (tmp_path / "README.md").write_text("hello")

    discovery = ScriptDiscovery(tmp_path)
    scripts = discovery.discover_scripts()

    assert [s.name for s in scripts] == [
        "000_init.sql",
        "001_first.sql",
        "002_second.sql",
        "008_last.sql",
    ]


def test_discover_scripts_excludes_down_files(tmp_path: Path) -> None:
    """Forward discovery must not pick up ``*_down.sql`` rollback files."""
    (tmp_path / "001_first.sql").write_text("FIRST")
    (tmp_path / "001_first_down.sql").write_text("FIRST_DOWN")

    discovery = ScriptDiscovery(tmp_path)
    scripts = discovery.discover_scripts()

    assert [s.name for s in scripts] == ["001_first.sql"]


def test_discover_scripts_empty_when_bundle_empty(tmp_path: Path) -> None:
    discovery = ScriptDiscovery(tmp_path)
    assert discovery.discover_scripts() == []


def test_discover_down_scripts_in_range(tmp_path: Path) -> None:
    """001..007 down scripts are returned; 000_down and 008_down are excluded."""
    (tmp_path / "000_init.sql").write_text("INIT")
    (tmp_path / "000_init_down.sql").write_text("INIT_DOWN")
    (tmp_path / "001_first.sql").write_text("FIRST")
    (tmp_path / "001_first_down.sql").write_text("FIRST_DOWN")
    (tmp_path / "007_seventh.sql").write_text("SEVENTH")
    (tmp_path / "007_seventh_down.sql").write_text("SEVENTH_DOWN")
    (tmp_path / "008_last.sql").write_text("LAST")
    (tmp_path / "008_last_down.sql").write_text("LAST_DOWN")
    (tmp_path / "README.md").write_text("hello")

    discovery = ScriptDiscovery(tmp_path)
    down = discovery.discover_down_scripts()

    assert [d.name for d in down] == [
        "001_first_down.sql",
        "007_seventh_down.sql",
    ]


def test_discover_down_scripts_empty_when_none_present(tmp_path: Path) -> None:
    (tmp_path / "001_first.sql").write_text("FIRST")

    discovery = ScriptDiscovery(tmp_path)
    assert discovery.discover_down_scripts() == []


def test_read_script_returns_contents(tmp_path: Path) -> None:
    body = "CREATE TABLE foo (id INTEGER);\n-- trailing comment\n"
    (tmp_path / "001_first.sql").write_text(body)

    discovery = ScriptDiscovery(tmp_path)
    assert discovery.read_script("001_first.sql") == body


def test_read_script_missing_raises(tmp_path: Path) -> None:
    discovery = ScriptDiscovery(tmp_path)
    import pytest

    with pytest.raises(FileNotFoundError):
        discovery.read_script("999_missing.sql")
