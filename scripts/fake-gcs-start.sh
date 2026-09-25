#!/usr/bin/env bash
# scripts/fake-gcs-start.sh
# Start fake-gcs-server with the canonical Session-Buddy bucket layout.
set -euo pipefail

DATA_DIR="${FAKE_GCS_DATA_DIR:-$HOME/.cache/session-buddy/fake-gcs}"
PORT="${FAKE_GCS_PORT:-4443}"
HOST="${FAKE_GCS_HOST:-127.0.0.1}"
PROJECT="${GCS_PROJECT:-local-dev}"

mkdir -p "$DATA_DIR"

# Idempotency: if already running on this port, skip.
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "fake-gcs-server already running on port $PORT"
  exit 0
fi

echo "Starting fake-gcs-server on $HOST:$PORT (data: $DATA_DIR)"
nohup fake-gcs-server \
  -filesystem-root "$DATA_DIR" \
  -port "$PORT" \
  -host "$HOST" \
  -location "US-CENTRAL1" \
  -public-host "$HOST:$PORT" \
  > "$DATA_DIR/server.log" 2>&1 &

echo $! > "$DATA_DIR/server.pid"
echo "PID $(cat "$DATA_DIR/server.pid"); logs at $DATA_DIR/server.log"
