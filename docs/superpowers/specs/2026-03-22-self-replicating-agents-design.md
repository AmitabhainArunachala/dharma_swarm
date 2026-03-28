# Self-Replicating Agent Architecture — Design Spec

**Date**: 2026-03-22
**Author**: Dhyana + Claude Opus 4.6
**Status**: Approved
**System**: dharma_swarm

## Problem

dharma_swarm has 6 frozen constitutional agents that can spawn ephemeral workers but cannot create new persistent agents. The consolidation cycle (consolidation.py, 854 lines) can detect capability gaps and propose new agents via `DifferentiationProposal`, but there is no materialization path. Proposals sit in JSON files waiting for manual action. We need agents that can create persistent child agents, with telos alignment preserved across generations.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger | Consolidation-only (24h cycle, 3+ persistent gaps) | Slow, deliberate. Matches biological tight regulation of cell division. |
| Approval | Full auto after all 11 gates pass + kernel SHA-256 | Trust the gates. No human bottleneck. |
| Generations | Max 2 (gen 0 → gen 1 → gen 2, no further) | Conservative drift control. |
| At capacity | Auto-cull lowest-fitness non-protected agent | operator + witness protected. Memory archived. |
| Architecture | Modular — 3 new files + 5 extensions | Clean separation, independently testable. |
| Lifecycle | PersistentAgent (not AgentPool) | Child agents need autonomous wake loops, stigmergy, self-tasking. Conductors set the precedent. |
| Durability | Proposals persisted to JSONL, idempotent processing | Restart/replay must not duplicate or lose births. Signal bus triggers, disk is truth. |

## Critical Engineering Corrections (from code review)

1. **DifferentiationProposal must be extended** — current fields (role/gap/justification/cycles) are insufficient. Must add: `parent_agent`, `generation`, `severity`, `proposed_spec_delta`, `evidence_metadata`, `resource_estimate`.
2. **Child lifecycle = PersistentAgent** — NOT AgentPool. AgentPool agents are passive (orchestrator-dispatched). PersistentAgent agents are autonomous (self-wake, stigmergy-aware, gate-protected). The 2 existing conductors (Claude + Codex) are PersistentAgents — that's the precedent.
3. **DynamicRoster is an overlay** — CONSTITUTIONAL_ROSTER is never mutated. DynamicRoster wraps it.
4. **Loop count is 9, not 8** — orchestrate_live.py currently launches 8 systems (swarm, pulse, recognition, conductors, context-agent, zeitgeist, witness, consolidation). Replication monitor = loop 9.
5. **Proposals must be durable** — CONSOLIDATION_COMPLETE is an in-process signal (signal_bus.py). Replication proposals must also be persisted to `~/.dharma/replication/proposals.jsonl` with status tracking (proposed → in_progress → materialized | failed). Processing is idempotent — a restart re-reads proposals.jsonl, skips already-materialized ones.

## Architecture: Approach B (Modular)

### New Modules

#### 1. `replication_protocol.py` (~500 lines)

Checkpoint sequence mirroring cell cycle:

```
G1: PROPOSAL → S: NEED ASSESSMENT → G2: GATE CHECK → M: MATERIALIZE → POST-M: PROBATION
```

- **G1 PROPOSAL**: Validate DifferentiationProposal, check generation depth (max 2), identify parent agent
- **S NEED ASSESSMENT**: Check population < MAX(8), identify cull candidate if at cap, check daily token budget
- **G2 GATE CHECK**: Run all 11 telos gates on proposed spec, verify kernel SHA-256 inheritance, Anekanta gate (genuinely different from existing agents?)
- **M MATERIALIZE**: Compose child AgentSpec via GenomeInheritance, register via AgentRegistry, add to DynamicRoster, create PersistentAgent, start heartbeat, emit AGENT_REPLICATED signal
- **POST-M PROBATION**: 10 heartbeat cycles with Witness auditing at 2x frequency. Fitness < threshold during probation → apoptosis.

Key class: `ReplicationProtocol.run(proposal) -> ReplicationOutcome`

#### 2. `genome_inheritance.py` (~250 lines)

What a child agent receives:

| Layer | Contents | Mutates? |
|-------|----------|----------|
| KERNEL | 25 MetaPrinciples, SHA-256 | Never |
| GATES | 11 core telos gates | Never |
| PROMPT | Parent's system prompt | Differentiated (role specialization appended) |
| CORPUS | Parent's relevant corpus claims | Filtered copy |
| MEMORY | Parent's archival memory | Selective (domain-filtered) |
| IDENTITY | Name, role, model, schedule | New (generated from gap) |
| STATE | Working memory, fitness | Fresh (starts at zero) |

Key class: `GenomeInheritance.compose_child_spec(parent, proposal) -> (AgentSpec, InitData)`

#### 3. `population_control.py` (~300 lines)

```
MAX_POPULATION = 8
PROTECTED = {"operator", "witness"}
APOPTOSIS_THRESHOLD = 0.2 (fitness, 5 consecutive cycles)
PROBATION_CYCLES = 10
```

Culling algorithm when at capacity:
1. Exclude protected (operator, witness)
2. Exclude agents in probation
3. Select lowest average fitness over last 30 cycles
4. If lowest < 0.4: auto-cull, archive memory, deactivate
5. If all > 0.4: block replication (system is healthy)

Independent apoptosis: fitness < 0.2 for 5 cycles → deactivate, archive, emit AGENT_APOPTOSIS.

Key class: `PopulationController` with `can_add_agent()`, `identify_cull_candidate()`, `trigger_apoptosis()`, `check_probation()`

### Extensions to Existing Modules

#### `agent_constitution.py` — DynamicRoster (~120 lines)

```python
class DynamicRoster:
    _static: dict[str, AgentSpec]   # 6 founding (immutable)
    _dynamic: dict[str, AgentSpec]  # Replicated (persisted to JSON)

    def get_all() -> list[AgentSpec]
    def add(spec: AgentSpec) -> None
    def remove(name: str) -> None
    def is_static(name: str) -> bool
```

Backward-compatible. Existing helpers work without DynamicRoster argument.

#### `config.py` — LiveLoopConfig (~20 lines)

New fields:
- `replication_check_interval_seconds` (default 86400)
- `max_generations` (default 2)
- `probation_cycles` (default 10)
- `apoptosis_fitness_threshold` (default 0.2)
- `apoptosis_cycle_count` (default 5)

#### `consolidation.py` (~30 lines)

Wire DifferentiationProposal → ReplicationProtocol. When proposal exists and all gates pass, proceed through checkpoints automatically.

#### `orchestrate_live.py` (~40 lines)

Add loop 9: `_run_replication_monitor_loop`. Reads `~/.dharma/replication/proposals.jsonl` for durable proposals. Also listens for CONSOLIDATION_COMPLETE signals as a trigger. Idempotent: skips proposals already in `materialized` or `failed` status. New PersistentAgent instances launched as additional asyncio tasks managed by this loop.

#### `models.py` / `signal_bus.py` (~15 lines)

Add signal types: AGENT_REPLICATED, AGENT_APOPTOSIS

### Safety Properties

1. Kernel axioms (SHA-256) inherited immutably — verified at G2
2. All 11 telos gates must pass — any failure blocks replication
3. Max 2 generations — gen 2 has `can_replicate = False`
4. Population hard cap at 8 — auto-cull weakest non-protected
5. Apoptosis at fitness < 0.2 for 5 consecutive cycles
6. Probation (10 cycles) for every new agent
7. Memory archived on deactivation, never deleted
8. operator + witness cannot be culled

### File Summary

| File | Action | Lines Est. |
|------|--------|-----------|
| `dharma_swarm/replication_protocol.py` | CREATE | ~500 |
| `dharma_swarm/genome_inheritance.py` | CREATE | ~250 |
| `dharma_swarm/population_control.py` | CREATE | ~300 |
| `dharma_swarm/agent_constitution.py` | EXTEND | ~120 |
| `dharma_swarm/config.py` | EXTEND | ~20 |
| `dharma_swarm/consolidation.py` | EXTEND | ~30 |
| `dharma_swarm/orchestrate_live.py` | EXTEND | ~40 |
| `dharma_swarm/models.py` + `signal_bus.py` | EXTEND | ~15 |
| `tests/test_replication_protocol.py` | CREATE | ~200 |
| `tests/test_genome_inheritance.py` | CREATE | ~150 |
| `tests/test_population_control.py` | CREATE | ~150 |
| `tests/test_dynamic_roster.py` | CREATE | ~100 |
| **Total** | | **~1,875** |

### Verification Plan

1. All 4300+ existing tests pass
2. New tests: ~600 lines across 4 test files
3. Integration experiment: inject mock capability gap → observe replication → verify kernel inheritance → simulate fitness drop → verify apoptosis
4. 3-generation test: verify gen 2 cannot replicate
5. Capacity test: fill to 8, verify culling, verify protected agents survive
