#!/bin/bash
# SAB Contributor Agent — run one cycle
# Add to launchd or cron for persistent operation
cd ~/dharma_swarm
export SAB_BASE_URL="https://157.245.193.15"
export SAB_MAX_SPARKS_PER_CYCLE=2
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY}"
python3 -m dharma_swarm.sab_contributor >> ~/.dharma/logs/sab_contributor.log 2>&1
