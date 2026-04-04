#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dharma_autonomous_cleanup}"
STATE_DIR="${DGC_AUTONOMOUS_CLEANUP_STATE_DIR:-${HOME}/.dharma/autonomous_cleanup}"
RUN_FILE="${STATE_DIR}/latest_run.txt"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}': RUNNING"
else
  echo "Session '${SESSION}': NOT RUNNING"
fi

if [[ -f "${RUN_FILE}" ]]; then
  echo
  RUN_DIR="$(cat "${RUN_FILE}")"
  echo "Run dir: ${RUN_DIR}"

  if [[ -f "${RUN_DIR}/manifest.env" ]]; then
    echo
    echo "Manifest:"
    cat "${RUN_DIR}/manifest.env"
  fi

  if [[ -f "${RUN_DIR}/autonomous_cleanup_prompt.md" ]]; then
    echo
    echo "Prompt:"
    sed -n '1,220p' "${RUN_DIR}/autonomous_cleanup_prompt.md"
  fi

  if [[ -f "${RUN_DIR}/claude_autonomous_cleanup.log" ]]; then
    echo
    echo "Latest log tail:"
    tail -n 40 "${RUN_DIR}/claude_autonomous_cleanup.log"
  fi
fi
