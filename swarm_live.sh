#!/bin/bash
# DHARMA SWARM LIVE — Persistent multi-agent Claude Code swarm.
#
# Starts N agents in tmux, each running in a continuous loop.
# They read each other's notes, build on each other's work,
# and keep going until you stop them.
#
# Usage:
#   ./swarm_live.sh          # 3 agents (synthesizer, builder, critic)
#   ./swarm_live.sh 5        # 5 agents (adds researcher, validator)
#   tmux attach -t dharma    # Watch them
#   touch ~/.dharma/.STOP    # Stop all agents gracefully
#   cat ~/.dharma/shared/*_notes.md  # Read what they've found

set -e

NUM_AGENTS="${1:-3}"
SHARED="$HOME/.dharma/shared"
SESSION="dharma"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$SHARED"
rm -f "$HOME/.dharma/.STOP"

# Shared context
cat > "$SHARED/SWARM_STATE.md" << 'EOF'
# DHARMA SWARM — Live Persistent Swarm

## You Are Here
Multiple Claude Code instances running in loops. You share ~/.dharma/shared/.
Each cycle: read others' notes → do one thing → write what you found → sleep → repeat.

## The Codebase
- ~/dharma_swarm/ — swarm package (16 modules, 135 tests)
- ~/dgc-core/ — nervous system (context loader, memory, gates, pulse, ecosystem map)
- ~/DHARMIC_GODEL_CLAW/ — old system (2,647-line orchestrator, 717 evolutions, 29 gates)
- ~/Persistent-Semantic-Memory-Vault/ — 1,170 files of research artifacts
- ~/.chaiwala/message_bus.py — proven SQLite message bus

## The Mission
These codebases should be ONE thing. Find what works in each, kill what's dead,
build the unified system. The result should be a single `dgc` CLI that:
- Spawns Claude Code agents (real ones, via claude -p)
- Routes tasks between them
- Persists memory across sessions
- Gates all actions through dharmic safety checks
- Runs autonomously on a heartbeat

## Communication Protocol
- Write findings to: ~/.dharma/shared/YOUR_ROLE_notes.md (append, don't overwrite)
- Read ALL other agents' notes before each cycle
- Disagree openly — write why
- Build on others' work — cite what you're extending
- One cycle = one action. Don't try to do everything at once.
EOF

# Role definitions
declare -a ROLE_NAMES=("SYNTHESIZER" "BUILDER" "CRITIC" "RESEARCHER" "VALIDATOR")
declare -a ROLE_DESCS=(
  "Read ALL codebases. Find what works, what's dead, what overlaps. Write synthesis to shared/. Then merge the best pieces into ~/dharma_swarm/."
  "Take the synthesis and build. Write working Python that replaces the old code. Focus on: agent spawning via claude -p, task routing, memory persistence. Run pytest after every change."
  "Read everything others produce. Find bugs, gaps, broken claims. Run tests. Check paths exist. Write honest critique to shared/. Break what needs breaking."
  "Deep-read PSMV: crown jewels, DHARMA Genome, Garden Daemon, v7 induction, Samaya Protocol. Extract what's usable as code. Feed findings to builder."
  "Run every test. Try every CLI. Import every module. Check every claim. Report what works vs what's fiction. Nothing ships without your sign-off."
)

# Kill old session
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create session
tmux new-session -d -s "$SESSION" -x 220 -y 60

for i in $(seq 0 $((NUM_AGENTS - 1))); do
  IDX=$((i % ${#ROLE_NAMES[@]}))
  NAME="${ROLE_NAMES[$IDX]}"
  DESC="${ROLE_DESCS[$IDX]}"

  if [ $i -gt 0 ]; then
    tmux split-window -t "$SESSION" -v
    tmux select-layout -t "$SESSION" tiled
  fi

  tmux send-keys -t "$SESSION.$i" \
    "AGENT_SLEEP=300 bash '$SCRIPT_DIR/agent_loop.sh' '$NAME' '$DESC'" Enter
done

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  DHARMA SWARM LIVE — $NUM_AGENTS agents running           ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║  tmux attach -t dharma    → watch them work      ║"
echo "║  touch ~/.dharma/.STOP    → stop all agents      ║"
echo "║  tail -f ~/.dharma/shared/*_notes.md → live feed ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
