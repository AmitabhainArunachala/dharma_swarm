# Cybernetics Directive

**Status**: Activation seed
**Date**: 2026-03-26
**Purpose**: Turn cybernetic theory into a living governance subsystem for `dharma_swarm`

## Why This First

The system already has a large semantic and telos surface, but the repo's own audits say the control plane is still fragmented:
- the ontology family is not the hot-path coordination bus
- `PolicyCompiler` remains a bottleneck between knowledge and behavior
- context injection, audit, and environmental intelligence are only partially closed into one loop

Cybernetics comes first because it is the wiring layer. More traditions without this layer become semantic accumulation, not regulation.

## Mission

Install a living cybernetics subsystem that can:
- diagnose the current S2/S3/S4/S5 wiring
- choose one bounded activation lever at a time
- push that lever into runtime behavior or task routing
- audit whether the result is alive or still decorative
- feed the next iteration back into the director

## Steward Seats

These are stewardship seats, not sacred identities. They map to existing runtime lanes so the subsystem is live immediately.

Active runtime roster as of 2026-03-27:
- `cyber-glm5` -> `ollama://glm-5:cloud`
- `cyber-kimi25` -> `ollama://kimi-k2.5:cloud`
- `cyber-codex` -> `ollama://qwen3-coder:480b-cloud`
- `cyber-opus` -> `ollama://deepseek-v3.2:cloud`

1. `Identity Steward`
Current lane: `cyber-opus`
Responsibility: preserve telos, adjudicate scope, keep the directive from drifting into feature sprawl.

2. `Variety Cartographer`
Current lanes: `cyber-glm5`, `cyber-kimi25`
Responsibility: map where governance variety exists, where it is attenuated, and where the system is still under-regulated.

3. `Control Architect`
Current lane: `cyber-codex`
Responsibility: wire the smallest hot-path control improvement with concrete interfaces and verification.

4. `Audit Challenger`
Current lanes: `cyber-opus` with support from `cyber-glm5`
Responsibility: challenge false closure, detect decorative wiring, and define the next bounded reroute.

## Operating Loop

1. Map the live control plane.
2. Define the activation spine.
3. Wire the smallest live lever.
4. Audit and reroute.

This loop is intentionally modest. It should produce one real governance improvement per cycle, not a grand theory deck.

## First Activation Targets

1. Director/task-board activation for cybernetics-specific work.
2. A durable artifact that records steward seats, evidence, and next bounded step.
3. One runtime bridge that moves a governance pathway closer to the hot path.
4. A validation pass that distinguishes alive behavior from decorative architecture.

## Non-Goals

- Creating a parallel management theater detached from runtime
- Adding new traditions before the loop closes
- Minting new agent personas without routing, tasks, and evidence
- Treating ontology population as success if it does not alter behavior

## Activation

Seed the first workflow with:

```bash
python3 scripts/seed_cybernetics_directive.py
```

This creates a bounded workflow in the director/task-board system and writes an activation note to `~/.dharma/shared/`.
