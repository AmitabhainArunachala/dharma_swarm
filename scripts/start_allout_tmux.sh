#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dgc_allout}"
HOURS="${1:-6}"
POLL_SECONDS="${POLL_SECONDS:-300}"
FILES_PER_CYCLE="${FILES_PER_CYCLE:-10}"
TODO_MIN="${TODO_MIN:-3}"
TODO_MAX="${TODO_MAX:-5}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"
AUTONOMY_PROFILE="${AUTONOMY_PROFILE:-workspace_auto}"
MISSION_PROFILE="${MISSION_PROFILE:-${AUTONOMY_PROFILE}}"
NVIDIA_ENV_FILE="${DGC_NVIDIA_ENV_FILE:-${HOME}/.dharma/env/nvidia_remote.env}"

if [[ -f "${NVIDIA_ENV_FILE}" ]]; then
  incoming_rag="${DGC_NVIDIA_RAG_URL-}"
  incoming_ingest="${DGC_NVIDIA_INGEST_URL-}"
  incoming_flywheel="${DGC_DATA_FLYWHEEL_URL-}"
  incoming_nim_key="${NVIDIA_NIM_API_KEY-}"
  incoming_flywheel_key="${DGC_DATA_FLYWHEEL_API_KEY-}"
  incoming_autonomy="${AUTONOMY_PROFILE-}"
  incoming_mission="${MISSION_PROFILE-}"
  # shellcheck disable=SC1090
  source "${NVIDIA_ENV_FILE}"
  [[ -n "${incoming_rag}" ]] && DGC_NVIDIA_RAG_URL="${incoming_rag}"
  [[ -n "${incoming_ingest}" ]] && DGC_NVIDIA_INGEST_URL="${incoming_ingest}"
  [[ -n "${incoming_flywheel}" ]] && DGC_DATA_FLYWHEEL_URL="${incoming_flywheel}"
  [[ -n "${incoming_nim_key}" ]] && NVIDIA_NIM_API_KEY="${incoming_nim_key}"
  [[ -n "${incoming_flywheel_key}" ]] && DGC_DATA_FLYWHEEL_API_KEY="${incoming_flywheel_key}"
  [[ -n "${incoming_autonomy}" ]] && AUTONOMY_PROFILE="${incoming_autonomy}"
  [[ -n "${incoming_mission}" ]] && MISSION_PROFILE="${incoming_mission}"
fi

ACCEL_MODE="${DGC_ACCELERATOR_MODE:-}"
if [[ -z "${ACCEL_MODE}" ]]; then
  if [[ -n "${DGC_NVIDIA_RAG_URL:-}" || -n "${DGC_NVIDIA_INGEST_URL:-}" || -n "${DGC_DATA_FLYWHEEL_URL:-}" ]]; then
    ACCEL_MODE="enabled"
  else
    ACCEL_MODE="dormant"
  fi
fi

if [[ "${ACCEL_MODE}" == "0" || "${ACCEL_MODE}" == "off" || "${ACCEL_MODE}" == "disabled" || "${ACCEL_MODE}" == "none" || "${ACCEL_MODE}" == "dormant" ]]; then
  RAG_URL=""
  INGEST_URL=""
  FLYWHEEL_URL=""
else
  RAG_URL="${DGC_NVIDIA_RAG_URL:-http://127.0.0.1:8081/v1}"
  INGEST_URL="${DGC_NVIDIA_INGEST_URL:-http://127.0.0.1:8082/v1}"
  FLYWHEEL_URL="${DGC_DATA_FLYWHEEL_URL:-http://127.0.0.1:8000/api}"
fi
MISSION_PREFLIGHT="${MISSION_PREFLIGHT:-1}"
MISSION_STRICT_CORE="${MISSION_STRICT_CORE:-1}"
MISSION_REQUIRE_TRACKED="${MISSION_REQUIRE_TRACKED:-1}"
MISSION_BLOCK_ON_FAIL="${MISSION_BLOCK_ON_FAIL:-1}"

if [[ -z "${DGC_TRUST_MODE+x}" ]]; then
  case "${MISSION_PROFILE}" in
    readonly_audit|strict_external)
      DGC_TRUST_MODE="external_strict"
      ;;
    workspace_auto|yolo_local_container)
      DGC_TRUST_MODE="internal_yolo"
      ;;
    *)
      echo "Unknown autonomy profile: ${MISSION_PROFILE}"
      echo "Valid: readonly_audit, workspace_auto, strict_external, yolo_local_container"
      exit 64
      ;;
  esac
fi

mkdir -p "${HOME}/.dharma/logs/allout"

if [[ "${MISSION_PREFLIGHT}" == "1" ]]; then
  echo "Running mission preflight (blocking)..."
  (
    cd "${ROOT}" && \
    MISSION_PROFILE="${MISSION_PROFILE}" \
    MISSION_STRICT_CORE="${MISSION_STRICT_CORE}" \
    MISSION_REQUIRE_TRACKED="${MISSION_REQUIRE_TRACKED}" \
    MISSION_BLOCK_ON_FAIL="${MISSION_BLOCK_ON_FAIL}" \
    DGC_TRUST_MODE="${DGC_TRUST_MODE}" \
    scripts/mission_preflight.sh
  )
fi

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' already running. Use scripts/status_allout_tmux.sh"
  exit 0
fi

if [[ "${HOURS}" == "forever" ]]; then
  HOURS="0"
fi

runner="python3 scripts/thinkodynamic_director.py --hours '${HOURS}' --poll-seconds '${POLL_SECONDS}' --files-per-cycle '${FILES_PER_CYCLE}' --todo-min '${TODO_MIN}' --todo-max '${TODO_MAX}'"
if [[ "${USE_CAFFEINATE}" == "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  runner="caffeinate -i ${runner}"
fi

tmux_cmd="cd '${ROOT}' && \
DGC_NVIDIA_RAG_URL='${RAG_URL}' \
DGC_NVIDIA_INGEST_URL='${INGEST_URL}' \
DGC_DATA_FLYWHEEL_URL='${FLYWHEEL_URL}' \
DGC_ACCELERATOR_MODE='${ACCEL_MODE}' \
DGC_TRUST_MODE='${DGC_TRUST_MODE}' \
AUTONOMY_PROFILE='${MISSION_PROFILE}' \
${runner}"

tmux new-session -d -s "${SESSION}" "${tmux_cmd}"

echo "Started session '${SESSION}'"
echo "Hours: ${HOURS}"
if [[ "${HOURS}" == "0" ]]; then
  echo "Mode: continuous (no wall-clock stop)"
fi
echo "Poll seconds: ${POLL_SECONDS}"
echo "Files per cycle: ${FILES_PER_CYCLE}"
echo "TODO steps per cycle: ${TODO_MIN}-${TODO_MAX}"
echo "Use caffeinate: ${USE_CAFFEINATE}"
echo "Autonomy profile: ${MISSION_PROFILE}"
echo "Trust mode: ${DGC_TRUST_MODE}"
echo "Accelerator mode: ${ACCEL_MODE}"
echo "Use: scripts/status_allout_tmux.sh"
