#!/bin/bash
# OVERNIGHT CONTROLLER — manages 5-phase evolution spiral
# Runs until 8 AM JST or 2 full iterations, whichever comes first
# Each iteration: READ (45m) -> SYNTHESIZE (30m) -> IMPLEMENT (90m) -> VALIDATE (30m) -> CHECKPOINT (15m)

set -uo pipefail

# --- Mission preflight (fail-closed) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/mission_preflight.sh" || {
    echo "[overnight] Preflight failed — launch aborted." >&2
    exit 1
}

WORK_DIR="$HOME/.dharma/overnight"
SHARED="$HOME/.dharma/shared"
PROMPTS="$WORK_DIR/prompts"
LOG="$WORK_DIR/controller.log"
ITERATION=0
MAX_ITERATIONS=2

# Python-based timeout wrapper (macOS has no `timeout` command)
py_timeout() {
    local secs="$1"
    shift
    python3 -c "
import subprocess, sys, shlex
try:
    r = subprocess.run(sys.argv[1:], timeout=$secs, capture_output=False)
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    sys.exit(124)
" "$@"
}

# Run for 6 hours from now
START_TIME=$(date +%s)
END_TIME=$((START_TIME + 21600))  # 6 hours = 21600 seconds

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# Ensure shared directory exists
mkdir -p "$SHARED" "$WORK_DIR/artifacts" "$WORK_DIR/checkpoints"

# Clean stale outputs from previous runs (keep *_notes.md)
find "$SHARED" -name "allout_*" -mmin +120 -delete 2>/dev/null || true

log "=== OVERNIGHT CONTROLLER STARTED ==="
log "End time: $(date -r $END_TIME '+%Y-%m-%d %H:%M' 2>/dev/null || date -d @$END_TIME '+%Y-%m-%d %H:%M')"
log "Max iterations: $MAX_ITERATIONS"

# Record baseline test count (with 120s timeout — tests may hang)
BASELINE_TESTS=$(cd ~/dharma_swarm && python3 -c "
import subprocess, sys
try:
    r = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=no', '-x', '--timeout=10'],
                       capture_output=True, text=True, timeout=120)
    print(r.stdout.strip().split(chr(10))[-1])
except subprocess.TimeoutExpired:
    print('TIMEOUT after 120s')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1)
log "Baseline tests: $BASELINE_TESTS"
echo "$BASELINE_TESTS" > "$WORK_DIR/baseline_tests.txt"

wait_for_agents() {
    local phase_dir="$1"
    local max_wait="$2"  # seconds
    shift 2
    local files=("$@")
    local start=$(date +%s)

    while true; do
        sleep 30
        local done=0
        for f in "${files[@]}"; do
            [ -f "$phase_dir/$f" ] && [ -s "$phase_dir/$f" ] && done=$((done + 1))
        done
        local elapsed=$(( $(date +%s) - start ))
        log "  Waiting: $done/${#files[@]} done ($((elapsed/60))m elapsed)"

        if [ $done -ge ${#files[@]} ] || [ $elapsed -gt $max_wait ]; then
            break
        fi

        # Check stop signal
        if [ -f "$HOME/.dharma/.STOP" ]; then
            log "STOP signal received!"
            return 1
        fi

        # Check time budget
        if [ $(date +%s) -gt $END_TIME ]; then
            log "Time budget exceeded!"
            return 1
        fi
    done
    return 0
}

run_claude_agent() {
    local prompt_file="$1"
    local output_file="$2"
    local timeout_sec="$3"

    # Pipe prompt via stdin to avoid shell quoting issues with $(cat)
    # Unset CLAUDECODE env var so nested claude works from tmux
    python3 -c "
import subprocess, sys, os
env = dict(os.environ)
env.pop('CLAUDECODE', None)
env.pop('CLAUDE_CODE_ENTRY_POINT', None)
with open(sys.argv[1]) as f:
    prompt = f.read()
try:
    r = subprocess.run(
        ['claude', '-p', prompt, '--dangerously-skip-permissions', '--output-format', 'text'],
        capture_output=True, text=True, timeout=int(sys.argv[3]), env=env,
        cwd=os.path.expanduser('~/dharma_swarm')
    )
    with open(sys.argv[2], 'w') as out:
        out.write(r.stdout if r.stdout else '')
        if r.stderr:
            out.write('\n\nSTDERR:\n' + r.stderr)
except subprocess.TimeoutExpired:
    with open(sys.argv[2], 'w') as out:
        out.write('AGENT TIMED OUT after $timeout_sec seconds')
except Exception as e:
    with open(sys.argv[2], 'w') as out:
        out.write(f'AGENT ERROR: {e}')
" "$prompt_file" "$output_file" "$timeout_sec" || true
}

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    log ""
    log "=========================================="
    log "ITERATION $ITERATION / $MAX_ITERATIONS"
    log "=========================================="

    # Time check
    REMAINING=$(( END_TIME - $(date +%s) ))
    if [ $REMAINING -lt 3600 ]; then
        log "Less than 1 hour remaining. Stopping for safety."
        break
    fi
    log "Time remaining: $((REMAINING/3600))h $((REMAINING%3600/60))m"

    # Stop signal check
    [ -f "$HOME/.dharma/.STOP" ] && { log "Stop signal."; break; }

    # ============================================
    # PHASE 1: DEEP READ (3 parallel agents, 45min max)
    # ============================================
    log "--- PHASE 1: DEEP READ (3 agents, 45m max) ---"
    P1_DIR="$WORK_DIR/phase1/iter${ITERATION}"
    mkdir -p "$P1_DIR"

    # For iteration 2, prepend validation report to prompts
    if [ $ITERATION -gt 1 ]; then
        PREV_REPORT="$WORK_DIR/phase4/iter$((ITERATION-1))/VALIDATION_REPORT.md"
        if [ -f "$PREV_REPORT" ]; then
            for p in phase1_reader_a.txt phase1_reader_b.txt phase1_reader_c.txt; do
                ITER2_PROMPT="$PROMPTS/${p%.txt}_iter2.txt"
                {
                    echo "=== ITERATION 2 CONTEXT ==="
                    echo "The previous iteration produced this validation report. Focus on what REMAINS BROKEN or MISSING:"
                    echo ""
                    cat "$PREV_REPORT"
                    echo ""
                    echo "=== ORIGINAL PROMPT ==="
                    cat "$PROMPTS/$p"
                } > "$ITER2_PROMPT"
            done
            READER_A_PROMPT="$PROMPTS/phase1_reader_a_iter2.txt"
            READER_B_PROMPT="$PROMPTS/phase1_reader_b_iter2.txt"
            READER_C_PROMPT="$PROMPTS/phase1_reader_c_iter2.txt"
        else
            READER_A_PROMPT="$PROMPTS/phase1_reader_a.txt"
            READER_B_PROMPT="$PROMPTS/phase1_reader_b.txt"
            READER_C_PROMPT="$PROMPTS/phase1_reader_c.txt"
        fi
    else
        READER_A_PROMPT="$PROMPTS/phase1_reader_a.txt"
        READER_B_PROMPT="$PROMPTS/phase1_reader_b.txt"
        READER_C_PROMPT="$PROMPTS/phase1_reader_c.txt"
    fi

    # Launch 3 readers in parallel (background)
    run_claude_agent "$READER_A_PROMPT" "$P1_DIR/reader_a_findings.md" 2700 &
    PID_A=$!
    run_claude_agent "$READER_B_PROMPT" "$P1_DIR/reader_b_audit.md" 2700 &
    PID_B=$!
    run_claude_agent "$READER_C_PROMPT" "$P1_DIR/reader_c_patterns.md" 2700 &
    PID_C=$!

    log "  Launched readers: PIDs $PID_A $PID_B $PID_C"

    wait_for_agents "$P1_DIR" 2700 \
        "reader_a_findings.md" "reader_b_audit.md" "reader_c_patterns.md" || break

    # Wait for background processes to finish
    wait $PID_A $PID_B $PID_C 2>/dev/null

    log "Phase 1 complete. Output sizes:"
    for f in "$P1_DIR"/*.md; do
        [ -f "$f" ] && log "  $(basename $f): $(wc -l < $f) lines"
    done

    # ============================================
    # PHASE 2: SYNTHESIS (1 agent, 30min max)
    # ============================================
    log "--- PHASE 2: SYNTHESIS (1 agent, 30m max) ---"
    P2_DIR="$WORK_DIR/phase2/iter${ITERATION}"
    mkdir -p "$P2_DIR"

    run_claude_agent "$PROMPTS/phase2_synthesizer.txt" "$P2_DIR/synthesis_output.md" 1800 &
    PID_S=$!

    wait_for_agents "$P2_DIR" 1800 "synthesis_output.md" || break
    wait $PID_S 2>/dev/null

    log "Phase 2 complete."

    # ============================================
    # PHASE 3: IMPLEMENTATION (3 parallel agents, 90min max)
    # ============================================
    log "--- PHASE 3: IMPLEMENTATION (3 agents, 90m max) ---"
    P3_DIR="$WORK_DIR/phase3/iter${ITERATION}"
    mkdir -p "$P3_DIR"

    run_claude_agent "$PROMPTS/phase3_impl_core.txt" "$P3_DIR/impl_core_output.md" 5400 &
    PID_IC=$!
    run_claude_agent "$PROMPTS/phase3_impl_planner.txt" "$P3_DIR/impl_planner_output.md" 5400 &
    PID_IP=$!
    run_claude_agent "$PROMPTS/phase3_impl_safety.txt" "$P3_DIR/impl_safety_output.md" 5400 &
    PID_IS=$!

    log "  Launched implementers: PIDs $PID_IC $PID_IP $PID_IS"

    wait_for_agents "$P3_DIR" 5400 \
        "impl_core_output.md" "impl_planner_output.md" "impl_safety_output.md" || break

    wait $PID_IC $PID_IP $PID_IS 2>/dev/null

    log "Phase 3 complete. Output sizes:"
    for f in "$P3_DIR"/*.md; do
        [ -f "$f" ] && log "  $(basename $f): $(wc -l < $f) lines"
    done

    # ============================================
    # PHASE 4: TESTING/VALIDATION (1 agent, 30min max)
    # ============================================
    log "--- PHASE 4: VALIDATION (1 agent, 30m max) ---"
    P4_DIR="$WORK_DIR/phase4/iter${ITERATION}"
    mkdir -p "$P4_DIR"

    run_claude_agent "$PROMPTS/phase4_validator.txt" "$P4_DIR/validator_output.md" 1800 &
    PID_V=$!

    wait_for_agents "$P4_DIR" 1800 "validator_output.md" || break
    wait $PID_V 2>/dev/null

    log "Phase 4 complete."

    # ============================================
    # PHASE 5: CHECKPOINT
    # ============================================
    log "--- PHASE 5: CHECKPOINT ---"
    CHECKPOINT="$WORK_DIR/checkpoints/iteration_${ITERATION}.md"
    {
        echo "# Iteration $ITERATION Checkpoint"
        echo "## Time: $(date)"
        echo "## Elapsed: $(( ($(date +%s) - START_TIME) / 60 )) minutes"
        echo ""
        echo "## Test Suite Status:"
        cd ~/dharma_swarm && python3 -c "
import subprocess, sys
try:
    r = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=no', '-x', '--timeout=10'],
                       capture_output=True, text=True, timeout=120)
    for line in r.stdout.strip().split(chr(10))[-5:]: print(line)
except: print('TIMEOUT')
" 2>&1
        echo ""
        echo "## Phase 1 Outputs:"
        for f in "$P1_DIR"/*.md; do
            [ -f "$f" ] && echo "- $(basename $f): $(wc -l < "$f") lines"
        done
        echo ""
        echo "## Phase 2 Synthesis:"
        [ -f "$P2_DIR/synthesis_output.md" ] && echo "$(wc -l < "$P2_DIR/synthesis_output.md") lines"
        echo ""
        echo "## Phase 3 Implementation:"
        for f in "$P3_DIR"/*.md; do
            [ -f "$f" ] && echo "- $(basename $f): $(wc -l < "$f") lines"
        done
        echo ""
        echo "## Phase 4 Validation:"
        [ -f "$P4_DIR/validator_output.md" ] && head -30 "$P4_DIR/validator_output.md"
        echo ""
        echo "## Shared Notes:"
        ls -la "$SHARED"/*_notes.md 2>/dev/null || echo "No shared notes"
        echo ""
        echo "## Git Status:"
        cd ~/dharma_swarm && git diff --stat 2>/dev/null || echo "No git changes"
    } > "$CHECKPOINT" 2>&1

    log "Checkpoint written: $CHECKPOINT"
    log "Iteration $ITERATION complete."

done

# ============================================
# FINAL SUMMARY
# ============================================
log ""
log "=== OVERNIGHT CONTROLLER FINISHED ==="
TOTAL_SEC=$(( $(date +%s) - START_TIME ))
log "Iterations completed: $ITERATION"
log "Total runtime: $((TOTAL_SEC/3600))h $((TOTAL_SEC%3600/60))m"

{
    echo "# Overnight Run Summary"
    echo "Started: $(date -r $START_TIME '+%Y-%m-%d %H:%M' 2>/dev/null)"
    echo "Finished: $(date '+%Y-%m-%d %H:%M')"
    echo "Iterations: $ITERATION"
    echo "Runtime: $((TOTAL_SEC/3600))h $((TOTAL_SEC%3600/60))m"
    echo ""
    echo "## Baseline Tests (before overnight):"
    cat "$WORK_DIR/baseline_tests.txt"
    echo ""
    echo "## Final Tests (after overnight):"
    cd ~/dharma_swarm && python3 -c "
import subprocess, sys
try:
    r = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=short', '-x', '--timeout=10'],
                       capture_output=True, text=True, timeout=120)
    for line in r.stdout.strip().split(chr(10))[-20:]: print(line)
except: print('TIMEOUT')
" 2>&1
    echo ""
    echo "## Files Modified:"
    cd ~/dharma_swarm && git diff --stat 2>/dev/null || echo "Not tracked"
    echo ""
    echo "## All Outputs:"
    find "$WORK_DIR" -name "*.md" -newer "$WORK_DIR/start_time.txt" 2>/dev/null | sort
    echo ""
    echo "## Shared Notes:"
    for f in "$SHARED"/*_notes.md; do
        [ -f "$f" ] && echo "=== $(basename $f) ===" && head -20 "$f" && echo "..."
    done
} > "$WORK_DIR/artifacts/OVERNIGHT_SUMMARY.md" 2>&1

log "Summary written to: $WORK_DIR/artifacts/OVERNIGHT_SUMMARY.md"
log "=== DONE ==="
