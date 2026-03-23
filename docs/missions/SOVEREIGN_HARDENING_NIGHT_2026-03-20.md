# Sovereign Hardening Night Mission

You own the single write-capable overnight lane for the canonical `dharma_swarm` repo.

## Primary Objective

Wake up with a more coherent DHARMA system by hardening canonical seams instead of widening the product surface.

## Success Criteria

- at least one bounded, real slice shipped
- every shipped slice has focused verification when feasible
- morning handoff reports exact result, files, tests, blockers, and next move
- no collision with unrelated user work

## Allowed Write Zones

Prefer these areas:

- `dharma_swarm/contracts/`
- `dharma_swarm/integrations/`
- `dharma_swarm/*telemetry*`
- `dharma_swarm/*evaluation*`
- `dharma_swarm/assurance/`
- focused tests for the above
- `docs/plans/`
- `docs/missions/`
- sovereign overnight wrapper scripts

## Avoid By Default

Do not widen these surfaces unless fixing a direct contract bug with a focused test:

- `dashboard/`
- `api/`
- `dharma_swarm/providers.py`
- `dharma_swarm/ontology.py`
- `dharma_swarm/ontology_*`
- `dharma_swarm/dgc_cli.py`
- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/swarm.py`
- `dharma_swarm/orchestrator.py`

## Priority Order

1. contract adoption and invariants
2. evaluation and telemetry normalization
3. assurance scanners, validators, and paired tests
4. morning handoff quality and overnight operability

## Operating Rules

- inspect the current repo state each cycle before choosing work
- respect existing uncommitted changes; do not revert or clean them
- choose one bounded slice at a time
- prefer tests, assertions, adapters, validators, and thin compatibility layers
- if blocked, leave exact evidence and the next unblock move
- do not commit, push, reset, or open PRs

## Stop Conditions

Stop and leave a clean handoff if any of the following becomes true:

- the slice expands across more than two domains
- the slice requires broad schema changes outside DHARMA-owned adapter tables
- the slice collides with active edits from another worker
- the only path forward is a dashboard or provider refactor

## Morning Output Shape

- RESULT: one short paragraph
- FILES: comma-separated paths or none
- TESTS: exact command run or not run
- BLOCKERS: none or one short concrete blocker
