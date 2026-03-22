# Ecosystem Forensics Audit

Date: 2026-03-19

Scope:
- Local canonical repo: `/Users/dhyana/dharma_swarm`
- Local comparison repos: `/Users/dhyana/repos/openclaw-orchestration-stack/openclaw`, `/Users/dhyana/zeroclaw`
- Upstream comparison set: OpenClaw, Hermes Agent, Goose, OpenHands, Letta, LangGraph, Google ADK, NVIDIA NeMo Agent Toolkit

## Executive Judgment

DHARMA SWARM is not behind on raw primitives. It is already unusually rich:
- 348 Python modules
- 304 Python test files
- 82 ops scripts
- 139 docs under `docs/`
- FastAPI backend
- Next.js dashboard
- GraphQL and WebSocket surfaces
- MCP server
- SQLite message bus
- multi-layer memory
- persistent agents
- evolution and evaluation surfaces

The main problem is not lack of ideas or lack of subsystems. The main problem is fragmentation, centralization, and missing product-grade interfaces.

The strongest outside systems are winning in narrow, productized lanes:
- OpenClaw: assistant OS, channels, devices, voice, canvas, onboarding, safety defaults
- Hermes: learning loop, skill creation, migration path, remote/serverless backends, trajectory/RL pipeline
- Goose: local dev-agent UX, extensibility, Rust runtime, distro/recipe packaging
- OpenHands: software-engineering agent product and cloud/enterprise packaging
- Letta: stateful memory as first-class product
- LangGraph: durable execution substrate
- ADK: code-first multi-agent + HITL + A2A
- NeMo Agent Toolkit: profiling, observability, eval, optimization, MCP/A2A publishing

The correct strategic goal is not literal repo amalgamation. That would create an unmaintainable chimera. The correct goal is capability supersets behind stable DHARMA-owned interfaces.

## Local Baseline

Canonical repo evidence:
- `README.md` defines `/Users/dhyana/dharma_swarm` as the operator-facing swarm runtime and control plane.
- `scripts/repo_xray.py` reports:
  - 348 Python modules
  - 304 Python test files
  - 82 scripts
  - 139 markdown docs in `docs/`
- Most coupled module: `dharma_swarm/dgc_cli.py` at 6,928 lines with 139 outbound local imports.
- Other major hotspots:
  - `dharma_swarm/thinkodynamic_director.py`
  - `dharma_swarm/evolution.py`
  - `dharma_swarm/tui/app.py`
  - `dharma_swarm/orchestrator.py`
  - `dharma_swarm/swarm.py`
  - `dharma_swarm/agent_runner.py`

Concrete shipped surfaces:
- FastAPI app: `api/main.py`
- Next.js dashboard: `dashboard/package.json`
- Persistent operator router: `dharma_swarm/operator_router.py`
- Resident operator: `dharma_swarm/resident_operator.py`
- Persistent agent loop: `dharma_swarm/persistent_agent.py`
- Async message bus: `dharma_swarm/message_bus.py`
- Strange loop memory: `dharma_swarm/memory.py`
- Conversation memory plane: `dharma_swarm/engine/conversation_memory.py`
- MCP server: `dharma_swarm/mcp_server.py`
- Hermes-inspired build engine: `dharma_swarm/build_engine.py`
- Hermes-inspired cron scheduler: `dharma_swarm/cron_scheduler.py`
- Live orchestrator: `dharma_swarm/orchestrate_live.py`

Structural warning:
- There is fork drift between `/Users/dhyana/dharma_swarm` and `/Users/dhyana/dharma_swarm_autoresearch`.
- The canonical repo has the public remote and current active branch.
- The autoresearch fork is carrying active changes and conceptual material.
- This is already a governance and integration risk before any external work begins.

## What DHARMA SWARM Already Has

Capabilities that are genuinely present:
- Swarm orchestration and task dispatch
- Persistent agents and wake loops
- Agent-to-agent message bus
- Multi-layer persistent memory
- CLI + API + dashboard control plane
- Evaluation and scoring surfaces
- Evolution / Darwin / prompt and policy experimentation
- MCP server exposure
- Ontology / graph / stigmergy / witness concepts
- Operator-grade SSE and WebSocket interfaces

This matters because many peer systems only own one of those layers.

## Where DHARMA SWARM Is Actually Weak

### 1. Product Surface Coherence

Peers ship a legible product.

DHARMA SWARM ships many subsystems, but the user-facing story is split across:
- `dgc_cli.py`
- multiple daemon entry points
- multiple dashboards and reports
- research docs mixed with runtime
- separate operator, swarm, pulse, evolution, and dashboard concepts

The system has more capability than its UX suggests.

### 2. Monolithic Control Surfaces

`dharma_swarm/dgc_cli.py` is too central.

Symptoms:
- 6,928 lines
- highest outbound coupling in the repo
- many different missions mixed into one command surface

This slows iteration, obscures ownership, and makes safe integration harder.

### 3. Gateway / Device / Always-On Assistant Productization

OpenClaw is materially ahead here.

DHARMA SWARM has operator routing, APIs, and daemon loops, but it does not currently present:
- OpenClaw-grade multi-channel inbox breadth
- mobile nodes
- voice wake / talk mode
- canvas surface
- device-local action protocol
- polished onboarding and doctor flows

### 4. Learning Loop and Skillization

Hermes is materially ahead here.

DHARMA SWARM has memory, evaluation, and agent loops, but not a clearly productized closed learning loop with:
- automatic skill extraction from work
- skill self-improvement during use
- cross-session user model as first-class feature
- explicit migration path from adjacent assistant runtimes

### 5. Durable Execution / Checkpointing / HITL

LangGraph and ADK are ahead on disciplined execution semantics.

DHARMA SWARM has many loops, but its workflow durability story is less explicit than peers that foreground:
- resumable checkpoints
- interrupt/review/continue semantics
- tool confirmation as first-class interface
- explicit agent graph definitions and replay

### 6. Profiling / Observability / Optimizer Plane

NeMo Agent Toolkit is ahead here.

DHARMA SWARM has evaluation and traces, but not a clearly unified product surface for:
- workflow profiling
- token/path bottleneck analysis
- prompt optimizer loops
- performance primitives
- benchmark-grade observability at the framework boundary

### 7. Memory Productization

Letta is ahead on memory as a product.

DHARMA SWARM has multiple memory subsystems, but its memory model is not yet as portable or legible as:
- explicit memory blocks
- stable agent memory APIs
- serializable agent artifacts
- clearly separated short-term vs long-term memory contracts

## Comparison Matrix

| Capability | DHARMA SWARM | Strongest peer | Audit note |
|---|---|---|---|
| Swarm orchestration | Strong | LangGraph / ADK | Present, but less explicit as durable graphs |
| Persistent agent identity | Medium-strong | Hermes / Letta | Present, but fragmented across operator, swarm, memory, witness |
| Messaging gateway | Weak-medium | OpenClaw / Hermes | Needs channel layer and delivery productization |
| Device nodes / mobile / voice | Weak | OpenClaw | Major missing lane |
| Learning loop / autonomous skill creation | Weak-medium | Hermes | Important gap |
| Memory substrate | Strong but fragmented | Letta | Needs consolidation and API clarity |
| Eval / observability / optimizer | Medium | NeMo / LangSmith / ADK | Needs unified plane |
| HITL / approvals / tool confirmation | Medium | ADK / LangGraph | Partial, not fully productized |
| MCP exposure | Strong | OpenClaw / Hermes / NeMo | Already present |
| A2A / ACP interoperability | Early | ADK / Hermes / NeMo / Goose | Conceptually present, not first-class |
| Local coding agent UX | Medium | Goose / OpenHands | Lacks polished execution surface |
| Install / onboarding / updates / doctor | Weak-medium | OpenClaw / Hermes | Needs packaging discipline |
| Security model clarity | Medium | OpenClaw / Goose / ZeroClaw | Pieces exist, defaults and docs need tightening |

## What To Import From Each Repo

### OpenClaw

Steal the product lanes, not the code wholesale:
- gateway/channel abstraction
- onboarding wizard
- doctor/update lifecycle
- pairing and allowlist defaults
- multi-device node model
- voice + canvas + companion app concepts
- multi-agent routing around sessions/workspaces

What this would mean in DHARMA terms:
- introduce a `GatewayAdapter` layer
- separate "assistant runtime" from "swarm substrate"
- add `dharma gateway`, `dharma doctor`, `dharma onboard`
- define device-node protocol instead of only API/dashboard clients

### Hermes

This is the highest-value conceptual donor.

Import:
- closed learning loop
- automatic skill creation and improvement
- user modeling
- serverless / remote terminal backends
- OpenClaw migration semantics
- ACP adapter and registry direction
- trajectory generation / compression / RL hooks

In DHARMA terms:
- upgrade `PersistentAgent` from wake loop to compounding loop
- make `build_engine.py` a real bridge, not just an optional side integration
- define a `LearningEngine` with skill extraction and behavior refinement

### Goose

Import:
- local dev-agent ergonomics
- distribution / recipe / distro packaging model
- ACP client direction
- Rust-style runtime discipline as design inspiration

In DHARMA terms:
- split operator UX from research corpus
- ship a sharp local coding mode
- define reusable "workflow recipes" for repeatable tasks

### OpenHands

Import:
- software-engineering agent packaging
- local GUI + CLI parity
- cloud / enterprise boundary discipline
- issue/PR/dev workflow focus

In DHARMA terms:
- create a first-class "engineering lane" instead of burying it in the general swarm
- isolate coding agent workflows behind a stable API
- formalize collaboration, permissions, and multi-user boundaries if needed

### Letta

Import:
- memory blocks
- memory-first agent model
- state serialization discipline
- portable agent state artifacts

In DHARMA terms:
- unify `memory.py`, `conversation_memory.py`, witness/dev/meta layers, and runtime store behind a single `MemoryPlane`
- separate memory schema from agent execution schema

### LangGraph

Import:
- durable execution semantics
- resumable checkpoint model
- explicit graph/state design
- clearer HITL interrupt model

In DHARMA terms:
- make long-lived workflows replayable and inspectable
- reduce hidden loop behavior
- formalize supervisor checkpoints for risky actions

### Google ADK

Import:
- code-first agent definitions
- tool confirmation flow
- A2A integration
- development UI pattern

In DHARMA terms:
- create a simpler public agent-definition API
- formalize approval gates as a product feature, not just policy text

### NVIDIA NeMo Agent Toolkit

Import:
- profiler
- workflow observability
- evaluation harness
- prompt / hyperparameter optimizer
- workflow publishing as MCP server
- A2A and performance primitives

In DHARMA terms:
- add an `EvaluationSink` and `TraceProfiler`
- make every major loop measurable
- make optimization a bounded subsystem instead of scattered heuristics

## The Future-Proofing Strategy

Do not future-proof by copying all competitor code.

Future-proof by owning interfaces.

The minimum durable interface set is:
- `AgentRuntime`
- `SessionStore`
- `MemoryPlane`
- `ToolBus`
- `GatewayAdapter`
- `InteropAdapter`
- `EvaluationSink`
- `SandboxProvider`
- `SkillStore`
- `CheckpointStore`

If these interfaces are stable, DHARMA SWARM can absorb capabilities from:
- OpenClaw-style gateways
- Hermes-style learning loops
- Letta-style memory blocks
- LangGraph-style checkpoint graphs
- ADK-style confirmations and A2A
- NeMo-style observability and optimization

without turning into an unmaintainable fork graveyard.

## Concrete Risks Inside DHARMA SWARM

1. Canonicality drift
- Multiple local DHARMA trees are active.
- This will break integration sequencing and truth surfaces.

2. Control-plane centralization
- `dgc_cli.py` is too large and too coupled.

3. Runtime/research blending
- Runtime, dashboard, experiments, and strategic prose live side by side.
- This is good for ideation and bad for product clarity.

4. Partial interop
- MCP is real.
- A2A/ACP is mostly conceptual or partial.

5. Product gap
- The external systems often win by being narrower and more polished, not deeper.

## Recommended Program

### Phase 0: Canonicalize

- Freeze `/Users/dhyana/dharma_swarm` as the only canonical runtime repo.
- Reduce `dharma_swarm_autoresearch` to research/artifact status or merge it.
- Generate and version a canonical subsystem map.

### Phase 1: Decompose the Monolith

- Split `dgc_cli.py` into command modules.
- Split operator, swarm, engineering, and research lanes.
- Define stable interface modules for gateway, memory, eval, interop.

### Phase 2: Build the Memory Plane

- Merge strange-loop memory, conversation memory, runtime facts, and witness/dev/meta into one schema contract.
- Add explicit short-term, long-term, persona, and user-model blocks.
- Make agent state exportable.

### Phase 3: Add Real Interop

- Keep MCP.
- Add first-class A2A/ACP adapter support.
- Define import/migration paths for OpenClaw and Hermes.

### Phase 4: Add the Assistant Surface

- Add channel gateway abstraction.
- Add pairing, allowlists, onboarding, doctor, and update flows.
- Add device/node protocol as separate from dashboard/API.

### Phase 5: Add the Learning Loop

- Promote skill extraction to a first-class subsystem.
- Add user-model and agent self-improvement loop.
- Make completed work improve future execution.

### Phase 6: Add the Eval Plane

- Add workflow profiling, traces, replay, and optimizer surfaces.
- Standardize benchmark tasks and eval artifacts.
- Expose this in dashboard and CLI.

## Immediate High-Leverage Moves

These are the first moves that actually compound:

1. Canonicalize repo truth.
2. Break up `dgc_cli.py`.
3. Define the `MemoryPlane` interface.
4. Define a `GatewayAdapter` interface.
5. Turn `PersistentAgent` + `build_engine.py` into a real Hermes-style learning loop.
6. Make eval, replay, and profiling first-class.

## Bottom Line

DHARMA SWARM does not need to become those repos.

It needs to become the system that can host all of their strongest ideas behind cleaner interfaces than they have.

Right now it already has many of the primitives. The gap is:
- productization
- interface discipline
- learning-loop productization
- interoperable gateways
- durable eval/observability

If those are fixed, DHARMA SWARM can become a superset rather than a derivative.
