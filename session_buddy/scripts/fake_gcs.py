"""Thin Python entry-point for the fake-gcs-server lifecycle scripts.

Dispatches ``session-buddy-fake-gcs {start|stop|init}`` to the
corresponding shell script under ``scripts/``. Used by Track B (Cold/Hot
Tiering via fake-gcs-server) so operators have a single console-script
entry point.

Environment variables consumed by the underlying shell scripts:
- FAKE_GCS_DATA_DIR (default ``~/.cache/session-buddy/fake-gcs``)
- FAKE_GCS_PORT (default ``4443``)
- FAKE_GCS_HOST (default ``127.0.0.1``)
- GCS_ENDPOINT (default ``http://127.0.0.1:4443``)
- GCS_PROJECT (default ``local-dev``)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("FAKE_GCS_DATA_DIR", Path.home() / ".cache/session-buddy/fake-gcs")
)
# session_buddy/scripts/fake_gcs.py -> repo_root/scripts/fake-gcs-*.sh
SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"


def main() -> int:
    """Dispatch to ``scripts/fake-gcs-<command>.sh``."""
    if len(sys.argv) < 2:
        print("usage: session-buddy-fake-gcs {start|stop|init}", file=sys.stderr)
        return 2
    cmd, *rest = sys.argv[1:]
    script = SCRIPTS / f"fake-gcs-{cmd}.sh"
    if not script.exists():
        print(f"no script: {script}", file=sys.stderr)
        return 2
    return subprocess.call(["bash", str(script), *rest])


if __name__ == "__main__":
    sys.exit(main())
