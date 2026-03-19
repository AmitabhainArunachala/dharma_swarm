#!/usr/bin/env bash

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOME_DIR="${HOME}"
LAUNCH_AGENTS_DIR="${HOME_DIR}/Library/LaunchAgents"
STATE_DIR="${HOME_DIR}/.dharma"
LAUNCH_DOMAIN="gui/${UID}"

API_LABEL="com.dharma.dashboard-api"
WEB_LABEL="com.dharma.dashboard-web"
API_PLIST="${LAUNCH_AGENTS_DIR}/${API_LABEL}.plist"
WEB_PLIST="${LAUNCH_AGENTS_DIR}/${WEB_LABEL}.plist"
INSTALL_SCRIPT="${SCRIPT_DIR}/install_dashboard_launch_agents.sh"

kickstart_label() {
    local label="$1"
    launchctl kickstart -k "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 \
        || launchctl kickstart -k "${label}" >/dev/null 2>&1
}

unload_plist() {
    local plist="$1"
    launchctl bootout "${LAUNCH_DOMAIN}" "$plist" >/dev/null 2>&1 || true
}

ensure_loaded() {
    local label="$1"
    local plist="$2"
    launchctl print "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 \
        || launchctl bootstrap "${LAUNCH_DOMAIN}" "$plist"
}

ensure_installed() {
    if [[ ! -f "$API_PLIST" || ! -f "$WEB_PLIST" ]]; then
        bash "$INSTALL_SCRIPT" install
        return
    fi

    ensure_loaded "$API_LABEL" "$API_PLIST"
    ensure_loaded "$WEB_LABEL" "$WEB_PLIST"
}

status() {
    bash "$INSTALL_SCRIPT" status
    echo
    echo "PID files:"
    ls -l "${STATE_DIR}/operator.pid" "${STATE_DIR}/dashboard-ui.pid" 2>/dev/null || true
}

start() {
    ensure_installed
    kickstart_label "$API_LABEL"
    kickstart_label "$WEB_LABEL"
    sleep 2
    status
}

stop() {
    unload_plist "$API_PLIST"
    unload_plist "$WEB_PLIST"
    rm -f "${STATE_DIR}/operator.pid" "${STATE_DIR}/dashboard-ui.pid"
    echo "Dashboard launch agents stopped."
}

restart() {
    stop
    start
}

logs() {
    local lines="${2:-60}"
    echo "== API =="
    tail -n "$lines" "${STATE_DIR}/logs/dashboard-api.stdout.log" 2>/dev/null || true
    tail -n "$lines" "${STATE_DIR}/logs/dashboard-api.stderr.log" 2>/dev/null || true
    tail -n "$lines" "${STATE_DIR}/logs/operator.log" 2>/dev/null || true
    echo
    echo "== WEB =="
    tail -n "$lines" "${STATE_DIR}/logs/dashboard-web.stdout.log" 2>/dev/null || true
    tail -n "$lines" "${STATE_DIR}/logs/dashboard-web.stderr.log" 2>/dev/null || true
    tail -n "$lines" "${STATE_DIR}/logs/dashboard-ui.log" 2>/dev/null || true
}

usage() {
    cat <<'EOF'
Usage: bash scripts/dashboard_ctl.sh [install|start|stop|restart|status|logs]
EOF
}

command="${1:-status}"
case "$command" in
    install)
        bash "$INSTALL_SCRIPT" install
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs "$@"
        ;;
    *)
        usage >&2
        exit 1
        ;;
esac
