#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_allout}"
LOG_DIR="${HOME}/.dharma/logs/thinkodynamic_director"
HEARTBEAT_FILE="${HOME}/.dharma/thinkodynamic_director_heartbeat.json"
LATEST_JSON="${LOG_DIR}/latest.json"
DIRECTOR_LOG="${LOG_DIR}/director.log"

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

if [[ -f "${LATEST_JSON}" ]]; then
  echo
  echo "Latest snapshot:"
  cat "${LATEST_JSON}"
fi

if [[ -f "${DIRECTOR_LOG}" ]]; then
  echo
  echo "Latest log: ${DIRECTOR_LOG}"
  echo "--- tail ---"
  tail -n 40 "${DIRECTOR_LOG}"
fi

LATEST_REPORT="$(ls -1t "${HOME}/.dharma/shared"/compounding_24h_*.md 2>/dev/null | head -n1 || true)"
if [[ -n "${LATEST_REPORT}" ]]; then
  echo
  echo "Latest 24h report: ${LATEST_REPORT}"
fi
