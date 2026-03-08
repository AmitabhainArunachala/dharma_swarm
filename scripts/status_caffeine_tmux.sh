#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_caffeine}"
LOG_DIR="${HOME}/.dharma/logs/caffeine"
HEARTBEAT_FILE="${HOME}/.dharma/caffeine_heartbeat.json"

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

LATEST_LOG="$(ls -1t "${LOG_DIR}"/caffeine_*.log 2>/dev/null | head -n1 || true)"
if [[ -n "${LATEST_LOG}" ]]; then
  echo
  echo "Latest log: ${LATEST_LOG}"
  echo "--- tail ---"
  tail -n 30 "${LATEST_LOG}"
fi
