# FILE MAP

## Phase 5: Optimizer Bridge

Primary files to create:

- `dharma_swarm/optimizer_bridge.py`
- `dharma_swarm/optimizers/__init__.py`
- `dharma_swarm/optimizers/nevergrad_bridge.py`
- `dharma_swarm/optimizers/textual_gradient_bridge.py`
- `tests/test_optimizer_bridge.py`
- `tests/test_evolution_runtime_fields.py`

Primary files to modify:

- `dharma_swarm/evolution.py`

Existing supporting seams:

- `dharma_swarm/runtime_fields.py`
- `dharma_swarm/agent_runner.py`
- `dharma_swarm/archive.py`
- `dharma_swarm/evaluator.py`
- `dharma_swarm/auto_grade/models.py`

## Phase 6: Topology Genome

Primary files to create:

- `dharma_swarm/topology_genome.py`
- `tests/test_topology_genome.py`
- `tests/test_topology_execution.py`

Primary files to modify:

- `dharma_swarm/workflow.py`
- `dharma_swarm/orchestrator.py`

Existing supporting seams:

- `dharma_swarm/models.py` (`TopologyType` still exists)
- `dharma_swarm/lineage.py`
- `dharma_swarm/traces.py`

## Phase 7: Curriculum Engine

Primary files to create:

- `dharma_swarm/curriculum_engine.py`
- `tests/test_curriculum_engine.py`

Primary files to modify:

- `dharma_swarm/evolution.py`
- `dharma_swarm/agent_registry.py`

Existing supporting seams:

- `dharma_swarm/auto_grade/models.py`
- `dharma_swarm/evaluation_registry.py`
- `dharma_swarm/archive.py`

## Phase 8: Export / Install Expansion

Primary files to create:

- `dharma_swarm/agent_install.py`
- `tests/test_agent_install.py`

Primary files to modify:

- `dharma_swarm/agent_export.py`
- `tests/test_agent_export.py`

## Phase 9: Offline Training Lane

Primary files to create:

- `dharma_swarm/offline_training_bridge.py`
- `tests/test_offline_training_bridge.py`
- `docs/plans/2026-03-26-offline-training-lane.md`

## Cross-Cutting Hardening

Primary files to create:

- `tests/fixtures/research/good_report.json`
- `tests/fixtures/research/hallucinated_report.json`
- `tests/fixtures/research/contradiction_heavy_report.json`
- `tests/fixtures/research/stale_report.json`

Primary files to modify:

- `tests/test_auto_grade_engine.py`
- additional adversarial tests as needed
