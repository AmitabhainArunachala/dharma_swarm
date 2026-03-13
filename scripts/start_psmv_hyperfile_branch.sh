#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATE_TAG="$(TZ=Asia/Tokyo date +%Y%m%d)"
SESSION="${SESSION_NAME:-psmv_hyperfile_branch}"
VAULT_ROOT="${VAULT_ROOT:-${HOME}/Persistent-Semantic-Memory-Vault}"
STATE_DIR="${STATE_DIR:-${ROOT}/.dharma_psmv_hyperfile_branch}"
STAGE_DIR="${STAGE_DIR:-${ROOT}/reports/psmv_hyperfiles_${DATE_TAG}}"
MISSION_FILE="${MISSION_FILE:-${ROOT}/docs/missions/PSMV_HYPERFILE_BRANCH_2026-03-13.md}"
SOURCE_PACK="${SOURCE_PACK:-${ROOT}/docs/research/PSMV_AGENTIC_SOURCE_PACK_2026-03-13.json}"
MODE="${MODE:-direct}"
POLL_SECONDS="${POLL_SECONDS:-45}"
SIGNAL_LIMIT="${SIGNAL_LIMIT:-32}"
MAX_CANDIDATES="${MAX_CANDIDATES:-600}"
MAX_ACTIVE_TASKS="${MAX_ACTIVE_TASKS:-24}"
TARGET_COUNT="${TARGET_COUNT:-24}"
INTERNAL_LINKS="${INTERNAL_LINKS:-20}"
EXTERNAL_LINKS="${EXTERNAL_LINKS:-20}"
VAULT_MAX_FILES="${VAULT_MAX_FILES:-2500}"
REPO_MAX_FILES="${REPO_MAX_FILES:-900}"
USE_CAFFEINATE="${USE_CAFFEINATE:-1}"
PID_FILE="${STATE_DIR}/${SESSION}.pid"
LOG_FILE="${STATE_DIR}/${SESSION}.log"

if [[ ! -d "${VAULT_ROOT}" ]]; then
  echo "Vault root not found: ${VAULT_ROOT}" >&2
  exit 2
fi

if [[ ! -f "${MISSION_FILE}" ]]; then
  echo "Mission file not found: ${MISSION_FILE}" >&2
  exit 2
fi

if [[ ! -f "${SOURCE_PACK}" ]]; then
  echo "Source pack not found: ${SOURCE_PACK}" >&2
  exit 2
fi

HOURS="$(python3 - <<'PY'
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("Asia/Tokyo"))
cutoff = datetime.combine(now.date(), time(14, 0), tzinfo=ZoneInfo("Asia/Tokyo"))
remaining = (cutoff - now).total_seconds() / 3600.0
if remaining <= 0:
    raise SystemExit(1)
print(f"{remaining:.4f}")
PY
)" || {
  echo "The 14:00 JST cutoff has already passed; refusing to start." >&2
  exit 2
}

mkdir -p "${STATE_DIR}" "${STAGE_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  EXISTING_PID="$(cat "${PID_FILE}")"
  if [[ -n "${EXISTING_PID}" ]] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
    echo "Session '${SESSION}' already running with pid ${EXISTING_PID}."
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

RUNNER="cd '${ROOT}' && python3 scripts/psmv_hyperfile_bootstrap.py --repo-root '${ROOT}' --vault-root '${VAULT_ROOT}' --stage-dir '${STAGE_DIR}' --source-pack '${SOURCE_PACK}' --target-count '${TARGET_COUNT}' --internal-links '${INTERNAL_LINKS}' --external-links '${EXTERNAL_LINKS}' --vault-max-files '${VAULT_MAX_FILES}' --repo-max-files '${REPO_MAX_FILES}' && python3 scripts/thinkodynamic_director.py --hours '${HOURS}' --poll-seconds '${POLL_SECONDS}' --mode '${MODE}' --repo-root '${ROOT}' --state-dir '${STATE_DIR}' --scan-roots 'docs:scripts:dharma_swarm:tests:reports' --external-roots '${VAULT_ROOT}' --mission-file '${MISSION_FILE}' --signal-limit '${SIGNAL_LIMIT}' --max-candidates '${MAX_CANDIDATES}' --max-active-tasks '${MAX_ACTIVE_TASKS}'"
LAUNCH_CMD=(bash -lc "${RUNNER}")

if [[ "${USE_CAFFEINATE}" == "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  LAUNCH_CMD=(caffeinate -i "${LAUNCH_CMD[@]}")
fi

{
  echo "[launcher] $(date -u +%Y-%m-%dT%H:%M:%SZ) session=${SESSION}"
  echo "[launcher] cwd=${ROOT}"
  echo "[launcher] mode=${MODE} cutoff_hours=${HOURS}"
} >"${LOG_FILE}"

nohup "${LAUNCH_CMD[@]}" >>"${LOG_FILE}" 2>&1 &
LAUNCH_PID="$!"
echo "${LAUNCH_PID}" >"${PID_FILE}"

echo "Started session '${SESSION}'"
echo "PID: ${LAUNCH_PID}"
echo "Log file: ${LOG_FILE}"
echo "State dir: ${STATE_DIR}"
echo "Stage dir: ${STAGE_DIR}"
echo "Vault root: ${VAULT_ROOT}"
echo "Hours until cutoff: ${HOURS}"
echo "Mission file: ${MISSION_FILE}"
