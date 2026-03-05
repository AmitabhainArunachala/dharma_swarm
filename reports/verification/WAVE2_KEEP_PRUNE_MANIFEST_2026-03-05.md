# Wave 2 Keep/Prune Manifest (2026-03-05)

Purpose: fast, low-chaos merge decisions after Claude Wave 2/3 completes.

Status source: live `git status --porcelain` snapshot during Wave 2 execution.

## Merge Strategy

1. Merge **Core Evolution/Governance** first (must pass full suite).
2. Merge **Living Layers** second (only if governance and observability remain stable).
3. Keep **local/runtime noise** out of canonical commits.

---

## KEEP NOW (Core v1)

These are high-confidence, directly aligned to Gödel Claw v1 core:

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

Core tests to keep with these:

- `tests/test_dharma_kernel.py`
- `tests/test_dharma_corpus.py`
- `tests/test_policy_compiler.py`
- `tests/test_anekanta_gate.py`
- `tests/test_dogma_gate.py`
- `tests/test_steelman_gate.py`
- `tests/test_evolution.py`
- `tests/test_canary.py`
- `tests/test_archive.py`
- `tests/test_telos_gates.py`
- `tests/test_swarm.py`

---

## KEEP IF GREEN (Wave 2 living layers)

Keep only if all pass:
- no regression in full suite,
- no split-brain path introduced,
- no fake stubs in critical execution path.

- `dharma_swarm/stigmergy.py`
- `dharma_swarm/shakti.py`
- `dharma_swarm/subconscious.py`
- `tests/test_stigmergy.py`
- `tests/test_shakti.py`
- `tests/test_subconscious.py`

Integration points likely touched by Agent 13 (review diff quality before keeping):

- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/tui.py`
- `dharma_swarm/monitor.py`
- `dharma_swarm/context.py`
- `dharma_swarm/startup_crew.py`
- `tests/test_dgc_cli.py`
- `tests/test_tui.py`
- `tests/test_monitor.py`

---

## DEFER (separate branch or later pass)

Not required for v1 acceptance. Keep in a side branch if useful, but do not block core merge:

- `PUBLISH_TOMORROW.md`
- `scripts/publish_canonical.sh`
- `OVERNIGHT_AUTOPILOT.md`
- `VERIFICATION_LANE.md`
- `cron_jobs.json`
- `scripts/overnight_autopilot.py`
- `scripts/start_overnight.sh`
- `scripts/stop_overnight.sh`
- `scripts/start_verification_lane.sh`
- `scripts/stop_verification_lane.sh`
- `scripts/verification_lane.py`
- `scripts/ecosystem_synthesis.sh`

---

## PRUNE / DO NOT COMMIT (local/session noise)

- `.claude-flow/`
- `.claude/`
- `.swarm/`
- `.mcp.json` (unless intentionally standardized and reviewed)
- `reports/` (runtime outputs, generated logs)

Also avoid accidental inclusion of transient/generated artifacts under home-level runtime dirs.

---

## Acceptance Commands

Run these before final merge decision:

```bash
cd ~/dharma_swarm
scripts/wave2_acceptance_gate.sh --triple
```

Review report and ensure:
- full suite green,
- core imports/gate-count smoke pass,
- canonical `dgc` command path stable,
- no blocking runtime regressions.

---

## Suggested Commit Slicing

Commit A (Core v1):
- all files in KEEP NOW.

Commit B (Living Layers):
- files in KEEP IF GREEN only.

Commit C (Docs/Ops optional):
- DEFER bucket only, if explicitly desired.

This keeps rollback simple and reduces contamination risk from broad multi-agent runs.
