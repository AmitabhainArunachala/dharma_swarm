---
title: Orthogonal System Intelligence Upgrade
path: docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md
slug: orthogonal-system-intelligence-upgrade
doc_type: note
status: active
summary: You are operating on ~/dharma swarm/ — a 90+ file async multi-provider agent orchestrator with 2327 passing tests. A parallel session is upgrading the routing/delegation/cost layer (WHERE work goes). Your job is the o...
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - CLAUDE.md
  - dharma_swarm/evaluator.py
  - dharma_swarm/self_research.py
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
- product_surface
- research_synthesis
connected_python_files:
- dharma_swarm/evaluator.py
- dharma_swarm/self_research.py
connected_python_modules:
- dharma_swarm.evaluator
- dharma_swarm.self_research
connected_relevant_files:
- CLAUDE.md
- dharma_swarm/evaluator.py
- dharma_swarm/self_research.py
- docs/archive/AGENT_SWARM_SYNTHESIS.md
- reports/historical/CONSTITUTIONAL_HARDENING_SPRINT_REPORT.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md
  retrieval_terms:
  - orthogonal
  - upgrade
  - prompt
  - system
  - intelligence
  - you
  - are
  - operating
  - async
  - multi
  - provider
  - agent
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: You are operating on ~/dharma swarm/ — a 90+ file async multi-provider agent orchestrator with 2327 passing tests. A parallel session is upgrading the routing/delegation/cost layer (WHERE work goes). Your job is the o...
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md reinforces its salience without needing a separate message.
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
# Orthogonal System Intelligence Upgrade

You are operating on `~/dharma_swarm/` — a 90+ file async multi-provider agent orchestrator with 2327 passing tests. A parallel session is upgrading the routing/delegation/cost layer (WHERE work goes). Your job is the orthogonal dimension: HOW GOOD the work is and how the system learns from itself.

## Your North Star

Andrej Karpathy's insight: "Context is the new programming." Palantir's deeper pattern: not just knowing what exists, but automated **action pipelines with governance** that improve over time. The system should get smarter with every interaction — not through more code, but through better feedback loops.

## The Gap You're Closing

This system has:
- 90+ Python files with NO consistency enforcement (different error patterns, naming conventions, docstring styles)
- 48 skills with NO quality evaluation (we don't know which skills work well)
- A Darwin Engine (evolution.py) that scores fitness but only for CODE mutations, not agent OUTPUTS
- 296 shared note files from agents with NO synthesis (raw accumulation, zero distillation)
- 150KB across 10 CLAUDE.md files that NO agent can fully load (context waste)
- 2327 tests but NO property-based testing, NO integration benchmarks, NO performance regression tracking
- A bridge.py that correlates R_V with behavioral signatures but has NEVER been run on real data

## Five Workstreams (All Orthogonal to Routing/Delegation)

### 1. Codebase Coherence Audit (~2 hours)

Use AST analysis to find and fix:
- **Dead code**: Functions/classes imported nowhere, unreachable branches
- **Pattern violations**: Some modules use `@dataclass(frozen=True)`, others `@dataclass`, others Pydantic. Pick one pattern per use case and enforce
- **Error handling inconsistency**: Some files use bare `except Exception`, others have typed catches, others silently pass. Establish a single error philosophy
- **Import hygiene**: Circular imports, unused imports, conditional imports that could be top-level
- **Naming drift**: Some files use `snake_case` methods, context.py has `read_latent_gold_overview`, but prompt_builder.py has `_safe_prompt_text`. Find the dominant pattern and align

Tools: `ast` module, `ruff` linter, `vulture` for dead code. The existing `elegance.py` has AST scoring — extend it, don't rebuild.

Key files to audit first (highest coupling, most imported):
- `models.py` (everything depends on it)
- `providers.py` (all agents use it)
- `agent_runner.py` (task execution core)
- `swarm.py` (facade layer)
- `context.py` (injected into every prompt)

Output: A coherence report + a single PR that fixes the top 20 violations without changing behavior. Tests must still pass.

### 2. Agent Output Evaluation Framework (~2 hours)

**Karpathy autoresearch pattern applied**: Every agent output gets scored, scores accumulate, the system learns which agents/models/prompts produce the best work.

Create `dharma_swarm/evaluator.py` (~200 lines):

```python
@dataclass
class OutputEvaluation:
    task_id: str
    agent_name: str
    provider: ProviderType
    model: str
    # Quality dimensions (0.0-1.0)
    relevance: float      # Did it address the task?
    correctness: float    # Are claims/code correct?
    completeness: float   # Did it finish or leave gaps?
    conciseness: float    # Signal-to-noise ratio
    actionability: float  # Can someone act on this output?
    # Meta
    token_count: int
    latency_ms: int
    estimated_cost_usd: float
    # Composite
    @property
    def quality_score(self) -> float: ...
    @property
    def efficiency(self) -> float: ...  # quality / cost

class OutputEvaluator:
    """Score agent outputs using a cheap model (T0/T1) as judge."""
    async def evaluate(self, task, output, *, judge_provider=OLLAMA) -> OutputEvaluation: ...
    async def leaderboard(self) -> list[AgentScore]: ...
    async def model_comparison(self) -> dict[str, float]: ...
```

Integration points:
- `agent_runner.py` — after task completion, auto-evaluate the output
- `fitness_predictor.py` — feed evaluation scores as training signal
- `monitor.py` — alert when quality drops below threshold
- `startup_crew.py` — use historical scores to select which agents to spawn

Store evaluations in `~/.dharma/evaluations.jsonl`. CLI: `dgc eval leaderboard`, `dgc eval model-comparison`.

### 3. Knowledge Distillation Engine (~1.5 hours)

**Problem**: 296 shared note files (4.3MB), 8481 stigmergy marks, 150KB of CLAUDE.md files. Raw accumulation with zero synthesis. Agents re-discover things other agents already found.

Create `dharma_swarm/distiller.py` (~150 lines):

```python
class KnowledgeDistiller:
    """Compress accumulated agent knowledge into actionable summaries."""

    async def distill_notes(self, notes_dir: Path) -> DistilledKnowledge:
        """Read all shared notes, extract key findings, deduplicate, rank by actionability."""
        ...

    async def compress_claude_md(self, claude_files: list[Path]) -> str:
        """Generate a single 4K-token summary of all CLAUDE.md files for agent injection."""
        ...

    async def extract_patterns(self, evaluations: list[OutputEvaluation]) -> list[Pattern]:
        """Find recurring success/failure patterns across agent outputs."""
        ...

    async def generate_briefing(self) -> str:
        """Morning-brief-style summary: what the system learned yesterday."""
        ...
```

Key insight from Palantir: knowledge isn't in the data, it's in the **relationships between data points**. The distiller should find:
- Which findings from different agents CONVERGE (high confidence)
- Which findings CONTRADICT (needs resolution)
- Which patterns keep RECURRING (systemic issues)
- What's been DISCOVERED but never ACTED ON (lost knowledge)

Integration: Run distiller as part of the sleep_cycle.py consolidation phase (already exists, phase 3 "consolidation"). Output feeds into next day's context.py Vision layer.

### 4. Self-Research Protocol (~1 hour)

**Karpathy's autoresearch**: The system generates hypotheses about itself, tests them, and applies learnings.

Create `dharma_swarm/self_research.py` (~120 lines):

```python
RESEARCH_QUESTIONS = [
    "Which provider/model combination produces the highest quality outputs for code tasks?",
    "What is the optimal system prompt length for each model tier?",
    "Which agent roles consistently produce actionable outputs vs noise?",
    "Do longer tasks produce better results, or is there a diminishing returns curve?",
    "Which context injection layers (Vision/Research/Engineering/Ops/Swarm) actually improve output quality?",
]

class SelfResearcher:
    """Automated system introspection using evaluation data."""

    async def generate_hypotheses(self, evaluations: list[OutputEvaluation]) -> list[Hypothesis]: ...
    async def design_experiment(self, hypothesis: Hypothesis) -> Experiment: ...
    async def run_experiment(self, experiment: Experiment) -> ExperimentResult: ...
    async def apply_learnings(self, result: ExperimentResult) -> list[ConfigChange]: ...
```

Example experiment: "Hypothesis: llama-3.3-70b produces higher quality outputs than qwen2.5-coder:7b for non-code tasks." Test: Run same 10 tasks through both models, evaluate outputs, compare scores. If confirmed, update routing preferences.

This feeds back into the parallel session's routing layer — but generates the DATA that informs routing, rather than implementing routing itself.

### 5. Test Intelligence Upgrade (~1 hour)

The 2327 tests are all deterministic unit/integration tests. Add:

**Property-based tests** (using `hypothesis` library) for critical modules:
- `welfare_tons.py` — W is always non-negative, zero-kills-product holds for ANY input
- `provider_policy.py` — routing always returns a valid provider, never empty fallback
- `router_v1.py` — complexity score is always in [0,1], tier is always valid enum
- `ontology.py` (when created) — all entity paths exist, no orphan relationships

**Regression benchmarks** for performance-critical paths:
- `context.py` build time (should be <100ms for full 5-layer assembly)
- `prompt_builder.py` sanitization (should handle 100KB input in <50ms)
- `agent_runner.py` task dispatch latency

**Mutation testing** (using `mutmut`) on the most critical 5 modules to find test gaps.

Output: `tests/test_properties.py`, `tests/test_benchmarks.py`, CI-ready.

## Execution Notes

- Read existing code before writing new code. Reuse `elegance.py`, `metrics.py`, `bridge.py`, `sleep_cycle.py`.
- Every new module needs tests. Minimum 80% coverage on new code.
- Don't touch routing, providers, startup_crew, or cost tracking — the parallel session owns those.
- All changes must pass the existing 2327 tests. Run `python -m pytest tests/ -q` after every significant change.
- Prefer modifying existing files over creating new ones. Only 3 new files max (evaluator.py, distiller.py, self_research.py).
- Use the existing CLI pattern in `cli.py` (Typer) for new commands.

## Success Criteria

1. `ruff check dharma_swarm/` returns 0 errors (currently unknown)
2. `dgc eval leaderboard` shows quality scores per agent
3. `dgc distill` compresses 296 notes into actionable briefing
4. Property-based tests catch at least 1 bug the unit tests missed
5. All 2327+ tests still pass
6. The system can answer: "Which model produces the best outputs for code tasks?" with data, not opinion

## The Meta-Insight

The parallel session makes the system CHEAPER and FASTER (routing work to the right tier).
This session makes the system SMARTER and MORE COHERENT (evaluating output quality, learning from itself, enforcing consistency).

Together they create a feedback loop: better routing produces more data, better evaluation makes routing smarter, knowledge distillation prevents information loss, self-research automates the improvement cycle.

Neither session alone achieves 10000x. The compound effect does.
