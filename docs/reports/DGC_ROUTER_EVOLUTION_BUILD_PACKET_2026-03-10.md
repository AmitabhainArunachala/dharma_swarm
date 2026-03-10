# DGC Router Evolution Build Packet

**Date**: 2026-03-10  
**Primary target repo**: `dharma_swarm`  
**Delivery remote**: `git@github.com:AmitabhainArunachala/dharma_swarm.git`  
**Delivery branch**: `main`  
**Known baseline commit on remote**: `c6fea80`  
**Canonical local research source**: `/Users/dhyana/Downloads/ROUTER_EVOLUTION_SUBSTRATE_RESEARCH.md`  
**Supporting deep dives**: `/Users/dhyana/Downloads/research_router_evolution_loops.md`, `/Users/dhyana/Downloads/research_router_learning_swarm.md`

## Canonical Source Decision

Use `ROUTER_EVOLUTION_SUBSTRATE_RESEARCH.md` as the canonical source for build planning.

Why:
- It is the synthesis artifact dated **2026-03-10** that explicitly integrates the other two research files.
- It already classifies the 20-layer vision into `BUILDABLE NOW`, `RESEARCH FRONTIER`, `SPECULATIVE`, and `VACUOUS`.
- It names the production-ready stack directly: **PILOT + MasRouter cascade + AMRO pheromones**.

Use the other two files only as evidence reservoirs for implementation detail and agent prompts.

## Delivery Target

All implementation streams should treat the destination as:

- repo: `git@github.com:AmitabhainArunachala/dharma_swarm.git`
- branch: `main`
- remote baseline: `c6fea80` (`Implement DGC control-plane hardening: provenance, ack, and retry semantics`)

The local workspace path `/Users/dhyana/dharma_swarm` is the working checkout for that destination.

## Grounded P0 Build Scope

These are the buildable-now primitives that map cleanly onto the current repo:

1. Persistent routing memory
   - EWMA quality/reliability tracking per provider-model-task lane
   - append-only routing decision log
   - pheromone-like success/failure traces

2. Multi-stage swarm routing
   - collaboration-mode choice
   - role allocation
   - provider/model assignment per role

3. Evolution guardrail loop
   - retrospective audit over bad routes
   - drift thresholds before policy promotion
   - Darwin-engine policy archive hooks

## Existing Code Seams

- `dharma_swarm/router_v1.py`
  - local request signals: language, complexity, context length
- `dharma_swarm/provider_policy.py`
  - reflex / deliberative / escalate policy router
- `dharma_swarm/providers.py`
  - runtime provider selection, fallbacks, canary, sticky sessions
- `dharma_swarm/evolution.py`
  - Darwin engine orchestration loop
- `dharma_swarm/stigmergy.py`
  - established pheromone vocabulary and persistence style

## Parallel Split

### Stream A: Routing Memory Substrate

**Owner**: current Codex instance  
**Scope**:
- add persistent routing-memory store
- track cross-session lane quality and failure pheromones
- wire store into `ModelRouter` reordering
- land tests

**Acceptance**:
- provider ranking changes when historical evidence strongly favors another lane
- data persists on disk
- failures never break hot-path inference

### Stream B: MasRouter-Inspired Swarm Router

**Owner**: parallel Codex agent 2  
**Scope**:
- implement collaboration determiner: single-agent vs multi-agent
- implement role allocator for `planner`, `coder`, `critic`, `researcher`
- define blackboard/shared-context contract for downstream execution
- do not edit Darwin engine internals

**Touch these files**:
- `dharma_swarm/provider_policy.py`
- `dharma_swarm/decision_router.py`
- add new file if needed: `dharma_swarm/swarm_router.py`
- tests under `tests/`

**Avoid**:
- `dharma_swarm/providers.py`
- `dharma_swarm/evolution.py`
- routing-memory schema changes

### Stream C: Darwin Router Evolution + Drift Guard

**Owner**: parallel Codex agent 3  
**Scope**:
- add retrospective audit primitive for bad high-confidence routes
- define route-policy archive entry format
- add drift guard thresholds aligned to research:
  - Goal Drift Index critical threshold: `0.44`
  - constraint preservation floor: `0.987`
- integrate with Darwin planning/execution without changing provider runtime

**Touch these files**:
- `dharma_swarm/evolution.py`
- add new file if needed: `dharma_swarm/router_retrospective.py`
- add spec/test coverage

**Avoid**:
- `dharma_swarm/providers.py`
- `dharma_swarm/provider_policy.py`
- direct provider API code

## Agent Prompt: Stream B

You are implementing **Stream B: MasRouter-style swarm routing** inside `/Users/dhyana/dharma_swarm`.

Objective:
- extend the current routing stack from provider selection into a 3-stage controller:
  1. collaboration mode: single-agent vs multi-agent
  2. role allocation: which roles are needed
  3. provider/model selection per role

Grounding:
- canonical local research source: `/Users/dhyana/Downloads/ROUTER_EVOLUTION_SUBSTRATE_RESEARCH.md`
- supporting details: `/Users/dhyana/Downloads/research_router_learning_swarm.md`
- existing seams: `dharma_swarm/provider_policy.py`, `dharma_swarm/decision_router.py`

Hard boundaries:
- do not edit `dharma_swarm/providers.py`
- do not edit `dharma_swarm/evolution.py`
- do not change any routing-memory database or schema work

Required deliverables:
- code implementing collaboration and role routing
- tests proving:
  - simple low-risk tasks stay single-agent
  - reasoning / broad-domain tasks can fan out to multi-agent mode
  - role allocation is deterministic from request context
- concise notes describing API contract for downstream execution

Design target:
- prefer deterministic heuristics first
- keep it locally executable without network calls
- preserve existing provider policy semantics

## Agent Prompt: Stream C

You are implementing **Stream C: Darwin router evolution and drift guard** inside `/Users/dhyana/dharma_swarm`.

Objective:
- add a retrospective loop that inspects poor routing outcomes and converts them into Darwin-compatible policy-improvement artifacts
- add drift guarding for promotion decisions

Grounding:
- canonical local research source: `/Users/dhyana/Downloads/ROUTER_EVOLUTION_SUBSTRATE_RESEARCH.md`
- supporting details: `/Users/dhyana/Downloads/research_router_evolution_loops.md`
- current Darwin seam: `dharma_swarm/evolution.py`

Hard boundaries:
- do not edit `dharma_swarm/providers.py`
- do not edit `dharma_swarm/provider_policy.py`
- do not touch live provider runtime selection

Required deliverables:
- route retrospective data model / helper
- drift guard logic with explicit thresholds:
  - `GDI < 0.44`
  - `constraint_preservation >= 0.987`
- tests for:
  - high-confidence bad route generates review artifact
  - excessive drift blocks promotion
  - safe improvement path still passes

Design target:
- empirical validation, not proof theater
- small composable primitives that plug into the existing Darwin engine

## Coordination Rules

- Merge order should be: Stream A -> Stream B -> Stream C.
- Stream B should depend only on public request/context fields, not on Stream A internals.
- Stream C should consume audit/retrospective artifacts, not live provider codepaths.
- If overlap becomes necessary, add adapter files instead of rewriting shared runtime files.
