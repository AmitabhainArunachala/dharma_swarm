#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
cd "${ROOT}"

PROFILE="${MISSION_PROFILE:-${AUTONOMY_PROFILE:-workspace_auto}}"
AS_JSON="${MISSION_PREFLIGHT_JSON:-0}"

profile_strict_core=1
profile_require_tracked=1
profile_block_on_fail=1
profile_trust_mode="internal_yolo"

case "${PROFILE}" in
  readonly_audit)
    profile_trust_mode="external_strict"
    ;;
  workspace_auto)
    profile_trust_mode="internal_yolo"
    ;;
  strict_external)
    profile_trust_mode="external_strict"
    ;;
  yolo_local_container)
    profile_trust_mode="internal_yolo"
    ;;
  *)
    echo "[mission-preflight] FAIL: unknown autonomy profile '${PROFILE}'"
    echo "[mission-preflight] valid profiles: readonly_audit, workspace_auto, strict_external, yolo_local_container"
    exit 64
    ;;
esac

if [[ -z "${MISSION_STRICT_CORE+x}" ]]; then
  STRICT_CORE="${profile_strict_core}"
else
  STRICT_CORE="${MISSION_STRICT_CORE}"
fi

if [[ -z "${MISSION_REQUIRE_TRACKED+x}" ]]; then
  REQUIRE_TRACKED="${profile_require_tracked}"
else
  REQUIRE_TRACKED="${MISSION_REQUIRE_TRACKED}"
fi

if [[ -z "${MISSION_BLOCK_ON_FAIL+x}" ]]; then
  BLOCK_ON_FAIL="${profile_block_on_fail}"
else
  BLOCK_ON_FAIL="${MISSION_BLOCK_ON_FAIL}"
fi

if [[ -z "${DGC_TRUST_MODE+x}" ]]; then
  DGC_TRUST_MODE="${profile_trust_mode}"
fi
export DGC_TRUST_MODE

cmd=(python3 -m dharma_swarm.dgc_cli mission-status)
cmd+=(--profile "${PROFILE}")
if [[ "${STRICT_CORE}" == "1" ]]; then
  cmd+=(--strict-core)
fi
if [[ "${REQUIRE_TRACKED}" == "1" ]]; then
  cmd+=(--require-tracked)
fi
if [[ "${AS_JSON}" == "1" ]]; then
  cmd+=(--json)
fi

echo "[mission-preflight] profile=${PROFILE} trust_mode=${DGC_TRUST_MODE} strict_core=${STRICT_CORE} require_tracked=${REQUIRE_TRACKED} block_on_fail=${BLOCK_ON_FAIL}"
echo "[mission-preflight] running: ${cmd[*]}"
set +e
output="$("${cmd[@]}" 2>&1)"
rc=$?
set -e
printf '%s\n' "${output}"

if [[ ${rc} -eq 0 ]]; then
  echo "[mission-preflight] PASS"
  exit 0
fi

echo "[mission-preflight] FAIL (rc=${rc})"
if [[ "${BLOCK_ON_FAIL}" == "1" ]]; then
  echo "[mission-preflight] BLOCK_ON_FAIL=1 -> exiting non-zero"
  exit "${rc}"
fi

echo "[mission-preflight] continuing (BLOCK_ON_FAIL=0)"
exit 0
