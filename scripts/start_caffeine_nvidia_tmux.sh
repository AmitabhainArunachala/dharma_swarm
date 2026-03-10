#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
TARGET_JST="${1:-08:00}"
NVIDIA_ENV_FILE="${DGC_NVIDIA_ENV_FILE:-${HOME}/.dharma/env/nvidia_remote.env}"

if [[ "${TARGET_JST}" == "-h" || "${TARGET_JST}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  scripts/start_caffeine_nvidia_tmux.sh [HH:MM]

Examples:
  scripts/start_caffeine_nvidia_tmux.sh 08:00
  POLL_SECONDS=90 scripts/start_caffeine_nvidia_tmux.sh 04:00
EOF
  exit 0
fi

if [[ ! -d "${ROOT}" ]]; then
  echo "Missing repo directory: ${ROOT}"
  exit 1
fi

cd "${ROOT}"

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

# NVIDIA lane launcher explicitly arms accelerator mode unless caller overrides it.
export DGC_ACCELERATOR_MODE="${DGC_ACCELERATOR_MODE:-enabled}"
export DGC_NVIDIA_RAG_URL="${DGC_NVIDIA_RAG_URL:-http://127.0.0.1:8081/v1}"
export DGC_NVIDIA_INGEST_URL="${DGC_NVIDIA_INGEST_URL:-http://127.0.0.1:8082/v1}"
export DGC_DATA_FLYWHEEL_URL="${DGC_DATA_FLYWHEEL_URL:-http://127.0.0.1:8000/api}"
export POLL_SECONDS="${POLL_SECONDS:-120}"
export USE_CAFFEINATE="${USE_CAFFEINATE:-1}"
export AUTONOMY_PROFILE="${AUTONOMY_PROFILE:-workspace_auto}"
export MISSION_PROFILE="${MISSION_PROFILE:-${AUTONOMY_PROFILE}}"
export MISSION_PREFLIGHT="${MISSION_PREFLIGHT:-1}"
export MISSION_STRICT_CORE="${MISSION_STRICT_CORE:-1}"
export MISSION_REQUIRE_TRACKED="${MISSION_REQUIRE_TRACKED:-1}"
export MISSION_BLOCK_ON_FAIL="${MISSION_BLOCK_ON_FAIL:-1}"

echo "Launching caffeine tmux session until JST ${TARGET_JST}"
echo "RAG=${DGC_NVIDIA_RAG_URL}"
echo "INGEST=${DGC_NVIDIA_INGEST_URL}"
echo "FLYWHEEL=${DGC_DATA_FLYWHEEL_URL}"
echo "ACCELERATOR_MODE=${DGC_ACCELERATOR_MODE}"
echo "POLL_SECONDS=${POLL_SECONDS}"
echo "USE_CAFFEINATE=${USE_CAFFEINATE}"
echo "AUTONOMY_PROFILE=${MISSION_PROFILE}"
echo "MISSION_PREFLIGHT=${MISSION_PREFLIGHT}"
echo "MISSION_STRICT_CORE=${MISSION_STRICT_CORE}"
echo "MISSION_REQUIRE_TRACKED=${MISSION_REQUIRE_TRACKED}"
echo "MISSION_BLOCK_ON_FAIL=${MISSION_BLOCK_ON_FAIL}"

exec scripts/start_caffeine_tmux.sh "${TARGET_JST}"
