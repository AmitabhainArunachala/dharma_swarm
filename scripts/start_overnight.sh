#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/dharma_swarm"
STATE="$HOME/.dharma"
LOG_DIR="$STATE/logs"
PID_FILE="$STATE/overnight.pid"
RUN_FILE="$STATE/overnight_run_dir.txt"
STOP_FILE="$STATE/STOP_OVERNIGHT"

mkdir -p "$LOG_DIR"
rm -f "$STOP_FILE"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Overnight autopilot already running (PID $OLD_PID)"
    [[ -f "$RUN_FILE" ]] && echo "Run dir: $(cat "$RUN_FILE")"
    exit 0
  fi
fi

HOURS="${1:-8}"
POLL_SECONDS="${POLL_SECONDS:-600}"
MIN_PENDING="${MIN_PENDING:-6}"
TASKS_PER_LOOP="${TASKS_PER_LOOP:-3}"
DAEMON_INTERVAL="${DAEMON_INTERVAL:-60}"
QUALITY_EVERY_LOOPS="${QUALITY_EVERY_LOOPS:-6}"

cd "$ROOT"

NEW_PID="$(
  python3 - "$ROOT" "$LOG_DIR/overnight_supervisor_stdout.log" \
    "$HOURS" "$POLL_SECONDS" "$MIN_PENDING" "$TASKS_PER_LOOP" \
    "$DAEMON_INTERVAL" "$QUALITY_EVERY_LOOPS" <<'PY'
import os
import subprocess
import sys

root = sys.argv[1]
stdout_path = sys.argv[2]
hours = sys.argv[3]
poll_seconds = sys.argv[4]
min_pending = sys.argv[5]
tasks_per_loop = sys.argv[6]
daemon_interval = sys.argv[7]
quality_every = sys.argv[8]

cmd = [
    sys.executable,
    "scripts/overnight_autopilot.py",
    "--hours", hours,
    "--poll-seconds", poll_seconds,
    "--min-pending", min_pending,
    "--tasks-per-loop", tasks_per_loop,
    "--daemon-interval", daemon_interval,
    "--quality-every-loops", quality_every,
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
echo "Started overnight autopilot PID=$NEW_PID"
sleep 1
if [[ -f "$RUN_FILE" ]]; then
  echo "Run dir: $(cat "$RUN_FILE")"
fi
echo "Stdout: $LOG_DIR/overnight_supervisor_stdout.log"
