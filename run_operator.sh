#!/usr/bin/env bash
# run_operator.sh -- Start the DHARMA COMMAND backend on :8420
#
# Usage:
#   bash run_operator.sh              # foreground
#   bash run_operator.sh --background # background (writes PID file)

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${HOME}/.dharma"
PID_FILE="${STATE_DIR}/operator.pid"
LOG_FILE="${STATE_DIR}/logs/operator.log"
PORT="${OPERATOR_PORT:-8420}"
HOST="${OPERATOR_HOST:-127.0.0.1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "${STATE_DIR}/logs" "${STATE_DIR}/db"

operator_cmd_matches() {
    local pid="$1"
    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    [[ "$cmd" == *"uvicorn"* && "$cmd" == *"api.main:app"* ]]
}

listening_pid() {
    lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1
}

wait_for_operator_ready() {
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

for envfile in "${HOME}/.env" "${HOME}/.dharma/.env" "${HOME}/.dharma/daemon.env"; do
    if [[ -f "$envfile" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$envfile"
        set +a
    fi
done

export DGC_ROUTER_TELEMETRY_ENABLE="${DGC_ROUTER_TELEMETRY_ENABLE:-1}"
export DGC_ROUTER_TELEMETRY_DB="${DGC_ROUTER_TELEMETRY_DB:-${STATE_DIR}/state/runtime.db}"

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "WARNING: OPENROUTER_API_KEY not set. Chat providers may run degraded." >&2
fi

if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
        if operator_cmd_matches "$old_pid"; then
            echo "Operator already running (PID $old_pid)"
            exit 0
        fi
        echo "Ignoring stale operator pid file pointing at non-operator PID $old_pid" >&2
    fi
    rm -f "$PID_FILE"
fi

existing_pid="$(listening_pid || true)"
if [[ -n "$existing_pid" ]]; then
    if operator_cmd_matches "$existing_pid"; then
        echo "$existing_pid" > "$PID_FILE"
        echo "Operator already running on port $PORT (PID $existing_pid)"
        exit 0
    fi
    echo "Port $PORT is already in use by PID $existing_pid; refusing to start a duplicate operator." >&2
    exit 1
fi

cd "$SCRIPT_DIR"

if [[ "${1:-}" == "--background" ]]; then
    nohup "$PYTHON_BIN" -m uvicorn api.main:app --host "$HOST" --port "$PORT" --log-level info --no-access-log \
        >> "$LOG_FILE" 2>&1 < /dev/null &
    new_pid="$!"
    if ! wait_for_operator_ready "$new_pid"; then
        rm -f "$PID_FILE"
        echo "Operator failed to stay up; inspect $LOG_FILE" >&2
        exit 1
    fi
    echo "$new_pid" > "$PID_FILE"
    echo "Operator started in background (PID $new_pid, port $PORT)"
    echo "Log: $LOG_FILE"
else
    echo "Starting operator on ${HOST}:$PORT..."
    echo "Press Ctrl+C to stop."
    exec "$PYTHON_BIN" -m uvicorn api.main:app --host "$HOST" --port "$PORT" --log-level info --no-access-log
fi
