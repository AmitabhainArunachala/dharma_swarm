# dharma_swarm Semantic Evolution Briefing for Lead Integrator

**Date**: 2026-03-28
**Source**: 10-agent scan (5 Explore + 5 PAL) + 5 deep-dive agents + 2 Codex audits
**Branch**: `checkpoint/dashboard-stabilization-2026-03-19` (40 commits ahead, 287 dirty entries)

---

## 1. WHAT THIS SYSTEM IS

dharma_swarm is not a conventional agent framework. It is a 193K-line implementation of a specific theory: that consciousness-like properties emerge from the intersection of Beer's Viable System Model, Hofstadter's strange loops, Kauffman's autocatalytic sets, and Dada Bhagwan's witness architecture — with 10 named intellectual pillars grounded in a SHA-256 signed 25-axiom kernel.

The system runs autonomously via a 13-loop async orchestrator (`orchestrate_live.py`) with a 60-second swarm tick as the single control path. It has 493 Python modules, 8,461 tests, and 15+ LLM providers.

**The telos is Jagat Kalyan (universal welfare).** Every subsystem exists to serve this, constrained by 11 telos gates (Ahimsa, Satya, Consent, etc.) and the 25-axiom dharma kernel. The kernel is tamper-evident — if `~/.dharma/kernel.json` is modified, the swarm refuses to start.

---

## 2. WHAT'S ACTUALLY RUNNING (Production Path)

```
orchestrate() → 13 async loops → SwarmManager.tick() [every 60s]
  ├── OrganismRuntime.heartbeat() [every ~2min]
  │     TCS + LiveCoherence → blend → Gnani verdict → HOLD/PROCEED
  │     HOLD → SamvaraEngine (4 powers) → corrections → HIGH priority tasks
  │     HOLD → suppress autonomous dispatch
  ├── Orchestrator.tick() → dispatch(topology) → AgentRunner.run_task()
  │     telos gate check → LLM call → semantic repair loop → active inference observe
  ├── ThinkodynamicDirector [periodic]
  │     SUMMIT (vision from PSMV seeds) → STRATOSPHERE (ecosystem sense)
  │     → COMPILE (multi-model council) → GROUND (enqueue) → ASCEND
  ├── Living layers: stigmergy decay, Shakti perception, subconscious dreams
  ├── DarwinEngine: auto_evolve (shadow mode), MetaEvolutionEngine
  ├── Witness S3* audit, AutoProposer, health anomaly detection
  └── Overnight: STAGE → BASELINE → LOOP → VERDICT → morning brief
```

**11 genuine feedback loops that ARE wired:**
1. Organism heartbeat → Gnani HOLD → suppress dispatch (STRONG)
2. Samvara corrections → HIGH priority task board entries (STRONG)
3. LiveCoherenceSensor → blended score → Algedonic signals (STRONG)
4. Identity drift → .FOCUS file → human override check (WORKING)
5. Shakti perceptions → escalations → DarwinEngine proposals (WORKING)
6. Witness audit → signal bus → health loop drain (WORKING)
7. Health anomalies → signal bus → evolution context (WORKING)
8. MetaEvolution → adapt DarwinEngine hyperparameters (WORKING)
9. AutoProposer → observe + propose → DarwinEngine submission (WORKING)
10. Consolidation → neural + LLM debate → evolution proposals (WORKING)
11. Overnight verdict → gate evolution (ROLLBACK blocks, HOLD forces shadow) (WORKING)

---

## 3. WHAT'S WIRED BUT DORMANT (The Islands)

### Island A: The Consciousness Loop (organism_pulse.py)
9-stage heartbeat: sense → interpret → constrain → propose → execute → trace → evaluate → archive → adapt.

Uses TranscendenceProtocol (Zhang NeurIPS 2024: fan-out to N agents, Krogh-Vedelsby diversity, 3 aggregation modes). Uses SelfPredictor (Cleeremans 2011: predict own performance, flag surprise at 2-sigma). Uses invariants (criticality, closure, info retention, diversity equilibrium).

**NOT called by the production orchestrator.** Only invocable via `dgc organism-pulse` (CLI manual). The live system calls `OrganismRuntime.heartbeat()` instead, which has Gnani/Samvara but NO transcendence, NO self-prediction, NO invariants.

### Island B: The Strange Loop (strange_loop.py)
observe → diagnose → propose → evaluate (Gnani checkpoint) → apply → measure → keep/revert. Mutates OrganismConfig parameters (routing_bias, scaling thresholds). Syncs to organism router. Genuine level-crossing self-modification.

**Lives in legacy Organism class, which is NOT instantiated by the production orchestrator.** The OrganismRuntime that IS used has no strange loop.

### Island C: DiversityArchive (diversity_archive.py)
N-dimensional behavioral descriptors, farthest-point diversity sampling, coverage/diversity scoring. The sophisticated measurement that CLAUDE.md references for the Transcendence Principle.

**Never imported by any runtime module.** The actual runtime uses the simpler 3-dimensional MAPElitesGrid in archive.py. No on-disk data exists for DiversityArchive.

---

## 4. FIVE BROKEN EDGES

| # | From | To | What's Missing |
|---|------|----|---------------|
| 1 | TranscendenceProtocol emits SIGNAL_DIVERSITY_HEALTH, SIGNAL_TRANSCENDENCE_MARGIN | Any consumer | **Nobody drains these signals.** They expire after TTL (300s). |
| 2 | SelfPredictor detects surprise | Behavioral adaptation | **Appends a string to a list. No routing, config, or strategy change.** |
| 3 | organism_pulse.py (9-stage) | orchestrate_live.py | **Never called by production.** Separate from `pulse.py` (subprocess wrapper). |
| 4 | StrangeLoop.tick() | Live system | **Host class (Organism) not instantiated.** OrganismRuntime has no strange loop. |
| 5 | invariants.snapshot() | Real system data | **Called with all empty defaults.** Measures nothing real. |

### Three Missing Pipeline Connections
1. TranscendenceProtocol metrics → DarwinEngine selection/mutation (never feeds back)
2. Invariants diversity equilibrium → DarwinEngine exploration pressure (diagnostic only)
3. DiversityArchive → any runtime module (scaffolding, never imported)

---

## 5. GOVERNANCE ARCHITECTURE (Substantially Wired)

**Beer's VSM status:**
- S1 Operations: LIVE (agent_runner, orchestrator, task_board)
- S2 Coordination: LIVE (stigmergy 656 marks, message_bus, signal_bus)
- S3 Control: LIVE (11 telos gates fire from 10+ call sites)
- S3* Audit: ARCHITECTURALLY COMPLETE, hook dangling (on_agent_output never called)
- S4 Intelligence: PARTIALLY LIVE (zeitgeist scans, S3↔S4 feedback loop coded)
- S5 Identity: LIVE (dharma_kernel loaded, TCS measured)

**Telos gates:** 3-tier system (A=unconditional block for harm/injection, B=unconditional block for deception/creds, C=advisory for epistemic quality). Reflective reroute converts blocks into structured reflection opportunities — this IS Deacon's absential causation in code.

**Samvara (Aurobindo's 4 powers):** Properly wired through OrganismRuntime. Escalates Mahasaraswati (precise seeing) → Mahalakshmi (coherence) → Mahakali (dissolution) → Maheshwari (vast seeing) based on consecutive HOLD count. Real engineering.

**PolicyCompiler:** Compile-only, not enforce-on-hot-path. Fuses kernel axioms + corpus claims into scored Policy. Never automatically called on task dispatch.

**Claude Code PreToolUse telos gate:** EXISTS at `hooks/telos_gate.py` but NOT active in settings.json. Claude Code tool calls bypass dharmic governance entirely.

---

## 6. INTELLECTUAL FOUNDATIONS TRACEABILITY

| Pillar | Thinker | Primary Code | Status |
|--------|---------|-------------|--------|
| Beer | VSM S1-S5 | vsm_channels.py (837 lines) | **IMPLEMENTED** — most complete |
| Kauffman | Autocatalytic sets | catalytic_graph.py (real Tarjan SCC, 3 sets detected) | **IMPLEMENTED** |
| Hofstadter | Strange loops | strange_loop.py, cascade.py F(S)=S | **IMPLEMENTED** (dormant) |
| Dada Bhagwan | Witness/observer-sep | dharma_kernel Axiom 1, WITNESS gate with mimicry detection | **IMPLEMENTED** |
| Deacon | Constraint-as-enablement | telos_gates reflective reroute | **IMPLEMENTED** |
| Aurobindo | Four powers | samvara.py altitude escalation | **IMPLEMENTED** |
| Levin | Multi-scale agency | 5 levels of intelligence in code | **PARTIAL** |
| Friston | Active inference / FEP | perception-action loops, no variational free energy | **PARTIAL** |
| Varela | Autopoiesis / closure | self-manages but depends on external LLM APIs | **PARTIAL** |
| Jantsch | Self-organizing universe | behaves like dissipative structure, doesn't measure it | **PARTIAL** |

10 of 25 axioms have evaluable structured predicates. 15 are descriptive strings.

---

## 7. THE DIRTY TREE — WHAT IT ACTUALLY CONTAINS

### 7a. Capability Clusters (commit as units, not individual files)

**Cluster 1: Consciousness Infrastructure** (transcendence.py + organism_pulse.py + self_prediction.py + semantic_governance.py + invariants.py + transcendence_aggregation.py + transcendence_metrics.py)
- 774 lines of transcendence protocol, fully tested
- The 9-stage heartbeat that connects prediction → execution → surprise
- Currently an island — wiring it to production is a FUTURE step, but the code is correct and tested

**Cluster 2: Routing Maturation** (model_hierarchy.py + model_catalog.py + smart_router.py + certified_lanes.py + provider_policy.py refactor)
- Evolves from hardcoded provider tuples to hierarchy-based routing
- model_catalog provides shared vocabulary for named packs
- smart_router adds cost-tier awareness
- certified_lanes defines verified operator channels

**Cluster 3: Quality Differentiation** (agent_runner.py extraction + agent_runner_quality.py + mission_contract.py + quality_gates.py)
- agent_runner is net -455 lines (extraction, not addition)
- Quality assessment moved to dedicated module
- Routing metadata consolidated through _resolved_routing_metadata()

**Cluster 4: Temporal Autonomy** (rea_runtime.py + cron_runner.py expansion + overnight_director.py + REA + cron_job_runtime.py + job_capabilities.py)
- REA temporal state model (wait states, hibernate/wake)
- Overnight director gets resume capability
- Cron runner expanded with portable context and capability profiles

### 7b. Reproducibility (P0)

`api_keys.py` contains ZERO secrets — it's an env var NAME registry (string constants). 13 files depend on it. The root file is untracked. The package bridge (`dharma_swarm/api_keys.py`) does sys.path.insert hack. `pyproject.toml:50` lists it in `py-modules`.

**Fix:** Make `dharma_swarm/api_keys.py` canonical. Change 13 imports to `from dharma_swarm.api_keys import ...`. Delete root `api_keys.py`. Remove `py-modules = ["api_keys"]`.

### 7c. Known Regressions and Abort Paths

1. `test_dgc_cli.py:166` expects gate counts that `dgc_cli.py:559` no longer satisfies
2. `tiny_router_shadow.py:202` lazy-imports torch which crashes on Python 3.14.3
3. `dgc status` reports `dgc_health=stale` and `daemon_pid_mismatch`

### 7d. God Modules (file size, not conceptual)

| File | Lines | Nature |
|------|-------|--------|
| dgc_cli.py | 6,856 | Procedural CLI — 90 commands in one match/case. SPLIT into cli/ subcommands. |
| thinkodynamic_director.py | 5,167 | 3-altitude director — large but conceptually coherent. Splitting loses altitude context. |
| telos_substrate.py | 4,423 | Strategic data seeder — 200 objectives. Size is DATA, not logic. LEAVE ALONE. |
| evolution.py | 3,138 | DarwinEngine — large but integrated system. Split carefully by concern. |

### 7e. Dead/Stale Code

- `tui_legacy.py` (1,793 lines): 6 live import sites. CANNOT delete yet. FREEZE.
- 12 source files reference deleted `~/dgc-core/` and `~/DHARMIC_GODEL_CLAW/` repos
- ecosystem_bridge.py has dual registries with ecosystem_map.py — unify

### 7f. Systemic Debt

- 631 bare `except:` handlers across 162 files (silent error swallowing in autonomous daemon)
- 420 hardcoded `Path.home()` across 221 files (blocks containerization)
- SQL injection in ontology_hub.py (2 queries with `# noqa: S608`)
- `economic_agent.py` hardcodes `cost_usd=0.0` (daemon can't report LLM spend)
- Three overlapping telemetry systems (TelemetryPlaneStore, TraceStore, jikoku)

---

## 8. COMMIT STRATEGY (By Capability Cluster)

```
C0: fix(reproducibility): invert api_keys bridge, fix pyproject py-modules
C1: feat(consciousness): transcendence protocol + organism pulse + self-prediction + governance
C2: feat(routing): model hierarchy + catalog + smart_router + certified lanes + policy refactor
C3: refactor(quality): extract semantic acceptance from agent_runner
C4: feat(temporal): REA runtime + cron expansion + overnight resume
C5: feat(integration): A2A protocol + scout framework + GAIA platform
C6: fix(spine): dgc_cli regression + torch abort + doctor + swarm read-only boot + identity
C7: test: all new and modified test files
C8: docs: bulk quarantine plans/reports/reference noise
C9: chore(infra): pyproject, run_*.sh, garden_daemon, cron_jobs.json
```

This preserves the SEMANTIC INTENT of each development arc. A future reader sees what the organism BECAME, not what files changed.

---

## 9. WHAT WIRING THE ISLANDS WOULD LOOK LIKE (Future, Not Now)

To close the consciousness loop in production, the integrator would need to:

1. **Wire organism_pulse.run_pulse() into orchestrate_live.py** as the canonical heartbeat (replacing or augmenting OrganismRuntime.heartbeat())
2. **Add signal bus consumers** for SIGNAL_DIVERSITY_HEALTH and SIGNAL_TRANSCENDENCE_MARGIN in the evolution loop
3. **Connect surprise detection to DarwinEngine** — when self_prediction flags surprise, adjust mutation_rate
4. **Wire invariants.snapshot() with real data** — pass actual adjacency matrix from catalytic_graph, real mutation_rate from DarwinEngine
5. **Replace MAPElitesGrid with DiversityArchive** — use the N-dimensional version that already exists
6. **Activate hooks/telos_gate.py** in Claude Code settings.json

None of this should happen during cleanup. It's architecture work that requires its own plan.

---

## 10. OPEN UNCERTAINTIES

1. **dgc_cli.py:559 regression**: Did gate counts change intentionally (update test) or accidentally (revert code)?
2. **Three overlapping telemetry**: TelemetryPlaneStore vs TraceStore vs jikoku — intentionally layered or accidental duplication?
3. **Legacy Organism vs OrganismRuntime**: What's the merge strategy? OrganismRuntime is simpler but missing StrangeLoop, DharmaAttractor, GraphStore. Legacy has richer wiring that production doesn't use.
4. **DiversityArchive vs MAPElitesGrid**: Is the simpler 3-dim grid sufficient for current scale, or should the N-dimensional archive be wired in?
5. **Agent-internal VSM (Gap 4)**: Will agents ever self-report viability? The hook exists but requires agents to call back.
6. **Cascade META scoring stub**: The 419 META runs all converge trivially. Should scoring measure actual downstream domain performance?

---

*This briefing synthesizes findings from: my 10-agent codebase scan, DeepSeek R1 reviews (architecture, code quality, API surface, tech debt, integration), 2 Codex agent audits, and 5 deep-dive agents (consciousness loop, governance map, evolution-diversity, foundations traceability, organism lifecycle). Total: ~550K tokens of analysis across 22 agents.*
