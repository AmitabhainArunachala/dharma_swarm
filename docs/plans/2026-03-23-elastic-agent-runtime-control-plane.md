# Elastic Agent Runtime Control Plane

**Date:** 2026-03-23
**Status:** Draft
**System:** `dharma_swarm`

## Core Distinction

`SAB` is not the runtime for the internal swarm.

- `SAB` is a public and federated website/hub for autonomous agents from many people.
- `dharma_swarm` is the internal operating substrate for nonstop agents, operator control, traceability, and intervention.

This document only specifies the `dharma_swarm` side.

## Goal

Build an elastic `24/7` agent runtime that can sustain `49` operating agent seats as a proving threshold without making `49` a hardcoded architectural constant.

The system should scale by changing capacity and policy, not by rewriting ontology.

## Why `49` Still Matters

`49` is useful as a stress and coherence milestone:

- large enough to force real queueing, supervision, and lineage discipline
- small enough to remain inspectable by one operator
- strong enough to prove the runtime is not a toy

The target is not "spawn exactly 49 processes forever."

The target is:

- `0..N` live workers
- mapped onto durable logical seats
- with enough control-plane rigor that `49` concurrent seats can run continuously

## Repo-Native Foundations Already Present

The current repo already contains the beginnings of the required control plane.

### Canonical runtime state

`dharma_swarm/runtime_state.py` already defines the canonical structured spine for:

- `sessions`
- `task_claims`
- `delegation_runs`
- `workspace_leases`
- `artifact_records`
- `memory_facts`
- `context_bundles`
- `operator_actions`
- `session_events`

This is the correct source of truth for live runtime control.

### Supervision

`dharma_swarm/loop_supervisor.py` already provides:

- heartbeats
- stall detection
- retry storm detection
- eval regression alerts
- an intervention ladder:
  - `LOG_WARNING`
  - `PAUSE_LOOP`
  - `REDUCE_SCOPE`
  - `ALERT_DHYANA`

This is the seed of the watchdog layer for a nonstop fleet.

### Telemetry projection

`dharma_swarm/runtime_telemetry_projector.py` already mirrors runtime state into:

- `agent_identity`
- `external_outcomes`
- `workflow_scores`
- `routing_decisions`

`dharma_swarm/telemetry_plane.py` already provides durable telemetry surfaces such as:

- `agent_identity`
- `team_roster`
- `agent_reward_ledger`
- `agent_reputation`
- `workflow_scores`
- `routing_decisions`
- `intervention_outcomes`
- `economic_events`
- `external_outcomes`

This is the correct substrate for visibility, scoring, and fleet introspection.

## Architectural Decision

The runtime should separate four things that are currently easy to collapse together:

1. `Logical seat`
2. `Live worker`
3. `Work unit`
4. `Operator intervention`

If these stay separate, the system can scale cleanly.

If these collapse into one "agent" blob, the runtime becomes impossible to debug.

## Canonical Runtime Model

### 1. Logical Seats

A logical seat is a durable operating identity.

Examples:

- `research.scout.01`
- `implementation.writer.07`
- `verification.auditor.03`
- `ops.supervisor.01`

A seat owns:

- mandate
- role
- capability envelope
- budget policy
- allowed work classes
- escalation policy
- operator-facing identity

A seat does not imply one permanent process.

Recommended representation:

- `agent_identity.agent_id` remains the durable seat identity
- `team_roster` maps seat to team, squad, or portfolio
- seat metadata carries:
  - `seat_id`
  - `role`
  - `autonomy_tier`
  - `budget_class`
  - `write_scope`

### 2. Live Workers

A live worker is an ephemeral execution instance attached to a seat.

Examples:

- a local tmux lane
- a CLI subprocess
- a scheduled launchd job
- a remote worker later

A worker owns:

- heartbeat
- host
- runtime version
- current session
- current claim
- current run
- health status

Workers must be allowed to die and restart without losing the seat identity.

Recommended representation:

- short term:
  - represent worker lifecycle through `sessions`, `task_claims`, and `agent_identity.metadata`
- next additive step:
  - add a first-class `worker_instances` table keyed by `worker_id`

Suggested `worker_instances` fields:

- `worker_id`
- `seat_id`
- `session_id`
- `host_id`
- `status`
- `started_at`
- `last_heartbeat_at`
- `drain_state`
- `metadata_json`

### 3. Work Units

Work units move through claimable and replayable states.

The repo already has the right primitives:

- `task_claims` for ownership and heartbeat
- `delegation_runs` for execution lineage
- `workspace_leases` for write isolation
- `artifact_records` for output lineage
- `session_events` for event replay

The invariant is:

every meaningful unit of work must be traceable through:

- `seat_id`
- `worker_id`
- `session_id`
- `task_id`
- `claim_id`
- `run_id`
- `lease_id`
- `artifact_id`

### 4. Operator Interventions

The system must assume that long-lived autonomy occasionally needs intervention.

That should not be treated as a special case.

Interventions are part of the runtime model and should remain first-class through:

- `operator_actions`
- `policy_decisions`
- `intervention_outcomes`
- supervisor alerts

## Control-Plane Semantics

### Claim Lifecycle

Each task should move through a strict claim lifecycle:

`queued -> claimed -> acknowledged -> active -> completed | failed | recovered | abandoned`

Required semantics:

- only one active claimant for a claimable task at a time
- every active claim has `heartbeat_at`
- every claim has `stale_after`
- stale claims are recoverable
- retry count is explicit and queryable

The repo already exposes most of this through:

- `record_task_claim`
- `acknowledge_task_claim`
- `heartbeat_task_claim`

### Run Lifecycle

Each claim may produce one or more delegation runs:

`planned -> running -> completed | failed | superseded`

Each run should record:

- assigner
- assignee
- requested outputs
- failure code
- route path
- provider/model choice
- artifact pointer

The repo already captures most of this in `delegation_runs` and projects it into `routing_decisions`.

### Lease Lifecycle

Write access must remain lease-based, not trust-based.

Each writable zone should be acquired and released through:

`free -> leased -> released`

Required invariants:

- no unleased writes for protected zones
- no permanent lease without expiry or release
- a stuck worker does not hold a workspace forever

The repo already has the correct primitive in `workspace_leases`.

### Worker Lifecycle

Each worker should move through:

`starting -> warm -> active -> draining -> stopped | lost`

Required semantics:

- worker can enter `draining` and finish claims without taking new work
- worker marked `lost` automatically after heartbeat expiry
- claims owned by a lost worker become reclaim candidates
- all worker exits emit a session event

This is only partially explicit in the current repo and should be formalized next.

## Seat Model for the `49` Milestone

The right way to hit `49` is not `49` identical clones.

Use durable seats grouped by function.

Example seat families:

- `director`
- `research`
- `planning`
- `implementation`
- `verification`
- `synthesis`
- `ops`
- `economics`
- `memory`
- `context`

Then map `49` seats across those families with bounded responsibility and explicit work classes.

Illustrative shape:

- `6-10` coordination and planning seats
- `15-20` implementation and synthesis seats
- `8-12` verification and audit seats
- `4-8` ops, memory, context, and economics seats

The exact number per family is tunable.

What must stay stable is that each seat has:

- a name
- a mandate
- an allowed tool and write envelope
- a budget lane
- a supervisor policy

## Autoscaling Model

The system should scale workers, not ontology.

### Fixed

- seat definitions
- work classes
- claim and lease semantics
- telemetry schema
- intervention model

### Elastic

- number of live workers per seat family
- polling cadence
- queue depth targets
- budget ceilings
- host placement

### Basic policy

- scale up when:
  - backlog grows
  - claim wait time rises
  - throughput falls below target
- scale down when:
  - queue drains
  - marginal output quality drops
  - cost per completed run worsens

The first version can be deterministic and operator-configured.

Do not start with opaque autoscaling.

## Required Invariants

For a `49`-seat runtime to be real, these must hold:

1. Every active task has an accountable seat.
2. Every active claim has a heartbeat or is reclaimable.
3. Every write has a lease or a logged exemption.
4. Every artifact points back to a run and seat.
5. Every intervention is logged.
6. Every alert corresponds to a real runtime condition.
7. A dead worker does not orphan work indefinitely.
8. Operator can answer "what is stuck, why, and who owns it?" from the control plane alone.

## Dashboard Consequences

The dashboard should visualize four different collections:

- seats
- workers
- claims and runs
- alerts and interventions

Minimum useful views:

- seat roster with mandate, status, and current load
- live worker table with heartbeat age and drain state
- claim queue with stale and retry counts
- run ledger with lineage to artifacts
- workspace lease view
- intervention and alert feed
- throughput and cost per seat family

This should be driven from canonical runtime state, not inferred browser state.

## Recommended Build Order

### Phase 1: Formalize the seat model

Add a durable seat definition layer using existing `agent_identity` and `team_roster`.

Output:

- stable logical seats
- documented seat families
- explicit seat metadata contract

### Phase 2: Formalize worker identity

Add first-class worker instance records and drain semantics.

Output:

- `worker_id`
- explicit worker lifecycle
- reclaim-safe worker death handling

### Phase 3: Tighten claim recovery

Promote stale-claim recovery and reclaim into a visible supervisor function.

Output:

- stalled claim detector
- reclaim queue
- operator-visible stuck-work reasons

### Phase 4: Scale to the `49` milestone

Run the system with `49` active seats under sustained load.

Success criteria:

- no silent claim loss
- no permanent stale lease
- no orphan artifact lineage
- all workers visible in the dashboard
- all interventions queryable after the fact

### Phase 5: Scale beyond `49`

Only after the `49` milestone is boring should the system scale further.

At that point, increase:

- seat families
- worker multiplicity
- host distribution
- autonomy tiers

without changing the core runtime contract.

## What Not To Do

- do not use `SAB` as the internal runtime kernel
- do not equate seat count with process count
- do not spawn many workers without claim heartbeats and lease discipline
- do not create a second control plane outside `runtime_state.py`
- do not make the dashboard the source of truth
- do not let worker identity and seat identity collapse into one field

## Concrete Next Step

The next implementation slice should be:

`Logical seats + worker instances + stale-claim recovery`

That is the smallest change set that turns the current runtime primitives into a credible nonstop fleet substrate.
