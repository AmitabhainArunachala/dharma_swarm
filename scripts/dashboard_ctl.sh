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

service_port() {
    local label="$1"

    case "$label" in
        "$API_LABEL")
            printf '%s\n' "8420"
            ;;
        "$WEB_LABEL")
            printf '%s\n' "3420"
            ;;
        *)
            return 1
            ;;
    esac
}

http_ready() {
    local url="$1"
    local attempts="${2:-3}"
    local sleep_seconds="${3:-1}"

    for ((i = 1; i <= attempts; i++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$sleep_seconds"
    done

    return 1
}

service_is_ready() {
    local label="$1"

    case "$label" in
        "$API_LABEL")
            http_ready "http://127.0.0.1:8420/api/health"
            ;;
        "$WEB_LABEL")
            http_ready "http://127.0.0.1:3420/"
            ;;
        *)
            return 1
            ;;
    esac
}

listening_pid_for_label() {
    local label="$1"
    local port
    port="$(service_port "$label")" || return 1
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1
}

launch_job_pid() {
    local label="$1"
    launchctl print "${LAUNCH_DOMAIN}/${label}" 2>/dev/null \
        | awk '/^[[:space:]]*pid = / { print $3; exit }'
}

process_descends_from() {
    local child_pid="$1"
    local parent_pid="$2"
    local current_pid="$child_pid"
    local next_pid=""

    while [[ -n "$current_pid" && "$current_pid" != "0" ]]; do
        if [[ "$current_pid" == "$parent_pid" ]]; then
            return 0
        fi
        next_pid="$(ps -p "$current_pid" -o ppid= 2>/dev/null | tr -d '[:space:]')"
        if [[ -z "$next_pid" || "$next_pid" == "$current_pid" ]]; then
            break
        fi
        current_pid="$next_pid"
    done

    return 1
}

reconcile_service_owner() {
    local label="$1"
    local listening_pid=""
    local launch_pid=""

    listening_pid="$(listening_pid_for_label "$label" || true)"
    if [[ -z "$listening_pid" ]]; then
        return 0
    fi

    launch_pid="$(launch_job_pid "$label" || true)"
    if [[ -n "$launch_pid" ]] && process_descends_from "$listening_pid" "$launch_pid"; then
        return 0
    fi

    echo "Reconciling stray process on port $(service_port "$label") for ${label} (PID ${listening_pid})"
    kill "$listening_pid" >/dev/null 2>&1 || true
    sleep 1
}

kickstart_label() {
    local label="$1"
    local target="${LAUNCH_DOMAIN}/${label}"
    if service_is_ready "$label"; then
        return 0
    fi
    if launchctl kickstart -k "${target}" >/dev/null 2>&1; then
        return 0
    fi
    sleep 1
    if service_is_ready "$label"; then
        return 0
    fi
    launchctl kickstart -k "${target}" >/dev/null 2>&1 || service_is_ready "$label"
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
    reconcile_service_owner "$API_LABEL"
    reconcile_service_owner "$WEB_LABEL"
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
