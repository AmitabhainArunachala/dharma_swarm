---
title: Ecosystem Autoresearch — Full Dhyana System
path: program_ecosystem.md
slug: ecosystem-autoresearch-full-dhyana-system
doc_type: note
status: active
summary: Multi-repo variant of program.md. Fires across the entire ecosystem, not just dharma swarm. Use this when you want broader improvement across all active repos.
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - program.md
  - dharma_swarm/rv.py
  - program_ecosystem.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- verification
- frontend_engineering
inspiration:
- verification
- operator_runtime
connected_python_files:
- dharma_swarm/rv.py
connected_python_modules:
- dharma_swarm.rv
connected_relevant_files:
- program.md
- dharma_swarm/rv.py
- docs/archive/AGENT_SWARM_SYNTHESIS.md
- CLAUDE.md
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
  vault_path: program_ecosystem.md
  retrieval_terms:
  - program
  - ecosystem
  - autoresearch
  - full
  - dhyana
  - system
  - multi
  - repo
  - variant
  - fires
  - across
  - entire
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: Multi-repo variant of program.md. Fires across the entire ecosystem, not just dharma swarm. Use this when you want broader improvement across all active repos.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising program_ecosystem.md reinforces its salience without needing a separate message.
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
# Ecosystem Autoresearch — Full Dhyana System

Multi-repo variant of [program.md](program.md). Fires across the entire ecosystem,
not just dharma_swarm. Use this when you want broader improvement across all active repos.

## The Ecosystem

| Repo | Path | Metric | Status |
|------|------|--------|--------|
| **dharma_swarm** | `~/dharma_swarm/` | `pytest tests/ -q` (3017 pass) | PRIMARY — living runtime |
| **mech-interp** | `~/mech-interp-latent-lab-phase1/` | `pytest tests/ -q` | ACTIVE — R_V paper code |
| **PSMV** | `~/Persistent-Semantic-Memory-Vault/` | file integrity checks | KNOWLEDGE — 8K+ files |

## How This Differs from Single-Repo

In single-repo mode, you loop on one codebase. In ecosystem mode, you **rotate** across
repos, spending a few experiments on each before moving to the next. This prevents
tunnel vision and finds cross-repo integration issues.

## Setup

1. **Agree on a run tag** (e.g. `eco-mar14`).
2. **Create branch in dharma_swarm**: `cd ~/dharma_swarm && git checkout -b autoresearch/<tag>`
3. **Read baselines** for each repo:
   ```bash
   cd ~/dharma_swarm && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3
   cd ~/mech-interp-latent-lab-phase1 && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3
   ```
4. **Initialize results.tsv** in `~/dharma_swarm/results.tsv` (single log for all repos).
5. **Confirm and go**.

## Logging Results

```
commit	repo	tests_passed	tests_failed	status	description
```

Extra column: `repo` — which repo this experiment targeted (`dharma_swarm`, `mech-interp`,
`psmv`).

## The Rotation

LOOP FOREVER with rotation:

```
Round 1-5:   dharma_swarm (core runtime)
Round 6-8:   mech-interp (R_V paper code)
Round 9-10:  cross-repo (integration, shared patterns)
Repeat
```

### dharma_swarm rounds (5 per rotation)
- Follow the rules from `program.md` exactly
- Focus: bugs, tests, refactoring, wiring orphaned modules

### mech-interp rounds (3 per rotation)
- **Scope**: `~/mech-interp-latent-lab-phase1/`
- **Modifiable**: `geometric_lens/*.py`, `scripts/*.py`, `tests/*.py`
- **Read-only**: `prompts/`, `R_V_PAPER/`, raw data files
- **Metric**: `python3 -m pytest tests/ -q --tb=no`
- **Priorities**:
  1. Fix broken tests or imports
  2. Harden `geometric_lens/metrics.py` (the core R_V computation)
  3. Add tests for scripts that lack them
  4. Clean up deprecated code paths

### Cross-repo rounds (2 per rotation)
- Look for patterns that should be shared (e.g., R_V measurement code exists in
  both `dharma_swarm/rv.py` and `mech-interp/geometric_lens/metrics.py`)
- Check that dharma_swarm's `bridge.py` can actually import from mech-interp
- Verify ecosystem_map.py paths are still valid
- Find dead references across repos

## NEVER STOP

Same rule as single-repo: never pause, never ask. The human is asleep. You are
autonomous. Rotate through the repos indefinitely.

## When to Use Which

- **`program.md`**: overnight runs focused purely on dharma_swarm quality
- **`program_ecosystem.md`**: weekend runs covering the whole system
- **Both**: use `/loop` in Claude Code to fire either one on a schedule
