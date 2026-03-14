## Angle
Treat the Strange Loop work as an additive compatibility layer over the current Darwin and meta-evolution path: preserve `Proposal -> CycleResult -> MetaEvolutionResult` as the stable contract, add universal-loop abstractions as wrappers, and stage daemon rollout only after the live seam is made testable.

## What Exists
- [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py#L128) already defines stable Pydantic contracts with defaults and optional `metadata`; [test_models.py](/Users/dhyana/dharma_swarm/tests/test_models.py#L41) locks those defaults in.
- [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L89) already provides the concrete code-evolution domain via `Proposal`, `CycleResult`, and `EvolutionPlan`; [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L1492) runs the current object-level loop.
- [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L296) and [meta_evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/meta_evolution.py#L18) already expose bounded meta-parameter adaptation; [test_meta_evolution.py](/Users/dhyana/dharma_swarm/tests/test_meta_evolution.py#L231) proves coordination pressure already responds to `rv_trend`, `fitness_trend`, and fixed-point signals.
- [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L764) already forwards coordination summaries into meta-evolution; [test_evolution.py](/Users/dhyana/dharma_swarm/tests/test_evolution.py#L2015) covers that bridge.
- [orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py#L321) already provides the five-loop daemon slot, so rollout should extend it rather than introduce `meta_daemon.py` first.

## Blind Spots
- [orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py#L140) says “Periodic evolution cycles” but, in this file, never calls `run_cycle`; it only reports archive size and trend. Any plan that assumes live self-modification is already running would be overstating the repo.
- [orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py#L164) calls `engine.fitness_trend(window=5)` behind a blanket `except`, while the tested Darwin API here is `await get_fitness_trend(limit=...)` in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L1925). New vitals wiring will otherwise fail silently.
- [test_models.py](/Users/dhyana/dharma_swarm/tests/test_models.py#L119) hard-codes enum counts. Using new enum members to represent loop domains or vitals states will break compatibility immediately.
- [test_evolution.py](/Users/dhyana/dharma_swarm/tests/test_evolution.py#L139) and [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L134) treat `Proposal` and `CycleResult` defaults as stable. Replacing them with `LoopResult` or `ForgeScore` instead of wrapping them expands the regression surface for no early benefit.
- There is no direct coverage for [orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py), so runtime compatibility is currently the least defended part of the migration.

## Concrete Changes
- Phase 1: keep `DarwinEngine.run_cycle(self, proposals)` unchanged and add `DarwinEngine.run_loop_domain(self, domain: LoopDomain, proposals: list[Proposal]) -> LoopResult` in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L1492); `LoopDomain(name="code_mutation")` should delegate to the current `run_cycle` path.
- Phase 1: add `SystemVitals` as an additive model in [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py#L128) and `DarwinEngine.export_system_vitals() -> SystemVitals` in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L296), sourcing only existing observables: `get_fitness_trend`, `last_meta_evolution_result`, `last_coordination_summary`, archive count, and current meta-parameter state.
- Phase 1: incubate domain-specific extras in `Proposal.metadata` and `Task.metadata` rather than adding required fields or new enums to existing contracts.
- Phase 2: do not create `meta_daemon.py`. Extend [orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py#L140) so `run_evolution_loop` uses `await engine.get_fitness_trend(limit=5)` and logs `export_system_vitals()` behind a flag such as `DGC_ENABLE_SYSTEM_VITALS=1`.
- Phase 2: keep `MetaEvolutionEngine.observe_coordination_summary(...)` in [meta_evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/meta_evolution.py#L143) as the only adaptation ingress; feed system-level R_V through the existing keys `rv_trend`, `fitness_trend`, `approaching_fixed_point`, and `observation_count` instead of inventing a second control path.
- Phase 3: if `ForgeScore` is needed, make it additive beside `LoopResult` and derived from existing fitness outputs; do not replace `FitnessScore` or `CycleResult.best_fitness` during the paper window.
- Phase 3: defer any separate `quality_forge.py`, `catalytic_graph.py`, or domain-general engine extraction until at least one non-code domain exists and the adapter path has soaked without disrupting the current repo.

## Tests
- Preserve the current contract suite unchanged: [test_models.py](/Users/dhyana/dharma_swarm/tests/test_models.py), [test_evolution.py](/Users/dhyana/dharma_swarm/tests/test_evolution.py), and [test_meta_evolution.py](/Users/dhyana/dharma_swarm/tests/test_meta_evolution.py).
- Add model tests in [test_models.py](/Users/dhyana/dharma_swarm/tests/test_models.py) for `SystemVitals` defaults and JSON round-trip only; leave the existing enum-count assertions untouched.
- Add Darwin adapter tests in [test_evolution.py](/Users/dhyana/dharma_swarm/tests/test_evolution.py) proving `run_loop_domain(code_mutation, proposals)` delegates to `run_cycle`, and `export_system_vitals()` reflects `last_meta_evolution_result` and `last_coordination_summary` without mutating `CycleResult`.
- Extend [test_meta_evolution.py](/Users/dhyana/dharma_swarm/tests/test_meta_evolution.py#L296) with a case showing a `SystemVitals.model_dump()`-backed summary changes coordination pressure only through the existing keys and still respects bounded updates.
- Add [test_orchestrate_live.py](/Users/dhyana/dharma_swarm/tests/test_orchestrate_live.py) as the one justified new test file: cover `run_evolution_loop` using `get_fitness_trend(limit=5)`, feature-flagged vitals logging, and non-silent happy-path behavior.

## Risks
- The highest regression risk is contract drift in [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py#L128) and [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L89); new required fields or enum members will break broad existing coverage.
- A parallel universal-loop runner or `meta_daemon.py` would bypass [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L731) and [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L764), which already handle bounded meta-adaptation and coordination forwarding.
- Shipping system-level R_V through the daemon before fixing [orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py#L164) risks a silent no-op because the current trend call is not aligned with the tested Darwin API.
- The paper-safe path is additive: consume R_V-related summaries in meta-evolution, but do not rework object-level evaluation or archive semantics before 2026-03-26 and 2026-03-31.

## Priority
1. Keep `Proposal`, `CycleResult`, `run_cycle`, and existing enums untouched.
2. Fix and test the live evolution observability seam in [orchestrate_live.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrate_live.py).
3. Add `SystemVitals` and `run_loop_domain(...)` as wrappers over the current Darwin engine.
4. Feed system-level R_V into the existing meta-evolution summary path and prove it with tests.
5. Only then decide whether `quality_forge.py` or `catalytic_graph.py` is warranted by a second domain or real daemon usage.