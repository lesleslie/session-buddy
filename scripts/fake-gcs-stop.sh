#!/usr/bin/env bash
# scripts/fake-gcs-stop.sh
set -euo pipefail

DATA_DIR="${FAKE_GCS_DATA_DIR:-$HOME/.cache/session-buddy/fake-gcs}"
PIDFILE="$DATA_DIR/server.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No PID file at $PIDFILE; nothing to stop."
  exit 0
fi

PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped fake-gcs-server (PID $PID)"
fi
rm -f "$PIDFILE"
