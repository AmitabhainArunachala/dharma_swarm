#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
STATE="${HOME}/.dharma"
LOG_DIR="${STATE}/logs/merge_loop"
HEARTBEAT_FILE="${STATE}/merge_loop_heartbeat.json"

TARGET_JST="${1:-08:00}"
POLL_SECONDS="${POLL_SECONDS:-600}"
CONTINUE_AFTER_TARGET="${CONTINUE_AFTER_TARGET:-0}"
MISSION_PROFILE="${MISSION_PROFILE:-workspace_auto}"
STRICT_CORE="${MERGE_STRICT_CORE:-1}"
REQUIRE_TRACKED="${MERGE_REQUIRE_TRACKED:-1}"
RUN_TESTS="${MERGE_RUN_TESTS:-0}"
APPEND_LEDGER="${MERGE_APPEND_LEDGER:-1}"
IMPORT_LEGACY_ONCE="${MERGE_IMPORT_LEGACY_ONCE:-1}"
IMPORT_LEGACY_DONE_FILE="${STATE}/merge_import_legacy.done"
STATE_ONLY="${MERGE_STATE_ONLY:-1}"

mkdir -p "${LOG_DIR}" "${STATE}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LOG="${LOG_DIR}/merge_loop_${STAMP}.log"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${RUN_LOG}"
}

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

log "Starting merge-control loop"
log "Target JST: ${TARGET_JST}"
log "Target epoch: ${END_EPOCH}"
log "Continue after target: ${CONTINUE_AFTER_TARGET}"
log "Poll seconds: ${POLL_SECONDS}"
log "Mission profile: ${MISSION_PROFILE}"
log "State-only outputs: ${STATE_ONLY}"

if [[ "${IMPORT_LEGACY_ONCE}" == "1" ]] && [[ ! -f "${IMPORT_LEGACY_DONE_FILE}" ]]; then
  log "Running one-time legacy archive import bootstrap"
  set +e
  import_out="$(python3 scripts/import_legacy_archive.py 2>&1)"
  import_rc=$?
  set -e
  if [[ ${import_rc} -eq 0 ]]; then
    log "OK legacy-import rc=0"
    log "OUT ${import_out}"
    printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${IMPORT_LEGACY_DONE_FILE}"
  else
    log "WARN legacy-import rc=${import_rc}"
    log "OUT ${import_out}"
  fi
fi

cycle=0
while true; do
  cycle=$((cycle + 1))
  NOW_JST="$(TZ=Asia/Tokyo date +%H:%M)"
  NOW_EPOCH="$(date +%s)"

  if [[ "${CONTINUE_AFTER_TARGET}" != "1" ]] && (( NOW_EPOCH >= END_EPOCH )); then
    log "Reached target window (JST ${NOW_JST}); exiting."
    break
  fi

  log "Cycle ${cycle} start (JST ${NOW_JST})"

  cmd=(python3 scripts/merge_snapshot.py --profile "${MISSION_PROFILE}")
  if [[ "${STRICT_CORE}" == "1" ]]; then
    cmd+=(--strict-core)
  fi
  if [[ "${REQUIRE_TRACKED}" == "1" ]]; then
    cmd+=(--require-tracked)
  fi
  if [[ "${RUN_TESTS}" == "1" ]]; then
    cmd+=(--run-tests)
  fi
  if [[ "${APPEND_LEDGER}" == "1" ]]; then
    cmd+=(--append-ledger)
  fi
  if [[ "${STATE_ONLY}" == "1" ]]; then
    cmd+=(--state-only)
  fi

  set +e
  out="$(${cmd[@]} 2>&1)"
  rc=$?
  set -e

  if [[ ${rc} -eq 0 ]]; then
    log "OK merge-snapshot rc=0"
    log "OUT ${out}"
  else
    log "WARN merge-snapshot rc=${rc}"
    log "OUT ${out}"
  fi

  printf '{"ts_utc":"%s","cycle":%d,"jst":"%s","rc":%d,"log":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${cycle}" "${NOW_JST}" "${rc}" "${RUN_LOG}" \
    > "${HEARTBEAT_FILE}"

  log "Cycle complete; sleeping ${POLL_SECONDS}s"
  sleep "${POLL_SECONDS}"
done

log "Merge loop complete"
printf '{"ts_utc":"%s","cycle":%d,"status":"complete","log":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${cycle}" "${RUN_LOG}" \
  > "${HEARTBEAT_FILE}"

echo "Report log: ${RUN_LOG}"
