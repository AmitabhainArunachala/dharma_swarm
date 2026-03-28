# Roaming Control Plane Spec

Date: 2026-03-26

## Purpose

This document explains the current roaming-agent architecture in plain language,
why the git mailbox exists, what phase the system is in now, and what the next
stable infrastructure step should be.

The goal is not to build a second swarm. The goal is to let many different
agent embodiments plug into one `dharma_swarm` organism:

- Kimi Claw on a phone
- OpenClaw on a remote host
- Claude Code on a VPS
- Codex locally
- Hermes or other harnesses later

All of them should share:

- one identity plane
- one task-routing plane
- one runtime truth model
- one semantic memory stack
- one telos/governance layer

## Plain-Language Model

`dharma_swarm` has three different layers that should not be confused.

1. The substrate
   This is the Python code. It defines the laws, queues, memory contracts,
   registries, traces, grading, and orchestration surfaces.

2. The living agents
   These are runtime citizens. Each should have:
   - a stable swarm identity
   - a dock
   - a department
   - a capability profile
   - a task history
   - a memory namespace
   - a heartbeat
   - an autonomy policy

3. The transport/control plane
   This is how far-away embodiments talk to the shared organism.

The git mailbox is part of layer 3. It is transport, not ontology.

## Current Phase

Current phase: `Federated bootstrap`

What exists now:

- roaming onboarding
- mailbox transport
- remote poller
- bridge from real `OperatorBridge` tasks into the mailbox
- local daemon that dispatches and collects mailbox work

This means a remote agent can now:

1. be onboarded into swarm identity
2. receive real work from the canonical bridge queue
3. respond asynchronously
4. have that response re-imported into the real runtime

This is enough to do useful real work.

This is not yet enough to call the system a full distributed control plane.

## Why The Git Mailbox Exists

The mailbox exists because the remote agent and the local swarm do not share:

- the same filesystem
- the same process space
- the same database
- the same network trust boundary

Git gave an immediate common transport that already existed on both sides.

Advantages:

- works across phone/cloud/local
- no new server required
- easy to audit
- failure-tolerant
- async-friendly

Limitations:

- not low latency
- weak presence/heartbeat model
- awkward for high task volume
- branch conflicts eventually become painful
- not a good final control plane

Conclusion:

The mailbox is the correct bootstrap transport.
It is not the final nervous system.

## What Was Built In This Phase

### 1. Onboarding

Module:
- `dharma_swarm/roaming_onboarding.py`

Purpose:
- create a stable swarm record for a roaming agent
- persist dock/card/receipt metadata

### 2. Mailbox transport

Module:
- `dharma_swarm/roaming_mailbox.py`

Purpose:
- store roaming tasks and responses as git-syncable files

### 3. Remote poller

Module:
- `dharma_swarm/roaming_poller.py`

Purpose:
- let a remote agent host continuously:
  - pull branch changes
  - claim mailbox work
  - run a responder command
  - push responses back

### 4. Real-task adapter

Module:
- `dharma_swarm/roaming_operator_bridge.py`

Purpose:
- export real `OperatorBridge` tasks into mailbox transport
- import mailbox responses back into the canonical bridge queue

### 5. Local dispatcher/collector daemon

Module:
- `dharma_swarm/roaming_dispatch_daemon.py`

Purpose:
- continuously:
  - sync mailbox view
  - collect completed roaming responses
  - dispatch new real bridge work to roaming agents

## What Phase We Should Enter Next

Next phase: `Hybrid control plane`

Do not jump directly to "everything runs in the cloud now."

The right next step is:

- keep the git mailbox as fallback transport
- add one small VPS control plane

This gives the system two channels:

1. Fast lane
   HTTP/A2A queue, heartbeats, presence, live task routing

2. Slow lane
   Git mailbox fallback for mobile, NAT, or low-trust environments

That is the right architecture for the next stage.

## Recommended VPS Control Plane

One small VPS should host:

### 1. Agent registry service

Responsibilities:
- canonical `LivingAgent` record
- harness type
- endpoint or transport mode
- department
- capabilities
- trust/autonomy policy
- heartbeat state

### 2. Task router

Responsibilities:
- accept new work
- match tasks to eligible agents
- publish assignments
- handle retries and stale claims

### 3. Heartbeat/presence service

Responsibilities:
- mark roaming agents online/offline
- track last-seen
- detect stale workers

### 4. Artifact metadata service

Responsibilities:
- store artifact references
- relate outputs to tasks and agents
- support lineage and trace lookup

### 5. A2A/HTTP ingress

Responsibilities:
- direct machine-to-machine agent communication
- future non-git transport
- standardized external agent registration

### 6. Audit and kill-switch controls

Responsibilities:
- pause an agent
- revoke an endpoint
- cap task scope
- freeze unsafe routes

## Canonical Long-Term Shape

Long term, the system should look like this:

### Shared control plane

- central registry
- central queue/router
- central truth DB
- central telemetry
- central semantic promotion services

### Roaming workers

- Kimi phone worker
- OpenClaw worker
- Claude Code worker
- Codex worker
- Hermes worker

### Shared semantics

Research and cognition should not stay trapped in prompts or transient files.
Durable outputs should move upward through these levels:

1. raw artifact
2. graded report
3. promoted fact
4. semantic graph node/edge
5. compiled policy/routing/workflow effect

That is how roaming work becomes organismal knowledge.

## Why Not "Everything In One Cloud Server" Immediately

Because that would solve the wrong problem first.

The current bottleneck is not raw hosting. The bottleneck is:

- identity coherence across harnesses
- clean task transport
- response import
- routing discipline
- observability

The git mailbox plus hybrid control-plane step solves those in the right order.

Moving everything blindly to one server now would:

- increase operational complexity
- collapse harness diversity too early
- make experimentation harder
- not actually solve identity or routing by itself

## Phase Map

### Phase 0: Local organism

Status: already existed

- local swarm runtime
- internal agents
- internal memory/eval/evolution loops

### Phase 1: Federated bootstrap

Status: now landed

- roaming onboarding
- git mailbox
- remote poller
- bridge queue adapter
- local dispatch daemon

### Phase 2: Hybrid control plane

Status: next

- small VPS service
- heartbeats
- central registry
- live routing
- mailbox fallback retained

### Phase 3: Native multi-harness swarm

Status: later

- A2A-first endpoints
- department-level orchestration
- capability routing
- direct live task dispatch

### Phase 4: Semantic organism

Status: later

- research promotion into semantic memory
- compiler effects on routing/workflows
- stronger department autonomy
- deeper self-modification

## Operational Recommendation

Do this next:

1. Run the local roaming dispatch daemon from a clean repo checkout or worktree.
2. Run the remote Kimi poller in loop mode.
3. Feed only bounded real tasks first.
4. Add the VPS control plane next, not after months of more duct tape.

## First Real Production Use

Best first use:

- research department overflow
- bounded quant/research memo tasks
- synthesis or literature tasks
- coding subtasks with explicit output contracts

Avoid first:

- ungated execution
- high-frequency dispatch
- fully autonomous trading
- anything that assumes low-latency RPC

## Success Criteria For The Next Phase

The hybrid control plane phase is successful when:

- agents can register from multiple harnesses with one stable identity
- presence is visible without git polling alone
- tasks can be routed live over HTTP/A2A
- mailbox remains available as fallback
- outputs import cleanly into the same runtime truth model
- no second swarm/runtime is introduced

## Bottom Line

The current system is not fake. It is past the demo stage.

But it is still in bootstrap transport mode.

The correct next move is:

- keep the mailbox
- add a small VPS control plane
- preserve one canonical runtime
- let many embodiments plug into it

That is how `dharma_swarm` becomes one organism with many bodies instead of a pile of disconnected agents.
