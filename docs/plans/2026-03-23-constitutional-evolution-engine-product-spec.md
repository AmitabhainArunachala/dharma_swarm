# dharma_swarm Constitutional Evolution Engine

## Merge-Target Product Spec

**Date:** 2026-03-23
**Status:** Merge-target architecture
**Scope:** Constitutional replication + operating fleet scaling + trajectory learning + daily operational rhythm
**Intent:** Turn `dharma_swarm` from a capable multi-agent runtime into a bounded, self-specializing, self-improving organism without creating a second control plane or colliding with parallel dashboard work

**Synthesizes:**

- `docs/superpowers/specs/2026-03-22-self-replicating-agents-design.md`
- `docs/plans/2026-03-23-elastic-agent-runtime-control-plane.md`

## 1. Product Boundary

### What this system is

`dharma_swarm` is the internal runtime and control substrate for:

- nonstop agents
- operator intervention
- trajectory capture
- constitutional growth
- bounded learning
- fleet observability

### What this system is not

`SAB` is not the kernel for this work.

- `SAB` is a public and federated website or hub for autonomous agents from many people
- `dharma_swarm` is the internal operating substrate

This product spec only covers the `dharma_swarm` side.

### Merge-safe rule

This spec must fit the repo as it exists now:

- no new repo
- no second orchestrator
- no second control plane
- no dashboard-owned truth
- no rewrite of the parallel visualization track

The dashboard and API should read projections of canonical state. They should not become the place where constitutional logic lives.

## 2. Core Thesis

`dharma_swarm` should not merely run agents. It should behave as a governed organism that can:

- observe its own runtime behavior
- identify persistent structural gaps
- create new persistent specialists when justified
- learn from real work trajectories
- improve prompts, routing, and datasets
- remain bounded by explicit governance and population rules

The right synthesis is not "autonomy everywhere."

It is:

- fast runtime execution
- slow constitutional change
- continuous behavioral learning
- hard population and budget constraints
- first-class observability and intervention

## 3. Repo Truth Today

This spec is anchored to what is already present in the codebase, not wishful architecture.

### 3.1 Control-plane substrate is already real

`dharma_swarm/runtime_state.py` is already the canonical structured spine for:

- `sessions`
- `task_claims`
- `delegation_runs`
- `workspace_leases`
- `artifact_records`
- `context_bundles`
- `operator_actions`
- `session_events`

`dharma_swarm/loop_supervisor.py` already provides:

- heartbeat tracking
- stall detection
- retry storm detection
- eval regression alerts
- intervention ladder semantics

`dharma_swarm/runtime_telemetry_projector.py` and `dharma_swarm/telemetry_plane.py` already provide durable fleet telemetry for:

- `agent_identity`
- `team_roster`
- `agent_reward_ledger`
- `agent_reputation`
- `workflow_scores`
- `routing_decisions`
- `intervention_outcomes`
- `economic_events`
- `external_outcomes`

This is the correct substrate for the rest of the system.

### 3.2 Constitutional replication is already wired

The replication stack is not hypothetical. It exists today:

- `dharma_swarm/replication_protocol.py`
- `dharma_swarm/genome_inheritance.py`
- `dharma_swarm/population_control.py`
- `dharma_swarm/agent_constitution.py`
- `dharma_swarm/orchestrate_live.py`

`orchestrate_live.py` already runs a replication monitor as loop `9`.

### 3.3 Learning flywheel is already partially wired

The learning side is also not just scattered modules. It is already composed by:

- `dharma_swarm/training_flywheel.py`
- `dharma_swarm/trajectory_collector.py`
- `dharma_swarm/thinkodynamic_scorer.py`
- `dharma_swarm/strategy_reinforcer.py`
- `dharma_swarm/dataset_builder.py`
- `dharma_swarm/model_registry.py`
- `dharma_swarm/economic_engine.py`
- `dharma_swarm/resource_scout.py`

`orchestrate_live.py` already launches the training flywheel as loop `10`.

What is live today is:

- trajectory reinforcement
- dataset construction
- training readiness and budget checks

What is not yet a full closed loop is:

- automatic training execution
- automatic evaluation against incumbent baselines
- automatic promotion of a new deployed generation

## 4. The Missing Distinction That Makes the Whole System Coherent

The current architectural tension disappears once four layers are separated.

### Layer A: Control Plane

This is the substrate:

- claims
- runs
- leases
- events
- telemetry
- supervision

This layer must stay singular.

### Layer B: Operating Fleet

This is where the `49` milestone belongs.

It consists of:

- logical operating seats
- live workers attached to those seats
- real tasks, runs, artifacts, and interventions

This layer can scale.

### Layer C: Constitutional Population

This is not the same thing as the operating fleet.

It consists of:

- the six founding constitutional agents
- a small number of durable replicated specialists
- slow, checkpointed changes to the persistent topology

This layer must remain small, deliberate, and bounded.

### Layer D: Learning Flywheel

This layer improves behavior within the runtime by metabolizing real work:

- trajectories
- strategy patterns
- datasets
- model readiness
- eventually model comparison and promotion

This layer must remain subordinate to constitutional and budget gates.

## 5. One Runtime, Two Populations

This is the key synthesis.

### Constitutional population stays small

The constitutional roster is the durable organism topology:

- six founding agents are immutable
- dynamic replicated children are slow and rare
- total stable population remains bounded

This is where replication and apoptosis operate.

### Operating population can scale to `49+`

The operating fleet is the active execution layer:

- many logical seats can exist under constitutional authority
- many live workers can be attached to those seats
- worker count is elastic
- seat count can grow to `49` and beyond without requiring `49` constitutional species

This is how the system can be both:

- constitutionally bounded
- operationally large

Without this separation, "replication cap = 8" and "operate 49 agents nonstop" appear contradictory. They are not.

## 6. Canonical Runtime Model

### 6.1 Logical operating seats

A seat is a durable runtime identity such as:

- `research.scout.01`
- `implementation.writer.07`
- `verification.auditor.03`
- `ops.supervisor.01`

A seat owns:

- mandate
- role
- write scope
- budget class
- escalation policy
- supervising constitutional parent

A seat is durable. A seat is not a process.

### 6.2 Live workers

A worker is an ephemeral executor attached to a seat.

Examples:

- tmux lane
- local subprocess
- scheduled loop
- remote worker later

A worker owns:

- heartbeat
- host
- session
- claim
- run
- drain state

Workers must be restartable without destroying seat identity.

### 6.3 Work units

Work must remain traceable through:

- `seat_id`
- `worker_id`
- `session_id`
- `task_id`
- `claim_id`
- `run_id`
- `lease_id`
- `artifact_id`

### 6.4 Operator interventions

Intervention is part of the runtime, not an exception path.

It must remain first-class through:

- `operator_actions`
- `policy_decisions`
- `intervention_outcomes`
- supervisor alerts

## 7. Constitutional Replication Engine

The replication system is the organism's constitutional growth membrane.

The five-stage checkpoint pipeline is correct and should remain canonical:

- `G1 Proposal`
- `S Assessment`
- `G2 Gate Check`
- `M Materialize`
- `Post-M Probation`

This keeps persistent growth:

- explicit
- slow
- reviewable
- durable

### Current repo mapping

- `replication_protocol.py` owns checkpoint execution
- `genome_inheritance.py` owns inherited prompt or kernel or memory composition
- `population_control.py` owns cap or cull or apoptosis or probation
- `agent_constitution.py` owns frozen roster plus `DynamicRoster`
- `consolidation.py` owns persistent gap detection and proposal production
- `orchestrate_live.py` owns long-cycle replication monitoring

## 8. Learning Through Real Work

The learning path should metabolize actual work already performed by the swarm.

The correct doctrine is:

- learn from real task execution
- optimize prompts, routing, and strategies first
- build datasets from successful work plus foundations
- check budget and readiness before training
- only promote model generations that beat the incumbent

The current repo already supports the first four items.

The missing last step is a governed training and evaluation promotion protocol.

## 9. Daily Rhythm

A healthy day in the finished system should look like this.

### During the day

- seats and workers handle normal tasks
- claims and runs produce artifacts
- trajectories are captured from real work
- telemetry accumulates evidence on cost, quality, and failure

### Every few hours

- runtime signals are summarized
- strategy reinforcement extracts winning patterns
- routing and method-level adaptation improve execution

### At consolidation time

- consolidation produces loss reports and differentiation proposals
- persistent capability gaps are distinguished from transient noise

### At replication time

- pending proposals enter the G1 -> S -> G2 -> M pipeline
- any required cull happens first
- child agent is materialized into the dynamic constitutional roster
- probation begins under heightened scrutiny

### At learning time

- high-quality trajectories are scored
- datasets are assembled
- readiness is checked against budget and resource constraints
- only if later evaluation gates pass does model promotion occur

This is the flywheel:

`work -> traces -> reflection -> specialization -> improvement -> better work`

## 10. Merge Strategy

This spec should merge safely with the parallel visualization and control-plane build by respecting write-scope boundaries.

### This spec owns

- constitutional evolution semantics
- runtime seat and worker distinction
- learning flywheel product contract
- durability and invariants for growth and learning

### This spec does not own

- dashboard page composition
- visualization router design
- ReactFlow or operator UI rendering details

### Shared rule

All read models for visualization should come from canonical runtime or telemetry state.

No architectural logic from this spec should require a frontend-owned source of truth.

## 11. What Must Be True Before Claiming Merge-Ready

These are the real merge gates, grounded in the current code.

### 11.1 Dynamic agents must become first-class runtime citizens

`DynamicRoster` exists, but several lookup paths still read only the frozen constitutional roster through static helpers.

That means replicated children are not yet universally treated as equal runtime citizens.

This must be resolved in all lookup and authority paths that currently assume:

- `CONSTITUTIONAL_ROSTER`
- `get_agent_spec()`

are sufficient on their own.

### 11.2 Generation semantics must be derived, not trusted

Today the replication pipeline accepts `proposal.generation` and passes it through the materialization path.

That is workable, but it is weaker than deriving lineage from the actual parent record at runtime.

The merge target should derive effective generation from:

- parent lineage
- dynamic roster metadata
- genome template provenance

not only from proposal payload.

### 11.3 Population control must use real composite fitness

`PopulationController` already supports injected fitness, but its fallback behavior is neutral.

That means culling is not yet fully grounded in live swarm quality unless the runtime injects a real fitness function.

The merge target should compute cull and apoptosis decisions from explicit composite fitness combining at least:

- runtime performance
- thinkodynamic quality
- outcome value
- reliability
- operator trust or intervention burden

### 11.4 Replication and learning state must be visible in the control plane

Durability under `~/.dharma/replication/` is good, but it is not enough by itself.

Replication proposals, probation, apoptosis, and training readiness should also become visible through canonical runtime or telemetry projections.

Otherwise the operator cockpit remains blind to the organism's own self-modification path.

### 11.5 The training flywheel must stay honest about what is active

The current training flywheel is real, but it currently stops at:

- reinforcement
- dataset build
- readiness and recommendation

That is good and useful.

It should not be described as autonomous model training and deployment until:

- training jobs actually run
- evaluation compares challenger to incumbent
- promotion is gated and durable

### 11.6 The whole system must survive restart

The following state must remain durable across restart:

- replication proposals
- dynamic roster
- genome lineage
- probation status
- apoptosis log
- seat metadata
- worker identity
- training lineage
- model lineage

In-process signals may accelerate work. They cannot be the source of truth.

## 12. Phased Build Plan

This is the merge-safe sequence.

### Phase 1: Runtime citizenship

Make dynamic agents and operating seats first-class in runtime lookup and authority paths.

Output:

- unified lookup path for static and dynamic agents
- seat model formalized
- no frozen-roster-only authority assumptions

### Phase 2: Worker identity and recovery

Introduce first-class worker identity and reclaim-safe semantics.

Output:

- `worker_id`
- heartbeat ownership
- drain and loss states
- reclaimable stale claims

### Phase 3: Fitness-grounded population control

Inject real composite fitness into cull and apoptosis decisions.

Output:

- real culling basis
- visible probation scoring
- explicit death rationale

### Phase 4: Replication visibility

Project replication and probation state into runtime or telemetry read models.

Output:

- operator-visible proposal queue
- probation table
- apoptosis history
- child lineage view

### Phase 5: Learning flywheel hardening

Promote training from readiness recommendation to governed execution.

Output:

- training job records
- challenger versus incumbent evaluation
- gated promotion semantics
- model lineage visible to operators

### Phase 6: `49` operating-seat milestone

Scale the operating fleet to `49` logical seats with durable lineage and intervention surfaces.

Success means:

- no orphan work
- no invisible workers
- no permanent stale lease
- no silent constitutional mutations
- no model promotion without evaluation

## 13. Hard Invariants

These rules should remain non-negotiable.

1. There is one control plane.
2. The six founding constitutional agents are immutable.
3. Constitutional population is bounded and slow-changing.
4. Operating fleet scale is elastic and separate from constitutional population.
5. Every active claim has heartbeat or reclaim semantics.
6. Every write has a lease or explicit exemption.
7. Every artifact traces back to a run and accountable seat.
8. Every constitutional birth has a durable rationale and lineage record.
9. Every constitutional death has a durable rationale and audit record.
10. No model promotion happens outside budget, evaluation, and governance gates.

## 14. Final Position

The self-replication system is the constitutional heart.

The training flywheel is the adaptive metabolism.

The control plane is the nervous system.

The operating seat and worker fleet is the musculature that can scale to `49+`.

The correct future is not to choose one of these.

It is to bind them without collapsing them into each other:

- specialize slowly
- learn continuously
- operate at scale
- stay bounded
- stay observable
- never optimize outside the governance membrane
