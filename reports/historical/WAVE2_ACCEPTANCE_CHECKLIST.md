---
title: Wave 2 Acceptance Checklist
path: reports/historical/WAVE2_ACCEPTANCE_CHECKLIST.md
slug: wave-2-acceptance-checklist
doc_type: note
status: active
summary: Use this after Claude's Wave 2 completes.
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - scripts/wave2_acceptance_gate.sh
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- swarm_intelligence
- software_architecture
- research_methodology
- verification
- machine_learning
inspiration:
- stigmergy
- verification
- operator_runtime
- research_synthesis
connected_python_files:
- tests/tui/test_stream_output_observability.py
- tests/test_claude_cli.py
- tests/test_dgc_cli.py
- tests/test_dgc_cli_cron.py
- tests/test_dgc_cli_memory_retrospectives.py
connected_python_modules:
- tests.tui.test_stream_output_observability
- tests.test_claude_cli
- tests.test_dgc_cli
- tests.test_dgc_cli_cron
- tests.test_dgc_cli_memory_retrospectives
connected_relevant_files:
- scripts/wave2_acceptance_gate.sh
- tests/tui/test_stream_output_observability.py
- tests/test_claude_cli.py
- tests/test_dgc_cli.py
- tests/test_dgc_cli_cron.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: reports/historical/WAVE2_ACCEPTANCE_CHECKLIST.md
  retrieval_terms:
  - wave2
  - acceptance
  - checklist
  - wave
  - use
  - after
  - claude
  - completes
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.55
  coordination_comment: Use this after Claude's Wave 2 completes.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising reports/historical/WAVE2_ACCEPTANCE_CHECKLIST.md reinforces its salience without needing a separate message.
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
# Wave 2 Acceptance Checklist

Use this after Claude's Wave 2 completes.

## Hard Gates (must pass)
- [ ] Full test suite passes.
- [ ] No false-success semantics (failed runs are not marked completed).
- [ ] Canonical CLI path works (`/opt/homebrew/bin/dgc`).
- [ ] No new split-brain runtime path introduced.
- [ ] Telos gates remain enforceable.
- [ ] Evolution path has working rollback with lineage.

## Quality Gates (should pass)
- [ ] New modules have focused tests with clear behavioral assertions.
- [ ] TUI/CLI commands are additive and backward compatible.
- [ ] No fake stubs in critical paths (`gate`, `sandbox`, `promote`, `rollback`).
- [ ] Process-level observability improved (runtime/git/truth visibility).

## Living Layers Guardrail
- [ ] `specs/research_living_layers/` remains intact as v2+ north star.
- [ ] Living-layer features (Shakti/Stigmergy/Subconscious) are either:
  - [ ] integrated with tests and governance checks, or
  - [ ] explicitly deferred with rationale.

## One-command verification
Run:

```bash
scripts/wave2_acceptance_gate.sh --triple
```

Output report path:

- `reports/verification/wave2_acceptance_YYYYMMDD_HHMMSS.md`
