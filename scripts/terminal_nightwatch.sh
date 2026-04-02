#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TERMINAL_DIR="$ROOT/terminal"
PYTHON_BIN="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/reports/generated/nightwatch"
STAMP="$(date +%Y%m%d)"
LOG_PATH="$LOG_DIR/terminal_nightwatch_${STAMP}.log"

mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*" | tee -a "$LOG_PATH"
}

run_check() {
  log "cycle:start"

  if (cd "$TERMINAL_DIR" && bunx tsc --noEmit) >>"$LOG_PATH" 2>&1; then
    log "check:tsc ok"
  else
    log "check:tsc failed"
  fi

  if "$PYTHON_BIN" -m py_compile "$ROOT/dharma_swarm/terminal_bridge.py" >>"$LOG_PATH" 2>&1; then
    log "check:py_compile ok"
  else
    log "check:py_compile failed"
  fi

  if printf '%s\n' \
    '{"id":"1","type":"workspace.snapshot"}' \
    '{"id":"2","type":"ontology.snapshot"}' \
    '{"id":"3","type":"runtime.snapshot"}' \
    | (cd "$ROOT" && "$PYTHON_BIN" -m dharma_swarm.terminal_bridge stdio) >>"$LOG_PATH" 2>&1; then
    log "check:bridge snapshots ok"
  else
    log "check:bridge snapshots failed"
  fi

  log "cycle:end"
}

log "nightwatch:boot root=$ROOT"
while true; do
  run_check
  sleep 300
done
