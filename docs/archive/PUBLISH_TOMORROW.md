---
title: Publish Tomorrow Checklist
path: docs/archive/PUBLISH_TOMORROW.md
slug: publish-tomorrow-checklist
doc_type: report
status: archival
summary: 'Canonical repo target: - https://github.com/shakti-saraswati/dharma swarm'
source:
  provenance: repo_local
  kind: report
  origin_signals:
  - scripts/publish_canonical.sh
  cited_urls:
  - https://github.com/shakti-saraswati/dharma_swarm`
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- software_architecture
inspiration:
- knowledge_management
- software_architecture
connected_python_files:
- scripts/ginko_run_signals.py
- scripts/live_organism_run.py
- scripts/repo_xray.py
- scripts/run_concept_extraction.py
- scripts/self_optimization/run_production_self_optimization.py
connected_python_modules:
- scripts.ginko_run_signals
- scripts.live_organism_run
- scripts.repo_xray
- scripts.run_concept_extraction
- scripts.self_optimization.run_production_self_optimization
connected_relevant_files:
- scripts/publish_canonical.sh
- scripts/ginko_run_signals.py
- scripts/live_organism_run.py
- scripts/repo_xray.py
- scripts/run_concept_extraction.py
improvement:
  room_for_improvement:
  - 'Surface the decision delta: what should change now because this report exists.'
  - Link findings to exact code, tests, or commits where possible.
  - Distinguish measured facts from operator interpretation.
  - Review whether this file should stay in `docs/reports` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: report
  vault_path: docs/archive/PUBLISH_TOMORROW.md
  retrieval_terms:
  - reports
  - publish
  - tomorrow
  - checklist
  - canonical
  - repo
  - target
  - https
  - github
  - com
  - shakti
  - saraswati
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: archive
  semantic_weight: 0.55
  coordination_comment: 'Canonical repo target: - https://github.com/shakti-saraswati/dharma swarm'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/archive/PUBLISH_TOMORROW.md reinforces its salience without needing a separate message.
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
# Publish Tomorrow Checklist

Canonical repo target:
- `https://github.com/shakti-saraswati/dharma_swarm`

## One command
From `/Users/dhyana/dharma_swarm`:

```bash
bash scripts/publish_canonical.sh
```

## If auth is stale
Run:

```bash
env -u GITHUB_TOKEN -u GH_TOKEN gh auth login --hostname github.com --git-protocol https --web
```

Then run:

```bash
bash scripts/publish_canonical.sh
```

## What this script does
1. Verifies `gh` auth is valid.
2. Creates `shakti-saraswati/dharma_swarm` as private if missing.
3. Sets local `origin` to the canonical URL.
4. Pushes `main` with upstream tracking.
