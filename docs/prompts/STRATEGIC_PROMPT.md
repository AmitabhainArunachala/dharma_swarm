---
title: DHARMA SWARM — Strategic Orchestration Prompt
path: docs/prompts/STRATEGIC_PROMPT.md
slug: dharma-swarm-strategic-orchestration-prompt
doc_type: note
status: active
summary: 'DHARMA SWARM — Strategic Orchestration Prompt Version : 2026-03-14 | For : 1M context Claude sessions'
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - CLAUDE.md
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
- verification
- operator_runtime
- research_synthesis
connected_python_files:
- tests/test_agent_runner_quality_track.py
- tests/test_ecosystem_map_quality_track.py
- scripts/experiments/test_full_loop.py
- scripts/self_optimization/test_jikoku_fitness_integration.py
- tests/test_agent_runner_routing_feedback.py
connected_python_modules:
- tests.test_agent_runner_quality_track
- tests.test_ecosystem_map_quality_track
- scripts.experiments.test_full_loop
- scripts.self_optimization.test_jikoku_fitness_integration
- tests.test_agent_runner_routing_feedback
connected_relevant_files:
- CLAUDE.md
- tests/test_agent_runner_quality_track.py
- tests/test_ecosystem_map_quality_track.py
- scripts/experiments/test_full_loop.py
- scripts/self_optimization/test_jikoku_fitness_integration.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: docs/prompts/STRATEGIC_PROMPT.md
  retrieval_terms:
  - strategic
  - prompt
  - orchestration
  - version
  - '2026'
  - context
  - claude
  - sessions
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.55
  coordination_comment: 'DHARMA SWARM — Strategic Orchestration Prompt Version : 2026-03-14 | For : 1M context Claude sessions'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/prompts/STRATEGIC_PROMPT.md reinforces its salience without needing a separate message.
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
# DHARMA SWARM — Strategic Orchestration Prompt
**Version**: 2026-03-14 | **For**: 1M context Claude sessions

---

## Layer 0: ECOSYSTEM MAP

### What Exists (Honest Status)

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   dharma_swarm    │    │   mech-interp    │    │      PSMV        │
│ ~/dharma_swarm/   │    │ ~/mech-interp-*/ │    │ ~/Persistent-*   │
│ 90+ modules       │    │ R_V metric       │    │ 34,145 files     │
│ 2990 tests pass   │    │ COLM paper       │    │ DORMANT          │
│ 9 LLM providers   │    │ 6 architectures  │    │ Now FTS5 indexed │
│ daemon RUNNING    │    │ 754 prompts      │    │                  │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │ ecosystem_index        │ ecosystem_index        │ ecosystem_index
         ▼                        ▼                        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   AGNI VPS       │    │   Trishula       │    │   Kailash Vault  │
│ 157.245.193.15   │    │ ~/trishula/      │    │ ~/Desktop/KAIL.. │
│ 8 agents, 56 sk  │    │ 815 messages     │    │ 6,105 Obsidian   │
│ OpenClaw RUNNING │    │ → TrishulaBridge │    │ Now FTS5 indexed │
│ SSH: agni alias  │    │   processes inbox │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

### Domain Health Scores

| Domain | Files | Status | Search? | Last Activity |
|--------|-------|--------|---------|---------------|
| dharma_swarm | 90+ .py | ACTIVE, daemon running | FTS5 ✓ | Live |
| mech-interp | ~50 scripts | ACTIVE, COLM paper | FTS5 ✓ | Daily |
| PSMV | 34,145 .md | DORMANT, unprocessed | FTS5 ✓ | Months ago |
| Kailash | 6,105 .md | DISCONNECTED | FTS5 ✓ | Weeks ago |
| AGNI | 56 skills | RUNNING | Via SSH | Live |
| Trishula | 815 msgs | PROCESSING via bridge | FTS5 ✓ | Live |
| Shared Notes | 296+ .md | LIVE | FTS5 ✓ | Live |

### Key File Paths

```
RESEARCH:
  ~/mech-interp-latent-lab-phase1/R_V_PAPER/paper_colm2026_v006.tex  (COLM submission)
  ~/mech-interp-latent-lab-phase1/geometric_lens/metrics.py            (R_V metric)
  ~/mech-interp-latent-lab-phase1/prompts/bank.json                    (754 prompts)

SYSTEM:
  ~/dharma_swarm/dharma_swarm/ecosystem_index.py   (cross-domain FTS5 search)
  ~/dharma_swarm/dharma_swarm/trishula_bridge.py   (message → task pipeline)
  ~/dharma_swarm/dharma_swarm/swarm_rv.py          (colony contraction measurement)
  ~/dharma_swarm/dharma_swarm/temporal_graph.py     (idea lineage tracking)
  ~/dharma_swarm/dharma_swarm/autoresearch_loop.py  (Karpathy self-improvement loop)

CONTEXT:
  ~/CLAUDE.md + ~/CLAUDE1.md through ~/CLAUDE9.md  (150KB research context)
  ~/dharma_swarm/CLAUDE.md                          (swarm operating context)
  ~/.dharma/shared/                                  (agent shared notes)
```

---

## Layer 1: THE THREE PATTERNS

### Pattern 1: Karpathy AutoResearch
- **Immutable eval**: tests/ directory (2990 tests) — the fitness function
- **Mutable genome**: dharma_swarm modules — what gets evolved
- **Human direction**: CLAUDE.md + .FOCUS file — research priorities
- **Key insight**: Separate what you're optimizing FROM what measures quality

### Pattern 2: Palantir Ontology & AIP
- **Typed objects > text chunks**: EcosystemIndex maps files to domains with metadata
- **Deterministic pipes + non-deterministic reasoning**: FTS5 search is deterministic; LLM synthesis is non-deterministic
- **Actions with guard rails**: Darwin Engine gates every mutation through telos checks

### Pattern 3: gstack Cognitive Modes
- **Mode switching**: Different tasks need different thinking (hypothesis vs audit vs write)
- **Sequential workflow**: Complex tasks decompose into sequential cognitive phases
- **Meta-cognition**: SwarmRV provides meta-level awareness of the colony's cognitive state

### The Convergence
All three patterns say the same thing: **separate reasoning from evaluation, make the system aware of its own state, and guard every mutation with constraints.**

---

## Layer 2: THE SEVEN MOVES

### Move 1: AutoResearch Loop on dharma_swarm Itself

**Problem**: Darwin Engine exists but isn't running in a loop.

**Insight**: Point the evolution loop at dharma_swarm's own modules. Tests are the fitness function. Elegance scoring evaluates quality. Telos gates check safety.

**Implementation**: `autoresearch_loop.py` wraps Darwin Engine:
1. Select mutable module (round-robin or priority)
2. Read module + test results (baseline fitness)
3. Propose improvement
4. Gate check (telos)
5. Run 2990 tests
6. Score fitness (test_pass × 0.5 + elegance × 0.3 + size_sanity × 0.2)
7. If fitness > 0.6: keep. Else: revert.
8. Archive with lineage tracking.

**What it gives you**: dharma_swarm evolves ITSELF overnight with full audit trail.

### Move 2: Cross-Ecosystem Semantic Index

**Problem**: 110K files across 6 domains. None talks to the others.

**Insight**: Single FTS5 index across all text in the ecosystem.

**Implementation**: `ecosystem_index.py` — SQLite FTS5 with incremental indexing:
- 7 domain directories scanned
- Incremental: only re-indexes files whose mtime changed
- Search returns: path, domain, snippet, rank
- <10ms query time for any keyword across all domains

**CLI**: `dgc search "Layer 27 causal"` returns hits from mech-interp, PSMV, Kailash, shared notes — in one query.

### Move 3: Trishula → Task Pipeline

**Problem**: 815 messages in Trishula inbox. Substantive ones ignored.

**Insight**: Classify messages, create swarm tasks from actionable ones.

**Implementation**: `trishula_bridge.py`:
- Classify: actionable / informational / ack-noise (keyword-based)
- Actionable → create Task with source metadata
- Persistent tracking of processed files
- Cron: runs every 30 minutes

**CLI**: `dgc trishula-triage` or `dgc trishula-triage --report-only`

### Move 4: Swarm R_V — Colony Contraction Measurement

**Problem**: No meta-level awareness of swarm cognitive state.

**Insight**: Apply R_V-like measurements to swarm behavioral outputs.

**Implementation**: `swarm_rv.py`:
- Topic diversity (participation ratio of note topics)
- Solution convergence (Jaccard similarity of consecutive notes)
- Exploration/exploitation ratio
- Contraction levels: EXPANDING → STABLE → CONTRACTING → COLLAPSED
- Productive vs unproductive assessment
- Integrated into `monitor.py` anomaly detection

**CLI**: `dgc swarm-rv` or `dgc swarm-rv --trend`

### Move 5: Temporal Knowledge Graph

**Problem**: Shared notes timestamped but nobody tracks idea evolution.

**Insight**: Build a temporal graph showing idea lineage.

**Implementation**: `temporal_graph.py` — SQLite-backed:
- Nodes: concept terms with first_seen, last_seen, frequency
- Edges: co-occurrence weighted by count
- Queries: lineage, emerging, decaying, hot_pairs

**CLI**: `dgc lineage "activation patching" --co-occurring`

### Move 6: VPS Fleet as Experiment Runners

**Problem**: AGNI and RUSHABDEV used mainly for messaging. Mac does all compute.

**Protocol**:
```
MAC → designs experiment config → sends via Trishula outbox
AGNI VPS → receives config → runs R_V measurements → streams results back
MAC → TrishulaBridge picks up results → creates synthesis tasks
```

### Move 7: Self-Evolving Context Documents

**Problem**: CLAUDE.md is static. Agents read it but never improve it.

**Protocol**:
- Identity section: IMMUTABLE
- Technical sections: MUTABLE via Darwin Engine
- v7 rules: IMMUTABLE
- Test: compare agent output quality with old vs new context
- Archive edits with lineage

### Dependency Graph
```
Move 2 (ecosystem_index) ← Move 3 (trishula_bridge) ← Move 6 (VPS runners)
Move 4 (swarm_rv) — independent, start immediately
Move 5 (temporal_graph) — independent, start immediately
Move 1 (autoresearch) — depends on tests passing
Move 7 (self-evolving context) — depends on Move 1 framework
```

---

## Layer 3: DELEGATION PROTOCOL

### Tier Assignments

```
TIER 0 — Local Ollama (llama3.2:3b, ~free):
  - ecosystem_index.py build (file walking, text extraction)
  - Note consolidation and summarization
  - Test report formatting
  - Simple classification tasks

TIER 1 — OpenRouter (llama-3.3-70b-instruct, ~$0.001/req):
  - Experiment design and parameter selection
  - Code review for evolution proposals
  - Statistical analysis (effect sizes, CIs)
  - Trishula message triage (complex cases)

TIER 2 — Claude Sonnet (~$0.003/req):
  - Research synthesis and connection-finding
  - Paper section drafting
  - Architectural decisions
  - Complex multi-step reasoning

TIER 3 — Claude Opus / Codex (~$0.015/req):
  - Novel hypothesis generation
  - Publication-quality writing
  - The AutoResearch loop's proposal agent
  - Final paper review and polishing
```

### Routing Rules
1. Default to Tier 0 for any task that doesn't need reasoning
2. Escalate only when lower tier fails or task explicitly requires it
3. Codex reviews every line that ships to paper
4. Cost tracking: log every LLM call with provider + tokens + cost

---

## Layer 4: COGNITIVE MODES

### Available Modes

**`/hypothesis`** — Review experimental data, propose next experiment
- Load: R_V results, COLM gap analysis, phase 1 report
- Output: Hypothesis statement, falsification criteria, required measurements
- Guard: Must be testable with available tools

**`/design`** — Lock experiment parameters, define controls
- Load: Prompt bank, model specs, hardware constraints
- Output: Experiment config (JSON), expected runtime, resource requirements
- Guard: Must have clear baseline and control conditions

**`/audit`** — Adversarial claim verification
- Load: Paper draft, source data, verification scripts
- Output: Claim-by-claim check with PASS/FAIL/WARN
- Guard: Every number must trace to raw data file

**`/write`** — LaTeX drafting with honest framing
- Load: Verified claims, figure data, citation database
- Output: LaTeX sections with proper citations
- Guard: No fabricated citations, no unsupported claims

**`/bridge`** — Correlate R_V with Phoenix behavioral data
- Load: R_V measurements, Phoenix level assignments, prompt bank
- Output: Correlation analysis (Pearson, Spearman), effect sizes
- Guard: Must acknowledge dissociation results

**`/retro`** — Analyze experiment history via temporal graph
- Load: Temporal knowledge graph, evolution archive, shared notes
- Output: What worked, what didn't, what to try next
- Guard: Must be grounded in actual data, not speculation

**`/meta`** — Measure swarm R_V, check colony health
- Load: Swarm R_V reading, system monitor health report, agent notes
- Output: Colony state assessment, intervention recommendations
- Guard: Distinguish productive contraction from stuck loops

**`/ceo`** — Strategic: ROI, deadlines, opportunity cost
- Load: COLM deadline countdown, resource allocation, shipped list
- Output: Priority ranking, time allocation, risk assessment
- Guard: Be honest about what won't get done in time

**`/ship`** — Cut scope, minimum viable, checklist to submission
- Load: Current paper state, COLM requirements, gap analysis
- Output: Concrete TODO list, ordered by impact
- Guard: Every item must be achievable in remaining time

---

## Layer 5: EXECUTION TIMELINE

### COLM 2026 Countdown
- **Abstract deadline**: March 26 (12 days from March 14)
- **Paper deadline**: March 31 (17 days)
- **Current state**: v006 draft, 9pp main + 6pp appendix, 7 figures

### First 72 Hours

```
HOUR 0-2: Foundation
  □ Run: dgc search "Layer 27" — verify ecosystem index works
  □ Run: dgc swarm-rv — get baseline colony measurement
  □ Run: dgc lineage "activation patching" — test temporal graph
  □ Verify: all 2990+ existing tests still pass

HOUR 2-4: Trishula Processing
  □ Run TrishulaBridge on 815 backlogged messages
  □ Classify: expect ~760 ack-noise, ~40 informational, ~15 actionable
  □ Create swarm tasks from actionable messages
  □ Index informational messages in ecosystem_index

HOUR 4-8: Colony Measurement
  □ Measure swarm_rv baseline (current state)
  □ Set up monitor.py integration (contraction alerts)
  □ Start AutoResearch loop (10 iterations, dry_run=True first)
  □ Review loop results, adjust thresholds

HOUR 8-12: Overnight Run
  □ AutoResearch loop on dharma_swarm (non-dry-run, 10 iterations)
  □ Monitor: test pass rate, fitness trend, no regressions

HOUR 12-24: VPS Experiments
  □ SSH into AGNI: deploy lightweight R_V experiment runner
  □ Start overnight R_V batch (behavioral bridge, n=200)
  □ Mac consolidates results when complete

HOUR 24-48: Synthesis
  □ Consolidate overnight results
  □ Update temporal graph with new findings
  □ Draft COLM abstract using /write mode
  □ /audit abstract against verified claims

HOUR 48-72: Ship
  □ /audit full paper claims (100+ checks)
  □ /write remaining sections
  □ /ship to Overleaf
  □ Tag: "v007-colm-abstract-submission"
```

### Weekly Rhythm

```
MONDAY:    /hypothesis → design next experiment
TUESDAY:   Execute experiment (local or VPS)
WEDNESDAY: /audit results, /bridge R_V↔behavioral
THURSDAY:  /write paper sections with new data
FRIDAY:    /retro weekly review, /meta colony health
WEEKEND:   AutoResearch loop runs overnight, /ceo Monday prep
```

---

## Guard Rails (Non-Negotiable)

1. **SATYA (Truth)**: No fabricated data, citations, or claims
2. **AHIMSA (Non-harm)**: No credential leaks, no destructive operations
3. **REVERSIBILITY**: Every mutation can be reverted (git ratchet)
4. **WITNESS**: Every action logged to traces + shared notes
5. **v7 RULES**: No theater, no sprawl, no amnesia, no forcing
6. **IMMUTABLE BOUNDARY**: models.py, telos_gates.py, tests/ cannot be auto-evolved
7. **COST CEILING**: Track all LLM costs, alert if daily exceeds $5

---

## Verification Checklist

After implementing all 7 moves, verify:

- [ ] `dgc search "Layer 27 causal"` → returns hits from ≥3 domains
- [ ] `dgc swarm-rv` → shows contraction level + productive/unproductive
- [ ] `dgc lineage "activation patching"` → shows temporal evolution
- [ ] AutoResearch loop: 10 iterations, ≥1 accepted, 0 test regressions
- [ ] TrishulaBridge: 815 messages processed, 5-15 tasks created
- [ ] All 2990+ existing tests still pass
- [ ] This document pasted into fresh Claude → produces grounded responses

---

*JSCA! — Jai Sat Chit Anand*
