#!/usr/bin/env python3
"""Bootstrap settings/ecosystem.yaml from mahavishnu's settings/repos.yaml.

Keys the output by SLUG (Path.name) so consumers can use canonical
short names (e.g., "mahavishnu") instead of absolute paths.

Idempotent. Re-running overwrites the gitignored dest file.

If the source is missing, emits an empty manifest with a WARNING so
session-buddy's first checkpoint fails gracefully rather than crashing.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
from oneiric.core.logging import get_logger

_log = get_logger(__name__)


DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "mahavishnu" / "settings" / "repos.yaml"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "settings" / "ecosystem.yaml"
ENV_SOURCE = "MAHAVISHNU_REPOS_YAML"


def bootstrap(*, source_yaml: Path, dest_yaml: Path) -> dict:
    if not source_yaml.exists():
        _log.warning(
            "ecosystem_manifest_source_missing",
            extra={"path": str(source_yaml)},
        )
        ecosystem: dict[str, dict[str, str | None]] = {}
    else:
        try:
            raw = yaml.safe_load(source_yaml.read_text())
        except (yaml.YAMLError, OSError) as exc:
            _log.warning(
                "ecosystem_manifest_source_malformed",
                extra={"path": str(source_yaml), "error": str(exc)},
            )
            ecosystem = {}
        else:
            repos = (raw or {}).get("repos", []) if isinstance(raw, dict) else []
            ecosystem = {}
            for repo in repos:
                if not isinstance(repo, dict):
                    continue
                path_str = repo.get("path", "")
                if not path_str:
                    continue
                slug = Path(path_str).name
                tags = repo.get("tags") or []
                role = tags[0] if tags else None
                ecosystem[slug] = {"path": path_str, "role": role}
    dest_yaml.parent.mkdir(parents=True, exist_ok=True)
    dest_yaml.write_text(yaml.safe_dump({"ecosystem": ecosystem}))
    return {"ecosystem": ecosystem}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    source_default = Path(os.environ.get(ENV_SOURCE, DEFAULT_SOURCE))
    p.add_argument("--source", type=Path, default=source_default, help="source repos.yaml")
    p.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="dest ecosystem.yaml")
    args = p.parse_args(argv)
    bootstrap(source_yaml=args.source, dest_yaml=args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
