#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_thinkodynamic_director}"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  tmux kill-session -t "${SESSION}"
  echo "Stopped session '${SESSION}'"
else
  echo "Session '${SESSION}' is not running"
fi
