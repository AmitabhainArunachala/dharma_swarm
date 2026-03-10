#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_thinkodynamic_director}"
STATE_DIR="${DGC_DIRECTOR_STATE_DIR:-${HOME}/.dharma}"
HEARTBEAT_FILE="${STATE_DIR}/thinkodynamic_director_heartbeat.json"
LOG_DIR="${STATE_DIR}/logs/thinkodynamic_director"
SUMMARY_FILE="${STATE_DIR}/shared/thinkodynamic_director_latest.md"

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

LATEST_JSON="${LOG_DIR}/latest.json"
if [[ -f "${LATEST_JSON}" ]]; then
  echo
  echo "Latest snapshot:"
  cat "${LATEST_JSON}"
fi

if [[ -f "${SUMMARY_FILE}" ]]; then
  echo
  echo "Summary file: ${SUMMARY_FILE}"
fi
