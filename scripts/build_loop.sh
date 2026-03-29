#!/bin/bash
# dharma_swarm Autonomous Build Loop
# Based on Ralph Wiggum pattern + Anthropic scientific computing research
#
# Usage:
#   bash scripts/build_loop.sh                    # Run with defaults
#   bash scripts/build_loop.sh --max-iter 20      # Limit iterations
#   bash scripts/build_loop.sh --dry-run           # Show plan without executing
#
# Each iteration:
#   1. Reads build_queue.json for next pending task
#   2. Launches claude -p with fresh 200K context
#   3. Agent implements one task, runs tests, commits
#   4. Loop advances to next task
#
# State persists via filesystem (build_queue.json + progress.txt)
# Context resets every iteration — no rot, no compaction spirals

set -uo pipefail

QUEUE="$HOME/.dharma/build_loop/build_queue.json"
PROGRESS="$HOME/.dharma/build_loop/progress.txt"
PROMPT="$HOME/.dharma/build_loop/PROMPT_BUILD.md"
LOG_DIR="$HOME/.dharma/build_loop/logs"
MAX_ITER=50
MAX_TURNS=30
DRY_RUN=false
DEFAULT_MODEL="claude-sonnet-4-6"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --max-iter) MAX_ITER="$2"; shift 2 ;;
    --max-turns) MAX_TURNS="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --model) DEFAULT_MODEL="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

mkdir -p "$LOG_DIR"
cd "$HOME/dharma_swarm" || exit 1

echo "=== dharma_swarm Build Loop ==="
echo "Queue: $QUEUE"
echo "Max iterations: $MAX_ITER"
echo "Max turns/iter: $MAX_TURNS"
echo "Default model: $DEFAULT_MODEL"
echo ""

# Show queue summary
python3 -c "
import json
q = json.load(open('$QUEUE'))
by_status = {}
by_model = {}
for t in q:
    s = t['status']
    m = t.get('model', 'sonnet')
    by_status[s] = by_status.get(s, 0) + 1
    by_model[m] = by_model.get(m, 0) + 1
print(f'Tasks: {len(q)} total')
for s, c in sorted(by_status.items()):
    print(f'  {s}: {c}')
print(f'Models: {by_model}')
"

if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "DRY RUN — would execute the above queue. Exiting."
  exit 0
fi

echo ""
echo "Starting loop at $(date -u)"
echo ""

ITER=0
COMPLETED=0
FAILED=0
CONSECUTIVE_DEAD=0

while [ $ITER -lt $MAX_ITER ]; do
  ITER=$((ITER + 1))

  # Check remaining tasks
  PENDING=$(python3 -c "
import json
q = json.load(open('$QUEUE'))
print(sum(1 for t in q if t['status'] == 'pending'))
")

  if [ "$PENDING" -eq 0 ]; then
    echo ""
    echo "ALL TASKS COMPLETE"
    break
  fi

  # Get next task info
  TASK_INFO=$(python3 -c "
import json
q = json.load(open('$QUEUE'))
task = next((t for t in q if t['status'] == 'pending'), None)
if task:
    model = task.get('model', 'sonnet')
    print(f\"{task['id']}|{model}|{task['task'][:60]}\")
else:
    print('none|none|none')
")

  TASK_ID=$(echo "$TASK_INFO" | cut -d'|' -f1)
  TASK_MODEL=$(echo "$TASK_INFO" | cut -d'|' -f2)
  TASK_DESC=$(echo "$TASK_INFO" | cut -d'|' -f3)

  if [ "$TASK_ID" = "none" ]; then
    echo "No pending tasks found. Exiting."
    break
  fi

  # Map model shorthand
  case "$TASK_MODEL" in
    sonnet) MODEL_ID="claude-sonnet-4-6" ;;
    opus)   MODEL_ID="claude-opus-4-6" ;;
    *)      MODEL_ID="$DEFAULT_MODEL" ;;
  esac

  echo "[$(date -u +%H:%M:%S)] Iter $ITER: $TASK_ID ($MODEL_ID) — $TASK_DESC"

  # Run claude with fresh context
  claude -p "$(cat "$PROMPT")" \
    --allowedTools "Edit,Write,Read,Bash,Glob,Grep" \
    --model "$MODEL_ID" \
    --max-turns "$MAX_TURNS" \
    2>&1 | tee "$LOG_DIR/iter_$(printf '%03d' $ITER)_${TASK_ID}.log"

  # Check outcome
  STATUS=$(python3 -c "
import json
q = json.load(open('$QUEUE'))
task = next((t for t in q if t['id'] == '$TASK_ID'), None)
print(task['status'] if task else 'unknown')
")

  case "$STATUS" in
    completed)
      COMPLETED=$((COMPLETED + 1))
      CONSECUTIVE_DEAD=0
      echo "  -> COMPLETED ($COMPLETED total)"
      ;;
    failed)
      FAILED=$((FAILED + 1))
      CONSECUTIVE_DEAD=0
      echo "  -> FAILED ($FAILED total)"
      ;;
    pending)
      # Task still pending = agent didn't update queue (dead cycle)
      CONSECUTIVE_DEAD=$((CONSECUTIVE_DEAD + 1))
      echo "  -> DEAD CYCLE ($CONSECUTIVE_DEAD consecutive)"
      if [ $CONSECUTIVE_DEAD -ge 5 ]; then
        echo ""
        echo "5 consecutive dead cycles. Stopping."
        break
      fi
      ;;
  esac

  sleep 5
done

echo ""
echo "=========================================="
echo "Build Loop Complete"
echo "=========================================="
echo "Iterations: $ITER"
echo "Completed:  $COMPLETED"
echo "Failed:     $FAILED"
echo "Pending:    $PENDING"
echo "Finished:   $(date -u)"
echo "=========================================="

# Append summary to progress
echo "" >> "$PROGRESS"
echo "=== Loop Complete: $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$PROGRESS"
echo "Iterations: $ITER, Completed: $COMPLETED, Failed: $FAILED" >> "$PROGRESS"
