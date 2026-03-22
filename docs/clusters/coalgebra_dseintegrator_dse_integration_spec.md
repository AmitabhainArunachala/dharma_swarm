# Coalgebra - Dseintegrator - Dse Integration

## Goal

Ground the existing `DSEIntegrator` runtime in a coalgebra-facing bridge that
is importable as its own cluster artifact. The bridge should let downstream
tools talk about one DSE cycle in terms of coalgebra observation, monadic
observation depth, and sheaf coordination status without reimplementing the
runtime hook itself.

## Design

- Re-export the canonical runtime types from `dharma_swarm.dse_integration`:
  `DSEIntegrator`, `ObservationWindow`, and `CoordinationSnapshot`.
- Define `DSECycleBridge` as the portable artifact for one cycle summary.
- Provide `build_dse_cycle_bridge()` for callers that already have an
  `EvolutionObservation`.
- Provide `build_dse_cycle_bridge_from_cycle()` for callers that start from the
  usual `CycleResult + archive_entries + proposals` tuple.

## Key Invariant

This module is a bridge, not a fork.

It must never duplicate `after_cycle()` or coordination logic from
`dse_integration.py`. The live runtime remains canonical there; this cluster
module only packages its observable seam into a stable import target.

## Expected Behavior

- The module imports cleanly and exposes the canonical DSE runtime types.
- A coalgebra observation can be summarized into one `DSECycleBridge`.
- If a `CoordinationSnapshot` is present, the bridge exposes sheaf-level facts
  such as global truths, productive disagreements, and fixed-point pressure.
- If a caller only has a `CycleResult`, the module can derive the observation by
  delegating to `build_evolution_observation()`.

## Integration

This bridge is suitable for campaign memory, ledger artifacts, and any future
thin adapters that need to serialize the DSE seam in thesis terms:

- `coalgebra`: the current `EvolutionObservation`
- `monad`: observation depth and fixed-point pressure
- `sheaf`: coordination claims and disagreement hints
