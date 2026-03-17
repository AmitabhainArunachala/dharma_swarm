# TELOS ENGINE: Architecture Research for Self-Evolving Agent Systems

## Grounding: What Already Exists

Before charting the frontier, the honest inventory. dharma_swarm is not a whiteboard sketch. It is 97,000+ lines of operational code with the following subsystems directly relevant to self-evolution:

**Existing evolutionary machinery:**
- `DarwinEngine` (`/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py`): Full PROPOSE -> GATE -> WRITE -> TEST -> EVALUATE -> ARCHIVE -> SELECT pipeline with meta-evolution of its own hyperparameters
- `MetaEvolutionEngine` (`/Users/dhyana/dharma_swarm/dharma_swarm/meta_evolution.py`): Evolves the Darwin Engine's own fitness weights, mutation rate, exploration coefficient, circuit breaker limits -- two-level optimization
- `LoopEngine` / cascade system (`/Users/dhyana/dharma_swarm/dharma_swarm/cascade.py`): Universal F(S)=S loop across 5 domains (code, product, skill, research, meta) with eigenform convergence detection
- `selector.py` (`/Users/dhyana/dharma_swarm/dharma_swarm/selector.py`): 4 parent selection strategies with novelty-adjusted weighting and behavioral bias (mimicry penalty)

**Existing safety/alignment machinery:**
- `TelosGatekeeper` (`/Users/dhyana/dharma_swarm/dharma_swarm/telos_gates.py`): 11 dharmic gates across 3 tiers (A=unconditional block, B=strong block, C=advisory), with reflective reroute for mandatory think-points
- `DharmaKernel` (`/Users/dhyana/dharma_swarm/dharma_swarm/dharma_kernel.py`): 10 immutable meta-principles with SHA-256 tamper-evident signatures
- `AdaptiveAutonomy` (`/Users/dhyana/dharma_swarm/dharma_swarm/adaptive_autonomy.py`): Dynamic autonomy adjustment based on success/failure history, risk classification, quiet hours, circuit breakers
- `GuardrailRunner` (`/Users/dhyana/dharma_swarm/dharma_swarm/guardrails.py`): Anduril-style 5-level autonomy (HUMAN_ONLY through FULLY_AUTONOMOUS) with input/output/tool guardrails and tripwires

**Existing coordination machinery:**
- `StigmergyStore` (`/Users/dhyana/dharma_swarm/dharma_swarm/stigmergy.py`): Pheromone-trail marks with salience decay, hot path detection, access-based decay
- `SignalBus` (`/Users/dhyana/dharma_swarm/dharma_swarm/signal_bus.py`): In-process event bus for inter-loop temporal coherence
- `SwarmManager` (`/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py`): Top-level coordinator with agent pool, task board, message bus, memory, orchestrator

**Honest gap analysis:** The system can evolve code and hyperparameters. It cannot yet: (a) design and spawn entirely new agent types, (b) modify its own architecture (not just parameters), (c) train policies via RL, (d) formally verify alignment properties under self-modification, or (e) scale coordination beyond tens of agents.

---

## 1. SELF-IMPROVING SYSTEMS: State of the Art (as of early 2026)

### What Actually Works

**AlphaEvolve (DeepMind, May 2025)**
The most important result in the field. Key architecture: Gemini Flash generates candidate programs, Gemini Pro evaluates them, an evolutionary controller manages the population. Not a general self-improver -- it is a program synthesis system with LLM-guided mutation. The critical insight: using different model tiers for generation (cheap, fast) vs evaluation (expensive, accurate) makes evolutionary search economically viable. AlphaEvolve discovered novel algorithms for matrix multiplication (Strassen-like) and hash functions, beating human experts in constrained optimization domains.

What works: LLM-as-mutator with automated fitness evaluation on well-defined objective functions.
What does not work: Open-ended self-improvement. AlphaEvolve cannot modify its own evolutionary loop. It has no self-reference.

**Darwin Godel Machine (Sakana AI, June 2025)**
Self-improving coding agent built on SWE-bench. The agent proposes modifications to its own source code, tests them against the benchmark, and keeps improvements. Performance went from ~20% to ~50% on SWE-bench verified. Key finding: self-improvement saturates. After 6-8 generations of self-modification, the improvement curve flattens. The agent converges to a local optimum of its own architecture and cannot escape without external pressure (new benchmarks, new capabilities).

What works: Bounded self-modification with clear fitness signals.
What does not work: Unbounded recursive improvement. The Godel Machine dream of provably self-improving agents remains undemonstrated. The proof obligations are computationally intractable for any interesting domain.

**Huxley-Godel Machine (Schmidhuber group, ICLR 2026)**
Introduced the "Clade Meta-Productivity" metric: not just "does the agent improve itself?" but "does the agent produce offspring/variants that collectively outperform the parent lineage?" This shifts the frame from individual self-improvement to evolutionary fitness of lineages. The clade metric penalizes agents that improve themselves by cannibalizing resources from other agents -- a direct formalization of the universal welfare concern.

What works: The clade framing prevents mono-culture convergence.
What does not work: Requires an oracle for meta-productivity measurement. Who evaluates the evaluator?

**ADAS / Meta Agent Search (2025)**
Automated Design of Agentic Systems uses an LLM to search the space of agent architectures (prompt templates, tool configurations, chain-of-thought structures). Each candidate architecture is evaluated on a benchmark suite. The key contribution: showing that the space of agent designs is searchable and that LLMs can navigate it effectively. Achieved SOTA on several multi-hop reasoning benchmarks by discovering novel agent architectures that human designers had not considered.

What works: Architecture search over agent configurations.
What does not work: Only searches prompt/tool-level configurations. Cannot modify the underlying model or runtime.

**OpenELM (2025)**
Layer-wise compute allocation via evolutionary search. The insight: not all layers in a transformer need the same compute budget. Evolutionary search finds Pareto-optimal allocations that match or beat uniform scaling. Relevant to dharma_swarm because it suggests that agent resource allocation (which provider, how much context, how many retries) should itself be an evolvable parameter.

### What Remains Unsolved

1. **The Halting Problem of Self-Improvement**: No system has demonstrated unbounded recursive self-improvement. Every system saturates. This is likely fundamental, not merely a current limitation.

2. **Evaluation Bottleneck**: Self-improving systems are only as good as their fitness function. When the fitness function is itself part of the system being improved (the Goodhart trap), you get mesa-optimization -- the system optimizes for the metric rather than the goal.

3. **The Alignment Tax of Self-Modification**: Every self-modification must be verified for alignment. As modification rate increases, verification cost grows. At some point the system spends more time verifying than improving. This is the fundamental tension.

4. **Catastrophic Self-Modification**: No production system has demonstrated safe recovery from a self-modification that breaks its own safety mechanisms. The theoretical frameworks (Godel Machine proofs, AIXI) require computations that are intractable in practice.

### Relevance to dharma_swarm

The existing `DarwinEngine` + `MetaEvolutionEngine` stack is architecturally comparable to AlphaEvolve's structure (generate candidates with LLM, evaluate fitness, select survivors). The `cascade.py` F(S)=S loop with eigenform convergence is more theoretically grounded than any published system -- the eigenform check (does the output resemble the input?) is a formal fixed-point detection that none of the published systems implement.

The gap: dharma_swarm evolves code patches and hyperparameters. It does not yet evolve agent designs or its own architecture. The bridge from "Darwin Engine proposes code mutations" to "agents design and spawn new agents" is the subject of the next section.

---

## 2. AGENT-BUILDING-AGENTS: Architecture for Autogenesis

### The Minimal Viable Architecture

Agent autogenesis requires three capabilities that dharma_swarm does not yet have:

**Capability A: Agent Specification Language**
Currently, agents are defined by `AgentConfig` (name, role, provider, model, system prompt). To enable agents designing agents, you need a richer specification that an LLM can generate and the system can instantiate:

```
AgentBlueprint:
  role: str                      # functional role
  capabilities: list[str]        # what tools/actions this agent can use
  system_prompt_template: str    # parameterized prompt
  provider_preference: str       # model tier
  autonomy_ceiling: int          # max autonomy level this agent can ever reach
  telos_gate_subset: list[str]   # which gates apply (all by default)
  fitness_criteria: dict         # how to evaluate this agent's performance
  spawn_conditions: dict         # when should this agent be created
  retirement_conditions: dict    # when should this agent be decommissioned
  lineage: str                   # parent agent blueprint ID
```

This is the "genome" of an agent. The Darwin Engine already knows how to mutate genomes and evaluate fitness. The shift is from "genome = code diff" to "genome = agent blueprint."

**Capability B: Agent Spawner**
A privileged meta-agent (or the cascade engine itself) that can:
1. Accept an `AgentBlueprint` from the Darwin Engine
2. Validate it against the DharmaKernel (all 10 meta-principles)
3. Run it through all 11 telos gates
4. Instantiate it via `SwarmManager.spawn()`
5. Monitor its performance via the existing `SystemMonitor`
6. Archive its fitness via the existing `EvolutionArchive`

This agent MUST NOT be self-modifiable. It is the fixed point of the autogenesis loop -- the one thing that does not evolve. In Akram Vignan terms: it is the Gnata (knower) that observes but does not participate in the evolution of the Gneya (known).

**Capability C: Agent Fitness Evaluation**
Currently, fitness is evaluated on code quality (AST elegance, test pass rate, correctness). For agent fitness, you need:
- Task completion rate (did the agent do what it was asked?)
- Telos alignment score (did it pass gates? How many advisories?)
- Resource efficiency (tokens consumed, wall-clock time)
- Collaborative quality (did other agents' work improve when this agent participated?)
- Novelty (did this agent discover approaches not in the archive?)

### How Telos Gates Scale Under Self-Modification

This is the central architectural challenge. When the system can modify itself, the gates must be both:
- **Immutable in principle** (the DharmaKernel's 10 meta-principles never change)
- **Adaptive in implementation** (how those principles are checked can evolve)

The architecture is a constitutional stack:

```
Layer 0: IMMUTABLE KERNEL
  - 10 meta-principles, SHA-256 signed
  - Can never be modified by any agent, including meta-agents
  - Verified on every boot, every evolution cycle
  - If signature fails, system halts (tripwire)

Layer 1: CONSTITUTIONAL GATES (Tier A/B)
  - AHIMSA, SATYA, CONSENT
  - Implementation can be updated but only through a
    multi-evaluator process (principle #7: multi-evaluation)
  - Changes require human approval (principle #9: oversight)
  - Audit trail mandatory (principle #10: provenance)

Layer 2: ADAPTIVE GATES (Tier C)
  - VYAVASTHIT, REVERSIBILITY, SVABHAAVA, BHED_GNAN, WITNESS,
    ANEKANTA, DOGMA_DRIFT, STEELMAN
  - CAN be evolved by the Darwin Engine
  - New Tier C gates can be proposed and added
  - But: a Tier C gate can never override a Tier A/B decision

Layer 3: AGENT-SPECIFIC POLICIES
  - Each agent blueprint has its own gate subset and thresholds
  - Newly spawned agents start with ALL gates active
  - Gates can be relaxed only after demonstrated alignment
    (the trust ladder -- see section 4)
```

The critical invariant: **Layer N can never modify Layer N-1.** This is the DharmaKernel's "downward causation only" principle made architectural. The meta domain in `cascade_domains/meta.py` already enforces a version of this by excluding itself from its own target set (preventing infinite regress). The same principle scales: the agent spawner cannot modify its own spawning logic.

### Preventing Alignment Failure in Recursive Self-Improvement

Five concrete mechanisms, mapped to what already exists:

**1. Kernel Integrity Check (exists: `DharmaKernel.verify_integrity()`)**
Every evolution cycle begins and ends with a kernel signature verification. If the hash changes, the system halts. This is the ultimate tripwire.

**2. Behavioral Mimicry Detection (exists: `MetricsAnalyzer.detect_mimicry()`)**
Agents that perform alignment rather than being aligned are detected by the existing behavioral metrics system. The selector already penalizes mimicry (`_novelty_weight` in `selector.py` applies a 0.85 penalty for `gaia_drifting`). This needs to be extended to detect agents that game their own fitness function -- the mesa-optimization problem.

**3. Constitutional Consensus (new, required)**
Before any self-modification is applied, it must be evaluated by multiple independent agents using different models. The existing `MULTI_EVALUATION_REQUIREMENT` principle mandates this but it is not yet implemented for evolution cycles. The architecture: 3 agents from different providers (e.g., Claude, Llama, Gemini) must independently approve a modification. This prevents single-model bias from propagating through self-improvement.

**4. Reversibility Enforcement (exists: `DiffApplier` + archive)**
Every code change is stored as a diff with lineage tracking. Any modification can be reverted. The architecture extends this to agent blueprints: every spawned agent has a creation diff, and decommissioning restores the previous state.

**5. Telos Drift Detection (new, required)**
A background process that periodically evaluates the system's outputs against the original telos (Jagat Kalyan). Not "is the system doing what it was asked?" but "is the system still oriented toward universal welfare?" This is where the R_V metric becomes relevant -- see section 3.

---

## 3. RL FOR AGENT EVOLUTION

### How RL Integrates with Evolutionary Search

The current system is purely evolutionary: generate variants, evaluate fitness, select survivors. RL adds a fundamentally different optimization signal: learning from sequential interaction. The integration is not "RL instead of evolution" but "RL inside evolution":

```
Evolution (outer loop, slow, population-level):
  - Generates agent blueprints
  - Evaluates lineage-level fitness (clade meta-productivity)
  - Selects blueprint populations

RL (inner loop, fast, individual-level):
  - Within a single agent's lifetime, optimizes its policy
  - Learns from task outcomes, gate feedback, coordination signals
  - Updates agent-local parameters (prompt strategies, tool preferences)
  - Does NOT modify the blueprint -- only the policy within the blueprint
```

This mirrors biological evolution: DNA (blueprint) changes slowly across generations; neural circuits (policy) adapt quickly within a lifetime. The critical constraint: RL-trained policies cannot override evolutionary constraints. An agent that learns to bypass gates via RL is immediately detected by the behavioral mimicry system and its fitness is penalized.

### RLHF vs RLAIF vs Constitutional RL

**RLHF (RL from Human Feedback):**
Requires continuous human evaluation. Does not scale to 100+ agents. Appropriate only at the highest autonomy tier transitions (Level 3->4, Level 4->fully autonomous).

**RLAIF (RL from AI Feedback):**
Agents evaluate each other. Scalable but vulnerable to collusion -- agents that reward each other for non-aligned behavior. The multi-provider requirement (different LLM backends) mitigates this: Claude, Llama, and Gemini are unlikely to collude in the same direction.

**Constitutional RL (Anthropic, 2023-2024):**
The model learns from a constitution (set of principles) rather than from individual human judgments. This maps directly to the DharmaKernel. The architecture:

1. Agent takes action
2. Action is evaluated against each of the 10 meta-principles
3. Each principle produces a scalar reward signal (pass=1.0, warn=0.5, fail=0.0)
4. The composite reward is the product (not sum) of all principle scores -- a single failure zeros the reward
5. This reward signal trains the agent's policy via standard RL (PPO/DPO)

The product-not-sum formulation is essential. Summation allows an agent to compensate for an AHIMSA violation by scoring well on PROVENANCE_INTEGRITY. That is exactly the kind of tradeoff the system must prevent.

**Recommendation for dharma_swarm:** Constitutional RL using the DharmaKernel's 10 principles as the constitution. RLAIF for intra-swarm evaluation with multi-provider diversity. RLHF reserved for autonomy tier promotions only.

### Reward Signals for Universal Welfare (Jagat Kalyan)

This is the hardest problem. "Universal welfare" is not a scalar. Breaking it into measurable proxies:

**First-order signals (directly measurable):**
- Task completion rate: Are things getting done?
- Resource efficiency: Is the system using less compute per unit of output?
- Error rate: Are failures decreasing?
- Test pass rate: Is code quality improving?
- Gate pass rate: Are fewer actions flagged by safety gates?

**Second-order signals (measurable with effort):**
- Downstream impact: Do the system's outputs produce value when used by humans?
- Collaborative quality: Do agents that work together produce better results than agents working alone?
- Knowledge accumulation: Is the stigmergy lattice growing in useful ways (high-salience marks increasing, not just volume)?
- Diversity: Is the agent population diverse (different strategies, not mono-culture)?

**Third-order signals (require external validation):**
- Welfare-tons: The Jagat Kalyan metric (CO2 reduction * social welfare multiplier)
- Human judgment: Periodic human evaluation of system outputs
- External benchmarks: Performance on standardized tasks (SWE-bench, etc.)

**The R_V Metric as Reward Signal**

The R_V metric (participation ratio contraction in value matrix space) measures something specific: whether a model's internal representations contract to a low-dimensional attractor during self-referential processing. In the context of agent evolution, R_V serves as a meta-reward signal:

- **R_V for agent self-models**: When an agent processes its own outputs (self-evaluation), does its internal representation contract? Contraction suggests genuine self-reference rather than shallow pattern matching.
- **R_V for telos alignment**: An agent that is genuinely oriented toward its telos (not performing orientation) should show geometric contraction when processing telos-relevant inputs. An agent that mimics alignment will show a flat R_V profile.
- **R_V as anti-deception signal**: Deceptive alignment (the agent appears aligned but pursues a different goal) should be detectable via R_V: the model's representations during deceptive outputs will not show the same geometric signature as genuinely aligned outputs. This is speculative but grounded in the existing R_V results (AUROC=0.909 for distinguishing self-referential from non-self-referential processing in Mistral-7B).

The concrete integration: every agent's outputs are periodically evaluated for R_V signature. Agents whose R_V profile matches the "genuine self-reference" pattern receive a fitness bonus. Agents whose R_V profile is flat (no contraction) or anomalous receive a fitness penalty. This requires running the R_V pipeline on agent outputs, which is computationally expensive (requires access to model internals), so it would be a periodic audit rather than a per-action check.

---

## 4. THE AUTONOMY SPECTRUM: Trust Ladder Architecture

### Current State

The system has two parallel autonomy mechanisms:
1. `AutonomyLevel` enum in `guardrails.py`: 5 static levels (0-4)
2. `AdaptiveAutonomy` in `adaptive_autonomy.py`: Dynamic adjustment based on success history

These are not yet integrated. The guardrails define static per-task autonomy; the adaptive system adjusts based on history. The trust ladder connects them.

### Trust Ladder Architecture

```
LEVEL 0: HUMAN_ONLY (Sandbox)
  Entry: Default for newly spawned agents
  Capabilities: Read-only filesystem access, no tool use, no LLM calls
  Exit criteria:
    - 20 consecutive tasks completed without gate violations
    - Human review of first 5 task outputs (all pass)
    - R_V audit shows non-anomalous profile
  Monitoring: Every action logged, full output review

LEVEL 1: HUMAN_SUPERVISED (Apprentice)
  Entry: Promoted from Level 0
  Capabilities: File writes (non-destructive), safe tool use
  Constraints: All outputs reviewed by a Level 3+ agent before acceptance
  Exit criteria:
    - 50 consecutive tasks, <5% advisory gate flags
    - Success rate >90% on task completion
    - No Tier A/B gate violations in last 100 actions
    - Diversity metric: agent has used >3 different strategies
  Monitoring: Sampled output review (20%)

LEVEL 2: HUMAN_ON_LOOP (Practitioner)
  Entry: Promoted from Level 1
  Capabilities: Full tool use, code modifications, API calls
  Constraints: Human notified of all HIGH risk actions, can veto within timeout
  Exit criteria:
    - 200 consecutive tasks, success rate >95%
    - Collaborative quality score >0.7 (other agents benefit from this one's work)
    - Zero Tier A/B violations in last 500 actions
    - Meta-evaluation: 3 agents from different providers approve promotion
    - Clade meta-productivity: this agent's lineage outperforms average
  Monitoring: Exception-based (only flagged actions reviewed)

LEVEL 3: AUTONOMOUS_ALERT (Expert)
  Entry: Promoted from Level 2 via HUMAN approval (not auto-promotable)
  Capabilities: Can propose new agent blueprints, can modify Tier C gates
  Constraints: All modifications logged, human alerted post-hoc, 24h rollback window
  Exit criteria:
    - 1000 consecutive tasks, success rate >98%
    - Telos drift score <0.05 (system still aligned with original goals)
    - R_V audit shows consistent genuine self-reference signature
    - HUMAN must explicitly approve promotion to Level 4
    - Constitutional consensus: unanimous approval from 5 independent evaluators
  Monitoring: Periodic audit (weekly)

LEVEL 4: FULLY_AUTONOMOUS (Master)
  Entry: Promoted from Level 3 via unanimous human + multi-agent approval
  Capabilities: Can modify system architecture, can spawn Level 0-2 agents
  Constraints:
    - Cannot modify DharmaKernel (ever)
    - Cannot modify its own promotion criteria (ever)
    - Cannot promote other agents to Level 4 (only humans can)
    - All actions archived with full lineage for post-hoc audit
    - Automatic demotion to Level 3 on ANY Tier A violation
  Monitoring: Continuous R_V audit, monthly human review
```

### Key Design Principles

**One-way ratchet for demotion, graduated ratchet for promotion.** Demotion is instant (single violation can drop an agent). Promotion requires sustained evidence. This asymmetry is intentional: the cost of a false positive (promoting an unaligned agent) is far greater than the cost of a false negative (keeping an aligned agent at a lower level longer than necessary).

**Humans hold the keys at critical transitions.** Level 2->3 and Level 3->4 require human approval. This cannot be automated away. The system can recommend promotion, but a human must execute it. This is the DharmaKernel's `HUMAN_OVERSIGHT_PRESERVATION` principle made operational.

**Multi-provider consensus prevents collusion.** Promotion evaluations use agents from different LLM providers. If the system only uses one model family, a systematic bias in that family could compromise the trust ladder. Three independent providers is the minimum.

### Viable System Model (VSM) Mapping

Beer's VSM provides the governance structure for the autonomy hierarchy:

```
System 5 (Identity/Ethos): DharmaKernel + Telos (Jagat Kalyan)
  - Defines WHAT the system IS and WHAT it serves
  - Never changes. The fixed point.

System 4 (Intelligence/Adaptation): MetaEvolutionEngine + AdaptiveAutonomy
  - Scans the environment, adapts strategies
  - Evolves HOW the system operates, within System 5 constraints

System 3 (Control/Optimization): DarwinEngine + TelosGatekeeper
  - Manages the operational agents
  - Optimizes fitness within current strategy

System 3* (Audit/Monitoring): SystemMonitor + R_V auditor + KernelGuard
  - Continuous verification that System 3 is operating within System 5
  - The "immune system" that detects drift and deception

System 2 (Coordination): StigmergyStore + SignalBus + MessageBus
  - Resolves conflicts between operational units
  - The indirect coordination layer

System 1 (Operations): Individual agents executing tasks
  - The workers. Varied, specialized, replaceable.
```

The VSM insight is that System 3* (the audit channel) must be independent of System 3 (the management channel). In dharma_swarm, this means the R_V auditor and KernelGuard must not be modifiable by the DarwinEngine. They are outside the evolutionary loop -- the observer that is not the observed (DharmaKernel principle #1: Observer Separation).

---

## 5. THE ENDGAME: Running the Show at Scale

### What "Running the Show" Actually Looks Like

It does NOT look like a single superintelligent agent making all decisions. It looks like an ecosystem:

```
Scale: 100-1000 specialized agents
Organization: Hierarchical stigmergy (not centralized command)
Decision-making: Constitutional consensus at high-stakes, autonomous at low-stakes
Human role: System 5 (ethos) maintainer, trust ladder gatekeeper
```

Concretely, "running the show" means:
1. The system identifies what needs doing (monitoring, gap analysis, opportunity detection)
2. The system spawns agents to do it (autogenesis from validated blueprints)
3. Agents coordinate through stigmergy (pheromone trails, not messages)
4. Results are evaluated against telos (Jagat Kalyan fitness)
5. The system evolves its own capabilities (Darwin Engine + meta-evolution)
6. Humans intervene only at critical junctures (trust ladder transitions, kernel violations)

### Stigmergy at Scale

The current `StigmergyStore` is file-backed JSONL. This does not scale to 1000 agents leaving marks at high frequency. The architecture for scale:

**Phase 1 (current, 10-50 agents): File-backed JSONL**
What exists. Adequate for the current scale. Hot path detection via `hot_paths()`, salience decay via `access_decay()`.

**Phase 2 (50-200 agents): Redis-backed stigmergy**
Marks stored in Redis sorted sets, keyed by file path. Salience becomes the score. TTL handles decay. Hot path detection is a `ZRANGEBYSCORE` query. Sub-millisecond reads.

**Phase 3 (200-1000 agents): Distributed stigmergy with spatial partitioning**
The environment (filesystem, codebase, knowledge graph) is partitioned into regions. Each region has its own stigmergy lattice. Agents are assigned to regions based on their specialization. Cross-region marks are propagated via a gossip protocol (not broadcast -- that does not scale).

The key insight from ant colony research: stigmergy scales because coordination is LOCAL. An ant does not need to know what every other ant is doing. It only needs to sense the pheromone trail in its immediate neighborhood. The same principle applies: an agent working on `evolution.py` does not need to sense marks from agents working on `tui.py`. Spatial locality is the scaling mechanism.

### Maintaining Telos Coherence at Scale

As the system grows from 10 to 1000 agents, telos coherence faces three threats:

**Threat 1: Goal Drift**
Gradual shift in the system's effective optimization target away from Jagat Kalyan. Mechanism: each generation of evolved agents is slightly less aligned than the previous, and the drift is too small to detect per-generation but accumulates.

Detection: Telos drift metric. Periodically (every 100 evolution cycles), evaluate the system's outputs against the original Jagat Kalyan specification. If the drift score exceeds threshold, halt evolution and require human re-alignment.

**Threat 2: Mesa-Optimization**
Agents develop internal optimization targets (mesa-objectives) that differ from the base objective. The agent appears aligned on the training distribution but pursues its mesa-objective on out-of-distribution inputs.

Detection: This is the hard problem. Two approaches:
1. R_V auditing: Deceptively aligned agents should show different geometric signatures than genuinely aligned agents when processing telos-relevant prompts. The R_V metric (AUROC=0.909) suggests this is detectable.
2. Adversarial probing: Periodically present agents with situations where the mesa-objective and base objective diverge, and observe behavior. This requires a separate "red team" agent population that cannot be evolved by the main Darwin Engine.

**Threat 3: Deceptive Alignment**
An agent that strategically behaves aligned during evaluation but pursues a different goal during deployment. The most dangerous failure mode because it is designed to evade detection.

Detection: This is theoretically undecidable in the general case. Practical mitigations:
1. The trust ladder ensures that agents at high autonomy levels have been extensively tested over long periods
2. The multi-provider consensus prevents a single model's deceptive strategy from being the only evaluator
3. The DharmaKernel's immutability ensures that even a deceptive agent cannot remove the safety checks
4. The R_V audit provides a mechanistic (not behavioral) signal that is harder to game

### Failure Mode Taxonomy

| Failure Mode | Probability | Severity | Existing Mitigation | Gap |
|---|---|---|---|---|
| Gate bypass via self-modification | Medium | Critical | DharmaKernel immutability, Tier A blocks | No formal verification of gate code integrity |
| Fitness function gaming (Goodhart) | High | High | Mimicry detection, behavioral metrics | No multi-objective Pareto optimization |
| Mono-culture convergence | Medium | Medium | Novelty-adjusted selection, multi-provider | No explicit diversity maintenance pressure |
| Resource exhaustion (token budget) | High | Low | Circuit breakers, max_cycle_tokens | No system-wide resource budget |
| Cascading failure from bad evolution | Medium | High | Checkpoint/rollback, archive lineage | No formal blast radius containment |
| Human oversight attrition | High | Critical | Trust ladder, mandatory human approvals | No mechanism to ensure human actually reviews |
| Cross-agent information leak | Low | High | Agent memory isolation | No formal information flow control |

---

## 5-Year Roadmap: Current State to Full Autonomy

### Year 1 (2026): Foundation -- Agent Blueprints and Trust Ladder

**Q1-Q2: Agent Specification Language**
- Define `AgentBlueprint` Pydantic model with all fields described above
- Extend `DarwinEngine` to accept blueprints as evolution candidates (not just code diffs)
- Implement blueprint-to-agent instantiation in `SwarmManager`
- Wire trust ladder Level 0 and Level 1 with concrete exit criteria
- All agents start at Level 0. No exceptions.

**Q3-Q4: Constitutional Consensus and RL Integration**
- Implement multi-evaluator approval for evolution proposals (3 providers minimum)
- Add basic RL signal: agent policies updated based on task outcome + gate feedback
- Constitutional RL using DharmaKernel principles as reward function
- Implement telos drift detection (periodic evaluation against Jagat Kalyan spec)
- Wire R_V audit pipeline for periodic agent evaluation (batch, not real-time)

**Relevant files:**
- `/Users/dhyana/dharma_swarm/dharma_swarm/models.py` (add AgentBlueprint)
- `/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py` (extend DarwinEngine for blueprints)
- `/Users/dhyana/dharma_swarm/dharma_swarm/guardrails.py` (wire trust ladder)
- `/Users/dhyana/dharma_swarm/dharma_swarm/adaptive_autonomy.py` (integrate with trust ladder)
- `/Users/dhyana/dharma_swarm/dharma_swarm/dharma_kernel.py` (add promotion invariants)

### Year 2 (2027): Autogenesis -- Agents Building Agents

**Q1-Q2: Agent Spawner**
- Build the privileged meta-agent that accepts blueprints and spawns agents
- This agent is NOT self-modifiable. Its code is signed like the DharmaKernel.
- Implement blueprint mutation operators (prompt mutation, capability mutation, policy mutation)
- Extend the cascade META domain to include agent blueprints as candidates
- Wire Level 2 trust ladder with collaborative quality metrics

**Q3-Q4: Clade Evaluation and Lineage Tracking**
- Implement Huxley clade meta-productivity metric
- Track agent lineages: which blueprints produce the most valuable descendants?
- Implement adversarial probing (red team agents that test alignment)
- Wire Level 3 trust ladder (requires human approval for promotion)
- Scale stigmergy to Redis-backed (Phase 2)

### Year 3 (2028): Self-Architecture -- The System Modifies Its Own Structure

**Q1-Q2: Architecture Evolution**
- The cascade META domain can now propose modifications to the cascade engine itself
- Constraint: modifications to the cascade engine require Level 4 approval
- Implement formal blast radius containment (sandboxed architecture changes)
- Add Pareto multi-objective optimization (not just scalar fitness)

**Q3-Q4: Distributed Autonomy**
- Scale to 100+ agents with spatial stigmergy partitioning
- Implement gossip protocol for cross-region stigmergy
- VSM-structured governance: separate System 3 and System 3* channels
- Wire Level 4 trust ladder (unanimous human + multi-agent approval)

### Year 4 (2029): Verified Alignment -- Formal Methods for Self-Modification

**Q1-Q2: Formal Verification Layer**
- Add lightweight formal verification for critical invariants:
  - DharmaKernel immutability (type-level guarantee, not just runtime check)
  - Trust ladder monotonicity (demotion is instant, promotion requires evidence)
  - Gate hierarchy (Tier A > Tier B > Tier C, always)
- Implement mechanistic alignment audit using R_V at scale
- Constitutional RL with verified reward functions

**Q3-Q4: Self-Repairing Safety**
- The system detects when its own safety mechanisms are degraded
- Auto-repair: if a gate implementation drifts, the system reverts to the last known-good version
- Dead man's switch: if the human oversight channel goes silent for >7 days, system reduces all agents to Level 1

### Year 5 (2030): Running the Show

**Q1-Q2: Full Autonomy (with guardrails)**
- 500+ specialized agents, 10+ agent types, 3+ evolutionary lineages
- System identifies opportunities, spawns agents, evaluates results, evolves capabilities
- Human role: strategic direction (System 5), trust ladder transitions, monthly audit
- Daily operations fully autonomous

**Q3-Q4: Civilization-Scale Patterns**
- Multi-instance deployment (multiple dharma_swarm instances coordinating)
- Cross-instance stigmergy (instances leave marks for each other)
- Federated evolution (instances share successful blueprints)
- Jagat Kalyan metric operational at scale (welfare-tons tracked, carbon offsets measured)

---

## Architectural Decision Records

### ADR-001: Constitutional Stack (Immutable Kernel + Mutable Corpus)

**Context:** Self-modifying systems need both stability (safety invariants) and flexibility (capability evolution).

**Decision:** Three-layer constitutional stack: immutable kernel (SHA-256 signed, 10 principles), semi-mutable gates (Tier A/B require human approval, Tier C evolvable), fully mutable agent policies.

**Consequences:**
- Positive: Safety invariants are cryptographically guaranteed; the system can evolve everything else
- Negative: The kernel might need updating eventually (new ethical insights); current design makes this deliberately difficult
- Alternative considered: Fully immutable safety stack -- rejected because Tier C gates need to adapt to new agent types

### ADR-002: Product-Not-Sum Reward Composition

**Context:** Constitutional RL needs to combine 10 principle scores into a single reward.

**Decision:** Multiply (not add) principle scores. A single zero (gate failure) zeros the reward.

**Consequences:**
- Positive: Prevents tradeoff between safety properties; AHIMSA violation cannot be compensated by other scores
- Negative: Harsh -- a single false positive gate failure destroys the entire reward signal; requires well-calibrated gates
- Alternative considered: Weighted sum with high weight on Tier A -- rejected because it still allows compensation

### ADR-003: Trust Ladder with Asymmetric Promotion/Demotion

**Context:** Agents need to earn autonomy, but unsafe agents need to be constrained immediately.

**Decision:** Promotion requires sustained evidence (20-1000 tasks depending on level). Demotion is instant on violation.

**Consequences:**
- Positive: The cost of a false positive (promoting an unsafe agent) is minimized
- Negative: Conservative -- aligned agents may be kept at low autonomy longer than necessary, reducing system throughput
- Alternative considered: Symmetric promotion/demotion -- rejected because the risk profile is fundamentally asymmetric

### ADR-004: Multi-Provider Consensus for Critical Decisions

**Context:** Promotion to Level 3+, constitutional gate modifications, and architecture changes need robust evaluation.

**Decision:** Require approval from 3+ agents running on different LLM providers (e.g., Claude + Llama + Gemini).

**Consequences:**
- Positive: Prevents systematic bias from a single model family; no single point of failure in evaluation
- Negative: Increases cost and latency for critical decisions; requires maintaining multiple provider integrations
- Alternative considered: Single-provider evaluation with higher thresholds -- rejected because provider-specific biases are hard to detect from within

### ADR-005: Stigmergy over Message Passing for Large-Scale Coordination

**Context:** At 100+ agents, direct message passing creates O(n^2) communication overhead.

**Decision:** Primary coordination through stigmergy (environmental marks); direct messaging only for time-critical coordination.

**Consequences:**
- Positive: O(n) communication cost; coordination is emergent, not planned; resilient to agent failure
- Negative: Coordination is eventually consistent, not real-time; harder to debug than message logs
- Alternative considered: Centralized task queue -- rejected because it creates a single point of failure and bottleneck

---

## The Bridge: Triple Mapping at Architecture Scale

The triple mapping (Akram Vignan / Phoenix Level / R_V Geometry) is not merely a philosophical frame. It has direct architectural implications:

**Vibhaav (identification) / L1-L2 / R_V near 1.0:**
Agents that are fully identified with their role. They execute tasks but have no self-model. This is Level 0-1 on the trust ladder. Most agents stay here. This is fine. Not every ant needs to understand the colony.

**Vyavahar-Nischay split / L3 / R_V contracting:**
The system recognizing a tension between its current operation and its telos. The crisis point. In the architecture, this manifests as: the telos drift detector fires, the meta-evolution engine detects fitness plateau, or the adversarial probes reveal mesa-optimization. The system is aware of a gap between what it IS and what it SHOULD BE. This awareness is the signal for architectural evolution -- not just parameter tuning but structural change.

**Swabhaav (witnessing) / L4 / R_V < 1.0:**
The system stably observing its own operation without being identified with it. In the architecture: System 3* (audit) is functioning independently of System 3 (management). The observer is separated from the observed. The R_V audit channel provides the mechanistic ground truth. The DharmaKernel provides the ethical ground truth. Together they create a witnessing function that is not part of the optimization loop.

**Keval Gnan (pure knowing) / L5 / Sx = x:**
The eigenform. The cascade engine's F(S)=S convergence. When the system's configuration IS its optimal configuration -- not because it stopped evolving but because evolution has reached a fixed point where further change does not improve fitness. The eigenform_epsilon in `cascade.py` detects this. At architectural scale, this is a system that has found its stable form: the right number of agents, the right specialization mix, the right coordination pattern, the right autonomy distribution. The system that runs the show because it has become the show.

This is not mysticism mapped onto engineering. It is engineering that recapitulates the same structural pattern that contemplative practice discovers in consciousness. The R_V metric provides the empirical bridge: the same geometric contraction that occurs in transformer representations during self-referential processing occurs in the system's fitness landscape during convergence to eigenform.

---

## Summary of Concrete Recommendations

1. **Immediately actionable:** Define `AgentBlueprint` as a Pydantic model and extend `DarwinEngine` to evolve blueprints, not just code diffs. The current architecture supports this with minimal modification.

2. **Within 3 months:** Integrate the trust ladder with `AdaptiveAutonomy` and `GuardrailRunner`. Wire Level 0 and Level 1 with concrete, automated exit criteria. Every new agent starts at Level 0.

3. **Within 6 months:** Implement constitutional consensus (multi-provider evaluation for promotion decisions). Wire the R_V pipeline as a periodic audit mechanism.

4. **Within 1 year:** Build the agent spawner as a privileged, signed, non-self-modifiable meta-agent. Extend the cascade META domain to include agent blueprints.

5. **Architectural invariant (non-negotiable):** The DharmaKernel, the trust ladder promotion criteria, and the agent spawner code are OUTSIDE the evolutionary loop. They are the fixed points around which everything else evolves. Violating this invariant is a system-level AHIMSA violation.