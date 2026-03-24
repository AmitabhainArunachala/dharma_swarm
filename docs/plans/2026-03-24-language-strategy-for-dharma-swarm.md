## dharma_swarm Language Strategy

Date: 2026-03-24
Status: Merge-safe strategy artifact
Scope: Language boundaries, migration triggers, and implementation doctrine

### 1. Executive Position

`dharma_swarm` should be a multi-language system, but not a multi-language mess.

The correct shape is:

- Python for cognition, orchestration, policy, evaluation, and rapid evolution
- TypeScript for operator-facing surfaces and dashboard interaction
- Rust for narrow substrate components that need systems-grade throughput, safety, or packaging
- Bash for thin glue only
- SQLite/JSONL as durable local state until a specific storage bottleneck justifies more

The system should not be "ported to Rust."
It should remain Python-led, with Rust introduced surgically at stable systems boundaries.

### 2. Current Repo Reality

The repo today is already split by function:

- Python runtime and control plane live in [dharma_swarm/swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py), [dharma_swarm/agent_runner.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py), [dharma_swarm/orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py), [dharma_swarm/runtime_state.py](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_state.py), and [dharma_swarm/telemetry_plane.py](/Users/dhyana/dharma_swarm/dharma_swarm/telemetry_plane.py).
- FastAPI operator/API surfaces live in [api/main.py](/Users/dhyana/dharma_swarm/api/main.py) and [api/routers](/Users/dhyana/dharma_swarm/api/routers).
- The dashboard is TypeScript/React in [dashboard/src](/Users/dhyana/dharma_swarm/dashboard/src).
- Rust is already present, but only as a thin Tauri shell in [desktop-shell/src-tauri/Cargo.toml](/Users/dhyana/dharma_swarm/desktop-shell/src-tauri/Cargo.toml) and [desktop-shell/src-tauri/src/main.rs](/Users/dhyana/dharma_swarm/desktop-shell/src-tauri/src/main.rs).

There is not yet a substantive Rust runtime substrate.

That matters because the strategic question is not "whether Rust is allowed."
It already is.
The real question is "where Rust belongs."

### 3. Language Constitution

#### 3.1 Python: The Cognitive Control Plane

Python remains the default language for:

- swarm orchestration
- agent execution flow
- policy and telos logic
- evaluation and thinkodynamic scoring
- replication and constitutional governance
- research loops and fast iteration
- most persistence adapters while the data model is still evolving

Why:

- fastest iteration for changing ontology
- strongest local ecosystem for LLM tooling and experimentation
- easiest language for agents and humans to modify together
- current repo already has strong typed/docstring conventions in Python

Files that should remain Python-first:

- [dharma_swarm/swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py)
- [dharma_swarm/agent_runner.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py)
- [dharma_swarm/orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py)
- [dharma_swarm/thinkodynamic_director.py](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py)
- [dharma_swarm/replication_protocol.py](/Users/dhyana/dharma_swarm/dharma_swarm/replication_protocol.py)
- [dharma_swarm/consolidation.py](/Users/dhyana/dharma_swarm/dharma_swarm/consolidation.py)

Doctrine:

- keep the control plane soft, expressive, and easy to mutate
- do not freeze evolving ontology into a systems language too early

#### 3.2 TypeScript: The Operator Surface

TypeScript remains the default language for:

- dashboard pages
- live operator control surfaces
- visualizations
- browser-native interactivity
- client-side state composition

Why:

- the dashboard is already established in TypeScript
- React/Next is the right tool for operator visibility and control
- the language boundary is clear: backend intelligence in Python, operator interaction in TypeScript

Files that should remain TypeScript-first:

- [dashboard/src/app/dashboard](/Users/dhyana/dharma_swarm/dashboard/src/app/dashboard)
- [dashboard/src/hooks](/Users/dhyana/dharma_swarm/dashboard/src/hooks)
- [dashboard/src/lib](/Users/dhyana/dharma_swarm/dashboard/src/lib)

#### 3.3 Rust: The Substrate Language

Rust should be introduced only for components that are:

- operationally stable
- failure-sensitive
- concurrency-heavy
- throughput-sensitive
- packaging-sensitive
- semantically narrow enough to hide behind a crisp contract

Rust is for substrate, not for ideology.

Good Rust targets:

- durable claim/run/lease engine
- high-volume telemetry ingestion and compaction
- trace indexing / log-structured event reduction
- workspace or sandbox supervisor
- file watching and process custody layer
- local daemon kernel or packaged operator binary
- graph/layout/parsing hot paths with measurable CPU pressure

Bad Rust targets right now:

- rapidly changing orchestration logic
- evolving policy/telos logic
- experimental research modules
- prompt, routing, or evaluation logic still under active conceptual change

### 4. Trigger Conditions For Leaving Python

A component should move from Python only if at least two of these are true:

1. It is on a measured hot path.
2. It must run continuously and recover cleanly after crashes.
3. It coordinates concurrent I/O or state transitions that are easy to corrupt.
4. It benefits materially from a single packaged binary.
5. The contract is stable enough that the boundary is unlikely to churn weekly.

A component should not move if any of these are true:

- the ontology is still changing rapidly
- the component is mostly decision logic
- the main pain is poor structure rather than Python performance
- debugging speed matters more than raw performance
- the boundary would be vague or leaky

### 5. Migration Order

The migration order should always be:

1. Stabilize the contract in Python.
2. Add tests that pin the contract.
3. Measure the real pain.
4. Extract the component behind a process boundary.
5. Re-implement behind that boundary in Rust only if the ROI is clear.

Process boundary first.
FFI later, only if needed.

Preferred integration modes:

- local HTTP or Unix socket service
- stdio sidecar
- append-only file or SQLite contract where appropriate

Avoid as the first move:

- deep `pyo3` coupling
- pervasive shared-memory assumptions
- broad rewrites of Python modules into Rust crates

### 6. Why Process Boundaries Win First

Process boundaries preserve:

- Python iteration speed
- independent testing
- restart isolation
- clear ownership
- better multi-agent development ergonomics

They also make it easier to decide later whether the Rust component is actually paying for itself.

If a Rust sidecar proves stable and indispensable, tighter integration can come later.

### 7. Why Not Go Or Other Languages

`dharma_swarm` should not casually expand beyond Python, TypeScript, and Rust.

Go is reasonable if the system ever wants a network-first distributed control plane with many long-lived services and simple operational packaging.
That is not the current need.

Right now:

- Python already owns the control plane
- TypeScript already owns the operator surface
- Rust already has a natural foothold for local systems work

Adding Go, Java, Elixir, or C++ now would increase cognitive tax without solving a real boundary problem.

### 8. Recommended Pilot Rust Candidates

If the repo adopts a real Rust substrate, the first pilot should be one of:

#### Option A: Runtime kernel sidecar

Owns:

- worker heartbeats
- claim leases
- stale-claim recovery
- process custody

Why:

- narrow semantics
- high operational value
- strong fit for state machines and recovery

#### Option B: Telemetry/event compactor

Owns:

- ingestion of session events
- compaction of traces
- efficient event queries

Why:

- throughput and durability matter
- the logic is mechanical, not conceptual

#### Option C: Workspace/sandbox supervisor

Owns:

- process launching
- kill/drain/restart semantics
- file watcher events
- supervisor invariants

Why:

- safety-sensitive
- process-oriented
- easy to keep semantically narrow

### 9. What Not To Do

Do not:

- rewrite `swarm.py` into Rust
- rewrite `agent_runner.py` into Rust
- move telos or policy logic into a compiled language before its semantics stabilize
- add Rust because it "feels more serious"
- introduce multiple systems languages at once

The correct pattern is:

- keep cognition flexible
- harden substrate selectively

### 10. Immediate Plan

The repo can act on this now without a research detour.

Immediate next steps:

1. Keep Python as the explicit default for new control-plane modules.
2. Declare Rust as `substrate-only` in architecture docs.
3. Choose one candidate substrate pilot, but do not implement until its contract is pinned.
4. Add migration gates:
   - measured bottleneck
   - stable interface
   - tests in place
   - process-boundary design approved
5. Revisit after the style constitution and runtime control-plane seams are cleaner.

### 11. Final Position

The language strategy should be:

- Python-led
- TypeScript-fronted
- Rust-backed where substrate pressure justifies it

That gives `dharma_swarm` the right balance:

- fast iteration
- recursive adaptability
- strong operator ergonomics
- modularity
- future-proofing without premature hardening

The system becomes more powerful not by rewriting itself into a lower-level language, but by putting the right language at the right boundary.
