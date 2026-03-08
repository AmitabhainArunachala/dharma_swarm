# DGC Merge Ledger

Purpose: enforce one canonical runtime (`~/dharma_swarm`) and track every import/merge decision from legacy generations.

## Canonical Runtime

- Runtime repo: `~/dharma_swarm`
- Legacy sources (import-only):
  - `~/DHARMIC_GODEL_CLAW`
  - `~/dgc-core`

## Decision Table

| Date (UTC) | Source | Target | Decision | Reason | Tests | Commit |
|---|---|---|---|---|---|---|

## Session Log

- Bootstrapped ledger. Use `scripts/merge_snapshot.py` to append factual checkpoints.

## Rules

1. No architecture/performance claim without command output or file reference.
2. No feature lane is "done" until `mission-status --strict-core --require-tracked` is green.
3. Legacy code is ported by evidence (`keep|port|drop`), never copied wholesale.
4. All overnight/autonomous runs must emit snapshot facts and heartbeat.
- 2026-03-08T14:46:26Z snapshot=20260308T144624Z branch=split/2026-03-08 head=807779213dfc mission_exit=0 tracked=8/8
- 2026-03-08T14:46:58Z snapshot=20260308T144655Z branch=split/2026-03-08 head=807779213dfc mission_exit=0 tracked=8/8
