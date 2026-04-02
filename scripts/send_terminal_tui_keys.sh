#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dharma_terminal_tui}"

if [[ "$#" -lt 1 ]]; then
  echo "Usage: $0 <keys...>"
  echo "Example: $0 Tab Enter"
  exit 1
fi

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' not running."
  exit 1
fi

tmux send-keys -t "${SESSION}" "$@"
echo "Sent keys to '${SESSION}': $*"
