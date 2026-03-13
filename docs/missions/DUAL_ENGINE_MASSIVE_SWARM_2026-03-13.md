# Dual-Engine Massive Swarm Mission

Date: 2026-03-13
Purpose: define one large-scale DGC operating mode that performs semantic deepening and execution at the same time without collapsing into chaos

## North Star

Build a `dual-engine massive swarm` that can do two jobs simultaneously:

1. deepen semantic understanding of a repo, vault, or wider filesystem
2. execute world-class build campaigns from the best hardened clusters

The standard is not "more agents."
The standard is `architectural composition`.

## Core Object

One `Campaign` governs two coordinated chambers:

- `Semantic Chamber`: turns raw material into clusters, contradictions, evidence, and briefs
- `Execution Chamber`: turns briefs into specs, code, tests, deployments, and handoffs

Both chambers write to one shared `campaign ledger`.

## Hard Rules

- One top-level mission at a time.
- Parallelism is read-heavy by default.
- Mutable work has a single write authority per workspace segment.
- No task is complete without an artifact and evidence.
- No external claim survives without a source or a marked uncertainty tag.
- No code change survives without verification.
- If execution stalls, deepen semantics.
- If semantic work stalls, attack contradictions, open questions, or quality gaps.
- If both stall, run probes, tests, or ingest more source material.

## Swarm Topology

### Command Layer

1. `Director`
   Uses `thinkodynamic_director.py` as mission authority.
   Owns mission selection, escalation, shutdown, and replan.

2. `Ledger Keeper`
   Uses `models.py`, `runtime_state.py`, `session_ledger.py`, and `task_board.py`.
   Owns campaign state, artifact references, and blocker truth.

### Semantic Chamber

1. `Cartographer`
   Scans repos, vaults, and filesystems.
   Primary seams: `semantic_digester.py`, `context_search.py`, `workspace_topology.py`.

2. `Archeologist`
   Recovers note meaning, provenance, backlinks, frontmatter, and latent themes.
   Primary seams: `semantic_digester.py`, `protocols/recursive_reading.py`, `memory_lattice.py`.

3. `Researcher`
   Grounds claims and seeks contradictions.
   Primary seams: `semantic_researcher.py`, `field_knowledge_base.py`, `context_compiler.py`.

4. `Synthesist`
   Builds clusters, formal intersections, and semantic gravity surfaces.
   Primary seams: `semantic_synthesizer.py`, `semantic_gravity.py`, `field_graph.py`.

5. `Contradiction Hunter`
   Looks for false coherence, citation weakness, and overclaimed synthesis.
   Primary seams: `steelman_gate.py`, `anekanta_gate.py`, `telos_gates.py`.

6. `Bridge Keeper`
   Pushes hardened semantic artifacts into retrieval and planning memory.
   Primary seams: `semantic_memory_bridge.py`, `memory_lattice.py`, `engine/unified_index.py`.

### Execution Chamber

1. `Architect`
   Converts clusters into system design and build briefs.
   Primary seams: `plan_compiler.py`, `mission_contract.py`, `artifact_manifest.py`.

2. `Planner`
   Turns briefs into bounded task trees.
   Primary seams: `planner.py`, `task_board.py`, `runtime_contract.py`.

3. `Builder`
   Sole default write authority for implementation.
   Primary seams: `agent_runner.py`, `diff_applier.py`, `orchestrator.py`.

4. `Surgeon`
   Handles targeted refactors, bug fixes, and debt removal under spec.
   Primary seams: `diff_applier.py`, `evolution.py`, `router_retrospective.py`.

5. `Validator`
   Owns tests, probes, and acceptance evidence.
   Primary seams: `full_power_probe.py`, `doctor.py`, `evolution.py`.

6. `Deployer`
   Owns packaging, runtime handoff, and externalization.
   Primary seams: `artifact_store.py`, `workspace_manager.py`, integration hooks.

### Meta Layer

1. `Quality Governor`
   Fail-closes transitions that lack evidence.
   Primary seams: `telos_gates.py`, `anekanta_gate.py`, `dogma_gate.py`.

2. `Evolution Steward`
   Learns from execution results without corrupting mission direction.
   Primary seams: `evolution.py`, `archive.py`, `fitness_predictor.py`.

## Operating Loop

### Loop A: Semantic Deepening

1. ingest source material
2. extract concepts, claims, links, and formal structures
3. ground claims and mark uncertainty
4. synthesize clusters and rank gravity
5. harden the top clusters
6. emit `brief-ready artifacts`

### Loop B: Execution

1. consume hardened cluster brief
2. compile spec and acceptance criteria
3. execute bounded build tasks
4. validate results
5. archive evidence and update the campaign ledger
6. feed new artifacts back into the semantic layer

### Coupling Loop

The two loops meet at one contract:

`cluster -> brief -> spec -> build -> evidence -> memory update`

If that contract is weak, the swarm becomes theater.
If that contract is strong, the swarm becomes compound intelligence.

## What Makes This An Architectural Masterpiece

The design succeeds only if it holds these tensions cleanly:

- depth without drift
- speed without recklessness
- parallelism without patch conflict
- autonomy without narrative inflation
- abstraction without loss of provenance

The masterpiece is not visual complexity.
It is `clear contracts across different kinds of cognition`.

## Immediate Build Targets

### Phase 1: Campaign Sovereignty

Target files:

- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/models.py`
- `dharma_swarm/runtime_state.py`
- `dharma_swarm/task_board.py`
- `dharma_swarm/session_ledger.py`

Goal:
Make the campaign object canonical and force every major task through it.

### Phase 2: Cluster-To-Spec Compiler

Target files:

- `dharma_swarm/semantic_synthesizer.py`
- `dharma_swarm/semantic_hardener.py`
- `dharma_swarm/semantic_memory_bridge.py`
- `dharma_swarm/plan_compiler.py`
- `dharma_swarm/artifact_manifest.py`

Goal:
Turn semantic clusters into execution-grade briefs with evidence and open questions.

### Phase 3: Parallel Discipline

Target files:

- `dharma_swarm/swarm.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/agent_runner.py`
- `dharma_swarm/startup_crew.py`

Goal:
Make semantic agents read-heavy and make the builder the default write authority.

### Phase 4: Quality Flywheel

Target files:

- `dharma_swarm/telos_gates.py`
- `dharma_swarm/evolution.py`
- `dharma_swarm/full_power_probe.py`
- `dharma_swarm/doctor.py`

Goal:
Ensure that every transition is gated by evidence, verification, and archive truth.

## Real Deliverables For A First Strong Run

1. one canonical campaign record
2. one repo semantic digest
3. one external corpus semantic digest
4. one ranked cross-corpus gravity map
5. three hardened cluster briefs
6. one execution brief promoted into a build branch
7. one verified artifact shipped or staged
8. one handoff packet with blockers and next actions

## Failure Modes

This mission fails if:

- agents mostly talk to each other and do not ship artifacts
- the semantic chamber generates link-rich but judgment-poor output
- the execution chamber codes without semantic context
- the director allows duplicate or generic churn
- the ledger cannot reconstruct why a decision was made

## Bottom Line

The next version of DGC should behave like a `bilingual organism`:

- one language is meaning
- one language is execution

The system wins when both languages stay alive in the same campaign and force each other to become more exact.
