#!/usr/bin/env bash
# run_operator.sh — Start the Resident Operator (SwarmManager + FastAPI + uvicorn)
#
# Usage:
#   bash run_operator.sh              # foreground
#   bash run_operator.sh --background # background (writes PID file)
#
# The operator runs:
#   1. SwarmManager (all subsystems)
#   2. ResidentOperator (persistent conductor agent)
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

# Python startup script (inline)
STARTUP_SCRIPT=$(cat <<'PYEOF'
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

async def main():
    from dharma_swarm.resident_operator import ResidentOperator, OPERATOR_PORT
    from dharma_swarm.api import create_app

    port = int(os.environ.get("OPERATOR_PORT", OPERATOR_PORT))

    operator = ResidentOperator()
    app = create_app(operator=operator)

    import uvicorn
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
PYEOF
)

cd "${HOME}/dharma_swarm"

if [[ "${1:-}" == "--background" ]]; then
    echo "$STARTUP_SCRIPT" | python3 - >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Operator started in background (PID $(cat $PID_FILE), port $PORT)"
    echo "Log: $LOG_FILE"
else
    echo "Starting operator (port $PORT)..."
    echo "Press Ctrl+C to stop."
    echo "$STARTUP_SCRIPT" | python3 -
fi
