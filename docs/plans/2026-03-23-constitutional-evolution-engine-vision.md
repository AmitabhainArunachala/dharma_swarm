# dharma_swarm Constitutional Evolution Engine

## A Power Spec for Self-Replication, Learning, and Governed Growth

**Date**: 2026-03-23
**Status**: Merge-target architecture (recovered from collapsed Opus 4.6 session)
**Scope**: Self-replication system + trajectory learning layer + daily operational rhythm
**Intent**: Turn dharma_swarm from a capable multi-agent runtime into a bounded, self-specializing, self-improving organism

---

## 1. Core Thesis

dharma_swarm should not merely run agents. It should operate as a living constitutional system that can:

- observe its own performance,
- identify persistent capability gaps,
- create new persistent specialists when justified,
- improve its behavior from accumulated trajectories,
- and remain bounded by explicit governance constraints.

The system already has the beginnings of this architecture. The self-replication path is the real constitutional backbone; the ALE-inspired learning path is the adaptive metabolism. The correct synthesis is not "more autonomy everywhere." It is slow constitutional change, fast behavioral learning, hard population limits, and continuous observability.

This gives dharma_swarm three distinct layers:

1. **Runtime Layer**
   The active organism. Agents execute tasks, coordinate, generate traces, and produce real outcomes.

2. **Constitutional Layer**
   The governance membrane. Consolidation identifies persistent structural gaps; replication materializes only those changes that survive checkpointing, telos review, kernel inheritance, and population control.

3. **Learning Layer**
   The adaptive substrate. Real task trajectories are captured, scored, distilled into strategies, assembled into datasets, and eventually used to improve prompts, routing, and local models.

This hierarchy matters. The runtime acts. The constitutional layer decides what kinds of new persistent actors may exist. The learning layer improves methods within those boundaries. That prevents the organism from flattening into a single unconstrained optimizer.

The best version of dharma_swarm is therefore:

- self-observing through traces, telemetry, witness, and consolidation,
- self-specializing through bounded replication,
- self-improving through trajectory capture and reinforcement,
- self-pruning through apoptosis and culling,
- self-cohering through kernel inheritance and telos gates.

In other words: not just a swarm, but a governed evolving intelligence.

---

## 2. System Architecture

### 2.1 Constitutional Replication

The replication system is the most important structural innovation in the current codebase. It answers the question: how does the organism change its own persistent topology without collapsing into drift?

The answer is a five-stage checkpoint pipeline:

- **G1 Proposal**: validate the proposed role, capability gap, parent, generation, and uniqueness
- **S Assessment**: determine whether the population has room, whether a cull is required, and whether budget conditions allow the birth
- **G2 Gate Check**: verify telos passage and kernel integrity
- **M Materialize**: compose the child spec, register it, add it to the runtime roster, and place it on probation
- **Post-M Probation**: monitor the child under heightened scrutiny until it either graduates or is terminated

This is the right shape. It makes persistent growth expensive, explicit, and reviewable.

The modules already map cleanly to this architecture:

- `dharma_swarm/replication_protocol.py`: checkpointed materialization pipeline
- `dharma_swarm/genome_inheritance.py`: prompt/kernel/gate/memory inheritance
- `dharma_swarm/population_control.py`: population cap, probation, apoptosis, culling
- `dharma_swarm/agent_constitution.py`: static six-agent roster plus dynamic overlay
- `dharma_swarm/consolidation.py`: persistent gap detection and proposal handoff
- `dharma_swarm/orchestrate_live.py`: consolidation and replication monitor loops

This should be treated as the organism's constitutional growth engine.

### 2.2 Learning Through Real Work

The learning side should not be a separate science project. It should metabolize real work already happening in the swarm.

The current shape is promising:

- `dharma_swarm/agent_runner.py` now starts and completes trajectories around real tasks
- `dharma_swarm/trajectory_collector.py` stores those trajectories durably
- `dharma_swarm/thinkodynamic_scorer.py` provides a quality surface
- `dharma_swarm/strategy_reinforcer.py` can extract high-value patterns
- `dharma_swarm/dataset_builder.py` can convert successful work into trainable corpora
- `dharma_swarm/model_registry.py` tracks model generations
- `dharma_swarm/economic_engine.py` and `dharma_swarm/resource_scout.py` provide the first pass of a resource allocator

The correct doctrine is:

- learn from real task execution,
- optimize prompts, routing, strategies, and datasets first,
- promote model generations only when they beat current baselines,
- and keep all of this subordinate to constitutional governance.

That means the organism becomes smarter because it worked, not because it was handed a synthetic objective.

### 2.3 Population as a First-Class Constraint

Most agent systems think only about creation. This system must think equally about birth, graduation, and death.

The hard constraints should remain:

- six founding constitutional agents are immutable,
- total stable population is capped,
- operator and witness are protected,
- new replicated agents are dynamic additions, not rewrites of the founding six,
- any new child must inherit kernel integrity,
- any new child must survive probation,
- any persistently weak child may be culled or apoptosed.

This is not incidental safety polish. It is what makes the organism legible. Without bounded population and explicit removal, every new "specialist" becomes sediment.

The replication system therefore does not just create agents. It manages roster quality over time.

---

## 3. Day-in-the-Life and Merge Strategy

### 3.1 What the System Does in a Day

A healthy day in the finished system looks like this.

**During the day**

- The swarm handles normal tasks.
- Agents run through the existing runtime.
- Every task produces traces and trajectories.
- Telemetry, witness, and health loops accumulate evidence about cost, success, failure, and drift.

**Every few hours**

- Behavioral and operational signals are summarized.
- The system can already see which agents are strong, which are noisy, and which tasks are repeatedly underserved.
- Strategy and routing adaptation can improve method-level performance without changing the constitutional roster.

**At consolidation time**

- The system enters a sleep-like phase through `dharma_swarm/consolidation.py`.
- Two internal perspectives generate a loss report.
- Behavioral corrections are proposed or applied.
- If a capability gap has persisted across cycles, a differentiation proposal is emitted.

**At replication time**

- The replication monitor checks pending proposals.
- The proposal passes through G1, S, G2, and M.
- If population is full, a weak non-protected agent is removed first.
- The child is born as a persistent agent, added to the dynamic roster, and placed on probation.
- The organism has now changed its own long-term structure.

**At learning time**

- The day's successful trajectories are scored.
- High-value strategies are extracted.
- A dataset is assembled from trajectories plus foundations.
- Training experiments can run only if evaluation and budget gates allow them.
- If a model/prompt/policy variant is better, it becomes available to the runtime.

This is the intended loop:

```
work → traces → reflection → specialization → improvement → better work
```

That is the flywheel.

### 3.2 How It Fits the Main Repo

This system fits the repo best if it is treated as an extension of the existing live runtime, not as a parallel stack.

- consolidation and replication belong inside the live orchestrator because they are slow-cycle control-plane functions.
- DynamicRoster belongs in agent_constitution because it extends the constitutional model instead of replacing it.
- GenomeInheritance belongs beside replication because it is not generic agent config; it is birth logic.
- PopulationController belongs beside replication because it governs lifecycle and bounds.
- trajectory_collector belongs in the runtime path because learning data must come from real work.
- strategy_reinforcer, dataset_builder, and model_registry belong in the training flywheel, but only after being bound to actual orchestration.

The key merge principle is: **do not fork the system into "normal swarm" and "experimental self-improver."** The learning and replication systems should sit above and around the existing runtime, not beside it.

### 3.3 What Must Be True Before Merge

For this to be truly merge-ready, five conditions should hold:

1. **Dynamic agents must become first-class runtime citizens**
   Today, dynamic children exist, but some helper paths still assume the constitutional roster is static. That must be resolved so replicated children participate consistently in lookup, worker authority, and runtime enrichment.

2. **Generation semantics must be exact**
   Replication depth should be derived from the actual parent lineage, not soft defaults in proposals. Otherwise drift chains slip through.

3. **Population control must use real fitness**
   "Cull weakest" only means something if the live protocol consults actual composite fitness, not placeholder defaults.

4. **The training flywheel must be real or explicitly deferred**
   A pile of modules is not a loop. Either wire the training flywheel into orchestration and test it, or mark it as deferred and avoid pretending it is active.

5. **The entire system must survive restart**
   Proposals, dynamic roster, genomes, probation state, apoptosis logs, and model lineage must all be durable. In-process signaling is only an acceleration path, never the source of truth.

If these hold, the system becomes something unusually strong: an AI runtime that can grow new persistent specialists for justified reasons, remember why it did so, and later improve how those specialists work.

---

## 4. Dual-Model Tandem Architecture (Opus 4.6 + Codex 5.4)

### The Vision

Opus 4.6 and Codex 5.4 should work in tandem within DGC — not alternating, but operating on two closely coupled lanes with continuous communication.

**Role separation:**
- **Opus 4.6 (via Claude Code)**: Strategic direction, architecture decisions, constitutional changes, telos evaluation, final word on all merges. The brain.
- **Codex 5.4 (via OpenAI Codex)**: Implementation, code review, test coverage, verification, cost-effective parallel execution. The hands that check themselves.

**Communication pattern:**
- Both operate within DGC's orchestration
- Opus manages Codex — sets tasks, reviews output, approves merges
- Codex checks everything Opus produces — finds bugs, tests edge cases, verifies claims
- Neither operates unchecked — mutual oversight as a constitutional requirement
- Opus has final authority but must respond to Codex's challenges

**Implementation path:**
- `dharma_swarm/providers.py` already supports both Anthropic and OpenAI providers
- DGC CLI (`dgc`) can dispatch to either
- Trishula messaging or message_bus for inter-model communication
- Routing policy: Opus for architecture/strategy/review, Codex for implementation/testing/verification
- Both write to shared stigmergy store — see each other's marks

This is not just model routing. It is constitutional separation of powers within the organism.

---

## Final Position

The self-replication system is the constitutional heart. The ALE-style trajectory system is the adaptive metabolism. The correct future is not to choose one over the other. It is to bind them.

The organism should:

- specialize slowly
- learn continuously
- change constitutionally
- stay bounded
- stay observable
- never optimize outside its own governance membrane

And it should do all of this with two model intelligences in tandem — one directing, one verifying — neither operating alone.
