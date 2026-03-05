#!/usr/bin/env bash
set -euo pipefail

STATE="$HOME/.dharma"
PID_FILE="$STATE/verification_lane.pid"
STOP_FILE="$STATE/STOP_VERIFICATION_LANE"
RUN_FILE="$STATE/verification_lane_run_dir.txt"

mkdir -p "$STATE"
echo "stop requested $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STOP_FILE"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No verification lane PID file found."
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "${PID:-}" ]]; then
  echo "PID file is empty."
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Sent TERM to verification lane PID $PID"
else
  echo "Process $PID is not running."
fi

echo "Run dir: $(cat "$RUN_FILE" 2>/dev/null || echo unknown)"

