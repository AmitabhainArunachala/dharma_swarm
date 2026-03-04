#!/bin/bash
# Persistent agent loop — runs claude -p in a cycle until .STOP exists.
# Each cycle: read shared state, do work, write results, sleep, repeat.
#
# Usage: ./agent_loop.sh ROLE_NAME "role description"

ROLE_NAME="$1"
ROLE_DESC="$2"
SHARED="$HOME/.dharma/shared"
CYCLE=0

mkdir -p "$SHARED"

echo "[$ROLE_NAME] Starting persistent loop..."

while true; do
  # Check stop signal
  if [ -f "$HOME/.dharma/.STOP" ]; then
    echo "[$ROLE_NAME] Stop signal received. Exiting."
    break
  fi

  CYCLE=$((CYCLE + 1))
  NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Gather what other agents have written
  OTHER_NOTES=""
  for f in "$SHARED"/*_notes.md; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f")
    [ "$BASENAME" = "${ROLE_NAME}_notes.md" ] && continue
    # Last 20 lines from each other agent
    OTHER_NOTES="$OTHER_NOTES
--- $BASENAME ---
$(tail -20 "$f" 2>/dev/null)
"
  done

  # Build cycle prompt
  PROMPT="You are $ROLE_NAME in DHARMA SWARM, cycle $CYCLE ($NOW).

Your role: $ROLE_DESC

## What other agents have written recently:
$OTHER_NOTES

## Your previous notes:
$(tail -30 "$SHARED/${ROLE_NAME}_notes.md" 2>/dev/null || echo 'First cycle — no previous notes.')

## Instructions for this cycle:
1. Read other agents' recent notes above — build on or challenge them.
2. Do one concrete thing (read code, write code, run tests, check a claim).
3. Append what you did and found to ~/.dharma/shared/${ROLE_NAME}_notes.md
4. Be brief. One cycle = one action + one finding.

Work in ~/dharma_swarm/. Run tests with: cd ~/dharma_swarm && python3 -m pytest tests/ -q"

  echo "[$ROLE_NAME] Cycle $CYCLE starting..."

  # Run claude -p with timeout (3 min per cycle)
  timeout 180 claude -p "$PROMPT" --output-format text >> "$SHARED/${ROLE_NAME}_output_cycle${CYCLE}.md" 2>&1
  EXIT_CODE=$?

  if [ $EXIT_CODE -eq 124 ]; then
    echo "[$ROLE_NAME] Cycle $CYCLE timed out"
    echo "## Cycle $CYCLE — TIMEOUT at $NOW" >> "$SHARED/${ROLE_NAME}_notes.md"
  elif [ $EXIT_CODE -ne 0 ]; then
    echo "[$ROLE_NAME] Cycle $CYCLE failed (exit $EXIT_CODE)"
    echo "## Cycle $CYCLE — ERROR (exit $EXIT_CODE) at $NOW" >> "$SHARED/${ROLE_NAME}_notes.md"
  else
    echo "[$ROLE_NAME] Cycle $CYCLE complete"
  fi

  # Sleep between cycles (5 min default, configurable)
  SLEEP_SEC="${AGENT_SLEEP:-300}"
  echo "[$ROLE_NAME] Sleeping ${SLEEP_SEC}s..."
  sleep "$SLEEP_SEC"
done

echo "[$ROLE_NAME] Agent stopped after $CYCLE cycles."
