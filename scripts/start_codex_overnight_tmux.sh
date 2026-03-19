#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dgc_codex_night}"
SOURCE_REPO_ROOT="${DGC_CODEX_NIGHT_REPO_ROOT:-${ROOT}}"
WORKTREE_ROOT="${DGC_CODEX_NIGHT_WORKTREE_ROOT:-}"
ISOLATE_WORKTREE="${DGC_CODEX_NIGHT_ISOLATE_WORKTREE:-0}"
STATE_DIR="${DGC_CODEX_NIGHT_STATE_DIR:-${HOME}/.dharma}"
HOURS="${1:-8}"
POLL_SECONDS="${POLL_SECONDS:-60}"
CYCLE_TIMEOUT="${CYCLE_TIMEOUT:-5400}"
MAX_CYCLES="${MAX_CYCLES:-0}"
MODEL="${DGC_CODEX_NIGHT_MODEL:-}"
MISSION_FILE="${DGC_CODEX_NIGHT_MISSION_FILE:-}"
LABEL="${DGC_CODEX_NIGHT_LABEL:-}"
YOLO="${DGC_CODEX_NIGHT_YOLO:-0}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' already running."
  exit 0
fi

if [[ "${HOURS}" == "forever" ]]; then
  HOURS="0"
fi

if [[ "${YOLO}" == "1" ]]; then
  if [[ "${HOURS}" == "8" ]]; then
    HOURS="10"
  fi
  if [[ -z "${POLL_SECONDS:-}" || "${POLL_SECONDS}" == "60" ]]; then
    POLL_SECONDS="20"
  fi
  if [[ -z "${CYCLE_TIMEOUT:-}" || "${CYCLE_TIMEOUT}" == "5400" ]]; then
    CYCLE_TIMEOUT="7200"
  fi
  if [[ -z "${LABEL}" ]]; then
    LABEL="allnight-yolo"
  fi
fi

mkdir -p "${STATE_DIR}"

runner="python3 scripts/codex_overnight_autopilot.py --hours '${HOURS}' --poll-seconds '${POLL_SECONDS}' --cycle-timeout '${CYCLE_TIMEOUT}' --repo-root '${SOURCE_REPO_ROOT}' --state-dir '${STATE_DIR}'"
if [[ "${MAX_CYCLES}" != "0" ]]; then
  runner="${runner} --max-cycles '${MAX_CYCLES}'"
fi
if [[ "${ISOLATE_WORKTREE}" == "1" ]]; then
  runner="${runner} --isolate-worktree"
fi
if [[ -n "${WORKTREE_ROOT}" ]]; then
  runner="${runner} --worktree-root '${WORKTREE_ROOT}'"
fi
if [[ -n "${MODEL}" ]]; then
  runner="${runner} --model '${MODEL}'"
fi
if [[ -n "${MISSION_FILE}" ]]; then
  runner="${runner} --mission-file '${MISSION_FILE}'"
fi
if [[ -n "${LABEL}" ]]; then
  runner="${runner} --label '${LABEL}'"
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
echo "Source repo: ${SOURCE_REPO_ROOT}"
echo "Isolate worktree: ${ISOLATE_WORKTREE}"
echo "Model: ${MODEL:-default}"
echo "Label: ${LABEL:-codex-overnight}"
echo "Mode: $([[ "${YOLO}" == "1" ]] && echo "YOLO" || echo "default")"
if [[ -n "${MISSION_FILE}" ]]; then
  echo "Mission file: ${MISSION_FILE}"
fi
echo "Use: scripts/status_codex_overnight_tmux.sh"
