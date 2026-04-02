#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dharma_terminal_tui}"
STATE_DIR="${DHARMA_TERMINAL_TUI_STATE_DIR:-${HOME}/.dharma/terminal_tui}"
LOG_FILE="${STATE_DIR}/session.log"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}': RUNNING"
else
  echo "Session '${SESSION}': NOT RUNNING"
fi

if [[ -f "${LOG_FILE}" ]]; then
  echo
  echo "Recent log:"
  tail -n 40 "${LOG_FILE}"
fi

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo
  echo "Pane snapshot:"
  tmux capture-pane -pt "${SESSION}" -S -80
fi
