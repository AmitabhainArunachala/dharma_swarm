# Root Drain Pass

Date: 2026-04-01
Repo: `dharma_swarm`
Scope: first non-hot-path root cleanup wave

This pass moved the safest clearly historical root-level markdown files out of repo root and into `reports/historical/`.

## Moved Files

| Old path | New path |
|----------|----------|
| `FULL_REPO_AUDIT_2026-03-28.md` | `reports/historical/FULL_REPO_AUDIT_2026-03-28.md` |
| `CONSTITUTIONAL_XRAY_REPORT.md` | `reports/historical/CONSTITUTIONAL_XRAY_REPORT.md` |
| `CONSTITUTIONAL_HARDENING_SPRINT_REPORT.md` | `reports/historical/CONSTITUTIONAL_HARDENING_SPRINT_REPORT.md` |
| `DUAL_SPRINT_COMPLETION_REPORT.md` | `reports/historical/DUAL_SPRINT_COMPLETION_REPORT.md` |
| `PHASE2_COMPLETION_REPORT.md` | `reports/historical/PHASE2_COMPLETION_REPORT.md` |
| `PHASE3_COMPLETION_REPORT.md` | `reports/historical/PHASE3_COMPLETION_REPORT.md` |
| `GODEL_CLAW_V1_REPORT.md` | `reports/historical/GODEL_CLAW_V1_REPORT.md` |
| `WAVE2_ACCEPTANCE_CHECKLIST.md` | `reports/historical/WAVE2_ACCEPTANCE_CHECKLIST.md` |

## Why These Moved First

- they are historical, evaluative, or completion-oriented artifacts
- they do not define current product or runtime truth
- they were among the clearest violations of the root bootstrap contract
- moving them reduces root noise without touching the dashboard hot path

## Intentionally Deferred

These were left in place for now because they have stronger active or operational coupling, or they need a more precise destination than `reports/historical/`:

- `docs/architecture/VERIFICATION_LANE.md`
- `docs/prompts/MEGA_PROMPT_STRANGE_LOOP.md`
- `docs/prompts/MEGA_PROMPT_v2.md`
- `docs/prompts/MEGA_PROMPT_v3.md`
- `docs/prompts/MEGA_PROMPT_v4.md`
- `docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT.md`
- `docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT_v2.md`
- `docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md`
- `docs/prompts/PALANTIR_UPGRADE_PROMPT.md`
- `docs/prompts/STRATEGIC_PROMPT.md`
- root-level architecture notes such as `docs/architecture/NAVIGATION.md` and `docs/architecture/INTEGRATION_MAP.md`

## Follow-On Waves

1. Rehome prompt artifacts into a dedicated `docs/prompts/` or `docs/archive/prompts/` subtree.
2. Rehome durable architecture notes into `docs/canon/` or `docs/architecture/`.
3. Rewrite `docs/README.md` and `specs/README.md` to reflect the new ontology.

## Constraint

This pass deliberately avoided:

- dashboard hot-path files
- runtime code changes
- speculative broad renames

It is a first root-drain step, not a full repository reorganization.
