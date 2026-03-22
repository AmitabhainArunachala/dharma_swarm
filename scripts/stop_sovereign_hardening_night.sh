#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
LAUNCH_DOMAIN="gui/$(id -u)"
CRON_LABEL="com.dharma.cron-daemon"
ALL_OUT_SESSION="${ALL_OUT_SESSION_NAME:-dgc_allout_sovereign}"
CODEX_SESSION="${CODEX_SESSION_NAME:-dgc_codex_sovereign}"
CAFFEINE_SESSION="${CAFFEINE_SESSION_NAME:-dgc_caffeine_sovereign}"
STOP_CRON_DAEMON="${STOP_CRON_DAEMON:-0}"

# shellcheck disable=SC1091
source "${ROOT}/scripts/_tmux_session_fallbacks.sh"

echo "Stopping sovereign hardening night lanes..."

ACTIVE_ALL_OUT_SESSION="$(resolve_tmux_session "${ALL_OUT_SESSION}" dgc_allout || true)"
ACTIVE_CODEX_SESSION="$(resolve_tmux_session "${CODEX_SESSION}" dgc_codex_night || true)"
ACTIVE_CAFFEINE_SESSION="$(resolve_tmux_session "${CAFFEINE_SESSION}" dgc_caffeine || true)"

SESSION_NAME="${ACTIVE_ALL_OUT_SESSION:-${ALL_OUT_SESSION}}" bash "${ROOT}/scripts/stop_allout_tmux.sh" || true
SESSION_NAME="${ACTIVE_CODEX_SESSION:-${CODEX_SESSION}}" bash "${ROOT}/scripts/stop_codex_overnight_tmux.sh" || true
SESSION_NAME="${ACTIVE_CAFFEINE_SESSION:-${CAFFEINE_SESSION}}" bash "${ROOT}/scripts/stop_caffeine_tmux.sh" || true
bash "${ROOT}/scripts/stop_verification_lane.sh" || true

if [[ "${STOP_CRON_DAEMON}" == "1" ]]; then
  launchctl bootout "${LAUNCH_DOMAIN}/${CRON_LABEL}" > /dev/null 2>&1 || true
fi

echo "Stopped."
