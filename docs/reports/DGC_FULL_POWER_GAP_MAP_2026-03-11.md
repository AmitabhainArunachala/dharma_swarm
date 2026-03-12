# DGC Full-Power Gap Map

Date: 2026-03-11
Purpose: define the upgraded north star, state where DGC is now, and specify
what must change for it to behave like a persistent mission organism

## Full-Power Definition

DGC at full power should be:

**a persistent mission organism that converts vague, high-stakes intent into
multi-step, evidence-backed execution campaigns with continuity across
sessions, agents, tools, and days.**

That means:

- it selects missions, not just commands
- it compiles deliverables, not just plans
- it routes specialized work, not just one general assistant loop
- it persists state and memory, not just text transcripts
- it ships artifacts, not just analyses
- it wakes up and continues, not restarts from scratch

## What A Really Good Run Should Look Like

If you give DGC one serious intent at night, by morning it should produce:

- 3-10 durable artifacts
- a clear mission tree
- explicit statuses: shipped, blocked, escalated, abandoned
- evidence for every important claim
- a ranked next-step queue
- a clean handoff for human judgment

If it only chats, scans, reflects, or generates more reports, it failed.

## Current State (Live, 2026-03-11)

Grounded in current commands:

- `python3 -m dharma_swarm.dgc_cli mission-status --json`
- `python3 -m dharma_swarm.dgc_cli doctor --json --quick`
- `python3 -m dharma_swarm.dgc_cli canonical-status --json`

### What Is Healthy

`mission-status`

- core mission spine: `6/6 PASS`
- tracked wiring: `16/16`
- accelerator lane: explicit `DORMANT` rather than broken
- OpenClaw config present with `15` agents and multiple providers

`doctor --quick`

- overall status: `PASS`
- all `8/8` checks pass
- env autoload, worker binaries, provider env, fasttext, redis, router paths,
  and router wiring all healthy

### What Is Still Structurally Weak

`canonical-status`

- canonical DGC repo is `/Users/dhyana/dharma_swarm`
- repo is `ahead 15` and still dirty
- overall DGC topology is not marked `fully_merged`
- legacy DGC repo is still mutating

And beyond the diagnostics:

- plain `dgc` still defaults to TUI/chat behavior rather than mission
  execution
- swarm init still spawns generic crew and generic seed tasks
- `ThinkodynamicDirector` is present but optional, not the commanding default
- many lanes observe and report well, but do not force closure on one artifact
- there is no hard campaign object with mission, deliverable, done criteria,
  stop condition, and owner

## Honest Diagnosis

DGC is no longer mainly blocked by wiring.

DGC is now blocked by **convergence architecture**.

The system can:

- remember
- route
- spawn
- gate
- evolve
- diagnose
- archive

But it still does not force those capabilities into one dominant pattern:

**mission -> artifact -> review -> next mission**

So it feels like wheel-spinning because the orchestration surface is richer than
the commitment surface.

## The Four Missing Powers

### 1. Mission Authority

DGC must have one active mission at a time at the top level.

Not:

- many generic seed tasks
- ambient backlog drift
- status-first idle loops

It needs:

- mission title
- why now
- deliverable
- done condition
- kill condition
- timebox

### 2. Campaign Ledger

DGC needs a first-class campaign object that spans sessions.

Minimum fields:

- mission id
- current branch
- active subtasks
- artifacts produced
- blockers
- decisions made
- next highest-leverage move

Without this, memory exists but campaign continuity is still weak.

### 3. Director Sovereignty

`ThinkodynamicDirector` should stop being merely available.

It should become the authority that:

- selects the mission
- decides when to descend into execution
- decides when work is done enough
- decides when to re-ascend and choose the next move

Right now it is a subsystem.
At full power it should be the top of the stack.

### 4. Closure Pressure

DGC needs stronger anti-dissipation rules:

- no report without updating a mission branch
- no task without a deliverable
- no overnight run without a bounded artifact set
- no generic startup churn when a live mission already exists

## Build Path

## Phase 0: Change The Default Behavior

Target:

- `dharma_swarm/dgc_cli.py`

Required change:

- default `dgc` should enter mission mode, not TUI mode
- if no mission is active, synthesize top candidate missions from memory,
  backlog, and operator hints
- force explicit selection or preview mode

Success condition:

- the first thing DGC does is choose what matters

## Phase 1: Introduce A Canonical Mission Object

Targets:

- `dharma_swarm/models.py`
- `dharma_swarm/task_board.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/runtime_state.py`

Required change:

- add `Mission` / `Campaign` records with deliverable, done condition,
  blockers, and artifact links
- bind tasks to a mission by default
- persist mission state across sessions

Success condition:

- every important task belongs to one mission branch

## Phase 2: Promote Director To Commanding Layer

Targets:

- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/swarm.py`
- `dharma_swarm/startup_crew.py`

Required change:

- director chooses or resumes the active mission on startup
- generic seed tasks are suppressed when a live mission exists
- fast-finishing tasks immediately escalate back upward for the next best move

Success condition:

- no more idle seed-task churn when meaningful mission work exists

## Phase 3: Campaign Ledger And Artifact Discipline

Targets:

- `dharma_swarm/orchestrator.py`
- `dharma_swarm/message_bus.py`
- `dharma_swarm/runtime_state.py`
- `dharma_swarm/flywheel_exporter.py`

Required change:

- every branch emits artifact and progress facts
- every blocker emits a human-facing escalation artifact
- every completed branch updates campaign state and next-step ranking

Success condition:

- the morning handoff is reconstructable from the ledger, not just prose

## Phase 4: Provider-Role Specialization

Targets:

- `dharma_swarm/providers.py`
- `dharma_swarm/agent_runner.py`
- `dharma_swarm/startup_crew.py`
- `dharma_swarm/routing_memory.py`

Required change:

- thinkers, validators, implementers, and external-research lanes become
  explicit mission roles
- route by empirical success for role + mission type
- allow mixed-provider campaign execution without losing coherence

Success condition:

- DGC behaves like a coordinated organism, not a single model wearing many hats

## Phase 5: Overnight Campaign Mode

Targets:

- `scripts/start_overnight.sh`
- `scripts/start_codex_overnight_tmux.sh`
- `scripts/start_thinkodynamic_director_tmux.sh`
- `dharma_swarm/dgc_cli.py`

Required change:

- overnight runs require:
  - active mission
  - max branches
  - artifact budget
  - escalation policy
  - stop conditions

Success condition:

- overnight mode reliably yields a bounded artifact set and next-step map

## What To Expect At Full Power

The operator experience should become:

You provide one intention.
DGC returns:

- the chosen mission
- why it chose it
- what it will produce
- what happened while you were away
- what changed in the system
- what still needs you

That is the threshold where DGC stops feeling like a cluster of good ideas and
starts feeling like a real execution organism.

## Near-Term Priority

The highest-leverage next move is:

**make mission selection and mission continuity the default operating loop.**

Not more status.
Not more subsystems.
Not more parallel generic tasks.

That single change would force the rest of DGC to begin compounding in the
right direction.
