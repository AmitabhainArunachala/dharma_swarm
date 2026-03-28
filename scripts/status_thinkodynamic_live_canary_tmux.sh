#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION_NAME:-dgc_thinkodynamic_canary}"
STATE_DIR="${DGC_CANARY_STATE_DIR:-${HOME}/.dharma}"
LATEST_JSON="${STATE_DIR}/logs/thinkodynamic_canary/latest.json"
LATEST_MD="${STATE_DIR}/logs/thinkodynamic_canary/latest.md"

if tmux ls 2>/dev/null | grep -q "^${SESSION}:"; then
  echo "TMUX session '${SESSION}': PRESENT"
else
  echo "TMUX session '${SESSION}': MISSING"
fi

if ps auxww 2>/dev/null | grep -q "[t]hinkodynamic_live_canary.py"; then
  echo "Canary process: RUNNING"
else
  echo "Canary process: IDLE OR NOT RUNNING"
fi

if [[ -f "${LATEST_JSON}" ]]; then
  echo
  echo "Latest canary snapshot:"
  cat "${LATEST_JSON}"
fi

if [[ -f "${LATEST_MD}" ]]; then
  echo
  echo "Latest canary report:"
  cat "${LATEST_MD}"
fi
