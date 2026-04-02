---
title: Provider Matrix Harness
path: docs/architecture/PROVIDER_MATRIX_HARNESS.md
slug: provider-matrix-harness
doc_type: documentation
status: active
summary: 'The live provider/model matrix harness is wired into the CLI as:'
source:
  provenance: repo_local
  kind: documentation
  origin_signals: []
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- product_strategy
- operations
- machine_learning
inspiration:
- operator_runtime
connected_python_files:
- dharma_swarm/codex_cli.py
- dharma_swarm/dgc_cli.py
- dharma_swarm/model_hierarchy.py
- dharma_swarm/provider_matrix.py
- dharma_swarm/runtime_artifacts.py
connected_python_modules:
- dharma_swarm.codex_cli
- dharma_swarm.dgc_cli
- dharma_swarm.model_hierarchy
- dharma_swarm.provider_matrix
- dharma_swarm.runtime_artifacts
connected_relevant_files:
- dharma_swarm/codex_cli.py
- dharma_swarm/dgc_cli.py
- dharma_swarm/model_hierarchy.py
- dharma_swarm/provider_matrix.py
- dharma_swarm/runtime_artifacts.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/architecture/PROVIDER_MATRIX_HARNESS.md
  retrieval_terms:
  - provider
  - matrix
  - harness
  - live
  - model
  - wired
  - cli
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.55
  coordination_comment: 'The live provider/model matrix harness is wired into the CLI as:'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/PROVIDER_MATRIX_HARNESS.md reinforces its salience without needing a separate message.
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
# Provider Matrix Harness

The live provider/model matrix harness is wired into the CLI as:

```bash
dgc provider-matrix [options]
```

## What It Does

- Builds a curated target matrix from the canonical provider hierarchy.
- Keeps `Codex` and `Opus` sovereign at the top of the lane order.
- Expands delegated lanes across `GLM`, `Kimi`, `MiniMax`, `Qwen`, and other cheap/open providers.
- Runs a fixed deployment-oriented prompt corpus.
- Scores responses for uptime, schema compliance, and latency.
- Writes operator-facing JSON + Markdown leaderboard artifacts.

## Profiles

- `quick`
  Fast sanity check across the sovereign pair and a small delegated lane set.

- `live25`
  Broad live matrix with 25 curated provider/model lanes.
  The scheduler is prompt-major, so the default budget reaches delegated lanes before it spends on repeated sovereign passes.

## Default Corpus

`deployment`

This corpus asks every lane to produce compact JSON for:

- best deployment wedge
- sovereign/delegated handoff plan
- launch guardrail recommendation

## Budget Model

The harness uses synthetic cost units so it can stop before burning too much paid capacity:

- `free = 1`
- `cheap = 2`
- `paid = 5`

`--budget-units` is not a dollar estimator. It is a deterministic stop condition for mixed-lane sweeps.

## Recommended Runs

Quick local pass:

```bash
dgc provider-matrix --profile quick --max-prompts 1 --budget-units 12
```

Broad live sweep:

```bash
dgc provider-matrix --profile live25 --budget-units 40
```

Deep repeat pass after the broad sweep:

```bash
dgc provider-matrix --profile live25 --max-prompts 3 --budget-units 80
```

Machine-readable output:

```bash
dgc provider-matrix --profile live25 --json
```

Include lanes even when auth/binaries are missing:

```bash
dgc provider-matrix --profile live25 --include-unavailable
```

## Artifacts

By default each run writes:

- `~/.dharma/shared/provider_matrix_<RUN_ID>.json`
- `~/.dharma/shared/provider_matrix_<RUN_ID>.md`

Use `--artifact-dir PATH` to redirect output or `--no-artifacts` to suppress writes.

## Status Semantics

- `ok`: response matched the required JSON contract
- `schema_invalid`: provider answered, but did not follow the required schema
- `provider_error`: CLI/provider returned an error banner or access failure in-band
- `timeout`, `auth_failed`, `missing_config`, `unknown_model`, `unreachable`: runtime failures
