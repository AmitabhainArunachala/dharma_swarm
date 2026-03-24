#!/usr/bin/env bash
# Claude Code Overnight Loop
#
# Runs Claude Code in a tight time-boxed loop on dharma_swarm.
# Each cycle: pick a bounded task -> execute -> verify -> record -> next.
#
# Usage:
#   bash ~/dharma_swarm/tools/claude_overnight.sh [--hours 8] [--dry-run]
#
# What this does in plain language:
#   1. Looks at dharma_swarm and finds concrete work to do
#      (modules without tests, known bugs, coverage gaps)
#   2. Gives Claude Code ONE bounded task at a time
#   3. Sets a 15-minute timer per task
#   4. After each task, checks: did anything actually change?
#      If not, marks it as a dead cycle and moves on
#   5. Writes a morning brief so you know what happened
#   6. Stops when time runs out or tasks run out
#
# Inspired by Karpathy's AutoResearch: 630 lines, 700 experiments in 2 days.
# The trick is simplicity: time-box, verify, keep/discard, repeat.

set -euo pipefail

REPO_ROOT="$HOME/dharma_swarm"
STATE_DIR="$HOME/.dharma"
DATE=$(date -u +%Y-%m-%d)
RUN_DIR="$STATE_DIR/claude_overnight/$DATE"
AUDIT_LOG="$RUN_DIR/audit.jsonl"
MORNING_BRIEF="$RUN_DIR/morning_brief.md"
SHARED_BRIEF="$STATE_DIR/shared/claude_overnight_morning_brief.md"

HOURS="${1:-8}"
CYCLE_TIMEOUT=900  # 15 minutes per task
MAX_DEAD_STREAK=5

# Parse args
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --hours) HOURS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
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

mkdir -p "$RUN_DIR" "$STATE_DIR/shared"

# ---------------------------------------------------------------------------
# Task generation — find bounded, verifiable work
# ---------------------------------------------------------------------------

generate_tasks() {
    local tasks_file="$RUN_DIR/tasks.jsonl"

    # Use Python for reliable JSON generation and sorting
    python3 << 'PYEOF' > "$tasks_file"
import json, os
from pathlib import Path

repo = Path(os.environ.get("REPO_ROOT", Path.home() / "dharma_swarm"))
state = Path(os.environ.get("STATE_DIR", Path.home() / ".dharma"))
tasks = []

# Source 1: Modules without test files
src_dir = repo / "dharma_swarm"
test_dir = repo / "tests"
if src_dir.exists():
    for src in sorted(src_dir.glob("*.py")):
        if src.name.startswith("_"):
            continue
        module = src.stem
        test_file = test_dir / f"test_{module}.py"
        if not test_file.exists():
            lines = len(src.read_text(errors="ignore").splitlines())
            priority = min(lines / 100.0, 10.0)
            tasks.append({
                "task_id": f"test_{module}",
                "type": "test_coverage",
                "goal": f"Write smoke tests for {module}.py ({lines} lines)",
                "acceptance": f"pytest tests/test_{module}.py passes",
                "priority": round(priority, 1),
                "module": module,
            })

# Source 2: Human-curated queue
queue_file = state / "overnight" / "queue.yaml"
if queue_file.exists():
    try:
        import yaml
        data = yaml.safe_load(queue_file.read_text())
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict) and "goal" in item:
                    tasks.append({
                        "task_id": item.get("id", f"custom_{i}"),
                        "type": item.get("type", "custom"),
                        "goal": item["goal"],
                        "acceptance": item.get("acceptance", "Manual review"),
                        "priority": float(item.get("priority", 5.0)),
                        "module": "",
                    })
    except Exception:
        pass

# Sort by priority descending
tasks.sort(key=lambda t: t["priority"], reverse=True)

for t in tasks:
    print(json.dumps(t, ensure_ascii=True))
PYEOF

    local count=$(wc -l < "$tasks_file" | tr -d ' ')
    echo "$count"
}

# ---------------------------------------------------------------------------
# Execute one cycle via claude -p
# ---------------------------------------------------------------------------

run_cycle() {
    local cycle_num="$1"
    local task_json="$2"
    # Parse all fields in one Python call for reliability
    local parsed
    parsed=$(echo "$task_json" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    print(d.get('task_id', ''))
    print(d.get('goal', ''))
    print(d.get('acceptance', ''))
    print(d.get('module', ''))
except:
    print(''); print(''); print(''); print('')
" 2>/dev/null)
    local task_id goal acceptance module
    task_id=$(echo "$parsed" | sed -n '1p')
    goal=$(echo "$parsed" | sed -n '2p')
    acceptance=$(echo "$parsed" | sed -n '3p')
    module=$(echo "$parsed" | sed -n '4p')

    if [[ -z "$task_id" ]]; then
        echo "[$(date -u +%H:%M:%S)] [skip] Could not parse task JSON"
        return 1
    fi

    local cycle_id=$(printf "cycle_%04d" "$cycle_num")
    local cycle_dir="$RUN_DIR/$cycle_id"
    mkdir -p "$cycle_dir"

    local ts_start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "[$(date -u +%H:%M:%S)] [$cycle_id] Task: $task_id — $goal"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "{\"cycle\":\"$cycle_id\",\"task\":\"$task_id\",\"status\":\"dry_run\",\"ts\":\"$ts_start\"}" >> "$AUDIT_LOG"
        return 0
    fi

    # Build the prompt for Claude
    local prompt="You are running an overnight autonomous cycle on dharma_swarm.

Cycle: $cycle_num
Repo: $REPO_ROOT
Task ID: $task_id

GOAL: $goal

ACCEPTANCE CRITERION: $acceptance

RULES:
- You have 15 minutes maximum.
- Do ONE bounded thing. Not two. ONE.
- Write the code, then verify it works.
- If writing tests: run them with pytest and confirm they pass.
- Do NOT commit, push, or modify git state.
- Do NOT touch protected files: telos_gates.py, dharma_kernel.py, config.py
- If you cannot complete the task, explain why concisely and stop.
- At the end, output a summary line starting with 'RESULT:' followed by:
  - RESULT: completed — <what you did>
  - RESULT: failed — <why>
  - RESULT: blocked — <what you need>

$(if [[ -n "$module" ]]; then echo "The module to test is: dharma_swarm/${module}.py"; fi)
"

    # Run Claude with timeout
    local output_file="$cycle_dir/output.txt"

    # Unset CLAUDECODE to allow nesting
    env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT \
        timeout "${CYCLE_TIMEOUT}" \
        "$CLAUDE_BIN" -p "$prompt" \
        --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
        --permission-mode bypassPermissions \
        --output-format text \
        --max-turns 25 \
        2>&1 | tee "$output_file" || true

    local ts_end=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Check for state change (did any file get created/modified?)
    local files_changed=$(cd "$REPO_ROOT" && git diff --name-only 2>/dev/null | head -20)
    local untracked=$(cd "$REPO_ROOT" && git ls-files --others --exclude-standard 2>/dev/null | head -20)
    local all_changes="$files_changed"$'\n'"$untracked"
    all_changes=$(echo "$all_changes" | grep -v '^$' | head -20)
    local change_count=$(echo "$all_changes" | grep -c . 2>/dev/null || echo "0")

    # Parse result from output
    local result_line=$(grep "^RESULT:" "$output_file" 2>/dev/null | tail -1 || echo "")
    local status="unknown"
    if echo "$result_line" | grep -qi "completed"; then
        status="completed"
    elif echo "$result_line" | grep -qi "failed"; then
        status="failed"
    elif echo "$result_line" | grep -qi "blocked"; then
        status="blocked"
    elif [[ "$change_count" -gt 0 ]]; then
        status="completed"
    else
        status="dead_cycle"
    fi

    # If acceptance criterion is a pytest command, verify
    if [[ "$status" == "completed" ]] && echo "$acceptance" | grep -q "pytest"; then
        local test_target=$(echo "$acceptance" | grep -oP 'pytest \K\S+' || echo "")
        if [[ -n "$test_target" ]] && [[ -f "$REPO_ROOT/$test_target" ]]; then
            cd "$REPO_ROOT" && python3 -m pytest "$test_target" -q --tb=short 2>&1 | tee "$cycle_dir/verification.txt"
            if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
                status="failed"
            fi
        fi
    fi

    # Audit
    echo "{\"cycle\":\"$cycle_id\",\"task\":\"$task_id\",\"goal\":\"$goal\",\"status\":\"$status\",\"changes\":$change_count,\"ts_start\":\"$ts_start\",\"ts_end\":\"$ts_end\"}" >> "$AUDIT_LOG"

    echo "[$(date -u +%H:%M:%S)] [$cycle_id] Status: $status (${change_count} files changed)"

    # Return status via exit code
    case "$status" in
        completed) return 0 ;;
        dead_cycle) return 2 ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# Morning brief
# ---------------------------------------------------------------------------

write_morning_brief() {
    local total="$1"
    local completed="$2"
    local failed="$3"
    local dead="$4"

    cat > "$MORNING_BRIEF" << EOF
# Claude Code Overnight Brief — $DATE

**Duration**: ${HOURS}h | **Cycles**: $total | **Completed**: $completed | **Failed**: $failed | **Dead**: $dead

## Cycle Log

$(cat "$AUDIT_LOG" 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        status_icon = {'completed':'done','failed':'FAIL','dead_cycle':'DEAD','blocked':'BLOCK','dry_run':'DRY'}.get(d.get('status','?'),'?')
        print(f\"- [{status_icon}] {d.get('cycle','')} — {d.get('task','')} ({d.get('changes',0)} files)\")
    except: pass
" 2>/dev/null || echo "- (no log)")

## Action Items

- [ ] Review completed cycle outputs in \`$RUN_DIR/\`
- [ ] Check failed tasks for retry
- [ ] Review audit log: \`$AUDIT_LOG\`

*Generated at $(date -u +%Y-%m-%dT%H:%M:%SZ)*
EOF

    cp "$MORNING_BRIEF" "$SHARED_BRIEF" 2>/dev/null || true
    echo "[$(date -u +%H:%M:%S)] [director] Morning brief: $MORNING_BRIEF"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

echo "=============================================="
echo "  Claude Code Overnight Loop"
echo "  Date: $DATE"
echo "  Hours: $HOURS | Dry run: $DRY_RUN"
echo "=============================================="

# Generate tasks
task_count=$(generate_tasks)
echo "[$(date -u +%H:%M:%S)] [director] Staged $task_count tasks"

if [[ "$task_count" -eq 0 ]]; then
    echo "No tasks found. Exiting."
    write_morning_brief 0 0 0 0
    exit 0
fi

# Calculate deadline
deadline=$(($(date +%s) + $(echo "$HOURS * 3600" | bc | cut -d. -f1)))

# Counters
total=0
completed=0
failed=0
dead=0
dead_streak=0
cycle_num=0

# Read tasks and execute
while IFS= read -r task_json; do
    # Check deadline
    if [[ $(date +%s) -ge $deadline ]]; then
        echo "[$(date -u +%H:%M:%S)] [director] Time's up"
        break
    fi

    # Check dead streak
    if [[ $dead_streak -ge $MAX_DEAD_STREAK ]]; then
        echo "[$(date -u +%H:%M:%S)] [director] Halting: $dead_streak consecutive dead cycles"
        break
    fi

    cycle_num=$((cycle_num + 1))
    total=$((total + 1))

    set +e
    run_cycle "$cycle_num" "$task_json"
    rc=$?
    set -e

    case $rc in
        0) completed=$((completed + 1)); dead_streak=0 ;;
        2) dead=$((dead + 1)); dead_streak=$((dead_streak + 1)) ;;
        *) failed=$((failed + 1)); dead_streak=0 ;;
    esac

done < "$RUN_DIR/tasks.jsonl"

# Write morning brief
write_morning_brief "$total" "$completed" "$failed" "$dead"

echo "=============================================="
echo "  Overnight Complete"
echo "  Completed: $completed | Failed: $failed | Dead: $dead"
echo "=============================================="
