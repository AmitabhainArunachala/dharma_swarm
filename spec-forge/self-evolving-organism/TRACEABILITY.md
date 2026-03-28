# TRACEABILITY: Remaining Build

## Requirement Matrix

| Requirement ID | Requirement | Features |
|---|---|---|
| R-001 | Live optimization shall mutate runtime fields through existing mutation seams, not source-file edits. | `SEO-P5-001` to `SEO-P5-018` |
| R-002 | Optimizer trials shall evaluate through `RewardSignal` and archive-compatible fitness. | `SEO-P5-009` to `SEO-P5-018` |
| R-003 | Workflow topology shall be representable as explicit genome contracts. | `SEO-P6-001` to `SEO-P6-009` |
| R-004 | Genome execution shall compile into the existing workflow runtime and preserve provenance. | `SEO-P6-009` to `SEO-P6-018` |
| R-005 | Curriculum generation shall derive frontier tasks from failures, contradictions, uncertainty, and stale capabilities. | `SEO-P7-001` to `SEO-P7-014` |
| R-006 | Curriculum outputs shall persist through canonical runtime truth instead of a shadow task system. | `SEO-P7-009` to `SEO-P7-014` |
| R-007 | Export rendering shall remain pure while installation remains explicit and side-effectful. | `SEO-P8-001` to `SEO-P8-014` |
| R-008 | Offline training support shall be export-only and never execute training in the live runtime. | `SEO-P9-001` to `SEO-P9-006` |
| R-009 | Research fixtures and adversarial grading tests shall harden the system against weak or fabricated reports. | `SEO-X-001` to `SEO-X-008` |
| R-010 | Remaining work shall preserve one runtime, one archive, one provenance model, and one promotion pipeline. | all features; especially `SEO-P5-*`, `SEO-P6-*`, `SEO-P7-*`, `SEO-P8-*`, `SEO-P9-*` |

## Verification Mapping

| Verification ID | Verification Method | Features |
|---|---|---|
| V-001 | `pytest tests/test_optimizer_bridge.py -q` | `SEO-P5-001` to `SEO-P5-016` |
| V-002 | `pytest tests/test_evolution_runtime_fields.py -q` | `SEO-P5-011` to `SEO-P5-018` |
| V-003 | `pytest tests/test_topology_genome.py -q` | `SEO-P6-001` to `SEO-P6-015` |
| V-004 | `pytest tests/test_topology_execution.py -q` | `SEO-P6-009` to `SEO-P6-018` |
| V-005 | `pytest tests/test_curriculum_engine.py -q` | `SEO-P7-001` to `SEO-P7-012` |
| V-006 | `pytest tests/test_agent_install.py -q` | `SEO-P8-002` to `SEO-P8-014` |
| V-007 | `pytest tests/test_offline_training_bridge.py -q` | `SEO-P9-001` to `SEO-P9-006` |
| V-008 | `pytest tests/test_auto_grade_engine.py -q` plus new fixture-backed tests | `SEO-X-001` to `SEO-X-008` |

## Already-Implemented Requirements

These are satisfied already and are not part of the remaining feature graph:

- canonical research contracts and deterministic report emission
- canonical grading contracts and reward math
- canonical evaluation registration for research reward signals
- canonical workflow trace and lineage emission for research runs

## Scope Control

Any feature that:

- introduces a second runtime
- trains a model in the live path
- bypasses runtime fields
- bypasses archive / evaluation registration
- mixes export and install side effects

is out of spec and must be rejected as divergence, not “creative implementation.”
