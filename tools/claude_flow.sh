#!/usr/bin/env bash
# Claude Code Flow Loop
#
# "Keep going" mode. Reads a flow brief, executes bounded work cycles
# via claude -p, updates the brief after each cycle, repeats until
# time runs out or the work is done.
#
# Usage:
#   bash ~/dharma_swarm/tools/claude_flow.sh [--hours 4] [--dry-run] [--brief path]
#
# The brief file (~/.dharma/flow/brief.md) is the continuity mechanism.
# It's written by the /flow command before this script starts, capturing
# what the session was working on. Each cycle reads it, does work, updates it.

set -euo pipefail

STATE_DIR="$HOME/.dharma"
FLOW_DIR="$STATE_DIR/flow"
SESSION_ID=$(date -u +%Y%m%dT%H%M%SZ)
SESSION_DIR="$FLOW_DIR/$SESSION_ID"
AUDIT_LOG="$SESSION_DIR/audit.jsonl"
BRIEF_FILE="$FLOW_DIR/brief.md"

HOURS=4
CYCLE_TIMEOUT=900  # 15 minutes
MAX_DEAD_STREAK=5
DRY_RUN=false

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --hours) HOURS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --brief) BRIEF_FILE="$2"; shift 2 ;;
        --timeout) CYCLE_TIMEOUT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Claude binary
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.npm-global/bin/claude}"
if [[ ! -x "$CLAUDE_BIN" ]]; then
    CLAUDE_BIN=$(which claude 2>/dev/null || echo "")
fi
if [[ -z "$CLAUDE_BIN" ]]; then
    echo "ERROR: claude binary not found" >&2
    exit 1
fi

# Verify brief exists
if [[ ! -f "$BRIEF_FILE" ]]; then
    echo "ERROR: No flow brief at $BRIEF_FILE" >&2
    echo "Run /flow from a Claude Code session to generate the brief first." >&2
    exit 1
fi

mkdir -p "$SESSION_DIR"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log() {
    echo "[$(date -u +%H:%M:%S)] [flow] $1"
}

audit() {
    local event="$1"
    shift
    echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"session\":\"$SESSION_ID\",\"event\":\"$event\"$([ $# -gt 0 ] && echo ",$*")}" >> "$AUDIT_LOG"
}

# ---------------------------------------------------------------------------
# Cycle execution
# ---------------------------------------------------------------------------

run_cycle() {
    local cycle_num="$1"
    local cycle_id=$(printf "cycle_%04d" "$cycle_num")
    local cycle_dir="$SESSION_DIR/$cycle_id"
    mkdir -p "$cycle_dir"

    local brief_content
    brief_content=$(cat "$BRIEF_FILE")

    log "[$cycle_id] Starting cycle"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[$cycle_id] Dry run — skipping execution"
        audit "cycle" "\"cycle\":\"$cycle_id\",\"status\":\"dry_run\""
        return 0
    fi

    local prompt="You are continuing a flow session. Read the brief below carefully — it tells you what we're working on, what's done, and what to do next.

RULES:
- Do ONE bounded task from the 'What's next' list. The FIRST uncompleted item.
- Time limit: 15 minutes. Do not start anything you can't finish.
- After completing the task, verify it works (run tests if applicable).
- Do NOT commit, push, or modify git state.
- Respect the 'Rules' section in the brief.
- At the end, output exactly this format:
  FLOW_STATUS: completed|failed|blocked|done
  FLOW_SUMMARY: <one line describing what you did>
  FLOW_NEXT: <what the next cycle should work on>

If ALL items in 'What's next' are done, output:
  FLOW_STATUS: done
  FLOW_SUMMARY: All tasks complete
  FLOW_NEXT: none

--- FLOW BRIEF ---
$brief_content
--- END BRIEF ---"

    local output_file="$cycle_dir/output.txt"

    # Run Claude with timeout, suppress CLAUDECODE nesting issue
    env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT \
        timeout "${CYCLE_TIMEOUT}" \
        "$CLAUDE_BIN" -p "$prompt" \
        --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
        --permission-mode bypassPermissions \
        --output-format text \
        --max-turns 25 \
        2>&1 | tee "$output_file" || true

    # Parse status from output
    local status="unknown"
    local summary=""
    local next_task=""

    status=$(grep "^FLOW_STATUS:" "$output_file" 2>/dev/null | tail -1 | sed 's/FLOW_STATUS: *//' | tr -d '[:space:]' || echo "unknown")
    summary=$(grep "^FLOW_SUMMARY:" "$output_file" 2>/dev/null | tail -1 | sed 's/FLOW_SUMMARY: *//' || echo "")
    next_task=$(grep "^FLOW_NEXT:" "$output_file" 2>/dev/null | tail -1 | sed 's/FLOW_NEXT: *//' || echo "")

    # Fallback: check git diff for state change
    local files_changed
    files_changed=$(cd "$HOME/dharma_swarm" 2>/dev/null && git diff --name-only 2>/dev/null | wc -l | tr -d ' ' || echo "0")
    local untracked
    untracked=$(cd "$HOME/dharma_swarm" 2>/dev/null && git ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ' || echo "0")
    local total_changes=$((files_changed + untracked))

    if [[ "$status" == "unknown" || "$status" == "" ]]; then
        if [[ "$total_changes" -gt 0 ]]; then
            status="completed"
        else
            status="dead_cycle"
        fi
    fi

    log "[$cycle_id] Status: $status ($total_changes files changed)"
    [[ -n "$summary" ]] && log "[$cycle_id] $summary"

    audit "cycle" "\"cycle\":\"$cycle_id\",\"status\":\"$status\",\"changes\":$total_changes,\"summary\":\"$(echo "$summary" | tr '"' "'")\""

    # Update the brief with progress
    if [[ "$status" == "completed" && -n "$summary" ]]; then
        # Append to "What's done" section
        python3 -c "
import re, sys
brief = open('$BRIEF_FILE').read()

# Add to done section
done_marker = '## What\\'s done'
if done_marker in brief:
    brief = brief.replace(done_marker, done_marker + '\n- [cycle $cycle_num] $summary')

# Update next section if we have info
next_info = '''$next_task'''
if next_info and next_info != 'none':
    pass  # Let the next cycle figure it out from the brief

open('$BRIEF_FILE', 'w').write(brief)
" 2>/dev/null || true
    fi

    # Return status
    case "$status" in
        completed) return 0 ;;
        done) return 3 ;;  # Special: all work complete
        dead_cycle) return 2 ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

write_summary() {
    local total="$1" completed="$2" failed="$3" dead="$4" elapsed="$5"

    cat > "$SESSION_DIR/summary.md" << EOF
# Flow Session Summary — $SESSION_ID

**Duration**: ${elapsed}s | **Cycles**: $total | **Completed**: $completed | **Failed**: $failed | **Dead**: $dead

## Audit Trail
$(cat "$AUDIT_LOG" 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        if d.get('event') == 'cycle':
            print(f\"- [{d.get('status','?')}] {d.get('cycle','')} ({d.get('changes',0)} files) — {d.get('summary','')}\")
    except: pass
" 2>/dev/null || echo "- (no log)")

## Brief at End
$(cat "$BRIEF_FILE" 2>/dev/null | head -30)

*Session: $SESSION_ID*
EOF

    # Copy to shared for easy access
    cp "$SESSION_DIR/summary.md" "$FLOW_DIR/latest_summary.md" 2>/dev/null || true
    log "Summary: $SESSION_DIR/summary.md"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

log "=========================================="
log "  Claude Code Flow Loop"
log "  Session: $SESSION_ID"
log "  Hours: $HOURS | Dry run: $DRY_RUN"
log "  Brief: $BRIEF_FILE"
log "=========================================="

# Keep Mac awake
CAFFEINATE_PID=""
if command -v caffeinate &>/dev/null; then
    caffeinate -i -w $$ &
    CAFFEINATE_PID=$!
    log "caffeinate started (pid $CAFFEINATE_PID)"
fi

cleanup() {
    [[ -n "$CAFFEINATE_PID" ]] && kill "$CAFFEINATE_PID" 2>/dev/null || true
    log "Flow loop stopped"
}
trap cleanup EXIT

deadline=$(($(date +%s) + $(echo "$HOURS * 3600" | bc | cut -d. -f1)))
start_time=$(date +%s)

total=0
completed=0
failed=0
dead=0
dead_streak=0
cycle_num=0

audit "start" "\"hours\":$HOURS,\"brief\":\"$BRIEF_FILE\""

while true; do
    # Time check
    now=$(date +%s)
    if [[ $now -ge $deadline ]]; then
        log "Time's up ($HOURS hours)"
        break
    fi

    # Dead streak check
    if [[ $dead_streak -ge $MAX_DEAD_STREAK ]]; then
        log "Halting: $dead_streak consecutive dead cycles"
        break
    fi

    cycle_num=$((cycle_num + 1))
    total=$((total + 1))

    set +e
    run_cycle "$cycle_num"
    rc=$?
    set -e

    case $rc in
        0) completed=$((completed + 1)); dead_streak=0 ;;
        2) dead=$((dead + 1)); dead_streak=$((dead_streak + 1)) ;;
        3) completed=$((completed + 1)); log "All tasks complete — stopping"; break ;;
        *) failed=$((failed + 1)); dead_streak=0 ;;
    esac
done

elapsed=$(( $(date +%s) - start_time ))
audit "end" "\"total\":$total,\"completed\":$completed,\"failed\":$failed,\"dead\":$dead,\"elapsed\":$elapsed"

write_summary "$total" "$completed" "$failed" "$dead" "$elapsed"

log "=========================================="
log "  Flow Complete"
log "  Completed: $completed | Failed: $failed | Dead: $dead"
log "  Elapsed: ${elapsed}s"
log "=========================================="
