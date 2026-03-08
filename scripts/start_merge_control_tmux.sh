#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
SESSION="${SESSION_NAME:-dgc_merge_control}"
TARGET_JST="${1:-08:00}"
POLL_SECONDS="${POLL_SECONDS:-600}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"
CONTINUE_AFTER_TARGET="${CONTINUE_AFTER_TARGET:-0}"
MISSION_PROFILE="${MISSION_PROFILE:-workspace_auto}"
MERGE_STRICT_CORE="${MERGE_STRICT_CORE:-1}"
MERGE_REQUIRE_TRACKED="${MERGE_REQUIRE_TRACKED:-1}"
MERGE_RUN_TESTS="${MERGE_RUN_TESTS:-0}"
MERGE_APPEND_LEDGER="${MERGE_APPEND_LEDGER:-1}"

if [[ ! -d "${ROOT}" ]]; then
  echo "Missing repo directory: ${ROOT}"
  exit 1
fi

mkdir -p "${HOME}/.dharma/logs/merge_loop"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session '${SESSION}' already running. Use scripts/status_merge_control_tmux.sh"
  exit 0
fi

runner="/bin/bash scripts/merge_loop.sh '${TARGET_JST}'"
if [[ "${USE_CAFFEINATE}" == "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  runner="caffeinate -i ${runner}"
fi

tmux_cmd="cd '${ROOT}' && \
POLL_SECONDS='${POLL_SECONDS}' \
CONTINUE_AFTER_TARGET='${CONTINUE_AFTER_TARGET}' \
MISSION_PROFILE='${MISSION_PROFILE}' \
MERGE_STRICT_CORE='${MERGE_STRICT_CORE}' \
MERGE_REQUIRE_TRACKED='${MERGE_REQUIRE_TRACKED}' \
MERGE_RUN_TESTS='${MERGE_RUN_TESTS}' \
MERGE_APPEND_LEDGER='${MERGE_APPEND_LEDGER}' \
${runner}"

tmux new-session -d -s "${SESSION}" "${tmux_cmd}"

echo "Started session '${SESSION}'"
echo "Target JST: ${TARGET_JST}"
echo "Poll seconds: ${POLL_SECONDS}"
echo "Use caffeinate: ${USE_CAFFEINATE}"
echo "Continue after target: ${CONTINUE_AFTER_TARGET}"
echo "Profile: ${MISSION_PROFILE}"
echo "Strict core: ${MERGE_STRICT_CORE}"
echo "Require tracked: ${MERGE_REQUIRE_TRACKED}"
echo "Run tests each cycle: ${MERGE_RUN_TESTS}"
echo "Append ledger: ${MERGE_APPEND_LEDGER}"
echo "Use: scripts/status_merge_control_tmux.sh"
