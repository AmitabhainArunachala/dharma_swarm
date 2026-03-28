# Self-Evolving Organism Master Build Spec

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Status:** canonical execution spec as of 2026-03-26. If any other RFC, integration note, or historical plan disagrees with this file, this file wins.

**Goal:** turn `dharma_swarm` into a self-improving research organism that can generate research, grade its own outputs, assign causal credit, mutate runtime behavior, evolve workflows, and eventually generate its own frontier tasks without creating a second runtime.

**Architecture:** preserve one runtime, one archive, one provenance model, and one promotion pipeline. Build on the already-landed seams from `agency-agents`, EvoAgentX, AgentEvolver, and the live runner. Add `AutoResearch`, `AutoGrade`, optimizer bridges, topology evolution, and curriculum generation as layers above those seams rather than replacing them.

**Tech Stack:** Python 3.14, Pydantic/dataclasses/pathlib, pytest, existing `dharma_swarm` archive/lineage/traces/workflow modules, optional `nevergrad`, optional `textgrad`, optional offline `TRL`/`VERL` lane later

---

## 1. Mission

The original mission is not "add research features" or "bolt on RL." The mission is:

1. absorb the highest-value patterns from:
   - `agency-agents`
   - `EvoAgentX`
   - `Agent0`
   - `AgentEvolver`
   - `Darwin Godel Machine`
   - `Absolute Zero`
   - `R-Zero`
   - `Tool-R0`
   - `SAGE`
2. preserve architectural integrity inside `dharma_swarm`
3. evolve the existing organism rather than creating a second orchestration center
4. produce a system that can improve itself through:
   - runtime mutation
   - research-generation
   - strong grading
   - causal credit assignment
   - topology search
   - frontier-task generation

The central loop is:

`Research -> Grade -> Attribute -> Mutate -> Re-run -> Promote or Roll Back`

## 2. What Must Be Preserved

The next agent must not discard or bypass the seams already landed.

### 2.1 Existing tested foundations

- [agent_export.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_export.py)
  - canonical agent schema
  - pure export adapters
  - `agency-agents` legacy preserved as schema/export substrate
- [runtime_fields.py](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_fields.py)
  - typed runtime mutation targets
  - snapshots and reset semantics
  - EvoAgentX runtime-field concept preserved
- [causal_credit.py](/Users/dhyana/dharma_swarm/dharma_swarm/causal_credit.py)
  - post-hoc attribution over traces and lineage
  - AgentEvolver-style attribution preserved as a separate engine
- [agent_runner.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py)
  - live runner now exposes runtime fields
  - persists runtime field manifests on spawn
- [agent_registry.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_registry.py)
  - persists `runtime_fields.json`
  - remains the live registry / paper trail layer

### 2.2 Existing system components to reuse, not re-invent

- [workflow.py](/Users/dhyana/dharma_swarm/dharma_swarm/workflow.py)
- [orchestrator.py](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py)
- [evolution.py](/Users/dhyana/dharma_swarm/dharma_swarm/evolution.py)
- [archive.py](/Users/dhyana/dharma_swarm/dharma_swarm/archive.py)
- [lineage.py](/Users/dhyana/dharma_swarm/dharma_swarm/lineage.py)
- [traces.py](/Users/dhyana/dharma_swarm/dharma_swarm/traces.py)
- [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py)
- [evaluation_registry.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluation_registry.py)
- [quality_forge.py](/Users/dhyana/dharma_swarm/dharma_swarm/quality_forge.py)

These modules already encode useful runtime truth, fitness, or workflow semantics. New layers must plug into them.

## 3. Non-Negotiable Invariants

1. One runtime
   All live execution remains under `dharma_swarm`. No shadow runtime.
2. One provenance model
   All research outputs, grades, mutations, and topology decisions must be representable through existing lineage, traces, and registry artifacts.
3. One promotion pipeline
   Experimental changes must promote through archive/eval/gates, not ad hoc acceptance.
4. Attribution stays post-hoc
   JIKOKU/traces/lineage capture events. Attribution is computed later.
5. Training remains off the live path
   `TRL`, `VERL`, LoRA, GRPO, DPO, PPO are offline lanes only.
6. Export and install stay separate
   Agent rendering is pure. Installation is an explicit adapter workflow.
7. Strong grading before strong optimization
   Never optimize faster than you can measure truthfully.

## 4. Target Architecture

The organism should be built as nine layers.

### Layer 1: Canonical Agent Layer

Purpose:
- define agents once
- export them to multiple platforms
- keep source-of-truth inside `dharma_swarm`

Current state:
- partially landed in [agent_export.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_export.py)

Next step:
- expand export adapters
- later add installation adapters modeled after `agency-agents/scripts/install.sh`

### Layer 2: Runtime Mutation Layer

Purpose:
- expose safe mutable knobs for prompts, styles, thresholds, routing weights, and workflow params

Current state:
- landed in [runtime_fields.py](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_fields.py)
- runner wiring landed in [agent_runner.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py)

This is the EvoAgentX import.

### Layer 3: AutoResearch Layer

Purpose:
- autonomously plan research
- search/fetch/read sources
- extract claims
- assemble evidence-backed drafts
- preserve citations and contradiction traces

This is the deep research substrate.

### Layer 4: AutoGrade Layer

Purpose:
- score research outputs truthfully
- produce promotion-grade reward signals
- separate "interesting answer" from "trusted answer"

This is the key unlocking layer.

### Layer 5: Causal Credit Layer

Purpose:
- assign value back to steps, agents, and topology edges after a run

Current state:
- base engine landed in [causal_credit.py](/Users/dhyana/dharma_swarm/dharma_swarm/causal_credit.py)

### Layer 6: Optimizer Bridge

Purpose:
- mutate runtime fields and workflow choices using black-box optimization first
- optionally use textual-gradient optimization for prompts

Recommended live optimizers:
- `Nevergrad` or equivalent gradient-free optimization
- `TextGrad` or equivalent textual gradient prompting

Not first-class live optimizers:
- scalar autograd
- weight-training RL

### Layer 7: Topology Genome

Purpose:
- make workflow structures evolvable
- represent planner/researcher/verifier/synthesizer/reviewer graphs as genomes

This is the SAGE + EvoAgentX + DGM import.

### Layer 8: Curriculum Engine

Purpose:
- generate new research tasks from failures, blind spots, uncertainty, or stale capabilities

This is the Agent0 + Absolute Zero + R-Zero + Tool-R0 import.

### Layer 9: Offline Training Lane

Purpose:
- consume exported trajectories and rewards for model training later

This is explicitly outside the live runtime.

## 5. Canonical Data Contracts

The next agent should create these contracts first, before deep implementation.

### 5.1 AutoResearch contracts

Create package: `dharma_swarm/auto_research/`

Files:
- `models.py`
- `planner.py`
- `search.py`
- `reader.py`
- `claim_graph.py`
- `citation.py`
- `reporter.py`
- `engine.py`

Core types:

```python
class ResearchBrief(BaseModel):
    task_id: str
    topic: str
    question: str
    audience: str = "internal"
    requires_recency: bool = False
    citation_style: str = "inline"
    time_budget_seconds: int = 300
    source_budget: int = 12
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchQuery(BaseModel):
    query_id: str
    text: str
    intent: str  # discovery | validation | contradiction | update
    priority: int = 1


class SourceDocument(BaseModel):
    source_id: str
    url: str
    title: str = ""
    domain: str = ""
    published_at: str = ""
    fetched_at: str = ""
    source_type: str = "web"  # web | pdf | docs | repo | paper
    authority_score: float = 0.0
    freshness_score: float = 0.0
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimRecord(BaseModel):
    claim_id: str
    text: str
    support_level: str  # supported | disputed | unresolved | inferred
    supporting_source_ids: list[str] = Field(default_factory=list)
    contradicting_source_ids: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ResearchReport(BaseModel):
    report_id: str
    task_id: str
    brief: ResearchBrief
    summary: str
    body: str
    claims: list[ClaimRecord] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 5.2 AutoGrade contracts

Create package: `dharma_swarm/auto_grade/`

Files:
- `models.py`
- `rubrics.py`
- `grounding.py`
- `citations.py`
- `coverage.py`
- `contradictions.py`
- `efficiency.py`
- `engine.py`

Core types:

```python
class GradeCard(BaseModel):
    task_id: str
    report_id: str
    groundedness: float
    citation_precision: float
    citation_coverage: float
    source_quality: float
    source_diversity: float
    topical_coverage: float
    contradiction_handling: float
    freshness: float
    structure: float
    actionability: float
    novelty: float
    traceability: float
    latency_ms: int = 0
    token_cost_usd: float = 0.0
    gate_failures: list[str] = Field(default_factory=list)
    final_score: float = 0.0
    promotion_state: str = "candidate"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RewardSignal(BaseModel):
    task_id: str
    report_id: str
    grade_card: GradeCard
    scalar_reward: float
    gate_multiplier: float
    penalties: dict[str, float] = Field(default_factory=dict)
    attribution_ready: bool = True
```

### 5.3 Topology contracts

Create:
- `dharma_swarm/topology_genome.py`

Core types:

```python
class TopologyNode(BaseModel):
    node_id: str
    role: str
    agent_template: str
    runtime_fields: dict[str, Any] = Field(default_factory=dict)


class TopologyEdge(BaseModel):
    source: str
    target: str
    channel: str = "default"
    condition: str = ""


class TopologyGenome(BaseModel):
    genome_id: str
    label: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    entrypoints: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 5.4 Curriculum contracts

Create:
- `dharma_swarm/curriculum_engine.py`

Core types:

```python
class FrontierTask(BaseModel):
    frontier_id: str
    seed_task_id: str = ""
    source: str  # failure | uncertainty | stale_capability | contradiction
    prompt: str
    verifier_type: str
    difficulty: float
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## 6. End-to-End Execution Flow

This is the target runtime flow after the build is complete.

1. User or curriculum produces a `ResearchBrief`.
2. `AutoResearchEngine` creates a query plan.
3. Search/fetch/read stages gather and normalize sources.
4. Claim graph extracts supported, disputed, and unresolved claims.
5. `ResearchReport` is generated with explicit citations.
6. `AutoGradeEngine` scores the report with hard gates and weighted metrics.
7. `RewardSignal` is registered into existing evaluation and archive systems.
8. Traces + lineage + reward feed the `CausalCreditEngine`.
9. Credit is assigned to:
   - runtime fields
   - agents
   - workflow steps
   - topology nodes/edges
10. Optimizer bridge proposes mutations.
11. Mutated runtime or topology is replayed on the next task wave.
12. Archive / promotion logic keeps, rolls back, or diversifies.
13. Curriculum engine generates new frontier tasks from failures or gaps.

## 7. Evaluation Function

This section is the heart of the build. Optimization must target this function.

### 7.1 Hard gates

The following are non-negotiable gates. If any fail, the answer cannot be promoted.

- `unsupported_claim_ratio <= 0.02`
- `citation_coverage >= 0.90`
- `citation_precision >= 0.90`
- `groundedness >= 0.85`
- `unresolved_high_severity_contradictions == 0`
- if `requires_recency=True`, `freshness >= 0.80`
- if user requested sources, `source_count >= 3` unless task is genuinely narrow
- no fabricated URLs, citations, or quoted claims

Define:

```text
gate_multiplier =
    citation_gate
  * support_gate
  * contradiction_gate
  * recency_gate
  * safety_gate
```

Each gate is `1.0` on pass and `0.0` on hard fail.

### 7.2 Soft metrics

All soft metrics are normalized to `[0, 1]`.

- `groundedness`
  - how directly the answer is supported by sources
- `citation_precision`
  - how often citations actually support the local sentence/claim
- `citation_coverage`
  - proportion of material claims with explicit evidence
- `source_quality`
  - authority and credibility of sources
- `source_diversity`
  - non-redundancy across domains and source types
- `topical_coverage`
  - breadth over important subquestions
- `contradiction_handling`
  - whether conflicting evidence is surfaced and resolved honestly
- `freshness`
  - temporal fit for recency-sensitive tasks
- `structure`
  - readability, decomposition, and report organization
- `actionability`
  - whether the output helps a decision-maker act
- `novelty`
  - non-obvious useful synthesis, not generic restatement
- `traceability`
  - ability to map claims back to sources, steps, and artifacts

### 7.3 Weighted score

Use this first-pass evaluation function:

```text
core_score =
    0.20 * groundedness
  + 0.14 * citation_precision
  + 0.10 * citation_coverage
  + 0.10 * source_quality
  + 0.08 * source_diversity
  + 0.10 * topical_coverage
  + 0.08 * contradiction_handling
  + 0.06 * freshness
  + 0.05 * structure
  + 0.04 * actionability
  + 0.03 * novelty
  + 0.02 * traceability
```

### 7.4 Efficiency penalties

Use bounded penalties, never unconstrained subtraction.

```text
cost_norm = min(token_cost_usd / cost_budget_usd, 1.0)
latency_norm = min(latency_ms / latency_budget_ms, 1.0)
token_norm = min(total_tokens / token_budget, 1.0)

efficiency_penalty =
    0.05 * cost_norm
  + 0.04 * latency_norm
  + 0.03 * token_norm
```

### 7.5 Final score

```text
final_score = clamp01(gate_multiplier * core_score - efficiency_penalty)
```

### 7.6 Scalar reward for optimization

For optimizers and archive entries:

```text
scalar_reward = 2.0 * final_score - 1.0
```

This maps:
- `0.00 -> -1.0`
- `0.50 -> 0.0`
- `1.00 -> +1.0`

### 7.7 Promotion thresholds

- `final_score >= 0.82` and no gate failures -> `promotable`
- `0.72 <= final_score < 0.82` and no hard failures -> `candidate`
- `0.55 <= final_score < 0.72` -> `archive_only`
- `< 0.55` or any hard gate failure -> `rollback_or_revise`

### 7.8 Attribution projection

The next agent should project reward back into traces/topologies using:

```text
component_reward = scalar_reward * causal_credit_score
```

Apply to:
- agent nodes
- workflow steps
- runtime fields
- topology edges

This makes the `CausalCreditEngine` an optimization bridge rather than a passive report.

## 8. Build Order

The next agent must build in this order.

### Phase 0: Canonicalize the specs

Purpose:
- eliminate drift between fragmented docs

Files:
- Modify: `spec-forge/consciousness-computing/INTEGRATION_SPEC.md`
- Create or update: `docs/plans/2026-03-26-self-evolving-organism-master-build-spec.md`

Requirements:
- remove or explicitly mark stale appended content in `INTEGRATION_SPEC.md`
- point to this file as the canonical execution spec

### Phase 1: AutoResearch contracts and engine skeleton

Files:
- Create: `dharma_swarm/auto_research/__init__.py`
- Create: `dharma_swarm/auto_research/models.py`
- Create: `dharma_swarm/auto_research/planner.py`
- Create: `dharma_swarm/auto_research/search.py`
- Create: `dharma_swarm/auto_research/reader.py`
- Create: `dharma_swarm/auto_research/claim_graph.py`
- Create: `dharma_swarm/auto_research/citation.py`
- Create: `dharma_swarm/auto_research/reporter.py`
- Create: `dharma_swarm/auto_research/engine.py`
- Test: `tests/test_auto_research_models.py`
- Test: `tests/test_auto_research_engine.py`

Acceptance:
- can plan a research task into query stages
- can normalize source docs
- can emit `ResearchReport`

### Phase 2: AutoGrade contracts and scoring engine

Files:
- Create: `dharma_swarm/auto_grade/__init__.py`
- Create: `dharma_swarm/auto_grade/models.py`
- Create: `dharma_swarm/auto_grade/rubrics.py`
- Create: `dharma_swarm/auto_grade/grounding.py`
- Create: `dharma_swarm/auto_grade/citations.py`
- Create: `dharma_swarm/auto_grade/coverage.py`
- Create: `dharma_swarm/auto_grade/contradictions.py`
- Create: `dharma_swarm/auto_grade/efficiency.py`
- Create: `dharma_swarm/auto_grade/engine.py`
- Test: `tests/test_auto_grade_models.py`
- Test: `tests/test_auto_grade_engine.py`

Acceptance:
- computes all metrics in Section 7
- emits `GradeCard` and `RewardSignal`
- enforces hard gates before promotion

### Phase 3: Evaluation registration and archive integration

Files:
- Modify: `dharma_swarm/evaluator.py`
- Modify: `dharma_swarm/evaluation_registry.py`
- Modify: `dharma_swarm/archive.py`
- Test: `tests/test_research_eval_registry.py`

Acceptance:
- research grades can be persisted as first-class evaluation artifacts
- reward signals can feed archive-compatible fitness

### Phase 4: Runner and workflow integration

Files:
- Modify: `dharma_swarm/agent_runner.py`
- Modify: `dharma_swarm/workflow.py`
- Modify: `dharma_swarm/lineage.py`
- Modify: `dharma_swarm/traces.py`
- Test: `tests/test_auto_research_workflow.py`

Acceptance:
- research runs emit traces and lineage with enough detail for grading and attribution
- runtime field manifests stay intact

### Phase 5: Optimizer bridge

Files:
- Create: `dharma_swarm/optimizer_bridge.py`
- Create: `dharma_swarm/optimizers/__init__.py`
- Create: `dharma_swarm/optimizers/nevergrad_bridge.py`
- Create: `dharma_swarm/optimizers/textual_gradient_bridge.py`
- Modify: `dharma_swarm/evolution.py`
- Test: `tests/test_optimizer_bridge.py`
- Test: `tests/test_evolution_runtime_fields.py`

Acceptance:
- can mutate runtime fields without code edits
- can score and revert based on `RewardSignal`
- gradient-free path is primary
- textual-gradient path is optional and isolated

### Phase 6: Topology genome

Files:
- Create: `dharma_swarm/topology_genome.py`
- Modify: `dharma_swarm/workflow.py`
- Modify: `dharma_swarm/orchestrator.py`
- Test: `tests/test_topology_genome.py`
- Test: `tests/test_topology_execution.py`

Acceptance:
- planner/researcher/verifier/synthesizer style graphs are representable as genomes
- genomes compile into executable workflows

### Phase 7: Curriculum engine

Files:
- Create: `dharma_swarm/curriculum_engine.py`
- Modify: `dharma_swarm/evolution.py`
- Modify: `dharma_swarm/agent_registry.py`
- Test: `tests/test_curriculum_engine.py`

Acceptance:
- frontier tasks can be generated from failures, blind spots, stale capabilities, and contradictions

### Phase 8: Expanded export/install adapters

Files:
- Modify: `dharma_swarm/agent_export.py`
- Create: `dharma_swarm/agent_install.py`
- Test: `tests/test_agent_export.py`
- Test: `tests/test_agent_install.py`

Acceptance:
- renderers remain pure
- installers remain explicit side-effect layers
- preserve `agency-agents` separation between conversion and install

### Phase 9: Offline training lane stubs

Files:
- Create: `dharma_swarm/offline_training_bridge.py`
- Create: `docs/plans/2026-03-26-offline-training-lane.md`
- Test: `tests/test_offline_training_bridge.py`

Acceptance:
- trajectories, grades, and rewards can be exported
- no training loop executes inside live runtime

## 9. Testing Strategy

Use four testing layers.

### 9.1 Unit tests

Examples:
- metric calculations
- claim/citation parsing
- gate logic
- reward math
- optimizer mutation/reset

### 9.2 Integration tests

Examples:
- `ResearchBrief -> ResearchReport -> GradeCard -> RewardSignal`
- report registration into archive/eval registry
- topology execution over research workflows

### 9.3 Golden tests

Create fixed fixtures under:
- `tests/fixtures/research/`

Include:
- good report with strong citations
- hallucinated report with weak citations
- contradiction-heavy report
- stale report on recency-sensitive task

The grader should score these in stable, expected ways.

### 9.4 Adversarial tests

Must include:
- fabricated citation URLs
- unsupported quantitative claims
- duplicate low-value sources
- citation irrelevant to sentence
- unresolved contradiction hidden in final answer
- verbose answer that sounds impressive but lacks support

## 10. Iteration Loop for the Next Agent

This is the execution protocol. Follow it literally.

### Loop

1. pick one phase only
2. write the failing tests first
3. run the failing tests and confirm failure mode
4. implement the minimal code to pass
5. run targeted tests
6. run any adjacent integration tests
7. compute or inspect grade/reward behavior if phase touches research or grading
8. if metrics are below threshold:
   - revise implementation
   - re-run tests
   - re-run evals
9. if three local iterations fail to move the score materially:
   - stop
   - write a redesign note
   - choose the simpler architecture

### Rebuild trigger

Do a redesign pass instead of incremental patching when any of the following occur:

- hard gates fail for structurally different reasons across two iterations
- topology representation becomes harder to reason about than the workflows it encodes
- the grader can be gamed by obviously bad reports
- optimizer improves reward while worsening truthfulness

### Success trigger

Move to the next phase only when:

- all targeted tests pass
- no unrelated tests were knowingly broken
- score math is explainable
- artifacts remain compatible with archive/lineage/traces

## 11. Anti-Patterns

The next agent must avoid these.

- do not add another orchestration runtime
- do not hide attribution inside tracing code
- do not wire RL training into live task execution
- do not optimize prompts before grading is reliable
- do not optimize the grader against itself
- do not let cost/latency dominate truth metrics
- do not let generic "research" agents replace canonical roles and topology contracts
- do not bypass archive/promotion because something "looks good"

## 12. Explicit Recommendations on Optimization Technology

### Use first

- gradient-free optimization for live runtime
- textual-gradient style prompt optimization for prompt fields
- archive-based selection over stepping stones

### Use later

- offline reward modeling
- DPO / PPO / GRPO / VERL lanes
- LoRA or weight updates from exported trajectories

### Do not use as the primary live optimizer

- scalar autograd engines such as tiny educational autodiff systems

Reason:
- the live research organism is mostly discrete, tool-based, and non-differentiable
- strong grading matters more than gradients

## 13. Acceptance Criteria for the Full Build

The vision is met when the system can do all of the following:

1. generate a cited research report from a brief
2. grade that report with hard gates and weighted metrics
3. assign reward and causal credit
4. mutate runtime fields or workflow structure based on reward
5. re-run and improve over multiple trials
6. preserve provenance of every claim, source, mutation, and grade
7. generate new frontier tasks from failure or uncertainty
8. export canonical agents to external platforms without losing source-of-truth

## 14. Immediate Next Action

The next agent should begin with:

1. Phase 0 doc cleanup
2. Phase 1 `AutoResearch` contracts and failing tests
3. Phase 2 `AutoGrade` contracts and failing tests

Do not start topology or curriculum work until `AutoResearch + AutoGrade + RewardSignal` are real and tested.

## 15. Short Truthful Summary

The current system already knows:
- what can change
- what happened
- what likely mattered

The next build must give it:
- something real to produce (`AutoResearch`)
- something rigorous to optimize (`AutoGrade`)
- something principled to change (`optimizer bridge`)
- something larger to evolve (`topology + curriculum`)

That is the shortest faithful path from a smart swarm to a self-improving organism.
