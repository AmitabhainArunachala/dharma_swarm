#!/usr/bin/env bash
# run_operator.sh — Start the canonical DHARMA COMMAND backend on :8420
#
# Usage:
#   bash run_operator.sh              # foreground
#   bash run_operator.sh --background # background (writes PID file)
#
# The backend runs:
#   1. SwarmManager
#   2. Resident operators (Claude + Codex)
#   3. FastAPI + uvicorn on port 8420 (localhost only)

set -euo pipefail

DHARMA_STATE="${HOME}/.dharma"
PID_FILE="${DHARMA_STATE}/operator.pid"
LOG_FILE="${DHARMA_STATE}/logs/operator.log"
PORT="${OPERATOR_PORT:-8420}"

mkdir -p "${DHARMA_STATE}/logs" "${DHARMA_STATE}/db"

# Source API keys if available
for envfile in "${HOME}/.env" "${HOME}/.dharma/.env"; do
    if [[ -f "$envfile" ]]; then
        set -a
        source "$envfile"
        set +a
    fi
done

# Ensure OPENROUTER_API_KEY is available
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "WARNING: OPENROUTER_API_KEY not set. Operator will use fallback providers."
fi

# Check for existing operator process
if [[ -f "$PID_FILE" ]]; then
    old_pid=$(cat "$PID_FILE")
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "Operator already running (PID $old_pid)"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

cd "${HOME}/dharma_swarm"

if [[ "${1:-}" == "--background" ]]; then
    python3 -m uvicorn api.main:app --host 127.0.0.1 --port "$PORT" --log-level info --no-access-log >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Operator started in background (PID $(cat $PID_FILE), port $PORT)"
    echo "Log: $LOG_FILE"
else
    echo "Starting operator (port $PORT)..."
    echo "Press Ctrl+C to stop."
    exec python3 -m uvicorn api.main:app --host 127.0.0.1 --port "$PORT" --log-level info --no-access-log
fi
