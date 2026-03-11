#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_codex_night}"
STATE_DIR="${DGC_CODEX_NIGHT_STATE_DIR:-${HOME}/.dharma}"
HEARTBEAT_FILE="${STATE_DIR}/codex_overnight_heartbeat.json"
RUN_FILE="${STATE_DIR}/codex_overnight_run_dir.txt"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}': RUNNING"
else
  echo "Session '${SESSION}': NOT RUNNING"
fi

if [[ -f "${RUN_FILE}" ]]; then
  echo
  echo "Run dir: $(cat "${RUN_FILE}")"
fi

if [[ -f "${HEARTBEAT_FILE}" ]]; then
  echo
  echo "Heartbeat:"
  cat "${HEARTBEAT_FILE}"
fi

LATEST_JSON="${STATE_DIR}/logs/codex_overnight/$(basename "$(cat "${RUN_FILE}" 2>/dev/null || echo "")")/latest.json"
if [[ -f "${LATEST_JSON}" ]]; then
  echo
  echo "Latest snapshot:"
  cat "${LATEST_JSON}"
fi
