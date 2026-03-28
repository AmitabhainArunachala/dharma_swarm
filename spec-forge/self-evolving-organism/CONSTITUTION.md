# CONSTITUTION: Self-Evolving Organism Handoff

**Version**: 1.0
**Date**: 2026-03-26
**Status**: Governing build context for remaining Phases 5-9
**Scope**: Continue the canonical build after verified completion of Phases 0-4

---

## I. Project Identity

This project is not a generic research-agent scaffold. It is a continuation of the canonical `dharma_swarm` build defined in `docs/plans/2026-03-26-self-evolving-organism-master-build-spec.md`.

The system already knows:

- what can change: `runtime_fields.py`
- what happened: `traces.py`, `lineage.py`, `evaluation_registry.py`
- what likely mattered: `causal_credit.py`
- how to produce and grade research: `auto_research/`, `auto_grade/`

The remaining work gives it:

- principled runtime optimization
- evolvable topology
- frontier-task generation
- explicit install/export layers
- offline training exports only

## II. Current State Is Real, Not Aspirational

The following work is complete and should be treated as source-of-truth:

- `dharma_swarm/auto_research/` exists and is tested
- `dharma_swarm/auto_grade/` exists and is tested
- `dharma_swarm/evaluator.py` contains `ResearchEvaluator`
- `dharma_swarm/evaluation_registry.py` contains `record_research_grade(...)`
- `dharma_swarm/archive.py` contains `research_reward_to_fitness(...)`
- `dharma_swarm/workflow.py` contains `execute_auto_research_workflow(...)`
- `dharma_swarm/agent_runner.py` contains `run_auto_research_workflow(...)`
- `dharma_swarm/traces.py` and `dharma_swarm/lineage.py` contain AutoResearch-specific helpers

Do not re-scaffold these layers. Extend them.

## III. Non-Negotiable Invariants

1. One runtime only.
2. One archive only.
3. One provenance model only.
4. One promotion pipeline only.
5. Attribution stays post-hoc.
6. Offline training stays export-only.
7. Export rendering stays pure and separate from installation.
8. Strong grading remains upstream of strong optimization.

## IV. Remaining Phase Order

The next agent shall build in this order only:

1. Phase 5: optimizer bridge
2. Phase 6: topology genome
3. Phase 7: curriculum engine
4. Phase 8: expanded export/install adapters
5. Phase 9: offline training lane stubs

Do not start Phase 6 before Phase 5 is minimally real and tested.
Do not start Phase 7 before topology contracts are minimally real and tested.
Do not start Phase 8 before live-runtime work is done.
Do not start Phase 9 before export/install separation is explicit.

## V. Dirty Tree Discipline

The repo is already dirty in unrelated areas. The builder shall:

- read before editing
- never revert unrelated changes
- avoid destructive git commands
- assume uncommitted changes outside the current file set are user-owned

## VI. Build Commands

Primary focused verification commands:

```bash
pytest tests/test_auto_grade_models.py tests/test_auto_grade_engine.py -q
pytest tests/test_research_eval_registry.py -q
pytest tests/test_auto_research_workflow.py -q
```

Broader regression command used at handoff:

```bash
pytest \
  tests/test_auto_research_models.py \
  tests/test_auto_research_engine.py \
  tests/test_auto_grade_models.py \
  tests/test_auto_grade_engine.py \
  tests/test_research_eval_registry.py \
  tests/test_auto_research_workflow.py \
  tests/test_agent_export.py \
  tests/test_runtime_fields.py \
  tests/test_causal_credit.py \
  tests/test_archive.py \
  tests/test_evaluation_registry.py \
  tests/test_agent_runner.py \
  tests/test_agent_registry.py \
  -q
```

## VII. File Routing Table

- `dharma_swarm/optimizer_bridge.py`, `dharma_swarm/optimizers/*`, `dharma_swarm/evolution.py`
  - Phase 5
- `dharma_swarm/topology_genome.py`, `dharma_swarm/workflow.py`, `dharma_swarm/orchestrator.py`
  - Phase 6
- `dharma_swarm/curriculum_engine.py`, `dharma_swarm/evolution.py`, `dharma_swarm/agent_registry.py`
  - Phase 7
- `dharma_swarm/agent_export.py`, `dharma_swarm/agent_install.py`
  - Phase 8
- `dharma_swarm/offline_training_bridge.py`, `docs/plans/2026-03-26-offline-training-lane.md`
  - Phase 9
- `tests/fixtures/research/*`, new `tests/test_*`
  - cross-cutting hardening

## VIII. Known Failure Modes

### F1. Optimizer tries to bypass runtime fields

Bad:
- mutating code files directly as the optimization primitive

Good:
- projecting mutable knobs through `RuntimeFieldRegistry`
- snapshotting before mutation
- rolling back via `reset()`

### F2. Topology genome replaces existing topology enums

Bad:
- breaking `TopologyType` dispatch

Good:
- adding genome compilation alongside the enum path

### F3. Curriculum becomes a second task system

Bad:
- shadow queues, shadow registries, ad hoc task stores

Good:
- `FrontierTask` generation that projects into existing runtime truth and agent-facing pathways

### F4. Install side effects leak into export layer

Bad:
- `render_agent(...)` writing files

Good:
- pure rendering in `agent_export.py`
- explicit side effects in `agent_install.py`

### F5. Offline lane becomes live training

Bad:
- any runtime code that launches PPO/DPO/GRPO/LoRA/VERL jobs

Good:
- export bundle only

## IX. Quality Gates for Completion

A phase is complete only when:

1. new tests fail first, then pass
2. phase-targeted tests pass
3. adjacent seam tests still pass
4. no second runtime was introduced
5. reward math, lineage, and archive behavior remain explainable

## X. Same-Instance Clause

This handoff goes to the same instance lineage, but the builder must behave as if memory could be partial:

- reload current-state docs first
- trust tests over recollection
- trust canonical docs over conversational memory
- do not assume the next phase “must be obvious” because the same instance touched the prior one
