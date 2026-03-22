#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
STATE_DIR="${HOME}/.dharma"
RUN_ROOT="${STATE_DIR}/sovereign_hardening"
LATEST_RUN_FILE="${RUN_ROOT}/latest_run.txt"
ALL_OUT_SESSION="${ALL_OUT_SESSION_NAME:-dgc_allout_sovereign}"
CODEX_SESSION="${CODEX_SESSION_NAME:-dgc_codex_sovereign}"
CAFFEINE_SESSION="${CAFFEINE_SESSION_NAME:-dgc_caffeine_sovereign}"
LAUNCH_DOMAIN="gui/$(id -u)"
CRON_LABEL="com.dharma.cron-daemon"

# shellcheck disable=SC1091
source "${ROOT}/scripts/_tmux_session_fallbacks.sh"

if [[ -f "${LATEST_RUN_FILE}" ]]; then
  RUN_DIR="$(cat "${LATEST_RUN_FILE}")"
else
  RUN_DIR=""
fi

echo "Run dir: ${RUN_DIR:-"(none)"}"

if [[ -n "${RUN_DIR}" && -f "${RUN_DIR}/manifest.env" ]]; then
  echo
  echo "== Manifest =="
  cat "${RUN_DIR}/manifest.env"
fi

echo
echo "== Cron daemon =="
if launchctl print "${LAUNCH_DOMAIN}/${CRON_LABEL}" > /dev/null 2>&1; then
  echo "${CRON_LABEL}: LOADED"
else
  echo "${CRON_LABEL}: NOT LOADED"
fi

echo
echo "== Split-brain guard =="
bash "${ROOT}/scripts/split_brain_guard.sh" || true

echo
echo "== Director lane =="
ACTIVE_ALL_OUT_SESSION="$(resolve_tmux_session "${ALL_OUT_SESSION}" dgc_allout || true)"
SESSION_NAME="${ACTIVE_ALL_OUT_SESSION:-${ALL_OUT_SESSION}}" bash "${ROOT}/scripts/status_allout_tmux.sh" || true

echo
echo "== Codex lane =="
ACTIVE_CODEX_SESSION="$(resolve_tmux_session "${CODEX_SESSION}" dgc_codex_night || true)"
SESSION_NAME="${ACTIVE_CODEX_SESSION:-${CODEX_SESSION}}" bash "${ROOT}/scripts/status_codex_overnight_tmux.sh" || true

echo
echo "== Verification lane =="
if [[ -f "${STATE_DIR}/verification_lane.pid" ]]; then
  PID="$(cat "${STATE_DIR}/verification_lane.pid" 2>/dev/null || true)"
  if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
    echo "verification_lane: RUNNING (PID ${PID})"
  else
    echo "verification_lane: NOT RUNNING"
  fi
else
  echo "verification_lane: NOT RUNNING"
fi

echo
echo "== Caffeine lane =="
ACTIVE_CAFFEINE_SESSION="$(resolve_tmux_session "${CAFFEINE_SESSION}" dgc_caffeine || true)"
SESSION_NAME="${ACTIVE_CAFFEINE_SESSION:-${CAFFEINE_SESSION}}" bash "${ROOT}/scripts/status_caffeine_tmux.sh" || true

if [[ -n "${RUN_DIR}" && -d "${RUN_DIR}/logs" ]]; then
  echo
  echo "== Launcher logs =="
  find "${RUN_DIR}/logs" -type f | sort | while read -r path; do
    echo "--- ${path} ---"
    tail -n 20 "${path}" || true
    echo
  done
fi
