#!/usr/bin/env bash
# run_overnight.sh — Master overnight launcher for dharma_swarm + Claude Code evolution
# Verifies all daemons running, starts missing ones, loads launchd plists,
# triggers initial evolution cascade, and sets up overnight logging.
#
# Usage: bash ~/dharma_swarm/run_overnight.sh
# Monitor: tail -f ~/.dharma/overnight/$(date +%Y-%m-%d).log

set -uo pipefail

LOG_DIR="$HOME/.dharma/overnight"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/${DATE}.log"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG"; }

log "=== OVERNIGHT EVOLUTION ENGINE START ==="
log "Date: $DATE | Host: $(hostname) | RAM: $(sysctl -n hw.memsize | awk '{printf "%.0fGB", $1/1073741824}')"

# ── 1. DGC Orchestrate-live (9 concurrent loops including replication monitor) ──
if pgrep -f "orchestrate_live" > /dev/null 2>&1; then
    PID=$(pgrep -f "orchestrate_live" | head -1)
    log "[OK] orchestrate-live running (PID $PID)"
else
    log "[START] orchestrate-live (background)"
    cd ~/dharma_swarm
    source ~/.zshrc 2>/dev/null || true
    nohup python3 -m dharma_swarm.orchestrate_live --background >> "$LOG" 2>&1 &
    sleep 2
    log "[STARTED] orchestrate-live (PID $!)"
fi

# ── 2. Garden Daemon (4 skills, 6h cycles) ──
if pgrep -f "garden_daemon" > /dev/null 2>&1; then
    PID=$(pgrep -f "garden_daemon" | head -1)
    log "[OK] garden daemon running (PID $PID)"
else
    log "[START] garden daemon"
    nohup bash ~/dharma_swarm/run_garden.sh --daemon >> "$LOG" 2>&1 &
    sleep 1
    log "[STARTED] garden daemon (PID $!)"
fi

# ── 3. Mycelium Daemon (Ollama local models) ──
if pgrep -f "mycelium/daemon.py" > /dev/null 2>&1; then
    PID=$(pgrep -f "mycelium/daemon.py" | head -1)
    log "[OK] mycelium daemon running (PID $PID)"
else
    # Check if Ollama is running first
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        log "[START] mycelium daemon (Ollama available)"
        nohup python3 ~/.dharma/mycelium/daemon.py >> "$LOG" 2>&1 &
        sleep 1
        log "[STARTED] mycelium daemon (PID $!)"
    else
        log "[SKIP] mycelium daemon (Ollama not running)"
    fi
fi

# ── 4. Deep Reading Daemon (8h cycles, lodestones + annotations) ──
if pgrep -f "deep_reading_daemon" > /dev/null 2>&1; then
    PID=$(pgrep -f "deep_reading_daemon" | head -1)
    log "[OK] deep reading daemon running (PID $PID)"
else
    if [ -f ~/dharma_swarm/run_deep_reading.sh ]; then
        log "[START] deep reading daemon"
        nohup bash ~/dharma_swarm/run_deep_reading.sh --daemon >> "$LOG" 2>&1 &
        sleep 1
        log "[STARTED] deep reading daemon (PID $!)"
    else
        log "[SKIP] deep reading daemon (script not found)"
    fi
fi

# ── 5. DGC Cron Daemon ──
if pgrep -f "dgc cron daemon" > /dev/null 2>&1; then
    log "[OK] dgc cron daemon running"
else
    log "[START] dgc cron daemon"
    nohup /opt/homebrew/bin/dgc cron daemon >> "$LOG" 2>&1 &
    sleep 1
    log "[STARTED] dgc cron daemon (PID $!)"
fi

# ── 6. Load launchd plists ──
log "--- Loading launchd plists ---"
LOADED=0
SKIPPED=0
for plist in ~/Library/LaunchAgents/com.dhyana.*.plist ~/Library/LaunchAgents/com.dharma.*.plist; do
    [ -f "$plist" ] || continue
    name=$(basename "$plist" .plist)
    if launchctl list "$name" > /dev/null 2>&1; then
        SKIPPED=$((SKIPPED + 1))
    else
        launchctl load "$plist" 2>/dev/null && LOADED=$((LOADED + 1)) || true
    fi
done
log "[LAUNCHD] Loaded $LOADED new, $SKIPPED already running"

# ── 7. Initial evolution trigger ──
log "--- Triggering evolution ---"
cd ~/dharma_swarm
/opt/homebrew/bin/dgc evolve trend >> "$LOG" 2>&1 || log "[WARN] dgc evolve failed (non-fatal)"

# ── 8. System health snapshot ──
log "--- System Health ---"
PROC_COUNT=$(ps aux | grep -E "orchestrate|garden|mycelium|deep_reading|dgc" | grep -v grep | wc -l | tr -d ' ')
log "Active daemon processes: $PROC_COUNT"
log "Stigmergy marks: $(wc -l < ~/.dharma/stigmergy/marks.jsonl 2>/dev/null || echo 0)"
log "Replication proposals: $(wc -l < ~/.dharma/replication/proposals.jsonl 2>/dev/null || echo 0)"
log "Garden cycles: $(ls ~/.dharma/garden/cycle_*.json 2>/dev/null | wc -l | tr -d ' ')"

# ── 9. Schedule morning summary ──
SUMMARY_TIME="04:00"
log "Morning summary scheduled for $SUMMARY_TIME"

# Run summary generator at 04:00 if overnight_summary.py exists
if [ -f ~/dharma_swarm/overnight_summary.py ]; then
    # Calculate seconds until 04:00
    NOW_EPOCH=$(date +%s)
    TARGET_EPOCH=$(date -j -f "%Y-%m-%d %H:%M" "$DATE 04:00" +%s 2>/dev/null || date -d "$DATE 04:00" +%s 2>/dev/null)
    if [ "$TARGET_EPOCH" -le "$NOW_EPOCH" ]; then
        TARGET_EPOCH=$((TARGET_EPOCH + 86400))  # Tomorrow 04:00
    fi
    SLEEP_SECS=$((TARGET_EPOCH - NOW_EPOCH))
    log "Summary will run in ${SLEEP_SECS}s (~$((SLEEP_SECS / 3600))h)"
    (sleep "$SLEEP_SECS" && python3 ~/dharma_swarm/overnight_summary.py >> "$LOG" 2>&1) &
fi

log "=== ALL SYSTEMS GO ==="
log "Monitor: tail -f $LOG"
log "Check: ps aux | grep -E 'orchestrate|garden|mycelium|deep_reading' | grep -v grep"
