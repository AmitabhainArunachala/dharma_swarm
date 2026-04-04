---
title: DHARMA SWARM — Briefing for Parallel Agent
path: docs/archive/BRIEFING.md
slug: dharma-swarm-briefing-for-parallel-agent
doc_type: documentation
status: archival
summary: 'Date : 2026-03-04 Status : Phase 1 complete, committed, 115/115 tests passing Location : ~/dharma swarm/'
source:
  provenance: repo_local
  kind: documentation
  origin_signals: []
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
- operations
inspiration:
- verification
- operator_runtime
- research_synthesis
connected_python_files:
- dharma_swarm/cli.py
- dharma_swarm/telos_gates.py
connected_python_modules:
- dharma_swarm.cli
- dharma_swarm.telos_gates
connected_relevant_files:
- dharma_swarm/cli.py
- dharma_swarm/telos_gates.py
- docs/archive/FIRST_LIVE_RUN_REPORT.md
- docs/archive/OVERNIGHT_BUILD_PLAN.md
- docs/archive/TEST_STRATEGY.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs/archive` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/archive/BRIEFING.md
  retrieval_terms:
  - archive
  - briefing
  - parallel
  - agent
  - date
  - '2026'
  - status
  - phase
  - complete
  - committed
  - '115'
  - tests
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: archive
  semantic_weight: 0.45
  coordination_comment: 'Date : 2026-03-04 Status : Phase 1 complete, committed, 115/115 tests passing Location : ~/dharma swarm/'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/archive/BRIEFING.md reinforces its salience without needing a separate message.
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
# DHARMA SWARM — Briefing for Parallel Agent

**Date**: 2026-03-04
**Status**: Phase 1 complete, committed, 115/115 tests passing
**Location**: `~/dharma_swarm/`

## What Is It

DHARMA SWARM (Darwin-Heuristic Autonomous Recursive Meta-Agent Swarm) is a Python package that orchestrates AI agent swarms. It was built in a single session using 8 parallel Claude Code agents, each writing one module.

## What It Can Do Right Now

```bash
cd ~/dharma_swarm
pip install -e ".[dev]"
pytest tests/ -v                              # 115 tests pass
python3 -m dharma_swarm.cli init              # creates .dharma/ state dir
python3 -m dharma_swarm.cli spawn --name w1 --role coder
python3 -m dharma_swarm.cli task create "Do something"
python3 -m dharma_swarm.cli status
python3 -m dharma_swarm.cli memory store "remember this"
python3 -m dharma_swarm.cli memory recall
```

## Architecture (7 Layers, Phase 1 Scope)

```
L7: Dharma Layer   → telos_gates.py    8 safety gates (ahimsa, satya, etc.)
L6: Darwin Engine  → NOT BUILT YET     Self-evolution (Phase 2)
L5: Orchestrator   → orchestrator.py   Fan-out/fan-in task routing
L4: Swarm          → swarm.py          Agent pool + lifecycle
L3: Memory Palace  → memory.py         5-layer strange loop (SQLite)
L2: Nervous System → message_bus.py    Pub/sub agent messaging (SQLite)
L1: Substrate      → providers.py      LLM abstraction (Anthropic/OpenAI)
                     sandbox.py        Subprocess execution
```

Supporting: `models.py` (15 Pydantic models), `task_board.py` (CRUD + FSM), `agent_runner.py` (agent lifecycle), `cli.py` (Typer), `mcp_server.py` (MCP tools)

## What It Ports From

| Component | Source | Lines |
|-----------|--------|-------|
| Telos Gates (8 dharmic gates) | `~/dgc-core/hooks/telos_gate.py` | 183→224 |
| Strange Loop Memory (5 layers) | `~/dgc-core/memory/strange_loop.py` | 261→242 |
| Message Bus (SQLite pub/sub) | `~/.chaiwala/message_bus.py` | 419→233 |

All three were ported from sync to async, from file-based to SQLite, from scripts to Pydantic-validated classes.

## What It Does NOT Do Yet

1. **No real LLM calls** — agents return mock results without API keys set
2. **No self-evolution** — Layer 6 (Darwin Engine) is the entire point and isn't built
3. **No persistence daemon** — CLI is run-and-exit, not a long-running service
4. **No RAG/vector search** — memory is keyword-based SQLite, not semantic
5. **Not better than Claude Code native teams** — yet. The differentiator is L6.

## Key Design Decisions

- **SQLite everywhere** (zero infra — no Redis, no Postgres, no Docker)
- **Async-first** (aiosqlite, httpx, asyncio subprocess)
- **Pydantic v2** (strict validation, JSON serialization)
- **Duck-typed integration** (orchestrator doesn't import agent_runner directly — uses Protocols)
- **Immutable Dharma Layer** (telos_gates.py never self-modifies, even when Darwin Engine exists)

## The Big Question

**What justifies this existing when Claude Code native teams already work?**

Answer: **The Darwin Engine (Phase 2).** Self-evolving agents that read their own code, propose modifications, and accept/reject based on test results — gated by dharmic safety gates. This is the DGM paper's architecture but with Akram Vignan ethics baked in at the immutable layer.

Without Phase 2, this is just another agent coordinator. With Phase 2, it's a self-improving system with a conscience.

## Research Context Available

4 deep research docs in `~/Downloads/`:
- `research_swarm_frameworks.md` — LangGraph, CrewAI, AutoGen, DSPy
- `research_self_evolving.md` — DGM, ADAS, Voyager, test-gated evolution
- `research_memory_context.md` — MemGPT/Letta, RAG, knowledge graphs
- `research_tools_sandboxes.md` — MCP, E2B, Daytona, Modal

## Verification

```bash
cd ~/dharma_swarm
python3 -m pytest tests/ -v          # 115 pass in <1s
python3 -c "from dharma_swarm.telos_gates import check_action; print(check_action('rm -rf /').decision)"  # block
python3 -c "from dharma_swarm.telos_gates import check_action; print(check_action('echo hello').decision)"  # allow
```

## Honest Assessment

Phase 1 is solid — tested, committed, installable. But it's plumbing. The value is in what gets built on top of it. The critical path is: Phase 1.5 (real LLM integration test) → Phase 2 (Darwin Engine) → then it becomes something genuinely new.
