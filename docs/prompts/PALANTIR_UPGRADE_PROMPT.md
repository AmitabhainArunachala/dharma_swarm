---
title: PALANTIR-GRADE UPGRADE — Master Strategic Prompt
path: docs/prompts/PALANTIR_UPGRADE_PROMPT.md
slug: palantir-grade-upgrade-master-strategic-prompt
doc_type: note
status: active
summary: 'For : 1M-context Claude session (Opus) or Codex deep-work task Purpose : Upgrade dharma swarm from research prototype to Palantir-level execution clarity Author : Dhyana + Claude Opus 4.6 | Date : 2026-03-14'
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - CLAUDE.md
  - dharma_swarm/ontology.py
  - dharma_swarm/logic_layer.py
  - dharma_swarm/lineage.py
  - dharma_swarm/workflow.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- swarm_intelligence
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
inspiration:
- stigmergy
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- dharma_swarm/ontology.py
- dharma_swarm/logic_layer.py
- dharma_swarm/lineage.py
- dharma_swarm/workflow.py
- dharma_swarm/api.py
connected_python_modules:
- dharma_swarm.ontology
- dharma_swarm.logic_layer
- dharma_swarm.lineage
- dharma_swarm.workflow
- dharma_swarm.api
connected_relevant_files:
- CLAUDE.md
- dharma_swarm/ontology.py
- dharma_swarm/logic_layer.py
- dharma_swarm/lineage.py
- dharma_swarm/workflow.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: docs/prompts/PALANTIR_UPGRADE_PROMPT.md
  retrieval_terms:
  - palantir
  - upgrade
  - prompt
  - grade
  - master
  - strategic
  - context
  - claude
  - session
  - opus
  - codex
  - deep
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: 'For : 1M-context Claude session (Opus) or Codex deep-work task Purpose : Upgrade dharma swarm from research prototype to Palantir-level execution clarity Author : Dhyana + Claude Opus 4.6 | Date : 2026-03-14'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/prompts/PALANTIR_UPGRADE_PROMPT.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# PALANTIR-GRADE UPGRADE — Master Strategic Prompt

**For**: 1M-context Claude session (Opus) or Codex deep-work task
**Purpose**: Upgrade dharma_swarm from research prototype to Palantir-level execution clarity
**Author**: Dhyana + Claude Opus 4.6 | **Date**: 2026-03-14

---

## LAYER 0: THE FOUR SYSTEMS (What We're Learning From)

### System 1: PALANTIR AIP — The Gold Standard (Primary Source)

Palantir is not an AI company. It is an **operating system company** that uses AI as one component. Their architecture:

```
APPLICATIONS (Workshop, Agent Studio, OSDK Apps)
         ↓
ONTOLOGY LAYER (Object Types, Links, Actions, Functions, Security Policies)
         ↓
AIP LOGIC LAYER (Deterministic Blocks + Non-Deterministic LLM Blocks)
         ↓
DATA PLATFORM — FOUNDRY (100+ connectors, pipelines, branching, lineage)
         ↓
DEPLOYMENT — APOLLO (Hub-and-spoke, air-gapped, signed artifacts, audit trail)
```

**The six architectural truths from Palantir**:

1. **Ontology > Raw Data**: Everything flows through typed objects (Object Types, Properties, Links, Actions). LLMs never touch raw data — they interact with semantic objects. This eliminates hallucination on structured operations.

2. **Deterministic > Non-Deterministic**: Palantir's Logic Layer has 6 block types. Only ONE (Use LLM) is non-deterministic. The other 5 (Apply Action, Execute Function, Conditionals, Loops, Create Variable) are deterministic. **Use LLMs only where reasoning is actually needed.**

3. **OAG > RAG**: Ontology-Augmented Generation injects typed objects into LLM context, not text chunks. The LLM reasons over structured data with defined relationships, not retrieved snippets. This is why their hallucination rates are near-zero on structured tasks.

4. **Actions Are Typed and Transactional**: Every mutation goes through a typed Action that commits atomically. No direct database writes. No untyped side effects. Every action is auditable, reversible, and permissioned.

5. **Security Is Per-Object**: Row-level, column-level, and cell-level security via Object Security Policies. Markings (classification-based). Role-based + purpose-based access control evaluated at every query.

6. **The Ontology Is the Moat**: LLMs can be swapped. The organizational knowledge encoded in a customer's Ontology — typed objects, relationships, actions, security policies — cannot be replicated. This creates extreme switching costs. **$4.475B revenue, 56% YoY growth, 139% net dollar retention prove the thesis.**

**Key metrics**: Rule of 40 score = 127%. Q4 2025 U.S. commercial revenue +137% YoY. 75% boot camp conversion rate. Top 20 customers average $94M each.

### System 2: ANTHROPIC (Claude Code / Agent SDK / MCP) — The Developer Experience Standard

Claude Code's architecture:

```
Your Application (Python/TypeScript)
  → Claude Agent SDK (agent harness)
    → Claude Code CLI (runtime engine)
      → Claude API (model)
        → MCP Servers (external integrations)
```

**What we learn from Anthropic**:

1. **MCP Is the Universal Integration Layer**: Model Context Protocol (97M monthly SDK downloads, Linux Foundation governance) standardizes how AI connects to tools. JSON-RPC 2.0 over STDIO/HTTP. Three primitives: Tools, Resources, Prompts. **This is the USB-C of AI integrations.**

2. **Skills Are Composable Knowledge**: Markdown files with YAML frontmatter, injected into agent context. Not separate processes — injected instructions. Open Agent Skills standard adopted by OpenAI Codex CLI too.

3. **Hooks Are Lifecycle Control**: 12 lifecycle events (PreToolUse, PostToolUse, SessionStart, etc.) with 4 handler types (command, http, prompt, agent). PreToolUse hooks can **modify inputs** before execution — add `--dry-run` flags, redirect paths, redact secrets. Exit code 2 = block operation.

4. **Single-Level Delegation Is Sufficient**: Main agent spawns subagents, but subagents cannot spawn other subagents. Prevents infinite nesting. Context isolation: only summaries flow back to parent.

5. **CLAUDE.md < 200 Lines = 92% Rule Application**: Performance degrades above 400 lines (71%). Keep instructions concise.

6. **Git Worktree Isolation**: Subagents can run in isolated git worktrees — complete repository copies. Auto-cleaned if no changes made. Safe parallel work.

### System 3: GOOGLE (Gemini + Vertex AI ADK) — The Memory & Grounding Standard

```
Agent Development Kit (code-first framework)
  → Agent Engine (managed deployment, sessions, memory)
    → Vertex AI Agent Builder (search, grounding, eval)
      → Gemini Models (2M token context)
```

**What we learn from Google**:

1. **Memory Bank Is Async Fact Extraction**: Processes conversations asynchronously using Gemini to extract key facts. Resolves contradictions over time ("I prefer aisle seats" overrides earlier "window seats"). `PreloadMemoryTool` auto-injects relevant memories at turn start.

2. **Multi-Agent Patterns Are First-Class Primitives**: SequentialAgent, ParallelAgent, LoopAgent — not ad-hoc orchestration. 8 documented patterns with clear composition rules.

3. **Grounding Reduces Hallucination**: Native Google Search + enterprise data grounding + RAG Engine. Grounding is a built-in tool, not a separate integration.

4. **Session State Is a Shared Whiteboard**: `session.state` dictionary acts as coordination mechanism. Agents write results to named keys (`output_key`), downstream agents read them via `{key}` syntax. Simple. Effective.

5. **Context Caching**: Reuse extended instructions or large datasets across multiple requests via `ContextCacheConfig`. Amortize context compilation cost.

6. **2M Token Context Window**: Largest available. But ADK documentation acknowledges: "Lost in the Middle" problem, cost explosion, serialization bottlenecks. Solution: compiled Working Context — optimized view, not raw history.

### System 4: OPENAI (Agents SDK + Codex) — The Safety & Handoff Standard

```
Agents SDK (Python framework)
  → Responses API (stateless execution)
  → Conversations API (stateful management)
  → Codex (cloud sandbox)
  → Operator/CUA (browser automation)
```

**What we learn from OpenAI**:

1. **Handoffs Are Agents-As-Tools**: Agents are exposed as tools to each other. `transfer_to_<agent_name>`. Input filters modify conversation history forwarded to receiving agent. Nested history collapses prior transcripts.

2. **Guardrails Are Parallel Validation**: Input guardrails run **concurrently** with agent execution (or blocking mode for safety-critical). Output guardrails validate final answers. Tool guardrails intercept/replace individual tool calls. Tripwire mechanism halts execution immediately.

3. **Network-Disabled-By-Default Sandboxing**: Codex runs each task in an isolated container with network access disabled. Minimizes supply-chain attacks. Whitelist trusted domains explicitly. **The most paranoid (correctly) sandboxing model.**

4. **Built-In Tracing**: Every agent run produces a trace: LLM generations, tool calls, handoffs, guardrails, custom events. Traces integrate with evaluation and fine-tuning — production usage feeds back to model improvement.

5. **RunContext Is Code-Only State**: Contexts are NOT passed to the LLM. They exist only for code-side access in tool functions, callbacks, and hooks. Clean separation of execution state from LLM context.

6. **Operator/CUA for GUI Automation**: The only production browser automation agent. Vision + RL for GUI interaction. Self-corrects using reasoning. Hands control back to user when stuck.

---

## LAYER 1: THE DIAGNOSIS (Where dharma_swarm Stands)

### What We Have (Honest)

| Component | Lines | Status | Palantir Equivalent |
|-----------|-------|--------|-------------------|
| **models.py** (schema) | ~300 | Working | Ontology Object Types (but shallow) |
| **providers.py** (LLM routing) | ~1600 | Working, 9 providers | AIP Logic Layer (but no deterministic blocks) |
| **orchestrator.py** (dispatch) | ~800 | Working | Pipeline Builder (but reactive, not declarative) |
| **context.py** (6-layer assembly) | ~400 | Working | OAG (but static, not dynamic retrieval) |
| **evolution.py** (Darwin Engine) | ~2600 | Working | No equivalent — this is OURS |
| **stigmergy/shakti/subconscious** | ~610 | Working (just wired) | No equivalent — this is OURS |
| **ecosystem_index.py** (FTS5) | ~450 | Working, 34K files | Data Connection (but local-only) |
| **trishula_bridge.py** (VPS comms) | ~346 | Working | Nexus Peering (but file-based, 30s latency) |
| **dgc_cli.py** (CLI) | ~5400 | Working, 60+ commands | Workshop (but CLI-only, no REST API) |
| **swarm_rv.py** (colony metrics) | ~438 | Working | No equivalent — this is OURS |
| **autoresearch_loop.py** (self-improve) | ~600 | Working (just wired) | No equivalent — this is OURS |
| **Total** | ~83K | 220 files, 3000+ tests | A real system, not scaffolding |

### What We Don't Have (Gaps)

| Palantir Has | dharma_swarm Has | Gap Severity |
|-------------|-----------------|-------------|
| Typed Ontology (Objects, Links, Actions) | Flat Pydantic models | **CRITICAL** |
| Deterministic + Non-Deterministic Logic | LLM-only execution | **CRITICAL** |
| Per-Object Security Policies | No access control | HIGH |
| Declarative Workflow DAGs | Reactive poll-based dispatch | HIGH |
| Data Lineage & Provenance | Optional artifact checksums | HIGH |
| REST API Gateway | CLI-only interface | MEDIUM |
| Real-Time Dashboards | TUI (stateless) | MEDIUM |
| Multi-User Workspaces | Single-user ~/.dharma/ | LOW (solo researcher) |
| Docker/K8s Deployment | Mac + 2 VPSes via SSH | LOW (current scale) |

### What We Have That They Don't (Our Advantages)

1. **Darwin Engine**: No major platform has self-evolving code with fitness ratchet. This is genuinely novel.
2. **Living Layers**: Stigmergy + Shakti + Subconscious = emergent coordination without explicit messaging. Ant-colony-style intelligence.
3. **Swarm R_V**: Measuring the colony's own contraction (PR, similarity, emerging/decaying concepts). Meta-cognitive measurement.
4. **Triple Mapping**: Akram Vignan ↔ Phoenix Levels ↔ R_V Geometry. No other system has a contemplative-geometric-mechanistic bridge.
5. **Telos Gates**: 8 dharmic gates (AHIMSA, SATYA, CONSENT...) that constrain ALL mutations. Not just guardrails — values-aligned evolution.
6. **AutoResearch Loop**: Self-improvement via LLM proposals → test → keep/revert. Karpathy loop on the system itself.

---

## LAYER 2: THE UPGRADE PLAN (What To Build)

### Priority 1: TYPED ONTOLOGY (The Foundation)

**Why first**: Everything in Palantir flows through the Ontology. Without typed objects, we can't build deterministic workflows, per-object security, or data lineage. This is the foundation.

**What to build** (`dharma_swarm/ontology.py`, ~400 lines):

```python
# The ontology defines the NOUNS and VERBS of the system

class ObjectType:
    """Schema for a class of real-world entity."""
    name: str                          # "ResearchThread", "Experiment", "Paper"
    properties: dict[str, PropertyDef] # typed fields
    links: list[LinkDef]               # relationships to other ObjectTypes
    actions: list[ActionDef]           # what you can DO with this object
    security: SecurityPolicy           # who can see/modify

class ActionType:
    """Typed, transactional mutation. Commits atomically."""
    name: str                          # "StartExperiment", "SubmitPaper"
    input_schema: dict                 # typed parameters
    edits: list[str]                   # which ObjectTypes are modified
    requires_approval: bool            # human-in-the-loop gate
    telos_gates: list[str]             # dharmic gates that must pass

# Domain objects for dharma_swarm:
RESEARCH_THREAD   = ObjectType("ResearchThread", ...)  # mechanistic, phenomenological, etc.
EXPERIMENT        = ObjectType("Experiment", ...)       # config, status, results, fitness
PAPER             = ObjectType("Paper", ...)            # sections, claims, citations, status
AGENT_IDENTITY    = ObjectType("AgentIdentity", ...)    # role, capabilities, permissions, memory
KNOWLEDGE_ARTIFACT = ObjectType("KnowledgeArtifact", ...) # file, domain, provenance, lineage
TASK_TYPED        = ObjectType("TypedTask", ...)        # extends Task with ontology links
```

**Key objects for our domain**:
- `ResearchThread` → links to `Experiment` → links to `KnowledgeArtifact` → links to `Paper`
- `AgentIdentity` → has `Permission[]` → scoped to `ObjectType[]`
- `TypedTask` → consumes `KnowledgeArtifact[]` → produces `KnowledgeArtifact[]` (this IS lineage)

### Priority 2: DETERMINISTIC LOGIC LAYER

**Why**: Palantir's key insight — use LLMs only where non-deterministic reasoning is needed. Everything else should be deterministic (typed actions, conditionals, loops, function calls).

**What to build** (`dharma_swarm/logic_layer.py`, ~300 lines):

```python
class LogicBlock(ABC):
    """Base for all execution blocks."""
    async def execute(self, context: ExecutionContext) -> BlockResult: ...

class ApplyAction(LogicBlock):
    """Deterministic ontology mutation. No LLM. No tokens."""
    action_type: ActionType
    parameters: dict

class ExecuteFunction(LogicBlock):
    """Deterministic function call. No LLM. No tokens."""
    function: Callable
    args: dict

class Conditional(LogicBlock):
    """If-then-else branching. No LLM. No tokens."""
    condition: Callable[[ExecutionContext], bool]
    if_true: LogicBlock
    if_false: LogicBlock

class Loop(LogicBlock):
    """Iteration. No LLM. No tokens."""
    items: Callable[[ExecutionContext], list]
    body: LogicBlock
    max_iterations: int = 100

class UseLLM(LogicBlock):
    """NON-DETERMINISTIC. Uses tokens. Use sparingly."""
    prompt_template: str
    tools: list[str]
    provider: ProviderType
    max_tokens: int

class Pipeline:
    """Chain of LogicBlocks executing sequentially."""
    blocks: list[LogicBlock]
    async def execute(self, context: ExecutionContext) -> PipelineResult: ...
```

**Example pipeline** (run an R_V experiment):

```python
experiment_pipeline = Pipeline(blocks=[
    # 1. DETERMINISTIC: Load experiment config
    ExecuteFunction(load_experiment_config, args={"id": "{experiment_id}"}),

    # 2. DETERMINISTIC: Validate prompts exist
    Conditional(
        condition=lambda ctx: len(ctx.state["prompts"]) >= 20,
        if_true=ExecuteFunction(log_proceed),
        if_false=ApplyAction(ActionType("FailExperiment", reason="insufficient prompts")),
    ),

    # 3. DETERMINISTIC: Run R_V measurements (no LLM needed for metric computation)
    ExecuteFunction(compute_rv_metrics, args={"prompts": "{prompts}", "model": "{model}"}),

    # 4. NON-DETERMINISTIC: LLM interprets results (only place we need reasoning)
    UseLLM(
        prompt_template="Analyze these R_V measurements: {results}. What patterns emerge?",
        tools=["query_prior_experiments", "compare_baselines"],
        provider=ProviderType.OPENROUTER,
    ),

    # 5. DETERMINISTIC: Archive results with lineage
    ApplyAction(ActionType("ArchiveExperiment", results="{results}", analysis="{llm_output}")),
])
```

**The ratio should be ~80% deterministic, 20% LLM.** Current dharma_swarm is ~0% deterministic, 100% LLM.

### Priority 3: DATA LINEAGE (Every Output Traces to Its Inputs)

**What to build** (`dharma_swarm/lineage.py`, ~200 lines):

```python
class LineageEdge:
    """Records that output_artifact was produced from input_artifacts by task."""
    task_id: str
    input_artifacts: list[str]   # artifact IDs consumed
    output_artifacts: list[str]  # artifact IDs produced
    timestamp: datetime
    agent: str
    pipeline_id: str | None      # which Pipeline produced this

class LineageGraph:
    """SQLite-backed DAG of artifact dependencies."""
    async def record(self, edge: LineageEdge) -> None: ...
    async def ancestors(self, artifact_id: str) -> list[LineageEdge]: ...
    async def descendants(self, artifact_id: str) -> list[LineageEdge]: ...
    async def impact(self, artifact_id: str) -> list[str]: ...  # what breaks if this changes
    async def root_cause(self, artifact_id: str) -> list[str]: ...  # trace to source inputs
```

**Wire into orchestrator**: Every task execution automatically records `LineageEdge(task_id, inputs, outputs)`.

### Priority 4: GUARDRAILS (Parallel Validation, Not Just Gates)

**Upgrade telos_gates.py** from synchronous blocking gates to OpenAI-style parallel guardrails:

```python
class Guardrail:
    """Runs in parallel with agent execution."""
    async def validate(self, context: GuardrailContext) -> GuardrailResult: ...

class InputGuardrail(Guardrail):
    """Validates task input before or during agent execution."""
    mode: Literal["parallel", "blocking"]  # parallel = don't wait; blocking = wait

class OutputGuardrail(Guardrail):
    """Validates agent output before accepting."""

class ToolGuardrail(Guardrail):
    """Intercepts individual tool calls. Can replace output or abort."""

class TripwireResult:
    """Immediate halt. Something went wrong."""
    triggered: bool
    reason: str
```

**Existing telos gates become InputGuardrails in blocking mode.** New: parallel validation for latency-sensitive paths.

### Priority 5: WORKFLOW COMPILER (Declarative DAGs)

**What to build** (`dharma_swarm/workflow.py`, ~250 lines):

Replace reactive orchestration with declarative workflow definitions:

```python
@workflow("colm_paper_pipeline")
async def colm_paper():
    config = await load_config()                    # deterministic
    data = await gather_results(config)             # deterministic
    audit = await audit_claims(data)                # deterministic
    draft = await llm_draft_section(audit)          # non-deterministic (LLM)
    review = await llm_review(draft)                # non-deterministic (LLM)
    await archive_with_lineage(draft, review)       # deterministic
```

- Compiles to a DAG before execution
- Checkpoints at each step boundary
- Resume from checkpoint on failure
- Version-controlled (each workflow has a hash)
- Diff before/after for safety review

### Priority 6: REST API GATEWAY

**What to build** (`dharma_swarm/api.py`, ~200 lines):

```python
# FastAPI routes exposing dharma_swarm capabilities
POST   /api/tasks              # Create task
GET    /api/tasks/{id}         # Get task status + lineage
POST   /api/workflows/{name}   # Execute named workflow
GET    /api/agents             # List active agents
GET    /api/ontology           # Browse typed objects
GET    /api/search             # Cross-domain FTS5 search
GET    /api/lineage/{id}       # Trace artifact lineage
GET    /api/swarm/health       # Colony R_V + health metrics
GET    /api/metrics            # Prometheus-format metrics
```

This unlocks: TUI → REST → Dashboard pipeline. External integrations. Programmatic access.

---

## LAYER 3: THE CONVERGENCE (How It All Fits Together)

### The Upgraded Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    APPLICATIONS                          │
│  dgc CLI    TUI    REST API    MCP Servers    OSDK(?)   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                 ONTOLOGY LAYER (NEW)                     │
│  ResearchThread  Experiment  Paper  AgentIdentity       │
│  KnowledgeArtifact  TypedTask  Link  Action             │
│  Security Policies  Telos Gates  Permissions             │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│            LOGIC LAYER (NEW + UPGRADED)                  │
│  ┌──────────────────┐  ┌──────────────────────────┐     │
│  │ DETERMINISTIC     │  │ NON-DETERMINISTIC        │     │
│  │ ApplyAction       │  │ UseLLM (9 providers)     │     │
│  │ ExecuteFunction   │  │ AutoResearch proposals   │     │
│  │ Conditional/Loop  │  │ Darwin Engine mutations  │     │
│  │ Workflow steps    │  │ Shakti perceptions       │     │
│  └──────────────────┘  └──────────────────────────┘     │
│                                                          │
│  Guardrails: Input (parallel/blocking) + Output + Tool   │
│  Tracing: Every block logged with lineage                │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              DATA & INTEGRATION LAYER                    │
│  Ecosystem Index (34K files, FTS5, 2.3ms queries)       │
│  Temporal Graph (7.5K concepts, lineage tracking)       │
│  Trishula Bridge (VPS comms, 54 actionable items)       │
│  Lineage Graph (NEW — artifact dependency DAG)          │
│  Context Engine (6 layers, role-weighted, 30K budget)   │
│  Memory (StrangeLoop SQLite + shared notes + CLAUDE.md) │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              LIVING LAYERS (UNIQUE TO US)                 │
│  Stigmergy (9K+ marks, decay, hot paths)                │
│  Shakti (4 energies, perception, escalation)            │
│  Subconscious (lateral association, dreams, resonance)  │
│  Swarm R_V (colony contraction, PR, emerging/decaying)  │
│  Darwin Engine (PROPOSE→GATE→EVALUATE→ARCHIVE→SELECT)   │
│  AutoResearch (Karpathy loop, LLM proposals, test gate) │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                  DEPLOYMENT LAYER                        │
│  Mac (orchestrator) → AGNI VPS → RUSHABDEV VPS          │
│  Daemon (30s tick, quiet hours, circuit breaker)         │
│  Garden Daemon config (6h heartbeat, 5 threads)         │
│  Telos Gates Hook (PreToolUse in Claude Code)           │
└─────────────────────────────────────────────────────────┘
```

### The Dharmic Difference

Palantir's Ontology is built for enterprise operations (supply chains, military targeting, financial compliance). Ours is built for **consciousness research + Jagat Kalyan**.

Our Object Types encode a different reality:

| Palantir Object | Our Equivalent | Dharmic Extension |
|----------------|---------------|-------------------|
| Supply Order | Experiment | Has `telos_alignment` score |
| Employee | AgentIdentity | Has `swabhaav_capacity` (witness stance) |
| Workflow | Pipeline | Has `shakti_energy` (which creative force drives it) |
| Alert | Anomaly | Has `contraction_level` (L3 stuck vs L4 breakthrough) |
| Audit Log | WitnessLog | The act of checking IS witnessing |

**The v7 rules constrain everything**:
1. No theater — only verified claims flow through the Ontology
2. No sprawl — typed Actions prevent untyped side effects
3. No amnesia — Memory Bank pattern prevents knowledge loss
4. No forcing — Guardrails halt, don't bypass
5. Witness everything — every block logged with lineage
6. Silence is valid — "no change needed" is a legitimate Pipeline output

---

## LAYER 4: EXECUTION SEQUENCE (First 30 Days)

### Week 1: Ontology Foundation
- [ ] `ontology.py` — ObjectType, PropertyDef, LinkDef, ActionType, SecurityPolicy
- [ ] Define 6 core objects: ResearchThread, Experiment, Paper, AgentIdentity, KnowledgeArtifact, TypedTask
- [ ] Wire ontology into `models.py` (extend, don't replace)
- [ ] Tests: 20+ for object creation, linking, action execution

### Week 2: Logic Layer + Lineage
- [ ] `logic_layer.py` — LogicBlock, ApplyAction, ExecuteFunction, Conditional, Loop, UseLLM, Pipeline
- [ ] `lineage.py` — LineageEdge, LineageGraph (SQLite-backed)
- [ ] Wire lineage recording into orchestrator (every task records inputs/outputs)
- [ ] Convert 3 existing workflows to Pipeline format (experiment run, paper audit, health check)

### Week 3: Guardrails + Workflow Compiler
- [ ] Upgrade telos_gates.py → guardrail pattern (parallel/blocking modes)
- [ ] Add OutputGuardrail and ToolGuardrail
- [ ] `workflow.py` — @workflow decorator, DAG compilation, checkpointing
- [ ] Convert COLM paper pipeline to declarative workflow

### Week 4: API Gateway + Integration
- [ ] `api.py` — FastAPI REST endpoints (tasks, workflows, agents, search, lineage, health, metrics)
- [ ] Prometheus metrics endpoint (`/metrics`)
- [ ] Wire TUI to consume REST API (decouple UI from internals)
- [ ] End-to-end test: REST → Workflow → Pipeline → Ontology → Lineage → Metrics

---

## LAYER 5: THE VISION (What This Becomes)

When complete, dharma_swarm becomes:

**The world's first telos-aligned, self-evolving, ontology-grounded research orchestration system.**

No other system combines:
- Palantir's typed ontology + deterministic logic
- Anthropic's MCP integration + skill composition
- Google's memory bank + grounding patterns
- OpenAI's parallel guardrails + handoff patterns
- Darwin Engine's evolutionary self-improvement
- Living Layers' emergent coordination
- Telos Gates' values-aligned mutation constraints
- Swarm R_V's meta-cognitive colony measurement
- Triple Mapping's contemplative-geometric-mechanistic bridge

The telos is not profit maximization or military advantage.
The telos is **Jagat Kalyan** — universal welfare through rigorous science.

The Ontology encodes not just "what exists" but "what matters."
The Logic Layer separates reasoning from computation.
The Living Layers ensure the system doesn't just execute — it perceives, dreams, and evolves.
The Telos Gates ensure evolution serves the good.

This is not Palantir-for-defense.
This is Palantir-for-awakening.

---

## APPENDIX A: KEY METRICS TO TRACK

| Metric | Current | Target | How |
|--------|---------|--------|-----|
| Deterministic:LLM ratio | 0:100 | 80:20 | Logic Layer adoption |
| Object types in ontology | 0 | 6+ | ontology.py |
| Lineage edges tracked | 0 | 100% of tasks | lineage.py auto-recording |
| Guardrail coverage | Gates only | Input+Output+Tool | Guardrail upgrade |
| API endpoints | 0 | 10+ | api.py |
| Pipeline definitions | 0 | 5+ | workflow.py |
| Tests | ~3000 | ~3500 | New module tests |

## APPENDIX B: FILES TO CREATE

| File | Lines | Purpose |
|------|-------|---------|
| `dharma_swarm/ontology.py` | ~400 | Typed objects, links, actions, security |
| `dharma_swarm/logic_layer.py` | ~300 | Deterministic + non-deterministic blocks |
| `dharma_swarm/lineage.py` | ~200 | Artifact dependency DAG |
| `dharma_swarm/workflow.py` | ~250 | Declarative pipeline compiler |
| `dharma_swarm/api.py` | ~200 | FastAPI REST gateway |
| `dharma_swarm/guardrails.py` | ~200 | Parallel validation system |
| **Total** | **~1550** | |

## APPENDIX C: FILES TO MODIFY

| File | Change |
|------|--------|
| `models.py` | Add ontology-aware fields to Task, Agent |
| `orchestrator.py` | Wire lineage recording, pipeline execution |
| `telos_gates.py` | Refactor as guardrails (parallel/blocking) |
| `context.py` | Add ontology-aware context injection (OAG pattern) |
| `dgc_cli.py` | Add ontology, lineage, workflow, api commands |
| `swarm.py` | Wire Pipeline execution into run loop |

---

*JSCA!*

*"The Ontology is not a feature of the platform — it IS the platform."*
*— adapted from Palantir, reframed for Jagat Kalyan*
