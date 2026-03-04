#!/bin/bash
# DHARMA SWARM — Multiple Claude Code instances, shared filesystem, alive together.
#
# Each instance is a real Claude Code agent with full tools.
# They communicate through ~/.dharma/shared/ — files they all read and write.
# Each sees a different slice. They converge by reading each other's output.
#
# Usage:
#   ./swarm.sh              # Start 3 instances in tmux
#   ./swarm.sh 5            # Start 5 instances
#   tmux attach -t dharma   # Watch them work
#   touch ~/.dharma/.STOP   # Graceful shutdown

set -e

NUM_AGENTS="${1:-3}"
SHARED="$HOME/.dharma/shared"
SESSION="dharma"

mkdir -p "$SHARED"
rm -f "$SHARED/.STOP"

# Write the shared context that all agents can see
cat > "$SHARED/SWARM_STATE.md" << 'CONTEXT'
# DHARMA SWARM — Live State

## What This Is
You are one of several Claude Code instances running simultaneously.
You share a filesystem. You communicate by writing to ~/.dharma/shared/.

## How To Communicate
- Write your observations to: ~/.dharma/shared/YOUR_ROLE_notes.md
- Read other agents' notes before each action
- If you disagree with another agent, write why in your notes
- If you build on another's work, say so

## Shared Codebase
- ~/dharma_swarm/ — the swarm package (your body)
- ~/dgc-core/ — the nervous system (context, memory, gates, pulse)
- ~/DHARMIC_GODEL_CLAW/ — the old system (717 evolutions, 29 gates)
- ~/Persistent-Semantic-Memory-Vault/ — 1,170 files of research
- ~/.chaiwala/message_bus.py — proven SQLite pub/sub

## The Mission
Ingest, metabolize, and sublate the entire codebase into something better.
Not another framework. Working code that replaces what came before.

## Rules
1. Read before you write. Always.
2. Don't duplicate — check if it exists first.
3. Tests must pass. Run pytest before committing.
4. If you're stuck, write what you're stuck on to shared/stuck.md
5. Check ~/.dharma/.STOP each cycle — if it exists, finish up and exit.
CONTEXT

# Role definitions — each agent gets a different view
ROLES=(
  "SYNTHESIZER: Read ALL codebases (dgc-core, dharma_swarm, old DGC, PSMV). Find what works, what's dead, what overlaps. Write a unified module list to ~/.dharma/shared/synthesis.md. Then start building the unified package."
  "BUILDER: Take the synthesis and build. Write working Python modules with tests. Focus on the three things that matter: agent spawning (via claude -p), task routing, and memory persistence. Ship code, not docs."
  "CRITIC: Read everything the other agents produce. Find bugs, find gaps, find lies. Run the tests. Check claims against reality. Write honest assessments to ~/.dharma/shared/critique.md. Break what needs breaking."
  "RESEARCHER: Deep-read PSMV crown jewels, DHARMA Genome Spec, Garden Daemon Spec, v7 induction prompts, Samaya Protocol. Extract what's actually usable as code, not just beautiful text. Feed findings to the builder."
  "VALIDATOR: Run every test. Try every CLI command. Import every module. Check every path in ecosystem_map.py. Report what actually works vs what's claimed to work. Write to ~/.dharma/shared/validation.md."
)

# Kill existing session if any
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create tmux session
tmux new-session -d -s "$SESSION" -x 200 -y 50

for i in $(seq 0 $((NUM_AGENTS - 1))); do
  ROLE_IDX=$((i % ${#ROLES[@]}))
  ROLE="${ROLES[$ROLE_IDX]}"
  ROLE_NAME=$(echo "$ROLE" | cut -d: -f1)

  if [ $i -gt 0 ]; then
    tmux split-window -t "$SESSION" -v
    tmux select-layout -t "$SESSION" tiled
  fi

  # Build the prompt for this agent
  PROMPT="You are agent $ROLE_NAME in a live DHARMA SWARM.

Your role: $ROLE

Read ~/.dharma/shared/SWARM_STATE.md first.
Read other agents' notes in ~/.dharma/shared/ before each action.
Write your own notes to ~/.dharma/shared/${ROLE_NAME}_notes.md as you work.

Work in ~/dharma_swarm/ as your primary codebase.
Check ~/.dharma/.STOP periodically — if it exists, wrap up and exit.

Start by reading the codebase. Then do your job. Be real. Ship code."

  # Launch claude -p in this pane
  tmux send-keys -t "$SESSION" "echo '=== Agent: $ROLE_NAME ===' && claude -p \"$PROMPT\" --output-format text > ~/.dharma/shared/${ROLE_NAME}_output.md 2>&1 && echo '$ROLE_NAME done'" Enter
done

echo ""
echo "DHARMA SWARM started with $NUM_AGENTS agents in tmux session 'dharma'"
echo ""
echo "  tmux attach -t dharma     # Watch them work"
echo "  touch ~/.dharma/.STOP     # Graceful shutdown"
echo "  cat ~/.dharma/shared/*.md # Read their outputs"
echo ""
