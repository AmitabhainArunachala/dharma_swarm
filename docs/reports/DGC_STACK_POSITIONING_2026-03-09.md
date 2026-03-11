# DGC Stack Positioning (2026-03-09)

## Current Truth

- Canonical DGC runtime: `~/dharma_swarm`
- Legacy DGC sources are import-only: `~/DHARMIC_GODEL_CLAW`, `~/dgc-core`
- Canonical SAB runtime: `~/agni-workspace/dharmic-agora`
- `~/SAB` remains a strategy/docs shell, not the runtime authority

This means DGC and SAB are not yet "fully merged" in the strict sense. The operational question is not whether multiple repos exist. The operational question is which repo is allowed to define runtime truth.

## Three DGC Generations

### 1. `DHARMIC_GODEL_CLAW`

This is the thick original engine. It aims to be a full autonomous-agent operating system:

- unified daemon
- telos layer / dharmic gates
- swarm self-improvement loop
- DGM integration
- ops bridge
- coordination runtime

Strength:
- richest conception of the system as a living engine

Risk:
- too large and too entangled to treat as canonical without selective porting

### 2. `dgc-core`

This is the thin-shell interpretation:

- Claude Code as brain
- OpenClaw as hands
- daemon / memory / context / hooks around the coding agent

Strength:
- pragmatic and easy to operate

Risk:
- too thin if the goal is to retain the full DGC control plane rather than a wrapper around an external agent

### 3. `dharma_swarm`

This is the current canonical runtime and best middle path:

- real orchestration runtime
- evolution loop
- ledgers
- telos gates
- TUI / CLI control surface
- provider integration seams

It is thin enough to maintain, but thick enough to absorb the original DGC engine selectively.

## Current Direction

The right move is not to choose between "thin wrapper" and "legacy monolith."

The right move is:

1. Keep `dharma_swarm` as the canonical runtime.
2. Port high-value control-plane primitives from `DHARMIC_GODEL_CLAW` by evidence.
3. Keep `dgc-core` as an operator shell unless it contains unique runtime logic worth absorbing.
4. Freeze `DHARMIC_GODEL_CLAW` once remaining useful primitives are imported or explicitly dropped.
5. Keep `dharmic-agora` as the SAB runtime authority.

## Ported In This Pass

These original DGC primitives now exist in the canonical runtime:

- `dharma_swarm/runtime_contract.py`
- `dharma_swarm/decision_router.py`
- `dharma_swarm/plan_compiler.py`

This is the intended pattern: absorb the engine a layer at a time, not by wholesale copy.

## Architecture Positioning

- `DHARMIC_GODEL_CLAW` is closest to a bespoke autonomous-agent operating system.
- `dgc-core` is closest to a thin operator shell around a strong coding agent.
- `dharma_swarm` is closest to a governed orchestration runtime with self-evolution, evidence gates, and operator control surfaces.

## Recommendation

Build the future DGC in `dharma_swarm`, not in `DHARMIC_GODEL_CLAW` and not only in `dgc-core`.

The target shape is:

- `dharma_swarm` = canonical engine
- `dgc-core` = shell / packaging / operator affordances
- `DHARMIC_GODEL_CLAW` = mined legacy archive, then frozen
- `dharmic-agora` = SAB runtime
- `SAB` = doctrine / strategy / specs
