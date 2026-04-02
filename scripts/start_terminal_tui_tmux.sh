#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dharma_terminal_tui}"
STATE_DIR="${DHARMA_TERMINAL_TUI_STATE_DIR:-${HOME}/.dharma/terminal_tui}"
LOG_FILE="${STATE_DIR}/session.log"
TERMINAL_DIR="${ROOT}/terminal"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' already running."
  exit 0
fi

mkdir -p "${STATE_DIR}"

tmux new-session -d -s "${SESSION}" "cd '${TERMINAL_DIR}' && bun run src/index.tsx"
tmux pipe-pane -o -t "${SESSION}" "cat >> '${LOG_FILE}'"

echo "Started terminal TUI session '${SESSION}'"
echo "Terminal dir: ${TERMINAL_DIR}"
echo "State dir: ${STATE_DIR}"
echo "Log file: ${LOG_FILE}"
echo "Attach: tmux attach -t ${SESSION}"
echo "Capture: scripts/capture_terminal_tui_tmux.sh"
