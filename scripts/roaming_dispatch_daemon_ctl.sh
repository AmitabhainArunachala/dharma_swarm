#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_dir="${HOME}/.dharma/roaming"
mkdir -p "$state_dir"

pid_file="${state_dir}/roaming-dispatch-daemon.pid"
log_file="${state_dir}/roaming-dispatch-daemon.log"

db_path="${HOME}/.dharma/db/messages.db"
ledger_dir="${HOME}/.dharma/ledgers"
branch="roaming-fixall-20260326"
recipient="kimi-claw-phone"
responder="kimi-claw-phone"
interval="15"

usage() {
  cat <<EOF
Usage:
  bash scripts/roaming_dispatch_daemon_ctl.sh <start|stop|restart|status|run> [options]

Options:
  --db-path PATH
  --ledger-dir PATH
  --branch NAME
  --recipient NAME
  --responder NAME
  --interval SECONDS
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

action="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-path) db_path="$2"; shift 2 ;;
    --ledger-dir) ledger_dir="$2"; shift 2 ;;
    --branch) branch="$2"; shift 2 ;;
    --recipient) recipient="$2"; shift 2 ;;
    --responder) responder="$2"; shift 2 ;;
    --interval) interval="$2"; shift 2 ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

is_running() {
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_daemon() {
  if is_running; then
    echo "already running: pid $(cat "$pid_file")"
    echo "log: $log_file"
    return 0
  fi

  rm -f "$pid_file"

  (
    cd "$repo_root"
    exec env PYTHONPATH=. python3 -m dharma_swarm.roaming_dispatch_daemon \
      --db-path "$db_path" \
      --ledger-dir "$ledger_dir" \
      --repo-root "$repo_root" \
      --git-branch "$branch" \
      --recipient "$recipient" \
      --responder "$responder" \
      run-loop --interval "$interval"
  ) >>"$log_file" 2>&1 &

  local pid=$!
  echo "$pid" >"$pid_file"
  sleep 1
  if is_running; then
    echo "started: pid $pid"
    echo "log: $log_file"
    return 0
  fi

  echo "failed to start; tailing log:" >&2
  tail -n 40 "$log_file" >&2 || true
  return 1
}

run_foreground() {
  cd "$repo_root"
  exec env PYTHONPATH=. python3 -m dharma_swarm.roaming_dispatch_daemon \
    --db-path "$db_path" \
    --ledger-dir "$ledger_dir" \
    --repo-root "$repo_root" \
    --git-branch "$branch" \
    --recipient "$recipient" \
    --responder "$responder" \
    run-loop --interval "$interval"
}

stop_daemon() {
  if ! is_running; then
    rm -f "$pid_file"
    echo "not running"
    return 0
  fi
  local pid
  pid="$(cat "$pid_file")"
  kill "$pid" 2>/dev/null || true
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    echo "still running after TERM: pid $pid" >&2
    return 1
  fi
  rm -f "$pid_file"
  echo "stopped: pid $pid"
}

status_daemon() {
  if is_running; then
    echo "running: pid $(cat "$pid_file")"
  else
    echo "not running"
  fi
  echo "log: $log_file"
  if [[ -f "$log_file" ]]; then
    tail -n 20 "$log_file" || true
  fi
}

case "$action" in
  start) start_daemon ;;
  stop) stop_daemon ;;
  restart)
    stop_daemon || true
    start_daemon
    ;;
  status) status_daemon ;;
  run) run_foreground ;;
  *)
    usage
    exit 2
    ;;
esac
