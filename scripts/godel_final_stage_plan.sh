#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
# Godel final staged merge plan (dry output)
# Run from repo root: ~/dharma_swarm

# Commit A: Core governance/evolution kernel
# git add \
#   dharma_swarm/dharma_kernel.py \
#   dharma_swarm/dharma_corpus.py \
#   dharma_swarm/policy_compiler.py \
#   dharma_swarm/anekanta_gate.py \
#   dharma_swarm/dogma_gate.py \
#   dharma_swarm/steelman_gate.py \
#   dharma_swarm/evolution.py \
#   dharma_swarm/canary.py \
#   dharma_swarm/archive.py \
#   dharma_swarm/telos_gates.py \
#   dharma_swarm/swarm.py \
#   dharma_swarm/selector.py \
#   dharma_swarm/fitness_predictor.py \
#   dharma_swarm/metrics.py \
#   dharma_swarm/traces.py \
#   dharma_swarm/rv.py \
#   dharma_swarm/elegance.py \
#   dharma_swarm/file_lock.py \
#   dharma_swarm/bridge.py \
#   tests/test_dharma_kernel.py \
#   tests/test_dharma_corpus.py \
#   tests/test_policy_compiler.py \
#   tests/test_anekanta_gate.py \
#   tests/test_dogma_gate.py \
#   tests/test_steelman_gate.py \
#   tests/test_evolution.py \
#   tests/test_canary.py \
#   tests/test_archive.py \
#   tests/test_swarm.py \
#   tests/test_telos_gates.py \
#   tests/test_selector.py \
#   tests/test_fitness_predictor.py \
#   tests/test_metrics.py \
#   tests/test_traces.py \
#   tests/test_rv.py \
#   tests/test_elegance.py \
#   tests/test_file_lock.py \
#   tests/test_bridge.py
# git commit -m "godel-core: dharma kernel/corpus/policy + gated evolution"

# Commit B: Living layers + integration
# git add \
#   dharma_swarm/stigmergy.py \
#   dharma_swarm/shakti.py \
#   dharma_swarm/subconscious.py \
#   dharma_swarm/dgc_cli.py \
#   dharma_swarm/tui.py \
#   dharma_swarm/monitor.py \
#   dharma_swarm/context.py \
#   dharma_swarm/startup_crew.py \
#   dharma_swarm/cli.py \
#   dharma_swarm/pulse.py \
#   dharma_swarm/splash.py \
#   dharma_swarm/ecosystem_map.py \
#   pyproject.toml \
#   tests/test_stigmergy.py \
#   tests/test_shakti.py \
#   tests/test_subconscious.py \
#   tests/test_dgc_cli.py \
#   tests/test_tui.py \
#   tests/test_monitor.py \
#   tests/test_godel_claw_cli.py \
#   tests/test_ecosystem_map.py \
#   tests/test_integration.py
# git commit -m "living-layers: stigmergy + shakti + subconscious + cli/tui wiring"

# Commit C: Wave 3 docs + e2e validation
# git add \
#   reports/historical/GODEL_CLAW_V1_REPORT.md \
#   LIVING_LAYERS.md \
#   tests/test_godel_claw_e2e.py \
#   specs/GODEL_CLAW_V1_SPEC.md \
#   specs/Dharma_Constitution_v0.md \
#   specs/Dharma_Corpus_Schema.md \
#   specs/research_living_layers/README.md \
#   specs/research_living_layers/research_subconscious_ai.md \
#   specs/research_living_layers/research_stigmergy_agents.md \
#   specs/research_living_layers/research_shakti_creative_autonomy.md
# git commit -m "docs+e2e: godel v1 report, living layers architecture, end-to-end checks"

# Commit D: Optional ops/docs
# git add \
#   PUBLISH_TOMORROW.md \
#   scripts/publish_canonical.sh \
#   OVERNIGHT_AUTOPILOT.md \
#   docs/architecture/VERIFICATION_LANE.md \
#   cron_jobs.json \
#   scripts/ecosystem_synthesis.sh \
#   scripts/overnight_autopilot.py \
#   scripts/start_overnight.sh \
#   scripts/stop_overnight.sh \
#   scripts/start_verification_lane.sh \
#   scripts/stop_verification_lane.sh \
#   scripts/verification_lane.py
# git commit -m "ops/docs: optional automation and publishing artifacts"

# Never commit local/session noise:
# .claude-flow/ .claude/ .swarm/ .mcp.json reports/
EOF
