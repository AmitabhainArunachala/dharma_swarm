#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
STATE_DIR="${HOME}/.dharma"
RUN_ROOT="${STATE_DIR}/sovereign_hardening"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="${RUN_ROOT}/${RUN_ID}"
LOG_DIR="${RUN_DIR}/logs"
MANIFEST_FILE="${RUN_DIR}/manifest.env"
LATEST_RUN_FILE="${RUN_ROOT}/latest_run.txt"

HOURS="${1:-8}"
TARGET_JST="${2:-04:30}"
MISSION_FILE="${MISSION_FILE:-${ROOT}/docs/missions/SOVEREIGN_HARDENING_NIGHT_2026-03-20.md}"

ALL_OUT_SESSION="${ALL_OUT_SESSION_NAME:-dgc_allout_sovereign}"
CODEX_SESSION="${CODEX_SESSION_NAME:-dgc_codex_sovereign}"
CAFFEINE_SESSION="${CAFFEINE_SESSION_NAME:-dgc_caffeine_sovereign}"
READONLY_PROFILE="${READONLY_PROFILE:-readonly_audit}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"

BOOTSTRAP_CRON_DAEMON="${BOOTSTRAP_CRON_DAEMON:-1}"
START_ALL_OUT="${START_ALL_OUT:-1}"
START_CODEX="${START_CODEX:-1}"
START_VERIFICATION="${START_VERIFICATION:-1}"
START_CAFFEINE="${START_CAFFEINE:-1}"
VERIFY_DIFF_SCAN="${VERIFY_DIFF_SCAN:-1}"

CRON_PLIST="${ROOT}/scripts/com.dharma.cron-daemon.plist"
LAUNCH_DOMAIN="gui/$(id -u)"
CRON_LABEL="com.dharma.cron-daemon"
CODEX_LABEL="${CODEX_LABEL:-sovereign-hardening-${RUN_ID}}"

mkdir -p "${LOG_DIR}"

if [[ ! -d "${ROOT}" ]]; then
  echo "Missing repo directory: ${ROOT}" >&2
  exit 1
fi

if [[ ! -f "${MISSION_FILE}" ]]; then
  echo "Mission file not found: ${MISSION_FILE}" >&2
  exit 1
fi

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

run_and_log() {
  local name="$1"
  shift
  log "STEP ${name}: $*"
  "$@" > "${LOG_DIR}/${name}.log" 2>&1
  log "OK   ${name} -> ${LOG_DIR}/${name}.log"
}

session_exists_any() {
  local name
  for name in "$@"; do
    if tmux has-session -t "${name}" 2>/dev/null; then
      printf '%s\n' "${name}"
      return 0
    fi
  done
  return 1
}

cat > "${MANIFEST_FILE}" <<EOF
RUN_ID='${RUN_ID}'
RUN_DIR='${RUN_DIR}'
MISSION_FILE='${MISSION_FILE}'
HOURS='${HOURS}'
TARGET_JST='${TARGET_JST}'
ALL_OUT_SESSION='${ALL_OUT_SESSION}'
CODEX_SESSION='${CODEX_SESSION}'
CAFFEINE_SESSION='${CAFFEINE_SESSION}'
READONLY_PROFILE='${READONLY_PROFILE}'
CODEX_LABEL='${CODEX_LABEL}'
EOF

echo "${RUN_DIR}" > "${LATEST_RUN_FILE}"

cd "${ROOT}"

run_and_log split_brain_guard scripts/split_brain_guard.sh
run_and_log mission_preflight env MISSION_PROFILE="${READONLY_PROFILE}" scripts/mission_preflight.sh

if [[ "${VERIFY_DIFF_SCAN}" == "1" ]]; then
  run_and_log assurance_diff python3 -m dharma_swarm.assurance.run_scanners --diff-only
fi

if [[ "${BOOTSTRAP_CRON_DAEMON}" == "1" ]]; then
  if ! launchctl print "${LAUNCH_DOMAIN}/${CRON_LABEL}" > /dev/null 2>&1; then
    launchctl bootstrap "${LAUNCH_DOMAIN}" "${CRON_PLIST}" > "${LOG_DIR}/cron_bootstrap.log" 2>&1 || true
  fi
  launchctl kickstart -k "${LAUNCH_DOMAIN}/${CRON_LABEL}" >> "${LOG_DIR}/cron_bootstrap.log" 2>&1 || true
  log "OK   cron_bootstrap -> ${LOG_DIR}/cron_bootstrap.log"
fi

if [[ "${START_ALL_OUT}" == "1" ]]; then
  existing="$(session_exists_any "${ALL_OUT_SESSION}" dgc_allout || true)"
  if [[ -n "${existing}" ]]; then
    log "SKIP allout: session already running (${existing})"
  else
    run_and_log start_allout env \
      SESSION_NAME="${ALL_OUT_SESSION}" \
      AUTONOMY_PROFILE="${READONLY_PROFILE}" \
      MISSION_PROFILE="${READONLY_PROFILE}" \
      USE_CAFFEINATE="${USE_CAFFEINATE}" \
      scripts/start_allout_tmux.sh "${HOURS}"
  fi
fi

if [[ "${START_CODEX}" == "1" ]]; then
  existing="$(session_exists_any "${CODEX_SESSION}" dgc_codex_night || true)"
  if [[ -n "${existing}" ]]; then
    log "SKIP codex: session already running (${existing})"
  else
    run_and_log start_codex env \
      SESSION_NAME="${CODEX_SESSION}" \
      DGC_CODEX_NIGHT_MISSION_FILE="${MISSION_FILE}" \
      DGC_CODEX_NIGHT_LABEL="${CODEX_LABEL}" \
      USE_CAFFEINATE="${USE_CAFFEINATE}" \
      scripts/start_codex_overnight_tmux.sh "${HOURS}"
  fi
fi

if [[ "${START_VERIFICATION}" == "1" ]]; then
  run_and_log start_verification scripts/start_verification_lane.sh "${HOURS}"
fi

if [[ "${START_CAFFEINE}" == "1" ]]; then
  existing="$(session_exists_any "${CAFFEINE_SESSION}" dgc_caffeine || true)"
  if [[ -n "${existing}" ]]; then
    log "SKIP caffeine: session already running (${existing})"
  else
    run_and_log start_caffeine env \
      SESSION_NAME="${CAFFEINE_SESSION}" \
      AUTONOMY_PROFILE="${READONLY_PROFILE}" \
      MISSION_PROFILE="${READONLY_PROFILE}" \
      USE_CAFFEINATE="${USE_CAFFEINATE}" \
      scripts/start_caffeine_tmux.sh "${TARGET_JST}"
  fi
fi

cat <<EOF
Sovereign hardening night prepared.
Run dir: ${RUN_DIR}
Mission file: ${MISSION_FILE}
Status: bash scripts/status_sovereign_hardening_night.sh
Stop:   bash scripts/stop_sovereign_hardening_night.sh
EOF
