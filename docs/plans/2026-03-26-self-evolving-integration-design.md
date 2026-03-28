# Self-Evolving Integration Design

**Date:** 2026-03-26

**Goal:** absorb the highest-value patterns from `agency-agents`, EvoAgentX, Agent0, AgentEvolver, Darwin Gödel Machine, Absolute Zero, R-Zero, Tool-R0, and SAGE without creating a second runtime inside `dharma_swarm`.

## Architecture

The integration has to preserve one runtime, one archive, one provenance model, and one promotion pipeline.

The system is split into five layers:

1. `Canonical agent schema + export adapters`
   This is the `agency-agents` import. Source agent definitions stay canonical inside `dharma_swarm`, then emit tool-specific artifacts. Conversion and installation remain separate concerns.

2. `Runtime field registry`
   This is the EvoAgentX import. Runtime prompts, thresholds, and routing weights become typed, snapshot-capable mutation targets without forcing code-file mutations.

3. `Causal credit engine`
   This is the AgentEvolver import. JIKOKU remains a tracing substrate; attribution runs after execution over spans, traces, and lineage.

4. `Topology genome`
   This is the SAGE + EvoAgentX + DGM import. Workflow structures become evolvable artifacts instead of static enum branches.

5. `Curriculum engine`
   This is the Agent0 + Absolute Zero + R-Zero + Tool-R0 import. It generates frontier tasks from failures, uncertainty, and verifier-rich environments.

Offline RL, LoRA, VERL, and GRPO remain a separate lane. They are training systems, not live runtime dependencies.

## Data Flow

Canonical agent definitions are authored once. Export adapters render artifacts for external tools.

Runtime actors register optimizable fields at startup. Darwin-compatible evaluation loops can later mutate those fields while preserving snapshots and reset semantics.

Execution emits JIKOKU spans and lineage edges. The future causal credit engine consumes those outputs and writes attribution artifacts without changing tracing semantics.

Topology and curriculum evolution will be introduced later on top of the same archive, telemetry, and promotion gates already used by the live system.

## Error Handling

Export adapters must be pure renderers by default. They should not install into user directories.

Runtime field tracking must snapshot before mutation and support rollback per field and globally.

Unsupported export targets should fail loudly with a typed exception rather than silently degrading output.

## Testing

The first slice is verified with isolated unit tests:

- runtime field tracking, mutation, batch registration, and reset
- export rendering, target-specific frontmatter, path generation, and color normalization

Later phases should add:

- attribution replay tests over recorded traces
- topology genome serialization and selection tests
- curriculum generation tests with verifier-backed tasks
