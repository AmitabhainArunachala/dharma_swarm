# Strange Loop Master Plan

Date: 2026-03-14
Repo: `/Users/dhyana/dharma_swarm`
Prompt basis: `MEGA_PROMPT_STRANGE_LOOP.md`
Seed basis: user's Strange Loop seed plan
Swarm basis: 10 read-only Codex agent notes in `reports/architectural/strange_loop_swarm_20260314/`

## 1. Eigenform Equation

`F(S) = S`

Concrete meaning in this repo:

- `S` is not only the artifact under evolution. It is the current live system state composed of:
  - evolution/archive state
  - system vitals
  - recognition seed / identity state
  - daemon coordination state
  - catalytic artifact graph
- `F` is not a metaphor. It is the composed transformation:
  - observe
  - gate
  - score
  - archive
  - select
  - regenerate prompts/context
- The loop is structurally closed only when one cycle produces artifacts that become typed inputs to the next cycle.

The minimum eigenform test in `dharma_swarm` is:

1. A cycle produces a typed `recognition_seed` artifact and closure gaps.
2. The next cycle's proposal/context builder consumes those exact artifacts.
3. The system records whether closure improved, plateaued, or diverged.
4. The system can reject recursive self-modification that is rhetorically reflective but structurally ungrounded.

This makes fixed-point behavior testable instead of poetic.

## 2. The Core Correction

The seed plan was directionally right but too greenfield.

The repo already contains much of the substrate:

- universal-loop kernel: `dharma_swarm/evolution.py`
- meta-adaptation: `dharma_swarm/meta_evolution.py`
- mechanistic + system R_V surfaces: `dharma_swarm/rv.py`, `dharma_swarm/bridge.py`, `dharma_swarm/swarm_rv.py`, `dharma_swarm/monitor.py`
- quality forge substrate: `dharma_swarm/foreman.py`, `dharma_swarm/evaluator.py`, `dharma_swarm/elegance.py`, `dharma_swarm/cost_tracker.py`
- recognition/memory substrate: `dharma_swarm/context.py`, `dharma_swarm/sleep_cycle.py`, `dharma_swarm/bootstrap.py`, `dharma_swarm/thinkodynamic_director.py`
- daemon + colony control plane: `dharma_swarm/swarm.py`, `dharma_swarm/orchestrate_live.py`
- artifact topology substrate: `dharma_swarm/semantic_gravity.py`, `dharma_swarm/distiller.py`, `dharma_swarm/workflow.py`, `dharma_swarm/semantic_briefs.py`

So the 5.15a move is not "add five new modules."

It is:

- extract one universal loop from the Darwin engine
- make system vitals first-class
- compile recognition into state
- close the loop through persisted artifacts
- harden the daemon and gate path
- preserve current contracts while adding new ones

## 3. What Not To Build First

Do not start with:

- a new `system_rv.py`
- a new `meta_daemon.py`
- a standalone `quality_forge.py`
- a standalone `catalytic_graph.py`
- replacing `Proposal`, `CycleResult`, or `FitnessScore`
- introducing executor-internal cycles into `workflow.py`

Reason:

- `swarm_rv.py`, `EvolutionRVTracker`, `SystemMonitor`, `Foreman`, `SleepCycle`, `SemanticGravity`, and the current Darwin engine already give the right seams.
- The paper deadline punishes architecture churn more than missing elegance.

## 4. Revised Architecture

### 4.1 Universal Loop Engine

Keep `DarwinEngine` as the public facade.

Inside `dharma_swarm/evolution.py`, factor the existing code path into a domain runner:

```python
class LoopDomain(BaseModel):
    name: str
    artifact_type: str
    executor_mode: str
    selector_strategy: str
    score_axes: list[str]
    feature_coords: list[str] = Field(default_factory=list)
    convergence_threshold: float = 0.0
    mutation_budget: int = 0
    gates: list[str] = Field(default_factory=list)


class LoopResult(BaseModel):
    domain: str
    cycle_id: str
    artifact_refs: list[str] = Field(default_factory=list)
    closure_score: float = 0.0
    closure_gaps: list[str] = Field(default_factory=list)
    stop_reason: str | None = None
    vitals_snapshot: dict[str, Any] = Field(default_factory=dict)


async def run_loop_domain(
    self,
    domain: LoopDomain,
    proposals: list[Proposal],
) -> LoopResult:
    ...
```

Rules:

- `run_cycle()` remains the compatibility path for `code_mutation`.
- `run_cycle_with_sandbox()` becomes an executor mode, not a second loop.
- `MetaEvolutionEngine` evolves domain genomes only after the compatibility path is stable.

### 4.2 Typed Self-Reference

Add additive contracts in `dharma_swarm/models.py`:

```python
class RecursiveRef(BaseModel):
    kind: str
    ref_id: str
    role: str


class SystemVitals(BaseModel):
    system_contraction: dict[str, Any] | None = None
    contraction_source: str | None = None
    contraction_confidence: float = 0.0
    closure_score: float = 0.0
    loop_efficiencies: dict[str, float] = Field(default_factory=dict)
    identity_drift: float = 0.0
    catalytic_priority: float = 0.0
    daemon_health: dict[str, Any] = Field(default_factory=dict)
```

Extend, do not replace:

- `SwarmState`
- `Proposal`
- `CycleResult`

New fields should stay additive:

- `loop_domain`
- `subject_refs`
- `feedback_refs`
- `vitals_snapshot`
- `closure_score`
- `closure_gaps`

### 4.3 System R_V As Vital, Not Myth

Do not add a new R_V stack.

Use:

- `dharma_swarm/swarm_rv.py` for cheap online colony contraction
- `dharma_swarm/rv.py` for tracked cycle-level readings
- `dharma_swarm/bridge.py` for research/evolution correlation
- `dharma_swarm/monitor.py` for health exposure

Plan:

- Promote `SwarmRVReading` into `HealthReport`
- Make `SystemMonitor.check_health()` compute contraction once and surface it directly
- Extend `EvolutionRVTracker` and `EvolutionBridge` so proxy, behavioral, and geometric sources carry explicit provenance
- Reserve expensive `RVMeasurer` runs for sparse offline calibration only

This yields:

- daemon-safe online signal
- paper-safe provenance separation
- no confusion between heuristic contraction and mechanistic R_V

### 4.4 Recognition Seed As Runtime State

The seed plan was right that identity must be active, not documentary.

Implement that by extending existing nightly consolidation:

- `dharma_swarm/sleep_cycle.py`
- `dharma_swarm/bootstrap.py`
- `dharma_swarm/context.py`
- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/prompt_builder.py`

Nightly output:

- `~/.dharma/state/recognition_seed.json`
- `~/.dharma/shared/recognition_seed.md`

Minimum fields:

- `active_thesis`
- `identity_invariants`
- `anti_targets`
- `open_loops`
- `evidence_paths`
- `recognition_signature`
- `identity_drift`
- `last_validated_cycle`

The director should emit structured recognition data, not only `vision_text`.
The context builder should inject a compact S5 block into agent context.
The bootstrap manifest should separate:

- stable identity: "what this system is"
- active S5 state: "what invariants must survive this cycle"

### 4.5 Quality Forge = Foreman + Evaluator + Cost Tracker

The forge already exists in pieces.

Do not add a new phase-1 module.

Extend:

- `dharma_swarm/foreman.py`
- `dharma_swarm/evaluator.py`
- `dharma_swarm/elegance.py`
- `dharma_swarm/cost_tracker.py`
- `dharma_swarm/iteration_depth.py`

New behavior:

- compute `quality_delta`
- compute `quality_gain_per_dollar`
- compute `elegance_delta`
- record `stop_reason`
- self-score generated tasks/build summaries only on meaningful state changes

This makes the forge a real thermodynamic controller instead of a perpetual motion machine.

### 4.6 Catalytic Graph = Extend Semantic Gravity

Keep `workflow.py` acyclic.

The strange loop should close across persisted artifacts and reruns, not by making the executor cyclic.

Extend:

- `dharma_swarm/semantic_gravity.py`
- `dharma_swarm/distiller.py`
- `dharma_swarm/workflow.py`
- `dharma_swarm/semantic_briefs.py`
- `dharma_swarm/ecosystem_index.py`

Add edge types:

- `CATALYZES`
- `REGENERATES`

Add metrics:

- `closure_score()`
- `autocatalytic_cycles()`
- `prioritize_artifacts()`

Closure counts only when a strongly connected component contains:

- discovery artifact
- planning artifact
- execution artifact
- verification artifact
- at least one regeneration edge to a selector artifact

### 4.7 Viable System Closure

Map the existing repo to Beer:

- `S1 Operations`: `SwarmManager`, Darwin code-mutation domain, workflow execution
- `S2 Coordination`: coordination summaries, disagreement synthesis, loop-domain metadata
- `S3 Control`: `SwarmManager.tick()`, budgets, quiet-hours, contribution limits
- `S3* Audit`: `SystemMonitor`, monitor anomalies, contraction, failure accounting
- `S4 Intelligence`: director pulse, semantic gravity, ecosystem retrieval, recognition synthesis
- `S5 Identity`: computed recognition seed + bootstrap identity + telos policy

Critical correction:

- `orchestrate_live.py` must stop bypassing the real swarm control path

The live daemon should center on one `SwarmManager.tick()` control plane.
`orchestrate_live.py` becomes a thin supervisor, not a second brain.

## 5. Immediate Repo Reality Corrections

The swarm found concrete mismatches that the master plan must treat as phase-zero truth:

1. `orchestrate_live.py` currently bypasses much of `SwarmManager.run()` by calling `_orchestrator.tick()` directly.
2. `run_evolution_loop()` reports observability but does not actually run the evolution loop described by its own docstring.
3. `run_evolution_loop()` calls a trend method behind a blanket `except`, which makes future vitals work prone to silent failure.
4. `DOGMA_DRIFT` and `STEELMAN` are effectively decorative in `telos_gates.py`.
5. reflective reroute can self-certify with scaffold language
6. monitor failure accounting misses real rejected/rolled-back mutation states
7. bridge summaries overclaim relative to the current evidence lane

These are not side notes. They are the actual root of the phase order.

## 6. Implementation Order

### Phase 0: Control Truth

Window: 2026-03-14 to 2026-03-16

Goals:

- canonicalize the daemon around one `SwarmManager.tick()` path
- fix PID identity split
- fix `orchestrate_live.py` evolution observability seam
- expose system contraction in `HealthReport`

Files:

- `dharma_swarm/orchestrate_live.py`
- `dharma_swarm/swarm.py`
- `dharma_swarm/monitor.py`
- `dharma_swarm/swarm_rv.py`

Tests:

- new `tests/test_orchestrate_live.py`
- extend `tests/test_swarm.py`
- extend `tests/test_monitor.py`

Why first:

- without this, the system is not alive in the way the plan assumes

### Phase 1: Additive Contracts

Window: 2026-03-16 to 2026-03-18

Goals:

- add `RecursiveRef`, `SystemVitals`, `LoopDomain`, `LoopResult`
- extend `Proposal` and `CycleResult` additively
- add `DarwinEngine.export_system_vitals()`
- make `run_loop_domain(...)` wrap the existing `run_cycle()`

Files:

- `dharma_swarm/models.py`
- `dharma_swarm/evolution.py`
- `dharma_swarm/archive.py`
- `dharma_swarm/selector.py`
- `dharma_swarm/meta_evolution.py`

Tests:

- `tests/test_models.py`
- `tests/test_evolution.py`
- `tests/test_archive.py`
- `tests/test_selector.py`
- `tests/test_meta_evolution.py`

Why second:

- this gives the seed plan its universal-loop skeleton without breaking the existing Darwin surface

### Phase 2: Paper-Safe R_V + Pramana

Window: 2026-03-18 to 2026-03-21

Goals:

- separate proxy vs behavioral vs geometric provenance
- thread evaluator provenance into `ResearchBridge`
- populate inferential fields that the bridge contract already claims
- make summary language paper-safe

Files:

- `dharma_swarm/rv.py`
- `dharma_swarm/bridge.py`
- `dharma_swarm/evaluator.py`
- `dharma_swarm/monitor.py`

Tests:

- `tests/test_bridge.py`
- `tests/test_rv.py`
- `tests/test_monitor.py`

Why before abstract:

- it directly protects the March 26 abstract and March 31 paper from architectural overclaim

### Phase 3: Recognition Closure

Window: 2026-03-21 to 2026-03-24

Goals:

- compile nightly `recognition_seed`
- inject S5 block into context and prompts
- persist identity drift
- make reflection artifacts feed the next cycle

Files:

- `dharma_swarm/sleep_cycle.py`
- `dharma_swarm/bootstrap.py`
- `dharma_swarm/context.py`
- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/prompt_builder.py`
- `dharma_swarm/evolution.py`

Tests:

- `tests/test_sleep_cycle.py`
- `tests/test_context.py`
- `tests/test_prompt_builder.py`
- `tests/test_thinkodynamic_director.py`
- `tests/test_evolution.py`

Why here:

- it closes execution -> recognition -> execution without destabilizing the paper path first

### Phase 4: Thermodynamic Forge + Honest Gates

Window: 2026-03-24 to 2026-03-26

Goals:

- unify quality/cost accounting
- stop plateaued loops
- make `DOGMA_DRIFT` and `STEELMAN` real on mutation paths
- harden diff-content scanning
- fix failure accounting

Files:

- `dharma_swarm/foreman.py`
- `dharma_swarm/evaluator.py`
- `dharma_swarm/cost_tracker.py`
- `dharma_swarm/telos_gates.py`
- `dharma_swarm/dogma_gate.py`
- `dharma_swarm/steelman_gate.py`
- `dharma_swarm/anekanta_gate.py`
- `dharma_swarm/monitor.py`

Tests:

- `tests/test_foreman.py`
- `tests/test_evaluator.py`
- `tests/test_cost_tracker.py`
- `tests/test_telos_gates.py`
- `tests/test_anekanta_gate.py`
- `tests/test_monitor.py`
- `tests/test_evolution.py`

Why before abstract freeze:

- better to see a harsher but honest baseline than a permissive false green bar

### Phase 5: Catalytic Closure

Window: after 2026-03-31 paper submission

Goals:

- extend semantic gravity with catalytic edges
- emit artifact telemetry from workflows
- rank execution briefs by closure contribution and reuse

Files:

- `dharma_swarm/semantic_gravity.py`
- `dharma_swarm/distiller.py`
- `dharma_swarm/workflow.py`
- `dharma_swarm/semantic_briefs.py`
- `dharma_swarm/ecosystem_index.py`

Tests:

- `tests/test_semantic_evolution.py`
- `tests/test_workflow.py`
- `tests/test_distiller.py`
- `tests/test_ecosystem_index.py`
- `tests/test_semantic_briefs.py`

Why after paper:

- it is strategically important but not on the critical path to honest self-measurement or the research deadline

## 7. The Fixed-Point Test Envelope

The plan is not 5.15a unless the tests enforce the topology.

Minimum new assertions:

- a `recognition_seed` artifact is archived and reused next cycle
- `run_loop_domain(code_mutation, ...)` preserves existing Darwin behavior
- `HealthReport` includes system contraction without forcing mechanistic R_V on the hot path
- the daemon uses one canonical tick/control path
- destructive diffs block even when the natural-language action string sounds benign
- scaffold-only reflection does not pass mutation gates
- a closure score is zero when feedback refs are missing
- catalytic closure requires regeneration, not just dense semantic connectivity

## 8. YSD Regrade

The seed plan said "5.14c on paper, 5.15a in execution."

This merged plan is closer to 5.15a because it makes five corrections:

1. it uses the existing Darwin engine as the universal loop seed instead of inventing a second engine
2. it makes system R_V additive and provenance-aware instead of duplicating it
3. it compiles recognition into durable runtime state
4. it treats the daemon/control seam as part of the philosophy, not implementation trivia
5. it keeps executor DAGs acyclic and closes the strange loop across persisted artifacts, which is the correct topology

That is the actual 5.15a move:

- less novelty theater
- more structural self-reference
- more truthful observability
- fewer invented modules
- stronger convergence between philosophy and code

## 9. Open Questions

These are not blockers, but they determine the next implementation turn:

1. Should `SystemVitals` live entirely in `models.py`, or should colony-contraction detail stay in `swarm_rv.py` and only surface as a typed projection?
2. Do you want the phase-0 work to target `orchestrate_live.py` as the canonical daemon entry, or do you want `run_daemon.sh` / `SwarmManager.run()` to remain primary and the supervisor collapsed into that?
3. For the paper window, do you want catalytic closure work fully deferred until after March 31, or only the ranking layer deferred while topology fields land earlier?
