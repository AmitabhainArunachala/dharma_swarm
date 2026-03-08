#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_merge_control}"
LOG_DIR="${HOME}/.dharma/logs/merge_loop"
HEARTBEAT_FILE="${HOME}/.dharma/merge_loop_heartbeat.json"

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

LATEST_LOG="$(ls -1t "${LOG_DIR}"/merge_loop_*.log 2>/dev/null | head -n1 || true)"
if [[ -n "${LATEST_LOG}" ]]; then
  echo
  echo "Latest log: ${LATEST_LOG}"
  echo "--- tail ---"
  tail -n 40 "${LATEST_LOG}"
fi

LATEST_STATE="${HOME}/.dharma/merge/CANONICAL_STATE.md"
if [[ ! -f "${LATEST_STATE}" ]]; then
  LATEST_STATE="${HOME}/dharma_swarm/docs/merge/CANONICAL_STATE.md"
fi
if [[ -f "${LATEST_STATE}" ]]; then
  echo
  echo "Latest canonical state: ${LATEST_STATE}"
fi
