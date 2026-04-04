---
title: Model Routing Canon
path: docs/architecture/MODEL_ROUTING_CANON.md
slug: model-routing-canon
doc_type: note
status: active
summary: This is the single story for model and provider selection in dharma swarm.
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - dharma_swarm/model_hierarchy.py
  - dharma_swarm/free_fleet.py
  - dharma_swarm/model_catalog.py
  - dharma_swarm/provider_policy.py
  - dharma_swarm/providers.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- research_methodology
- machine_learning
inspiration:
- operator_runtime
- research_synthesis
connected_python_files:
- dharma_swarm/model_hierarchy.py
- dharma_swarm/free_fleet.py
- dharma_swarm/model_catalog.py
- dharma_swarm/provider_policy.py
- dharma_swarm/providers.py
connected_python_modules:
- dharma_swarm.model_hierarchy
- dharma_swarm.free_fleet
- dharma_swarm.model_catalog
- dharma_swarm.provider_policy
- dharma_swarm.providers
connected_relevant_files:
- dharma_swarm/model_hierarchy.py
- dharma_swarm/free_fleet.py
- dharma_swarm/model_catalog.py
- dharma_swarm/provider_policy.py
- dharma_swarm/providers.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: docs/architecture/MODEL_ROUTING_CANON.md
  retrieval_terms:
  - model
  - routing
  - canon
  - single
  - story
  - provider
  - selection
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: This is the single story for model and provider selection in dharma swarm.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/MODEL_ROUTING_CANON.md reinforces its salience without needing a separate message.
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
# Model Routing Canon

This is the single story for model and provider selection in `dharma_swarm`.

## Source Of Truth

- Provider lanes, default models, and paid/free ordering live in [model_hierarchy.py](/Users/dhyana/dharma_swarm/dharma_swarm/model_hierarchy.py).
- Live free-tier OpenRouter rosters live in [free_fleet.py](/Users/dhyana/dharma_swarm/dharma_swarm/free_fleet.py).
- Human-friendly selectors such as `top open models` and `tier one models` live in [model_catalog.py](/Users/dhyana/dharma_swarm/dharma_swarm/model_catalog.py).
- Routing execution still lives in [provider_policy.py](/Users/dhyana/dharma_swarm/dharma_swarm/provider_policy.py) and [providers.py](/Users/dhyana/dharma_swarm/dharma_swarm/providers.py).

## Canonical Selectors

- `top_open_models`
  Open-model lanes across the shared router.
- `driver_models`
  Primary driver lanes for sovereign execution and escalation.
- `free_models`
  All currently discovered free OpenRouter models.
- `tier1_models`
  Heavy free reasoning models.
- `tier2_models`
  General-purpose free models.
- `tier3_models`
  Fast/light free models.

Natural aliases are supported:

- `top open models`
- `free models`
- `tier one models`
- `tier1`

## Runtime Contract

Use the selector metadata instead of hand-rolled provider allowlists:

```python
metadata = {
    "model_catalog_selector": "top open models",
}
```

That expands into the routing keys the runtime already understands:

- `allow_provider_routing`
- `available_provider_types`
- `preferred_provider`
- `preferred_model`

This expansion is now honored in:

- [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py)
- [agent_runner.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py)
- [worker_spawn.py](/Users/dhyana/dharma_swarm/dharma_swarm/worker_spawn.py)

## Inspection

```bash
dgc model-catalog
dgc model-catalog "top open models"
dgc model-catalog "tier one models" --json
```

## Mental Model

1. Human or spec chooses a canonical selector.
2. [model_catalog.py](/Users/dhyana/dharma_swarm/dharma_swarm/model_catalog.py) resolves it into routing metadata.
3. Agent and worker execution honor that metadata through the shared router.
4. [provider_policy.py](/Users/dhyana/dharma_swarm/dharma_swarm/provider_policy.py) and [providers.py](/Users/dhyana/dharma_swarm/dharma_swarm/providers.py) still make the final path decision, but they now start from one shared vocabulary instead of ad hoc lists.
