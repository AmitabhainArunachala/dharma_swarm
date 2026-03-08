#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dgc_caffeine}"
TARGET_JST="${1:-04:00}"
POLL_SECONDS="${POLL_SECONDS:-300}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"
CONTINUE_AFTER_4AM="${CONTINUE_AFTER_4AM:-0}"
AUTONOMY_PROFILE="${AUTONOMY_PROFILE:-workspace_auto}"
MISSION_PROFILE="${MISSION_PROFILE:-${AUTONOMY_PROFILE}}"
RAG_URL="${DGC_NVIDIA_RAG_URL:-http://127.0.0.1:8081/v1}"
INGEST_URL="${DGC_NVIDIA_INGEST_URL:-http://127.0.0.1:8082/v1}"
FLYWHEEL_URL="${DGC_DATA_FLYWHEEL_URL:-http://127.0.0.1:8000/api}"
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

mkdir -p "${HOME}/.dharma/logs/caffeine"

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
  echo "Session '${SESSION}' already running. Use scripts/status_caffeine_tmux.sh"
  exit 0
fi

runner="/bin/bash scripts/caffeine_until_jst.sh '${TARGET_JST}'"
if [[ "${USE_CAFFEINATE}" == "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  runner="caffeinate -i ${runner}"
fi

tmux_cmd="cd '${ROOT}' && \
DGC_NVIDIA_RAG_URL='${RAG_URL}' \
DGC_NVIDIA_INGEST_URL='${INGEST_URL}' \
DGC_DATA_FLYWHEEL_URL='${FLYWHEEL_URL}' \
DGC_TRUST_MODE='${DGC_TRUST_MODE}' \
AUTONOMY_PROFILE='${MISSION_PROFILE}' \
POLL_SECONDS='${POLL_SECONDS}' \
CONTINUE_AFTER_4AM='${CONTINUE_AFTER_4AM}' \
${runner}"

tmux new-session -d -s "${SESSION}" "${tmux_cmd}"
echo "Started session '${SESSION}'"
echo "Target JST: ${TARGET_JST}"
echo "Poll seconds: ${POLL_SECONDS}"
echo "Use caffeinate: ${USE_CAFFEINATE}"
echo "Continue after 04:00: ${CONTINUE_AFTER_4AM}"
echo "Autonomy profile: ${MISSION_PROFILE}"
echo "Trust mode: ${DGC_TRUST_MODE}"
echo "RAG URL: ${RAG_URL}"
echo "INGEST URL: ${INGEST_URL}"
echo "Flywheel URL: ${FLYWHEEL_URL}"
echo "Use: scripts/status_caffeine_tmux.sh"
