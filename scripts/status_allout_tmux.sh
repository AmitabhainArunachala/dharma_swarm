#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_allout}"
LOG_DIR="${HOME}/.dharma/logs/allout"
HEARTBEAT_FILE="${HOME}/.dharma/allout_heartbeat.json"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}': RUNNING"
else
  echo "Session '${SESSION}': NOT RUNNING"
fi

if [[ -f "${HEARTBEAT_FILE}" ]]; then
  echo
  echo "Heartbeat:"
  cat "${HEARTBEAT_FILE}"
fi

LATEST_LOG="$(find "${LOG_DIR}" -name allout.log -type f 2>/dev/null | sort | tail -n1 || true)"
if [[ -n "${LATEST_LOG}" ]]; then
  echo
  echo "Latest log: ${LATEST_LOG}"
  echo "--- tail ---"
  tail -n 40 "${LATEST_LOG}"
fi

LATEST_REPORT="$(ls -1t "${HOME}/.dharma/shared"/compounding_24h_*.md 2>/dev/null | head -n1 || true)"
if [[ -n "${LATEST_REPORT}" ]]; then
  echo
  echo "Latest 24h report: ${LATEST_REPORT}"
fi
