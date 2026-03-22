# Ecosystem Absorption Master Index

This is the sovereign donor map for DHARMA SWARM.

The rule is simple:

- steal patterns aggressively
- port code only when the license and maintenance burden make sense
- never let donor internals become DHARMA's canonical state model
- keep routing, memory, telemetry, evaluation, and interop under DHARMA-owned contracts

## Priority 1

### TensorZero
- Repo: `tensorzero/tensorzero`
- URL: <https://github.com/tensorzero/tensorzero>
- Steal:
  - gateway-grade route/eval/optimization loop
  - experiment-friendly observability semantics
  - control-plane thinking for provider traffic
- Land in:
  - `dharma_swarm/provider_policy.py`
  - `dharma_swarm/telemetry_plane.py`
  - `dharma_swarm/evaluation_registry.py`
- Why:
  - DHARMA needs closed-loop optimization, not just route decisions.

### LiteLLM
- Repo: `BerriAI/litellm`
- URL: <https://github.com/BerriAI/litellm>
- Steal:
  - provider normalization
  - cost-aware routing and fallback logic
  - gateway thinking for multi-provider fleets
- Land in:
  - `dharma_swarm/base_provider.py`
  - `dharma_swarm/model_manager.py`
  - `dharma_swarm/provider_policy.py`
- Why:
  - DHARMA already routes providers, but it needs better cost and failover discipline.

### A2A
- Repo: `a2aproject/A2A`
- URL: <https://github.com/a2aproject/A2A>
- Steal:
  - capability discovery
  - protocol-grade agent handoff semantics
  - external interoperability boundaries
- Land in:
  - `dharma_swarm/handoff.py`
  - `dharma_swarm/contracts/runtime.py`
  - future interop adapters
- Why:
  - sovereignty does not mean isolation.

### Phoenix
- Repo: `Arize-ai/phoenix`
- URL: <https://github.com/Arize-ai/phoenix>
- Steal:
  - trace-first debugging
  - eval-linked observability
  - subject-centric experiment views
- Land in:
  - `dharma_swarm/telemetry_plane.py`
  - `dharma_swarm/telemetry_views.py`
  - dashboard telemetry surfaces
- Why:
  - telemetry should explain behavior, not just count events.

## Priority 2

### browser-use
- Repo: `browser-use/browser-use`
- URL: <https://github.com/browser-use/browser-use>
- Steal:
  - browser action abstractions
  - agent-readable web state
- Land in:
  - `dharma_swarm/gateway/`
  - `dharma_swarm/sandbox.py`
  - future browser adapters

### Skyvern
- Repo: `Skyvern-AI/skyvern`
- URL: <https://github.com/Skyvern-AI/skyvern>
- Steal:
  - checkpoint-heavy web workflows
  - structured browser automation semantics
- Land in:
  - workflow execution
  - checkpointing and operator review layers

### mem0
- Repo: `mem0ai/mem0`
- URL: <https://github.com/mem0ai/mem0>
- Steal:
  - memory retrieval ergonomics
  - operational memory shaping patterns
- Land in:
  - `dharma_swarm/engine/event_memory.py`
  - `dharma_swarm/engine/unified_index.py`
  - `dharma_swarm/contracts/intelligence.py`

## Priority 3

### AutoGen
- Repo: `microsoft/autogen`
- URL: <https://github.com/microsoft/autogen>
- Steal:
  - role-based collaboration patterns
  - multi-agent conversation decomposition
- Land in:
  - `dharma_swarm/swarm_router.py`
  - `dharma_swarm/operator_bridge.py`
  - `dharma_swarm/handoff.py`

### Microsoft Agent Framework
- Repo: `microsoft/agent-framework`
- URL: <https://github.com/microsoft/agent-framework>
- Steal:
  - durable workflow lifecycle semantics
  - deployment-grade orchestration ideas
- Land in:
  - `dharma_swarm/runtime_state.py`
  - `dharma_swarm/operator_bridge.py`
  - `dharma_swarm/contracts/runtime.py`

### PydanticAI
- Repo: `pydantic/pydantic-ai`
- URL: <https://github.com/pydantic/pydantic-ai>
- Steal:
  - schema-first tool boundaries
  - typed agent IO discipline
- Land in:
  - `dharma_swarm/contracts/`
  - API models
  - tool schemas

## What We Do Not Do

- We do not adopt donor state models as canonical truth.
- We do not wrap DHARMA around someone else's runtime.
- We do not create a chimera repo with donor code everywhere.

## Current Build Implication

The first absorption slice should stay inside sovereign DHARMA services:

1. telemetry-driven provider ranking
2. cost-aware control-plane routing
3. A2A-compatible interop boundary
4. browser action substrate
5. stronger memory-plane policy
