#!/usr/bin/env bash

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOME_DIR="${HOME}"
LAUNCH_AGENTS_DIR="${HOME_DIR}/Library/LaunchAgents"
LOG_DIR="${HOME_DIR}/.dharma/logs"
LAUNCH_DOMAIN="gui/${UID}"

API_LABEL="com.dharma.dashboard-api"
WEB_LABEL="com.dharma.dashboard-web"
API_TEMPLATE="${SCRIPT_DIR}/${API_LABEL}.plist"
WEB_TEMPLATE="${SCRIPT_DIR}/${WEB_LABEL}.plist"
API_DEST="${LAUNCH_AGENTS_DIR}/${API_LABEL}.plist"
WEB_DEST="${LAUNCH_AGENTS_DIR}/${WEB_LABEL}.plist"

render_template() {
    local src="$1"
    local dest="$2"
    sed \
        -e "s#__REPO_ROOT__#${REPO_ROOT}#g" \
        -e "s#__HOME__#${HOME_DIR}#g" \
        "$src" > "$dest"
    chmod 644 "$dest"
}

unload_if_present() {
    local plist="$1"
    launchctl bootout "${LAUNCH_DOMAIN}" "$plist" >/dev/null 2>&1 || true
}

load_plist() {
    local plist="$1"
    launchctl bootstrap "${LAUNCH_DOMAIN}" "$plist"
}

kickstart_label() {
    local label="$1"
    launchctl kickstart -k "${LAUNCH_DOMAIN}/${label}" >/dev/null 2>&1 || true
}

ensure_dashboard_build() {
    if [[ -f "${REPO_ROOT}/dashboard/.next/BUILD_ID" ]]; then
        return 0
    fi

    # Remove stale .next output (preserve cache for faster rebuilds)
    rm -rf "${REPO_ROOT}/dashboard/.next/static" \
           "${REPO_ROOT}/dashboard/.next/server" \
           "${REPO_ROOT}/dashboard/.next/build-manifest.json"

    (
        cd "${REPO_ROOT}/dashboard"
        npm run build
    )
}

status() {
    echo "Launch agents:"
    launchctl list | grep -E "${API_LABEL}|${WEB_LABEL}" || true
    echo
    echo "Listening ports:"
    lsof -n -P -iTCP:3420 -sTCP:LISTEN || true
    lsof -n -P -iTCP:8420 -sTCP:LISTEN || true
}

install() {
    mkdir -p "${LAUNCH_AGENTS_DIR}" "${LOG_DIR}"
    ensure_dashboard_build
    render_template "${API_TEMPLATE}" "${API_DEST}"
    render_template "${WEB_TEMPLATE}" "${WEB_DEST}"
    unload_if_present "${API_DEST}"
    unload_if_present "${WEB_DEST}"
    load_plist "${API_DEST}"
    load_plist "${WEB_DEST}"
    kickstart_label "${API_LABEL}"
    kickstart_label "${WEB_LABEL}"
    echo "Installed launch agents:"
    echo "  ${API_DEST}"
    echo "  ${WEB_DEST}"
}

uninstall() {
    unload_if_present "${API_DEST}"
    unload_if_present "${WEB_DEST}"
    rm -f "${API_DEST}" "${WEB_DEST}"
    echo "Removed launch agents."
}

restart() {
    install
}

usage() {
    cat <<'EOF'
Usage: bash scripts/install_dashboard_launch_agents.sh [install|restart|status|uninstall]
EOF
}

command="${1:-install}"
case "$command" in
    install) install ;;
    restart) restart ;;
    status) status ;;
    uninstall) uninstall ;;
    *)
        usage >&2
        exit 1
        ;;
esac
