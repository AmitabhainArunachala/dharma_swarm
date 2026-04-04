# Cybernetic Loop Map — dharma_swarm

**Generated:** 2026-04-04 | **Purpose:** Document every feedback loop's sense→act→evaluate→adapt path.
Each loop is traced from data source to data sink. A loop is "closed" only when its output feeds back as input to a future cycle.

---

## Loop Status Summary

| # | Loop | Interval | Closed? | Blocker |
|---|------|----------|---------|---------|
| 1 | Swarm Task Loop | 60s | **NO** | Agent execution crashes (MISMATCH-01 in INTERFACE_MISMATCH_MAP.md) |
| 2 | Organism Heartbeat | 300s | **PARTIAL** | Sense works (computes invariants). Act/adapt require running agents to produce data. |
| 3 | Evolution Loop | every 3rd tick | **NO** | Requires completed tasks to score fitness. No tasks complete. |
| 4 | Consolidation Loop | configurable | **NO** | Requires memories to consolidate. No memories exist. |
| 5 | Zeitgeist Scanner | configurable | **PARTIAL** | Local file scanning works. Claude-assisted scanning requires API key. |
| 6 | Witness Auditor | 3600s | **NO** | Provider type mismatch (MISMATCH-11). Also needs running agents to audit. |
| 7 | Training Flywheel | 300s | **NO** | Requires trajectory data from completed tasks. None exists. |
| 8 | Recognition Loop | 7200s | **NO** | Recognition seed never generated. Depends on cascade history. |
| 9 | Conductors | 120s | **NO** | Hardcoded to Anthropic, no fallback (INCONSISTENCY-03 in MODEL_ROUTING_MAP.md). |
| 10 | Context Agent | 60s | **NO** | Requires working agent_runner which crashes. |
| 11 | Replication Monitor | 3600s | **NO** | Enum deserialization gap (MISMATCH-02). |
| 12 | Self-Improvement | 3600s | **NO** | Requires DHARMA_SELF_IMPROVE + functioning DarwinEngine.evolve(). |
| 13 | Free Evolution Grind | 600s | **NO** | Requires DarwinEngine with functioning provider chain. |

---

## Detailed Loop Traces

### Loop 1: Swarm Task Loop (the core loop — everything depends on this)

```
SENSE:   orchestrator.tick() → route_next() → find ready tasks + idle agents
ACT:     orchestrator._execute_task() → agent_runner.run_task() → provider.complete_for_task()
         → router_v1.build_routing_signals() [CRASHES HERE: huggingface_hub import]
         → ModelRouter selects provider → LLM call → response
EVALUATE: orchestrator._execute_task() → on_task_complete():
         - Writes result to shared notes (~/.dharma/shared/)
         - Leaves stigmergy mark (StigmergyStore.leave_mark)
         - Emits SIGNAL_TASK_COMPLETED to signal_bus
         - Records cost in economic_spine
ADAPT:   orchestrator.route_next() reads stigmergy hot_paths to influence routing
         DarwinEngine reads fitness from task outcomes
         DynamicCorrectionEngine detects error_cascade/budget_overrun/dharmic_drift
```

**Data flow when working:**
```
Task queue → Orchestrator → AgentRunner → ModelRouter → LLM Provider
                                                           ↓
                                              LLM Response (text/tool_use)
                                                           ↓
                                              Task result stored:
                                                → shared notes (file)
                                                → stigmergy marks (JSONL)
                                                → signal_bus (in-memory)
                                                → economic_spine (SQLite)
                                                           ↓
                                              Next tick: Orchestrator reads
                                              stigmergy + fitness + corrections
                                              to route DIFFERENTLY
```

**What "closed" means:** The orchestrator's routing decisions in tick N+1 are influenced by the outcomes of tick N. Specifically:
- `route_next()` reads `hot_paths()` from stigmergy to prioritize active areas
- `_fitness_biased_pick()` uses agent fitness scores to prefer better agents
- `DynamicCorrectionEngine` signals cause task reassignment or agent retirement

**Current state:** Broken at the LLM call. No task has ever returned a result. The entire downstream feedback path is untested against real data.

---

### Loop 2: Organism Heartbeat

```
SENSE:   organism.heartbeat() computes 4 invariants:
         - criticality (λ_max): spectral radius of agent interaction graph
         - closure_ratio: fraction of loops where output feeds back as input
         - info_retention: fraction of state that persists across ticks
         - diversity_equilibrium: behavioral diversity across agent pool
INTERPRET: OrganismPulse classifies overall health (critical/degraded/healthy)
CONSTRAIN: TelosGatekeeper.check() — should this pulse trigger any action?
PROPOSE:  If health is degraded, propose corrective actions:
         - spawn new agents if diversity is low
         - retire failing agents if error_cascade detected
         - adjust DarwinEngine parameters if convergence stalled
EXECUTE:  Apply proposed actions (spawn, retire, adjust)
EVALUATE: Compare pre/post invariant values
ADAPT:    Update organism state, emit SIGNAL_HEARTBEAT to signal_bus
```

**Current state:** SENSE works (computes invariants, all zeros because nothing runs). INTERPRET works (correctly reports "critical"). Everything downstream is untested because there's no agent activity to respond to.

---

### Loop 3: Evolution Loop (DarwinEngine)

```
SENSE:   Read fitness scores from completed tasks
         Read stigmergy marks for hotspot detection
         Read routing_memory EWMA for provider performance
ACT:     DarwinEngine.auto_evolve():
         1. AutoProposer.cycle() — scan codebase for improvement opportunities
         2. DarwinEngine.propose() — generate code mutation
         3. TelosGatekeeper.check() — safety gate (AHIMSA, SATYA, etc.)
         4. Apply mutation (diff_applier.py — backup → apply → test → rollback if fail)
         5. Run tests to verify mutation doesn't break anything
EVALUATE: FitnessScore = weighted combination of:
         - correctness (test pass rate)
         - dharmic_alignment (gate scores)
         - performance (jikoku timing)
         - utilization (token efficiency)
         - elegance (code quality heuristics)
         - efficiency (API cost)
         - safety (no security regressions)
ADAPT:   Archive mutation + fitness in evolution/archive.jsonl
         MetaEvolutionEngine adjusts DarwinEngine parameters based on fitness trends
         DiversityArchive (MAP-Elites) tracks behavioral diversity
         Population control spawns/retires agents based on fitness
```

**Current state:** DarwinEngine can be instantiated. AutoProposer crashes on stigmergy None access (MISMATCH-10). No real fitness data exists because no tasks complete.

---

### Loop 4: Consolidation Loop (Memory)

```
SENSE:   Read recent pulse history, agent outputs, shared notes
ACT:     SleepTimeAgent.consolidate_knowledge():
         - Extract entities from text
         - Classify into Propositions (facts) and Prescriptions (recommendations)
         - Store in knowledge graph (graph_nexus)
         NeuralConsolidator (if provider available):
         - Synthesize patterns from multiple sources
         - Generate consolidated memory entries
EVALUATE: Check if consolidated knowledge matches existing entries (dedup)
ADAPT:   MemoryLattice.index_document() — add to searchable memory
         Stigmergy marks with action="dream" — subconscious contributions
         Next agent context compilation includes consolidated knowledge
```

**Current state:** SleepTimeAgent instantiates. Has consolidate_knowledge() method. But no raw material exists to consolidate — no agent outputs, no shared notes with real content.

---

### Loop 5: Zeitgeist Scanner (Environmental Intelligence)

```
SENSE:   ZeitgeistScanner.scan():
         - _scan_local(): read witness logs, shared notes, gate check patterns
         - _scan_claude(): (optional) use LLM to classify signals
ACT:     Classify signals as: competing_research, tool_release, methodology, threat, opportunity
EVALUATE: Count threats. If high gate block rate detected:
         - Write gate_pressure.json to ~/.dharma/
         - This tightens S3 trust mode (VSM System 3 control)
ADAPT:   Next cycle: telos gates read gate_pressure.json and adjust strictness
         This closes VSM Gap #1: S3↔S4 bidirectional feedback
```

**Current state:** Local scanning works (reads files). No gate checks are happening so there's no gate_pressure data to feed back. The VSM S3↔S4 loop is structurally present but has no data flowing through it.

---

### Loop 6: Witness Auditor (Random Audit)

```
SENSE:   WitnessAuditor randomly samples agent behavior
ACT:     LLM evaluates: "Does this agent output violate any dharmic principle?"
EVALUATE: Score output on dharmic dimensions
ADAPT:   Record witness observation to ~/.dharma/witness/
         Emit SIGNAL_WITNESS_ALERT if violation detected
         Evolution engine uses witness scores as fitness signal
```

**Current state:** WitnessAuditor receives ModelRouter as provider (should receive cost-controlled free provider). No agent outputs exist to audit.

---

### Loop 7: Training Flywheel

```
SENSE:   trajectory_collector reads recent agent execution traces
ACT:     thinkodynamic_scorer scores each trajectory on quality dimensions
         strategy_reinforcer uses UCB1 to select winning patterns
EVALUATE: Compare strategy effectiveness over time
ADAPT:   dataset_builder creates training JSONL for fine-tuning
         Strategy patterns are fed back into agent system prompts
         UCB exploration/exploitation balance shifts based on accumulated evidence
```

**Current state:** No trajectories exist. The flywheel has nothing to spin.

---

### Loop 8: Recognition Loop (Strange Loop / Eigenform)

```
SENSE:   Read cascade history (39 entries in 5 domains)
ACT:     Compute recognition seed — system's self-model
         Run cascade F(S)=S across domains until convergence (eigenform)
EVALUATE: Did the cascade converge? What fitness did each domain reach?
ADAPT:   Write recognition_seed.md to ~/.dharma/meta/
         Update catalytic_graph.json (autocatalytic set detection)
         The recognition seed influences future agent system prompts
```

**Current state:** 39 cascade entries exist (suspicious EIGENFORM convergence). Recognition seed never generated. This loop has historical data but the recognition computation has never been triggered.

---

### Loops 9-13: Dependent Loops

These loops (Conductors, Context Agent, Replication Monitor, Self-Improvement, Free Evolution Grind) all depend on Loop 1 (Swarm Task Loop) working first. They cannot close independently.

---

## Which Loops Close First After Bootstrap

Once Claude Code applies the 9 fixes from INTERFACE_MISMATCH_MAP.md:

**Immediately closeable (Fix 1 alone):**
- Loop 1 (Swarm Task) — agents can reach LLMs, complete tasks, store results
- Loop 2 (Organism Heartbeat) — invariants will have real data to compute

**Closeable after first task completes:**
- Loop 5 (Zeitgeist) — local scanning will find real gate check logs
- Loop 6 (Witness) — will have real agent outputs to audit (after Fix 7)

**Closeable after ~10 tasks complete:**
- Loop 3 (Evolution) — enough fitness data for DarwinEngine to propose mutations
- Loop 4 (Consolidation) — enough shared notes to consolidate
- Loop 7 (Flywheel) — enough trajectories to score and reinforce

**Closeable after ~100 tasks:**
- Loop 8 (Recognition) — enough cascade data for genuine eigenform convergence
- Loops 9-13 (dependent loops) — enough system stability for replication, self-improvement

---

## Verification Checklist

After the bootstrap sprint, run these commands to verify loop closure:

```bash
# Loop 1: Did a task complete?
dgc status  # Tasks Completed > 0

# Loop 2: Did invariants move?
dgc organism-pulse --dry-run  # criticality > 0, closure > 0

# Loop 3: Does evolution have real data?
dgc evolve trend  # fitness entries from real tasks

# Loop 4: Does memory have content?
dgc memory  # memory entries > 0

# Loop 5: Did zeitgeist find signals?
dgc loops  # Check signal bus status

# Loop 6: Did witness produce observations?
ls ~/.dharma/witness/  # witness log files exist

# The acid test: run two consecutive ticks and check if tick 2 is different from tick 1
# If the orchestrator routes differently on tick 2 because of tick 1's outcome,
# the loop is closed.
```

---

*End of Cybernetic Loop Map*
