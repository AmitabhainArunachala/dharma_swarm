#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dharma_terminal_tui}"
LINES="${1:-120}"

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' not running."
  exit 1
fi

tmux capture-pane -pt "${SESSION}" -S "-${LINES}"
