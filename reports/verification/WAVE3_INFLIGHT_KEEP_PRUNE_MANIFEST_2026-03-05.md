# Wave 3 In-Flight Keep/Prune Manifest (2026-03-05)

This is a **provisional** manifest while Wave 3 is still running.

## Current verified baseline (pre-Wave-3 finalize)
- Acceptance gate report: `reports/verification/wave2_acceptance_20260305_183320.md`
- Triple suite result: `775 passed` on all 3 runs
- Canonical CLI smoke: pass (`/opt/homebrew/bin/dgc status`)
- Telos gate count smoke: `11`

## KEEP NOW (safe core)
- `dharma_swarm/dharma_kernel.py`
- `dharma_swarm/dharma_corpus.py`
- `dharma_swarm/policy_compiler.py`
- `dharma_swarm/anekanta_gate.py`
- `dharma_swarm/dogma_gate.py`
- `dharma_swarm/steelman_gate.py`
- `dharma_swarm/canary.py`
- `dharma_swarm/evolution.py`
- `dharma_swarm/telos_gates.py`
- `dharma_swarm/swarm.py`
- `dharma_swarm/archive.py`

Core tests:
- `tests/test_dharma_kernel.py`
- `tests/test_dharma_corpus.py`
- `tests/test_policy_compiler.py`
- `tests/test_anekanta_gate.py`
- `tests/test_dogma_gate.py`
- `tests/test_steelman_gate.py`
- `tests/test_canary.py`
- `tests/test_evolution.py`
- `tests/test_archive.py`
- `tests/test_telos_gates.py`
- `tests/test_swarm.py`

## KEEP IF GREEN (Wave 2/3 integration)
Only keep if final post-Wave-3 acceptance remains green.

- `dharma_swarm/stigmergy.py`
- `dharma_swarm/shakti.py`
- `dharma_swarm/subconscious.py`
- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/tui.py`
- `dharma_swarm/monitor.py`
- `dharma_swarm/context.py`
- `dharma_swarm/startup_crew.py`
- `tests/test_stigmergy.py`
- `tests/test_shakti.py`
- `tests/test_subconscious.py`
- `tests/test_dgc_cli.py`
- `tests/test_tui.py`
- `tests/test_monitor.py`
- `tests/test_godel_claw_cli.py`

## WAVE 3 ARTIFACTS (pending)
Defer merge decision until Wave 3 outputs are complete and test-verified.

Expected candidates:
- `GODEL_CLAW_V1_REPORT.md`
- `LIVING_LAYERS.md`
- `tests/test_godel_claw_e2e.py` (if added)
- any new docs in `specs/`

## DO NOT COMMIT (local/session noise)
- `.claude-flow/`
- `.claude/`
- `.swarm/`
- `.mcp.json` (unless explicitly standardized)
- `reports/` runtime outputs

## Next step after Wave 3 completes
Run:

```bash
cd ~/dharma_swarm
scripts/wave2_acceptance_gate.sh --triple
```

Then regenerate final merge slices from latest `git status` before staging.
