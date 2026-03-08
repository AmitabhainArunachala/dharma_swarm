#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
TARGET_JST="${1:-08:00}"

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

# Safe defaults; caller can override with env vars.
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
echo "POLL_SECONDS=${POLL_SECONDS}"
echo "USE_CAFFEINATE=${USE_CAFFEINATE}"
echo "AUTONOMY_PROFILE=${MISSION_PROFILE}"
echo "MISSION_PREFLIGHT=${MISSION_PREFLIGHT}"
echo "MISSION_STRICT_CORE=${MISSION_STRICT_CORE}"
echo "MISSION_REQUIRE_TRACKED=${MISSION_REQUIRE_TRACKED}"
echo "MISSION_BLOCK_ON_FAIL=${MISSION_BLOCK_ON_FAIL}"

exec scripts/start_caffeine_tmux.sh "${TARGET_JST}"
