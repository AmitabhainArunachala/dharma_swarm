# DHARMA Current State Deep Dive

Date: 2026-03-19
Scope: forensic review of the canonical `/Users/dhyana/dharma_swarm` repo before the next build phase
Method: local code inspection, repo_xray output, test inventory, and prior ecosystem comparison against OpenClaw, Hermes, Letta, LangGraph, ADK, NeMo, Goose, and OpenHands

## Executive Judgment

DHARMA SWARM is not an empty shell. It already contains a serious runtime substrate, a large amount of orchestration logic, a real API/dashboard surface, multi-layer memory, MCP exposure, evolutionary scoring, and an emerging resident-operator model.

The problem is not missing ambition or missing primitives.

The problem is that the repo still behaves like a federation of strong subsystems rather than one productized operating system with one canonical contract layer.

In direct terms:

- The runtime substrate is stronger than the UX around it.
- The memory and evaluation substrate are stronger than the learning-loop product.
- The API surface is broader than its read-model discipline.
- The codebase has many power features, but too few canonical interfaces.
- Some modules already encode donor behavior from Hermes or older internal systems, but in a way that risks architecture drift.

The repo is much closer to "proto sovereign agent OS" than to "toy swarm". The next phase should not add another vision layer. It should harden and unify what is already here.

## Canonical Repo Reality

The canonical working repo is `/Users/dhyana/dharma_swarm`.

Observed repo_xray baseline:

- Python modules: 348
- Python tests: 304
- Shell scripts: 82
- Markdown docs: 139
- Largest file: `dharma_swarm/dgc_cli.py` at 6928 lines
- Highest outbound coupling: `dgc_cli`, `swarm`, `agent_runner`, `evolution`, `orchestrate_live`
- Most imported local module: `dharma_swarm.models`

This is already a large system. The next phase is not "start building". It is "impose a sovereign shape on a large existing codebase."

## What Is Already Real

### 1. Canonical runtime spine

The strongest local foundation is the SQLite-backed runtime spine:

- `dharma_swarm/runtime_state.py`
- `dharma_swarm/operator_bridge.py`
- `dharma_swarm/operator_views.py`
- `dharma_swarm/message_bus.py`
- `dharma_swarm/session_ledger.py`

This stack already gives DHARMA:

- durable session state
- task claims
- delegation runs
- workspace leases
- artifact records and lineage links
- memory facts and edges
- context bundle persistence
- operator actions
- searchable session events
- bridge queue state mirrored into runtime

This is more architecturally serious than what many agent repos ship.

### 2. Memory plane and replay substrate

`dharma_swarm/engine/event_memory.py` already defines a meaningful memory plane with:

- event log
- source documents and chunks
- retrieval log
- conversation turns
- idea shards
- idea links
- idea uptake

This is an unusually strong base for replay, retrieval analysis, and learning loops. It means DHARMA does not need to borrow memory architecture wholesale from Letta or Hermes. It needs to finish and discipline its own.

### 3. Operator bridge and audit

The operator bridge is not just a queue. It already models:

- enqueue
- claim
- claim acknowledgement
- heartbeats
- partial artifacts
- response emission
- delivery acknowledgement
- stale recovery
- lifecycle publication
- ledger mirroring
- runtime mirroring

This is a real control-plane seam and should become the backbone of Command Nexus.

### 4. API and dashboard surfaces

The repo already exposes a large API surface:

- FastAPI app
- multiple routers
- WebSocket feeds
- GraphQL-like ontology endpoints
- dashboard pages for agents, ecosystem, modules, stigmergy, and synthesizer flows

This means DHARMA is not blocked on basic product surfacing. It is blocked on consolidation and truth discipline.

### 5. Scheduling, autonomy, and persistent presence

DHARMA already has:

- `persistent_agent.py` for wake-loop style conductors
- `cron_scheduler.py` for scheduled task execution
- resident operator logic
- orchestration and swarm layers

These are not vapor. They are working foundations that can absorb some of Hermes's strengths without adopting Hermes's internals.

### 6. Test coverage around key seams

The substrate is not untested. There are focused tests for:

- runtime state
- operator bridge
- operator views
- event memory
- cron scheduler
- MCP server
- persistent agent
- build engine
- workspace manager
- evaluation registry
- context compiler

That matters. It means the next phase can tighten contracts instead of rebuilding from scratch.

## What Is Only Partially Real

### 1. Learning loop

The repo has components that smell like a learning flywheel, but not one coherent productized loop that does all of the following in a first-class way:

- extract reusable skills from traces
- settle them into a canonical skill store
- track skill performance over time
- adapt routing based on proven skill outcomes
- update an explicit user model and agent model

This is where Hermes currently has the clearest donor advantage.

### 2. Evaluation and observability plane

DHARMA has evaluation machinery and archive/fitness logic, but the repo does not yet present one canonical evaluation sink that unifies:

- run trace
- artifact outcome
- scorecard
- judge/eval result
- cost
- latency
- routing decision
- operator intervention effect

This is where NeMo and ADK-style discipline is still ahead conceptually.

### 3. Memory productization

The memory substrate is richer than the exposed memory product.

Current state:

- several memory forms exist
- retrieval is present
- facts, turns, shards, uptake, and provenance exist

Missing:

- one canonical MemoryPlane API
- memory lifecycle states that every subsystem respects
- first-class promotion and decay policy
- user-model memory
- skill memory
- environment memory
- explicit memory scoring and trust policy

This is where Letta's posture is a useful donor reference.

### 4. Durable execution semantics

DHARMA has sessions, claims, runs, leases, and ledgers, but it is not yet as explicit as LangGraph/ADK on:

- resumability contracts
- human approval checkpoints
- replay boundaries
- state-machine legality
- durable workflow identity across interruptions

The substrate is close. The discipline is not complete.

### 5. Gateway and device surface

Compared with OpenClaw, DHARMA lacks a mature assistant-facing gateway/device layer:

- channels are not yet the product center of gravity
- no OpenClaw-grade device/app node fabric
- no comparable onboarding, doctor, or user-facing assistant shell
- no equivalent voice/mobile surface

This is not a substrate gap. It is a product gap.

## What Is Missing or Risky

### 1. Too many "master" narratives

The repo contains several documents with master-spec energy, but they do not all define the same build doctrine.

Observed pattern:

- `SWARMLENS_MASTER_SPEC.md` is ambitious but product/venture heavy
- `docs/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md` is closer to the right operational doctrine
- `specs/KERNEL_CORE_SPEC.md` defines philosophical/telos invariants
- `docs/README.md` and merge docs introduce additional framing layers

This creates architectural drift risk. The new build phase needs one canonical operational spec and one canonical build prompt.

### 2. Company telemetry schema is still missing

The three-plane architecture doc is correct: the next missing layer is not UI. It is company telemetry.

Still absent as first-class runtime records:

- agent identity ledger
- reward ledger
- reputation ledger
- team roster
- revenue events
- cost events
- external outcomes
- customer feedback
- workflow scores
- routing decisions
- policy decisions
- intervention outcomes

Without these, Fitness Engine and Agent World will stay partially synthetic.

### 3. `dgc_cli.py` is oversized and over-central

The CLI is a major coupling hotspot. That is manageable in the short term, but it increases the chance that new features bypass clean interface boundaries and wire themselves directly into the monolith.

### 4. Build engine is not sovereign yet

`dharma_swarm/build_engine.py` is useful as a donor-inspired experiment, but it is not a canonical sovereign build path yet.

Problems:

- it explicitly couples to `external/hermes-agent`
- it requires external API keys for useful execution
- it contains rollback logic that uses destructive git patterns
- it encodes a donor architecture instead of a DHARMA-owned execution contract

This module should be treated as a prototype, not the sovereign build kernel.

### 5. Scheduler persistence is weaker than runtime persistence

`cron_scheduler.py` uses file-backed job storage under `~/.dharma/cron/jobs.json`.

That is serviceable, but it is weaker than the runtime-state spine. Scheduled work should eventually become a first-class runtime record with the same audit semantics as claims, runs, and operator actions.

### 6. MCP surface is currently narrow

`mcp_server.py` exposes DHARMA through a useful but minimal tool layer. It does not yet expose the full power of the runtime, operator plane, memory plane, evaluation plane, or workflow semantics.

### 7. Dirty worktree and legacy import history

The repo is active and dirty. Merge docs show a history of large imports and consolidation work. That means the next phase must be especially disciplined about not widening drift while trying to unify architecture.

## Capability Position Relative To The Ecosystem

If we compare the real repo rather than the marketing story:

### DHARMA already matches or exceeds peers on

- internal orchestration primitives
- runtime-state richness
- memory substrate richness
- operator-bridge semantics
- local auditability
- combinatorial feature density
- willingness to encode economics, telos, and evolution in one system

### DHARMA is behind peers on

- clean product packaging
- assistant/gateway polish
- durable workflow discipline
- memory productization
- learning-loop coherence
- unified eval/observability surface
- clear interface ownership

### DHARMA's strategic opportunity

Because DHARMA already has unusually rich internal primitives, it does not need to chase any one peer repo.

It should instead become the sovereign superset:

- OpenClaw contributes gateway and assistant-product ideas
- Hermes contributes learning loop, skills, remote execution, and migration semantics
- Letta contributes memory discipline
- LangGraph and ADK contribute checkpoint/HITL discipline
- NeMo contributes eval and observability discipline
- Goose and OpenHands contribute coding-agent UX and packaging discipline

## Build Doctrine Implication

The next phase should not be "integrate all these repos."

It should be:

1. Make DHARMA's runtime interfaces canonical.
2. Move donor capabilities behind those interfaces.
3. Promote the runtime spine into the source of truth for all planes.
4. Finish the missing company telemetry layer.
5. Productize one serious control plane before widening the surface area again.

## Hard Conclusions

1. DHARMA already has the bones of a sovereign agent operating system.
2. The repo's biggest weakness is not capability poverty. It is interface poverty.
3. The next winning move is not more features. It is canonicalization.
4. The three-plane architecture doc is directionally correct, but it needs to be tightened into a build spec.
5. Hermes, OpenClaw, Letta, LangGraph, ADK, and NeMo should be treated as donor corpora, not runtime dependencies.

## Recommended Immediate Build Targets

Immediate highest-leverage work:

- define the sovereign interface layer
- move scheduler/gateway/eval/memory semantics behind it
- add the missing telemetry records
- harden Command Nexus first
- convert experimental donor-inspired modules into DHARMA-native contract implementations

That is the shortest path from "large promising system" to "coherent sovereign system."
