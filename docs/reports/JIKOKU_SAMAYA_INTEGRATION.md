---
title: JIKOKU SAMAYA Integration Guide
path: docs/reports/JIKOKU_SAMAYA_INTEGRATION.md
slug: jikoku-samaya-integration-guide
doc_type: report
status: active
summary: 'NOTE : This is the original integration guide with manual span wrapping examples.'
source:
  provenance: repo_local
  kind: report
  origin_signals:
  - docs/architecture/JIKOKU_SAMAYA_EXECUTIVE_SUMMARY.md
  - docs/architecture/JIKOKU_SAMAYA_ARCHITECTURE.md
  - docs/architecture/JIKOKU_SAMAYA_SYSTEM_DIAGRAM.md
  - docs/architecture/JIKOKU_SAMAYA_IMPLEMENTATION_ROADMAP.md
  - dharma_swarm/swarm.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- research_methodology
- verification
- product_strategy
- frontend_engineering
inspiration:
- product_surface
- research_synthesis
connected_python_files:
- dharma_swarm/swarm.py
- dharma_swarm/providers.py
- dharma_swarm/evolution.py
- dharma_swarm/archive.py
- dharma_swarm/dgc_cli.py
connected_python_modules:
- dharma_swarm.swarm
- dharma_swarm.providers
- dharma_swarm.evolution
- dharma_swarm.archive
- dharma_swarm.dgc_cli
connected_relevant_files:
  - docs/architecture/JIKOKU_SAMAYA_EXECUTIVE_SUMMARY.md
  - docs/architecture/JIKOKU_SAMAYA_ARCHITECTURE.md
  - docs/architecture/JIKOKU_SAMAYA_SYSTEM_DIAGRAM.md
  - docs/architecture/JIKOKU_SAMAYA_IMPLEMENTATION_ROADMAP.md
  - dharma_swarm/swarm.py
improvement:
  room_for_improvement:
  - 'Surface the decision delta: what should change now because this report exists.'
  - Link findings to exact code, tests, or commits where possible.
  - Distinguish measured facts from operator interpretation.
  - Review whether this file should stay in `docs/reports` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: report
  vault_path: docs/reports/JIKOKU_SAMAYA_INTEGRATION.md
  retrieval_terms:
  - reports
  - jikoku
  - samaya
  - integration
  - guide
  - original
  - manual
  - span
  - wrapping
  - examples
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: 'NOTE : This is the original integration guide with manual span wrapping examples.'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/reports/JIKOKU_SAMAYA_INTEGRATION.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: diagnostic_or_evidence_trace
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
# JIKOKU SAMAYA Integration Guide

**NOTE**: This is the original integration guide with manual span wrapping examples.

**For deep OS integration** (automatic instrumentation), see:
- `docs/architecture/JIKOKU_SAMAYA_EXECUTIVE_SUMMARY.md` — Start here (high-level overview)
- `docs/architecture/JIKOKU_SAMAYA_ARCHITECTURE.md` — Complete technical architecture
- `docs/architecture/JIKOKU_SAMAYA_SYSTEM_DIAGRAM.md` — Visual diagrams
- `docs/architecture/JIKOKU_SAMAYA_IMPLEMENTATION_ROADMAP.md` — Day-by-day implementation guide

---

## What Is It?

**JIKOKU SAMAYA** is a computational efficiency protocol - a burning pledge to account for every moment of compute.

**NOT** about R_V contraction or contemplative consciousness (that's separate research).

**THIS** is about: **5% utilization → 50% = 10x efficiency gain, zero hardware.**

## The Three Convergences

1. **Jain samaya** - Indivisible time unit (Mahavir's 36x warning against pramāda/heedlessness)
2. **Vajrayana samaya** - Sacred commitment (dam tshig, burning pledge)
3. **GPU waste crisis** - Industry at 30-50% utilization, we're at ~5%

## The Protocol

**Span-level tracing** with real timestamps:
- `[JIKOKU:START]` / `[JIKOKU:END]` pairs create measured duration
- Categories: `boot | orient | execute.* | api_call | file_op | update | interrupt`
- ~5-15 spans per session
- Review every 7 sessions for kaizen (continuous improvement)
- Append-only JSONL format (`JIKOKU_LOG.jsonl`)

**The goal**: Detect pramāda (heedlessness) - the tilde in "~3.5 minutes" IS the waste.

## Integration into dharma_swarm

### 1. Wrap Agent Spawning

```python
# dharma_swarm/swarm.py

from dharma_swarm.jikoku_samaya import jikoku_span

async def spawn_agent(
    self,
    name: str,
    role: str,
    prompt: str,
    ...
) -> Agent:
    """Spawn new agent with JIKOKU tracing"""

    with jikoku_span(
        "execute.agent_spawn",
        f"Spawn agent '{name}' ({role})",
        agent_id=name,
        metadata={'role': role, 'prompt_len': len(prompt)}
    ):
        # Existing spawn logic
        agent = Agent(name=name, role=role, ...)
        self._agents[name] = agent
        return agent
```

### 2. Wrap LLM Calls

```python
# dharma_swarm/providers.py

from dharma_swarm.jikoku_samaya import jikoku_span

async def run_with_provider(self, messages, provider_id, ...):
    """Execute with JIKOKU tracing"""

    with jikoku_span(
        "api_call",
        f"LLM call to {provider_id}",
        metadata={
            'provider': provider_id,
            'messages': len(messages),
            'model': provider.model_id
        }
    ) as span_id:
        response = await provider.generate(messages, ...)

        # Add token/cost metadata at end
        jikoku_end(span_id, tokens=response.tokens, cost_usd=response.cost)

        return response
```

### 3. Wrap Evolution Cycles

```python
# dharma_swarm/evolution.py

from dharma_swarm.jikoku_samaya import jikoku_span

async def run_cycle(self, iteration: int) -> CycleResult:
    """Run evolution cycle with JIKOKU tracing"""

    with jikoku_span(
        "execute.evolution_cycle",
        f"Evolution cycle {iteration}",
        metadata={'iteration': iteration}
    ):
        # PROPOSE phase
        with jikoku_span("execute.propose", "Generate proposals"):
            proposals = await self.propose_mutations(...)

        # GATE phase
        with jikoku_span("execute.gate", "Run telos gates"):
            gated = await self.run_gates(proposals)

        # EVALUATE phase
        with jikoku_span("execute.evaluate", "Fitness evaluation"):
            evaluated = await self.evaluate_fitness(gated)

        # SELECT phase
        with jikoku_span("execute.select", "Parent selection"):
            selected = await self.select_parents(evaluated)

        return CycleResult(...)
```

### 4. Wrap File Operations

```python
# dharma_swarm/archive.py

from dharma_swarm.jikoku_samaya import jikoku_span

def save_to_archive(self, entry: ArchiveEntry):
    """Save with JIKOKU tracing"""

    with jikoku_span(
        "file_op",
        f"Save entry to archive",
        metadata={'entry_id': entry.id, 'fitness': entry.fitness}
    ):
        with open(self.archive_path, 'a') as f:
            f.write(entry.to_json() + '\n')
```

### 5. Kaizen Dashboard (Weekly Review)

```python
# dharma_swarm/dgc_cli.py

import typer
from dharma_swarm.jikoku_samaya import jikoku_kaizen

@app.command()
def kaizen():
    """
    Generate JIKOKU SAMAYA kaizen report.

    Reviews last 7 sessions for:
    - Utilization ratio (compute vs wall clock)
    - Pramāda detection (idle time)
    - Optimization targets (longest spans)
    - Efficiency gains possible
    """
    report = jikoku_kaizen(last_n_sessions=7)

    print(f"\n{'='*60}")
    print(f"JIKOKU SAMAYA - Kaizen Report (Last 7 Sessions)")
    print(f"{'='*60}\n")

    print(f"Sessions analyzed: {report['sessions_analyzed']}")
    print(f"Total spans: {report['total_spans']}")
    print(f"Total compute: {report['total_compute_sec']:.1f}s")
    print(f"Wall clock: {report['wall_clock_sec']:.1f}s")
    print(f"\n{'─'*60}")
    print(f"UTILIZATION: {report['utilization_pct']:.1f}%")
    print(f"PRAMĀDA (idle): {report['idle_pct']:.1f}%")
    print(f"{'─'*60}\n")

    # Potential gain
    if report['utilization_pct'] < 50:
        gain = 50 / report['utilization_pct']
        print(f"⚡ POTENTIAL GAIN: {gain:.1f}x efficiency (zero hardware)")
        print(f"   (Path to 50% utilization from {report['utilization_pct']:.1f}%)\n")

    # Category breakdown
    print("Category Breakdown:")
    for cat, stats in sorted(
        report['category_breakdown'].items(),
        key=lambda x: x[1]['total_sec'],
        reverse=True
    ):
        pct = (stats['total_sec'] / report['total_compute_sec']) * 100
        print(f"  {cat:20s} {stats['count']:3d} spans  "
              f"{stats['total_sec']:6.1f}s  ({pct:5.1f}%)")

    # Optimization targets
    print(f"\nTop Optimization Targets:")
    for i, target in enumerate(report['optimization_targets'][:5], 1):
        print(f"  {i}. [{target['category']}] {target['intent']}")
        print(f"     Duration: {target['duration_sec']:.2f}s")

    # Kaizen goals
    print(f"\nKaizen Goals:")
    for goal in report['kaizen_goals']:
        print(f"  • {goal}")

    print(f"\n{'='*60}\n")
```

## Run Tests

```bash
cd ~/dharma_swarm
python -m pytest tests/test_jikoku_samaya.py -v
```

## Usage Example

```python
from dharma_swarm.jikoku_samaya import init_tracer, jikoku_span

# Initialize tracer for session
init_tracer(session_id="dgc-session-001")

# Wrap operations
with jikoku_span("boot", "System initialization"):
    # ... boot logic ...
    pass

with jikoku_span("execute.llm_call", "Generate code", agent_id="coder"):
    response = llm.generate(...)

# Manual span control
span_id = jikoku_start("api_call", "Fetch from API")
try:
    data = api.fetch()
finally:
    jikoku_end(span_id, records=len(data))

# Generate kaizen report
from dharma_swarm.jikoku_samaya import jikoku_kaizen
report = jikoku_kaizen(last_n_sessions=7)
print(f"Utilization: {report['utilization_pct']:.1f}%")
print(f"Pramāda (waste): {report['idle_pct']:.1f}%")
```

## Expected Output Format (JIKOKU_LOG.jsonl)

```jsonl
{"span_id":"session-123-span-1-1234567890","category":"boot","intent":"System initialization","ts_start":"2026-03-08T00:00:00.000000+00:00","ts_end":"2026-03-08T00:00:01.500000+00:00","duration_sec":1.5,"session_id":"session-123","agent_id":null,"task_id":null,"metadata":{}}
{"span_id":"session-123-span-2-1234567891","category":"execute.llm_call","intent":"Generate code","ts_start":"2026-03-08T00:00:02.000000+00:00","ts_end":"2026-03-08T00:00:05.200000+00:00","duration_sec":3.2,"session_id":"session-123","agent_id":"coder","task_id":null,"metadata":{"model":"claude-opus-4","tokens":1500}}
{"span_id":"session-123-span-3-1234567892","category":"api_call","intent":"Fetch from API","ts_start":"2026-03-08T00:00:06.000000+00:00","ts_end":"2026-03-08T00:00:06.800000+00:00","duration_sec":0.8,"session_id":"session-123","agent_id":null,"task_id":null,"metadata":{"records":42}}
```

## The Product Vision

**Million-dollar line**: Span tracing for AI agents
- Pramāda (heedlessness) detection
- Kaizen engine for continuous improvement
- Dharmic time-awareness → measurably superior compute efficiency

**From the protocol**:
> "The tilde in '~3.5 minutes' IS the pramāda."

Every approximation is waste. JIKOKU makes it visible, measurable, improvable.

## Next Steps

1. **Tonight**: Add `jikoku_span` wrappers to swarm.py, providers.py, evolution.py
2. **Week 1**: Run baseline measurements (current utilization %)
3. **Week 2**: Identify top 5 optimization targets from kaizen report
4. **Week 3**: Implement fixes, re-measure, calculate actual efficiency gains
5. **Month 1**: Iterate kaizen loop → 50% utilization goal

**Goal**: 10x efficiency gain, zero hardware. Path from 5% → 50% utilization.

---

**JSCA!**
