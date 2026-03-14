# GSTACK SYSTEM UPGRADE AUDIT
## Date
2026-03-14

## Scope
Review `garrytan/gstack` and extract the highest-leverage patterns for the current system:

- `DGC`
- `OpenClaw`
- `KaizenOps`
- `Dharma Swarm`

Repo reviewed:
- local clone: `/Users/dhyana/repos/gstack`
- head: `f7b9532`

---

## What gstack actually is

`gstack` is not a full agent runtime.

It is a workflow operating system for Claude Code built from two things:

1. A small set of highly opinionated cognitive modes:
   - founder review
   - engineering review
   - paranoid PR review
   - release shipping
   - QA
   - retrospectives

2. A fast local browser binary with persistent state.

This is why the repo is so small and coherent:
- skill prompts in directories like `plan-ceo-review/`, `plan-eng-review/`, `review/`, `ship/`, `qa/`
- one compiled browser tool under `browse/`
- one `setup` script to build and register everything

See:
- `/Users/dhyana/repos/gstack/README.md`
- `/Users/dhyana/repos/gstack/SKILL.md`
- `/Users/dhyana/repos/gstack/BROWSER.md`
- `/Users/dhyana/repos/gstack/setup`

---

## What is genuinely strong

### 1. Explicit cognitive gears

This is the strongest idea in the repo.

`gstack` does not treat the coding agent like one mushy all-purpose assistant.
It forces explicit mode switches:

- `plan-ceo-review` for ambition and product taste
- `plan-eng-review` for architecture and test rigor
- `review` for bug/risk hunting
- `ship` for release mechanics
- `qa` and `browse` for interaction testing

This is better than generic prompting because it:

- reduces mode confusion
- improves repeatability
- makes teams legible
- encodes taste and workflow policy directly into the tool surface

### 2. Browser as a native operational tool

The browser is not exposed through a heavyweight protocol.
It is a compiled CLI talking to a persistent local HTTP daemon.

From `BROWSER.md`, the key architecture is:

```text
Claude/Coder -> CLI binary -> local server -> Playwright -> Chromium
```

That gives:

- low call overhead
- persistent cookies and tabs
- fast repeated actions
- per-workspace browser isolation

This is materially better than brittle slow browser-MCP patterns for repeated QA loops.

### 3. One-command install and distribution

`gstack` wins on packaging.

One repo:
- build browser
- install dependencies
- register skills
- symlink subskills

That is a major reason it feels usable instead of clever.

### 4. Workflow compression

`gstack` captures a very useful shape:

```text
rethink -> engineer -> implement -> review -> ship -> QA -> retro
```

That sequence is real. It maps to how strong individual engineers actually work.

### 5. Conductor-aware isolation

The browser instance derives its port from `CONDUCTOR_PORT`, which is a simple but excellent idea for multi-workspace parallelism.

This matters because your current system already wants many simultaneous workspaces.

---

## What is only moderately strong

### 1. The prompts are good, but they are still prompts

The skills are useful because they force posture and checklist discipline.
But most of the repo's intelligence is still encoded in Markdown behavior instructions, not typed contracts or real system state.

That means `gstack` is strongest when:
- one user
- one repo
- one engineering flow
- one coding assistant

It is weaker as:
- an auditable multi-agent operating system
- a true control plane
- a commercially governed agent platform

### 2. Shipping assumptions are narrow

The `/ship` flow assumes a very specific GitHub-style feature branch workflow and is tightly tuned to Claude Code plus a Rails/JS testing pattern.

That is fine for a productized personal workflow.
It is not enough for your larger system.

---

## What not to copy

### 1. Do not replace your system with gstack

That would be a downgrade.

You already have deeper assets:
- DGC execution and routing
- OpenClaw agent surfaces
- KaizenOps audit and command center
- Dharma Swarm / JIKOKU / SAMAYA semantics

`gstack` is a sharper local workflow layer, not a better whole system.

### 2. Do not copy the Claude-only assumption

Your system already spans:
- Codex
- Claude
- OpenClaw
- local/cloud model lanes

The right move is to copy the mode architecture, not the single-vendor binding.

### 3. Do not copy prompt-heavy authority without system state

The biggest limit in `gstack` is that modes are mostly behavioral overlays.
Your system should bind modes to:
- policy
- ontology
- telemetry
- budget
- routing
- audit trail

---

## What to copy directly

### A. Build your own explicit gear system

Create a cross-runtime skill/mode pack for:

- `ceo-review`
- `eng-review`
- `preflight-review`
- `ship`
- `qa`
- `browse`
- `retro`
- `incident-commander`

These should work across:
- Codex
- Claude Code
- OpenClaw
- DGC

Do not bury them in prose docs.
Make them first-class callable operating modes.

### B. Build a KaizenOps-native browser/QA lane

`gstack`'s browse binary is the single most concrete engineering pattern worth emulating.

You should either:
- adopt the same local CLI + persistent daemon pattern, or
- directly integrate a similar browser worker into KaizenOps and/or DGC

Desired result:
- per-workspace browser state
- persistent cookies
- reproducible smoke tests
- screenshots + console/network capture
- incidents emitted into KaizenOps

### C. Make setup one-step

Your system currently has too many partial surfaces.

You need one setup command that:
- verifies DGC
- verifies OpenClaw
- verifies local browser QA
- verifies KaizenOps
- verifies model lanes
- emits a single readiness report

This should feel like:

```text
bootstrap -> verify -> operate
```

not:

```text
many half-configured worlds
```

### D. Encode workflow sequence as doctrine

Adopt a standard execution ladder:

1. `ceo-review`
2. `eng-review`
3. implementation
4. `preflight-review`
5. `ship`
6. `qa`
7. `retro`

Then enforce it with:
- templates
- task states
- KaizenOps checkpoints

---

## What your system should become

The right synthesis is:

```text
Dharma Swarm = mission intelligence
DGC = execution and delegation runtime
OpenClaw = user-facing multi-agent shell
KaizenOps = command center, policy, incident, audit
Mode Pack = cognitive gears across all of the above
```

This means `gstack` should become a subsystem idea, not the center.

In your system, the upgraded equivalent should be:

### 1. Ontology

Use Palantir's pattern:

- Objects:
  - `Mission`
  - `Task`
  - `Workspace`
  - `Agent`
  - `Session`
  - `Artifact`
  - `Policy`
  - `Incident`
  - `Offer`
  - `Customer`
  - `RevenueEvent`

- Links:
  - `mission -> task`
  - `task -> session`
  - `session -> artifact`
  - `agent -> incident`
  - `workspace -> policy`
  - `customer -> offer`

- Actions:
  - `delegate`
  - `approve`
  - `reroute`
  - `release`
  - `qa_run`
  - `close_incident`

- Functions:
  - `health_score`
  - `risk_score`
  - `value_score`
  - `budget_score`
  - `readiness_score`

### 2. Mode-bound execution

Each mode should carry:
- allowed tools
- review depth
- required tests
- expected outputs
- escalation rules

So `eng-review` is not just a tone.
It is a contract.

### 3. KaizenOps as the mandatory audit surface

Every delegated coding flow should emit:
- task started
- mode selected
- branch/worktree
- artifacts created
- tests passed/failed
- review findings
- release state

That is where your system surpasses `gstack`.

---

## Immediate gaps in the current system

### 1. Too many configured agents, too little routing

Current OpenClaw shape:
- many agents configured
- almost no actual routing
- gateway health issues
- sandbox warnings on smaller models

That means your system has nominal capacity, not real coordinated capacity.

### 2. Local model inventory is not trustworthy yet

Ollama is configured, but the storage path is broken enough that `ollama list` fails.
Do not build strategy on "we have local models" until local model access is clean and inspectable.

### 3. DGC is stronger than the surrounding shell

DGC appears healthier than OpenClaw as an operational core.
That suggests you should anchor execution around DGC and let OpenClaw be a controlled surface, not the source of truth.

### 4. KaizenOps needs deeper integration with workflow states

KaizenOps can already audit sessions.
The next step is to make it understand:
- planning
- implementation
- review
- ship
- QA
- retro

as first-class states.

---

## Highest-leverage implementation plan

### Phase 1: Build your own gstack-equivalent mode pack

Create a shared package of mode contracts:

- `ceo-review`
- `eng-review`
- `preflight-review`
- `ship`
- `qa`
- `browse`
- `retro`
- `incident-commander`

Target:
- usable by Codex and Claude Code
- optionally wrapped for OpenClaw

### Phase 2: Add browser QA as a real runtime tool

Either:
- reuse the gstack browser directly as an operator tool, or
- build your own equivalent with the same architecture

Then route evidence into KaizenOps.

### Phase 3: Route all work through workspaces and modes

Every task should have:
- workspace
- mode
- budget
- owner
- review state
- incident state

### Phase 4: Make KaizenOps the factory-floor board

The board should show:
- work by mode
- work by agent
- work by customer
- open incidents
- QA failures
- release readiness
- value produced per session

---

## Bottom line

`gstack` is worth copying for:
- cognitive gear separation
- browser QA architecture
- one-command packaging
- operator ergonomics

It is not worth copying as:
- your main runtime
- your ontology
- your audit layer
- your commercial control plane

The correct move is:

```text
Copy gstack's workflow clarity.
Bind it to DGC execution.
Instrument it through KaizenOps.
Treat OpenClaw as a controlled shell, not the deepest core.
```

That is the path that actually levels up the whole system instead of just adding another clever layer.
