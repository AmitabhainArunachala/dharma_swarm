#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
STATE="${HOME}/.dharma"
LOG_DIR="${STATE}/logs/caffeine"
TODO_FILE="${ROOT}/docs/YOLO_4AM_TASKS.md"

TARGET_JST="${1:-04:00}"           # HH:MM (JST)
POLL_SECONDS="${POLL_SECONDS:-300}" # default 5 min
CONTINUE_AFTER_4AM="${CONTINUE_AFTER_4AM:-0}"
HEARTBEAT_FILE="${STATE}/caffeine_heartbeat.json"

mkdir -p "${LOG_DIR}" "${STATE}/shared"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LOG="${LOG_DIR}/caffeine_${STAMP}.log"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${RUN_LOG}"
}

run_step() {
  local label="$1"
  shift
  log "STEP ${label}: $*"
  if "$@" >>"${RUN_LOG}" 2>&1; then
    log "OK   ${label}"
  else
    log "WARN ${label} failed (continuing)"
  fi
}

if [[ ! -f "${TODO_FILE}" ]]; then
  log "Missing TODO file: ${TODO_FILE}"
  exit 1
fi

END_EPOCH="$(
python3 - <<PY
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

target = "${TARGET_JST}".strip()
hour, minute = [int(x) for x in target.split(":", 1)]

tz = ZoneInfo("Asia/Tokyo")
now = datetime.now(tz)
end = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
if now >= end:
    end += timedelta(days=1)
print(int(end.timestamp()))
PY
)"

log "Starting caffeine loop"
log "Target JST: ${TARGET_JST}"
log "Target epoch (next occurrence): ${END_EPOCH}"
log "Continue after target: ${CONTINUE_AFTER_4AM}"
log "Poll seconds: ${POLL_SECONDS}"
log "TODO file: ${TODO_FILE}"

cycle=0
while true; do
  cycle=$((cycle + 1))
  NOW_JST="$(TZ=Asia/Tokyo date +%H:%M)"
  NOW_EPOCH="$(date +%s)"

  if [[ "${CONTINUE_AFTER_4AM}" != "1" ]] && (( NOW_EPOCH >= END_EPOCH )); then
    log "Reached target window (JST ${NOW_JST}); exiting."
    break
  fi

  log "Cycle ${cycle} start (JST ${NOW_JST})"
  printf '{"ts_utc":"%s","cycle":%d,"jst":"%s","log":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${cycle}" "${NOW_JST}" "${RUN_LOG}" \
    > "${HEARTBEAT_FILE}"

  run_step "status" python3 -m dharma_swarm.dgc_cli status
  run_step "health-check" python3 -m dharma_swarm.dgc_cli health-check
  run_step "dharma-status" python3 -m dharma_swarm.dgc_cli dharma status

  if [[ -n "${DGC_NVIDIA_RAG_URL:-}" || -n "${DGC_NVIDIA_INGEST_URL:-}" ]]; then
    run_step "rag-health" python3 -m dharma_swarm.dgc_cli rag health --service rag
    run_step "ingest-health" python3 -m dharma_swarm.dgc_cli rag health --service ingest
  fi

  if [[ -n "${DGC_DATA_FLYWHEEL_URL:-}" ]]; then
    run_step "flywheel-jobs" python3 -m dharma_swarm.dgc_cli flywheel jobs
  fi

  run_step "tests-provider" python3 -m pytest -q tests/test_providers.py tests/test_providers_quality_track.py --tb=short
  run_step "tests-integrations" python3 -m pytest -q tests/test_integrations_nvidia_rag.py tests/test_integrations_data_flywheel.py --tb=short
  run_step "tests-engine" python3 -m pytest -q tests/test_engine_settings.py tests/test_engine_provider_runner.py --tb=short

  log "Cycle complete; sleeping ${POLL_SECONDS}s"
  sleep "${POLL_SECONDS}"
done

if [[ "${DGC_WRITE_24H_REPORT:-1}" == "1" ]]; then
  run_step "compounding-24h" python3 scripts/compounding_ledger.py --hours 24 --write
fi

log "Caffeine loop complete"
printf '{"ts_utc":"%s","cycle":%d,"status":"complete","log":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${cycle}" "${RUN_LOG}" \
  > "${HEARTBEAT_FILE}"
echo "Report log: ${RUN_LOG}"
