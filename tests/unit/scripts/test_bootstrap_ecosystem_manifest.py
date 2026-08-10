from __future__ import annotations

from pathlib import Path

import yaml

from scripts.bootstrap_ecosystem_manifest import bootstrap


def test_bootstrap_keys_by_slug_not_path(tmp_path: Path) -> None:
    """Slugs are Path.name, not absolute paths."""
    repos_yaml = tmp_path / "src.yaml"
    repos_yaml.write_text(yaml.safe_dump({
        "repos": [
            {"path": str(tmp_path / "session-buddy"), "tags": ["memory"], "description": "x"},
            {"path": str(tmp_path / "mahavishnu"), "tags": ["orchestrator"], "description": "x"},
        ]
    }))
    out = tmp_path / "ecosystem.yaml"
    bootstrap(source_yaml=repos_yaml, dest_yaml=out)
    data = yaml.safe_load(out.read_text())
    assert "session-buddy" in data["ecosystem"], f"slug key missing: {data}"
    assert "mahavishnu" in data["ecosystem"], f"slug key missing: {data}"
    assert data["ecosystem"]["session-buddy"]["path"] == str(tmp_path / "session-buddy")
    assert data["ecosystem"]["session-buddy"]["role"] == "memory"


def test_bootstrap_no_source_emits_empty_manifest(tmp_path: Path) -> None:
    out = tmp_path / "ecosystem.yaml"
    bootstrap(source_yaml=tmp_path / "nonexistent.yaml", dest_yaml=out)
    data = yaml.safe_load(out.read_text())
    assert data["ecosystem"] == {}
