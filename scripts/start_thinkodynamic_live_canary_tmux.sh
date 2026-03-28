#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dgc_thinkodynamic_canary}"
STATE_DIR="${DGC_CANARY_STATE_DIR:-${HOME}/.dharma}"
HOURS="${1:-8}"
INTERVAL_SECONDS="${CANARY_INTERVAL_SECONDS:-1800}"
MAX_ACTIVE_TASKS="${MAX_ACTIVE_TASKS:-16}"
MAX_CONCURRENT_TASKS="${MAX_CONCURRENT_TASKS:-1}"
MODE="${DGC_CANARY_MODE:-direct}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"
SESSION_LOG="${STATE_DIR}/logs/thinkodynamic_canary/session.log"

if tmux ls 2>/dev/null | grep -q "^${SESSION}:"; then
  echo "Session '${SESSION}' already running."
  exit 0
fi

mkdir -p "${STATE_DIR}/logs/thinkodynamic_canary"
rm -f "${STATE_DIR}/STOP_THINKODYNAMIC_CANARY"

runner="python3 scripts/thinkodynamic_live_canary.py --repo-root '${ROOT}' --state-dir '${STATE_DIR}' --hours '1' --max-cycles '1' --interval-seconds '${INTERVAL_SECONDS}' --max-active-tasks '${MAX_ACTIVE_TASKS}' --max-concurrent-tasks '${MAX_CONCURRENT_TASKS}' --mode '${MODE}' --preflight-probe"
if [[ "${USE_CAFFEINATE}" == "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  runner="caffeinate -i ${runner}"
fi

tmux_cmd="cd '${ROOT}' && END_EPOCH=\$(( \$(date +%s) + (${HOURS} * 3600) )); while [[ \$(date +%s) -lt \$END_EPOCH ]]; do ${runner} >> '${SESSION_LOG}' 2>&1; if [[ -f '${STATE_DIR}/STOP_THINKODYNAMIC_CANARY' ]]; then break; fi; sleep '${INTERVAL_SECONDS}'; done"
tmux new-session -d -s "${SESSION}" "${tmux_cmd}"

echo "Started session '${SESSION}'"
echo "Mode: ${MODE}"
echo "State dir: ${STATE_DIR}"
echo "Hours: ${HOURS}"
echo "Interval seconds: ${INTERVAL_SECONDS}"
echo "Use: scripts/status_thinkodynamic_live_canary_tmux.sh"
