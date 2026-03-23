#!/bin/bash
# Deep Reading Daemon launcher
# Usage:
#   bash run_deep_reading.sh                     # One full cycle (immediate)
#   bash run_deep_reading.sh --skill deep-read   # Single skill
#   bash run_deep_reading.sh --daemon            # Loop forever (for launchd)
#   bash run_deep_reading.sh --background        # Fork to background
#   bash run_deep_reading.sh --once              # One cycle (explicit)

set -euo pipefail

cd "$(dirname "$0")"

# Source API keys from shell config
if [ -f "$HOME/.zshrc" ]; then
    eval "$(grep -E '^export (ANTHROPIC_API_KEY|OPENROUTER_API_KEY)=' "$HOME/.zshrc" 2>/dev/null || true)"
fi

# Ensure output dirs
mkdir -p "$HOME/.dharma/deep_reads/annotations" \
         "$HOME/.dharma/deep_reads/cycle_reports" \
         "$HOME/.dharma/logs"

# Log
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Deep Reading Daemon starting: $*" >> "$HOME/.dharma/logs/deep_reading.log"

# Run
exec /opt/homebrew/bin/python3 -u deep_reading_daemon.py "$@" 2>&1 | tee -a "$HOME/.dharma/logs/deep_reading.log"
