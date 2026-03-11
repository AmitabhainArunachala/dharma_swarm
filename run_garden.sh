#!/bin/bash
# Garden Daemon launcher
# Usage:
#   bash run_garden.sh              # One full cycle (immediate)
#   bash run_garden.sh --quick      # Quick cycle (pulse + research only)
#   bash run_garden.sh --daemon     # Loop forever (for launchd)
#   bash run_garden.sh --skill hum  # Single skill

set -euo pipefail

cd "$(dirname "$0")"

# Source API keys from shell config
if [ -f "$HOME/.zshrc" ]; then
    eval "$(grep -E '^export (ANTHROPIC_API_KEY|OPENROUTER_API_KEY)=' "$HOME/.zshrc" 2>/dev/null || true)"
fi

# Ensure output dirs
mkdir -p "$HOME/.dharma/garden" "$HOME/.dharma/seeds" "$HOME/.dharma/subconscious" "$HOME/.dharma/logs"

# Log
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Garden Daemon starting: $*" >> "$HOME/.dharma/logs/garden.log"

# Run
exec /opt/homebrew/bin/python3 -u garden_daemon.py "$@" 2>&1 | tee -a "$HOME/.dharma/logs/garden.log"
