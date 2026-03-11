#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dgc_codex_night}"
STATE_DIR="${DGC_CODEX_NIGHT_STATE_DIR:-${HOME}/.dharma}"
HOURS="${1:-8}"
POLL_SECONDS="${POLL_SECONDS:-60}"
CYCLE_TIMEOUT="${CYCLE_TIMEOUT:-5400}"
MAX_CYCLES="${MAX_CYCLES:-0}"
MODEL="${DGC_CODEX_NIGHT_MODEL:-}"
MISSION_FILE="${DGC_CODEX_NIGHT_MISSION_FILE:-}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' already running."
  exit 0
fi

if [[ "${HOURS}" == "forever" ]]; then
  HOURS="0"
fi

mkdir -p "${STATE_DIR}"

runner="python3 scripts/codex_overnight_autopilot.py --hours '${HOURS}' --poll-seconds '${POLL_SECONDS}' --cycle-timeout '${CYCLE_TIMEOUT}' --state-dir '${STATE_DIR}'"
if [[ "${MAX_CYCLES}" != "0" ]]; then
  runner="${runner} --max-cycles '${MAX_CYCLES}'"
fi
if [[ -n "${MODEL}" ]]; then
  runner="${runner} --model '${MODEL}'"
fi
if [[ -n "${MISSION_FILE}" ]]; then
  runner="${runner} --mission-file '${MISSION_FILE}'"
fi

if [[ "${USE_CAFFEINATE}" == "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  runner="caffeinate -i ${runner}"
fi

tmux_cmd="cd '${ROOT}' && ${runner}"
tmux new-session -d -s "${SESSION}" "${tmux_cmd}"

echo "Started session '${SESSION}'"
echo "State dir: ${STATE_DIR}"
echo "Hours: ${HOURS}"
if [[ "${HOURS}" == "0" ]]; then
  echo "Mode: continuous (no wall-clock stop)"
fi
echo "Poll seconds: ${POLL_SECONDS}"
echo "Cycle timeout: ${CYCLE_TIMEOUT}"
echo "Model: ${MODEL:-default}"
echo "Use: scripts/status_codex_overnight_tmux.sh"
