#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dgc_thinkodynamic_director}"
STATE_DIR="${DGC_DIRECTOR_STATE_DIR:-${HOME}/.dharma}"
MODE="${DGC_DIRECTOR_MODE:-direct}"
HOURS="${1:-0}"
POLL_SECONDS="${POLL_SECONDS:-600}"
SIGNAL_LIMIT="${SIGNAL_LIMIT:-16}"
MAX_CANDIDATES="${MAX_CANDIDATES:-180}"
MAX_ACTIVE_TASKS="${MAX_ACTIVE_TASKS:-12}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' already running."
  exit 0
fi

mkdir -p "${STATE_DIR}"

runner="python3 scripts/thinkodynamic_director.py --hours '${HOURS}' --poll-seconds '${POLL_SECONDS}' --mode '${MODE}' --state-dir '${STATE_DIR}' --signal-limit '${SIGNAL_LIMIT}' --max-candidates '${MAX_CANDIDATES}' --max-active-tasks '${MAX_ACTIVE_TASKS}'"
if [[ "${USE_CAFFEINATE}" == "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  runner="caffeinate -i ${runner}"
fi

tmux_cmd="cd '${ROOT}' && ${runner}"
tmux new-session -d -s "${SESSION}" "${tmux_cmd}"

echo "Started session '${SESSION}'"
echo "Mode: ${MODE}"
echo "State dir: ${STATE_DIR}"
echo "Hours: ${HOURS}"
echo "Poll seconds: ${POLL_SECONDS}"
echo "Use: scripts/status_thinkodynamic_director_tmux.sh"
