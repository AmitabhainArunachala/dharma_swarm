#!/bin/bash
# dharma_swarm daemon launcher
# Runs the swarm in daemon mode (6h heartbeat from Garden Daemon config)
#
# Usage:
#   bash ~/dharma_swarm/run_daemon.sh          # foreground
#   bash ~/dharma_swarm/run_daemon.sh &         # background
#   launchctl load ~/Library/LaunchAgents/com.dhyana.dharma-swarm.plist  # persistent

set -e

cd ~/dharma_swarm

# --- Mission preflight (fail-closed) ---
MISSION_PREFLIGHT="${MISSION_PREFLIGHT:-1}"
if [[ "${MISSION_PREFLIGHT}" == "1" ]]; then
  scripts/mission_preflight.sh || {
    echo "[run_daemon] Preflight failed — daemon aborted." >&2
    exit 1
  }
fi

export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-$(grep -s OPENROUTER_API_KEY ~/.zshrc ~/.zprofile ~/.bash_profile 2>/dev/null | head -1 | sed 's/.*=//' | tr -d '"' | tr -d "'" | tr -d ' ')}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-$(grep -s ANTHROPIC_API_KEY ~/.zshrc ~/.zprofile ~/.bash_profile 2>/dev/null | head -1 | sed 's/.*=//' | tr -d '"' | tr -d "'" | tr -d ' ')}"

STATE_DIR="${HOME}/.dharma"
LOG_DIR="${STATE_DIR}/logs"
mkdir -p "$LOG_DIR"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) dharma_swarm daemon starting" | tee -a "$LOG_DIR/daemon.log"
echo "  state_dir: $STATE_DIR"
echo "  pid: $$"

# Write PID file
echo $$ > "$STATE_DIR/daemon.pid"

# Interval: 30s for interactive testing, omit --interval for full 6h daemon mode
INTERVAL="${DHARMA_INTERVAL:-30}"

# Enable verbose logging
export DHARMA_LOG_LEVEL="${DHARMA_LOG_LEVEL:-INFO}"

exec python3 -u -c "
import asyncio, logging, sys
logging.basicConfig(
    level=getattr(logging, '$DHARMA_LOG_LEVEL'),
    format='%(asctime)s %(name)s [%(levelname)s] %(message)s',
    stream=sys.stdout,
)

from dharma_swarm.swarm import SwarmManager

async def main():
    swarm = SwarmManager(state_dir='$STATE_DIR')
    await swarm.init()
    print(f'Crew ready. Thread: {swarm.current_thread}', flush=True)
    try:
        await swarm.run(interval=$INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        await swarm.shutdown()
        print('Daemon stopped.', flush=True)

asyncio.run(main())
" >> "$LOG_DIR/daemon.log" 2>&1
