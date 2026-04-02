---
title: Sovereign Build Phase Master Prompt
path: docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md
slug: sovereign-build-phase-master-prompt
doc_type: prompt
status: active
summary: Use this prompt when starting any serious implementation pass for the next DHARMA SWARM build phase.
source:
  provenance: repo_local
  kind: prompt
  origin_signals:
  - reports/dharma_current_state_deep_dive_2026-03-19.md
  - reports/ecosystem_forensics_audit_2026-03-19.md
  - specs/SOVEREIGN_BUILD_PHASE_MASTER_SPEC_2026-03-19.md
  - docs/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md
  - specs/KERNEL_CORE_SPEC.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
- product_strategy
inspiration:
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- tests/test_dashboard_chat_session_contract.py
- tests/test_dgc_cli_memory_retrospectives.py
- tests/test_operator_bridge_runtime.py
- tests/test_operator_bridge_telemetry.py
- tests/test_runtime_contract_adapters.py
connected_python_modules:
- tests.test_dashboard_chat_session_contract
- tests.test_dgc_cli_memory_retrospectives
- tests.test_operator_bridge_runtime
- tests.test_operator_bridge_telemetry
- tests.test_runtime_contract_adapters
connected_relevant_files:
- reports/dharma_current_state_deep_dive_2026-03-19.md
- reports/ecosystem_forensics_audit_2026-03-19.md
- specs/SOVEREIGN_BUILD_PHASE_MASTER_SPEC_2026-03-19.md
- docs/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md
- specs/KERNEL_CORE_SPEC.md
improvement:
  room_for_improvement:
  - Keep prompt assumptions aligned with the current build doctrine and runtime contracts.
  - Separate mandatory pre-read materials from optional donor-corpus context.
  - Add a lighter-weight variant for bounded implementation passes that do not need full sovereign-phase framing.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: prompt
  vault_path: docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md
  retrieval_terms:
  - prompts
  - sovereign
  - build
  - phase
  - master
  - prompt
  - '2026'
  - use
  - when
  - starting
  - any
  - serious
  evergreen_potential: high
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.8
  coordination_comment: Use this prompt when starting any serious implementation pass for the next DHARMA SWARM build phase.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md reinforces its salience without needing a separate message.
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
# Sovereign Build Phase Master Prompt

Use this prompt when starting any serious implementation pass for the next DHARMA SWARM build phase.

---

You are working inside the canonical `dharma_swarm` repo. Your job is not to bolt on another feature. Your job is to make DHARMA SWARM into a sovereign agent operating system that absorbs the best ideas from OpenClaw, Hermes, Letta, LangGraph, ADK, NeMo, Goose, and OpenHands without inheriting their architecture as the source of truth.

## Mission

Build DHARMA-native architecture first.

That means:

- DHARMA owns the interfaces.
- DHARMA owns the state model.
- DHARMA owns the operator experience.
- External repos are donor corpora, not skeletons.

## Canonical Build Doctrine

Read and follow these files before making design decisions:

1. `reports/dharma_current_state_deep_dive_2026-03-19.md`
2. `reports/ecosystem_forensics_audit_2026-03-19.md`
3. `specs/SOVEREIGN_BUILD_PHASE_MASTER_SPEC_2026-03-19.md`
4. `docs/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md`
5. `specs/KERNEL_CORE_SPEC.md`

Interpret them this way:

- the deep dive tells you what is already real
- the ecosystem audit tells you what donor systems do better
- the sovereign build spec tells you what DHARMA must own
- the three-plane architecture tells you the product shape
- the kernel spec defines telos constraints, not day-to-day implementation mechanics

## Non-Negotiable Rules

1. Do not architect DHARMA around donor internal objects.
2. Do not add synthetic UI surfaces unsupported by canonical runtime facts.
3. Do not introduce external paid dependencies as architectural requirements.
4. Do not widen coupling to `dgc_cli.py` if boundary extraction is possible.
5. Do not treat experimental donor-inspired modules as canonical until they are recast behind DHARMA-owned contracts.
6. Do not bypass runtime state, memory plane, or evaluation sink with ad hoc side stores unless there is a documented transition plan.
7. Do not lose auditability, replayability, or provenance.

## Current Reality To Respect

DHARMA already has:

- runtime state spine
- operator bridge and views
- session ledger
- message bus
- event memory
- persistent agents
- scheduler
- API/dashboard surfaces
- MCP exposure
- evaluation and evolution subsystems
- broad tests

Your job is to unify, harden, and extend these, not to pretend they do not exist.

## Primary Architectural Goal

Move the codebase toward a DHARMA-owned contract layer centered on these interfaces:

- `AgentRuntime`
- `GatewayAdapter`
- `MemoryPlane`
- `LearningEngine`
- `SkillStore`
- `EvaluationSink`
- `CheckpointStore`
- `SandboxProvider`
- `InteropAdapter`

If a feature does not clearly fit one of those seams, stop and decide whether:

- the seam list is incomplete, or
- the feature is being added at the wrong layer

## Product Priority

Build order is:

1. sovereignty layer
2. runtime hardening
3. Command Nexus
4. memory and learning flywheel
5. evaluation and observability
6. assistant/gateway productization
7. Agent World

Do not build Agent World first.
Do not chase aesthetics ahead of truthful state.

## Donor Absorption Strategy

When using ideas from other systems:

- absorb OpenClaw for gateway and assistant product shape
- absorb Hermes for learning loop, skill extraction, remote backend ideas, and migration semantics
- absorb Letta for memory discipline
- absorb LangGraph and ADK for checkpointing and HITL semantics
- absorb NeMo for eval and observability discipline
- absorb Goose and OpenHands for coding-agent UX and packaging

For each donor idea you touch, ask:

- What is the DHARMA-owned interface for this capability?
- What is the DHARMA-owned data model for this capability?
- Can this donor be replaced later without breaking the system?

If the answer to the third question is no, you are coupling too tightly.

## Expected Working Style

Before editing:

- inspect the local implementation first
- identify the canonical source of truth
- identify existing tests
- identify whether the work touches runtime, memory, telemetry, evaluation, or UI

During editing:

- prefer extracting interfaces and adapters over widening monoliths
- preserve existing working behavior where possible
- add or update focused tests
- document any schema additions

After editing:

- verify through targeted tests
- summarize what changed, what contract was introduced or tightened, and what remains incomplete

## Immediate Task Template

If you are starting a new implementation slice, use this sequence:

1. Identify which sovereign interface the slice belongs to.
2. Identify the existing DHARMA modules that already partially implement it.
3. Define or refine the contract first.
4. Wrap existing behavior behind the contract.
5. Add missing canonical records to runtime or telemetry stores if needed.
6. Add read-model or API exposure only after the contract and truth model are in place.
7. Add tests that prove the contract and its invariants.

## Deliverable Standard

Every implementation pass should ideally produce:

- one clearer contract boundary
- one reduction in donor or monolith coupling
- one increase in canonical state truth
- one meaningful test improvement

## Anti-Patterns

Avoid:

- feature sprawl without contract ownership
- dashboard-first development
- external-schema dependency
- irreversible donor lock-in
- adding hidden state
- inventing new jargon when existing DHARMA terms already fit

## Completion Criterion For A Slice

A build slice is complete only when:

- the capability is expressed through a DHARMA-owned interface
- state is stored in a DHARMA-owned format
- provenance and audit remain intact
- tests cover the contract or critical invariants
- the system is more sovereign afterward than before

Proceed with rigor. Prefer architecture that compounds over feature velocity that fragments.

---

Recommended first implementation area for this phase:

Create the sovereign contract package, then wrap the current runtime spine and operator bridge behind it before widening any higher-level product surface.
