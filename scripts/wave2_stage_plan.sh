#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
# Wave 2 staged merge plan (dry output)
# Run from repo root: ~/dharma_swarm

# Commit A: Core v1
# git add \
#   dharma_swarm/dharma_kernel.py \
#   dharma_swarm/dharma_corpus.py \
#   dharma_swarm/policy_compiler.py \
#   dharma_swarm/anekanta_gate.py \
#   dharma_swarm/dogma_gate.py \
#   dharma_swarm/steelman_gate.py \
#   dharma_swarm/canary.py \
#   dharma_swarm/evolution.py \
#   dharma_swarm/telos_gates.py \
#   dharma_swarm/swarm.py \
#   dharma_swarm/archive.py \
#   tests/test_dharma_kernel.py \
#   tests/test_dharma_corpus.py \
#   tests/test_policy_compiler.py \
#   tests/test_anekanta_gate.py \
#   tests/test_dogma_gate.py \
#   tests/test_steelman_gate.py \
#   tests/test_canary.py \
#   tests/test_evolution.py \
#   tests/test_archive.py \
#   tests/test_telos_gates.py \
#   tests/test_swarm.py
# git commit -m "godel-core: dharma kernel/corpus/policy + gated evolution pipeline"

# Commit B: Living layers (only if green)
# git add \
#   dharma_swarm/stigmergy.py \
#   dharma_swarm/shakti.py \
#   dharma_swarm/subconscious.py \
#   dharma_swarm/dgc_cli.py \
#   dharma_swarm/tui.py \
#   dharma_swarm/monitor.py \
#   dharma_swarm/context.py \
#   dharma_swarm/startup_crew.py \
#   tests/test_stigmergy.py \
#   tests/test_shakti.py \
#   tests/test_subconscious.py \
#   tests/test_dgc_cli.py \
#   tests/test_tui.py \
#   tests/test_monitor.py
# git commit -m "living-layers: stigmergy + shakti + subconscious integration"

# Commit C: Optional docs/ops
# git add \
#   PUBLISH_TOMORROW.md \
#   scripts/publish_canonical.sh \
#   OVERNIGHT_AUTOPILOT.md \
#   VERIFICATION_LANE.md \
#   cron_jobs.json \
#   scripts/overnight_autopilot.py \
#   scripts/start_overnight.sh \
#   scripts/stop_overnight.sh \
#   scripts/start_verification_lane.sh \
#   scripts/stop_verification_lane.sh \
#   scripts/verification_lane.py \
#   scripts/ecosystem_synthesis.sh
# git commit -m "ops/docs: optional automation and publishing artifacts"

# Never commit local/session noise:
# .claude-flow/ .claude/ .swarm/ reports/ .mcp.json
EOF
