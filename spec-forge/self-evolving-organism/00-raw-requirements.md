# Self-Evolving Organism: Raw Requirements

**Date**: 2026-03-26
**Project Root**: `/Users/dhyana/dharma_swarm`
**Consumer**: Same Codex instance that implemented Phases 0-4, but this package is written to remain usable after context loss.
**Target Build Hours**: 16-18 hours of sustained autonomous execution for the remaining phases only.
**Scope**: Continue the canonical build from Phase 5 through Phase 9 without reworking the already-landed seams or introducing a second runtime.

---

## Purpose

Turn the already-landed `dharma_swarm` research organism foundation into a reward-driven, evolvable system that can mutate runtime behavior, evolve workflow topology, generate frontier tasks, export canonical agents cleanly, and emit offline-training artifacts later, all while preserving one runtime, one archive, and one provenance model.

## Current State

The following is already implemented and verified:

- Phase 0: canonicalized docs
- Phase 1: `AutoResearch` contracts and deterministic engine skeleton
- Phase 2: `AutoGrade` contracts and canonical Section 7 scoring engine
- Phase 3: research evaluation registration into the existing runtime truth and archive path
- Phase 4: `AgentRunner` and `workflow.py` integration that emits traces and lineage for research workflows

Verified result at handoff time:

- Focused phase suites are green
- Adjacent seam suites are green
- Combined verification run passed `144` tests

## Functional Requirements

The remaining build shall:

1. add a live optimizer bridge that mutates runtime fields and workflow choices using black-box optimization first
2. connect optimizer output to `RewardSignal` and archive-compatible fitness without bypassing `EvolutionArchive`
3. represent workflow topologies as explicit genomes that compile into executable workflows
4. preserve compatibility with the existing enum-based `TopologyType` path while adding genome support
5. generate `FrontierTask` objects from failures, contradictions, uncertainty, and stale capabilities
6. persist curriculum outputs through existing runtime truth layers instead of creating shadow state
7. expand agent export/install support while preserving pure rendering and explicit side effects
8. add an export-only offline training lane stub for trajectories, grades, and rewards
9. harden the system with research fixtures, golden tests, and adversarial grader tests

## Non-Functional Requirements

- One runtime only. No secondary orchestration center.
- One provenance model only. Traces, lineage, registry, archive.
- One promotion pipeline only. Archive/eval/gates remain canonical.
- Offline training remains export-only. No PPO/DPO/GRPO/LoRA/VERL in the live path.
- Existing dirty files outside the current scope must not be reverted.
- All new work follows strict TDD: failing test first, verify red, minimal code, verify green.

## Constraints

- Preserve and extend the existing seams:
  - `dharma_swarm/agent_export.py`
  - `dharma_swarm/runtime_fields.py`
  - `dharma_swarm/causal_credit.py`
  - `dharma_swarm/agent_runner.py`
  - `dharma_swarm/agent_registry.py`
- Reuse, do not bypass:
  - `dharma_swarm/evolution.py`
  - `dharma_swarm/workflow.py`
  - `dharma_swarm/orchestrator.py`
  - `dharma_swarm/archive.py`
  - `dharma_swarm/evaluator.py`
  - `dharma_swarm/evaluation_registry.py`
  - `dharma_swarm/traces.py`
  - `dharma_swarm/lineage.py`
- Optional optimizer dependencies must be guarded:
  - `nevergrad`
  - `textgrad`

## Explicit Non-Goals

- Do not redesign or replace `AutoResearch` / `AutoGrade`.
- Do not move attribution into tracing capture.
- Do not add model training into runtime execution.
- Do not replace enum topology support with genome-only execution.
- Do not couple export rendering to filesystem installation side effects.
- Do not make archive promotion depend on unstructured heuristics outside `RewardSignal`.

## Integration Points

- `dharma_swarm/evolution.py` is the live improvement loop seam for Phase 5 and Phase 7.
- `dharma_swarm/workflow.py` is the topology compilation and execution seam for Phase 6.
- `dharma_swarm/orchestrator.py` is the dispatch/topology seam for Phase 6.
- `dharma_swarm/agent_export.py` plus new `dharma_swarm/agent_install.py` is the Phase 8 seam.
- `dharma_swarm/archive.py`, `dharma_swarm/evaluator.py`, and `dharma_swarm/evaluation_registry.py` are already reward-aware and must remain canonical.

## Prior Art and Existing Code References

- Canonical execution spec:
  - `docs/plans/2026-03-26-self-evolving-organism-master-build-spec.md`
- Integration RFC:
  - `spec-forge/consciousness-computing/INTEGRATION_SPEC.md`
- Current landed packages:
  - `dharma_swarm/auto_research/`
  - `dharma_swarm/auto_grade/`
- Current phase tests:
  - `tests/test_auto_research_models.py`
  - `tests/test_auto_research_engine.py`
  - `tests/test_auto_grade_models.py`
  - `tests/test_auto_grade_engine.py`
  - `tests/test_research_eval_registry.py`
  - `tests/test_auto_research_workflow.py`
