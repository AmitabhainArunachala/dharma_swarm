#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
STATE_DIR="${HOME}/.dharma"
CONCLAVE_DIR="${STATE_DIR}/build_conclave"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="${CONCLAVE_DIR}/${RUN_ID}"
MISSION_FILE="${RUN_DIR}/night_mission.md"
MANIFEST_FILE="${RUN_DIR}/manifest.env"
INDEX_SESSION="${INDEX_SESSION_NAME:-dgc_repo_index}"

HOURS="${1:-8}"
TARGET_JST="${TARGET_JST:-04:30}"
MISSION_PROFILE="${MISSION_PROFILE:-workspace_auto}"
SEMANTIC_MAX_FILES="${SEMANTIC_MAX_FILES:-1200}"
SEMANTIC_MAX_BRIEFS="${SEMANTIC_MAX_BRIEFS:-5}"
INSTALL_MODE_PACK="${INSTALL_MODE_PACK:-1}"
START_DASHBOARD="${START_DASHBOARD:-1}"
START_REPO_INDEX="${START_REPO_INDEX:-1}"
START_DIRECTOR="${START_DIRECTOR:-1}"
START_CODEX_NIGHT="${START_CODEX_NIGHT:-1}"
START_CAFFEINE="${START_CAFFEINE:-1}"
START_MERGE_CONTROL="${START_MERGE_CONTROL:-0}"
CONTINUE_AFTER_TARGET="${CONTINUE_AFTER_TARGET:-0}"

mkdir -p "${RUN_DIR}" "${RUN_DIR}/index" "${RUN_DIR}/logs"

if [[ ! -d "${ROOT}" ]]; then
  echo "Missing repo directory: ${ROOT}" >&2
  exit 1
fi

cd "${ROOT}"

MISSION_PROFILE="${MISSION_PROFILE}" bash scripts/mission_preflight.sh | tee "${RUN_DIR}/logs/mission_preflight.log"

if [[ "${INSTALL_MODE_PACK}" == "1" ]]; then
  bash scripts/install_mode_pack.sh --target repo | tee "${RUN_DIR}/logs/mode_pack_install.log"
fi

if [[ "${START_DASHBOARD}" == "1" ]]; then
  bash scripts/dashboard_ctl.sh start | tee "${RUN_DIR}/logs/dashboard_ctl.log"
fi

cat > "${MISSION_FILE}" <<EOF
# Dharma Swarm Night Build Conclave

Run ID: ${RUN_ID}
Repo: ${ROOT}
Mission profile: ${MISSION_PROFILE}
Target window: ${HOURS}h with caffeine target ${TARGET_JST} JST

Primary objective:
Turn dharma_swarm into a more coherent operator product by improving the canonical dashboard/runtime/control-plane path while respecting existing local work.

Priority stack:
1. Preserve product shell stability on ports 3420 and 8420.
2. Strengthen the command-post / qwen / runtime / observatory surfaces as one system.
3. Build on tracked, canonical paths rather than local drift.
4. Prefer bounded implementation slices with focused verification.
5. Leave strong morning artifacts: semantic packet, xray packet, handoff, logs.

Workstreams:
- CEO lane: sharpen product wedge and decide what deserves top-level surface area.
- Research lane: digest repo structure, xray drift, map the real architecture.
- Director lane: keep the task stream coherent and pressure high-leverage seams.
- Codex lane: implement one bounded improvement per cycle with evidence.
- QA lane: keep runtime, provider, and test health visible through the night.

Hard rules:
- Do not commit, push, reset, or clean unrelated work.
- Do not create alternate control planes.
- Prefer canonical runtime scripts and tracked dashboard routes.
- If blocked, produce a concrete brief, report, or test seam instead of vague notes.
EOF

cat > "${MANIFEST_FILE}" <<EOF
RUN_ID='${RUN_ID}'
RUN_DIR='${RUN_DIR}'
MISSION_FILE='${MISSION_FILE}'
INDEX_SESSION='${INDEX_SESSION}'
HOURS='${HOURS}'
TARGET_JST='${TARGET_JST}'
MISSION_PROFILE='${MISSION_PROFILE}'
EOF

if [[ "${START_REPO_INDEX}" == "1" ]]; then
  INDEX_RUNNER="${RUN_DIR}/index/run_repo_index.sh"
  cat > "${INDEX_RUNNER}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '${ROOT}'
SUMMARY_FILE='${RUN_DIR}/index/summary.txt'
touch "\${SUMMARY_FILE}"

if command -v caffeinate >/dev/null 2>&1; then
  CAFFEINATE=(caffeinate -i)
else
  CAFFEINATE=()
fi

run_step() {
  local label="\$1"
  local log_file="\$2"
  shift 2
  printf '[%s] START %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\${label}" >> "\${SUMMARY_FILE}"
  if "\${CAFFEINATE[@]}" "\$@" > "\${log_file}" 2>&1; then
    printf '[%s] OK %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\${label}" >> "\${SUMMARY_FILE}"
  else
    printf '[%s] WARN %s failed\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\${label}" >> "\${SUMMARY_FILE}"
  fi
}

run_step digest '${RUN_DIR}/index/semantic_digest.log' \
  python3 -m dharma_swarm.dgc_cli semantic digest --root '${ROOT}' --include-tests --max-files '${SEMANTIC_MAX_FILES}'

run_step brief '${RUN_DIR}/index/semantic_brief.log' \
  python3 -m dharma_swarm.dgc_cli semantic brief --root '${ROOT}' --max-briefs '${SEMANTIC_MAX_BRIEFS}' --json-output '${RUN_DIR}/index/semantic_brief_packet.json' --markdown-output '${RUN_DIR}/index/semantic_brief_packet.md'

run_step xray '${RUN_DIR}/index/xray.log' \
  python3 -m dharma_swarm.dgc_cli xray '${ROOT}' --packet --output '${RUN_DIR}/xray'
EOF
  chmod +x "${INDEX_RUNNER}"

  if tmux has-session -t "${INDEX_SESSION}" 2>/dev/null; then
    echo "Repo index session '${INDEX_SESSION}' already running."
  else
    tmux new-session -d -s "${INDEX_SESSION}" "bash '${INDEX_RUNNER}'"
    echo "Started repo index session '${INDEX_SESSION}'"
  fi
fi

if [[ "${START_DIRECTOR}" == "1" ]]; then
  MISSION_PROFILE="${MISSION_PROFILE}" \
  USE_CAFFEINATE=1 \
  bash scripts/start_allout_tmux.sh "${HOURS}" | tee "${RUN_DIR}/logs/start_allout.log"
fi

if [[ "${START_CODEX_NIGHT}" == "1" ]]; then
  DGC_CODEX_NIGHT_MISSION_FILE="${MISSION_FILE}" \
  DGC_CODEX_NIGHT_LABEL="${RUN_ID}" \
  USE_CAFFEINATE=1 \
  bash scripts/start_codex_overnight_tmux.sh "${HOURS}" | tee "${RUN_DIR}/logs/start_codex_night.log"
fi

if [[ "${START_CAFFEINE}" == "1" ]]; then
  MISSION_PROFILE="${MISSION_PROFILE}" \
  CONTINUE_AFTER_4AM="${CONTINUE_AFTER_TARGET}" \
  USE_CAFFEINATE=1 \
  bash scripts/start_caffeine_tmux.sh "${TARGET_JST}" | tee "${RUN_DIR}/logs/start_caffeine.log"
fi

if [[ "${START_MERGE_CONTROL}" == "1" ]]; then
  MISSION_PROFILE="${MISSION_PROFILE}" \
  CONTINUE_AFTER_TARGET="${CONTINUE_AFTER_TARGET}" \
  USE_CAFFEINATE=1 \
  bash scripts/start_merge_control_tmux.sh "${TARGET_JST}" | tee "${RUN_DIR}/logs/start_merge_control.log"
fi

echo "${RUN_DIR}" > "${CONCLAVE_DIR}/latest_run.txt"

echo
echo "Night build conclave prepared."
echo "Run dir: ${RUN_DIR}"
echo "Mission file: ${MISSION_FILE}"
echo "Status: bash scripts/status_build_conclave.sh"
