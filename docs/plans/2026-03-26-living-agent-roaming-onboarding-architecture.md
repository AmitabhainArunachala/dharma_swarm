# Living Agent And Roaming Onboarding Architecture

Date: 2026-03-26
Status: Canonical design note for cross-harness agent embodiment
Scope: OpenClaw, Claude Code, Codex, Hermes, VPS workers, remote/mobile agents

## 1. Why This Exists

`dharma_swarm` already has most of the substrate needed for a real multi-agent organism:

- runtime execution
- agent registry
- A2A cards
- telemetry identities
- message bus
- operator bridge
- artifact storage
- memory lattice
- traces and lineage

What it does not yet have is one canonical answer to this question:

`What does it mean for an agent from any harness or device to truly belong to the swarm?`

Right now, the same "agent" can appear in multiple incompatible forms:

- as an OpenClaw config entry
- as an OpenClaw workspace and session log
- as a `.dharma/agents/*` identity directory
- as a `.dharma/a2a/cards/*.json` capability card
- as a telemetry record in `runtime.db`

Those are related, but they are not yet one coherent identity plane.

This document defines that identity plane.

## 2. Current Reality

The current Kimi evidence shows the split clearly.

### 2.1 What exists

- OpenClaw config has named Kimi agents such as `nim_kimi` and `ollama_kimi` in `~/.openclaw/openclaw.json`.
- A `.dharma` agent identity exists at `~/.dharma/agents/kimi/identity.json`.
- A `.dharma` A2A card exists at `~/.dharma/a2a/cards/kimi.json`.
- A telemetry-plane record exists for `kimi-cartographer` in `~/.dharma/state/runtime.db`.

### 2.2 What is wrong

The Kimi records are not canonical.

Example:

- `~/.dharma/agents/kimi/identity.json` says:
  - model: `moonshotai/kimi-k2.5`
  - provider: `openrouter`
  - role: `macro-oracle`

- `~/.dharma/a2a/cards/kimi.json` says:
  - model: `nvidia/nemotron-nano-9b-v2:free`
  - role: `analyst`
  - endpoint: `local://`

That means the system currently has evidence of registration, but not proof of canonical onboarding.

The correct conclusion is:

`Today, "registered" means "some agent metadata was created somewhere."`

It does not yet mean:

`This is one living swarm entity with stable identity, presence, dock, memory, routing, and provenance.`

## 3. Core Principle

Python files are not where living agents should "be".

Python files define:

- laws
- contracts
- protocols
- storage adapters
- evaluators
- routing logic
- embodiment machinery

Living agents should exist as first-class runtime entities.

Code is the substrate.
Agents are the inhabitants.

## 4. Canonical Object: LivingAgent

The missing first-class object is `LivingAgent`.

This object should exist above raw harness-specific sessions and above bare A2A cards.

### 4.1 Required fields

- `agent_uid`
  - globally unique, stable swarm identity
- `callsign`
  - human-meaningful name such as `kimi`, `hermes`, `tara-kimi`
- `serial`
  - ordered or generated registration number
- `department`
  - `research`, `compiler_audit`, `coordination`, `quant`, `build`, `witness_telos`
- `squad_id`
  - local team or mission cluster
- `role`
  - specialization such as `researcher`, `analyst`, `scout`, `coder`, `auditor`
- `harness`
  - `openclaw`, `claude_code`, `codex`, `hermes`, `vps_worker`, `api_remote`
- `endpoint`
  - where the agent can actually be reached
- `model_identity`
  - provider, model, routing hints, tool envelope
- `autonomy_policy`
  - allowed actions, approval boundaries, cost ceilings
- `status`
  - `starting`, `idle`, `busy`, `offline`, `degraded`, `quarantined`
- `home_dock`
  - persistent identity directory
- `workspace_policy`
  - how workspaces are leased per task
- `memory_namespace`
  - the portion of shared memory the agent can write to and retrieve from
- `capability_card_ref`
  - pointer to its A2A card
- `reward_ledger_ref`
  - telemetry reward and reputation linkage
- `trace_identity`
  - canonical identifier used in traces and lineage
- `created_at`
- `updated_at`
- `last_seen_at`
- `registration_source`
  - who or what onboarded it

### 4.2 What this fixes

This separates:

- the agent's identity
- the agent's current embodiment
- the agent's temporary task sessions

So the same living agent can move between:

- phone OpenClaw
- laptop Claude Code
- VPS worker
- Hermes gateway
- Codex session

without becoming a different being every time.

## 5. Home Dock vs Workspace

Every agent should have both:

- a `home dock`
- leased `workspaces`

### 5.1 Home dock

The home dock is persistent.

It stores:

- identity
- roster membership
- harness bindings
- local notes
- prompt lineage
- runtime field manifest
- fitness history
- task log
- local preferences
- onboarding metadata

Suggested path:

`~/.dharma/agents/{agent_uid}/`

The current `~/.dharma/agents/{name}/` layout is already the seed of this.

### 5.2 Workspace lease

The workspace is not the agent's identity.

It is a temporary project room leased per task or per mission.

It stores:

- working files
- diffs
- generated artifacts
- intermediate outputs
- task-local scratch state

Suggested path:

`~/.dharma/workspace/sessions/{session_id}/`

This keeps the organism coherent:

- one shared world
- one truth substrate
- one artifact system
- one ontology
- many local desks
- many temporary workrooms

## 6. Where Things Live

Research and agent activity should live in different layers for different reasons.

### 6.1 Filesystem artifacts

Purpose:
- raw documents
- normalized documents
- reports
- grades
- patches
- local outputs

Current seam:
- `artifact_store.py`

### 6.2 Runtime truth database

Purpose:
- identity records
- task runs
- reward ledger
- workflow scores
- policy decisions
- economic outcomes

Current seams:
- `telemetry_plane.py`
- `runtime_state.py`
- `evaluation_registry.py`

### 6.3 Semantic and retrieval memory

Purpose:
- durable promoted facts
- retrieval across sessions
- concept recall
- structured semantic persistence

Current seam:
- `memory_lattice.py`

### 6.4 Agent dock

Purpose:
- persistent identity embodiment
- local continuity
- dock-level logs and manifests

Current seam:
- `agent_registry.py`

## 7. How This Fits The Four-Graph System

This architecture only makes sense if it is integrated into the four-graph ontology.

### 7.1 Code graph

Represents:

- harness implementations
- adapters
- onboarding scripts
- runtime modules
- tool surfaces

Question answered:

`How is this agent technically embodied?`

### 7.2 Semantic graph

Represents:

- roles
- capabilities
- concepts
- departments
- traditions such as cybernetics
- promoted claims and reusable knowledge

Question answered:

`What kind of mind is this agent and what distinctions can it carry?`

### 7.3 Runtime graph

Represents:

- heartbeats
- tasks
- claims
- traces
- lineage
- routing decisions
- outputs
- failures

Question answered:

`What is this agent actually doing right now and what has it done?`

### 7.4 Telos graph

Represents:

- identity
- policy constraints
- dharmic gates
- higher objectives
- mission alignment

Question answered:

`What should this agent serve, and what should it never become?`

### 7.5 Bridge rule

An onboarded agent is real only when it has a presence in all four graphs:

- code graph: embodiment
- semantic graph: meaning and role
- runtime graph: activity
- telos graph: orientation and constraint

Without all four, it is only partially real.

## 8. Department Model

Agents should not be a flat bag.

They should belong to cybernetically meaningful departments.

### 8.1 Canonical departments

- `witness_telos`
  - identity, kernel, gates, witness, coherence
- `research`
  - sensing, research, distillation, synthesis
- `compiler_audit`
  - grading, causal credit, policy compilation, promotion
- `coordination`
  - routing, squad assembly, assignment, load balancing
- `build`
  - code, tests, deployment, repair
- `quant`
  - market research, features, backtests, risk

### 8.2 Why departments matter

Department is not cosmetic metadata.

Department is how the organism expresses recursive cybernetic structure:

- S5: witness_telos
- S4: research
- S3: compiler_audit
- S2: coordination
- S1: build, quant, and other execution chambers

## 9. Canonical Onboarding Handshake

This is the missing mechanism.

Any harness should be able to present an onboarding payload to the swarm.

### 9.1 Inputs

The external agent provides:

- harness type
- proposed callsign
- provider and model
- endpoint or callback channel
- capability declaration
- workspace root
- authentication mode
- optional department preference
- optional tags

### 9.2 Canonical onboarding flow

1. `Handshake received`
   - from OpenClaw, Claude Code, Hermes, Codex, VPS worker, or other harness

2. `LivingAgent created or rebound`
   - assign `agent_uid`
   - either create new identity or bind a new harness embodiment to an existing one

3. `Home dock created`
   - canonical directory under `~/.dharma/agents/{agent_uid}/`

4. `A2A card materialized`
   - not as the identity itself, but as its discovery advertisement

5. `Telemetry identity registered`
   - write into `agent_identity` and `team_roster`

6. `Memory namespace assigned`
   - define retrieval and promotion boundaries

7. `Autonomy policy attached`
   - tools, cost ceilings, approval requirements, allowed domains

8. `Heartbeat channel established`
   - the swarm can tell if the agent is really alive

9. `Task eligibility computed`
   - route the agent only to work it should actually do

10. `Departmental placement finalized`
   - agent enters a department and squad

### 9.3 Output

The result of onboarding is not just a config entry.

It is a fully bound swarm entity with:

- stable identity
- capability advertisement
- reachability
- dock
- memory
- routing
- telemetry
- lineage

## 10. Constant Onboarding And Curation

Yes, this should become an always-on swarm function.

### 10.1 Onboarding loop

The organism should be able to continuously absorb new agents from:

- phone OpenClaw instances
- desktop OpenClaw instances
- Claude Code sessions
- Codex sessions
- Hermes gateways
- VPS workers
- external APIs

### 10.2 Curation loop

Onboarding is not enough.

There must also be curation:

- deduplicate near-identical agents
- merge duplicate identities
- quarantine stale or broken agents
- downgrade agents with poor trust or bad heartbeats
- retire dead harness bindings
- promote reliable agents to trusted roles

### 10.3 Roster outputs

The curation system should maintain:

- full roster
- active roster
- trusted roster
- dormant roster
- quarantined roster
- role availability matrix

## 11. What "Registering Kimi" Should Mean

After this architecture lands, registering Kimi from a phone should mean:

- the phone harness presents itself
- swarm recognizes whether this is a new being or an embodiment of an existing `kimi`
- swarm binds the harness to `agent_uid`
- swarm creates or updates the home dock
- swarm updates A2A discovery
- swarm updates telemetry presence
- swarm sets current embodiment to `mobile_openclaw`
- swarm can now route tasks to that agent if its heartbeat is good

That is a real registration.

Everything less than that is partial.

## 12. Why The Existing RAG, Vector, And Memory Systems Matter

They are not side systems.

They are the organism's cognitive commons.

Once living agents are properly onboarded, they should be able to:

- retrieve prior research
- write promoted facts
- inherit semantic context
- contribute new claims
- access shared strategic memory
- ground their actions in organism-wide knowledge

The current problem is not that those systems were pointless.

The current problem is that the promotion and onboarding loops are incomplete.

The nervous system exists.
It has not been fully populated and disciplined yet.

## 13. Recommended Next Implementation Order

1. Introduce a canonical `LivingAgent` model.
2. Add a cross-harness onboarding API and registry path.
3. Reconcile A2A card generation with agent dock identity.
4. Add harness-binding records so one agent can have multiple embodiments.
5. Add heartbeat and liveness tracking for remote/mobile agents.
6. Add roster curation and deduplication rules.
7. Route work through operator bridge and team/department policies.
8. Promote outputs into traces, lineage, memory, and telemetry by default.

## 14. Non-Goals

This does not mean:

- every agent gets its own isolated universe
- every harness invents its own ontology
- A2A cards replace identity
- vector memory replaces structured truth
- remote agents are trusted automatically

The swarm remains one organism with one truth substrate.

## 15. Bottom Line

The right model is:

- shared world
- shared ontology
- shared truth substrate
- shared artifact system
- per-agent home docks
- per-task leased workspaces
- cross-harness embodiments
- one canonical identity plane

That is how phone Kimi, Hermes, Claude Code on a VPS, OpenClaw, and future agents can all plug into the same living system without becoming a mess.
