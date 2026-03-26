# Corrected RFC: Self-Evolving Integrations

> Canonical execution spec: [2026-03-26-self-evolving-organism-master-build-spec.md](/Users/dhyana/dharma_swarm/docs/plans/2026-03-26-self-evolving-organism-master-build-spec.md)
>
> This RFC is now a narrowed integration reference. Build order, evaluation math, and the phase-by-phase execution protocol live only in the master build spec above.

## Status

Canonicalized on 2026-03-26 after local repo verification. Historical appended notes that drifted from the verified build order were removed from this RFC instead of being kept as pseudo-authoritative guidance.

## Objective

Absorb the highest-value patterns from:

- `agency-agents`
- `EvoAgentX`
- `Agent0`
- `AgentEvolver`
- `Darwin Gödel Machine`
- `Absolute Zero`
- `R-Zero`
- `Tool-R0`
- `SAGE`

without creating a second runtime or contaminating the live `dharma_swarm` organism with offline training machinery.

## Verified Corrections

- `agency-agents/scripts/convert.sh` and `agency-agents/scripts/install.sh` are the useful entry points. Conversion and installation are separate concerns.
- Claude Code and Copilot installation remain installation-layer concerns, not export-layer concerns.
- The strongest EvoAgentX donor for runtime field mutation is `evoagentx/optimizers/engine/registry.py`, not only `optimizer_core.py`.
- Agent0 and AgentEvolver are training-first frameworks. Their strongest imports are patterns and isolated subsystems, not direct runtime adoption.

## Non-Goals

- Do not embed VERL, GRPO, LoRA, or other training loops into the live runtime.
- Do not add installation side effects to core runtime modules.
- Do not modify JIKOKU tracing semantics to perform attribution inline.

## Canonical Layer Model

### Layer 1: Canonical Agent Schema + Export Adapters

Source of truth stays inside `dharma_swarm`.

Output adapters render tool-specific artifacts. Installation remains a separate workflow.

### Layer 2: Runtime Field Registry

Prompts, thresholds, routing knobs, and related runtime state become typed, snapshot-capable mutation targets.

This layer sits beside Darwin, not inside Darwin proposal objects.

### Layer 3: AutoResearch

The system can plan research, gather sources, normalize evidence, track claims, and emit cited reports without bypassing the existing runtime.

### Layer 4: AutoGrade

The system grades reports with hard gates and weighted metrics before any optimizer is allowed to treat a run as success.

### Layer 5: Causal Credit Engine

JIKOKU spans, traces, and lineage remain capture artifacts.

Attribution is computed after execution by a separate engine that writes credit artifacts and fitness signals.

### Layer 6: Optimizer Bridge

Live optimization targets runtime fields and workflow choices through black-box or textual-gradient style bridges, not weight updates in the runtime loop.

### Layer 7: Topology Genome

Workflow structures become evolvable artifacts rather than enum-only topologies.

### Layer 8: Curriculum Engine

The system generates verifier-rich frontier tasks from failures, uncertainty, and capability gaps.

### Layer 9: Offline Training Lane

Any future RL, LoRA, or VERL work runs outside the live runtime and consumes exported artifacts and telemetry.

## Implementation Rules

- One runtime
- One archive
- One provenance model
- One promotion pipeline
- Strong grading before strong optimization

All new layers must emit artifacts that existing archive, telemetry, and gate infrastructure can understand.

## Current Execution Boundary

The master build spec defines the required order:

1. Canonicalize docs
2. Build `AutoResearch`
3. Build `AutoGrade`
4. Integrate evaluation and archive registration
5. Only then build optimizer, topology, and curriculum layers

If this RFC and the master build spec ever disagree, the master build spec wins.
