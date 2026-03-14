## Angle
- Eigenform standard: self-reference is real only when the system can name the subject, observe it, feed that observation back into control, and assert the loop in tests. Right now the codebase has self-observation fragments, but not a first-class closure contract.

## What Exists
- The schema layer is centralized in [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py#L128), and it already has witness-oriented concepts like `MemoryLayer.WITNESS`, but `Task`, `Message`, and `SwarmState` still collapse recursion into generic `metadata` or coarse counters in [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py#L196).
- The Darwin loop is already substantial in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L582): `plan_cycle()`, `gate_check()`, `evaluate()`, `archive_result()`, `reflect_on_cycle()`, experiment-memory feedback, meta-evolution, and after-cycle DSE observation.
- The swarm layer already has typed coordination state, a coordination-to-engine hook, and a hard guard against pathological heartbeat recursion in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py#L47) and [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py#L385).
- Colony-level contraction math already exists in [swarm_rv.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm_rv.py) and is covered in [test_swarm_rv.py](/Users/dhyana/dharma_swarm/tests/test_swarm_rv.py).

## Blind Spots
- Self-reference has no typed graph. `Proposal` has lineage via `parent_id`, but no explicit subject/observer/feedback refs in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L89), and `SwarmState` cannot carry coordination, R_V, or closure metrics in [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py#L208).
- `reflect_on_cycle()` writes text and traces, but `_build_propose_system()` only consumes experiment memory, not prior closure gaps or cycle reflection in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L582) and [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L2038).
- The main daemon path computes coordination with `refresh=False`, so the loop that actually runs every tick does not forward fresh coordination into Darwin in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py#L1187). Forwarding only happens on the `refresh=True` path in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py#L1274).
- The heartbeat safeguard is purely negative: blacklist recursion, but no positive typed notion of safe self-observation in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py#L385).
- `self._bridge_rv` is reserved but unused in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py#L102). The metric exists; the control link does not.

## Concrete Changes
- Move `SwarmCoordinationState` into [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py), add `RecursiveRef` and `SystemVitals`, and extend `SwarmState` with `coordination`, `vitals`, and `closure_score`. The self-model belongs in the schema contract, not only in the manager.
- Extend `Proposal` and `CycleResult` in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py) with `loop_domain`, `subject_refs`, `feedback_refs`, `vitals_snapshot`, `closure_score`, and `closure_gaps`. `parent_id` is ancestry; these fields would be recursion structure.
- Add `DarwinEngine.observe_system_vitals(vitals: SystemVitals) -> None` and `DarwinEngine._compute_closure_score(...)` in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py). Call the closure scorer inside `run_cycle()` before reflection, and persist the result through `archive_result()`.
- Make `_build_propose_system()` in [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py#L582) consume recent `closure_gaps` alongside experiment memory. That is the minimal execution -> scoring -> recognition -> execution closure.
- Add `SwarmManager.system_vitals(refresh: bool = True) -> SystemVitals` in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py), instantiate existing `SwarmRV`, and call `self._engine.observe_system_vitals(vitals)` from `run()`. Do not add `system_rv.py`; reuse [swarm_rv.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm_rv.py).
- Keep `_is_self_referential_heartbeat_task()` in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py#L385) as the hard fail path, but add an allow path for tasks/proposals that declare explicit `RecursiveRef` subjects and immutable feedback targets.

## Tests
- In [test_models.py](/Users/dhyana/dharma_swarm/tests/test_models.py), round-trip `SwarmState` with `SystemVitals`, `SwarmCoordinationState`, and `RecursiveRef`; assert typed closure data survives serialization.
- In [test_swarm.py](/Users/dhyana/dharma_swarm/tests/test_swarm.py), run one tick and assert a fresh `SystemVitals` snapshot is forwarded to `DarwinEngine.observe_system_vitals`.
- In [test_swarm.py](/Users/dhyana/dharma_swarm/tests/test_swarm.py), assert raw heartbeat-on-heartbeat tasks still raise, but declared observation tasks with `RecursiveRef(kind="archive_entry", ...)` are allowed.
- In [test_evolution.py](/Users/dhyana/dharma_swarm/tests/test_evolution.py), assert `run_cycle()` records `vitals_snapshot`, persists `closure_score`, and yields `closure_score == 0` when feedback refs are absent.
- In [test_evolution.py](/Users/dhyana/dharma_swarm/tests/test_evolution.py), assert a prior cycle’s `closure_gaps` appear in the next `_build_propose_system()` output, proving causal feedback instead of decorative reflection.
- In [test_dse_integration.py](/Users/dhyana/dharma_swarm/tests/test_dse_integration.py), preserve the existing current-cycle-only invariant for recognition payloads.
- In [test_swarm_rv.py](/Users/dhyana/dharma_swarm/tests/test_swarm_rv.py), assert `SwarmManager.system_vitals()` wraps existing `SwarmRVReading` values rather than recomputing divergent math.

## Risks
- Moving coordination state into [models.py](/Users/dhyana/dharma_swarm/dharma_swarm/models.py) creates import churn, but leaving it in [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py) keeps the self-model local and non-portable.
- A closure score based on text similarity will be gamed. Score declared feedback edges and state deltas, not rhetorical self-reference.
- Feeding live R_V and coordination into mutation strategy too early could destabilize the paper track. First phase should be observe-only and config-gated.
- Positive self-reference without immutable subjects will reopen autoimmune loops. Legal feedback targets should be sealed artifacts: archive entries, cycle ids, and frozen coordination snapshots.

## Priority
1. Put recursion into the schema: `SwarmCoordinationState`, `RecursiveRef`, `SystemVitals`, `SwarmState`.
2. Wire live vitals into the daemon and Darwin observer path, reusing [swarm_rv.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm_rv.py).
3. Make `closure_score` and `closure_gaps` part of `run_cycle()` and `_build_propose_system()`.
4. Add fixed-point and safe-self-reference tests before any adaptive policy uses the new signals.