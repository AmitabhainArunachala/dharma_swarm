---
title: DHARMA SWARM Three-Plane Architecture
path: docs/architecture/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md
slug: dharma-swarm-three-plane-architecture
doc_type: documentation
status: active
summary: One System, Three Planes
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - dharma_swarm/runtime_state.py
  - dharma_swarm/operator_bridge.py
  - dharma_swarm/operator_views.py
  - dharma_swarm/message_bus.py
  - dharma_swarm/session_ledger.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- research_methodology
- verification
- product_strategy
- frontend_engineering
inspiration:
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- dharma_swarm/runtime_state.py
- dharma_swarm/operator_bridge.py
- dharma_swarm/operator_views.py
- dharma_swarm/message_bus.py
- dharma_swarm/session_ledger.py
connected_python_modules:
- dharma_swarm.runtime_state
- dharma_swarm.operator_bridge
- dharma_swarm.operator_views
- dharma_swarm.message_bus
- dharma_swarm.session_ledger
connected_relevant_files:
- dharma_swarm/runtime_state.py
- dharma_swarm/operator_bridge.py
- dharma_swarm/operator_views.py
- dharma_swarm/message_bus.py
- dharma_swarm/session_ledger.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/architecture/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md
  retrieval_terms:
  - three
  - plane
  - architecture
  - '2026'
  - one
  - system
  - planes
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: One System, Three Planes
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
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
# DHARMA SWARM Three-Plane Architecture

## One System, Three Planes

`dharma_swarm` should evolve into an agent-native operating system for an AI-run company.

The correct shape is not three disconnected dashboards. It is one canonical runtime substrate projected into three different control planes:

1. `Command Nexus`
2. `Fitness Engine`
3. `Agent World`

If the three planes do not read from the same underlying facts, the system will become visually impressive but operationally false.

## North Star

The system should support:

- real work orchestration
- operator intervention and audit
- swarm-wide performance scoring
- economic and external-outcome feedback
- compelling visibility into agent behavior

The company should be measurable at three levels:

- execution: what is happening now
- performance: what outcomes are being produced
- embodiment: how the company feels to observe and direct

## Shared Substrate

All three planes should be projections over a common substrate.

### Canonical state

Current strongest foundations:

- `dharma_swarm/runtime_state.py`
- `dharma_swarm/operator_bridge.py`
- `dharma_swarm/operator_views.py`
- `dharma_swarm/message_bus.py`
- `dharma_swarm/session_ledger.py`

This substrate should become the single source of truth for:

- sessions
- task claims
- delegation runs
- artifacts
- context bundles
- operator actions
- session events
- bridge queue state

### Missing substrate tables / records

The next layer of missing facts is not UI. It is company telemetry:

- `agent_identity`
- `agent_reward_ledger`
- `agent_reputation`
- `team_roster`
- `external_outcomes`
- `customer_feedback`
- `revenue_events`
- `cost_events`
- `workflow_scores`
- `policy_decisions`
- `routing_decisions`
- `intervention_outcomes`

Without these, Plane 3 cannot become real and Plane 1 cannot be honest.

### Event model

Every meaningful state change should be representable as an event with:

- `event_id`
- `session_id`
- `task_id`
- `run_id`
- `agent_id`
- `event_type`
- `status_before`
- `status_after`
- `payload`
- `economic_impact`
- `quality_impact`
- `operator_visible`
- `created_at`

This should drive all read models and all visualizations.

## Plane 1: Command Nexus

This is the serious control plane. It should be the first productized surface because the repo already has real foundations here.

### Primary purpose

Answer:

- what is running
- what is blocked
- what is failing
- what is risky
- what needs human intervention
- where value is flowing
- where the swarm is wasting effort

### Current repo foundation

- `dharma_swarm/runtime_state.py`
- `dharma_swarm/operator_bridge.py`
- `dharma_swarm/operator_views.py`
- `dashboard/src/lib/types.ts`
- `dashboard/src/app/dashboard/page.tsx`

### Required views

- mission overview
- active sessions and runs
- task pipeline and dependency graph
- queue pressure and claim timeouts
- artifact lineage
- operator interventions
- anomaly feed
- cost and throughput dashboard
- policy/routing decisions
- failure replay timeline

### Hard requirements

- everything drillable down to raw events
- every intervention logged
- every run traceable to agent, task, artifact, and outcome
- every alert tied to a real runtime condition, not a synthetic badge

### API / read model direction

Add or consolidate read models for:

- `overview`
- `runs`
- `queue`
- `artifacts`
- `interventions`
- `economics`
- `routing`
- `anomalies`
- `outcomes`

This is where the current dashboard should harden first.

## Plane 2: Fitness Engine

This is the company nervous system. Do not name this plane `RL`. RL is one possible mechanism inside it.

### Primary purpose

Continuously evaluate and improve the swarm using external outcomes and operational quality.

### Current repo foundation

- `dharma_swarm/economic_fitness.py`
- `dharma_swarm/quality_forge.py`
- `dharma_swarm/provider_policy.py`
- `dharma_swarm/adaptive_autonomy.py`
- `dharma_swarm/ucb_selector.py`
- `dharma_swarm/archive.py`

### Core score families

- execution quality
- external value delivered
- revenue generated
- cost efficiency
- output quality
- reliability
- speed
- coordination quality
- strategic learning
- operator trust

### What is missing now

The repo scores internal behavior better than external business outcomes. The missing work is:

- first-class revenue and cost records
- first-class customer feedback records
- first-class conversion and adoption records
- credit assignment from company outcomes back to runs, workflows, agents, and policies
- policy evaluation loops across time windows
- reward settlement for agents and teams

### Recommended implementation strategy

Start with:

- deterministic score aggregation
- weighted reward formulas
- bandit routing and policy comparison
- offline evaluation
- batch policy updates

Do not start with:

- full online RL
- opaque end-to-end policy tuning
- reinforcement loops without strong replay and audit

### Core outputs

- swarm fitness score
- workflow fitness score
- agent reward balance
- team performance score
- policy win rate
- routing confidence score
- intervention efficacy score

## Plane 3: Agent World

This is the immersive animated plane. It should be built last among the three visible planes, but designed early so the schema supports it.

### Primary purpose

Make the company legible, motivating, and inspectable at the human level.

### Current repo foundation

- `dashboard/src/app/dashboard/agents/page.tsx`
- `dashboard/src/components/dashboard/AgentCard.tsx`
- `dharma_swarm/models.py`

### Why it is not real yet

Current agent visualization is still mostly thin status projection:

- agent identity is too sparse
- health is mostly inferred from coarse status
- there is no real reward ledger
- there is no reputation system
- there is no rich squad or department model
- there is no grounded world-state

### Schema additions needed

Extend agent identity to include:

- `codename`
- `serial`
- `avatar_id`
- `department`
- `squad_id`
- `specialization`
- `level`
- `xp`
- `reputation`
- `reward_balance`
- `morale`
- `focus`
- `load`
- `economic_contribution`
- `quality_contribution`

### Visual rules

The immersive plane should only simulate presentation, not operational truth.

Good simulation:

- walking between rooms
- collaboration huddles
- mood and energy animation
- reward bursts
- office occupancy

Bad simulation:

- fake throughput
- fake productivity
- fake health
- fake “success” effects detached from real outcomes

The world should be an expressive rendering of the same facts used by Planes 1 and 2.

## Recommended Build Order

### Phase 1: Stabilize the substrate

Target:

- make `runtime_state` and `operator_bridge` the canonical control spine
- define missing outcome and reward schemas
- standardize event names and runtime IDs

Deliverables:

- event taxonomy
- outcome tables
- reward ledger tables
- policy decision records
- canonical read APIs

### Phase 2: Finish Command Nexus

Target:

- give the operator one trustworthy system map

Deliverables:

- queue and run views
- task dependency and blockage views
- intervention console
- artifact and lineage views
- anomaly and timeout views
- throughput and cost views

Success condition:

- an operator can understand the state of the company in under 60 seconds

### Phase 3: Unify Fitness Engine

Target:

- give the swarm a coherent performance and learning loop

Deliverables:

- company scorecard
- workflow scoring
- agent/team reward settlement
- bandit-based routing optimizer
- offline policy evaluator
- score history and replay

Success condition:

- the system can explain why one policy, workflow, or agent cohort is outperforming another

### Phase 4: Build Agent World

Target:

- make the company visible and emotionally legible

Deliverables:

- agent identity layer
- squad/world model
- room/zone projection
- avatar status animations
- reward/reputation visuals
- drill-through from avatar to real run, task, and outcome data

Success condition:

- the immersive world becomes a truthful operator surface, not a toy

## Real-Time vs Batched vs Simulated

### Real-time

- session status
- task claims
- run status
- queue pressure
- heartbeats
- anomalies
- operator actions
- policy/routing decisions

### Batched

- economic impact
- customer feedback aggregation
- reward settlement
- team scoring
- provider performance windows
- weekly strategy reports

### Simulated / interpolated

- avatar movement
- office occupancy animation
- ambient collaboration behavior
- mood transitions
- ceremonial reward effects

Simulation should smooth real events, never invent business truth.

## What Stays in Python

- orchestration
- policy logic
- agent prompting
- evaluation pipelines
- experimentation
- score aggregation
- batch learning loops

## Where Rust Helps

Only introduce Rust where it buys real value:

- append-only event spine
- high-volume stream aggregation
- retrieval/indexing hot paths
- queue/scheduler core
- websocket fanout for high-frequency UI updates

Do not move logic to Rust just because the repo feels large.

## Where Go Helps

Go is better than Rust for:

- supervisors
- service wrappers
- deploy/control daemons
- long-running ops binaries

If the system needs a clean operations sidecar or multi-host control daemon, Go is a strong fit.

## Current High-ROI Repo Sharpening

Highest ROI targets right now:

1. split `dharma_swarm/dgc_cli.py` into thinner command surfaces
2. reduce orchestration coupling in `dharma_swarm/swarm.py` and `dharma_swarm/orchestrator.py`
3. enrich `dharma_swarm/models.py` with agent identity and company telemetry contracts
4. unify dashboard APIs around the runtime spine instead of ad hoc views
5. add first-class outcome economics and reward ledgers before building more game UI

## Anti-Patterns To Avoid

- building the animated office before the fitness and runtime schemas exist
- calling the performance plane “RL” before outcome capture is real
- allowing each UI plane to invent its own metrics
- mixing control-plane truth with purely decorative frontend state
- scaling language/runtime complexity before fixing architecture boundaries

## Definition of Done

The architecture is working when:

- operators trust the command center
- the swarm is scored on real external outcomes
- agent rewards and reputation have a factual basis
- the immersive world reflects reality instead of masking it
- policy changes can be replayed, compared, and audited

At that point `dharma_swarm` stops being a swarm toolkit and becomes a real operating system for an AI-run company.
