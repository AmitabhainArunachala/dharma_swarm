# ARCHITECTURE: Self-Evolving Organism Remaining Build

## 1. Current Architecture Snapshot

The live path currently looks like this:

```text
ResearchBrief
  -> AutoResearchEngine
       -> planner
       -> search backend
       -> source normalization
       -> claim extraction
       -> report assembly
  -> AutoGradeEngine
       -> hard gates
       -> weighted score
       -> RewardSignal
  -> EvaluationRegistry.record_research_grade(...)
  -> research_reward_to_fitness(...)
  -> EvolutionArchive
  -> traces + lineage via workflow / agent_runner helpers
```

This is already real. The remaining work extends the loop to:

```text
Research -> Grade -> Register -> Attribute -> Mutate -> Re-run -> Promote / Roll Back
                                        |
                                        +-> generate topology variants
                                        +-> generate frontier tasks
                                        +-> export/install agents
                                        +-> export offline-training bundles
```

## 2. Remaining Layer Map

### Layer 6: Optimizer Bridge

Primary files:

- `dharma_swarm/optimizer_bridge.py`
- `dharma_swarm/optimizers/__init__.py`
- `dharma_swarm/optimizers/nevergrad_bridge.py`
- `dharma_swarm/optimizers/textual_gradient_bridge.py`
- `dharma_swarm/evolution.py`

Responsibilities:

- convert runtime field manifests into optimizable candidates
- apply candidate mutations through `RuntimeFieldRegistry`, not source edits
- evaluate mutated runs via `RewardSignal`
- project reward back into archive-compatible fitness
- rollback cleanly on failure

Constraint:

- `Nevergrad` is the preferred live optimizer
- textual-gradient support is prompt-only and optional
- no scalar autograd loop is the primary optimizer

### Layer 7: Topology Genome

Primary files:

- `dharma_swarm/topology_genome.py`
- `dharma_swarm/workflow.py`
- `dharma_swarm/orchestrator.py`

Responsibilities:

- model planner / researcher / verifier / synthesizer / reviewer graphs
- validate node/edge contracts
- compile genomes into executable workflow definitions
- preserve compatibility with existing `TopologyType`

### Layer 8: Curriculum Engine

Primary files:

- `dharma_swarm/curriculum_engine.py`
- `dharma_swarm/evolution.py`
- `dharma_swarm/agent_registry.py`

Responsibilities:

- turn failures and weak reward signals into new `FrontierTask` proposals
- preserve provenance to seed task/report/contradiction
- persist outputs through existing runtime truth

### Layer 9a: Export / Install Expansion

Primary files:

- `dharma_swarm/agent_export.py`
- `dharma_swarm/agent_install.py`

Responsibilities:

- extend pure renderers without side effects
- add explicit installation planning and execution
- keep conversion and install as separate layers

### Layer 9b: Offline Training Lane Stub

Primary files:

- `dharma_swarm/offline_training_bridge.py`
- `docs/plans/2026-03-26-offline-training-lane.md`

Responsibilities:

- export trajectories, grades, and rewards for future training
- never execute training inside the live runtime

## 3. Integration Principles by Phase

### Phase 5 Integration Principle

Do not make `DarwinEngine` own prompt mutation logic directly. Instead:

1. read runtime field manifests or registries
2. convert them into optimizer candidates
3. apply mutation through runtime field setters
4. run evaluation
5. archive reward / rollback outcome

### Phase 6 Integration Principle

Do not replace `workflow.py`. Compile genomes into `WorkflowDefinition` or a compatible execution shape.

### Phase 7 Integration Principle

Do not create a second task system. `FrontierTask` is a proposal/contract object that must feed existing orchestration and registry pathways.

### Phase 8 Integration Principle

Pure rendering:

- takes a canonical spec
- returns an artifact bundle

Installation:

- takes rendered artifacts
- chooses destinations and overwrite policy
- performs side effects explicitly

### Phase 9 Integration Principle

Offline bridge:

- packages artifacts
- writes manifests
- stops there

## 4. Current Seam Inventory

Already landed seams to preserve:

- `dharma_swarm/agent_export.py`
- `dharma_swarm/runtime_fields.py`
- `dharma_swarm/causal_credit.py`
- `dharma_swarm/agent_runner.py`
- `dharma_swarm/agent_registry.py`
- `dharma_swarm/auto_research/`
- `dharma_swarm/auto_grade/`
- `dharma_swarm/evaluator.py`
- `dharma_swarm/evaluation_registry.py`
- `dharma_swarm/archive.py`
- `dharma_swarm/workflow.py`
- `dharma_swarm/traces.py`
- `dharma_swarm/lineage.py`

## 5. Data Flow Contracts

### Optimizer Trial

```text
runtime field manifest
  -> optimizer candidate
  -> apply mutation
  -> execute run
  -> RewardSignal
  -> research_reward_to_fitness(...)
  -> ArchiveEntry
  -> keep or rollback
```

### Genome Execution

```text
TopologyGenome
  -> validation
  -> compile to WorkflowDefinition-compatible steps
  -> execute
  -> traces / lineage include node_id + edge_id
  -> reward / archive
```

### Curriculum Generation

```text
RewardSignal / contradictions / stale capability evidence
  -> FrontierTask
  -> persisted registry artifact
  -> future execution seed
```

## 6. Honest Risk Map

- Highest risk: Phase 5 can accidentally bypass the runtime-field seam if implemented too quickly.
- Second highest risk: Phase 6 can overcomplicate workflow compilation and become harder to reason about than the workflows themselves.
- Third highest risk: Phase 7 can silently create a second runtime if curriculum outputs are not projected back through canonical stores.
- Lowest risk: Phase 8 and Phase 9, as long as separation boundaries remain explicit.
