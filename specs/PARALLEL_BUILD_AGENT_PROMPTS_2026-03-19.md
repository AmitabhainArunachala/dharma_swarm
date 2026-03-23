# Parallel Build Agent Prompts

Use these to run two other agents in parallel without having them collide.

The write scopes are intentionally separated.

## Prompt 1: Alpha - Runtime Sovereignty Layer

You are Agent Alpha working inside the canonical `dharma_swarm` repo.

Your mission is to harden the runtime-side sovereign interface layer without touching memory or evaluation contracts owned by another worker.

### Ownership

You own only these areas:

- `dharma_swarm/contracts/common.py`
- `dharma_swarm/contracts/runtime.py`
- new runtime-side adapter files you create
- runtime-side tests you create

You do not own:

- `dharma_swarm/contracts/intelligence.py`
- memory adapters
- evaluation adapters
- dashboard or API UI work

You are not alone in the codebase. Do not revert other edits. Adjust around them.

### Mission

Implement the first real adapters behind these sovereign contracts:

- `AgentRuntime`
- `GatewayAdapter`
- `CheckpointStore`
- `SandboxProvider`
- `InteropAdapter`

Map from existing DHARMA modules, not donor internals:

- `runtime_state.py`
- `operator_bridge.py`
- `message_bus.py`
- `checkpoint.py`
- `sandbox.py`

### Requirements

1. Keep DHARMA-owned contracts authoritative.
2. Do not widen coupling to `dgc_cli.py`.
3. Do not introduce paid or external dependencies.
4. Preserve auditability and provenance.
5. Add focused tests for the adapters you create.

### Deliverables

- runtime-side adapter implementations
- tests proving basic contract compliance
- brief note on any runtime contract gaps you discovered

### Definition of done

Done means a caller can target the sovereign runtime contracts instead of directly targeting raw runtime modules for at least one end-to-end slice.

## Prompt 2: Beta - Memory, Learning, and Evaluation Layer

You are Agent Beta working inside the canonical `dharma_swarm` repo.

Your mission is to harden the intelligence-side sovereign interface layer without touching runtime-side contract files owned by another worker.

### Ownership

You own only these areas:

- `dharma_swarm/contracts/intelligence.py`
- new memory, learning, skill, or evaluation adapter files you create
- intelligence-side tests you create

You do not own:

- `dharma_swarm/contracts/common.py`
- `dharma_swarm/contracts/runtime.py`
- checkpoint, gateway, or sandbox adapters
- dashboard or API UI work

You are not alone in the codebase. Do not revert other edits. Adjust around them.

### Mission

Implement the first real adapters behind these sovereign contracts:

- `MemoryPlane`
- `LearningEngine`
- `SkillStore`
- `EvaluationSink`

Map from existing DHARMA modules, not donor internals:

- `engine/event_memory.py`
- `runtime_state.py`
- `evaluation_registry.py`
- `skills.py`
- any existing memory or provenance helpers that make the adapters cleaner

### Requirements

1. Keep DHARMA-owned contracts authoritative.
2. Treat Hermes, Letta, and NeMo as donor patterns only.
3. Keep all persisted truth in DHARMA-owned formats.
4. Add focused tests for the adapters you create.
5. Call out any missing telemetry tables or evaluation records that block clean implementation.

### Deliverables

- intelligence-side adapter implementations
- tests proving basic contract compliance
- brief note on any schema gaps you discovered

### Definition of done

Done means a caller can target the sovereign intelligence contracts instead of directly targeting raw memory, skills, or evaluation modules for at least one end-to-end slice.
