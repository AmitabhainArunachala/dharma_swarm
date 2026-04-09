#!/usr/bin/env bash
# run_dashboard_ui.sh -- Start the DHARMA COMMAND frontend on :3420
#
# Usage:
#   bash scripts/run_dashboard_ui.sh              # foreground
#   bash scripts/run_dashboard_ui.sh --background # background (writes PID file)

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DASHBOARD_DIR="${REPO_ROOT}/dashboard"
STATE_DIR="${HOME}/.dharma"
PID_FILE="${STATE_DIR}/dashboard-ui.pid"
LOG_FILE="${STATE_DIR}/logs/dashboard-ui.log"
PORT="${DASHBOARD_PORT:-3420}"
HOST="${DASHBOARD_HOST:-127.0.0.1}"
NPM_BIN="${NPM_BIN:-npm}"

mkdir -p "${STATE_DIR}/logs"

ui_cmd_matches() {
    local pid="$1"
    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    [[ "$cmd" == *"next-server"* || "$cmd" == *"next start"* ]]
}

listening_pid() {
    lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1
}

wait_for_ui_ready() {
    local pid="$1"
    local attempts="${2:-20}"
    local sleep_seconds="${3:-1}"
    local observed_pid

    for ((i = 1; i <= attempts; i++)); do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 1
        fi

        observed_pid="$(listening_pid || true)"
        if [[ "$observed_pid" == "$pid" ]]; then
            return 0
        fi

        sleep "$sleep_seconds"
    done

    return 1
}

dashboard_build_stale() {
    local build_id="${DASHBOARD_DIR}/.next/BUILD_ID"
    if [[ ! -f "$build_id" ]]; then
        return 0
    fi

    if find "${DASHBOARD_DIR}" \
        \( -path "${DASHBOARD_DIR}/.next" -o -path "${DASHBOARD_DIR}/node_modules" \) -prune -o \
        -type f \
        \( \
            -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' -o \
            -name '*.css' -o -name '*.md' -o -name 'package.json' -o \
            -name 'package-lock.json' -o -name 'next.config.ts' \
        \) \
        -newer "$build_id" -print -quit | grep -q .
    then
        return 0
    fi

    return 1
}

ensure_dashboard_build() {
    if ! dashboard_build_stale; then
        return 0
    fi

    if [[ -f "${DASHBOARD_DIR}/.next/BUILD_ID" ]]; then
        echo "Dashboard build stale; running npm run build..."
    else
        echo "Dashboard build missing; running npm run build..."
    fi

    # Remove stale .next output (preserve cache for faster rebuilds)
    rm -rf "${DASHBOARD_DIR}/.next/static" \
           "${DASHBOARD_DIR}/.next/server" \
           "${DASHBOARD_DIR}/.next/BUILD_ID" \
           "${DASHBOARD_DIR}/.next/build-manifest.json"

    (
        cd "${DASHBOARD_DIR}"
        "${NPM_BIN}" run build
    ) >> "${LOG_FILE}" 2>&1
}

for envfile in "${HOME}/.env" "${HOME}/.dharma/.env" "${HOME}/.dharma/daemon.env"; do
    if [[ -f "$envfile" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$envfile"
        set +a
    fi
done

if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
        if ui_cmd_matches "$old_pid"; then
            echo "Dashboard UI already running (PID $old_pid)"
            exit 0
        fi
        echo "Ignoring stale dashboard pid file pointing at non-dashboard PID $old_pid" >&2
    fi
    rm -f "$PID_FILE"
fi

existing_pid="$(listening_pid || true)"
if [[ -n "$existing_pid" ]]; then
    if ui_cmd_matches "$existing_pid"; then
        echo "$existing_pid" > "$PID_FILE"
        echo "Dashboard UI already running on port $PORT (PID $existing_pid)"
        exit 0
    fi
    echo "Port $PORT is already in use by PID $existing_pid; refusing to start a duplicate dashboard UI." >&2
    exit 1
fi

ensure_dashboard_build

cd "$DASHBOARD_DIR"

if [[ "${1:-}" == "--background" ]]; then
    nohup "${NPM_BIN}" run start -- --hostname "$HOST" --port "$PORT" \
        >> "$LOG_FILE" 2>&1 < /dev/null &
    new_pid="$!"
    if ! wait_for_ui_ready "$new_pid"; then
        rm -f "$PID_FILE"
        echo "Dashboard UI failed to stay up; inspect $LOG_FILE" >&2
        exit 1
    fi
    echo "$new_pid" > "$PID_FILE"
    echo "Dashboard UI started in background (PID $new_pid, port $PORT)"
    echo "Log: $LOG_FILE"
else
    echo "Starting dashboard UI on ${HOST}:$PORT..."
    echo "Press Ctrl+C to stop."
    exec "${NPM_BIN}" run start -- --hostname "$HOST" --port "$PORT"
fi
