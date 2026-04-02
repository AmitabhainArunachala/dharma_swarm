---
title: Parallel Build Agent Prompts
path: docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md
slug: parallel-build-agent-prompts
doc_type: prompt
status: active
summary: Use these to run two other agents in parallel without having them collide.
source:
  provenance: repo_local
  kind: prompt
  origin_signals:
  - dharma_swarm/contracts/common.py
  - dharma_swarm/contracts/runtime.py
  - dharma_swarm/contracts/intelligence.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- frontend_engineering
- operations
inspiration:
- operator_runtime
- product_surface
connected_python_files:
- dharma_swarm/contracts/common.py
- dharma_swarm/contracts/runtime.py
- dharma_swarm/contracts/intelligence.py
connected_python_modules:
- dharma_swarm.contracts.common
- dharma_swarm.contracts.runtime
- dharma_swarm.contracts.intelligence
connected_relevant_files:
- dharma_swarm/contracts/common.py
- dharma_swarm/contracts/runtime.py
- dharma_swarm/contracts/intelligence.py
- specs/DGC_TERMINAL_ARCHITECTURE.md
- specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md
improvement:
  room_for_improvement:
  - Keep write scopes explicit so parallel workers can act without merge collisions.
  - Add prompt variants for runtime-only, docs-only, and verification-only delegation lanes.
  - Link prompt instructions to the current worker-ownership conventions when those stabilize.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: prompt
  vault_path: docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md
  retrieval_terms:
  - prompts
  - parallel
  - build
  - agent
  - prompts
  - '2026'
  - use
  - these
  - run
  - two
  - other
  - agents
  evergreen_potential: high
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.8
  coordination_comment: Use these to run two other agents in parallel without having them collide.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: constraint_and_design_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
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
