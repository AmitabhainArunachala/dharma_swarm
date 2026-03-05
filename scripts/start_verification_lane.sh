#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/dharma_swarm"
STATE="$HOME/.dharma"
LOG_DIR="$STATE/logs"
PID_FILE="$STATE/verification_lane.pid"
RUN_FILE="$STATE/verification_lane_run_dir.txt"
STOP_FILE="$STATE/STOP_VERIFICATION_LANE"

mkdir -p "$LOG_DIR"
rm -f "$STOP_FILE"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Verification lane already running (PID $OLD_PID)"
    [[ -f "$RUN_FILE" ]] && echo "Run dir: $(cat "$RUN_FILE")"
    exit 0
  fi
fi

HOURS="${1:-8}"
INTERVAL="${VERIFY_INTERVAL:-300}"

cd "$ROOT"

NEW_PID="$(
  python3 - "$ROOT" "$LOG_DIR/verification_lane_stdout.log" "$HOURS" "$INTERVAL" <<'PY'
import os
import subprocess
import sys

root = sys.argv[1]
stdout_path = sys.argv[2]
hours = sys.argv[3]
interval = sys.argv[4]

cmd = [
    sys.executable,
    "scripts/verification_lane.py",
    "--hours", hours,
    "--interval", interval,
]

with open(stdout_path, "ab", buffering=0) as out:
    proc = subprocess.Popen(
        cmd,
        cwd=root,
        stdout=out,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
        env=os.environ.copy(),
    )

print(proc.pid)
PY
)"

echo "$NEW_PID" > "$PID_FILE"
echo "Started verification lane PID=$NEW_PID"
sleep 1
if [[ -f "$RUN_FILE" ]]; then
  echo "Run dir: $(cat "$RUN_FILE")"
fi
echo "Stdout: $LOG_DIR/verification_lane_stdout.log"

