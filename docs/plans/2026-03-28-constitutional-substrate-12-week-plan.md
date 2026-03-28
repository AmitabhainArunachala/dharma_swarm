# Constitutional Substrate 12-Week Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep the full DHARMA SWARM moonshot intact while making it computable: philosophy as runtime law, adaptive behavior as explicit protocol, and organismic state as measurable signal.

**Architecture:** Preserve the project’s ambition, but stratify it into six layers: constitutional kernel, action/event substrate, operational services, living adaptive layers, control plane, and verification/witness. The key move is not reducing scope; it is forcing every major concept to exist as `law`, `protocol`, or `signal`, then making those mappings explicit in code, tests, traces, and operator surfaces.

**Tech Stack:** Python 3, FastAPI, Next.js, SQLite, JSONL traces, pytest, launchd/tmux operator scripts, existing `dharma_swarm` telemetry and dashboard contracts.

---

## Non-Negotiable Rules

Every concept must compile to one of three forms:

- `Law`: invariant, gate, constraint, or policy boundary
- `Protocol`: lifecycle, state machine, or bounded interaction contract
- `Signal`: measurable runtime variable with source, update rule, and observer

The six-layer map for this plan:

1. `Kernel`: telos, reversibility, autonomy, identity, mutation rights
2. `Substrate`: actions, traces, events, decisions, provenance
3. `Services`: registry, tasks, memory, persistence, routing, costs
4. `Living Layers`: stigmergy, shakti, subconscious, evolution, organism
5. `Control Plane`: API, dashboard, shells, operator workflows
6. `Witness`: verification lane, replay, audits, probes, regression gates

Success at week 12 means:

- one canonical control-plane truth surface
- one constitutional kernel with typed invariants
- one action/event substrate for meaningful mutations
- organism/runtime boundaries no longer smeared across legacy/current seams
- verification runs as an actually independent witness
- live canaries prove that the system changes in ways the next cycle can build on

---

### Task 1: Week 1 — Freeze the Constitutional Map

**Files:**
- Create: `architecture/CONSTITUTIONAL_SUBSTRATE_V1.md`
- Modify: `architecture/PRINCIPLES.md`
- Modify: `LIVING_LAYERS.md`
- Modify: `VERIFICATION_LANE.md`

**Step 1: Write the constitutional RFC**

Define, for each major philosophical term in the repo, whether it is primarily:

- a law
- a protocol
- a signal

Minimum required mappings:

- telos
- dharma
- self-authorship
- downward causation
- witness
- organism
- strange loop
- dream layer
- evolution
- living layers

**Step 2: Add layer boundaries**

For each of the six layers above, document:

- what it is allowed to decide
- what it is allowed to emit
- what it is not allowed to bypass

**Step 3: Proof**

Run:

```bash
rg -n "Law|Protocol|Signal|Layer 0|Layer 1|Layer 2|Layer 3|Layer 4|Layer 5" architecture/CONSTITUTIONAL_SUBSTRATE_V1.md architecture/PRINCIPLES.md LIVING_LAYERS.md VERIFICATION_LANE.md
```

Expected:

- all major concepts are mapped
- witness and control-plane boundaries are explicit

---

### Task 2: Week 2 — Extract the Constitutional Kernel

**Files:**
- Create: `dharma_swarm/constitutional_kernel.py`
- Create: `tests/test_constitutional_kernel.py`
- Modify: `dharma_swarm/telos_gates.py`
- Modify: `dharma_swarm/guardrails.py`
- Modify: `dharma_swarm/dharma_kernel.py`

**Step 1: Write failing tests**

Cover:

- invariant loading
- mutation-right checks
- autonomy floor decisions
- reversibility requirement checks
- serialization of a kernel verdict

**Step 2: Implement minimal kernel surface**

Create a tiny typed surface for:

- invariants
- autonomy policy
- reversibility requirement
- mutation approval envelope

**Step 3: Route existing gate code through it**

The goal is not to rewrite all gates. It is to give them one typed kernel to call into.

**Step 4: Proof**

Run:

```bash
pytest -q tests/test_constitutional_kernel.py
```

Expected: PASS

---

### Task 3: Week 3 — Make Actions the Universal Mutation Unit

**Files:**
- Create: `dharma_swarm/action_contracts.py`
- Create: `tests/test_action_contracts.py`
- Modify: `dharma_swarm/traces.py`
- Modify: `dharma_swarm/agent_runner.py`
- Modify: `dharma_swarm/swarm.py`
- Modify: `dharma_swarm/telemetry_plane.py`

**Step 1: Write failing tests**

Cover a canonical action envelope with:

- actor
- intent
- object
- gate result
- outcome
- reversibility status
- cost
- confidence

**Step 2: Implement minimal typed action schema**

Do not boil the ocean. Start with the action schema and conversion helpers.

**Step 3: Thread through one real mutation path**

Pick one high-signal path, for example:

- agent tool execution
- task status mutation
- cron-job state transition

**Step 4: Proof**

Run:

```bash
pytest -q tests/test_action_contracts.py
```

Expected: PASS

Then prove one live path emits the action envelope.

---

### Task 4: Week 4 — Stabilize the Control-Plane Contract

**Files:**
- Modify: `api/main.py`
- Modify: `api/routers/chat.py`
- Modify: `api/routers/agents.py`
- Modify: `dashboard/src/lib/types.ts`
- Modify: `dashboard/src/lib/runtimeControlPlane.ts`
- Modify: `dashboard/src/components/chat/ChatInterface.tsx`
- Test: `tests/test_dashboard_chat_router.py`

**Step 1: Enumerate canonical operator contracts**

At minimum:

- `/api/chat/status`
- `/api/chat`
- `/api/agents`
- `/api/health`

**Step 2: Make the dashboard show only contract truth**

No hidden local assumptions about lanes, sessions, or status notes.

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_dashboard_chat_router.py
```

Expected: PASS

Also record any existing frontend compile/test blockers that are outside this diff.

---

### Task 5: Week 5 — Separate Witness From Organism

**Files:**
- Create: `dharma_swarm/runtime_replay.py`
- Create: `tests/test_runtime_replay.py`
- Modify: `scripts/system_integration_probe.py`
- Modify: `scripts/start_verification_lane.sh`
- Modify: `VERIFICATION_LANE.md`
- Modify: `dharma_swarm/provider_smoke.py`

**Step 1: Write failing tests for replayable witness artifacts**

Cover:

- trace replay load
- independent health verdict
- degraded verdict on missing evidence

**Step 2: Implement minimal replay/witness artifact**

The witness lane should be able to explain:

- what happened
- why it thinks it happened
- what evidence is missing

without sharing the same silent assumptions as the runtime path.

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_runtime_replay.py
python3 scripts/system_integration_probe.py
```

Expected:

- replay tests pass
- integration probe reports degradations honestly

---

### Task 6: Week 6 — Split the Organism Seam

**Files:**
- Create: `dharma_swarm/organism_legacy.py`
- Create: `dharma_swarm/organism_runtime.py`
- Modify: `dharma_swarm/organism.py`
- Modify: `dharma_swarm/swarm.py`
- Create: `tests/test_organism_runtime.py`

**Step 1: Write failing tests around the legacy/current split**

Cover:

- legacy organism import surface still works
- runtime heartbeat surface remains stable
- `SwarmManager` only depends on the runtime half

**Step 2: Extract without behavior changes**

The point is separation first, not redesign.

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_organism_runtime.py
```

Expected: PASS

---

### Task 7: Week 7 — Shrink the Coupling Hotspots

**Files:**
- Create: `dharma_swarm/cli/runtime_commands.py`
- Create: `dharma_swarm/cli/provider_commands.py`
- Create: `dharma_swarm/cli/control_plane_commands.py`
- Modify: `dharma_swarm/dgc_cli.py`
- Modify: `dharma_swarm/swarm.py`

**Step 1: Slice one command family out of `dgc_cli.py`**

Start with one bounded family only:

- runtime
- provider
- control-plane

**Step 2: Reduce cross-import sprawl**

The goal is to stop adding more weight to `dgc_cli.py` and `swarm.py`.

**Step 3: Proof**

Run:

```bash
wc -l dharma_swarm/dgc_cli.py dharma_swarm/swarm.py
pytest -q tests -k "dgc_cli or swarm"
```

Expected:

- line counts do not increase
- extracted command path passes

---

### Task 8: Week 8 — Formalize the Certified Peer Lanes

**Files:**
- Modify: `dharma_swarm/certified_lanes.py`
- Modify: `api/routers/chat.py`
- Modify: `dharma_swarm/contracts/intelligence_agents.py`
- Modify: `dharma_swarm/provider_smoke.py`
- Create: `scripts/certify_lanes.py`
- Test: `tests/test_dashboard_chat_router.py`
- Test: `tests/test_intelligence_agents.py`

**Step 1: Add lane certification protocol**

Each certified lane should have:

- registration identity
- live probe contract
- last verification result
- failure class
- operator role

**Step 2: Persist certification results**

Write machine-readable outputs under `~/.dharma`.

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_dashboard_chat_router.py tests/test_intelligence_agents.py
python3 scripts/certify_lanes.py --dry-run
```

Expected:

- dashboard and KaizenOps metadata stay aligned
- certification harness reports actual side effects, not just model text

---

### Task 9: Week 9 — Harden the Thinkodynamic Evolution Loop

**Files:**
- Modify: `dharma_swarm/thinkodynamic_director.py`
- Modify: `dharma_swarm/thinkodynamic_canary.py`
- Modify: `scripts/system_integration_probe.py`
- Test: `tests/test_thinkodynamic_canary.py`
- Test: `tests/test_thinkodynamic_director.py`

**Step 1: Remove false-green behavior**

Priority defects already observed:

- stale review reuse
- generic workflow mismatch
- heuristic-only council silently passing
- test files ranking as top strategic signals

**Step 2: Keep a scored canary in place**

Every cycle should generate:

- score
- degraded reasons
- concrete next fix

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_thinkodynamic_canary.py tests/test_thinkodynamic_director.py
python3 scripts/system_integration_probe.py
```

Expected:

- canary finds real failures
- probe does not claim full health if those failures remain

---

### Task 10: Week 10 — Build the Economic Closure Spine

**Files:**
- Modify: `dharma_swarm/economic_agent.py`
- Create: `dharma_swarm/economic_contracts.py`
- Create: `tests/test_economic_contracts.py`
- Modify: `dharma_swarm/contracts/intelligence_stack.py`

**Step 1: Define the economic protocol**

At minimum:

- intake
- qualification
- execution
- deliverable
- payout-ready
- blocked
- failed

**Step 2: Make outcome states explicit**

The system should know the difference between:

- thought
- work
- deliverable
- revenue event

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_economic_contracts.py
```

Expected: PASS

---

### Task 11: Week 11 — Add Replayable Adaptation

**Files:**
- Create: `dharma_swarm/adaptation_replay.py`
- Create: `tests/test_adaptation_replay.py`
- Modify: `dharma_swarm/routing_memory.py`
- Modify: `dharma_swarm/evolution.py`
- Modify: `dharma_swarm/epistemic_telemetry.py`

**Step 1: Record why adaptation happened**

Every meaningful adaptive change should be replayable from:

- observed signal
- selected response
- expected gain
- actual outcome

**Step 2: Do not let learning remain implicit**

If the system "evolves," the evidence for that evolution must be queryable.

**Step 3: Proof**

Run:

```bash
pytest -q tests/test_adaptation_replay.py
```

Expected: PASS

---

### Task 12: Week 12 — Ship the Operator Narrative

**Files:**
- Modify: `README.md`
- Modify: `PRODUCT_SURFACE.md`
- Modify: `dashboard/src/app/dashboard/runtime/page.tsx`
- Modify: `api/routers/chat.py`
- Create: `docs/plans/2026-03-28-operator-narrative-demo.md`

**Step 1: Define one end-to-end canonical pulse**

The demo path should answer:

- what the system sensed
- what it proposed
- what law constrained it
- what it executed
- what changed
- what the witness observed
- what the next cycle will inherit

**Step 2: Make it visible**

The dashboard should expose enough truth that an operator can follow this path without reading Python logs first.

**Step 3: Proof**

Run one narrative demo end-to-end and capture the exact commands, files, and outputs in `docs/plans/2026-03-28-operator-narrative-demo.md`.

---

## Week-by-Week Cadence

- Monday: constitution and invariants
- Tuesday: substrate and typed contracts
- Wednesday: control plane and operator surface
- Thursday: living layers and adaptive loops
- Friday: witness, replay, and regression truthfulness
- Saturday: one end-to-end narrative run
- Sunday: philosophy and architecture only if it resolves into the next week’s files, contracts, or tests

## Explicit Do-Not-Do List

Do not:

- introduce another parallel GUI
- add new visionary subsystems before replay exists
- let dashboard surfaces infer runtime truth from stale local assumptions
- let living layers mutate without traces
- let verification share the same silent assumptions as the runtime
- keep expanding `dgc_cli.py` and `swarm.py` without extracting seams

## The Core Sentence

Do not reduce the vision. Reduce the ambiguity.
