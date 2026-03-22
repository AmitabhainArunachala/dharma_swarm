# Sovereign Build Phase Master Spec

Date: 2026-03-19
Status: proposed canonical operational build doctrine
Scope: next build phase for `/Users/dhyana/dharma_swarm`

## 1. Thesis

DHARMA SWARM will not win by becoming a thin wrapper around Hermes, OpenClaw, Letta, LangGraph, ADK, NeMo, Goose, or OpenHands.

DHARMA SWARM will win by becoming the sovereign superset that:

- owns its own runtime contracts
- owns its own state model
- owns its own operator experience
- can absorb the strongest ideas from other systems without depending on their internals

This phase is therefore not an "integration phase" in the naive sense.

It is a sovereignty phase.

The architecture goal is:

One canonical runtime substrate.
One canonical contract layer.
Three coherent product planes.
Many donor-inspired capabilities behind DHARMA-owned interfaces.

## 2. Build Principles

### 2.1 Canonical truth

All product planes must project from DHARMA-owned facts.

Canonical state lives in DHARMA-owned stores and schemas, not in external repo formats.

### 2.2 Interface ownership

DHARMA owns the contracts for:

- runtime execution
- memory
- gateway/channel delivery
- scheduling
- skills and learning
- evaluation and observability
- checkpoints and recovery
- sandbox/execution backends
- interop and migration

External systems may inspire or back implementations, but they do not define DHARMA's contracts.

### 2.3 Selective donor absorption

We copy ideas aggressively.
We port code selectively when the license is clear and the code is truly superior.
We reimplement natively when the capability touches identity, memory, orchestration, telemetry, or state truth.

### 2.4 Zero-budget bias

The system must remain viable without hosted dependencies or paid platforms.

Paid providers may be used as optional execution lanes. They are never architectural prerequisites.

### 2.5 Audit-first execution

Every meaningful runtime transition should be replayable, attributable, and explainable.

### 2.6 No new fantasy surfaces

Do not widen the visible product surface until the substrate and read models are made honest.

## 3. Verified Starting Point

The current repo already contains:

- runtime state spine
- operator bridge and views
- async message bus
- session ledger
- event memory substrate
- persistent agents
- cron scheduler
- resident operator flow
- API and dashboard surfaces
- MCP server
- evaluation and evolutionary components
- broad test coverage

The next phase starts from these real assets. It does not discard them.

## 4. Core Problems This Phase Must Solve

### 4.1 Interface poverty

Strong subsystems exist, but too many features still wire together through direct module knowledge instead of stable contracts.

### 4.2 Telemetry incompleteness

Runtime state exists, but company telemetry is still not first-class:

- rewards
- reputation
- economics
- external outcomes
- routing decisions
- policy decisions
- intervention outcomes

### 4.3 Plane incoherence

The repo has material for Command Nexus, Fitness Engine, and Agent World, but only Command Nexus is close to being product-real.

### 4.4 Donor drift risk

Some modules already absorb external patterns directly. That is acceptable only if those patterns are recast as DHARMA-native contracts.

## 5. Canonical Interface Layer

Create and make authoritative a contract layer under a DHARMA-owned package, for example:

- `dharma_swarm/contracts/`

The following interfaces are canonical and mandatory.

### 5.1 `AgentRuntime`

Purpose:

- spawn, resume, stop, and inspect agent execution
- attach runs to sessions, tasks, checkpoints, and artifacts

Required semantics:

- durable run identity
- explicit status machine
- parent/child run relationships
- checkpoint hooks
- operator-visible transitions

### 5.2 `GatewayAdapter`

Purpose:

- abstract channels, assistant delivery, notifications, and device/app surfaces

Required semantics:

- channel registry
- send/receive semantics
- delivery acknowledgement
- message provenance
- user/operator targeting

### 5.3 `MemoryPlane`

Purpose:

- unify promoted facts, turns, shards, uptake, retrieval, and source documents

Required semantics:

- write candidate memory
- promote or decay memory
- retrieve by task/session/agent/user/skill
- attach provenance
- attach trust state
- emit uptake signals

### 5.4 `LearningEngine`

Purpose:

- convert traces, artifacts, and outcomes into reusable skill and routing improvements

Required semantics:

- extract skill candidates
- score skills over time
- update user model
- update agent model
- produce routing hints

### 5.5 `SkillStore`

Purpose:

- persist executable skills, prompts, recipes, and learned procedures in DHARMA-owned format

Required semantics:

- versioned skill artifacts
- provenance to runs and outcomes
- evaluation history
- trust and promotion state

### 5.6 `EvaluationSink`

Purpose:

- canonical landing zone for all eval, judge, replay, and operational quality signals

Required semantics:

- attach scores to runs, workflows, policies, skills, and agents
- store cost, latency, and throughput
- store judge rationale and evidence refs
- store pass/fail and confidence

### 5.7 `CheckpointStore`

Purpose:

- durable checkpoint and resume semantics across workflows and agents

Required semantics:

- checkpoint creation
- checkpoint metadata
- replay boundary
- resume legality
- operator approval requirements

### 5.8 `SandboxProvider`

Purpose:

- abstract local, subprocess, container, SSH, or future remote execution backends

Required semantics:

- execute
- inspect workspace
- attach outputs/artifacts
- enforce safety policy
- expose capability metadata

### 5.9 `InteropAdapter`

Purpose:

- import/export or interoperate with donor ecosystems without architectural dependence

Required semantics:

- OpenClaw import/export
- Hermes import/export
- MCP server/client mapping
- A2A/ACP compatibility mapping

## 6. Canonical Data Planes

The current runtime spine is good but incomplete. This phase extends it into five explicit data planes.

### 6.1 Runtime plane

Existing base:

- sessions
- task claims
- delegation runs
- workspace leases
- artifacts
- context bundles
- operator actions
- session events
- bridge queue state

### 6.2 Memory plane

Existing base:

- event log
- source documents
- retrieval log
- conversation turns
- idea shards
- idea links
- uptake

### 6.3 Telemetry plane

Must be added as first-class records:

- `agent_identity`
- `agent_reward_ledger`
- `agent_reputation`
- `team_roster`
- `workflow_scores`
- `routing_decisions`
- `policy_decisions`
- `intervention_outcomes`
- `revenue_events`
- `cost_events`
- `external_outcomes`
- `customer_feedback`

### 6.4 Skill plane

Must be added or normalized:

- `skills`
- `skill_versions`
- `skill_evaluations`
- `skill_dependencies`
- `skill_promotions`

### 6.5 Checkpoint plane

Must be added:

- `workflow_checkpoints`
- `checkpoint_artifacts`
- `checkpoint_approvals`
- `resume_attempts`

## 7. Product Planes

### 7.1 Plane 1: Command Nexus

This is the first productized surface and the first hardening target.

It must answer:

- what is running
- what is blocked
- what is risky
- what needs approval
- where value is flowing
- where the swarm is wasting effort

It must be powered only by real runtime, memory, telemetry, and evaluation records.

Core views:

- mission overview
- active sessions and runs
- queue and claim pressure
- artifact lineage
- interventions
- anomalies
- economics
- routing and policy decisions
- failure replay

### 7.2 Plane 2: Fitness Engine

This is the canonical evaluation and adaptation plane.

It must unify:

- internal quality
- external outcomes
- economics
- routing experiments
- skill win rates
- intervention efficacy
- operator trust

Start deterministic and auditable.
Do not jump to opaque online RL.

### 7.3 Plane 3: Agent World

This is built last.

It becomes real only after telemetry exists for:

- identity
- team structure
- rewards
- reputation
- embodied state
- squad or department placement

Until then it is a derived visualization, not a core build target.

## 8. Donor Map

### 8.1 OpenClaw

Absorb:

- assistant/gateway product shape
- channel abstractions
- device/app node idea
- onboarding and doctor ergonomics
- safety-default packaging

Do not absorb:

- external state model as canonical truth

### 8.2 Hermes

Absorb:

- learning loop posture
- skill extraction
- persistent user model concepts
- cron ergonomics
- remote backend abstraction
- migration semantics

Do not absorb:

- direct runtime dependence on Hermes internals

### 8.3 Letta

Absorb:

- memory product discipline
- explicit stateful-agent framing
- memory as primary architecture

Do not absorb:

- an external memory schema as canonical truth

### 8.4 LangGraph and ADK

Absorb:

- checkpoint legality
- durable workflow semantics
- human-in-the-loop approval points
- replay and resumability discipline

### 8.5 NeMo

Absorb:

- eval sink rigor
- observability posture
- profiling and optimizer mindset
- clear experiment accounting

### 8.6 Goose and OpenHands

Absorb:

- coding-agent UX
- packaging discipline
- project-level execution ergonomics

## 9. Phase Order

### Phase 0: Sovereignty Layer

Deliver:

- canonical contract package
- architecture decision record naming those contracts authoritative
- adapter boundary around current substrate modules
- no-op or thin implementations backed by current code

Exit criteria:

- new work can be built against contracts instead of concrete internals

### Phase 1: Runtime Hardening

Deliver:

- legal run state machine
- checkpoint store
- runtime event normalization
- scheduler moved or mirrored into runtime state
- explicit routing/policy/intervention records

Exit criteria:

- all meaningful execution is attributable, resumable, and searchable

### Phase 2: Command Nexus Hardening

Deliver:

- consolidated read models
- honest operator dashboard
- anomaly and failure replay views
- gateway acknowledgement semantics

Exit criteria:

- operator can run the system from Command Nexus without synthetic badges

### Phase 3: Memory and Learning Flywheel

Deliver:

- canonical memory API
- canonical skill store
- trace-to-skill extraction path
- user and agent model records
- routing hints grounded in observed outcomes

Exit criteria:

- DHARMA has a real learning loop, not just memory accumulation

### Phase 4: Evaluation and Observability

Deliver:

- evaluation sink
- scorecard registry
- cost and latency capture
- workflow and skill evaluation history
- experiment comparison tooling

Exit criteria:

- every important behavior can be scored and compared over time

### Phase 5: Assistant and Gateway Productization

Deliver:

- DHARMA-native gateway abstraction
- richer channels
- device/app surface design
- onboarding, status, and doctor flows

Exit criteria:

- DHARMA presents as a real assistant operating system, not only a backend

### Phase 6: Agent World

Deliver:

- identity/reward/reputation/team schema
- embodied visual layer grounded in telemetry

Exit criteria:

- Plane 3 is honest because the underlying data is now honest

## 10. Immediate Backlog

The first concrete work items are:

1. Create `dharma_swarm/contracts/` with the interfaces in this spec.
2. Create runtime-backed implementations that wrap existing substrate modules.
3. Add telemetry schema migrations for routing, policy, intervention, economics, and identity.
4. Define a canonical run lifecycle enum and transition policy.
5. Define a canonical evaluation record format.
6. Define a canonical skill artifact format.
7. Replace direct donor-oriented pathways with contract-oriented adapters.
8. Write the read-model endpoints for Command Nexus from the canonical stores.

## 11. Non-Goals

Do not do the following in this phase:

- merge donor repos into this repo
- make donor internal objects first-class in DHARMA
- widen the dashboard before read models are honest
- build Agent World before telemetry exists
- start with online RL or opaque policy tuning
- let `dgc_cli.py` continue to accumulate cross-cutting responsibility without boundary extraction

## 12. Definition of Done

This phase is complete when:

- DHARMA-owned contracts are the build target
- Command Nexus is honest and operationally useful
- learning, memory, evaluation, and scheduling all terminate in canonical stores
- donor systems are replaceable adapters or reference corpora
- new contributors can understand where truth lives and how capabilities connect

At that point, DHARMA will be structurally future-proof against peer repos because it will own the layer they cannot replace: the sovereign architecture itself.
